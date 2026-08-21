"""Runs a subset of the insights-layer assertions against a real Postgres
instance (TEST_DATABASE_URL) — the only thing that catches substr()
dialect divergence, Postgres's stricter GROUP BY, and Decimal leaking
into a JSON response as a string instead of a number."""
import importlib
import os

import pytest


def _pg_url():
    return os.environ.get("TEST_DATABASE_URL", "").strip()


requires_postgres = pytest.mark.skipif(
    not _pg_url(), reason="set TEST_DATABASE_URL to run against a real Postgres instance"
)


@pytest.fixture
def pg_budget_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _pg_url())

    import db as db_module
    import database as database_module
    import features.budget.schema as schema_module
    import features.budget.repo as repo_module
    import features.budget.periods as periods_module
    import features.budget.compute as compute_module
    import features.budget.insights as insights_module
    import features.budget.service as service_module
    modules = (db_module, schema_module, database_module, repo_module,
               periods_module, compute_module, insights_module, service_module)
    for m in modules:
        importlib.reload(m)

    database_module.init_db()
    conn = db_module.db_conn()
    conn.execute("DELETE FROM budget_transactions WHERE wallet_id IN (SELECT id FROM budget_wallets WHERE name LIKE '_PgIns%')")
    conn.execute("DELETE FROM budget_categories WHERE name LIKE '_PgIns%'")
    conn.execute("DELETE FROM budget_wallets WHERE name LIKE '_PgIns%'")
    conn.commit()
    conn.close()

    yield service_module, repo_module

    conn = db_module.db_conn()
    conn.execute("DELETE FROM budget_transactions WHERE wallet_id IN (SELECT id FROM budget_wallets WHERE name LIKE '_PgIns%')")
    conn.execute("DELETE FROM budget_categories WHERE name LIKE '_PgIns%'")
    conn.execute("DELETE FROM budget_wallets WHERE name LIKE '_PgIns%'")
    conn.commit()
    conn.close()
    for m in modules:
        importlib.reload(m)


@requires_postgres
def test_insights_aggregates_are_int_not_decimal_on_postgres(pg_budget_env):
    service, repo = pg_budget_env
    wallet = repo.create_wallet("_PgInsCash", opening_balance=500_000, is_default=True)
    fuel = repo.create_category("_PgInsFuel", "variable", monthly_limit=70_000)
    period = service.build_period_view()
    repo.create_transaction(35_000, "expense", category_id=fuel["id"], wallet_id=wallet["id"], period_id=period["period_id"])

    data = service.build_insights()
    assert isinstance(data["stats"]["spendToDate"], int)
    assert isinstance(data["stats"]["freeMoney"], int)
    assert isinstance(data["stats"]["dailyBudget"], int)
    assert isinstance(data["categories"][0]["spend"], int)


@requires_postgres
def test_insights_daily_bucketing_matches_sqlite_semantics_on_postgres(pg_budget_env):
    service, repo = pg_budget_env
    wallet = repo.create_wallet("_PgInsCash2", opening_balance=500_000, is_default=True)
    period = service.build_period_view()
    repo.create_transaction(
        10_000, "expense", wallet_id=wallet["id"], period_id=period["period_id"], occurred_at="2026-07-26 09:00",
    )
    repo.create_transaction(
        20_000, "expense", wallet_id=wallet["id"], period_id=period["period_id"], occurred_at="2026-07-28 09:00",
    )

    data = service.build_insights()
    by_date = {d["date"]: d for d in data["daily"]}
    assert by_date["2026-07-26"]["spend"] == 10_000
    assert by_date["2026-07-27"]["spend"] == 0  # dense gap-fill, same as SQLite
    assert by_date["2026-07-28"]["spend"] == 20_000


@requires_postgres
def test_insights_history_on_postgres(pg_budget_env):
    service, repo = pg_budget_env
    repo.create_wallet("_PgInsCash3", opening_balance=500_000, is_default=True)
    period = service.build_period_view()
    repo.create_transaction(15_000, "expense", period_id=period["period_id"])

    history = service.build_insights_history(periods=6)
    assert isinstance(history["periods"][0]["spend"], int)


@requires_postgres
def test_insights_history_month_mode_dense_gap_fill_on_postgres(pg_budget_env):
    # Exercises substr(occurred_at, 1, 7) + _int0() under the new
    # dense_months() gap-fill path -- a zero-filled synthetic month must
    # still be a plain int, not a Decimal or a missing key.
    service, repo = pg_budget_env
    from config import now_jkt
    repo.create_wallet("_PgInsCash4", opening_balance=500_000, is_default=True)
    current_month = now_jkt().date().strftime("%Y-%m")
    year, month = (int(x) for x in current_month.split("-"))
    idx = year * 12 + (month - 1) - 2
    y, m = divmod(idx, 12)
    older_month = f"{y:04d}-{m + 1:02d}"
    repo.create_transaction(25_000, "expense", occurred_at=f"{older_month}-05 09:00")

    history = service.build_insights_history(periods=6, group_by="month")
    months = [p["monthKey"] for p in history["periods"]]
    assert current_month in months
    gap_entry = next(p for p in history["periods"] if p["monthKey"] != older_month and p["monthKey"] != current_month)
    assert isinstance(gap_entry["spend"], int)
    assert gap_entry["spend"] == 0


@requires_postgres
def test_category_patterns_month_totals_are_int_on_postgres(pg_budget_env):
    # Exercises category_month_totals()'s substr()+_int0() grouping and the
    # dense_months_window() gap-fill path under Postgres's stricter GROUP BY.
    service, repo = pg_budget_env
    wallet = repo.create_wallet("_PgInsCash5", opening_balance=500_000, is_default=True)
    fuel = repo.create_category("_PgInsFuel2", "variable", monthly_limit=70_000)
    repo.create_transaction(35_000, "expense", category_id=fuel["id"], wallet_id=wallet["id"])

    patterns = service.build_category_patterns(months=3)
    entry = next(c for c in patterns["categories"] if c["categoryId"] == fuel["id"])
    assert isinstance(entry["total"], int)
    assert all(isinstance(v, int) for v in entry["series"])
