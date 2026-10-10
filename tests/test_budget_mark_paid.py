"""Mark-as-paid modes shared by bills and variable categories: mark only
(no transaction), attach many existing expenses, the amount-mismatch
check, and deleting a settling transaction un-paying the card."""
import importlib

import pytest

from features.budget.errors import BudgetAmountMismatch, BudgetConflict


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


def _expense(service, wallet, amount, category_id=None):
    txn, _ = service.create_transaction(
        amount=amount, direction="expense", wallet_id=wallet["id"], category_id=category_id,
    )
    return txn


def _bill_paid(service, bill_id):
    return not any(b["id"] == bill_id for b in service.build_period_view()["still_owed"])


def _category_item(service, category_id):
    return next(v for v in service.build_period_view()["remaining_var"] if v["id"] == category_id)


@pytest.fixture
def wallet(budget_env):
    _, repo = budget_env
    return repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)


# ---------------------------------------------------------------- mark only
def test_mark_only_bill_creates_no_transaction_and_keeps_balance(budget_env, wallet):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)

    txn, _ = service.pay_bill(bill["id"], create_transaction=False)

    assert txn is None
    assert _bill_paid(service, bill["id"])
    assert service.list_transactions()[1] == 0
    assert repo.wallet_balance(wallet["id"]) == 1_000_000


# ---------------------------------------------------------------- multi-attach
def test_attach_many_transactions_to_bill(budget_env, wallet):
    service, repo = budget_env
    fixed = service.create_category("Utilities", "fixed")
    bill = service.create_bill("Internet", 150_000, category_id=fixed["id"])
    a = _expense(service, wallet, 100_000)
    b = _expense(service, wallet, 50_000)

    service.pay_bill(bill["id"], transaction_ids=[a["id"], b["id"]])

    assert _bill_paid(service, bill["id"])
    for t in (a, b):
        refiled = repo.get_transaction(t["id"])
        assert refiled["bill_id"] == bill["id"]
        assert refiled["category_id"] == fixed["id"]
    payment = repo.get_bill_payment(bill["id"], service.build_period_view()["period_id"])
    assert {l["transaction_id"] for l in repo.get_payment_links("bill", payment["id"])} == {a["id"], b["id"]}
    assert service.list_transactions()[1] == 2  # nothing new logged


def test_attach_many_transactions_to_category_marks_it_paid(budget_env, wallet):
    service, repo = budget_env
    food = service.create_category("Food", "variable", monthly_limit=100_000)
    a = _expense(service, wallet, 60_000)
    b = _expense(service, wallet, 40_000)

    service.pay_variable_category(food["id"], transaction_ids=[a["id"], b["id"]])

    item = _category_item(service, food["id"])
    assert item["paid"] is True
    assert item["spent"] == 100_000
    assert repo.get_transaction(a["id"])["category_id"] == food["id"]
    assert repo.get_transaction(b["id"])["category_id"] == food["id"]


def test_category_total_counts_spend_already_filed_there(budget_env, wallet):
    service, repo = budget_env
    food = service.create_category("Food", "variable", monthly_limit=100_000)
    _expense(service, wallet, 30_000, category_id=food["id"])
    already_there = _expense(service, wallet, 20_000, category_id=food["id"])
    new = _expense(service, wallet, 50_000)

    # 30k + 20k already spent, +50k attached = 100k: no mismatch, and the
    # 20k row selected again isn't double-counted.
    service.pay_variable_category(food["id"], transaction_ids=[already_there["id"], new["id"]])
    assert _category_item(service, food["id"])["paid"] is True


# ---------------------------------------------------------------- amount mismatch
def test_bill_mismatch_without_amount_change_writes_nothing(budget_env, wallet):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)
    a = _expense(service, wallet, 100_000)

    with pytest.raises(BudgetAmountMismatch) as exc:
        service.pay_bill(bill["id"], transaction_ids=[a["id"]])

    assert exc.value.details == {"total": 100_000, "amount": 150_000}
    assert not _bill_paid(service, bill["id"])
    assert repo.get_transaction(a["id"])["bill_id"] is None
    assert repo.get_links_for_transaction(a["id"]) == []


