import importlib

import pytest


@pytest.fixture
def budget_env(tmp_path, monkeypatch):
    """Full-stack isolation: throwaway DB, every budget submodule reloaded
    so module-level `service`/`repo` references (bound once, at import
    time, in each other's namespaces) all resolve against the fresh DB."""
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


def test_no_wallets_returns_none(budget_env):
    service, repo = budget_env
    assert service.build_period_view() is None
    assert service.get_summary() is None


def test_full_view_matches_expected_shape_once_seeded(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=3_254_624, is_default=True)

    rent = repo.create_category("House Rent", "fixed")
    zakat = repo.create_category("Zakat", "fixed")
    internet = repo.create_category("Internet", "fixed")
    fuel = repo.create_category("Fuel", "variable", monthly_limit=70_000)

    # bills mirror the fixed categories (name/amount used by compute_budget,
    # not category_id) — still_owed/paid_fixed match by bill name.
    import db as db_module
    conn = db_module.db_conn()
    conn.execute(
        "INSERT INTO budget_bills (name, amount, due_day, created_at) VALUES (?, ?, ?, ?)",
        ("House Rent", 955_000, 25, "2026-08-03 00:00"),
    )
    conn.execute(
        "INSERT INTO budget_bills (name, amount, due_day, created_at) VALUES (?, ?, ?, ?)",
        ("Zakat", 250_000, 25, "2026-08-03 00:00"),
    )
    conn.execute(
        "INSERT INTO budget_bills (name, amount, due_day, created_at) VALUES (?, ?, ?, ?)",
        ("Internet", 150_000, None, "2026-08-03 00:00"),
    )
    conn.commit()
    conn.close()

    period = service.build_period_view()
    period_id = period["period_id"]

    # spend 35k on Fuel this period
    repo.create_transaction(35_000, "expense", category_id=fuel["id"], period_id=period_id)

    data = service.build_period_view()
    fuel_line = next(v for v in data["remaining_var"] if v["name"] == "Fuel")
    assert fuel_line["spent"] == 35_000
    assert fuel_line["remaining"] == 35_000

    # nothing paid yet -> all three bills still owed
    still_owed_names = {e["name"] for e in data["still_owed"]}
    assert still_owed_names == {"House Rent", "Zakat", "Internet"}
    assert data["total_still_owed"] == 955_000 + 250_000 + 150_000

    summary = service.get_summary()
    assert summary["remaining"] == 3_254_624
    assert summary["deductions"] == data["total_deductions"]
    # dailyBudget is coerced to int at the serialization boundary (repo.py
    # aggregates return Decimal on Postgres; a raw float/Decimal in JSON
    # would render as a string or NaN client-side) — compute_budget()'s
    # own float output in `data` is untouched.
    assert summary["dailyBudget"] == int(data["daily_budget"])
    assert "computedAt" in summary


def test_occurred_at_is_normalized_to_naive_minute_precision(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=100_000, is_default=True)

    txn, _ = service.create_transaction(5_000, "expense", occurred_at="2026-08-03T14:22:00+07:00")
    assert txn["occurred_at"] == "2026-08-03 14:22"

    txn2, _ = service.create_transaction(5_000, "expense", occurred_at="2026-08-03")
    assert txn2["occurred_at"] == "2026-08-03 00:00"


def test_list_transactions_date_to_is_inclusive_of_the_whole_day(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=100_000, is_default=True)

    service.create_transaction(5_000, "expense", occurred_at="2026-08-03 23:00")

    items, total = service.list_transactions(date_to="2026-08-03")
    assert total == 1
    assert len(items) == 1


def test_paying_a_bill_removes_it_from_still_owed(budget_env):
    service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)

    import db as db_module
    conn = db_module.db_conn()
    cur = conn.execute(
        "INSERT INTO budget_bills (name, amount, due_day, created_at) VALUES (?, ?, ?, ?)",
        ("Internet", 150_000, None, "2026-08-03 00:00"),
    )
    bill_id = cur.lastrowid
    conn.commit()
    conn.close()

    period = service.build_period_view()
    period_id = period["period_id"]
    assert any(e["name"] == "Internet" for e in period["still_owed"])

    conn = db_module.db_conn()
    conn.execute(
        "INSERT INTO budget_bill_payments (bill_id, period_id, paid_at) VALUES (?, ?, ?)",
        (bill_id, period_id, "2026-08-03 00:00"),
    )
    conn.commit()
    conn.close()

    data = service.build_period_view()
    assert not any(e["name"] == "Internet" for e in data["still_owed"])
    assert data["total_still_owed"] == 0
