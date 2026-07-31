from unittest.mock import patch


def test_get_events_passes_days_query_param(client, auth_headers):
    with patch("api.get_events_structured", return_value=[]) as mock_get:
        resp = client.get("/api/events?days=14", headers=auth_headers)
    assert resp.status_code == 200
    mock_get.assert_called_once_with(days_ahead=14)


def test_get_events_defaults_when_no_days_param(client, auth_headers):
    with patch("api.get_events_structured", return_value=[]) as mock_get:
        resp = client.get("/api/events", headers=auth_headers)
    assert resp.status_code == 200
    mock_get.assert_called_once_with()


def test_post_events_with_message_uses_ai_parser(client, auth_headers):
    parsed = {"title": "Lunch", "start": "2026-08-01 13:00", "end": "", "description": ""}
    with patch("api.parse_event_with_ai", return_value=parsed) as mock_parse, \
         patch("api.save_event", return_value="ok") as mock_save:
        resp = client.post("/api/events", headers=auth_headers, json={"message": "lunch tomorrow 1pm"})
    assert resp.status_code == 200
    mock_parse.assert_called_once_with("lunch tomorrow 1pm")
    mock_save.assert_called_once_with("Lunch", "2026-08-01 13:00", None, "")


def test_post_events_with_message_when_ai_parse_fails(client, auth_headers):
    with patch("api.parse_event_with_ai", return_value=None):
        resp = client.post("/api/events", headers=auth_headers, json={"message": "gibberish"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_post_events_with_explicit_fields(client, auth_headers):
    with patch("api.save_event", return_value="ok") as mock_save:
        resp = client.post(
            "/api/events",
            headers=auth_headers,
            json={"title": "Standup", "start": "2026-08-01 09:00", "end": "2026-08-01 09:30", "description": "daily"},
        )
    assert resp.status_code == 200
    mock_save.assert_called_once_with("Standup", "2026-08-01 09:00", "2026-08-01 09:30", "daily")


def test_post_events_missing_body_is_validation_error(client, auth_headers):
    resp = client.post("/api/events", headers=auth_headers, json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_event_not_found(client, auth_headers):
    with patch("api.edit_event_by_id", return_value=False):
        resp = client.patch("/api/events/evt123", headers=auth_headers, json={"title": "New title"})
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_patch_event_success(client, auth_headers):
    with patch("api.edit_event_by_id", return_value=True) as mock_edit:
        resp = client.patch("/api/events/evt123", headers=auth_headers, json={"title": "New title"})
    assert resp.status_code == 200
    mock_edit.assert_called_once_with("evt123", title="New title", start=None, end=None, description=None)


def test_delete_event_not_found(client, auth_headers):
    with patch("api.delete_event_by_id", return_value=False):
        resp = client.delete("/api/events/evt123", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_delete_event_success(client, auth_headers):
    with patch("api.delete_event_by_id", return_value=True):
        resp = client.delete("/api/events/evt123", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"id": "evt123", "deleted": True}
