"""Guards the Phase 3 migration to id-based category/bill matching.
compute_budget_by_id() must (1) reproduce compute_budget() exactly on any
fixture where names don't collide — proving the shared _finalize() tail
keeps both front ends in lockstep — and (2) get the collision case right
where the name-matched version demonstrably doesn't."""
from features.budget.compute import compute_budget, compute_budget_by_id

FIXED = [
    {"name": "House Rent", "amount": 955_000, "due_day": 25},
    {"name": "Zakat", "amount": 250_000, "due_day": 25},
    {"name": "Internet", "amount": 150_000, "due_day": None},
]
VARIABLE = [
    {"name": "Ticket to go home", "budget": 600_000},
    {"name": "Tidak terduga", "budget": 700_000},
    {"name": "Claude", "budget": 400_000},
]
DAYS_LEFT = 20
REMAINING_MONEY = 3_254_624

# Synthetic ids for the id-based fixture, mirroring FIXED/VARIABLE 1:1.
BILLS_BY_ID = [
    {"id": 1, "name": "House Rent", "amount": 955_000, "due_day": 25},
    {"id": 2, "name": "Zakat", "amount": 250_000, "due_day": 25},
    {"id": 3, "name": "Internet", "amount": 150_000, "due_day": None},
]
CATEGORIES_BY_ID = [
    {"id": 10, "name": "Ticket to go home", "budget": 600_000},
    {"id": 11, "name": "Tidak terduga", "budget": 700_000},
    {"id": 12, "name": "Claude", "budget": 400_000},
]


def _run_by_name(**overrides):
    kwargs = {
        "days_left": DAYS_LEFT,
        "remaining_money": REMAINING_MONEY,
        "fixed_expenses": FIXED,
        "variable_budgets": VARIABLE,
        "paid_fixed": ["House Rent", "Zakat"],
        "spent_variable": {"Claude": 400_000, "Ticket to go home": 300_000, "Tidak terduga": 580_972},
        "pending_conditional": [],
    }
    kwargs.update(overrides)
    return compute_budget(**kwargs)


def _run_by_id(**overrides):
    kwargs = {
        "days_left": DAYS_LEFT,
        "remaining_money": REMAINING_MONEY,
        "bills": BILLS_BY_ID,
        "categories": CATEGORIES_BY_ID,
        "paid_bill_ids": {1, 2},
        "spend_by_category_id": {12: 400_000, 10: 300_000, 11: 580_972},
    }
    kwargs.update(overrides)
    return compute_budget_by_id(**kwargs)


def _strip_ids(data: dict) -> dict:
    """The id-matched front end's still_owed/pending_amounts/remaining_var
    carry an "id" key (raw bill dicts, and category id threaded through for
    the mobile UI's edit affordances), and remaining_var also carries a
    "paid" key (compute_budget_by_id's paid_category_ids override — there's
    no id-less equivalent in the name-matched front end to compare against).
    Both are intentional, harmless shape differences — strip them so the
    equivalence check compares the numbers that actually matter."""
    out = dict(data)
    for key in ("still_owed", "pending_amounts", "remaining_var"):
        out[key] = [{k: v for k, v in e.items() if k not in ("id", "paid")} for e in data[key]]
    return out


def test_equivalence_pin_whole_dict_matches_name_matched_version():
    # The single most valuable assertion in this file: if the two front
    # ends ever diverge on a fixture where names don't collide, this
    # fails — worth more than a dozen field-level assertions.
    by_name = _run_by_name()
    by_id = _run_by_id()
    assert _strip_ids(by_id) == by_name


def test_equivalence_pin_overspent_category():
    by_name = _run_by_name(spent_variable={"Claude": 550_000, "Ticket to go home": 300_000, "Tidak terduga": 580_972})
    by_id = _run_by_id(spend_by_category_id={12: 550_000, 10: 300_000, 11: 580_972})
    assert _strip_ids(by_id) == by_name


def test_equivalence_pin_days_left_zero():
    by_name = _run_by_name(days_left=0)
    by_id = _run_by_id(days_left=0)
    assert _strip_ids(by_id) == by_name


def test_equivalence_pin_empty_goal_reservations():
    by_name = _run_by_name(goal_reservations=[])
    by_id = _run_by_id(goal_reservations=[])
    assert _strip_ids(by_id) == by_name


def test_the_collision_case_id_matching_gets_it_right():
    # "food" in "fast food" is True under the name-matched front end, so
    # Fast Food's spend silently gets attributed to Food. This is the
    # concrete bug id-based matching exists to fix.
    categories = [
        {"id": 1, "name": "Food", "budget": 500_000},
        {"id": 2, "name": "Fast Food", "budget": 300_000},
    ]
    spend = {1: 100_000, 2: 250_000}

    data = compute_budget_by_id(
        days_left=20, remaining_money=1_000_000, bills=[], categories=categories,
        spend_by_category_id=spend,
    )
    food = next(v for v in data["remaining_var"] if v["name"] == "Food")
    fast_food = next(v for v in data["remaining_var"] if v["name"] == "Fast Food")
    assert food["spent"] == 100_000
    assert food["remaining"] == 400_000
    assert fast_food["spent"] == 250_000
    assert fast_food["remaining"] == 50_000


