"""Covers db.py's rollback() and integrity_errors() — the two pieces
Phase 4's mark-paid 409 path depends on. rollback() is meaningful on both
dialects (SQLite's is native), but the bug this guards against is
Postgres-only: without it, the first IntegrityError on a connection
poisons every subsequent statement with InFailedSqlTransaction until a
rollback happens."""
import importlib
import os

import pytest


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATABASE_URL", "")

    import db as db_module
    import database as database_module
    import features.budget.schema as schema_module
    for m in (db_module, schema_module, database_module):
        importlib.reload(m)

    database_module.init_db()
    yield db_module

    for m in (db_module, schema_module, database_module):
        importlib.reload(m)


def test_rollback_recovers_connection_after_integrity_error(db_env):
    conn = db_env.db_conn()
    conn.execute(
        "INSERT INTO budget_wallets (name, created_at) VALUES (?, ?)",
        ("_DupWallet", "2026-08-03 00:00"),
    )
    conn.commit()

    with pytest.raises(db_env.integrity_errors()):
        conn.execute(
            "INSERT INTO budget_wallets (name, created_at) VALUES (?, ?)",
            ("_DupWallet", "2026-08-03 00:00"),
        )
    conn.rollback()

    # the connection must still be usable after rollback() — this is
    # exactly the recovery mark-paid's 409 path relies on
    conn.execute(
        "INSERT INTO budget_wallets (name, created_at) VALUES (?, ?)",
        ("_OtherWallet", "2026-08-03 00:00"),
    )
    conn.commit()
    row = conn.execute("SELECT COUNT(*) FROM budget_wallets WHERE name = ?", ("_OtherWallet",)).fetchone()
    assert row[0] == 1
    conn.close()


def _pg_url():
    return os.environ.get("TEST_DATABASE_URL", "").strip()


requires_postgres = pytest.mark.skipif(
    not _pg_url(), reason="set TEST_DATABASE_URL to run against a real Postgres instance"
)


@pytest.fixture
def pg_db_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _pg_url())

    import db as db_module
    import database as database_module
    import features.budget.schema as schema_module
    for m in (db_module, schema_module, database_module):
        importlib.reload(m)

    database_module.init_db()
    conn = db_module.db_conn()
    conn.execute("DELETE FROM budget_wallets WHERE name LIKE '_Pg%'")
    conn.commit()
    conn.close()

    yield db_module

    conn = db_module.db_conn()
    conn.execute("DELETE FROM budget_wallets WHERE name LIKE '_Pg%'")
    conn.commit()
    conn.close()
    for m in (db_module, schema_module, database_module):
        importlib.reload(m)


@requires_postgres
def test_rollback_recovers_pg_connection_after_integrity_error(pg_db_env):
    """The bug this pins: without _PGConn.rollback(), a second statement
    on the same connection after an IntegrityError fails with
    InFailedSqlTransaction, not the constraint error you'd expect —
    verified against a live instance before rollback() existed."""
    conn = pg_db_env.db_conn()
    conn.execute(
        "INSERT INTO budget_wallets (name, created_at) VALUES (?, ?)",
        ("_PgDupWallet", "2026-08-03 00:00"),
    )
    conn.commit()

    with pytest.raises(pg_db_env.integrity_errors()):
        conn.execute(
            "INSERT INTO budget_wallets (name, created_at) VALUES (?, ?)",
            ("_PgDupWallet", "2026-08-03 00:00"),
        )
    conn.rollback()

    conn.execute(
        "INSERT INTO budget_wallets (name, created_at) VALUES (?, ?)",
        ("_PgOtherWallet", "2026-08-03 00:00"),
    )
    conn.commit()
    row = conn.execute("SELECT COUNT(*) FROM budget_wallets WHERE name = ?", ("_PgOtherWallet",)).fetchone()
    assert row[0] == 1
    conn.close()
