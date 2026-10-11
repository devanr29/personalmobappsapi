"""Migration 7 forces a full Wallet records re-pull so rows stored with
UTC recordDate get rewritten in WIB."""
import importlib
import json

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATABASE_URL", "")

    import db as db_module
    import database as database_module
    import features.budget.schema as schema_module
    for m in (db_module, database_module, schema_module):
        importlib.reload(m)

    database_module.init_db()
    yield database_module, schema_module


def test_migration_7_drops_only_the_records_cursor(env):
    database, schema = env
    database.state_set("wallet_sync_cursors", json.dumps({
        "account": "2026-08-01T00:00:00Z", "record": "2026-09-01T00:00:00Z",
        "record_offset": 60, "record_running_max": "2026-09-02T00:00:00Z",
    }))
    for step in schema._migration_7():
        step(None)
    assert json.loads(database.state_get("wallet_sync_cursors")) == {"account": "2026-08-01T00:00:00Z"}
