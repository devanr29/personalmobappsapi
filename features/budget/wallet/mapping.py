"""Pure snake_case<->Wallet-JSON conversions. No DB, no HTTP, no clock —
same discipline as compute.py/insights.py, which is what makes those cheap
to test and safe to reason about. sync.py is the only caller; it supplies
whatever local lookups (category/wallet id maps) a function needs as plain
dicts rather than this module reaching into the DB itself.

See docs/BUDGETBAKERS_API.md's "Entity <-> local schema mapping" table for
the field-by-field rationale. amount handling assumes the caller always
requests records with convertTo=IDR (features/budget/wallet/client.py's
pull call does this) — see record_amount_idr()'s docstring for why that's
a hard requirement, not an optimization.

Transfers: Wallet represents a transfer as two paired "mirror" records on
two accounts. Collapsing a pair back into our single wallet_id/
transfer_wallet_id row requires reliably identifying each record's
partner, and the exact shape of Wallet's mirror-link field wasn't
confirmed against the live schema (see client.py's module docstring on
the BETA API's unconfirmed envelopes). Rather than guess at a field name
for financial data, each leg of a transfer is pulled as its own
independent expense/income transaction (source='wallet', category left
unset since Transfer is a restricted system category) — every wallet's
balance still ends up correct, it just shows as two rows instead of one
elegant transfer. sync.py never pushes transfers back to Wallet for the
same reason — see its module docstring.

Restricted system category UUIDs, from docs/BUDGETBAKERS_API.md:"""
WALLET_DEBT_CATEGORY_ID = "5c5c4e20-00c8-8000-8000-000000000000"
WALLET_TRANSFER_CATEGORY_ID = "5c5c4e21-00c8-8000-8000-000000000000"
WALLET_SHOPPING_LIST_CATEGORY_ID = "5c5c4e22-00c8-8000-8000-000000000000"
WALLET_UNCATEGORIZED_CATEGORY_ID = "5c5c4e23-00c8-8000-8000-000000000000"
RESTRICTED_CATEGORY_IDS = {
    WALLET_DEBT_CATEGORY_ID, WALLET_TRANSFER_CATEGORY_ID,
    WALLET_SHOPPING_LIST_CATEGORY_ID, WALLET_UNCATEGORIZED_CATEGORY_ID,
}

# accountType -> local budget_wallets.kind (free-text column, no enum) —
# CreditCard/Investment/Loan/etc. are mobile-app-managed and read-only via
# the API (see the write matrix), but still pulled for visibility.
_ACCOUNT_TYPE_TO_KIND = {
    "Cash": "cash", "General": "cash",
    "CurrentAccount": "bank", "SavingAccount": "bank", "Overdraft": "bank",
    "CreditCard": "credit", "Investment": "investment",
    "Loan": "loan", "Mortgage": "loan",
    "Insurance": "other", "Bonus": "other",
}
_KIND_TO_ACCOUNT_TYPE = {"cash": "Cash", "bank": "CurrentAccount"}

# budget_categories.kind ('fixed'|'variable') <-> Wallet cardinality
_CARDINALITY_TO_KIND = {"must": "fixed", "need": "fixed", "want": "variable", "none": "variable"}
_KIND_TO_CARDINALITY = {"fixed": "must", "variable": "want"}


