import importlib
import shutil

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("DATABASE_URL", "")

    import db as db_module
    import database as database_module
    import features.budget.schema as schema_module
    importlib.reload(db_module)
    importlib.reload(schema_module)
    importlib.reload(database_module)

    database_module.init_db()
    yield database_module

    importlib.reload(db_module)
    importlib.reload(schema_module)
    importlib.reload(database_module)


_BUDGET_TABLES = [
    "budget_wallets", "budget_categories", "budget_periods", "budget_bills",
    "budget_goals", "budget_transactions", "budget_bill_payments",
    "budget_goal_contributions", "budget_alert_prefs", "budget_alert_log",
]


def test_fresh_db_creates_all_budget_tables(tmp_db):
    import sqlite3
    conn = sqlite3.connect(db_path_of(tmp_db))
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    for table in _BUDGET_TABLES:
        assert table in existing, f"{table} was not created"


def test_init_db_is_idempotent(tmp_db):
    tmp_db.init_db()  # second call must not raise
    tmp_db.init_db()  # third, for good measure
    import sqlite3
    conn = sqlite3.connect(db_path_of(tmp_db))
    count = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'budget_%'").fetchone()[0]
    conn.close()
    assert count == len(_BUDGET_TABLES)


def test_existing_bot_state_rows_survive_a_run_against_a_real_db_copy(tmp_path):
    """Copy the real bot.db (with its 3 live bot_state keys) and confirm
    running init_db() against the copy only adds tables/keys, never drops
    or alters the existing ones."""
    import os
    real_db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot.db")
    if not os.path.exists(real_db):
        pytest.skip("no real bot.db present in this environment")

    db_copy = tmp_path / "bot_copy.db"
    shutil.copy(real_db, db_copy)

    import sqlite3
    conn = sqlite3.connect(db_copy)
    before = dict(conn.execute("SELECT key, value FROM bot_state").fetchall())
    conn.close()
    assert len(before) >= 1

    os.environ["DB_PATH"] = str(db_copy)
    os.environ["DATABASE_URL"] = ""
    import db as db_module
    import database as database_module
    importlib.reload(db_module)
    importlib.reload(database_module)
    database_module.init_db()

    conn = sqlite3.connect(db_copy)
    after = dict(conn.execute("SELECT key, value FROM bot_state").fetchall())
    conn.close()

    for key, value in before.items():
        if key == "budget_schema_version":
            # The one key that's SUPPOSED to change: a copy of the real
            # (older) bot.db should get migrated forward to whatever this
            # codebase's current BUDGET_SCHEMA_VERSION is, not stay pinned
            # to whatever version the copy happened to be at.
            import features.budget.schema as schema_module
            assert int(after[key]) == schema_module.BUDGET_SCHEMA_VERSION
            assert int(after[key]) >= int(value)
            continue
        assert after.get(key) == value, f"bot_state[{key}] changed or disappeared"

    del os.environ["DB_PATH"]
    del os.environ["DATABASE_URL"]
    importlib.reload(db_module)
    importlib.reload(database_module)


def db_path_of(database_module):
    import db as db_module
    return db_module.DB_PATH
