"""Exercises features/budget/wallet/sync.py's private per-entity pull/push
functions against an isolated throwaway DB (see _isolated_db below) — every
row created here is also torn down in a finally block, belt-and-suspenders,
but the isolation is what actually matters: _pull_accounts()/_pull_records()
call _set_cursor() as a real side effect whenever apply=True, and that
persists into bot_state regardless of whether the test's own rows get
cleaned up, so this must never point at the real bot.db."""
import importlib

import pytest

from db import db_conn
from features.budget import repo
from features.budget.wallet import mapping, sync


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Same recipe as tests/test_budget_schema.py's tmp_db and
    tests/test_budget_alerts.py's budget_env fixtures, applied file-wide via
    autouse so every test below — including direct sync._pull_*()/_push_*()
    calls that never go through the client fixture — gets a fresh SQLite
    file instead of the real bot.db."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATABASE_URL", "")

    import database as database_module
    import db as db_module
    import features.budget.repo as repo_module
    import features.budget.schema as schema_module
    import features.budget.wallet.sync as sync_module
    modules = (db_module, schema_module, database_module, repo_module, sync_module)
    for m in modules:
        importlib.reload(m)

    database_module.init_db()
    yield

    for m in modules:
        importlib.reload(m)


class FakeClient:
    def __init__(self, pages=None, post_response=None):
        self.pages = pages or {}
        self.post_calls = []
        self.patch_calls = []
        self.paginate_calls = []
        self.post_response = post_response if post_response is not None else {"id": "remote-created-1"}

    def paginate(self, path, **params):
        self.paginate_calls.append((path, params))
        return list(self.pages.get(path, []))

    def paginate_pages(self, path, start_offset=0, **params):
        self.paginate_calls.append((path, params))
        return [(list(self.pages.get(path, [])), None)]

    def post(self, path, body):
        self.post_calls.append((path, body))
        return self.post_response

    def patch(self, path, body):
        self.patch_calls.append((path, body))
        return {}

    def configured(self):
        return True


def _cleanup_wallet(wallet_id):
    repo.delete_link(sync.ENTITY_ACCOUNT, wallet_id)
    repo.delete_wallet(wallet_id)


def _cleanup_category(category_id):
    repo.delete_link(sync.ENTITY_CATEGORY, category_id)
    repo.delete_category(category_id)


def _cleanup_transaction(txn_id):
    repo.delete_link(sync.ENTITY_RECORD, txn_id)
    repo.soft_delete_transaction(txn_id)


# ================================================================
# PULL — accounts
# ================================================================
def test_pull_accounts_creates_wallet_and_link():
    account = {"id": "acc-remote-1", "name": "_TestWalletSyncAccount", "accountType": "Cash",
               "currencyCode": "IDR", "initialBalance": 250000, "updatedAt": "2026-08-01T00:00:00Z"}
    client = FakeClient(pages={"/v1/api/accounts": [account]})
    result = sync._pull_accounts(client, cursor=None, apply=True)
    link = repo.get_link_by_remote(sync.ENTITY_ACCOUNT, "acc-remote-1")
    try:
        assert result["created"] == 1
        assert link is not None
        wallet = repo.get_wallet(link["local_id"])
        assert wallet["name"] == "_TestWalletSyncAccount"
        assert wallet["opening_balance"] == 250000
    finally:
        if link:
            _cleanup_wallet(link["local_id"])


def test_pull_accounts_skips_non_idr_currency():
    account = {"id": "acc-remote-usd", "name": "_TestWalletSyncUSD", "accountType": "Cash", "currencyCode": "USD", "initialBalance": 100}
    client = FakeClient(pages={"/v1/api/accounts": [account]})
    result = sync._pull_accounts(client, cursor=None, apply=True)
    assert result["created"] == 0
    assert len(result["skipped"]) == 1
    assert repo.get_link_by_remote(sync.ENTITY_ACCOUNT, "acc-remote-usd") is None


# ================================================================
# PULL — categories
# ================================================================
def test_pull_categories_skips_restricted_system_category():
    category = {"id": mapping.WALLET_TRANSFER_CATEGORY_ID, "name": "Transfer", "cardinality": "none"}
    client = FakeClient(pages={"/v1/api/categories": [category]})
    result = sync._pull_categories(client, cursor=None, apply=True)
    assert result["created"] == 0
    assert len(result["skipped"]) == 1
    assert repo.get_link_by_remote(sync.ENTITY_CATEGORY, mapping.WALLET_TRANSFER_CATEGORY_ID) is None


