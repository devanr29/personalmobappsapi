from features.budget.blueprint import _handle_budget_error
from features.budget.errors import BudgetNotFound


def test_ping_requires_auth(client):
    resp = client.get("/api/budget/ping")
    assert resp.status_code == 401


def test_ping_ok_when_authed(client, auth_headers):
    resp = client.get("/api/budget/ping", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["data"] == {"pong": True}


def test_budget_error_maps_to_envelope(app):
    # Exercises the real errorhandler function registered on budget_bp,
    # without needing a throwaway route on the shared blueprint singleton.
    with app.test_request_context():
        resp, status = _handle_budget_error(BudgetNotFound("no such thing"))
        assert status == 404
        body = resp.get_json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "no such thing"


def test_summary_get_and_ping_coexist_on_the_same_blueprint(client, auth_headers):
    # GET /api/budget (the live summary) and GET /api/budget/ping both
    # live on budget_bp; api_bp separately still owns POST /api/budget
    # (the legacy whole-state NL parser, removed in Phase 2) on the exact
    # same path — confirms Werkzeug routes disjoint methods on one path
    # to different blueprints without collision.
    resp = client.get("/api/budget", headers=auth_headers)
    assert resp.status_code == 200
    resp = client.get("/api/budget/ping", headers=auth_headers)
    assert resp.status_code == 200


def test_wallets_list_includes_live_balance(client, auth_headers):
    from features.budget import repo

    wallet = repo.create_wallet("_TestWalletsList", opening_balance=250_000)
    try:
        resp = client.get("/api/budget/wallets", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.get_json()["data"]["items"]
        match = next(w for w in items if w["id"] == wallet["id"])
        assert match["name"] == "_TestWalletsList"
        assert match["balance"] == 250_000
    finally:
        repo.delete_wallet(wallet["id"])


def test_categories_list_filters_by_kind(client, auth_headers):
    from features.budget import repo

    category = repo.create_category("_TestCategoriesList", "variable", monthly_limit=100_000)
    try:
        resp = client.get("/api/budget/categories?kind=variable", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.get_json()["data"]["items"]
        assert any(c["id"] == category["id"] for c in items)

        resp = client.get("/api/budget/categories?kind=fixed", headers=auth_headers)
        items = resp.get_json()["data"]["items"]
        assert not any(c["id"] == category["id"] for c in items)
    finally:
        repo.delete_category(category["id"])
