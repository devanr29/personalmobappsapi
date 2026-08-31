"""Blueprint-level tests for /api/budget/sync/wallet/* — mirrors
test_budget_blueprint.py's conventions (client/auth_headers fixtures from
conftest.py). WalletClient is monkeypatched inside sync.py so these never
make a real network call."""
from features.budget.wallet import sync


class FakeClient:
    def __init__(self, configured=True):
        self._configured = configured
        self.token = "fake-token-for-status-test"

    def configured(self):
        return self._configured

    def get(self, path, **params):
        return {"data": []}

    def paginate(self, path, **params):
        return []

    def paginate_pages(self, path, start_offset=0, **params):
        return [([], None)]

    def post(self, path, body):
        return {}

    def patch(self, path, body):
        return {}


def test_sync_status_requires_auth(client):
    resp = client.get("/api/budget/sync/wallet/status")
    assert resp.status_code == 401


def test_sync_status_reports_not_configured_when_token_missing(client, auth_headers, monkeypatch):
    monkeypatch.setattr(sync, "WalletClient", lambda: FakeClient(configured=False))
    resp = client.get("/api/budget/sync/wallet/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["configured"] is False
    assert body["rateLimitRemaining"] is None


def test_sync_preview_returns_pull_and_push_summaries(client, auth_headers, monkeypatch):
    monkeypatch.setattr(sync, "WalletClient", lambda: FakeClient(configured=True))
    resp = client.post("/api/budget/sync/wallet/preview", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert "pull" in body and "push" in body
    assert set(body["pull"].keys()) == {"accounts", "categories", "labels", "goals", "bills", "records"}
    assert set(body["push"].keys()) == {"wallets", "categories", "labels", "records"}


def test_sync_pull_route_returns_summary_and_free_money(client, auth_headers, monkeypatch):
    monkeypatch.setattr(sync, "WalletClient", lambda: FakeClient(configured=True))
    resp = client.post("/api/budget/sync/wallet/pull", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert "pull" in body
    assert "summary" in body


def test_sync_push_route(client, auth_headers, monkeypatch):
    monkeypatch.setattr(sync, "WalletClient", lambda: FakeClient(configured=True))
    resp = client.post("/api/budget/sync/wallet/push", headers=auth_headers)
    assert resp.status_code == 200
    assert "push" in resp.get_json()["data"]


def test_sync_combined_route_runs_pull_then_push(client, auth_headers, monkeypatch):
    monkeypatch.setattr(sync, "WalletClient", lambda: FakeClient(configured=True))
    resp = client.post("/api/budget/sync/wallet", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert "pull" in body and "push" in body and "summary" in body


def test_sync_pull_route_maps_not_configured_to_503(client, auth_headers, monkeypatch):
    monkeypatch.setattr(sync, "WalletClient", lambda: FakeClient(configured=False))
    resp = client.post("/api/budget/sync/wallet/pull", headers=auth_headers)
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["error"]["code"] == "WALLET_NOT_CONFIGURED"


def test_sync_compare_route(client, auth_headers, monkeypatch):
    monkeypatch.setattr(sync, "WalletClient", lambda: FakeClient(configured=True))
    resp = client.get("/api/budget/sync/wallet/compare", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert "walletBudgets" in body
    assert "note" in body