def test_pull_categories_creates_local_category():
    category = {"id": "cat-remote-1", "name": "_TestWalletSyncCategory", "cardinality": "want"}
    client = FakeClient(pages={"/v1/api/categories": [category]})
    result = sync._pull_categories(client, cursor=None, apply=True)
    link = repo.get_link_by_remote(sync.ENTITY_CATEGORY, "cat-remote-1")
    try:
        assert result["created"] == 1
        assert repo.get_category(link["local_id"])["kind"] == "variable"
    finally:
        if link:
            _cleanup_category(link["local_id"])


# ================================================================
# PULL — records
# ================================================================
def test_pull_records_always_overrides_the_api_default_recordDate_window():
    # The live API silently limits GET /records to the last ~3 months of
    # recordDate when no recordDate filter is given (confirmed 2026-08-12
    # via appliedRecordDateFilters in the real response) — regardless of
    # the updatedAt cursor below, which filters on a different field.
    # Without an explicit floor every record older than ~3 months would be
    # dropped from every pull forever.
    client = FakeClient(pages={"/v1/api/records": []})
    conn = db_conn()
    try:
        sync._pull_records(client, cursor=None, payroll_day=25, conn=conn, apply=True)
        sync._pull_records(client, cursor="2026-08-01T00:00:00Z", payroll_day=25, conn=conn, apply=True)
    finally:
        conn.close()
    assert len(client.paginate_calls) == 2
    for _, params in client.paginate_calls:
        assert params["recordDate"] == f"gte.{sync._RECORD_DATE_FLOOR}"
    assert client.paginate_calls[1][1]["updatedAt"] == "gte.2026-08-01T00:00:00Z"


def test_pull_records_skips_unknown_account():
    record = {"id": "rec-1", "accountId": "acc-not-linked", "convertedAmount": {"value": -1000}, "recordDate": "2026-08-01T00:00:00Z"}
    client = FakeClient(pages={"/v1/api/records": [record]})
    conn = db_conn()
    try:
        result = sync._pull_records(client, cursor=None, payroll_day=25, conn=conn, apply=True)
    finally:
        conn.close()
    assert result["created"] == 0
    assert len(result["skipped"]) == 1
    assert "unknown account" in result["skipped"][0]["reason"]


def test_pull_records_creates_transaction_with_correct_period():
    wallet = repo.create_wallet("_TestWalletSyncRecordWallet", opening_balance=0)
    repo.upsert_link(sync.ENTITY_ACCOUNT, wallet["id"], "acc-remote-2", local_synced_at="2020-01-01")
    record = {
        "id": "rec-2", "accountId": "acc-remote-2",
        "convertedAmount": {"value": -45000}, "recordDate": "2026-08-05T14:30:00Z",
        "note": "_TestWalletSyncNote", "updatedAt": "2026-08-05T14:31:00Z",
    }
    client = FakeClient(pages={"/v1/api/records": [record]})
    conn = db_conn()
    try:
        result = sync._pull_records(client, cursor=None, payroll_day=25, conn=conn, apply=True)
    finally:
        conn.close()

    link = repo.get_link_by_remote(sync.ENTITY_RECORD, "rec-2")
    try:
        assert result["created"] == 1
        assert link is not None
        txn = repo.get_transaction(link["local_id"])
        assert txn["amount"] == 45000
        assert txn["direction"] == "expense"
        assert txn["wallet_id"] == wallet["id"]
        assert txn["source"] == "wallet"
        assert txn["note"] == "_TestWalletSyncNote"
        assert txn["period_id"] is not None
    finally:
        if link:
            _cleanup_transaction(link["local_id"])
        _cleanup_wallet(wallet["id"])