def test_category_mismatch_without_amount_change_writes_nothing(budget_env, wallet):
    service, repo = budget_env
    food = service.create_category("Food", "variable", monthly_limit=100_000)
    a = _expense(service, wallet, 70_000)

    with pytest.raises(BudgetAmountMismatch) as exc:
        service.pay_variable_category(food["id"], transaction_ids=[a["id"]])

    assert exc.value.details == {"total": 70_000, "amount": 100_000}
    assert _category_item(service, food["id"])["paid"] is False
    assert repo.get_transaction(a["id"])["category_id"] is None


def test_bill_amount_change_period_sets_override_only(budget_env, wallet):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)
    a = _expense(service, wallet, 120_000)

    service.pay_bill(bill["id"], transaction_ids=[a["id"]], amount_change="period")

    view = service.build_period_view()
    assert view["bill_period_amounts"] == {bill["id"]: 120_000}
    assert repo.get_bill(bill["id"])["amount"] == 150_000


def test_bill_amount_change_permanent_updates_bill(budget_env, wallet):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)
    a = _expense(service, wallet, 120_000)

    service.pay_bill(bill["id"], transaction_ids=[a["id"]], amount_change="permanent")

    assert repo.get_bill(bill["id"])["amount"] == 120_000
    assert service.build_period_view()["bill_period_amounts"] == {}


def test_category_amount_change_period_overrides_limit_this_period(budget_env, wallet):
    service, repo = budget_env
    food = service.create_category("Food", "variable", monthly_limit=100_000)
    a = _expense(service, wallet, 130_000)

    service.pay_variable_category(food["id"], transaction_ids=[a["id"]], amount_change="period")

    item = _category_item(service, food["id"])
    assert item["limit"] == 130_000
    assert item["over_budget"] == 0
    assert repo.get_category(food["id"])["monthly_limit"] == 100_000


def test_category_amount_change_permanent_updates_limit(budget_env, wallet):
    service, repo = budget_env
    food = service.create_category("Food", "variable", monthly_limit=100_000)
    a = _expense(service, wallet, 130_000)

    service.pay_variable_category(food["id"], transaction_ids=[a["id"]], amount_change="permanent")

    assert repo.get_category(food["id"])["monthly_limit"] == 130_000
    assert _category_item(service, food["id"])["limit"] == 130_000


# ---------------------------------------------------------------- delete -> unpaid
def test_deleting_created_bill_transaction_unpays_bill(budget_env, wallet):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)
    txn, _ = service.pay_bill(bill["id"])

    service.delete_transaction(txn["id"])

    assert not _bill_paid(service, bill["id"])
    # And it can be paid again, the UNIQUE(bill, period) row is gone.
    service.pay_bill(bill["id"])


def test_deleting_created_category_transaction_unpays_category(budget_env, wallet):
    service, repo = budget_env
    food = service.create_category("Food", "variable", monthly_limit=100_000)
    txn, _ = service.pay_variable_category(food["id"])

    service.delete_transaction(txn["id"])

    assert _category_item(service, food["id"])["paid"] is False


def test_deleting_one_of_two_attached_keeps_paid_both_unpays(budget_env, wallet):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)
    a = _expense(service, wallet, 100_000)
    b = _expense(service, wallet, 50_000)
    service.pay_bill(bill["id"], transaction_ids=[a["id"], b["id"]])

    service.delete_transaction(a["id"])
    assert _bill_paid(service, bill["id"])

    service.delete_transaction(b["id"])
    assert not _bill_paid(service, bill["id"])


def test_deleting_unrelated_transaction_leaves_mark_only_payment(budget_env, wallet):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)
    service.pay_bill(bill["id"], create_transaction=False)
    other = _expense(service, wallet, 10_000)

    service.delete_transaction(other["id"])

    assert _bill_paid(service, bill["id"])


# ---------------------------------------------------------------- unpay
def test_unpay_unties_attached_and_restores_category(budget_env, wallet):
    service, repo = budget_env
    snacks = service.create_category("Snacks", "variable")
    food = service.create_category("Food", "variable", monthly_limit=100_000)
    a = _expense(service, wallet, 60_000, category_id=snacks["id"])
    b = _expense(service, wallet, 40_000)
    service.pay_variable_category(food["id"], transaction_ids=[a["id"], b["id"]])

    service.unpay_variable_category(food["id"])

    assert repo.get_transaction(a["id"])["category_id"] == snacks["id"]
    assert repo.get_transaction(b["id"])["category_id"] is None
    assert repo.get_transaction(a["id"])["deleted_at"] is None
    assert repo.get_links_for_transaction(a["id"]) == []
    assert _category_item(service, food["id"])["paid"] is False


