"""Pure budget math — no DB, no LLM, no clock. Body is
features/budget/legacy_chat.py's original _compute_budget (itself moved
verbatim from the pre-package features/budget.py:105-188), with the Sheets
getters and the parsed-NL-message dict replaced by parameters, and the
days-to-payday clock computation replaced by the days_left parameter (now
owned by periods.days_to_payday).

This is the function tests/test_budget_compute.py guards: the clamping and
deduction-exclusion invariants below must never change without an explicit,
deliberate test update.

compute_budget() matches fixed/variable budget lines to paid/spend entries
by NAME, via bidirectional substring containment — inherited unchanged from
the original chat parser, where names were the only handle a freeform
message gave you. That matching is a real hazard once category names start
to overlap (e.g. "Food" vs "Fast Food": "food" in "fast food" is True, so
Fast Food's spend silently gets attributed to Food). compute_budget_by_id()
below is the id-matched replacement service.py now uses; both front ends
share the exact same arithmetic tail (_finalize), so the clamping and
deduction-exclusion invariants cannot drift between them. compute_budget()
itself is kept only as the frozen reference _finalize is tested against —
nothing in the app calls it after the Phase 3 migration except tests."""


def _finalize(*, remaining_money, days_left, still_owed, pending_amounts,
              remaining_var, unmatched_spending, goal_reservations) -> dict:
    total_still_owed = (
        sum(e["amount"] for e in still_owed)
        + sum(e["amount"] for e in pending_amounts)
        + sum(g["amount"] for g in goal_reservations)
    )
    total_var_remaining = sum(v["remaining"] for v in remaining_var)
    total_deductions = total_still_owed + total_var_remaining
    free_money = remaining_money - total_deductions
    daily_budget = free_money / days_left if days_left > 0 else free_money

    if daily_budget < 0:
        status_level = "short"
    elif daily_budget < 50_000:
        status_level = "tight"
    elif daily_budget < 100_000:
        status_level = "manageable"
    else:
        status_level = "comfortable"

    return {
        "remaining": remaining_money,
        "still_owed": still_owed,
        "pending_amounts": pending_amounts,
        "remaining_var": remaining_var,
        "unmatched_spending": unmatched_spending,
        "total_still_owed": total_still_owed,
        "total_var_remaining": total_var_remaining,
        "total_deductions": total_deductions,
        "free_money": free_money,
        "daily_budget": daily_budget,
        "days_left": days_left,
        "status_level": status_level,
    }


def compute_budget(
    *,
    days_left: int,
    remaining_money: int,
    fixed_expenses: list[dict],
    variable_budgets: list[dict],
    paid_fixed: list[str] | None = None,
    spent_variable: dict[str, int] | None = None,
    pending_conditional: list[str] | None = None,
    goal_reservations: list[dict] | None = None,
) -> dict:
    paid_fixed = [n.lower() for n in (paid_fixed or [])]
    original_spent_variable = spent_variable or {}
    spent_variable = {k.lower(): v for k, v in original_spent_variable.items()}
    pending_cond = [n.lower() for n in (pending_conditional or [])]
    goal_reservations = goal_reservations or []

    still_owed = [
        exp for exp in fixed_expenses
        if not any(exp["name"].lower() in p or p in exp["name"].lower() for p in paid_fixed)
    ]

    # Every configured variable budget is included here, even when fully
    # spent or overspent — a strict "leftover > 0" filter used to drop a
    # category the moment spend caught up with its cap (e.g. spent exactly
    # equal to budget), silently disappearing it from the breakdown instead
    # of showing "Rp 0 remaining". remaining is clamped to >= 0 so an
    # overspend can't reduce total_deductions below what's actually still
    # owed; the overspend itself is reported separately for visibility.
    remaining_var = []
    matched_spend_keys = set()
    for var in variable_budgets:
        name_lower = var["name"].lower()
        spent = 0
        for k, v in spent_variable.items():
            if name_lower in k or k in name_lower:
                spent = v
                matched_spend_keys.add(k)
                break
        leftover = var["budget"] - spent
        remaining_var.append({
            "name": var["name"],
            "remaining": max(leftover, 0),
            "spent": spent,
            "over_budget": max(-leftover, 0),
        })

    # spent_variable entries that matched no configured fixed/variable name
    # (e.g. a one-off category like "Claude") — surfaced so the amount
    # doesn't silently vanish from the breakdown. Not added to
    # total_deductions: remaining_money is already net of this spend, and
    # there's no ongoing budget line to reserve for it going forward.
    unmatched_spending = [
        {"name": name, "amount": amount}
        for name, amount in original_spent_variable.items()
        if name.lower() not in matched_spend_keys
    ]

    pending_amounts = [
        exp for exp in fixed_expenses
        if any(exp["name"].lower() in p or p in exp["name"].lower() for p in pending_cond)
        and not any(e["name"].lower() == exp["name"].lower() for e in still_owed)
    ]

    return _finalize(
        remaining_money=remaining_money,
        days_left=days_left,
        still_owed=still_owed,
        pending_amounts=pending_amounts,
        remaining_var=remaining_var,
        unmatched_spending=unmatched_spending,
        goal_reservations=goal_reservations,
    )


