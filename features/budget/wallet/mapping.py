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
elegant transfer.

Pull-only. Only accounts and records are synced now, so this module holds
only the Wallet->local direction for those two (see sync.py's module
docstring). The local->Wallet payload builders and the category / label /
goal / standing-order converters were removed with the push direction on
2026-08-31; `git log -- features/budget/wallet/` has them.

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

# budget_categories.kind ('fixed'|'variable') <-> Wallet cardinality


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
