import json

import pytest

from features.budget.errors import (
    WalletInitSyncInProgress, WalletNotConfigured, WalletRateLimited, WalletTokenExpired,
)
from features.budget.wallet.client import WalletClient, extract_items, extract_next_offset


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, headers=None, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.headers = headers or {}
        self.text = text or (json.dumps(json_body) if json_body is not None else "")
        self.content = self.text.encode() if self.text else b""

    def json(self):
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    # get() only — WalletClient has no write method to exercise.
    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({"method": "GET", "url": url, "params": params})
        return self.responses.pop(0)


def make_client(responses, **kwargs):
    session = FakeSession(responses)
    return WalletClient(token="fake-token", base_url="https://rest.example/wallet", session=session, **kwargs), session


def test_not_configured_without_token():
    client = WalletClient(token="", session=FakeSession([]))
    with pytest.raises(WalletNotConfigured):
        client.get("/v1/api/accounts")


def test_get_returns_json_body():
    client, session = make_client([FakeResponse(200, {"data": [{"id": "1"}]})])
    body = client.get("/v1/api/accounts")
    assert body == {"data": [{"id": "1"}]}
    assert session.calls[0]["method"] == "GET"


def test_401_raises_token_expired():
    client, _ = make_client([FakeResponse(401)])
    with pytest.raises(WalletTokenExpired):
        client.get("/v1/api/accounts")


def test_409_init_sync_raises_specific_error():
    body = {"error": "init_sync_in_progress", "message": "still syncing", "retry_after_minutes": 5}
    client, _ = make_client([FakeResponse(409, body)])
    with pytest.raises(WalletInitSyncInProgress):
        client.get("/v1/api/accounts")


def test_429_raises_rate_limited():
    client, _ = make_client([FakeResponse(429)])
    with pytest.raises(WalletRateLimited):
        client.get("/v1/api/accounts")


def test_rate_limit_headers_are_recorded():
    headers = {"X-RateLimit-Limit": "500", "X-RateLimit-Remaining": "487"}
    client, _ = make_client([FakeResponse(200, {"data": []}, headers=headers)])
    client.get("/v1/api/accounts")
    assert client.rate_limit_limit == 500
    assert client.rate_limit_remaining == 487


def test_reserve_threshold_blocks_before_making_the_call():
    client, session = make_client([], rate_limit_reserve=10)
    client.rate_limit_remaining = 5
    with pytest.raises(WalletRateLimited):
        client.get("/v1/api/accounts")
    assert session.calls == []  # never actually sent


def test_paginate_follows_next_offset():
    page1 = FakeResponse(200, {"data": [{"id": "a"}, {"id": "b"}], "nextOffset": 2})
    page2 = FakeResponse(200, {"data": [{"id": "c"}], "meta": {}})
    client, session = make_client([page1, page2])
    items = list(client.paginate("/v1/api/accounts", page_size=2))
    assert [i["id"] for i in items] == ["a", "b", "c"]
    assert session.calls[0]["params"]["offset"] == 0
    assert session.calls[1]["params"]["offset"] == 2


def test_paginate_stops_when_page_is_empty():
    client, session = make_client([FakeResponse(200, {"data": []})])
    items = list(client.paginate("/v1/api/accounts"))
    assert items == []
    assert len(session.calls) == 1


def test_extract_items_handles_bare_list_and_data_and_items_keys():
    assert extract_items([{"id": 1}]) == [{"id": 1}]
    assert extract_items({"data": [{"id": 1}]}) == [{"id": 1}]
    assert extract_items({"items": [{"id": 1}]}) == [{"id": 1}]
    assert extract_items({"nothing": True}) == []


def test_extract_items_reads_the_named_resource_key_for_every_confirmed_endpoint():
    assert extract_items({"accounts": [{"id": "a1"}], "limit": 5, "nextOffset": 5, "offset": 0}) == [{"id": "a1"}]
    assert extract_items({"categories": [{"id": "c1"}], "limit": 5, "offset": 0}) == [{"id": "c1"}]
    assert extract_items({"labels": [{"id": "l1"}], "limit": 1, "offset": 0}) == [{"id": "l1"}]
    assert extract_items({"goals": [{"id": "g1"}], "limit": 5, "nextOffset": None, "offset": 0}) == [{"id": "g1"}]
    assert extract_items({"limit": 5, "nextOffset": 5, "offset": 0, "standingOrders": [{"id": "s1"}]}) == [{"id": "s1"}]


def test_extract_items_records_ignores_appliedRecordDateFilters_even_though_it_sorts_first():
    # Real shape (confirmed 2026-08-12): appliedRecordDateFilters is itself
    # a list (of date-filter strings) and comes before "records" in the
    # response's key order — a naive "first list-valued field wins" scan
    # picks it instead of the actual record objects, which is exactly the
    # regression this test guards against (it shipped once already and
    # crashed sync.py's record["id"] on a plain string).
    body = {
        "appliedRecordDateFilters": ["gte.2026-05-12T00:47:51.072Z", "lt.2026-08-13T00:47:51.072Z"],
        "limit": 3, "nextOffset": 3, "offset": 0,
        "records": [{"id": "rec-1"}, {"id": "rec-2"}],
    }
    assert extract_items(body) == [{"id": "rec-1"}, {"id": "rec-2"}]


def test_extract_items_unknown_shape_prefers_a_list_of_objects_over_a_list_of_scalars():
    assert extract_items({"warnings": ["a", "b"], "widgets": [{"id": "w1"}]}) == [{"id": "w1"}]


def test_extract_next_offset_handles_top_level_and_nested_meta():
    assert extract_next_offset({"nextOffset": 30}) == 30
    assert extract_next_offset({"meta": {"nextOffset": 30}}) == 30
    assert extract_next_offset({"meta": {}}) is None
    assert extract_next_offset([1, 2, 3]) is None


