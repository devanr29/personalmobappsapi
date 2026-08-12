"""google_auth.get_google_services() caches its result in a module-level
global. GET /api/home now calls it from multiple concurrent worker threads
(features/api.py's ThreadPoolExecutor) — these tests guard the lock added
to keep the first, cold-cache call from racing (see google_auth.py's
_google_services_lock)."""
import threading
import time

import pytest

import google_auth


@pytest.fixture(autouse=True)
def _reset_cache():
    google_auth._google_services_cache = None
    yield
    google_auth._google_services_cache = None


def test_concurrent_calls_build_exactly_once(monkeypatch):
    call_count = []

    def fake_build():
        call_count.append(1)
        time.sleep(0.05)  # simulate a slow token refresh / build() call
        google_auth._google_services_cache = ("calendar", "sheets", "tasks")
        return google_auth._google_services_cache

    monkeypatch.setattr(google_auth, "_build_google_services", fake_build)

    results = []
    def worker():
        results.append(google_auth.get_google_services())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(call_count) == 1
    assert all(r == ("calendar", "sheets", "tasks") for r in results)


def test_second_call_uses_cache_without_rebuilding(monkeypatch):
    call_count = []

    def fake_build():
        call_count.append(1)
        google_auth._google_services_cache = ("calendar", "sheets", "tasks")
        return google_auth._google_services_cache

    monkeypatch.setattr(google_auth, "_build_google_services", fake_build)

    first = google_auth.get_google_services()
    second = google_auth.get_google_services()

    assert first == second
    assert len(call_count) == 1
