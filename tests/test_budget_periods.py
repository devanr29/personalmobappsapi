import calendar

from features.budget.periods import days_to_payday, period_bounds


def test_days_to_payday_matches_legacy_formula_before_payday():
    # legacy: today <= PAYROLL_DAY -> PAYROLL_DAY - today
    assert days_to_payday(3, 25, 31) == 22


def test_days_to_payday_matches_legacy_formula_on_payday():
    assert days_to_payday(25, 25, 31) == 0


def test_days_to_payday_matches_legacy_formula_after_payday():
    # legacy: today > PAYROLL_DAY -> (days_in_month - today) + PAYROLL_DAY
    assert days_to_payday(26, 25, 31) == (31 - 26) + 25


def test_days_to_payday_handles_february():
    days_in_feb = calendar.monthrange(2026, 2)[1]  # 28 (2026 is not a leap year)
    assert days_in_feb == 28
    assert days_to_payday(27, 25, days_in_feb) == (28 - 27) + 25


def test_period_bounds_before_payroll_day_uses_previous_month_start():
    import datetime
    start, end = period_bounds(datetime.date(2026, 8, 3), 25)
    assert start == "2026-07-25"
    assert end == "2026-08-25"


def test_period_bounds_on_or_after_payroll_day_uses_current_month_start():
    import datetime
    start, end = period_bounds(datetime.date(2026, 8, 26), 25)
    assert start == "2026-08-25"
    assert end == "2026-09-25"


def test_period_bounds_crosses_year_boundary():
    import datetime
    start, end = period_bounds(datetime.date(2026, 1, 10), 25)
    assert start == "2025-12-25"
    assert end == "2026-01-25"


def test_period_bounds_clamps_payroll_day_to_short_month():
    import datetime
    # payroll day 31 in a period that would span into February (28 days)
    start, end = period_bounds(datetime.date(2026, 2, 5), 31)
    assert start == "2026-01-31"
    assert end == "2026-02-28"
