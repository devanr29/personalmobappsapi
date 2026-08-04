"""Orchestration layer: gathers ledger data via repo, calls the pure
compute_budget_by_id(), and returns period-scoped views. No route/HTTP
concerns — those live in blueprint.py."""
import calendar
import datetime

from config import PAYROLL_DAY, now_jkt
from database import state_get, state_set
from features.budget import repo, insights
from features.budget.compute import compute_budget_by_id
from features.budget.errors import BudgetConflict, BudgetNotFound, BudgetValidationError
from features.budget.periods import ensure_current_period


def get_payroll_day() -> int:
    """config.PAYROLL_DAY is a constant; the setup wizard needs the pay
    cycle to be user-editable at runtime, so an explicit override in
    bot_state wins when present."""
    stored = state_get("payroll_day")
    return int(stored) if stored else PAYROLL_DAY


def set_payroll_day(day: int):
    if not isinstance(day, int) or not (1 <= day <= 31):
        raise BudgetValidationError("payrollDay must be an integer between 1 and 31.")
    state_set("payroll_day", str(day))


def build_period_view():
    """Returns the full compute_budget_by_id() dict for the current
    period, plus a period_id key, or None if the feature hasn't been set
    up yet (no wallets configured) — mirrors the legacy "never computed"
    null state."""
    wallets = repo.get_wallets()
    if not wallets:
        return None

    period = ensure_current_period(get_payroll_day())
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
        goal_reservations=goal_reservations(period),
    )
    data["period_id"] = period["id"]
    return data


def _months_between(from_date: datetime.date, to_date: datetime.date) -> int:
    """Whole calendar months from from_date to to_date, at least 1 — used
    to spread a goal's remaining target across its remaining runway when
    no explicit monthly_contribution is set."""
    months = (to_date.year - from_date.year) * 12 + (to_date.month - from_date.month)
    return max(months, 1)


