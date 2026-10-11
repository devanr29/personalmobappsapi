"""Attaching existing expenses to a variable category as spend
(POST /categories/:id/spend): they're re-filed under it so the card's
remaining drops, without marking it paid or asking about the amount."""
import importlib

import pytest

from features.budget.errors import BudgetConflict, BudgetNotFound, BudgetValidationError


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


@pytest.fixture
def wallet(budget_env):
    _, repo = budget_env
    return repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)


def _expense(service, wallet, amount, category_id=None, direction="expense"):
    txn, _ = service.create_transaction(
        amount=amount, direction=direction, wallet_id=wallet["id"], category_id=category_id,
    )
    return txn


def _category_item(service, category_id):
    return next(v for v in service.build_period_view()["remaining_var"] if v["id"] == category_id)


def test_attach_spend_reduces_remaining_without_marking_paid(budget_env, wallet):
    service, repo = budget_env
    food = service.create_category("Food", "variable", monthly_limit=40_000)
    txn = _expense(service, wallet, 20_000)

    attached, _ = service.attach_spend_to_category(food["id"], [txn["id"]])

    assert [t["id"] for t in attached] == [txn["id"]]
    assert repo.get_transaction(txn["id"])["category_id"] == food["id"]
    item = _category_item(service, food["id"])
    assert item["spent"] == 20_000
    assert item["remaining"] == 20_000
    assert item["paid"] is False
    period = service.ensure_current_period(service.get_payroll_day())
    assert repo.get_category_payment(food["id"], period["id"]) is None
    assert repo.wallet_balance(wallet["id"]) == 1_000_000 - 20_000
    assert service.list_transactions()[1] == 1


def test_attach_spend_moves_expense_from_other_category(budget_env, wallet):
    service, _ = budget_env
    food = service.create_category("Food", "variable", monthly_limit=40_000)
    misc = service.create_category("Misc", "variable", monthly_limit=40_000)
    txn = _expense(service, wallet, 15_000, category_id=misc["id"])

    service.attach_spend_to_category(food["id"], [txn["id"]])

    assert _category_item(service, food["id"])["remaining"] == 25_000
    assert _category_item(service, misc["id"])["remaining"] == 40_000


def test_attach_spend_over_limit_shows_over_budget(budget_env, wallet):
    service, _ = budget_env
    food = service.create_category("Food", "variable", monthly_limit=40_000)
    a = _expense(service, wallet, 30_000)
    b = _expense(service, wallet, 20_000)

    service.attach_spend_to_category(food["id"], [a["id"], b["id"]])

    item = _category_item(service, food["id"])
    assert item["remaining"] == 0
    assert item["over_budget"] == 10_000
    assert item["paid"] is False


def test_attach_spend_rejects_income(budget_env, wallet):
    service, _ = budget_env
    food = service.create_category("Food", "variable", monthly_limit=40_000)
    income = _expense(service, wallet, 20_000, direction="income")
    with pytest.raises(BudgetValidationError):
        service.attach_spend_to_category(food["id"], [income["id"]])


def test_attach_spend_rejects_deleted(budget_env, wallet):
    service, _ = budget_env
    food = service.create_category("Food", "variable", monthly_limit=40_000)
    txn = _expense(service, wallet, 20_000)
    service.delete_transaction(txn["id"])
    with pytest.raises(BudgetNotFound):
        service.attach_spend_to_category(food["id"], [txn["id"]])


def test_attach_spend_rejects_other_period(budget_env, wallet):
    service, repo = budget_env
    food = service.create_category("Food", "variable", monthly_limit=40_000)
    txn = _expense(service, wallet, 20_000)
    repo.update_transaction(txn["id"], period_id=None)
    with pytest.raises(BudgetValidationError):
        service.attach_spend_to_category(food["id"], [txn["id"]])
    assert repo.get_transaction(txn["id"])["category_id"] is None


def test_attach_spend_rejects_payment_linked(budget_env, wallet):
    service, repo = budget_env
    bill = service.create_bill("Internet", 20_000)
    food = service.create_category("Food", "variable", monthly_limit=40_000)
    txn = _expense(service, wallet, 20_000)
    service.pay_bill(bill["id"], transaction_ids=[txn["id"]])
    with pytest.raises(BudgetConflict):
        service.attach_spend_to_category(food["id"], [txn["id"]])
    assert repo.get_transaction(txn["id"])["category_id"] != food["id"]


def test_attach_spend_rejects_fixed_category_and_empty_ids(budget_env, wallet):
    service, _ = budget_env
    fixed = service.create_category("Utilities", "fixed")
    food = service.create_category("Food", "variable", monthly_limit=40_000)
    txn = _expense(service, wallet, 20_000)
    with pytest.raises(BudgetValidationError):
        service.attach_spend_to_category(fixed["id"], [txn["id"]])
    with pytest.raises(BudgetValidationError):
        service.attach_spend_to_category(food["id"], None)
    with pytest.raises(BudgetValidationError):
        service.attach_spend_to_category(food["id"], [])
