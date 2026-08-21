"""Variable-budget category mark-paid/unpay via the service layer — the
Variable-budget sibling of test_budget_bills.py, plus the createTransaction
toggle bills don't have."""
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


def test_pay_variable_category_zeroes_remaining_and_creates_transaction(budget_env):
    service, repo = budget_env
    wallet = repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Sedekah", "variable", monthly_limit=50_000)

    before = service.build_period_view()
    line = next(v for v in before["remaining_var"] if v["id"] == category["id"])
    assert line["remaining"] == 50_000
    assert line["paid"] is False

    txn, summary = service.pay_variable_category(category["id"])
    assert txn["amount"] == 50_000
    assert txn["direction"] == "expense"
    assert txn["category_id"] == category["id"]
    assert txn["wallet_id"] == wallet["id"]  # falls back to default wallet

    after = service.build_period_view()
    line = next(v for v in after["remaining_var"] if v["id"] == category["id"])
    assert line["remaining"] == 0
    assert line["paid"] is True
    assert summary["deductions"] == after["total_deductions"]


def test_pay_variable_category_default_amount_is_only_whats_left(budget_env):
    # A category can already carry partial spend logged via "Log spend"
    # before "Mark as paid" is tapped — the default amount must be the
    # leftover, not the full monthly_limit, or the transaction would
    # double-count the spend that's already there.
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Fuel", "variable", monthly_limit=70_000)
    service.create_transaction(amount=20_000, direction="expense", category_id=category["id"])

    txn, _ = service.pay_variable_category(category["id"])
    assert txn["amount"] == 50_000

    after = service.build_period_view()
    line = next(v for v in after["remaining_var"] if v["id"] == category["id"])
    assert line["remaining"] == 0
    assert line["spent"] == 70_000


def test_pay_variable_category_already_fully_spent_creates_no_transaction(budget_env):
    # Nothing left to log — "mark as paid" should still succeed (the
    # override still needs recording so the category reads as settled),
    # but there's nothing new to spend, so no transaction is created.
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Laundry", "variable", monthly_limit=60_000)
    service.create_transaction(amount=60_000, direction="expense", category_id=category["id"])

    txn, _ = service.pay_variable_category(category["id"])
    assert txn is None

    after = service.build_period_view()
    line = next(v for v in after["remaining_var"] if v["id"] == category["id"])
    assert line["paid"] is True


def test_pay_variable_category_with_custom_amount_uses_that_amount(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Ticket to go home", "variable", monthly_limit=600_000)

    txn, _ = service.pay_variable_category(category["id"], amount=550_000)
    assert txn["amount"] == 550_000


def test_pay_variable_category_without_creating_a_transaction(budget_env):
    # createTransaction=False — pure bookkeeping: paid flips true, remaining
    # reads as 0, but no transaction exists and the wallet is untouched.
    service, repo = budget_env
    wallet = repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Claude", "variable", monthly_limit=400_000)

    txn, summary = service.pay_variable_category(category["id"], create_transaction=False)
    assert txn is None

    after = service.build_period_view()
    line = next(v for v in after["remaining_var"] if v["id"] == category["id"])
    assert line["remaining"] == 0
    assert line["paid"] is True
    assert line["spent"] == 0  # no real spend was logged
    assert repo.wallet_balance(wallet["id"]) == 1_000_000  # untouched

    items, total = service.list_transactions(direction="expense")
    assert total == 0


def test_pay_variable_category_twice_in_same_period_is_409(budget_env):
    from features.budget.errors import BudgetConflict

    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Sedekah", "variable", monthly_limit=50_000)

    service.pay_variable_category(category["id"])
    with pytest.raises(BudgetConflict):
        service.pay_variable_category(category["id"])

    # If the failed second attempt's txn wasn't cleaned up this would be 2.
    items, total = service.list_transactions(direction="expense")
    assert total == 1


def test_unpay_variable_category_restores_remaining_and_soft_deletes_transaction(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Sedekah", "variable", monthly_limit=50_000)

    txn, _ = service.pay_variable_category(category["id"])
    unpaid_category, summary = service.unpay_variable_category(category["id"])
    assert unpaid_category["id"] == category["id"]

    after = service.build_period_view()
    line = next(v for v in after["remaining_var"] if v["id"] == category["id"])
    assert line["paid"] is False
    assert line["remaining"] == 50_000

    restored = repo.get_transaction(txn["id"])
    assert restored["deleted_at"] is not None


def test_unpay_variable_category_with_no_transaction_just_clears_the_flag(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Claude", "variable", monthly_limit=400_000)

    service.pay_variable_category(category["id"], create_transaction=False)
    service.unpay_variable_category(category["id"])

    after = service.build_period_view()
    line = next(v for v in after["remaining_var"] if v["id"] == category["id"])
    assert line["paid"] is False
    assert line["remaining"] == 400_000


def test_unpay_variable_category_not_paid_is_404(budget_env):
    from features.budget.errors import BudgetNotFound

    service, repo = budget_env
    category = service.create_category("Sedekah", "variable", monthly_limit=50_000)

    with pytest.raises(BudgetNotFound):
        service.unpay_variable_category(category["id"])


def test_pay_variable_category_with_no_wallet_falls_back_to_default(budget_env):
    service, repo = budget_env
    default_wallet = repo.create_wallet("Cash", opening_balance=500_000, is_default=True)
    repo.create_wallet("Bank", opening_balance=0, is_default=False)
    category = service.create_category("Sedekah", "variable", monthly_limit=50_000)

    txn, _ = service.pay_variable_category(category["id"])
    assert txn["wallet_id"] == default_wallet["id"]


def test_pay_variable_category_rejects_fixed_kind(budget_env):
    from features.budget.errors import BudgetValidationError

    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Rent", "fixed", monthly_limit=1_000_000)

    with pytest.raises(BudgetValidationError):
        service.pay_variable_category(category["id"])


def test_delete_category_with_payment_history_is_409(budget_env):
    from features.budget.errors import BudgetConflict

    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    category = service.create_category("Sedekah", "variable", monthly_limit=50_000)
    service.pay_variable_category(category["id"], create_transaction=False)

    with pytest.raises(BudgetConflict):
        service.delete_category(category["id"])
