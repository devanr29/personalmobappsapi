"""Pure-function coverage for features/budget/insights.py — no DB, no
clock. Mirrors the test_budget_compute.py style: every case is a plain
dict in, plain dict out."""
from features.budget import insights


# ================================================================
# daily_series
# ================================================================
def test_daily_series_fills_gaps_with_zeros():
    rows = [
        {"date": "2026-08-01", "spend": 10_000, "variable_spend": 10_000, "income": 0, "count": 1},
        {"date": "2026-08-03", "spend": 5_000, "variable_spend": 5_000, "income": 0, "count": 1},
    ]
    series = insights.daily_series(rows, "2026-08-01", "2026-08-03")
    assert [d["date"] for d in series] == ["2026-08-01", "2026-08-02", "2026-08-03"]
    assert series[1] == {"date": "2026-08-02", "spend": 0, "variableSpend": 0, "income": 0, "count": 0}


def test_daily_series_single_day_boundary():
    series = insights.daily_series([], "2026-08-01", "2026-08-01")
    assert len(series) == 1
    assert series[0]["spend"] == 0


def test_daily_series_empty_rows_still_produces_dense_range():
    series = insights.daily_series([], "2026-08-01", "2026-08-05")
    assert len(series) == 5
    assert all(d["spend"] == 0 for d in series)


# ================================================================
# cumulative_pace
# ================================================================
def test_cumulative_pace_total_days_zero_does_not_divide_by_zero():
    daily = [{"date": "2026-08-25", "spend": 0, "variableSpend": 0, "income": 0, "count": 0}]
    pace = insights.cumulative_pace(daily, envelope=700_000, total_days=0)
    assert pace["idealPerDay"] == 0
    assert pace["points"][0]["ideal"] == 0


def test_cumulative_pace_ahead_by_sign():
    daily = [
        {"date": "2026-07-25", "spend": 0, "variableSpend": 0, "income": 0, "count": 0},
        {"date": "2026-07-26", "spend": 100_000, "variableSpend": 100_000, "income": 0, "count": 1},
    ]
    pace = insights.cumulative_pace(daily, envelope=310_000, total_days=31)
    # ideal for day 2 = round(310000 * 2 / 31) = 20000; actual = 100000
    assert pace["points"][1]["actual"] == 100_000
    assert pace["aheadBy"] == pace["points"][1]["ideal"] - 100_000
    assert pace["aheadBy"] < 0  # spending faster than pace


def test_cumulative_pace_empty_daily_returns_zero_ahead_by():
    pace = insights.cumulative_pace([], envelope=100_000, total_days=30)
    assert pace["points"] == []
    assert pace["aheadBy"] == 0


# ================================================================
# top_n_with_other
# ================================================================
def _ranked(n):
    return [{"category_id": i, "name": f"Cat{i}", "spend": (n - i) * 1000, "count": 1} for i in range(n)]


def test_top_n_with_other_zero_categories():
    assert insights.top_n_with_other([], n=4) == []


def test_top_n_with_other_one_category_no_fold():
    result = insights.top_n_with_other(_ranked(1), n=4)
    assert len(result) == 1
    assert result[0]["isOther"] is False


def test_top_n_with_other_exactly_n_no_fold():
    result = insights.top_n_with_other(_ranked(4), n=4)
    assert len(result) == 4
    assert all(not r["isOther"] for r in result)


def test_top_n_with_other_five_folds_one_into_other():
    result = insights.top_n_with_other(_ranked(5), n=4)
    assert len(result) == 5
    assert result[-1]["isOther"] is True
    assert result[-1]["name"] == "Other"


def test_top_n_with_other_twelve_folds_rest_and_sums_correctly():
    ranked = _ranked(12)
    result = insights.top_n_with_other(ranked, n=4)
    assert len(result) == 5
    other = result[-1]
    expected_other_spend = sum(r["spend"] for r in ranked[4:])
    assert other["spend"] == expected_other_spend
    # full list sum must equal folded list sum (no money lost in the fold)
    assert sum(r["spend"] for r in ranked) == sum(r["spend"] for r in result)


