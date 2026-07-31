from unittest.mock import patch


def test_post_reminders_with_message_uses_ai_parser(client, auth_headers):
    with patch("api.parse_reminder_with_ai", return_value=("take medicine", "2026-08-01 08:00")) as mock_parse, \
         patch("api.save_reminder", return_value="ok") as mock_save:
        resp = client.post("/api/reminders", headers=auth_headers, json={"message": "remind me to take medicine at 8am"})
    assert resp.status_code == 200
    mock_parse.assert_called_once_with("remind me to take medicine at 8am")
    mock_save.assert_called_once_with("take medicine", "2026-08-01 08:00")


def test_post_reminders_with_explicit_fields(client, auth_headers):
    with patch("api.save_reminder", return_value="ok") as mock_save:
        resp = client.post(
            "/api/reminders",
            headers=auth_headers,
            json={"content": "take medicine", "remindAt": "2026-08-01 08:00"},
        )
    assert resp.status_code == 200
    mock_save.assert_called_once_with("take medicine", "2026-08-01 08:00")


def test_post_reminders_missing_body_is_validation_error(client, auth_headers):
    resp = client.post("/api/reminders", headers=auth_headers, json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_delete_reminder_success(client, auth_headers):
    with patch("api.delete_reminder_by_id", return_value=True) as mock_delete:
        resp = client.delete("/api/reminders/7", headers=auth_headers)
    assert resp.status_code == 200
    mock_delete.assert_called_once_with(7)
    assert resp.get_json()["data"] == {"id": 7, "deleted": True}


def test_delete_reminder_not_found(client, auth_headers):
    with patch("api.delete_reminder_by_id", return_value=False):
        resp = client.delete("/api/reminders/999", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"