def _embed_id(value):
    """Wallet embeds a related entity as either a bare id string or a
    small object with at least an 'id' (CategoryEmbed/LabelEmbed pattern)
    — accept either so a schema tweak on their side doesn't break every
    caller here."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get("id")
    return value


def is_restricted_category(remote_category_id) -> bool:
    return remote_category_id in RESTRICTED_CATEGORY_IDS


def round_idr(value) -> int:
    """Accepts either a bare number or a MonetaryAmount-shaped object
    ({"value": ..., "currencyCode": ...}) — confirmed against the live API
    2026-08-12: goals' targetAmount/initialAmount and records' amount both
    come back as the object form (records' convertedAmount already went
    through this), while standingOrders' amount is a bare number. Rather
    than track which field uses which shape, unwrap dicts everywhere."""
    if isinstance(value, dict):
        value = value.get("value")
    if value is None:
        return 0
    return int(round(float(value)))


# ================================================================
# ACCOUNTS <-> WALLETS
# ================================================================
def account_to_wallet_fields(account: dict) -> dict:
    """account must already be confirmed currencyCode == 'IDR' by the
    caller — the local ledger has no currency column, so a non-IDR
    account's opening_balance can't be represented and must be skipped
    upstream (sync.py's skip list), not silently misconverted here.

    The live API has no top-level initialBalance field — confirmed
    2026-08-12: it nests under balance.initial (balance also carries
    currentBalance/rawCurrentBalance, neither pulled here since the local
    ledger derives its own running balance from opening_balance + booked
    transactions). Bare initialBalance is kept as a fallback for whichever
    shape a create/update response turns out to use."""
    balance = account.get("balance") or {}
    opening_balance = balance.get("initial")
    if opening_balance is None:
        opening_balance = account.get("initialBalance", 0)
    return {
        "name": account["name"],
        "kind": _ACCOUNT_TYPE_TO_KIND.get(account.get("accountType"), "cash"),
        "opening_balance": round_idr(opening_balance),
        "spendable": not account.get("excludeFromStats", False),
        "archived": bool(account.get("archived", False)),
    }


def wallet_to_account_payload(wallet: dict) -> dict:
    """For POST /v1/api/accounts — single item, currencyCode fixed to IDR
    since that's the only currency the local ledger stores."""
    return {
        "name": wallet["name"][:80],
        "accountType": _KIND_TO_ACCOUNT_TYPE.get(wallet["kind"], "General"),
        "currencyCode": "IDR",
        "initialBalance": wallet["opening_balance"],
    }


def wallet_to_account_patch(wallet: dict) -> dict:
    return {
        "name": wallet["name"][:80],
        "archived": bool(wallet["archived"]),
        "excludeFromStats": not wallet["spendable"],
        "initialBalance": wallet["opening_balance"],
    }


# ================================================================
# CATEGORIES
# ================================================================
def category_to_local_fields(category: dict) -> dict:
    cardinality = category.get("cardinality") or "none"
    return {
        "name": category["name"],
        "kind": _CARDINALITY_TO_KIND.get(cardinality, "variable"),
        "archived": bool(category.get("archived", False)),
    }


def local_category_to_custom_payload(category: dict, parent_id: str) -> dict:
    """For POST /v1/api/categories/custom. parent_id must be a system
    (base) category UUID resolved by the caller — see
    docs/BUDGETBAKERS_API.md's restricted-categories note; Debt/Transfer/
    Shopping List/Uncategorized can never be a parentId."""
    return {
        "name": category["name"][:80],
        "parentId": parent_id,
        "cardinality": _KIND_TO_CARDINALITY.get(category["kind"], "want"),
    }


# ================================================================
# LABELS
# ================================================================
def label_to_local_fields(label: dict) -> dict:
    return {"name": label["name"], "color": label.get("color"), "archived": bool(label.get("archived", False))}


def local_label_to_payload(label: dict) -> dict:
    return {"name": label["name"][:80], "color": label.get("color")}


# ================================================================
# GOALS — pull-only, no Wallet write endpoint exists.
# ================================================================
def goal_to_local_fields(goal: dict) -> dict:
    return {
        "name": goal["name"],
        "kind": "sinking",
        "target_amount": round_idr(goal.get("targetAmount")),
        "target_date": goal.get("desiredDate"),
        "reserve_from_free": False,  # pulled goals don't drive our reservation math by default
        "archived": goal.get("state") in ("paused", "reached"),
    }


# ================================================================
# STANDING ORDERS -> BILLS — pull-only, no Wallet write endpoint exists.
# recurrenceRule is an RFC 5545 RRULE string (e.g. "FREQ=MONTHLY;..."); we
# only need a coarse cadence label plus dueDate's day-of-month, not a full
# RRULE parser — bills.py's own cadence handling is already just monthly.
# ================================================================
def _cadence_from_rrule(rule: str) -> str:
    rule = (rule or "").upper()
    if "FREQ=WEEKLY" in rule:
        return "weekly"
    if "FREQ=YEARLY" in rule:
        return "yearly"
    return "monthly"


def standing_order_category_id(order: dict):
    return _embed_id(order.get("category"))


def standing_order_to_bill_fields(order: dict) -> dict:
    due_date = order.get("dueDate")
    due_day = None
    if due_date and len(due_date) >= 10:
        try:
            due_day = int(due_date[8:10])
        except ValueError:
            due_day = None
    return {
        "name": order["name"],
        "amount": round_idr(order.get("amount")),
        "due_day": due_day,
        "cadence": _cadence_from_rrule(order.get("recurrenceRule")),
        "active": True,
    }


# ================================================================
# RECORDS <-> TRANSACTIONS
# ================================================================
def record_amount_idr(record: dict) -> int:
    """Requires the record to have been fetched with convertTo=IDR (every
    call in wallet/client.py's pull path does this) — record['amount'] is
    in the record's OWN account currency, which may not be IDR, and this
    module has no exchange-rate logic of its own. A record missing
    convertedAmount is a caller bug (the fetch forgot convertTo), not a
    value to guess at, so this raises rather than silently falling back to
    the wrong-currency amount."""
    converted = record.get("convertedAmount")
    if not isinstance(converted, dict) or "value" not in converted:
        raise ValueError(
            f"record {record.get('id')} has no convertedAmount — "
            "was it fetched without convertTo=IDR?"
        )
    return round_idr(converted["value"])


def record_direction(record: dict) -> str:
    if record.get("recordType") == "income" or record_amount_idr(record) >= 0:
        return "income"
    return "expense"


def record_category_id(record: dict):
    """Remote category id (or None) — sync.py resolves it to a local id
    via budget_wallet_links; this module stays DB-free."""
    return _embed_id(record.get("category"))


def record_label_ids(record: dict) -> list:
    """Remote label ids (or []) — same resolve-elsewhere contract as
    record_category_id()."""
    return [lid for lid in (_embed_id(x) for x in (record.get("labels") or [])) if lid]


def record_to_transaction_fields(record: dict, *, category_id=None, wallet_id=None, transfer_wallet_id=None) -> dict:
    """category_id/wallet_id/transfer_wallet_id are LOCAL ids, already
    resolved by sync.py from the remote UUIDs via budget_wallet_links —
    this function does no lookups of its own."""
    direction = "transfer" if transfer_wallet_id is not None else record_direction(record)
    amount = abs(record_amount_idr(record))
    return {
        "occurred_at": (record.get("recordDate") or "").replace("T", " ")[:16],
        "amount": amount,
        "direction": direction,
        "category_id": category_id,
        "wallet_id": wallet_id,
        "transfer_wallet_id": transfer_wallet_id,
        "note": record.get("note"),
        "source": "wallet",
        "raw_input": record.get("id"),
    }


def transaction_to_record_payload(txn: dict, *, account_id: str, category_id=None, label_ids=None) -> dict:
    """For POST /v1/api/records. account_id/category_id are Wallet UUIDs,
    already resolved by sync.py. Sign follows Wallet's convention
    (negative = expense), the inverse of our direction+positive-amount
    scheme. paymentType is hardcoded to 'cash' — the local ledger has no
    payment-method field to map from."""
    signed_amount = -txn["amount"] if txn["direction"] == "expense" else txn["amount"]
    payload = {
        "accountId": account_id,
        "amount": signed_amount,
        "recordDate": txn["occurred_at"].replace(" ", "T") + ":00Z",
        "paymentType": "cash",
    }
    if category_id:
        payload["categoryId"] = category_id
    if txn.get("note"):
        payload["note"] = txn["note"][:255]
    if label_ids:
        payload["labelIds"] = label_ids
    return payload


def transaction_to_record_patch(txn: dict, *, category_id=None, label_ids=None) -> dict:
    """For PATCH /v1/api/records — only the fields Wallet allows patching
    on metadata (see docs/BUDGETBAKERS_API.md); recordDate/amount/
    recordState are intentionally omitted here since they're locked on
    bank-synced records and sync.py never pushes to those anyway."""
    patch = {}
    if category_id:
        patch["categoryId"] = category_id
    if txn.get("note") is not None:
        patch["note"] = txn["note"][:255]
    if label_ids is not None:
        patch["labelIds"] = label_ids
    return patch
