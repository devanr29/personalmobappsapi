"""Pure budget math — no DB, no LLM, no clock. Body is
features/budget/legacy_chat.py's original _compute_budget (itself moved
verbatim from the pre-package features/budget.py:105-188), with the Sheets
getters and the parsed-NL-message dict replaced by parameters, and the
days-to-payday clock computation replaced by the days_left parameter (now
owned by periods.days_to_payday).

This is the function tests/test_budget_compute.py guards: the clamping and
deduction-exclusion invariants below must never change without an explicit,
deliberate test update."""


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
