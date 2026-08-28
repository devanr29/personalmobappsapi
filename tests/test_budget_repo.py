import importlib

import pytest


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATABASE_URL", "")

    import db as db_module
    import database as database_module
    import features.budget.schema as schema_module
    import features.budget.repo as repo_module
    import features.budget.periods as periods_module
    for m in (db_module, schema_module, database_module, repo_module, periods_module):
        importlib.reload(m)

    database_module.init_db()
    yield repo_module

    for m in (db_module, schema_module, database_module, repo_module, periods_module):
        importlib.reload(m)


@pytest.fixture
def period_id(repo):
    import features.budget.periods as periods_module
    return periods_module.ensure_current_period(payroll_day=25)["id"]


def test_wallet_crud_and_balance(repo):
    wallet = repo.create_wallet("Cash", kind="cash", opening_balance=100_000, is_default=True)
    assert wallet["opening_balance"] == 100_000
    assert wallet["spendable"] is True

    assert repo.wallet_balance(wallet["id"]) == 100_000

    repo.create_transaction(50_000, "expense", wallet_id=wallet["id"])
    assert repo.wallet_balance(wallet["id"]) == 50_000

    repo.create_transaction(20_000, "income", wallet_id=wallet["id"])
    assert repo.wallet_balance(wallet["id"]) == 70_000

    assert repo.get_default_wallet()["id"] == wallet["id"]


def test_money_in_hand_excludes_non_spendable_wallets(repo):
    cash = repo.create_wallet("Cash", opening_balance=100_000, spendable=True)
    savings = repo.create_wallet("Savings", opening_balance=500_000, spendable=False)
    assert repo.money_in_hand() == 100_000

    repo.update_wallet(savings["id"], spendable=True)
    assert repo.money_in_hand() == 600_000
    assert repo.get_wallet(cash["id"])["spendable"] is True


def test_category_crud_and_spend_by_category(repo, period_id):
    category = repo.create_category("Fuel", "variable", monthly_limit=70_000)
    period = {"id": period_id}

    assert repo.spend_by_category(category["id"], period["id"]) == 0
    repo.create_transaction(30_000, "expense", category_id=category["id"], period_id=period["id"])
    assert repo.spend_by_category(category["id"], period["id"]) == 30_000

    repo.update_category(category["id"], monthly_limit=80_000)
    assert repo.get_category(category["id"])["monthly_limit"] == 80_000

    assert repo.category_in_use(category["id"]) is True


def test_transaction_soft_delete_excludes_from_queries(repo, period_id):
    category = repo.create_category("Food", "variable", monthly_limit=200_000)
    txn = repo.create_transaction(15_000, "expense", category_id=category["id"], period_id=period_id)

    assert repo.spend_by_category(category["id"], period_id) == 15_000
    repo.soft_delete_transaction(txn["id"])
    assert repo.spend_by_category(category["id"], period_id) == 0

    items, total = repo.get_transactions(period_id=period_id)
    assert total == 0
    assert items == []


def test_get_transactions_pagination_and_filters(repo, period_id):
    category = repo.create_category("Misc", "variable", monthly_limit=100_000)
    for i in range(5):
        repo.create_transaction(1_000 * (i + 1), "expense", category_id=category["id"], period_id=period_id)

    items, total = repo.get_transactions(period_id=period_id, limit=2, offset=0)
    assert total == 5
    assert len(items) == 2

    items, total = repo.get_transactions(period_id=period_id, limit=2, offset=4)
    assert len(items) == 1

    items, total = repo.get_transactions(period_id=period_id, direction="income")
    assert total == 0


def test_wallet_balances_batches_every_wallet_in_one_pass(repo):
    cash = repo.create_wallet("Cash", opening_balance=100_000, spendable=True)
    bank = repo.create_wallet("Bank", opening_balance=500_000, spendable=True)

    repo.create_transaction(20_000, "expense", wallet_id=cash["id"])
    repo.create_transaction(10_000, "income", wallet_id=bank["id"])

    balances = repo.wallet_balances()
    assert balances[cash["id"]] == 80_000
    assert balances[bank["id"]] == 510_000
    assert repo.wallet_balance(cash["id"]) == balances[cash["id"]]
    assert repo.money_in_hand() == balances[cash["id"]] + balances[bank["id"]]


def test_wallet_balances_counts_transfers_and_adjustments(repo):
    cash = repo.create_wallet("Cash", opening_balance=100_000, spendable=True)
    bank = repo.create_wallet("Bank", opening_balance=0, spendable=True)

    repo.create_transaction(30_000, "transfer", wallet_id=cash["id"], transfer_wallet_id=bank["id"])
    balances = repo.wallet_balances()
    assert balances[cash["id"]] == 70_000
    assert balances[bank["id"]] == 30_000
    # a transfer conserves the total across both wallets
    assert balances[cash["id"]] + balances[bank["id"]] == 100_000

    repo.create_transaction(5_000, "adjustment", wallet_id=cash["id"])
    assert repo.wallet_balances()[cash["id"]] == 75_000


def test_aggregate_results_are_plain_int_not_decimal(repo, period_id):
    category = repo.create_category("Fuel", "variable", monthly_limit=70_000)
    wallet = repo.create_wallet("Cash", opening_balance=100_000)
    repo.create_transaction(15_000, "expense", category_id=category["id"], wallet_id=wallet["id"], period_id=period_id)

    assert isinstance(repo.spend_by_category(category["id"], period_id), int)
    assert isinstance(repo.wallet_balance(wallet["id"]), int)
    assert isinstance(repo.money_in_hand(), int)
    assert isinstance(repo.wallet_balances()[wallet["id"]], int)


def test_get_transactions_list_includes_joined_names(repo, period_id):
    category = repo.create_category("Fuel", "variable", monthly_limit=70_000)
    wallet = repo.create_wallet("Cash", opening_balance=100_000)
    repo.create_transaction(15_000, "expense", category_id=category["id"], wallet_id=wallet["id"], period_id=period_id)

    items, _ = repo.get_transactions(period_id=period_id)
    assert items[0]["category_name"] == "Fuel"
    assert items[0]["wallet_name"] == "Cash"


def test_get_transactions_list_uncategorized_row_not_dropped(repo, period_id):
    repo.create_transaction(5_000, "expense", period_id=period_id)
    items, total = repo.get_transactions(period_id=period_id)
    assert total == 1
    assert items[0]["category_name"] is None
    assert items[0]["wallet_name"] is None
