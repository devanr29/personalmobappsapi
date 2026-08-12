import time
from unittest.mock import patch


def test_home_returns_composed_shape(client, auth_headers):
    events = [{"id": "e1", "title": "Standup", "start": "2026-08-01 09:00", "allDay": False}]
    with patch("api.get_events_structured", return_value=events), \
         patch("api.get_tasks_structured", return_value=[{"id": "t1", "title": "Buy milk", "status": "needsAction"}]), \
         patch("api.get_budget_summary", return_value=None), \
         patch("api.get_reminders_structured", return_value=[]) as mock_reminders, \
         patch("api.get_quote_of_day", return_value={"quote": "q", "author": "a"}):
        resp = client.get("/api/home", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["nextEvent"] == events[0]
    assert body["tasks"] == [{"id": "t1", "title": "Buy milk", "status": "needsAction"}]
    assert body["budgetSummary"] is None
    assert body["reminders"] == []
    assert body["quoteOfDay"] == {"quote": "q", "author": "a"}
    mock_reminders.assert_called_once_with(limit=2)


def test_home_returns_null_next_event_when_no_events(client, auth_headers):
    with patch("api.get_events_structured", return_value=[]), \
         patch("api.get_tasks_structured", return_value=[]), \
         patch("api.get_budget_summary", return_value=None), \
         patch("api.get_reminders_structured", return_value=[]), \
         patch("api.get_quote_of_day", return_value={"quote": "", "author": ""}):
        resp = client.get("/api/home", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.get_json()["data"]["nextEvent"] is None


def test_home_sources_run_concurrently_not_sequentially(client, auth_headers):
    # Each source sleeps 200ms. Run sequentially that's >=1000ms; run
    # concurrently (the fix) it's close to 200ms. 700ms is a wide margin
    # that only a real parallelism regression would cross.
    def slow(*args, **kwargs):
        time.sleep(0.2)
        return None

    def slow_list(*args, **kwargs):
        time.sleep(0.2)
        return []

    def slow_quote(*args, **kwargs):
        time.sleep(0.2)
        return {"quote": "", "author": ""}

    with patch("api.get_events_structured", side_effect=slow_list), \
         patch("api.get_tasks_structured", side_effect=slow_list), \
         patch("api.get_budget_summary", side_effect=slow), \
         patch("api.get_reminders_structured", side_effect=slow_list), \
         patch("api.get_quote_of_day", side_effect=slow_quote):
        start = time.monotonic()
        resp = client.get("/api/home", headers=auth_headers)
        elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 0.7, f"expected concurrent execution (~0.2s), took {elapsed:.2f}s — looks sequential"
