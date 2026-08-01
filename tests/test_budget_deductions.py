from unittest.mock import patch

from features.budget import _compute_budget, _format_budget

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


def _parsed(**overrides):
    base = {
        "remaining_money": 3_254_624,
        "paid_fixed": ["House Rent", "Zakat"],
        "spent_variable": {"Claude": 400_000, "Ticket to go home": 300_000, "Tidak terduga": 580_972},
        "pending_conditional": [],
    }
    base.update(overrides)
    return base


def _run(**parsed_overrides):
    with patch("features.budget.get_variable_budgets", return_value=VARIABLE), \
         patch("features.budget.get_fixed_expenses", return_value=FIXED), \
         patch("features.budget._parse_budget_input", return_value=_parsed(**parsed_overrides)):
        return _compute_budget("irrelevant, parser is mocked")


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
    text = _format_budget(data)
    assert "Claude" in text
    assert "not tracked" not in text.lower()


def test_overspent_category_flagged_not_negative():
    data = _run(spent_variable={"Claude": 550_000, "Ticket to go home": 300_000, "Tidak terduga": 580_972})
    claude = next(v for v in data["remaining_var"] if v["name"] == "Claude")
    assert claude["remaining"] == 0
    assert claude["over_budget"] == 150_000

    text = _format_budget(data)
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

    text = _format_budget(data)
    assert "Netflix" in text
    assert "not tracked" in text.lower()


def test_no_unmatched_section_when_everything_matches():
    data = _run(spent_variable={"Ticket to go home": 300_000})
    assert data["unmatched_spending"] == []
    text = _format_budget(data)
    assert "not tracked" not in text.lower()
