"""Adapter-level tests for db.py / database.py against the SQLite fallback
path. Postgres-specific behavior (dialect translation, upsert) is exercised
by setting TEST_DATABASE_URL and re-running against a real instance — see
conftest.py."""
import importlib
import os

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Point DB_PATH at a throwaway file and reload db.py + database.py so
    every module-level constant (DB_PATH, IS_PG) picks up the override."""
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("DATABASE_URL", "")

    import db as db_module
    import database as database_module
    importlib.reload(db_module)
    importlib.reload(database_module)

    database_module.init_db()
    yield database_module

    importlib.reload(db_module)
    importlib.reload(database_module)


def test_init_db_creates_tables_and_is_idempotent(tmp_db):
    tmp_db.init_db()  # second call must not raise
    tmp_db.state_set("probe", "1")
    assert tmp_db.state_get("probe") == "1"


def test_state_roundtrip(tmp_db):
    assert tmp_db.state_get("missing_key") is None
    tmp_db.state_set("k", "v1")
    assert tmp_db.state_get("k") == "v1"
    tmp_db.state_set("k", "v2")  # upsert path
    assert tmp_db.state_get("k") == "v2"
    tmp_db.state_del("k")
    assert tmp_db.state_get("k") is None


def test_conversation_window_trims_to_limit(tmp_db):
    from config import CONV_WINDOW

    for i in range(CONV_WINDOW * 3):
        tmp_db.save_conv_turn("user", f"turn {i}")
    history = tmp_db.load_conv_history()
    assert len(history) == CONV_WINDOW * 2
    assert history[-1]["content"] == f"turn {CONV_WINDOW * 3 - 1}"


def test_clear_conv_history(tmp_db):
    tmp_db.save_conv_turn("user", "hi")
    tmp_db.clear_conv_history()
    assert tmp_db.load_conv_history() == []


def _pg_url():
    return os.environ.get("TEST_DATABASE_URL", "").strip()


requires_postgres = pytest.mark.skipif(
    not _pg_url(), reason="set TEST_DATABASE_URL to run against a real Postgres instance"
)


@pytest.fixture
def pg_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", _pg_url())

    import db as db_module
    import database as database_module
    importlib.reload(db_module)
    importlib.reload(database_module)

    database_module.init_db()
    yield database_module

    database_module.state_del("_test_probe_key")
    importlib.reload(db_module)
    importlib.reload(database_module)


@requires_postgres
def test_state_set_persists_on_a_fresh_connection_against_postgres(pg_db):
    """Regression test for a real bug found while wiring up Postgres:
    state_set()'s INSERT targets bot_state, whose primary key (TEXT) has
    no backing sequence. On a brand-new connection, _pg_lastrowid's
    lastval() probe raised ObjectNotInPrerequisiteState — and without the
    SAVEPOINT guard in db.py, that aborted the whole transaction, so the
    caller's following conn.commit() silently discarded the write with no
    exception raised anywhere. Verified against a live Neon instance
    before the fix, and this test would have failed on `assert ==
    "value1"` (state_get would have returned None instead)."""
    pg_db.state_set("_test_probe_key", "value1")
    assert pg_db.state_get("_test_probe_key") == "value1"
    pg_db.state_set("_test_probe_key", "value2")  # upsert path on a 2nd fresh connection
    assert pg_db.state_get("_test_probe_key") == "value2"
    pg_db.state_del("_test_probe_key")
    assert pg_db.state_get("_test_probe_key") is None