def test_pull_records_does_not_clobber_an_unpushed_local_edit():
    wallet = repo.create_wallet("_TestWalletSyncEditWallet", opening_balance=0)
    repo.upsert_link(sync.ENTITY_ACCOUNT, wallet["id"], "acc-remote-3", local_synced_at="2020-01-01")

    txn = repo.create_transaction(amount=10000, direction="expense", wallet_id=wallet["id"], occurred_at="2026-08-01 09:00")
    # Link was "synced" in the past; the local row is then edited (which
    # stamps a fresh updated_at) — simulating an edit made after the last
    # sync but not yet pushed back to Wallet.
    repo.upsert_link(sync.ENTITY_RECORD, txn["id"], "rec-3", local_synced_at="2020-01-01T00:00:00")
    repo.update_transaction(txn["id"], note="edited locally, not yet pushed")

    record = {
        "id": "rec-3", "accountId": "acc-remote-3",
        "convertedAmount": {"value": -99999}, "recordDate": "2026-08-01T00:00:00Z",
        "updatedAt": "2026-08-01T00:00:01Z",
    }
    client = FakeClient(pages={"/v1/api/records": [record]})
    conn = db_conn()
    try:
        result = sync._pull_records(client, cursor=None, payroll_day=25, conn=conn, apply=True)
    finally:
        conn.close()

    try:
        assert result["updated"] == 0
        assert len(result["skipped"]) == 1
        assert "not yet pushed" in result["skipped"][0]["reason"]
        # local edit must survive untouched
        assert repo.get_transaction(txn["id"])["amount"] == 10000
    finally:
        _cleanup_transaction(txn["id"])
        _cleanup_wallet(wallet["id"])


def test_pull_records_deadline_stops_at_page_boundary_and_resumes_by_offset():
    """A first backfill too big for one bounded request: the run stops at a
    page boundary, reports hasMore, persists its offset, and the next run
    resumes from there. The real updatedAt watermark stays unset until the
    whole history has drained (results aren't sorted by updatedAt, so a
    mid-backfill watermark would strand later-but-older rows)."""
    import time as _time

    wallet = repo.create_wallet("_TestWalletSyncBackfill", opening_balance=0)
    repo.upsert_link(sync.ENTITY_ACCOUNT, wallet["id"], "acc-bf", local_synced_at="2020-01-01")

    def _rec(n):
        return {
            "id": f"bf-{n}", "accountId": "acc-bf",
            "convertedAmount": {"value": -1000 * n}, "recordDate": "2026-08-01T00:00:00Z",
            "updatedAt": f"2026-08-0{n}T00:00:00Z",
        }

    class PagedClient:
        pages = [[_rec(1), _rec(2)], [_rec(3), _rec(4)], [_rec(5)]]

        def __init__(self):
            self.offsets_seen = []

        def configured(self):
            return True

        def paginate_pages(self, path, start_offset=0, **params):
            self.offsets_seen.append(start_offset)
            idx = start_offset // 2
            while idx < len(self.pages):
                page = self.pages[idx]
                idx += 1
                yield page, (idx * 2 if idx < len(self.pages) else None)

    client = PagedClient()
    past = _time.monotonic() - 1
    conn = db_conn()
    try:
        r1 = sync._pull_records(client, cursor=None, payroll_day=25, conn=conn, apply=True, deadline=past)
        assert (r1["created"], r1["hasMore"]) == (2, True)
        assert sync._get_record_progress()[0] == 2
        assert sync._get_cursors().get(sync.ENTITY_RECORD) is None  # watermark NOT advanced mid-backfill

        r2 = sync._pull_records(client, cursor=None, payroll_day=25, conn=conn, apply=True, deadline=past)
        assert (r2["created"], r2["hasMore"]) == (2, True)
        assert sync._get_record_progress()[0] == 4

        r3 = sync._pull_records(client, cursor=None, payroll_day=25, conn=conn, apply=True, deadline=None)
        assert (r3["created"], r3["hasMore"]) == (1, False)
        assert sync._get_record_progress() == (0, None)  # backfill progress cleared
        assert sync._get_cursors().get(sync.ENTITY_RECORD) == "2026-08-05T00:00:00Z"  # watermark advanced now
        assert client.offsets_seen == [0, 2, 4]
    finally:
        for n in range(1, 6):
            link = repo.get_link_by_remote(sync.ENTITY_RECORD, f"bf-{n}")
            if link:
                _cleanup_transaction(link["local_id"])
        conn.close()
        _cleanup_wallet(wallet["id"])


