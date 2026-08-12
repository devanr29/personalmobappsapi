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


def test_breakdown_carries_wallets_and_computed_at_and_unread_count(client, auth_headers):
    # These three fields let the mobile Budget screen build its whole view
    # from ONE request instead of four (GET /breakdown used to be joined
    # by separate GET /api/budget, /wallets, /alerts calls).
    from features.budget import repo

    wallet = repo.create_wallet("_TestBreakdownWallet", opening_balance=500_000)
    try:
        resp = client.get("/api/budget/breakdown", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.get_json()["data"]
        assert "computedAt" in body and body["computedAt"]
        assert isinstance(body["unreadAlertCount"], int)
        match = next(w for w in body["wallets"] if w["id"] == wallet["id"])
        assert match["name"] == "_TestBreakdownWallet"
        assert match["balance"] == 500_000
    finally:
        repo.delete_wallet(wallet["id"])
