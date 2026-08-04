"""Bill CRUD + mark-paid/unpay via the service layer."""
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


def test_pay_bill_removes_it_from_still_owed_and_creates_transaction(budget_env):
    service, repo = budget_env
    wallet = repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    bill = service.create_bill("Internet", 150_000)

    before = service.build_period_view()
    assert any(b["id"] == bill["id"] for b in before["still_owed"])

    txn, summary = service.pay_bill(bill["id"])
    assert txn["amount"] == 150_000
    assert txn["direction"] == "expense"
    assert txn["wallet_id"] == wallet["id"]  # falls back to default wallet

    after = service.build_period_view()
    assert not any(b["id"] == bill["id"] for b in after["still_owed"])
    assert summary["deductions"] == after["total_deductions"]


def test_pay_bill_twice_in_same_period_is_409(budget_env):
    from features.budget.errors import BudgetConflict

    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    bill = service.create_bill("Internet", 150_000)

    service.pay_bill(bill["id"])
    with pytest.raises(BudgetConflict):
        service.pay_bill(bill["id"])

    # get_transactions() always excludes soft-deleted rows, so if the
    # failed second attempt's txn wasn't cleaned up, this would be 2.
    items, total = service.list_transactions(direction="expense")
    assert total == 1


def test_unpay_bill_restores_still_owed_and_soft_deletes_transaction(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    bill = service.create_bill("Internet", 150_000)

    txn, _ = service.pay_bill(bill["id"])
    unpaid_bill, summary = service.unpay_bill(bill["id"])
    assert unpaid_bill["id"] == bill["id"]

    after = service.build_period_view()
    assert any(b["id"] == bill["id"] for b in after["still_owed"])

    restored = repo.get_transaction(txn["id"])
    assert restored["deleted_at"] is not None


def test_unpay_bill_not_paid_is_404(budget_env):
    from features.budget.errors import BudgetNotFound

    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    bill = service.create_bill("Internet", 150_000)

    with pytest.raises(BudgetNotFound):
        service.unpay_bill(bill["id"])


def test_pay_bill_with_no_wallet_falls_back_to_default(budget_env):
    service, repo = budget_env
    default_wallet = repo.create_wallet("Cash", opening_balance=500_000, is_default=True)
    repo.create_wallet("Bank", opening_balance=0, is_default=False)
    bill = service.create_bill("Internet", 50_000)

    txn, _ = service.pay_bill(bill["id"])
    assert txn["wallet_id"] == default_wallet["id"]


def test_delete_bill_with_payment_history_is_409(budget_env):
    from features.budget.errors import BudgetConflict

    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    bill = service.create_bill("Internet", 150_000)
    service.pay_bill(bill["id"])

    with pytest.raises(BudgetConflict):
        service.delete_bill(bill["id"])


def test_delete_unused_bill_succeeds(budget_env):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)
    service.delete_bill(bill["id"])
    assert repo.get_bill(bill["id"]) is None


def test_update_bill(budget_env):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)
    updated = service.update_bill(bill["id"], amount=175_000, due_day=5)
    assert updated["amount"] == 175_000
    assert updated["due_day"] == 5
