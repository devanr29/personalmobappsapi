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
