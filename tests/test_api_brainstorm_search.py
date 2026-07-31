from unittest.mock import patch


def test_post_brainstorm(client, auth_headers):
    with patch("api.ai_brainstorm", return_value="🧠 *Brainstorm: widget*\n\nidea 1") as mock_brainstorm:
        resp = client.post("/api/brainstorm", headers=auth_headers, json={"topic": "widget"})
    assert resp.status_code == 200
    mock_brainstorm.assert_called_once_with("widget")
    assert resp.get_json()["data"] == {"text": "🧠 *Brainstorm: widget*\n\nidea 1"}


def test_post_brainstorm_missing_topic_is_validation_error(client, auth_headers):
    resp = client.post("/api/brainstorm", headers=auth_headers, json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_search(client, auth_headers):
    results = [{"source_type": "note", "content": "buy milk", "score": 0.8}]
    with patch("api.semantic_search", return_value=results) as mock_search:
        resp = client.get("/api/search?q=milk", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] == results
    mock_search.assert_called_once_with("milk")


def test_get_search_missing_query_is_validation_error(client, auth_headers):
    resp = client.get("/api/search", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
