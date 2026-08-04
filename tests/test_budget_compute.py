"""Regression suite for the pure compute_budget() function — successor to
tests/test_budget_deductions.py, which guarded the same invariants against
the pre-extraction _compute_budget via three unittest.mock patches. Since
compute_budget() takes its inputs as plain arguments, there is nothing left
to mock; the assertions below are carried over character-identical."""
from features.budget.compute import compute_budget
from features.budget.chat_view import format_budget_text

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

DAYS_LEFT = 20  # pinned constant — no assertion below reads days_left/daily_budget's exact value


def _run(**overrides):
    kwargs = {
        "days_left": DAYS_LEFT,
        "remaining_money": 3_254_624,
        "fixed_expenses": FIXED,
        "variable_budgets": VARIABLE,
        "paid_fixed": ["House Rent", "Zakat"],
        "spent_variable": {"Claude": 400_000, "Ticket to go home": 300_000, "Tidak terduga": 580_972},
        "pending_conditional": [],
    }
    kwargs.update(overrides)
    return compute_budget(**kwargs)


def test_fully_spent_category_still_appears_instead_of_vanishing():
    # This is the real bug: Claude's budget (400,000) exactly equals what
    # was spent, so leftover == 0. A strict "leftover > 0" filter used to
    # drop it from remaining_var entirely, making it disappear from every
    # part of the breakdown as if it had never been tracked.
    data = _run()
    claude = next(v for v in data["remaining_var"] if v["name"] == "Claude")
    assert claude["remaining"] == 0
    assert claude["spent"] == 400_000
    assert claude["over_budget"] == 0
    assert data["unmatched_spending"] == []


def test_fully_spent_category_shown_in_formatted_output():
    data = _run()
    text = format_budget_text(data)
    assert "Claude" in text
    assert "not tracked" not in text.lower()


def test_overspent_category_flagged_not_negative():
    data = _run(spent_variable={"Claude": 550_000, "Ticket to go home": 300_000, "Tidak terduga": 580_972})
    claude = next(v for v in data["remaining_var"] if v["name"] == "Claude")
    assert claude["remaining"] == 0
    assert claude["over_budget"] == 150_000

    text = format_budget_text(data)
    assert "over by" in text.lower()
    assert "Claude" in text


def test_overspend_never_contributes_a_negative_amount_to_total_deductions():
    data = _run(spent_variable={"Claude": 550_000, "Ticket to go home": 300_000, "Tidak terduga": 580_972})
    # A negative contribution from the overspent category would understate
    # total_deductions and overstate free_money, as if overspending created
    # extra headroom instead of just using up money that's already gone.
    assert data["total_var_remaining"] == 300_000 + 119_028 + 0


def test_genuinely_unmatched_category_is_surfaced_and_excluded_from_math():
    data = _run(spent_variable={"Netflix": 120_000, "Ticket to go home": 300_000, "Tidak terduga": 580_972})
    unmatched = {item["name"]: item["amount"] for item in data["unmatched_spending"]}
    assert unmatched == {"Netflix": 120_000}
    # Claude has no recorded spend this run, so its full budget is still owed.
    assert data["total_var_remaining"] == 400_000 + 300_000 + 119_028

    text = format_budget_text(data)
    assert "Netflix" in text
    assert "not tracked" in text.lower()


def test_no_unmatched_section_when_everything_matches():
    data = _run(spent_variable={"Ticket to go home": 300_000})
    assert data["unmatched_spending"] == []
    text = format_budget_text(data)
    assert "not tracked" not in text.lower()


def test_days_left_zero_does_not_divide_by_zero():
    data = _run(days_left=0)
    assert data["daily_budget"] == data["free_money"]


def test_empty_goal_reservations_reproduces_the_pre_goals_numbers():
    baseline = _run()
    with_empty_goals = _run(goal_reservations=[])
    assert with_empty_goals == baseline
