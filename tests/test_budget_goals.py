"""Goal CRUD, reservation math, and the free-money-neutral contribution
invariant."""
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
    import features.budget.service as service_module
    modules = (db_module, schema_module, database_module, repo_module,
               periods_module, compute_module, service_module)
    for m in modules:
        importlib.reload(m)

    database_module.init_db()
    yield service_module, repo_module

    for m in modules:
        importlib.reload(m)


def test_no_goals_reproduces_baseline_view(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    baseline = service.build_period_view()

    goal = service.create_goal("Emergency fund", 5_000_000, reserve_from_free=False)
    with_disabled_goal = service.build_period_view()

    assert with_disabled_goal == baseline
    service.delete_goal(goal["id"])


def test_active_goal_with_monthly_contribution_reserves_it(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    service.create_goal("Emergency fund", 5_000_000, monthly_contribution=200_000)

    view = service.build_period_view()
    assert view["total_still_owed"] == 200_000
    assert view["free_money"] == view["remaining"] - 200_000


def test_goal_derives_monthly_contribution_from_target_date(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    period = service.build_period_view()
    end = period["period_id"]

    # 2 months out, no monthly_contribution set -> derived as ceil(target/months)
    from features.budget.periods import ensure_current_period
    p = ensure_current_period(service.get_payroll_day())
    import datetime
    target = (datetime.date.fromisoformat(p["end_date"]) + datetime.timedelta(days=60)).isoformat()
    service.create_goal("Vacation", 1_000_000, target_date=target)

    reservations = service.goal_reservations(p)
    assert len(reservations) == 1
    assert reservations[0]["amount"] > 0


def test_contribution_is_free_money_neutral(budget_env):
    service, repo = budget_env
    cash = repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    savings = repo.create_wallet("Savings", opening_balance=0, spendable=False)
    goal = service.create_goal("Emergency fund", 5_000_000, monthly_contribution=200_000, wallet_id=savings["id"])

    free_before = service.build_period_view()["free_money"]
    result, summary = service.contribute_to_goal(goal["id"], 200_000, wallet_id=cash["id"])
    free_after = service.build_period_view()["free_money"]

    assert free_after == free_before
    assert result["saved"] == 200_000
    assert repo.wallet_balance(savings["id"]) == 200_000
    assert repo.wallet_balance(cash["id"]) == 800_000


def test_contribution_without_wallet_is_bookkeeping_only(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    goal = service.create_goal("Emergency fund", 5_000_000, monthly_contribution=200_000)

    money_before = repo.money_in_hand()
    result, summary = service.contribute_to_goal(goal["id"], 200_000)
    money_after = repo.money_in_hand()

    assert money_after == money_before  # no wallet -> no cash movement
    assert result["transaction"] is None
    assert result["saved"] == 200_000


def test_delete_goal_with_contributions_is_409(budget_env):
    from features.budget.errors import BudgetConflict

    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    goal = service.create_goal("Emergency fund", 5_000_000, monthly_contribution=200_000)
    service.contribute_to_goal(goal["id"], 100_000)

    with pytest.raises(BudgetConflict):
        service.delete_goal(goal["id"])


def test_delete_unused_goal_succeeds(budget_env):
    service, repo = budget_env
    goal = service.create_goal("Emergency fund", 5_000_000)
    service.delete_goal(goal["id"])
    assert repo.get_goal(goal["id"]) is None


def test_create_goal_requires_positive_target(budget_env):
    from features.budget.errors import BudgetValidationError

    service, repo = budget_env
    with pytest.raises(BudgetValidationError):
        service.create_goal("Bad goal", -100)


def test_archived_goal_excluded_from_reservations(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    goal = service.create_goal("Emergency fund", 5_000_000, monthly_contribution=200_000)
    service.update_goal(goal["id"], archived=True)

    period = service.build_period_view()
    assert period["total_still_owed"] == 0