def goal_reservations(period) -> list:
    """One reservation per active goal with reserve_from_free=1, net of
    what's already been contributed THIS period — a contribution already
    moved money out of the spendable wallets (if the goal has one), so
    reserving it again would double-count. Empty goals list -> empty
    reservations -> compute_budget_by_id's total_still_owed is unchanged,
    which is what keeps this a strict addition rather than a behavior
    change for ledgers with no goals."""
    out = []
    today = now_jkt().date()
    for g in repo.get_goals(include_archived=False):
        if not g["reserve_from_free"]:
            continue
        monthly = g["monthly_contribution"]
        if monthly is None:
            if not g["target_date"]:
                continue
            remaining_target = max(g["target_amount"] - repo.goal_saved(g["id"]), 0)
            target_date = datetime.date.fromisoformat(g["target_date"])
            months = _months_between(today, target_date)
            monthly = -(-remaining_target // months)  # ceil division
        already = repo.goal_contributed_in_period(g["id"], period["start_date"], period["end_date"])
        amount = max(monthly - already, 0)
        if amount > 0:
            out.append({"name": g["name"], "amount": amount})
    return out


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
# 'adjustment' is the one direction that can be negative — a reconcile that
# lowers a wallet's balance needs a negative delta. Every other direction's
# sign is implied by its name, so a negative expense/income/transfer would
# just be a confusing way to write the opposite direction.
_SIGNED_DIRECTIONS = {"adjustment"}


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
    if direction not in _VALID_DIRECTIONS:
        raise BudgetValidationError(f"direction must be one of {sorted(_VALID_DIRECTIONS)}.")
    if not isinstance(amount, (int, float)) or amount == 0:
        raise BudgetValidationError("amount must be a non-zero number.")
    if direction not in _SIGNED_DIRECTIONS and amount < 0:
        raise BudgetValidationError(f"amount must be positive for direction={direction}.")
    _validate_refs(category_id, wallet_id, transfer_wallet_id)

    period = ensure_current_period(get_payroll_day())
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


# ================================================================
# CATEGORIES
# ================================================================
_VALID_CATEGORY_KINDS = {"fixed", "variable"}


def create_category(name, kind, monthly_limit=None, rollover=False, icon=None, color_index=None):
    if not name or not name.strip():
        raise BudgetValidationError("name is required.")
    if kind not in _VALID_CATEGORY_KINDS:
        raise BudgetValidationError(f"kind must be one of {sorted(_VALID_CATEGORY_KINDS)}.")
    return repo.create_category(
        name.strip(), kind, monthly_limit=monthly_limit, rollover=rollover, icon=icon, color_index=color_index,
    )


def update_category(category_id, **fields):
    if repo.get_category(category_id) is None:
        raise BudgetNotFound(f"No category with id {category_id}.")
    if "kind" in fields and fields["kind"] not in _VALID_CATEGORY_KINDS:
        raise BudgetValidationError(f"kind must be one of {sorted(_VALID_CATEGORY_KINDS)}.")
    return repo.update_category(category_id, **fields)


def delete_category(category_id):
    if repo.get_category(category_id) is None:
        raise BudgetNotFound(f"No category with id {category_id}.")
    if repo.category_in_use(category_id):
        raise BudgetConflict("This category has transactions or bills — archive it instead of deleting it.")
    repo.delete_category(category_id)


# ================================================================
# WALLETS — CRUD, transfer between wallets, reconcile to an actual balance
# ================================================================
def create_wallet(name, kind="cash", opening_balance=0, spendable=True, is_default=False):
    if not name or not name.strip():
        raise BudgetValidationError("name is required.")
    return repo.create_wallet(
        name.strip(), kind=kind, opening_balance=opening_balance, spendable=spendable, is_default=is_default,
    )


def update_wallet(wallet_id, **fields):
    if repo.get_wallet(wallet_id) is None:
        raise BudgetNotFound(f"No wallet with id {wallet_id}.")
    return repo.update_wallet(wallet_id, **fields)


def delete_wallet(wallet_id):
    if repo.get_wallet(wallet_id) is None:
        raise BudgetNotFound(f"No wallet with id {wallet_id}.")
    if repo.wallet_in_use(wallet_id):
        raise BudgetConflict("This wallet has transactions, bills, or goals — archive it instead of deleting it.")
    repo.delete_wallet(wallet_id)


def transfer_between_wallets(from_wallet_id, to_wallet_id, amount, occurred_at=None, note=None):
    if from_wallet_id == to_wallet_id:
        raise BudgetValidationError("fromWalletId and toWalletId must be different wallets.")
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise BudgetValidationError("amount must be a positive number.")
    from_wallet = repo.get_wallet(from_wallet_id)
    to_wallet = repo.get_wallet(to_wallet_id)
    if from_wallet is None:
        raise BudgetValidationError(f"Unknown fromWalletId {from_wallet_id}.")
    if to_wallet is None:
        raise BudgetValidationError(f"Unknown toWalletId {to_wallet_id}.")
    if from_wallet["archived"] or to_wallet["archived"]:
        raise BudgetValidationError("Cannot transfer to or from an archived wallet.")

    period = ensure_current_period(get_payroll_day())
    txn = repo.create_transaction(
        amount=int(amount), direction="transfer", wallet_id=from_wallet_id,
        transfer_wallet_id=to_wallet_id, period_id=period["id"], note=note, source="manual",
        occurred_at=_normalize_occurred_at(occurred_at),
    )
    return txn, get_summary()


def reconcile_wallet(wallet_id, actual_balance, note=None):
    if repo.get_wallet(wallet_id) is None:
        raise BudgetNotFound(f"No wallet with id {wallet_id}.")
    if not isinstance(actual_balance, (int, float)):
        raise BudgetValidationError("actualBalance must be a number.")

    current = repo.wallet_balance(wallet_id)
    delta = int(actual_balance) - current
    if delta == 0:
        return {"adjusted": False, "delta": 0}, get_summary()

    period = ensure_current_period(get_payroll_day())
    txn = repo.create_transaction(
        amount=delta, direction="adjustment", wallet_id=wallet_id, period_id=period["id"],
        note=note or f"Reconciled to {int(actual_balance)}", source="reconcile",
    )
    return {"adjusted": True, "delta": delta, "transaction": txn}, get_summary()


# ================================================================
# BILLS
# ================================================================
def create_bill(name, amount, due_day=None, category_id=None, wallet_id=None, cadence="monthly", autopost=False):
    if not name or not name.strip():
        raise BudgetValidationError("name is required.")
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise BudgetValidationError("amount must be a positive number.")
    _validate_refs(category_id, wallet_id)
    return repo.create_bill(
        name.strip(), int(amount), due_day=due_day, category_id=category_id,
        wallet_id=wallet_id, cadence=cadence, autopost=autopost,
    )


def update_bill(bill_id, **fields):
    if repo.get_bill(bill_id) is None:
        raise BudgetNotFound(f"No bill with id {bill_id}.")
    _validate_refs(fields.get("category_id"), fields.get("wallet_id"))
    return repo.update_bill(bill_id, **fields)


def delete_bill(bill_id):
    if repo.get_bill(bill_id) is None:
        raise BudgetNotFound(f"No bill with id {bill_id}.")
    if repo.bill_in_use(bill_id):
        raise BudgetConflict("This bill has payment history — deactivate it instead of deleting it.")
    repo.delete_bill(bill_id)


def pay_bill(bill_id, wallet_id=None, amount=None, occurred_at=None):
    from db import integrity_errors

    bill = repo.get_bill(bill_id)
    if bill is None:
        raise BudgetNotFound(f"No bill with id {bill_id}.")
    if not bill["active"]:
        raise BudgetValidationError("This bill is not active.")

    period = ensure_current_period(get_payroll_day())
    resolved_wallet_id = wallet_id or bill["wallet_id"]
    if resolved_wallet_id is None:
        default_wallet = repo.get_default_wallet()
        resolved_wallet_id = default_wallet["id"] if default_wallet else None
    _validate_refs(bill["category_id"], resolved_wallet_id)

    txn = repo.create_transaction(
        amount=int(amount) if amount is not None else bill["amount"],
        direction="expense", category_id=bill["category_id"], wallet_id=resolved_wallet_id,
        period_id=period["id"], bill_id=bill["id"], note=bill["name"], source="bill",
        occurred_at=_normalize_occurred_at(occurred_at),
    )

    try:
        repo.create_bill_payment(bill["id"], period["id"], txn["id"], str(now_jkt()))
    except integrity_errors():
        # repo.create_bill_payment() already rolled back and closed its own
        # (now-failed) connection — soft_delete_transaction() below opens a
        # fresh one, so there's no poisoned state to carry over here.
        repo.soft_delete_transaction(txn["id"])
        raise BudgetConflict(f"Bill {bill['name']} is already marked paid for this period.")

    return txn, get_summary()


def unpay_bill(bill_id):
    bill = repo.get_bill(bill_id)
    if bill is None:
        raise BudgetNotFound(f"No bill with id {bill_id}.")

    period = ensure_current_period(get_payroll_day())
    payment = repo.get_bill_payment(bill_id, period["id"])
    if payment is None:
        raise BudgetNotFound(f"Bill {bill['name']} is not marked paid for this period.")

    if payment["transaction_id"] is not None:
        repo.soft_delete_transaction(payment["transaction_id"])
    repo.delete_bill_payment(bill_id, period["id"])
    return bill, get_summary()


# ================================================================
# SETUP WIZARD — replaces the Sheets import as the first-run path.
# Idempotent find-or-create rather than one transaction: repo functions
# each open their own connection, so a mid-wizard failure should leave
# state that a retry can pick up from cleanly, not a half-applied write.
# ================================================================
def get_setup_status():
    wallets = repo.get_wallets(include_archived=True)
    categories = repo.get_categories(include_archived=True)
    bills = repo.get_bills(active_only=False)
    return {
        "seeded": bool(state_get("budget_seeded_at")),
        "wallet_count": len(wallets),
        "category_count": len(categories),
        "bill_count": len(bills),
    }


def _find_by_name(items, name):
    for item in items:
        if item["name"] == name:
            return item
    return None


def run_setup(*, payroll_day=None, wallets=None, categories=None, bills=None, force=False):
    if state_get("budget_seeded_at") and not force:
        raise BudgetConflict("Budget has already been set up. Pass force=true to re-run.")

    wallets = wallets or []
    categories = categories or []
    bills = bills or []

    default_flags = [bool(w.get("isDefault")) for w in wallets]
    if wallets and default_flags.count(True) != 1:
        raise BudgetValidationError("Exactly one wallet must be marked isDefault.")

    if payroll_day is not None:
        set_payroll_day(int(payroll_day))

    existing_wallets = repo.get_wallets(include_archived=True)
    created_wallets = []
    for w in wallets:
        found = _find_by_name(existing_wallets, w["name"])
        created_wallets.append(found if found else repo.create_wallet(
            w["name"], kind=w.get("kind", "cash"), opening_balance=w.get("openingBalance", 0),
            spendable=w.get("spendable", True), is_default=w.get("isDefault", False),
        ))

    existing_categories = repo.get_categories(include_archived=True)
    created_categories = []
    for c in categories:
        found = _find_by_name(existing_categories, c["name"])
        created = found if found else repo.create_category(
            c["name"], c.get("kind", "variable"), monthly_limit=c.get("monthlyLimit"),
        )
        created_categories.append(created)
        existing_categories.append(created)

    existing_bills = repo.get_bills(active_only=False)
    created_bills = []
    for b in bills:
        category = None
        category_name = b.get("categoryName")
        if category_name:
            category = _find_by_name(existing_categories, category_name)
            if category is None:
                category = repo.create_category(category_name, "fixed")
                existing_categories.append(category)
                created_categories.append(category)
        found_bill = _find_by_name(existing_bills, b["name"])
        created_bills.append(found_bill if found_bill else repo.create_bill(
            b["name"], b["amount"], due_day=b.get("dueDay"),
            category_id=category["id"] if category else None,
        ))

    period = ensure_current_period(get_payroll_day())
    repo.ensure_alert_prefs()
    state_set("budget_seeded_at", str(now_jkt()))

    return {
        "wallets": created_wallets,
        "categories": created_categories,
        "bills": created_bills,
        "periodId": period["id"],
        "openingBalance": next((w["opening_balance"] for w in created_wallets if w["is_default"]), 0),
    }


# ================================================================
# TODAY CARD — shared by GET /breakdown ("today" block) and the insights
# endpoint's stats, so the two never compute this differently.
# ================================================================
def _next_bill_due(bills, today):
    """The soonest-due active unpaid bill with a due_day set. Bills are
    monthly cadence, so a due_day already passed this month wraps to next
    month; due_day is clamped to that month's real length (mirrors
    periods._clamp_day's payroll-day-31-in-a-30-day-month handling)."""
    candidates = [b for b in bills if b["due_day"] is not None]
    if not candidates:
        return None

    def days_until(b):
        due_day = b["due_day"]
        if due_day >= today.day:
            return due_day - today.day
        next_month = today.month % 12 + 1
        next_year = today.year + (1 if today.month == 12 else 0)
        days_in_next_month = calendar.monthrange(next_year, next_month)[1]
        clamped_due_day = min(due_day, days_in_next_month)
        days_in_this_month = calendar.monthrange(today.year, today.month)[1]
        return (days_in_this_month - today.day) + clamped_due_day

    best = min(candidates, key=days_until)
    return {"id": best["id"], "name": best["name"], "amount": best["amount"],
            "dueDay": best["due_day"], "daysUntil": days_until(best)}


def get_today_card():
    """Returns None when the ledger isn't set up (mirrors build_period_view).
    today_spend/allowance are computed once here and reused by both the
    /breakdown route and build_insights()'s stats, so the two can't drift."""
    view = build_period_view()
    if view is None:
        return None
    period = ensure_current_period(get_payroll_day())
    today = now_jkt().date()
    today_spend = repo.spend_today(period["id"], today.isoformat())
    allowance = insights.today_allowance(
        free_money=view["free_money"], days_left=view["days_left"], today_spend=today_spend,
    )
    bills_due = repo.bills_due_for_period(period["id"])
    return {
        "date": today.isoformat(),
        "spend": today_spend,
        "allowance": allowance["allowance"],
        "remainingToday": allowance["remainingToday"],
        "nextBill": _next_bill_due(bills_due, today),
    }


# ================================================================
# INSIGHTS — aggregated period view (charts) and cross-period history.
# Pure math lives in insights.py; this function is the only place that
# calls both repo (data) and insights (math) for the graphs layer.
# ================================================================
def _camel_largest_expense(row):
    if row is None:
        return None
    return {"id": row["id"], "name": row["name"], "amount": row["amount"], "occurredAt": row["occurred_at"]}


def build_insights():
    view = build_period_view()
    if view is None:
        return None

    period = ensure_current_period(get_payroll_day())
    today = now_jkt().date()
    start = datetime.date.fromisoformat(period["start_date"])
    end = datetime.date.fromisoformat(period["end_date"])
    total_days = max((end - start).days, 1)
    through = min(today, end - datetime.timedelta(days=1))
    if through < start:
        through = start
    elapsed_days = (through - start).days + 1

    daily_rows = repo.daily_buckets_for_period(period["id"])
    daily = insights.daily_series(daily_rows, period["start_date"], through.isoformat())

    variable = repo.get_categories(kind="variable")
    envelope = sum(c["monthly_limit"] or 0 for c in variable)
    pace = insights.cumulative_pace(daily, envelope, total_days)

    ranked = repo.category_spend_ranked_for_period(period["id"])
    total_category_spend = sum(r["spend"] for r in ranked) or 1
    categories_full = [
        {"categoryId": r["category_id"], "name": r["name"] or "Uncategorized", "kind": r["kind"],
         "spend": r["spend"], "count": r["count"], "limit": r["monthly_limit"],
         "share": round(r["spend"] / total_category_spend, 4)}
        for r in ranked
    ]
    categories_top = insights.top_n_with_other(ranked, n=4)

    spend_by_id = {r["category_id"]: r["spend"] for r in ranked if r["category_id"] is not None}
    budget_vs_actual = insights.budget_vs_actual(
        [{"id": c["id"], "name": c["name"], "monthly_limit": c["monthly_limit"]} for c in variable],
        spend_by_id,
    )

    cumulative_spend = sum(d["spend"] for d in daily)
    today_card = get_today_card()
    projection = insights.project_end_balance(
        money_in_hand=view["remaining"], total_still_owed=view["total_still_owed"],
        cumulative_spend=cumulative_spend, elapsed_days=elapsed_days, days_left=view["days_left"],
    )

    wallets = repo.get_wallets()
    balances = repo.wallet_balances()
    wallet_total = sum(balances.get(w["id"], 0) for w in wallets)
    wallet_items = sorted(
        [{"id": w["id"], "name": w["name"], "kind": w["kind"], "spendable": w["spendable"],
          "balance": balances.get(w["id"], 0),
          "share": round(balances.get(w["id"], 0) / wallet_total, 4) if wallet_total else 0}
         for w in wallets],
        key=lambda w: w["balance"], reverse=True,
    )
    spendable_total = sum(balances.get(w["id"], 0) for w in wallets if w["spendable"])

    return {
        "period": {
            "id": period["id"], "startDate": period["start_date"], "endDate": period["end_date"],
            "label": insights.period_label(period["start_date"], period["end_date"]),
            "totalDays": total_days, "elapsedDays": elapsed_days, "daysLeft": view["days_left"],
            "payrollDay": period["payroll_day"],
        },
        "daily": daily,
        "pace": pace,
        "categories": categories_full,
        "categoriesTop": categories_top,
        "budgetVsActual": budget_vs_actual,
        "stats": {
            "moneyInHand": view["remaining"],
            "totalStillOwed": view["total_still_owed"],
            "freeMoney": view["free_money"],
            "dailyBudget": int(view["daily_budget"]),
            "statusLevel": view["status_level"],
            "spendToDate": cumulative_spend,
            "avgDailySpend": projection["avgDailySpend"],
            "projectedRemainingSpend": projection["projectedRemainingSpend"],
            "projectedEndBalance": projection["projectedEndBalance"],
            "burnRateVsIdeal": projection["avgDailySpend"] - pace["idealPerDay"],
            "largestExpense": _camel_largest_expense(repo.largest_expense_for_period(period["id"])),
            "spendSparkline": insights.trailing_days(daily, 7),
            "todayAllowance": today_card["allowance"] if today_card else 0,
            "todayRemaining": today_card["remainingToday"] if today_card else 0,
        },
        "heatmap": insights.heatmap_cells(daily),
        "wallets": {"items": wallet_items, "total": wallet_total, "spendableTotal": spendable_total},
    }


def build_insights_history(periods: int = 6, group_by: str = "period"):
    """group_by='period' (default) buckets by pay cycle, matching every
    other number in the app; 'month' buckets by calendar month. Both
    return the same shape so the client's toggle is just a re-fetch with a
    different query param."""
    current_period_id = ensure_current_period(get_payroll_day())["id"]

    if group_by == "month":
        rows = repo.month_totals(limit=periods)
        current_month = now_jkt().date().strftime("%Y-%m")
        items = [
            {"periodId": None, "startDate": None, "endDate": None,
             "label": insights.month_label(r["month"]), "spend": r["spend"], "income": r["income"],
             "net": r["income"] - r["spend"], "count": r["count"], "isCurrent": r["month"] == current_month}
            for r in rows
        ]
    else:
        rows = repo.period_totals(limit=periods)
        items = [
            {"periodId": r["period_id"], "startDate": r["start_date"], "endDate": r["end_date"],
             "label": insights.period_label(r["start_date"], r["end_date"]), "spend": r["spend"],
             "income": r["income"], "net": r["income"] - r["spend"], "count": r["count"],
             "isCurrent": r["period_id"] == current_period_id}
            for r in rows
        ]

    complete = [i for i in items if not i["isCurrent"]]
    average_spend = round(sum(i["spend"] for i in complete) / len(complete)) if complete else 0
    delta = None
    if len(items) >= 2:
        latest, previous = items[-1], items[-2]
        spend_delta = latest["spend"] - previous["spend"]
        delta = {
            "spend": spend_delta,
            "spendPct": round(spend_delta / previous["spend"], 4) if previous["spend"] else 0,
            "isPartial": latest["isCurrent"],
        }

    return {
        "periods": items,
        "spendTrend": [i["spend"] for i in items],
        "incomeTrend": [i["income"] for i in items],
        "deltaVsPrevious": delta,
        "averageSpend": average_spend,
    }


# ================================================================
# GOALS
# ================================================================
_VALID_GOAL_KINDS = {"sinking", "debt", "emergency"}


def create_goal(name, target_amount, kind="sinking", target_date=None,
                monthly_contribution=None, reserve_from_free=True, wallet_id=None):
    if not name or not name.strip():
        raise BudgetValidationError("name is required.")
    if not isinstance(target_amount, (int, float)) or target_amount <= 0:
        raise BudgetValidationError("targetAmount must be a positive number.")
    if kind not in _VALID_GOAL_KINDS:
        raise BudgetValidationError(f"kind must be one of {sorted(_VALID_GOAL_KINDS)}.")
    if wallet_id is not None and repo.get_wallet(wallet_id) is None:
        raise BudgetValidationError(f"Unknown walletId {wallet_id}.")
    return repo.create_goal(
        name.strip(), int(target_amount), kind=kind, target_date=target_date,
        monthly_contribution=monthly_contribution, reserve_from_free=reserve_from_free, wallet_id=wallet_id,
    )


def update_goal(goal_id, **fields):
    if repo.get_goal(goal_id) is None:
        raise BudgetNotFound(f"No goal with id {goal_id}.")
    if "kind" in fields and fields["kind"] not in _VALID_GOAL_KINDS:
        raise BudgetValidationError(f"kind must be one of {sorted(_VALID_GOAL_KINDS)}.")
    if fields.get("wallet_id") is not None and repo.get_wallet(fields["wallet_id"]) is None:
        raise BudgetValidationError(f"Unknown walletId {fields['wallet_id']}.")
    return repo.update_goal(goal_id, **fields)


def delete_goal(goal_id):
    if repo.get_goal(goal_id) is None:
        raise BudgetNotFound(f"No goal with id {goal_id}.")
    if repo.goal_in_use(goal_id):
        raise BudgetConflict("This goal has contributions — archive it instead of deleting it.")
    repo.delete_goal(goal_id)


def get_goal_progress(goal_id):
    goal = repo.get_goal(goal_id)
    if goal is None:
        raise BudgetNotFound(f"No goal with id {goal_id}.")
    saved = repo.goal_saved(goal_id)
    return goal, saved


def contribute_to_goal(goal_id, amount, wallet_id=None, occurred_at=None):
    """If the goal has a wallet (ideally created spendable=False, a real
    sinking-fund account), the contribution is a transfer out of a
    spendable wallet — money_in_hand() drops by `amount`, and because
    goal_reservations() nets contributions already made this period off
    the reservation, free_money moves by exactly zero: the money was
    already being held back, this just makes the holding concrete. If the
    goal has no wallet, this is bookkeeping-only — no cash movement, just
    progress tracking toward target_amount."""
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise BudgetValidationError("amount must be a positive number.")
    goal = repo.get_goal(goal_id)
    if goal is None:
        raise BudgetNotFound(f"No goal with id {goal_id}.")

    txn = None
    if goal["wallet_id"] is not None:
        source_wallet_id = wallet_id or (repo.get_default_wallet() or {}).get("id")
        if source_wallet_id is None:
            raise BudgetValidationError("No source walletId given and no default wallet configured.")
        if source_wallet_id == goal["wallet_id"]:
            raise BudgetValidationError("Source wallet cannot be the goal's own wallet.")
        period = ensure_current_period(get_payroll_day())
        txn = repo.create_transaction(
            amount=int(amount), direction="transfer", wallet_id=source_wallet_id,
            transfer_wallet_id=goal["wallet_id"], period_id=period["id"], goal_id=goal["id"],
            note=f"Contribution to {goal['name']}", source="manual",
            occurred_at=_normalize_occurred_at(occurred_at),
        )

    repo.create_goal_contribution(
        goal_id, txn["id"] if txn else None, int(amount),
        _normalize_occurred_at(occurred_at) or str(now_jkt()),
    )
    return {"goal": repo.get_goal(goal_id), "transaction": txn, "saved": repo.goal_saved(goal_id)}, get_summary()
