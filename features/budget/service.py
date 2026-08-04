"""Orchestration layer: gathers ledger data via repo, calls the pure
compute_budget_by_id(), and returns period-scoped views. No route/HTTP
concerns — those live in blueprint.py."""
import datetime

from config import PAYROLL_DAY, now_jkt
from features.budget import repo
from features.budget.compute import compute_budget_by_id
from features.budget.errors import BudgetNotFound, BudgetValidationError
from features.budget.periods import ensure_current_period


def build_period_view():
    """Returns the full compute_budget_by_id() dict for the current
    period, plus a period_id key, or None if the feature hasn't been set
    up yet (no wallets configured) — mirrors the legacy "never computed"
    null state."""
    wallets = repo.get_wallets()
    if not wallets:
        return None

    period = ensure_current_period(PAYROLL_DAY)
    now = now_jkt().date()
    end = datetime.date.fromisoformat(period["end_date"])
    days_left = max((end - now).days, 0)

    bills = repo.get_bills()
    paid_bill_ids = repo.get_paid_bill_ids(period["id"])

    variable = repo.get_categories(kind="variable")
    variable_ids = {c["id"] for c in variable}
    categories = [{"id": c["id"], "name": c["name"], "budget": c["monthly_limit"] or 0} for c in variable]
    spend_rows = repo.spend_by_category_for_period(period["id"])
    spend_by_category_id = {r["category_id"]: r["spend"] for r in spend_rows}

    # Spend against a category_id that isn't a tracked variable budget —
    # either uncategorized (category_id is None) or a 'fixed'-kind
    # category — surfaced the same way the name-matched path surfaced a
    # spend key with no matching budget line: visible, but excluded from
    # total_deductions (money_in_hand() already nets it out).
    unmatched_spending = [
        {"name": r["category_name"] or "Uncategorized", "amount": r["spend"]}
        for r in spend_rows
        if r["category_id"] not in variable_ids and r["spend"] > 0
    ]

    data = compute_budget_by_id(
        days_left=days_left,
        remaining_money=repo.money_in_hand(),
        bills=[{"id": b["id"], "name": b["name"], "amount": b["amount"], "due_day": b["due_day"]} for b in bills],
        categories=categories,
        paid_bill_ids=paid_bill_ids,
        spend_by_category_id=spend_by_category_id,
        unmatched_spending=unmatched_spending,
    )
    data["period_id"] = period["id"]
    return data


def get_summary():
    """The 7-field camelCase-ready snapshot GET /api/budget has always
    returned — now derived live from the ledger instead of a stale
    bot_state blob."""
    data = build_period_view()
    if data is None:
        return None
    return {
        "remaining": data["remaining"],
        "deductions": data["total_deductions"],
        "free": data["free_money"],
        # compute_budget()'s free_money / days_left division produces a
        # float (or Decimal, on Postgres); coerced to int here so the
        # client never has to — AnimatedCurrency and any threshold compare
        # both want a plain int.
        "dailyBudget": int(data["daily_budget"]),
        "daysToPayday": data["days_left"],
        "statusLevel": data["status_level"],
        "computedAt": str(now_jkt()),
    }


# ================================================================
# TRANSACTIONS — every mutation returns (transaction, summary) so the
# screen that performed the action updates instantly, without a
# separate round-trip to GET /api/budget.
# ================================================================
_VALID_DIRECTIONS = {"expense", "income", "transfer", "adjustment"}


def _normalize_occurred_at(value):
    """Store one canonical 'YYYY-MM-DD HH:MM' shape. The insights layer
    buckets by substr(occurred_at, 1, 10) — the only date-truncation
    construct that behaves identically on SQLite and Postgres — so the
    first 10 characters must always be the local calendar date, never an
    ISO string with a 'T' separator or a timezone offset. Drops any tz
    suffix deliberately: the app is Asia/Jakarta-naive throughout
    (config.now_jkt() strips tzinfo), so a client-supplied offset would
    only ever be misleading, not more precise."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ")
    if len(text) == 10:
        return text + " 00:00"
    return text[:16]


def _validate_refs(category_id=None, wallet_id=None, transfer_wallet_id=None):
    if category_id is not None and repo.get_category(category_id) is None:
        raise BudgetValidationError(f"Unknown categoryId {category_id}.")
    if wallet_id is not None and repo.get_wallet(wallet_id) is None:
        raise BudgetValidationError(f"Unknown walletId {wallet_id}.")
    if transfer_wallet_id is not None and repo.get_wallet(transfer_wallet_id) is None:
        raise BudgetValidationError(f"Unknown transferWalletId {transfer_wallet_id}.")


def create_transaction(
    amount, direction, category_id=None, wallet_id=None, transfer_wallet_id=None,
    note=None, source="manual", raw_input=None, occurred_at=None, goal_id=None,
):
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise BudgetValidationError("amount must be a positive number.")
    if direction not in _VALID_DIRECTIONS:
        raise BudgetValidationError(f"direction must be one of {sorted(_VALID_DIRECTIONS)}.")
    _validate_refs(category_id, wallet_id, transfer_wallet_id)

    period = ensure_current_period(PAYROLL_DAY)
    txn = repo.create_transaction(
        amount=int(amount), direction=direction, category_id=category_id,
        wallet_id=wallet_id, transfer_wallet_id=transfer_wallet_id,
        period_id=period["id"], goal_id=goal_id, note=note, source=source,
        raw_input=raw_input, occurred_at=_normalize_occurred_at(occurred_at),
    )
    return txn, get_summary()


def update_transaction(txn_id, **fields):
    if repo.get_transaction(txn_id) is None:
        raise BudgetNotFound(f"No transaction with id {txn_id}.")
    _validate_refs(
        fields.get("category_id"), fields.get("wallet_id"), fields.get("transfer_wallet_id")
    )
    if "occurred_at" in fields:
        fields["occurred_at"] = _normalize_occurred_at(fields["occurred_at"])
    txn = repo.update_transaction(txn_id, **fields)
    return txn, get_summary()


def delete_transaction(txn_id):
    if repo.get_transaction(txn_id) is None:
        raise BudgetNotFound(f"No transaction with id {txn_id}.")
    txn = repo.soft_delete_transaction(txn_id)
    return txn, get_summary()


def list_transactions(**filters):
    # occurred_at is TEXT, compared lexically: "2026-08-03" <= "2026-08-03
    # 14:22" is already True, so date_from (a 10-char date) needs no
    # change. date_to is the opposite direction of the same comparison —
    # "occurred_at <= '2026-08-03'" excludes every transaction *on* that
    # date that has a time component, since any non-empty time sorts
    # after the bare date string. Extend it to the end of the day.
    date_to = filters.get("date_to")
    if date_to and len(date_to) == 10:
        filters["date_to"] = date_to + " 23:59:59"
    return repo.get_transactions(**filters)