def test_the_collision_case_name_matching_gets_it_wrong():
    # Documented characterization of the bug the migration fixes. "food" is
    # a substring of "fast food", so when compute_budget() scans Fast
    # Food's variable budget for a matching spend key, Food's own "food"
    # entry matches first (first-match-wins, dict iteration order) — Fast
    # Food ends up attributed Food's spend amount, never its own, and its
    # real 250_000 entry is left dangling in unmatched_spending even though
    # Fast Food is a tracked category.
    variable_budgets = [
        {"name": "Food", "budget": 500_000},
        {"name": "Fast Food", "budget": 300_000},
    ]
    data = compute_budget(
        days_left=20, remaining_money=1_000_000, fixed_expenses=[],
        variable_budgets=variable_budgets,
        spent_variable={"Food": 100_000, "Fast Food": 250_000},
    )
    food = next(v for v in data["remaining_var"] if v["name"] == "Food")
    fast_food = next(v for v in data["remaining_var"] if v["name"] == "Fast Food")
    assert food["spent"] == 100_000
    assert fast_food["spent"] == 100_000  # wrong: this is Food's spend, not its own
    unmatched = {u["name"]: u["amount"] for u in data["unmatched_spending"]}
    assert unmatched == {"Fast Food": 250_000}  # Fast Food's real spend, orphaned


def test_fully_spent_category_still_appears_at_zero():
    categories = [{"id": 1, "name": "Claude", "budget": 400_000}]
    data = compute_budget_by_id(
        days_left=20, remaining_money=1_000_000, bills=[], categories=categories,
        spend_by_category_id={1: 400_000},
    )
    claude = data["remaining_var"][0]
    assert claude["remaining"] == 0
    assert claude["over_budget"] == 0
    assert claude["spent"] == 400_000


def test_overspend_flagged_not_negative():
    categories = [{"id": 1, "name": "Claude", "budget": 400_000}]
    data = compute_budget_by_id(
        days_left=20, remaining_money=1_000_000, bills=[], categories=categories,
        spend_by_category_id={1: 550_000},
    )
    claude = data["remaining_var"][0]
    assert claude["remaining"] == 0
    assert claude["over_budget"] == 150_000


def test_overspend_never_contributes_negative_to_total_var_remaining():
    categories = [
        {"id": 1, "name": "A", "budget": 100_000},
        {"id": 2, "name": "B", "budget": 100_000},
    ]
    data = compute_budget_by_id(
        days_left=20, remaining_money=1_000_000, bills=[], categories=categories,
        spend_by_category_id={1: 150_000, 2: 20_000},  # A overspent by 50k
    )
    assert data["total_var_remaining"] == 80_000  # B's 80k remaining only, never negative


def test_unmatched_spending_is_surfaced_but_excluded_from_deductions():
    data = compute_budget_by_id(
        days_left=20, remaining_money=1_000_000, bills=[], categories=[],
        unmatched_spending=[{"name": "Netflix", "amount": 120_000}],
    )
    assert data["unmatched_spending"] == [{"name": "Netflix", "amount": 120_000}]
    assert data["total_deductions"] == 0


def test_days_left_zero_does_not_divide_by_zero():
    data = compute_budget_by_id(days_left=0, remaining_money=500_000, bills=[], categories=[])
    assert data["daily_budget"] == data["free_money"]


def test_finalize_is_shared_across_a_table_of_scenarios():
    scenarios = [
        {"paid": {1, 2}, "spend": {12: 400_000, 10: 300_000, 11: 580_972}},
        {"paid": set(), "spend": {}},
        {"paid": {1}, "spend": {10: 600_000}},
        {"paid": {1, 2, 3}, "spend": {12: 0, 10: 0, 11: 0}},
    ]
    name_map = {1: "House Rent", 2: "Zakat", 3: "Internet"}
    for scenario in scenarios:
        by_id = compute_budget_by_id(
            days_left=DAYS_LEFT, remaining_money=REMAINING_MONEY, bills=BILLS_BY_ID,
            categories=CATEGORIES_BY_ID, paid_bill_ids=scenario["paid"],
            spend_by_category_id=scenario["spend"],
        )
        by_name = compute_budget(
            days_left=DAYS_LEFT, remaining_money=REMAINING_MONEY, fixed_expenses=FIXED,
            variable_budgets=VARIABLE,
            paid_fixed=[name_map[i] for i in scenario["paid"]],
            spent_variable={
                {12: "Claude", 10: "Ticket to go home", 11: "Tidak terduga"}[k]: v
                for k, v in scenario["spend"].items()
            },
        )
        assert by_id["total_deductions"] == by_name["total_deductions"]
