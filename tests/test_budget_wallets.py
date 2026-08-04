"""Wallet CRUD, transfer, reconcile, and the delete-guard via the service
layer."""
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


def test_create_update_wallet(budget_env):
    service, repo = budget_env
    wallet = service.create_wallet("Cash", opening_balance=100_000, is_default=True)
    assert wallet["opening_balance"] == 100_000

    updated = service.update_wallet(wallet["id"], name="Cash Wallet", spendable=False)
    assert updated["name"] == "Cash Wallet"
    assert updated["spendable"] is False


def test_transfer_conserves_total_across_wallets(budget_env):
    service, repo = budget_env
    cash = service.create_wallet("Cash", opening_balance=500_000, is_default=True)
    bank = service.create_wallet("Bank", opening_balance=0)

    txn, summary = service.transfer_between_wallets(cash["id"], bank["id"], 200_000)
    assert txn["direction"] == "transfer"

    balances = repo.wallet_balances()
    assert balances[cash["id"]] == 300_000
    assert balances[bank["id"]] == 200_000
    assert balances[cash["id"]] + balances[bank["id"]] == 500_000


def test_transfer_rejects_same_wallet(budget_env):
    from features.budget.errors import BudgetValidationError

    service, repo = budget_env
    cash = service.create_wallet("Cash", opening_balance=500_000, is_default=True)
    with pytest.raises(BudgetValidationError):
        service.transfer_between_wallets(cash["id"], cash["id"], 100_000)


def test_reconcile_positive_delta_creates_adjustment(budget_env):
    service, repo = budget_env
    cash = service.create_wallet("Cash", opening_balance=100_000, is_default=True)

    result, summary = service.reconcile_wallet(cash["id"], 150_000)
    assert result["adjusted"] is True
    assert result["delta"] == 50_000
    assert repo.wallet_balance(cash["id"]) == 150_000


def test_reconcile_negative_delta(budget_env):
    service, repo = budget_env
    cash = service.create_wallet("Cash", opening_balance=100_000, is_default=True)

    result, summary = service.reconcile_wallet(cash["id"], 60_000)
    assert result["delta"] == -40_000
    assert repo.wallet_balance(cash["id"]) == 60_000


def test_reconcile_no_change_does_not_create_transaction(budget_env):
    service, repo = budget_env
    cash = service.create_wallet("Cash", opening_balance=100_000, is_default=True)

    result, summary = service.reconcile_wallet(cash["id"], 100_000)
    assert result["adjusted"] is False
    items, total = service.list_transactions()
    assert total == 0


def test_adjustment_excluded_from_spend_aggregates(budget_env):
    # A reconcile must never look like a spend spike on the daily chart —
    # spend_by_category_for_period only counts direction='expense'.
    service, repo = budget_env
    cash = service.create_wallet("Cash", opening_balance=100_000, is_default=True)
    period = service.build_period_view()
    service.reconcile_wallet(cash["id"], 500_000)

    spend_rows = repo.spend_by_category_for_period(period["period_id"])
    assert spend_rows == []


def test_delete_wallet_in_use_is_409(budget_env):
    from features.budget.errors import BudgetConflict

    service, repo = budget_env
    cash = service.create_wallet("Cash", opening_balance=100_000, is_default=True)
    repo.create_transaction(10_000, "expense", wallet_id=cash["id"])

    with pytest.raises(BudgetConflict):
        service.delete_wallet(cash["id"])


def test_archive_wallet_works_when_in_use(budget_env):
    service, repo = budget_env
    cash = service.create_wallet("Cash", opening_balance=100_000, is_default=True)
    repo.create_transaction(10_000, "expense", wallet_id=cash["id"])

    archived = service.update_wallet(cash["id"], archived=True)
    assert archived["archived"] is True


def test_delete_unused_wallet_succeeds(budget_env):
    service, repo = budget_env
    savings = service.create_wallet("Savings", opening_balance=0)
    service.delete_wallet(savings["id"])
    assert repo.get_wallet(savings["id"]) is None
