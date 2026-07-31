from unittest.mock import patch


def test_post_notes_creates(client, auth_headers):
    with patch("api.save_note", return_value="saved") as mock_save:
        resp = client.post("/api/notes", headers=auth_headers, json={"message": "buy milk"})
    assert resp.status_code == 200
    mock_save.assert_called_once_with("buy milk")


def test_post_notes_missing_message_is_validation_error(client, auth_headers):
    resp = client.post("/api/notes", headers=auth_headers, json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_notes_edits_by_index(client, auth_headers):
    with patch("api.edit_note", return_value="updated") as mock_edit:
        resp = client.patch("/api/notes/3", headers=auth_headers, json={"message": "buy oat milk"})
    assert resp.status_code == 200
    mock_edit.assert_called_once_with("buy oat milk", index=3)


def test_patch_notes_missing_message_is_validation_error(client, auth_headers):
    resp = client.patch("/api/notes/3", headers=auth_headers, json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_delete_notes_by_index(client, auth_headers):
    with patch("api.delete_note", return_value="🗑️ Note deleted: _buy milk_") as mock_delete:
        resp = client.delete("/api/notes/3", headers=auth_headers)
    assert resp.status_code == 200
    mock_delete.assert_called_once_with(index=3)
    assert resp.get_json()["data"] == {"index": 3, "deleted": True}


def test_delete_notes_not_found(client, auth_headers):
    with patch("api.delete_note", return_value="❌ Note not found. Use *get notes* to see your list, then refer by number or keyword."):
        resp = client.delete("/api/notes/99", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"