def test_top_n_with_other_tie_is_stable_by_input_order():
    ranked = [
        {"category_id": 1, "name": "A", "spend": 1000, "count": 1},
        {"category_id": 2, "name": "B", "spend": 1000, "count": 1},
    ]
    result = insights.top_n_with_other(ranked, n=4)
    assert [r["categoryId"] for r in result] == [1, 2]


def test_top_n_with_other_uncategorized_name_fallback():
    ranked = [{"category_id": None, "name": None, "spend": 5000, "count": 1}]
    result = insights.top_n_with_other(ranked, n=4)
    assert result[0]["name"] == "Uncategorized"


# ================================================================
# budget_vs_actual
# ================================================================
def test_budget_vs_actual_includes_zero_spend_category_with_limit():
    categories = [{"id": 1, "name": "Fuel", "monthly_limit": 70_000}]
    result = insights.budget_vs_actual(categories, {})
    assert result[0]["actual"] == 0
    assert result[0]["remaining"] == 70_000


def test_budget_vs_actual_excludes_category_with_no_limit():
    categories = [{"id": 1, "name": "Misc", "monthly_limit": None}]
    result = insights.budget_vs_actual(categories, {1: 5000})
    assert result == []


def test_budget_vs_actual_overspend_clamped_not_negative():
    categories = [{"id": 1, "name": "Fuel", "monthly_limit": 70_000}]
    result = insights.budget_vs_actual(categories, {1: 90_000})
    assert result[0]["remaining"] == 0
    assert result[0]["overBudget"] == 20_000


# ================================================================
# project_end_balance
# ================================================================
def test_project_end_balance_elapsed_days_zero_does_not_divide_by_zero():
    result = insights.project_end_balance(
        money_in_hand=1_000_000, total_still_owed=200_000, cumulative_spend=0, elapsed_days=0, days_left=20,
    )
    assert result["avgDailySpend"] == 0
    assert result["projectedRemainingSpend"] == 0


def test_project_end_balance_days_left_zero():
    result = insights.project_end_balance(
        money_in_hand=1_000_000, total_still_owed=200_000, cumulative_spend=100_000, elapsed_days=10, days_left=0,
    )
    assert result["projectedRemainingSpend"] == 0
    assert result["projectedEndBalance"] == 800_000


def test_project_end_balance_formula():
    result = insights.project_end_balance(
        money_in_hand=1_000_000, total_still_owed=100_000, cumulative_spend=200_000, elapsed_days=10, days_left=10,
    )
    assert result["avgDailySpend"] == 20_000
    assert result["projectedRemainingSpend"] == 200_000
    assert result["projectedEndBalance"] == 1_000_000 - 100_000 - 200_000


# ================================================================
# today_allowance
# ================================================================
def test_today_allowance_remaining_plus_spend_equals_allowance():
    result = insights.today_allowance(free_money=500_000, days_left=9, today_spend=30_000)
    assert result["remainingToday"] + 30_000 == result["allowance"]


def test_today_allowance_days_left_zero_still_divides_by_one():
    result = insights.today_allowance(free_money=100_000, days_left=0, today_spend=0)
    assert result["allowance"] == 100_000


# ================================================================
# trailing_days
# ================================================================
def test_trailing_days_pads_short_period():
    daily = [{"date": "2026-07-25", "spend": 10_000, "variableSpend": 10_000, "income": 0, "count": 1}]
    result = insights.trailing_days(daily, n=7)
    assert result == [0, 0, 0, 0, 0, 0, 10_000]


def test_trailing_days_truncates_long_period():
    daily = [{"date": f"2026-07-{d:02d}", "spend": d, "variableSpend": d, "income": 0, "count": 1} for d in range(1, 11)]
    result = insights.trailing_days(daily, n=7)
    assert result == [4, 5, 6, 7, 8, 9, 10]


