def test_health_requires_no_auth(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["status"] == "ok"


def test_protected_route_rejects_missing_token(client):
    resp = client.get("/api/tasks")
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_protected_route_accepts_valid_token(client, auth_headers):
    resp = client.get("/api/notes", headers=auth_headers)
    assert resp.status_code == 200
