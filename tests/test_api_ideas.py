from unittest.mock import patch


def test_post_ideas_creates(client, auth_headers):
    with patch("api.save_idea", return_value="saved") as mock_save:
        resp = client.post("/api/ideas", headers=auth_headers, json={"message": "build a widget"})
    assert resp.status_code == 200
    mock_save.assert_called_once_with("build a widget")


def test_post_ideas_missing_message_is_validation_error(client, auth_headers):
    resp = client.post("/api/ideas", headers=auth_headers, json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_ideas_edits_by_index(client, auth_headers):
    with patch("api.edit_idea", return_value="updated") as mock_edit:
        resp = client.patch("/api/ideas/2", headers=auth_headers, json={"message": "build a better widget"})
    assert resp.status_code == 200
    mock_edit.assert_called_once_with("build a better widget", index=2)


def test_patch_ideas_missing_message_is_validation_error(client, auth_headers):
    resp = client.patch("/api/ideas/2", headers=auth_headers, json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_delete_ideas_by_index(client, auth_headers):
    with patch("api.delete_idea", return_value="🗑️ Idea deleted: _build a widget_") as mock_delete:
        resp = client.delete("/api/ideas/2", headers=auth_headers)
    assert resp.status_code == 200
    mock_delete.assert_called_once_with(index=2)
    assert resp.get_json()["data"] == {"index": 2, "deleted": True}


def test_delete_ideas_not_found(client, auth_headers):
    with patch("api.delete_idea", return_value="❌ Idea not found. Use *get ideas* to see your list."):
        resp = client.delete("/api/ideas/99", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"
