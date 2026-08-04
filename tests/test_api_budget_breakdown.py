"""GET /api/budget/breakdown is now served by the features/budget blueprint
and derived live from the ledger (features/budget/service.py), not by
reading a stale bot_state blob — so there's nothing left to mock here.
Full CRUD-level coverage of the underlying computation lives in
tests/test_budget_service.py, which isolates its own throwaway DB."""


def test_breakdown_returns_null_when_no_wallets_configured(client, auth_headers):
    # True of any environment that hasn't run the one-time Sheets seed
    # (features/budget/seed.py, Phase 1 B1.5) yet — mirrors the legacy
    # "never computed" null state.
    resp = client.get("/api/budget/breakdown", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] is None


def test_summary_returns_null_when_no_wallets_configured(client, auth_headers):
    resp = client.get("/api/budget", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] is None
