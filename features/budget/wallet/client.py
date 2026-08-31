"""Thin HTTP transport over the Wallet by BudgetBakers REST API
(https://rest.budgetbakers.com/wallet — see docs/BUDGETBAKERS_API.md).

No sync logic here — this only knows how to make one HTTP call correctly:
auth header, pagination, rate-limit tracking, and mapping the vendor's
error shapes (401 / 409 init-sync / 429 / 207 partial-success) onto the
typed errors in features/budget/errors.py. features/budget/wallet/sync.py
is the only caller.

The BETA API's exact list-response envelope wasn't fully confirmed against
the live spec (a `nextOffset`-bearing PaginatedResponse object exists, but
whether it sits at the top level or nested under a `meta` key wasn't
pinned down) — extract_items()/extract_next_offset() below handle both
shapes defensively rather than assuming one. Batch write endpoints
(POST/PATCH /records, PATCH /accounts|categories|labels|budgets) are
assumed to take a raw JSON array as the body — verify with
POST /sync/wallet/preview against a couple of real records before trusting
a full push."""
import logging
import time

import requests

import config
from features.budget.errors import (
    WalletInitSyncInProgress, WalletNotConfigured, WalletRateLimited,
    WalletRequestError, WalletTokenExpired,
)

# Root logger (logging_setup.py) carries a bot_all.log handler at INFO, so
# this shows up there with no extra wiring — every call this process makes
# to the external Wallet API, gone before, is now one grep away instead of
# needing a live PowerShell probe to reconstruct what the vendor actually
# sent back.
logger = logging.getLogger(__name__)

_TIMEOUT = 20
_DEFAULT_RATE_LIMIT_RESERVE = 10  # stop before actually hitting 429, not after


_RESOURCE_LIST_KEYS = ("accounts", "categories", "labels", "records", "goals", "standingOrders", "budgets")


def extract_items(body):
    """The live BETA API wraps each endpoint's page under a resource-specific
    key instead of a generic envelope — confirmed against the real API
    2026-08-12: GET /accounts -> {"accounts": [...]}, /categories ->
    {"categories": [...]}, /records -> {"records": [...], ...}, /goals ->
    {"goals": [...]}, /standing-orders -> {"standingOrders": [...]}
    ("budgets" is inferred from the same naming pattern, not directly
    confirmed). These are looked up by name, NOT by "first list-valued
    field" — that heuristic previously shipped and broke on /records:
    its "..." is appliedRecordDateFilters, itself a list of date-filter
    strings that sorts ahead of "records" in the real response's key
    order, so the old first-list-wins scan grabbed two date strings and
    handed them to sync.py as if they were record objects
    (TypeError: string indices must be integers, not 'str' the moment it
    tried record["id"]). data/items are kept as a same-priority
    alternative in case some other endpoint uses a generic envelope
    instead. Only truly unknown shapes fall through to the old heuristic,
    now guarded to prefer a list of objects over a list of scalars."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        if isinstance(body.get("data"), list):
            return body["data"]
        if isinstance(body.get("items"), list):
            return body["items"]
        for key in _RESOURCE_LIST_KEYS:
            value = body.get(key)
            if isinstance(value, list):
                return value
        for value in body.values():
            if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                return value
    return []


def extract_next_offset(body):
    if not isinstance(body, dict):
        return None
    if "nextOffset" in body:
        return body["nextOffset"]
    meta = body.get("meta")
    if isinstance(meta, dict):
        return meta.get("nextOffset")
    return None


def _as_dict_with_id(value):
    return value.get("id") if isinstance(value, dict) and "id" in value else None


def extract_created_id(body):
    """Pulls the new entity's id out of a create response, whichever of
    the plausible BETA-API envelopes it turns out to be: a 207
    partial-success body ({"results": [{"success": true, "data": {...}}]}),
    a bare created object ({"id": ...} or {"data": {"id": ...}}), or that
    object wrapped in a single-element list. Returns None (never raises)
    when nothing recognizable is found — callers treat that as
    'record the failure, don't link'. See this module's docstring: the
    exact create-response shape wasn't confirmed against the live spec."""
    if isinstance(body, dict):
        results = body.get("results")
        if isinstance(results, list) and results and results[0].get("success"):
            item = results[0]
            return _as_dict_with_id(item.get("data")) or _as_dict_with_id(item)
        return _as_dict_with_id(body) or _as_dict_with_id(body.get("data"))
    if isinstance(body, list) and body:
        return _as_dict_with_id(body[0])
    return None


