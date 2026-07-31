from unittest.mock import patch


def test_get_news_list(client, auth_headers):
    articles = [{"title": "A", "source": "BBC", "publishedAt": "2026-08-01", "url": "http://x", "description": "d"}]
    with patch("api.get_news_structured", return_value=articles) as mock_get:
        resp = client.get("/api/news?topic=technology", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["data"] == articles
    mock_get.assert_called_once_with("technology")


def test_get_news_list_missing_topic_is_validation_error(client, auth_headers):
    resp = client.get("/api/news", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_news_article_summary(client, auth_headers):
    with patch("api.summarize_article", return_value="📰 *A*\nsummary...") as mock_summarize:
        resp = client.get(
            "/api/news/article",
            headers=auth_headers,
            query_string={"url": "http://x", "title": "A", "source": "BBC", "publishedAt": "2026-08-01"},
        )
    assert resp.status_code == 200
    mock_summarize.assert_called_once_with("A", "http://x", "BBC", "2026-08-01", "")


def test_get_news_article_missing_required_params(client, auth_headers):
    resp = client.get("/api/news/article", headers=auth_headers, query_string={"url": "http://x"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