# ================================================================
# heatmap_cells
# ================================================================
def test_heatmap_cells_reports_weekday_and_maxima():
    daily = [
        {"date": "2026-08-03", "spend": 50_000, "variableSpend": 50_000, "income": 0, "count": 2},
        {"date": "2026-08-04", "spend": 10_000, "variableSpend": 10_000, "income": 0, "count": 1},
    ]
    result = insights.heatmap_cells(daily)
    assert result["maxSpend"] == 50_000
    assert result["maxCount"] == 2
    assert result["cells"][0]["weekday"] == 0  # 2026-08-03 is a Monday
    assert result["cells"][0]["label"] == "3"


# ================================================================
# labels
# ================================================================
def test_period_label_format():
    assert insights.period_label("2026-07-25", "2026-08-25") == "Jul 25 - Aug 25"


def test_month_label_format():
    assert insights.month_label("2026-07") == "Jul 2026"


def test_month_short_label_format():
    assert insights.month_short_label("2026-07") == "Jul"


def test_period_short_label_format():
    assert insights.period_short_label("2026-07-25", "2026-08-25") == "Jul 25"


# ================================================================
# dense_months
# ================================================================
def test_dense_months_fills_gap_with_zeros():
    rows = [
        {"month": "2026-01", "spend": 10_000, "income": 0, "count": 1},
        {"month": "2026-04", "spend": 20_000, "income": 0, "count": 2},
    ]
    result = insights.dense_months(rows, through_month="2026-04")
    assert [r["month"] for r in result] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert result[1] == {"month": "2026-02", "spend": 0, "income": 0, "count": 0}
    assert result[2] == {"month": "2026-03", "spend": 0, "income": 0, "count": 0}
    assert result[3]["spend"] == 20_000


def test_dense_months_crosses_year_boundary():
    rows = [
        {"month": "2025-11", "spend": 5_000, "income": 0, "count": 1},
        {"month": "2026-02", "spend": 7_000, "income": 0, "count": 1},
    ]
    result = insights.dense_months(rows, through_month="2026-02")
    assert [r["month"] for r in result] == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_dense_months_extends_to_current_month_with_no_row_for_it():
    rows = [{"month": "2026-05", "spend": 15_000, "income": 0, "count": 1}]
    result = insights.dense_months(rows, through_month="2026-07")
    assert [r["month"] for r in result] == ["2026-05", "2026-06", "2026-07"]
    assert result[-1] == {"month": "2026-07", "spend": 0, "income": 0, "count": 0}


def test_dense_months_empty_rows_returns_empty():
    assert insights.dense_months([], through_month="2026-07") == []


def test_dense_months_single_month_unchanged():
    rows = [{"month": "2026-07", "spend": 50_000, "income": 10_000, "count": 3}]
    result = insights.dense_months(rows, through_month="2026-07")
    assert result == rows


def test_dense_months_through_month_older_than_last_row_still_ends_at_last_row():
    rows = [
        {"month": "2026-05", "spend": 1_000, "income": 0, "count": 1},
        {"month": "2026-07", "spend": 2_000, "income": 0, "count": 1},
    ]
    result = insights.dense_months(rows, through_month="2026-01")
    assert [r["month"] for r in result] == ["2026-05", "2026-06", "2026-07"]


# ================================================================
# shift_month
# ================================================================
def test_shift_month_forward():
    assert insights.shift_month("2026-07", 1) == "2026-08"


def test_shift_month_crosses_year_boundary_backward():
    assert insights.shift_month("2026-01", -1) == "2025-12"


def test_shift_month_zero_is_identity():
    assert insights.shift_month("2026-07", 0) == "2026-07"