class WalletClient:
    def __init__(self, token=None, base_url=None, session=None, rate_limit_reserve=_DEFAULT_RATE_LIMIT_RESERVE):
        self.token = token if token is not None else config.WALLET_API_TOKEN
        self.base_url = base_url or config.WALLET_API_BASE_URL
        self.session = session or requests.Session()
        self.rate_limit_reserve = rate_limit_reserve

        # Populated from response headers after each call — read by
        # sync.py's status endpoint and by the reserve check below.
        self.rate_limit_limit = None
        self.rate_limit_remaining = None
        self.last_data_change_at = None
        self.last_data_change_rev = None
        self.sync_in_progress = None

    def configured(self) -> bool:
        return bool(self.token)

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def _record_headers(self, resp):
        limit = resp.headers.get("X-RateLimit-Limit")
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if limit is not None:
            self.rate_limit_limit = int(limit)
        if remaining is not None:
            self.rate_limit_remaining = int(remaining)
        self.last_data_change_at = resp.headers.get("X-Last-Data-Change-At", self.last_data_change_at)
        self.last_data_change_rev = resp.headers.get("X-Last-Data-Change-Rev", self.last_data_change_rev)
        sync_flag = resp.headers.get("X-Sync-In-Progress")
        if sync_flag is not None:
            self.sync_in_progress = sync_flag.lower() == "true"

    def _request(self, method, path, params=None, json_body=None):
        if not self.configured():
            raise WalletNotConfigured(
                "WALLET_API_TOKEN is not set — mint a token in the Wallet web app "
                "(Settings -> REST API) and add it to environtment.env."
            )
        # Checked before every call, not just on a 429 response, so a run
        # stops with clean partial progress instead of burning its last
        # few requests on calls that would just 429 anyway.
        if self.rate_limit_remaining is not None and self.rate_limit_remaining <= self.rate_limit_reserve:
            raise WalletRateLimited(
                f"Only {self.rate_limit_remaining} Wallet API requests left this hour "
                f"(reserve is {self.rate_limit_reserve}) — stopping before the run hits 429."
            )

        started = time.monotonic()
        try:
            resp = self.session.request(
                method, self.base_url + path, headers=self._headers(),
                params=params, json=json_body, timeout=_TIMEOUT,
            )
        except requests.RequestException as e:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            logger.warning(f"{method} {path} — network error after {elapsed_ms}ms: {e}")
            raise WalletRequestError(f"Network error calling Wallet API: {e}")

        elapsed_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code < 400:
            logger.info(f"{method} {path} params={params} -> {resp.status_code} ({elapsed_ms}ms)")
        else:
            logger.warning(f"{method} {path} params={params} -> {resp.status_code} ({elapsed_ms}ms) body={_safe_json(resp)}")

        self._record_headers(resp)

        if resp.status_code == 401:
            raise WalletTokenExpired(
                "Wallet API token was rejected (missing, invalid, or past its 90-day expiry). "
                "Mint a new one in the Wallet web app and update environtment.env."
            )
        if resp.status_code == 409:
            body = _safe_json(resp)
            if isinstance(body, dict) and body.get("error") == "init_sync_in_progress":
                raise WalletInitSyncInProgress(
                    body.get("message", "Wallet's initial data sync is still running.")
                    + f" Retry in ~{body.get('retry_after_minutes', 5)} minute(s)."
                )
            raise WalletRequestError(f"{method} {path} -> 409: {body}")
        if resp.status_code == 429:
            raise WalletRateLimited("Wallet API returned 429 Too Many Requests.")
        if resp.status_code in (200, 207):
            return _safe_json(resp)
        if resp.status_code in (201, 204):
            return _safe_json(resp) or {}

        raise WalletRequestError(f"{method} {path} -> {resp.status_code}: {_safe_json(resp)}")

    # ------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------
    def get(self, path, **params):
        params = {k: v for k, v in params.items() if v is not None}
        return self._request("GET", path, params=params)

    def paginate(self, path, page_size=200, **params):
        """Yields items one at a time across every page. page_size caps at
        the API's documented max (200); callers that want incremental sync
        pass updatedAt=gte.<cursor> in **params."""
        for items, _next_offset in self.paginate_pages(path, page_size=page_size, **params):
            for item in items:
                yield item

    def paginate_pages(self, path, page_size=200, start_offset=0, **params):
        """Like paginate() but yields one whole page at a time as
        (items, next_offset), where next_offset is None on the last page.

        A caller persisting resume state needs the page boundary AND the
        offset: a large first backfill (the API caps a user at 20,000
        records) can't finish inside the mobile client's 20s abort or
        gunicorn's --timeout, and the result order isn't sorted by
        updatedAt, so resume has to be by offset — pass the persisted
        next_offset back as start_offset to pick up where the last run
        stopped."""
        offset = start_offset or 0
        limit = min(page_size, 200)
        while True:
            body = self.get(path, limit=limit, offset=offset, **params)
            items = extract_items(body)
            next_offset = extract_next_offset(body)
            if not items:
                next_offset = None
            yield items, next_offset
            if next_offset is None:
                return
            offset = next_offset

    # ------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------
    def post(self, path, body):
        return self._request("POST", path, json_body=body)

    def patch(self, path, body):
        return self._request("PATCH", path, json_body=body)

    def delete_batch(self, entity_type, ids):
        """DELETE /v1/api/{type} with a body of {"ids": [...]}, per
        docs/BUDGETBAKERS_API.md's 'Deleting Entities' section."""
        return self._request("DELETE", f"/v1/api/{entity_type}", json_body={"ids": list(ids)})

    def references(self, entity_type, ids):
        ids = list(ids)[:10]
        return self.get(f"/v1/api/{entity_type}/references", id=",".join(ids))


def _safe_json(resp):
    if not resp.content:
        return None
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text[:500]}
