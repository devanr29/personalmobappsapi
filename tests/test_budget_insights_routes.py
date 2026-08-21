"""DB-backed coverage for service.build_insights()/build_insights_history()/
get_today_card() — the wiring between the pure insights.py math and the
real ledger. The pure math itself is covered with zero DB setup in
test_budget_insights.py."""
import importlib

import pytest


@pytest.fixture
def budget_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATABASE_URL", "")

    import db as db_module
    import database as database_module
    import features.budget.schema as schema_module
    import features.budget.repo as repo_module
    import features.budget.periods as periods_module
    import features.budget.compute as compute_module
    import features.budget.insights as insights_module
    import features.budget.service as service_module
    modules = (db_module, schema_module, database_module, repo_module,
               periods_module, compute_module, insights_module, service_module)
    for m in modules:
        importlib.reload(m)

    database_module.init_db()
    yield service_module, repo_module

    for m in modules:
        importlib.reload(m)


def test_insights_none_when_no_wallets(budget_env):
    service, repo = budget_env
    assert service.build_insights() is None


def test_daily_series_length_equals_elapsed_days(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    view = service.build_period_view()

    data = service.build_insights()
    assert len(data["daily"]) == data["period"]["elapsedDays"]


def test_zero_spend_mid_period_day_present_with_zero(budget_env):
    service, repo = budget_env
    wallet = repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    period = service.build_period_view()
    repo.create_transaction(10_000, "expense", wallet_id=wallet["id"], period_id=period["period_id"],
                            occurred_at="2026-07-26 09:00")
    repo.create_transaction(20_000, "expense", wallet_id=wallet["id"], period_id=period["period_id"],
                            occurred_at="2026-07-28 09:00")

    data = service.build_insights()
    by_date = {d["date"]: d for d in data["daily"]}
    assert "2026-07-27" in by_date
    assert by_date["2026-07-27"]["spend"] == 0


def test_categories_spend_sums_to_spend_to_date(budget_env):
    service, repo = budget_env
    wallet = repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    fuel = repo.create_category("Fuel", "variable", monthly_limit=70_000)
    food = repo.create_category("Food", "variable", monthly_limit=500_000)
    period = service.build_period_view()
    repo.create_transaction(35_000, "expense", category_id=fuel["id"], wallet_id=wallet["id"], period_id=period["period_id"])
    repo.create_transaction(120_000, "expense", category_id=food["id"], wallet_id=wallet["id"], period_id=period["period_id"])

    data = service.build_insights()
    assert sum(c["spend"] for c in data["categories"]) == data["stats"]["spendToDate"]


def test_categories_top_sum_equals_full_list_sum(budget_env):
    service, repo = budget_env
    wallet = repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    period = service.build_period_view()
    for i in range(7):
        cat = repo.create_category(f"Cat{i}", "variable", monthly_limit=10_000)
        repo.create_transaction(1000 * (i + 1), "expense", category_id=cat["id"], wallet_id=wallet["id"], period_id=period["period_id"])

    data = service.build_insights()
    assert len(data["categoriesTop"]) <= 5
    assert sum(c["spend"] for c in data["categories"]) == sum(c["spend"] for c in data["categoriesTop"])


def test_limitless_variable_category_is_excluded_from_remaining_var(budget_env):
    # Regression guard for the "Variable budget" filter change: a
    # kind='variable' category with no monthly_limit is Wallet-sync
    # imported taxonomy, not a real budget envelope, and must not show up
    # as a meaningless "Rp 0 left" row.
    service, repo = budget_env
    wallet = repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    junk = repo.create_category("Bar cafe", "variable")  # no monthly_limit
    period = service.build_period_view()
    repo.create_transaction(15_000, "expense", category_id=junk["id"], wallet_id=wallet["id"], period_id=period["period_id"])

    view = service.build_period_view()
    assert view["remaining_var"] == []
    assert any(u["name"] == "Bar cafe" and u["amount"] == 15_000 for u in view["unmatched_spending"])
    assert view["total_var_remaining"] == 0


def test_limited_variable_category_stays_in_remaining_var_at_zero_spend(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    fuel = repo.create_category("Fuel", "variable", monthly_limit=70_000)
    service.build_period_view()

    view = service.build_period_view()
    assert len(view["remaining_var"]) == 1
    assert view["remaining_var"][0]["id"] == fuel["id"]
    assert view["remaining_var"][0]["remaining"] == 70_000
    assert view["total_var_remaining"] == 70_000


def test_transfer_and_adjustment_excluded_from_every_spend_figure(budget_env):
    service, repo = budget_env
    cash = repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    bank = repo.create_wallet("Bank", opening_balance=0)
    period = service.build_period_view()
    repo.create_transaction(50_000, "transfer", wallet_id=cash["id"], transfer_wallet_id=bank["id"], period_id=period["period_id"])
    repo.create_transaction(10_000, "adjustment", wallet_id=cash["id"], period_id=period["period_id"])

    data = service.build_insights()
    assert data["stats"]["spendToDate"] == 0
    assert data["categories"] == []
    assert all(d["spend"] == 0 for d in data["daily"])


def test_insights_and_breakdown_agree_on_free_money_and_daily_budget(budget_env):
    # The most valuable test here: catches the two screens drifting.
    service, repo = budget_env
    wallet = repo.create_wallet("Cash", opening_balance=2_500_000, is_default=True)
    fuel = repo.create_category("Fuel", "variable", monthly_limit=70_000)
    rent_cat = repo.create_category("House Rent", "fixed")
    repo.create_bill("House Rent", 955_000, due_day=25, category_id=rent_cat["id"])
    period = service.build_period_view()
    repo.create_transaction(35_000, "expense", category_id=fuel["id"], wallet_id=wallet["id"], period_id=period["period_id"])

    insights_data = service.build_insights()
    breakdown_data = service.build_period_view()
    from features.budget.serializers import camel_budget_breakdown
    breakdown = camel_budget_breakdown(breakdown_data)

    assert insights_data["stats"]["freeMoney"] == breakdown["freeMoney"]
    assert insights_data["stats"]["dailyBudget"] == breakdown["dailyBudget"]


def test_wallet_composition_shares_sum_to_roughly_one(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=300_000, is_default=True)
    repo.create_wallet("Bank", opening_balance=700_000)

    data = service.build_insights()
    total_share = sum(w["share"] for w in data["wallets"]["items"])
    assert abs(total_share - 1.0) < 0.01
    assert data["wallets"]["total"] == 1_000_000


# ================================================================
# TODAY CARD
# ================================================================
def test_today_card_none_when_not_set_up(budget_env):
    service, repo = budget_env
    assert service.get_today_card() is None


def test_today_card_allowance_reconstructs_correctly(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    today = service.get_today_card()
    assert today["remainingToday"] == today["allowance"]  # no spend yet today


def test_today_card_next_bill_due(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    repo.create_bill("House Rent", 955_000, due_day=25)
    repo.create_bill("Internet", 150_000, due_day=None)

    today = service.get_today_card()
    assert today["nextBill"]["name"] == "House Rent"
    assert today["nextBill"]["daysUntil"] >= 0


# ================================================================
# HISTORY
# ================================================================
def test_history_current_period_flagged_and_excluded_from_average(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    period = service.build_period_view()
    repo.create_transaction(100_000, "expense", period_id=period["period_id"])

    history = service.build_insights_history(periods=6)
    assert len(history["periods"]) == 1
    assert history["periods"][0]["isCurrent"] is True
    assert history["averageSpend"] == 0  # only period is current -> excluded


def test_history_group_by_month_returns_same_shape(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    period = service.build_period_view()
    repo.create_transaction(50_000, "expense", period_id=period["period_id"])

    history = service.build_insights_history(periods=6, group_by="month")
    assert len(history["periods"]) == 1
    assert history["periods"][0]["periodId"] is None
    assert history["spendTrend"] == [50_000]


def _shift_month(month_key, delta):
    """Local, deliberately independent of insights._month_index — this
    is the test's own ground truth for 'n months before/after', computed
    relative to config.now_jkt() rather than a hardcoded month so the
    test doesn't rot."""
    year, month = (int(x) for x in month_key.split("-"))
    idx = year * 12 + (month - 1) + delta
    y, m = divmod(idx, 12)
    return f"{y:04d}-{m + 1:02d}"


def test_history_items_carry_short_labels(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    period = service.build_period_view()
    repo.create_transaction(50_000, "expense", period_id=period["period_id"])

    period_history = service.build_insights_history(periods=6, group_by="period")
    assert period_history["periods"][0]["shortLabel"]
    assert period_history["periods"][0]["monthKey"] is None

    month_history = service.build_insights_history(periods=6, group_by="month")
    assert month_history["periods"][0]["shortLabel"]
    assert month_history["periods"][0]["monthKey"] is not None


def test_history_month_mode_includes_current_month_with_no_spend(budget_env):
    # Regression guard: month_totals() only returns months with activity,
    # so before this fix a current month with zero transactions was
    # simply absent -- isCurrent was never true and there was no partial
    # column to render at all.
    service, repo = budget_env
    from config import now_jkt
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    current_month = now_jkt().date().strftime("%Y-%m")
    older_month = _shift_month(current_month, -2)
    repo.create_transaction(10_000, "expense", occurred_at=f"{older_month}-05 09:00")

    history = service.build_insights_history(periods=6, group_by="month")
    assert history["periods"][-1]["monthKey"] == current_month
    assert history["periods"][-1]["isCurrent"] is True
    assert history["periods"][-1]["spend"] == 0


def test_history_month_mode_is_dense_across_a_gap(budget_env):
    service, repo = budget_env
    from config import now_jkt
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    current_month = now_jkt().date().strftime("%Y-%m")
    older_month = _shift_month(current_month, -3)
    repo.create_transaction(10_000, "expense", occurred_at=f"{older_month}-05 09:00")
    repo.create_transaction(20_000, "expense", occurred_at=f"{current_month}-01 09:00")

    history = service.build_insights_history(periods=6, group_by="month")
    months = [p["monthKey"] for p in history["periods"]]
    assert months == [_shift_month(current_month, d) for d in (-3, -2, -1, 0)]
    by_month = {p["monthKey"]: p for p in history["periods"]}
    assert by_month[_shift_month(current_month, -2)]["spend"] == 0
    assert by_month[_shift_month(current_month, -1)]["spend"] == 0
    assert by_month[older_month]["spend"] == 10_000
    assert by_month[current_month]["spend"] == 20_000


def test_history_twelve_months_returns_at_most_twelve(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    period = service.build_period_view()
    repo.create_transaction(10_000, "expense", period_id=period["period_id"])

    history = service.build_insights_history(periods=12, group_by="month")
    assert len(history["periods"]) <= 12


# ================================================================
# CATEGORY PATTERNS
# ================================================================
def test_category_patterns_months_axis_matches_window(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)

    patterns = service.build_category_patterns(months=6)
    assert len(patterns["months"]) == 6
    assert len(patterns["monthLabels"]) == 6
    assert patterns["windowMonths"] == 6
    assert patterns["completeMonths"] == 5
    assert patterns["months"][-1] == patterns["currentMonth"]


def test_category_patterns_every_series_matches_the_shared_axis(budget_env):
    service, repo = budget_env
    from config import now_jkt
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    current_month = now_jkt().date().strftime("%Y-%m")
    older_month = _shift_month(current_month, -2)
    cat = repo.create_category("Fuel", "variable")
    repo.create_transaction(10_000, "expense", category_id=cat["id"], occurred_at=f"{older_month}-05 09:00")

    patterns = service.build_category_patterns(months=6)
    assert len(patterns["categories"]) == 1
    entry = patterns["categories"][0]
    assert len(entry["series"]) == len(patterns["months"])
    assert entry["categoryId"] == cat["id"]
    assert entry["name"] == "Fuel"


def test_category_patterns_uncategorized_bucket_is_not_dropped(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    repo.create_transaction(5_000, "expense")  # no category_id

    patterns = service.build_category_patterns(months=6)
    names = [c["name"] for c in patterns["categories"]]
    assert "Uncategorized" in names


def test_category_patterns_dormant_categories_are_counted_not_listed(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    repo.create_category("Never spent", "variable")  # zero transactions ever

    patterns = service.build_category_patterns(months=6)
    assert patterns["categories"] == []
    assert patterns["dormantCount"] == 1


def test_category_patterns_share_sums_to_one(budget_env):
    # share is computed off `total`, which only counts COMPLETE months (the
    # current, still-accruing month is excluded) -- so the spend has to
    # land in a prior month within the window for share to be nonzero.
    service, repo = budget_env
    from config import now_jkt
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    current_month = now_jkt().date().strftime("%Y-%m")
    prior_month = _shift_month(current_month, -1)
    a = repo.create_category("A", "variable")
    b = repo.create_category("B", "variable")
    repo.create_transaction(30_000, "expense", category_id=a["id"], occurred_at=f"{prior_month}-05 09:00")
    repo.create_transaction(70_000, "expense", category_id=b["id"], occurred_at=f"{prior_month}-06 09:00")

    patterns = service.build_category_patterns(months=2)
    total_share = sum(c["share"] for c in patterns["categories"])
    assert round(total_share, 4) == 1.0
