"""Category CRUD + the delete-guard via the service layer."""
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


def test_create_category_requires_valid_kind(budget_env):
    from features.budget.errors import BudgetValidationError

    service, repo = budget_env
    with pytest.raises(BudgetValidationError):
        service.create_category("Fuel", "not_a_kind")


def test_create_and_update_category(budget_env):
    service, repo = budget_env
    category = service.create_category("Fuel", "variable", monthly_limit=70_000)
    assert category["monthly_limit"] == 70_000

    updated = service.update_category(category["id"], monthly_limit=80_000)
    assert updated["monthly_limit"] == 80_000


def test_delete_category_in_use_by_transaction_is_409(budget_env):
    from features.budget.errors import BudgetConflict

    service, repo = budget_env
    category = service.create_category("Fuel", "variable", monthly_limit=70_000)
    repo.create_transaction(10_000, "expense", category_id=category["id"])

    with pytest.raises(BudgetConflict):
        service.delete_category(category["id"])


def test_delete_category_in_use_by_bill_is_409(budget_env):
    from features.budget.errors import BudgetConflict

    service, repo = budget_env
    category = service.create_category("House Rent", "fixed")
    service.create_bill("House Rent", 955_000, category_id=category["id"])

    with pytest.raises(BudgetConflict):
        service.delete_category(category["id"])


def test_delete_unused_category_succeeds(budget_env):
    service, repo = budget_env
    category = service.create_category("Fuel", "variable", monthly_limit=70_000)
    service.delete_category(category["id"])
    assert repo.get_category(category["id"]) is None


def test_update_unknown_category_is_404(budget_env):
    from features.budget.errors import BudgetNotFound

    service, repo = budget_env
    with pytest.raises(BudgetNotFound):
        service.update_category(999_999, monthly_limit=1)