def compute_budget_by_id(
    *,
    days_left: int,
    remaining_money: int,
    bills: list[dict],                              # [{"id","name","amount","due_day"}]
    categories: list[dict],                          # [{"id","name","budget"}] variable only
    paid_bill_ids: set | None = None,
    spend_by_category_id: dict | None = None,         # {category_id: spent_amount}
    unmatched_spending: list[dict] | None = None,      # [{"name","amount"}] caller-supplied
    pending_bill_ids: set | None = None,
    paid_category_ids: set | None = None,
    goal_reservations: list[dict] | None = None,
) -> dict:
    """Exact-id-matched sibling of compute_budget(). Only the front end
    differs — how still_owed/pending_amounts/remaining_var get built — the
    arithmetic tail is the literal same _finalize() call, so every clamping
    and deduction-exclusion invariant compute_budget() upholds applies here
    by construction, not by parallel maintenance.

    unmatched_spending has a different meaning here than in the name-matched
    path: with ids there is no "closest name" to attribute stray spend to,
    so the caller (service.py) computes it directly from spend rows whose
    category_id names no configured variable category, and passes the
    result straight through."""
    paid_bill_ids = paid_bill_ids or set()
    pending_bill_ids = pending_bill_ids or set()
    spend_by_category_id = spend_by_category_id or {}
    unmatched_spending = unmatched_spending or []
    paid_category_ids = paid_category_ids or set()
    goal_reservations = goal_reservations or []

    still_owed = [b for b in bills if b["id"] not in paid_bill_ids]
    still_owed_ids = {b["id"] for b in still_owed}

    # Mirrors compute_budget()'s dedup guard exactly: a bill already
    # counted in still_owed (unpaid) never also appears in pending_amounts
    # — pending_bill_ids only surfaces a bill here when it's NOT already
    # unpaid-and-owed (i.e. it was matched paid, but flagged pending too).
    pending_amounts = [b for b in bills if b["id"] in pending_bill_ids and b["id"] not in still_owed_ids]

    remaining_var = []
    for cat in categories:
        spent = spend_by_category_id.get(cat["id"], 0)
        leftover = cat["budget"] - spent
        paid = cat["id"] in paid_category_ids
        # A category marked paid drops out of total_var_remaining the same
        # way a paid bill drops out of total_still_owed — regardless of
        # what was actually spent, the envelope is declared settled. over_budget
        # stays real (not zeroed): it's informational, not part of the
        # deduction math, so a paid-but-overspent category still shows it.
        remaining_var.append({
            "id": cat["id"],
            "name": cat["name"],
            "remaining": 0 if paid else max(leftover, 0),
            "spent": spent,
            "over_budget": max(-leftover, 0),
            "paid": paid,
        })

    return _finalize(
        remaining_money=remaining_money,
        days_left=days_left,
        still_owed=still_owed,
        pending_amounts=pending_amounts,
        remaining_var=remaining_var,
        unmatched_spending=unmatched_spending,
        goal_reservations=goal_reservations,
    )