def test_pull_all_skips_completed_entity_pulls_while_a_backfill_is_resuming(monkeypatch):
    """Once a records backfill is mid-flight (offset persisted), a resumed
    pull_all() call goes straight to /records — re-walking the five
    already-drained entities every round just burns seconds against a
    far-region DB."""
    monkeypatch.setattr("features.budget.service.get_payroll_day", lambda: 25)

    sync._set_record_progress(30, "2026-08-01T00:00:00Z")  # a backfill is in progress
    calls = []

    class FC:
        def configured(self):
            return True

        def paginate(self, path, **params):
            calls.append(path)
            return []

        def paginate_pages(self, path, start_offset=0, **params):
            calls.append(path)
            return [([], None)]  # nothing left -> records pull completes

    monkeypatch.setattr(sync, "WalletClient", lambda: FC())

    summary = sync.pull_all(apply=True, max_seconds=5)

    assert calls == ["/v1/api/records"]  # the other five endpoints untouched
    assert summary["accounts"] == {"created": 0, "updated": 0, "skipped": []}
    assert summary["records"]["hasMore"] is False
    assert sync._get_record_progress() == (0, None)  # drained -> progress cleared


# ================================================================
# PUSH — records
# ================================================================
def test_push_records_creates_remote_record_for_new_local_transaction():
    wallet = repo.create_wallet("_TestWalletSyncPushWallet", opening_balance=0)
    repo.upsert_link(sync.ENTITY_ACCOUNT, wallet["id"], "acc-remote-push-1", local_synced_at="2020-01-01")
    txn = repo.create_transaction(amount=15000, direction="expense", wallet_id=wallet["id"], occurred_at="2026-08-01 10:00", note="_TestPush")

    client = FakeClient(post_response={"id": "remote-record-created"})
    result = sync._push_records(client, apply=True)

    link = repo.get_link_by_local(sync.ENTITY_RECORD, txn["id"])
    try:
        assert result["created"] == 1
        assert len(client.post_calls) == 1
        path, body = client.post_calls[0]
        assert path == "/v1/api/records"
        assert body[0]["amount"] == -15000
        assert body[0]["accountId"] == "acc-remote-push-1"
        assert link is not None
        assert link["remote_id"] == "remote-record-created"
    finally:
        if link:
            repo.delete_link(sync.ENTITY_RECORD, txn["id"])
        _cleanup_transaction(txn["id"])
        _cleanup_wallet(wallet["id"])


def test_push_records_reports_transfer_direction_as_skipped_not_silent():
    wallet_a = repo.create_wallet("_TestWalletSyncTransferA", opening_balance=0)
    wallet_b = repo.create_wallet("_TestWalletSyncTransferB", opening_balance=0)
    txn = repo.create_transaction(
        amount=5000, direction="transfer", wallet_id=wallet_a["id"], transfer_wallet_id=wallet_b["id"],
        occurred_at="2026-08-01 10:00",
    )
    client = FakeClient()
    try:
        result = sync._push_records(client, apply=True)
        assert result["created"] == 0
        assert any(s["localId"] == txn["id"] for s in result["skipped"])
        assert client.post_calls == []
    finally:
        _cleanup_transaction(txn["id"])
        _cleanup_wallet(wallet_a["id"])
        _cleanup_wallet(wallet_b["id"])


def test_push_records_skips_when_wallet_not_yet_linked():
    wallet = repo.create_wallet("_TestWalletSyncUnlinked", opening_balance=0)
    txn = repo.create_transaction(amount=2000, direction="expense", wallet_id=wallet["id"], occurred_at="2026-08-01 10:00")
    client = FakeClient()
    try:
        result = sync._push_records(client, apply=True)
        assert result["created"] == 0
        assert any(s["localId"] == txn["id"] and "push accounts first" in s["reason"] for s in result["skipped"])
    finally:
        _cleanup_transaction(txn["id"])
        _cleanup_wallet(wallet["id"])


def test_push_records_never_pushes_a_log_only_entry():
    # A "Log spend" entry stands in for a record that already exists in
    # Wallet — pushing it would duplicate that record there.
    category = repo.create_category("_TestWalletSyncLogOnlyCat", "variable", monthly_limit=100_000)
    txn = repo.create_transaction(
        amount=8000, direction="expense", category_id=category["id"],
        occurred_at="2026-08-01 10:00", source="log_only",
    )
    client = FakeClient(post_response={"id": "should-not-be-used"})
    try:
        result = sync._push_records(client, apply=True)
        assert result["created"] == 0
        assert client.post_calls == []
        assert all(s["localId"] != txn["id"] for s in result["skipped"])
        assert repo.get_link_by_local(sync.ENTITY_RECORD, txn["id"]) is None
    finally:
        _cleanup_transaction(txn["id"])
        _cleanup_category(category["id"])