def test_unpay_bill_soft_deletes_created_and_unties_attached(budget_env, wallet):
    service, repo = budget_env
    fixed = service.create_category("Utilities", "fixed")
    bill = service.create_bill("Internet", 150_000, category_id=fixed["id"])
    a = _expense(service, wallet, 150_000)
    service.pay_bill(bill["id"], transaction_ids=[a["id"]])

    service.unpay_bill(bill["id"])
    untied = repo.get_transaction(a["id"])
    assert untied["bill_id"] is None
    assert untied["category_id"] is None  # bill category was only added by the attach
    assert untied["deleted_at"] is None

    created, _ = service.pay_bill(bill["id"])
    service.unpay_bill(bill["id"])
    assert repo.get_transaction(created["id"])["deleted_at"] is not None


# ---------------------------------------------------------------- conflicts
def test_one_transaction_cannot_settle_two_bills(budget_env, wallet):
    service, repo = budget_env
    first = service.create_bill("Internet", 150_000)
    second = service.create_bill("Phone", 150_000)
    a = _expense(service, wallet, 150_000)
    service.pay_bill(first["id"], transaction_ids=[a["id"]])

    with pytest.raises(BudgetConflict):
        service.pay_bill(second["id"], transaction_ids=[a["id"]])

    assert not _bill_paid(service, second["id"])
    assert repo.get_transaction(a["id"])["bill_id"] == first["id"]


def test_attach_to_already_paid_bill_is_conflict_and_leaves_rows_alone(budget_env, wallet):
    service, repo = budget_env
    bill = service.create_bill("Internet", 150_000)
    service.pay_bill(bill["id"], create_transaction=False)
    a = _expense(service, wallet, 150_000)

    with pytest.raises(BudgetConflict):
        service.pay_bill(bill["id"], transaction_ids=[a["id"]])

    assert repo.get_transaction(a["id"])["bill_id"] is None


# ---------------------------------------------------------------- migration 6
def test_migration_6_backfills_existing_payments_into_links(budget_env, wallet):
    service, repo = budget_env
    import features.budget.schema as schema
    from db import db_conn

    bill = service.create_bill("Internet", 150_000)
    attached_bill = service.create_bill("Phone", 50_000)
    food = service.create_category("Food", "variable", monthly_limit=100_000)
    period_id = service.build_period_view()["period_id"]

    created = repo.create_transaction(150_000, "expense", wallet_id=wallet["id"], period_id=period_id,
                                      bill_id=bill["id"], source="bill")
    attached = repo.create_transaction(50_000, "expense", wallet_id=wallet["id"], period_id=period_id,
                                       bill_id=attached_bill["id"])
    cat_txn = repo.create_transaction(100_000, "expense", wallet_id=wallet["id"], period_id=period_id,
                                      category_id=food["id"], source="category_payment")
    # Pre-migration-6 rows: payment.transaction_id set, no link rows.
    repo.create_bill_payment(bill["id"], period_id, created["id"], "2026-01-01")
    repo.create_bill_payment(attached_bill["id"], period_id, attached["id"], "2026-01-01")
    repo.create_category_payment(food["id"], period_id, cat_txn["id"], "2026-01-01")

    conn = db_conn()
    for statement in schema._migration_6():
        if callable(statement):
            statement(conn)
        else:
            conn.execute(statement)
    conn.commit()
    conn.close()

    created_link, = repo.get_links_for_transaction(created["id"])
    assert created_link["kind"] == "bill" and created_link["created_by_payment"] is True
    attached_link, = repo.get_links_for_transaction(attached["id"])
    assert attached_link["created_by_payment"] is False
    cat_link, = repo.get_links_for_transaction(cat_txn["id"])
    assert cat_link["kind"] == "category" and cat_link["created_by_payment"] is True

    # Re-running is a no-op (idempotent backfill).
    conn = db_conn()
    schema._migration_6()[-1](conn)
    conn.commit()
    conn.close()
    assert len(repo.get_links_for_transaction(created["id"])) == 1

    # The backfilled link drives unpay: the created row goes, the attached stays.
    service.unpay_bill(bill["id"])
    service.unpay_bill(attached_bill["id"])
    assert repo.get_transaction(created["id"])["deleted_at"] is not None
    assert repo.get_transaction(attached["id"])["deleted_at"] is None
    assert repo.get_transaction(attached["id"])["bill_id"] is None