# ================================================================
# dense_months_window
# ================================================================
def test_dense_months_window_fills_every_gap():
    rows = [{"month": "2026-02", "spend": 5_000}]
    result = insights.dense_months_window(rows, "2026-01", "2026-04")
    assert result == [0, 5_000, 0, 0]


def test_dense_months_window_empty_rows_still_dense():
    result = insights.dense_months_window([], "2026-01", "2026-03")
    assert result == [0, 0, 0]


def test_dense_months_window_ignores_rows_outside_the_window():
    rows = [{"month": "2025-01", "spend": 100}]
    result = insights.dense_months_window(rows, "2026-01", "2026-02")
    assert result == [0, 0]


# ================================================================
# classify_pattern
# ================================================================
def test_classify_pattern_new_when_first_activity_is_recent():
    # first (and only) active month is the last one in the window
    series = [0, 0, 0, 0, 0, 500]
    assert insights.classify_pattern(series, months_active=1) == "new"


def test_classify_pattern_new_wins_over_multiple_recent_active_months():
    series = [0, 0, 0, 0, 300, 500]
    assert insights.classify_pattern(series, months_active=2) == "new"


def test_classify_pattern_one_off_when_single_old_spike():
    series = [0, 0, 0, 500, 0, 0, 0, 0]
    assert insights.classify_pattern(series, months_active=1) == "one-off"


def test_classify_pattern_occasional_when_active_less_than_half():
    series = [100, 0, 0, 150, 0, 0, 120, 0]
    assert insights.classify_pattern(series, months_active=3) == "occasional"


def test_classify_pattern_short_window_defaults_to_recurring():
    series = [100, 120, 110]  # n=3 < 4, trend comparison skipped entirely
    assert insights.classify_pattern(series, months_active=3) == "recurring"


def test_classify_pattern_rising_trend():
    series = [100, 100, 100, 100, 100, 100, 300, 300, 300]
    assert insights.classify_pattern(series, months_active=9) == "rising"


def test_classify_pattern_falling_trend():
    series = [300, 300, 300, 300, 300, 300, 100, 100, 100]
    assert insights.classify_pattern(series, months_active=9) == "falling"


def test_classify_pattern_stable_spend_is_recurring():
    series = [200] * 9
    assert insights.classify_pattern(series, months_active=9) == "recurring"


def test_classify_pattern_zero_to_active_reads_as_rising():
    series = [0, 0, 0, 100, 100, 100, 100, 100, 100]
    assert insights.classify_pattern(series, months_active=6) == "rising"


def test_classify_pattern_empty_series_is_new():
    assert insights.classify_pattern([], months_active=0) == "new"


def test_classify_pattern_all_zero_is_new():
    assert insights.classify_pattern([0, 0, 0, 0], months_active=0) == "new"


# ================================================================
# category_pattern_stats
# ================================================================
def test_category_pattern_stats_shape():
    series = [0, 100, 200, 50]  # last entry is the current, partial month
    complete_series = series[:-1]
    stats = insights.category_pattern_stats("Test", "variable", None, series, complete_series, count=5)
    assert stats["name"] == "Test"
    assert stats["kind"] == "variable"
    assert stats["monthlyLimit"] is None
    assert stats["total"] == 300
    assert stats["count"] == 5
    assert stats["avgPerMonth"] == 100  # 300 / 3 complete months
    assert stats["avgPerActiveMonth"] == 150  # 300 / 2 active months
    assert stats["monthsActive"] == 2
    assert stats["monthsInWindow"] == 3
    assert stats["largestMonthIndex"] == 2  # index of 200 in the full series
    assert stats["series"] == series


def test_category_pattern_stats_all_zero_complete_months():
    stats = insights.category_pattern_stats("Idle", "variable", 50_000, [0, 0, 0], [0, 0], count=0)
    assert stats["total"] == 0
    assert stats["avgPerMonth"] == 0
    assert stats["avgPerActiveMonth"] == 0
    assert stats["pattern"] == "new"
