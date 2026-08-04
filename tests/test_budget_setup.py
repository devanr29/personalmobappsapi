"""The in-app setup wizard — service.run_setup()."""
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


WIZARD_INPUT = dict(
    payroll_day=25,
    wallets=[
        {"name": "Cash", "kind": "cash", "openingBalance": 3_254_624, "spendable": True, "isDefault": True},
        {"name": "Bank", "kind": "bank", "openingBalance": 0, "spendable": True, "isDefault": False},
    ],
    categories=[
        {"name": "Fuel", "kind": "variable", "monthlyLimit": 70_000},
    ],
    bills=[
        {"name": "House Rent", "amount": 955_000, "dueDay": 25, "categoryName": "House Rent"},
    ],
)


def test_setup_status_before_and_after(budget_env):
    service, repo = budget_env
    before = service.get_setup_status()
    assert before["seeded"] is False
    assert before["wallet_count"] == 0

    service.run_setup(**WIZARD_INPUT)

    after = service.get_setup_status()
    assert after["seeded"] is True
    assert after["wallet_count"] == 2
    assert after["category_count"] == 2  # Fuel + auto-created House Rent (fixed)
    assert after["bill_count"] == 1


def test_setup_requires_exactly_one_default_wallet(budget_env):
    from features.budget.errors import BudgetValidationError

    service, repo = budget_env
    bad_input = dict(WIZARD_INPUT)
    bad_input["wallets"] = [
        {"name": "Cash", "isDefault": True},
        {"name": "Bank", "isDefault": True},
    ]
    with pytest.raises(BudgetValidationError):
        service.run_setup(**bad_input)


def test_setup_creates_working_ledger(budget_env):
    service, repo = budget_env
    service.run_setup(**WIZARD_INPUT)

    view = service.build_period_view()
    assert view is not None
    assert view["remaining"] == 3_254_624
    assert any(b["name"] == "House Rent" for b in view["still_owed"])
    assert any(v["name"] == "Fuel" for v in view["remaining_var"])


def test_setup_sets_runtime_payroll_day(budget_env):
    service, repo = budget_env
    custom = dict(WIZARD_INPUT)
    custom["payroll_day"] = 5
    service.run_setup(**custom)
    assert service.get_payroll_day() == 5


def test_rerun_without_force_is_409(budget_env):
    from features.budget.errors import BudgetConflict

    service, repo = budget_env
    service.run_setup(**WIZARD_INPUT)
    with pytest.raises(BudgetConflict):
        service.run_setup(**WIZARD_INPUT)


def test_rerun_with_force_is_idempotent_no_duplicates(budget_env):
    service, repo = budget_env
    service.run_setup(**WIZARD_INPUT)
    force_input = dict(WIZARD_INPUT)
    force_input["force"] = True
    service.run_setup(**force_input)

    assert len(repo.get_wallets(include_archived=True)) == 2
    assert len(repo.get_bills(active_only=False)) == 1


def test_setup_creates_alert_prefs_row(budget_env):
    service, repo = budget_env
    service.run_setup(**WIZARD_INPUT)

    import db as db_module
    conn = db_module.db_conn()
    row = conn.execute("SELECT id FROM budget_alert_prefs WHERE id = 1").fetchone()
    conn.close()
    assert row is not None
