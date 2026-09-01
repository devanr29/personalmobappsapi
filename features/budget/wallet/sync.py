"""Pulls money data from Wallet by BudgetBakers into the local budget
ledger. client.py is the HTTP transport, mapping.py is the pure field
conversion; this module is the only place that combines them with repo.py
reads/writes. features/budget/blueprint.py's /sync/wallet/* routes are the
only callers - manual-trigger only, no scheduler job (see docs/BUDGETBAKERS_API.md).

ONE-DIRECTIONAL BY DESIGN. Wallet is where expenses are tracked, so this
app never writes back. There is no push, and client.py deliberately has no
post/patch/delete method to write with - every request this module makes is
a GET. (Removed 2026-08-31; `git log -- features/budget/wallet/` has the
two-way version if it is ever wanted back.)

Pull scope is narrow on purpose - accounts and records only, i.e. *money
status*: what each account holds and what moved through it. Category
NAMES are also pulled, but only into a read-only display cache — see
below, this is not the category pull that was removed.

    accounts        -> budget_wallets                 pulled
    records         -> budget_transactions             pulled
    category names  -> budget_wallet_category_names    pulled (cache only)
    categories (as budget structure) / labels / goals / standing-orders   NOT pulled

Wallet's categories are not pulled as budget structure — the budget itself
(budget_categories rows with a monthly_limit, budget_bills, budget_goals)
is configured by hand in the app instead. Pulling the full category
taxonomy in as budget_categories rows produced ~85 inert categories that
contributed nothing to the budget math, and re-created bills and goals
that had been deliberately deleted; labels/goals/standing-orders were
removed for the same reason.

What IS pulled now (added after that removal): a flat id->name cache,
budget_wallet_category_names, refreshed from Wallet's full category list
on every non-backfill-resume pull. It cannot affect budget math — it has
no monthly_limit/kind/bills/rollover, and nothing joins on it except a
transaction list's display label (features/budget/repo.py's
_TXN_LIST_SQL). Records still resolve category_id through the category
links earlier pulls left behind (budget_wallet_links entity_type=
'category'), so a record whose Wallet category is already linked still
arrives pre-filed with a real local category_id. One under an unlinked
category still gets category_id = NULL as before (filed by hand, or via
"Attach an existing transaction") but now also carries its raw Wallet
category id (wallet_category_remote_id), so the transaction list can show
the real Wallet category name instead of blank — a label only, never a
filed category.

CONFLICT POLICY: Wallet wins on money. occurred_at, amount, direction,
wallet_id and note are overwritten from Wallet on every pull. Wallet never
wins on category_id or bill_id - those are local budget decisions (made in
the app, e.g. "Attach an existing transaction") and a pull must not undo
them. There is no "local edit not yet pushed" skip, because there is no
push: money data is never frozen out of a sync.
"""
import base64
import datetime
import json
import time

import config
from database import state_get, state_set
from db import db_conn
from features.budget import repo
from features.budget.errors import WalletNotConfigured
from features.budget.periods import period_bounds
from features.budget.wallet import mapping
from features.budget.wallet.client import WalletClient

ENTITY_ACCOUNT = "account"
ENTITY_CATEGORY = "category"
ENTITY_LABEL = "label"
ENTITY_GOAL = "goal"
ENTITY_STANDING_ORDER = "standing_order"
ENTITY_RECORD = "record"

_CURSOR_STATE_KEY = "wallet_sync_cursors"
_LAST_RUN_STATE_KEY = "wallet_sync_last_run"


# ================================================================
# CURSORS — one watermark per entity type, stored as a single JSON blob
# in bot_state (same KV table service.py uses for payroll_day etc). Only
# advanced past a page once every row on it has been successfully
# upserted, so a run that dies partway through resumes from the last
# fully-applied page next time rather than skipping the failed one.
# ================================================================
def _get_cursors() -> dict:
    raw = state_get(_CURSOR_STATE_KEY)
    return json.loads(raw) if raw else {}


def _set_cursor(entity_type, value):
    if not value:
        return
    cursors = _get_cursors()
    if cursors.get(entity_type) and cursors[entity_type] >= value:
        return
    cursors[entity_type] = value
    state_set(_CURSOR_STATE_KEY, json.dumps(cursors))


# The records backfill can't finish in one bounded request, and the API's
# result order isn't sorted by updatedAt (docs/BUDGETBAKERS_API.md), so a
# mid-backfill resume can't use the updatedAt watermark — it walks by
# offset instead, carrying the running max updatedAt alongside so the real
# watermark can be set correctly once the whole history has drained. Both
# live in the same cursors blob and are dropped on completion.
_RECORD_OFFSET_KEY = "record_offset"
_RECORD_RUNNING_MAX_KEY = "record_running_max"


def _get_record_progress():
    """(offset, running_max_updated_at) for an in-flight records backfill."""
    cursors = _get_cursors()
    return int(cursors.get(_RECORD_OFFSET_KEY) or 0), cursors.get(_RECORD_RUNNING_MAX_KEY)


def _set_record_progress(offset, running_max):
    cursors = _get_cursors()
    if offset:
        cursors[_RECORD_OFFSET_KEY] = int(offset)
        if running_max:
            cursors[_RECORD_RUNNING_MAX_KEY] = running_max
    else:
        cursors.pop(_RECORD_OFFSET_KEY, None)
        cursors.pop(_RECORD_RUNNING_MAX_KEY, None)
    state_set(_CURSOR_STATE_KEY, json.dumps(cursors))


def _empty_pull_result() -> dict:
    """The zero-work per-entity shape every _pull_X() returns — used to
    stand in for an entity pull that's deliberately skipped this round."""
    return {"created": 0, "updated": 0, "skipped": []}


def _record_run(summary: dict):
    state_set(_LAST_RUN_STATE_KEY, json.dumps({
        "at": str(config.now_jkt()), "summary": summary,
    }))


def _decode_token_expiry(token: str):
    """Reads the JWT's exp claim without verifying the signature — this is
    purely so /sync/wallet/status can warn 'token expires soon' before it
    actually fails with a 401 (tokens are 90-day, minted in the Wallet web
    app; there's no refresh endpoint)."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        return datetime.datetime.fromtimestamp(claims["exp"], tz=datetime.timezone.utc)
    except Exception:
        return None


# ================================================================
# STATUS
# ================================================================
def get_status() -> dict:
    client = WalletClient()
    out = {
        "configured": client.configured(),
        "cursors": _get_cursors(),
        "lastRun": None,
        "tokenExpiresAt": None,
        "rateLimitLimit": None,
        "rateLimitRemaining": None,
        "linkCounts": {
            t: len(repo.list_links(t))
            for t in (ENTITY_ACCOUNT, ENTITY_CATEGORY, ENTITY_LABEL, ENTITY_GOAL, ENTITY_STANDING_ORDER, ENTITY_RECORD)
        },
        "error": None,
    }
    raw_last_run = state_get(_LAST_RUN_STATE_KEY)
    if raw_last_run:
        out["lastRun"] = json.loads(raw_last_run)
    if not client.configured():
        return out
    out["tokenExpiresAt"] = _decode_token_expiry(client.token)
    out["tokenExpiresAt"] = out["tokenExpiresAt"].isoformat() if out["tokenExpiresAt"] else None
    try:
        # Cheapest possible authenticated call, purely to populate the
        # rate-limit headers below — GET /accounts?limit=1 always exists
        # and every account-holder has at least a default account.
        client.get("/v1/api/accounts", limit=1, offset=0)
        out["rateLimitLimit"] = client.rate_limit_limit
        out["rateLimitRemaining"] = client.rate_limit_remaining
    except Exception as e:
        out["error"] = str(e)
    return out


# ================================================================
# SHARED HELPERS
# ================================================================
def _period_id_for(date_str, payroll_day, conn, cache=None):
    """Get-or-create the budget_periods row covering an arbitrary date —
    periods.ensure_current_period() only covers *today*, but a pull can
    backfill historical records that need their own (possibly already-
    closed) period. Duplicates ensure_current_period()'s small get-or-
    create query rather than changing that function's contract.

    `cache` (a dict keyed by period start_date) collapses the get-half to
    one query per distinct period per page instead of one per record — a
    page of 30 records usually spans only 1-2 periods. Does NOT commit:
    the INSERT rides the caller's page transaction (see _pull_records)."""
    d = datetime.date.fromisoformat((date_str or "")[:10])
    start_date, end_date = period_bounds(d, payroll_day)
    if cache is not None and start_date in cache:
        return cache[start_date]
    row = conn.execute("SELECT id FROM budget_periods WHERE start_date = ?", (start_date,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO budget_periods (start_date, end_date, payroll_day, expected_income) VALUES (?, ?, ?, 0)",
            (start_date, end_date, payroll_day),
        )
        row = conn.execute("SELECT id FROM budget_periods WHERE start_date = ?", (start_date,)).fetchone()
    if cache is not None:
        cache[start_date] = row[0]
    return row[0]


def _now() -> str:
    return str(config.now_jkt())


# ================================================================
# PULL — accounts and records only (see the module docstring for why the
# other four entity types are not pulled).
# Every _pull_X() takes apply=False to compute counts/skips without
# writing anything (the /sync/wallet/preview route), and apply=True to
# actually write (the /sync/wallet/pull route). Both paths run the exact
# same resolve/skip logic so a preview can't lie about what a real run
# would do.
# ================================================================
def _pull_accounts(client, cursor, apply=True) -> dict:
    result = {"created": 0, "updated": 0, "skipped": []}
    params = {"updatedAt": f"gte.{cursor}"} if cursor else {}
    max_updated = cursor
    for account in client.paginate("/v1/api/accounts", **params):
        remote_id = account["id"]
        updated_at = account.get("updatedAt")
        if updated_at and (not max_updated or updated_at > max_updated):
            max_updated = updated_at
        if account.get("currencyCode") != "IDR":
            result["skipped"].append({"remoteId": remote_id, "name": account.get("name"), "reason": "non-IDR currency"})
            continue

        fields = mapping.account_to_wallet_fields(account)
        link = repo.get_link_by_remote(ENTITY_ACCOUNT, remote_id)
        if link:
            if apply:
                repo.update_wallet(link["local_id"], **fields)
                repo.upsert_link(ENTITY_ACCOUNT, link["local_id"], remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull")
            result["updated"] += 1
        else:
            if apply:
                wallet = repo.create_wallet(fields["name"], kind=fields["kind"], opening_balance=fields["opening_balance"], spendable=fields["spendable"])
                if fields["archived"]:
                    repo.update_wallet(wallet["id"], archived=True)
                repo.upsert_link(ENTITY_ACCOUNT, wallet["id"], remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull")
            result["created"] += 1
    if apply:
        _set_cursor(ENTITY_ACCOUNT, max_updated)
    return result


def _pull_category_names(client, apply=True) -> dict:
    """Refreshes budget_wallet_category_names, the read-only id->name
    display cache, from Wallet's full category list (~85 rows, one page —
    small enough that a plain full refresh each run is simpler than a
    cursor, and categories change rarely enough that re-fetching is cheap
    against the 60/hour rate limit). This is NOT the category-as-budget-
    structure pull that was removed 2026-08-31 (see module docstring) — no
    budget_categories row is created or touched, only this cache table.

    Always reports every row as "updated" (create/update is not a
    meaningful distinction for a pure name cache)."""
    result = {"created": 0, "updated": 0, "skipped": []}
    conn = db_conn() if apply else None
    try:
        for category in client.paginate("/v1/api/categories"):
            fields = mapping.category_to_name_fields(category)
            if apply:
                repo.upsert_wallet_category_name(fields["remote_id"], fields["name"], conn=conn)
            result["updated"] += 1
        if apply:
            conn.commit()
    finally:
        if conn is not None:
            conn.close()
    return result


_RECORD_DATE_FLOOR = "2000-01-01T00:00:00.000Z"


def _pull_records(client, cursor, payroll_day, conn, apply=True, deadline=None) -> dict:
    """Confirmed against the live API 2026-08-12: GET /records silently
    defaults recordDate to the last ~3 months (visible in the response's
    own appliedRecordDateFilters) when no recordDate filter is given —
    unrelated to and stacking on top of the updatedAt cursor below, which
    only says "changed since". Without an explicit floor here, every
    record older than ~3 months is dropped from every pull forever, cursor
    or no cursor — pinning recordDate=gte.<floor> is what actually asks
    for full history.

    Records is the one unbounded pull (the API caps a user at 20,000).
    Three safeguards make a large first backfill survivable against the
    mobile-client abort and gunicorn's --timeout:
      - `deadline` (a time.monotonic() value) stops the loop at a page
        boundary and returns hasMore=True, so one request stays short and
        the caller just calls again until hasMore is False;
      - progress persists by OFFSET after each fully-applied page (results
        aren't sorted by updatedAt, so the updatedAt watermark can't be a
        resume point). The real updatedAt watermark is advanced, and the
        offset cleared, only once the whole history has drained;
      - every write for a page runs on the ONE caller-owned `conn` in a
        single transaction, committed once at the page boundary. Against a
        Postgres a ~600ms round-trip away (Railway logs, 2026-08), the old
        per-row INSERT+commit+re-SELECT for the txn, the labels and the
        link was ~13 round-trips/record — a shared transaction with no
        per-row commit and no re-fetch is ~4.
    """
    result = {"created": 0, "updated": 0, "skipped": [], "hasMore": False}
    params = {"recordDate": f"gte.{_RECORD_DATE_FLOOR}"}
    if cursor:
        params["updatedAt"] = f"gte.{cursor}"
    start_offset, carried_max = _get_record_progress() if apply else (0, None)
    max_updated = cursor or carried_max
    # Bounded so ONE page finishes inside gunicorn's --timeout and the
    # client's ceiling even in the slow-DB case (~4 round-trips/record x
    # ~600ms x 30 ≈ 75s); the deadline is only checked between pages.
    page_size = 30 if deadline is not None else 200
    period_cache: dict = {}
    for page, next_offset in client.paginate_pages(
        "/v1/api/records", convertTo="IDR", start_offset=start_offset, page_size=page_size, **params
    ):
        for record in page:
            remote_id = record["id"]
            updated_at = record.get("updatedAt")
            if updated_at and (not max_updated or updated_at > max_updated):
                max_updated = updated_at

            account_link = repo.get_link_by_remote(ENTITY_ACCOUNT, record.get("accountId"), conn=conn)
            if account_link is None:
                result["skipped"].append({"remoteId": remote_id, "reason": "unknown account — pull accounts first"})
                continue

            category_remote_id = mapping.record_category_id(record)
            category_id = None
            if category_remote_id and not mapping.is_restricted_category(category_remote_id):
                category_link = repo.get_link_by_remote(ENTITY_CATEGORY, category_remote_id, conn=conn)
                category_id = category_link["local_id"] if category_link else None

            try:
                fields = mapping.record_to_transaction_fields(
                    record, category_id=category_id, category_remote_id=category_remote_id,
                    wallet_id=account_link["local_id"],
                )
            except ValueError as e:
                result["skipped"].append({"remoteId": remote_id, "reason": str(e)})
                continue

            link = repo.get_link_by_remote(ENTITY_RECORD, remote_id, conn=conn)
            if link:
                if apply:
                    # Wallet wins on money — but category_id and bill_id are
                    # deliberately absent from this call. Those are local
                    # budget decisions (filed by hand, or via "Attach an
                    # existing transaction"), and re-sending the resolved
                    # value would blank them on every single sync.
                    # wallet_category_remote_id IS included: it's display-
                    # only (see _TXN_LIST_SQL), so refreshing it can't undo
                    # a local filing decision the way overwriting category_id
                    # would.
                    repo.update_transaction(
                        link["local_id"], conn=conn,
                        occurred_at=fields["occurred_at"], amount=fields["amount"],
                        direction=fields["direction"], wallet_id=fields["wallet_id"],
                        note=fields["note"], wallet_category_remote_id=fields["wallet_category_remote_id"],
                    )
                    repo.upsert_link(ENTITY_RECORD, link["local_id"], remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull", conn=conn)
                result["updated"] += 1
            else:
                if apply:
                    period_id = _period_id_for(fields["occurred_at"], payroll_day, conn, cache=period_cache)
                    txn_id = repo.create_transaction(
                        amount=fields["amount"], direction=fields["direction"], category_id=fields["category_id"],
                        wallet_id=fields["wallet_id"], period_id=period_id, note=fields["note"],
                        source="wallet", raw_input=remote_id, occurred_at=fields["occurred_at"],
                        wallet_category_remote_id=fields["wallet_category_remote_id"], conn=conn,
                    )
                    repo.upsert_link(ENTITY_RECORD, txn_id, remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull", conn=conn)
                result["created"] += 1

        # Page fully applied. Commit the whole page as one transaction, then
        # persist the resume point. A crash before the commit rolls the page
        # back and the offset isn't advanced -> the next run re-pulls it
        # (idempotent: links exist -> update path).
        if apply:
            conn.commit()
        if next_offset is not None:
            if apply:
                _set_record_progress(next_offset, max_updated)
            if deadline is not None and time.monotonic() >= deadline:
                result["hasMore"] = True
                return result

    # Whole history drained: now it's safe to advance the real updatedAt
    # watermark (steady-state incremental syncs key off it) and drop the
    # backfill progress.
    if apply:
        _set_cursor(ENTITY_RECORD, max_updated)
        _set_record_progress(0, None)
    return result


def pull_all(apply=True, max_seconds=None) -> dict:
    """Pulls accounts then records. Returns per-entity summaries;
    raises (rather than partially swallowing) on the first
    hard failure — features/budget/errors.py's WalletError subclasses all
    map to the standard envelope, so the blueprint route surfaces exactly
    what failed. Whatever ran before the failure already committed its
    writes and advanced its own cursor, so a retry resumes past it.

    `max_seconds` bounds the records pull (the only unbounded one): once
    the budget is spent it stops at a page boundary and returns with
    summary["records"]["hasMore"] True. The caller keeps calling pull_all()
    until that flag is False — each call resumes from the persisted offset
    (_get_record_progress). Left None (preview, tests) it drains everything."""
    from features.budget.service import get_payroll_day

    client = WalletClient()
    if not client.configured():
        raise WalletNotConfigured("WALLET_API_TOKEN is not set.")
    cursors = _get_cursors()
    deadline = (time.monotonic() + max_seconds) if max_seconds else None

    # Mid-backfill resume: accounts were drained on the first call (the
    # cursor is set), and re-walking them every /pull round adds seconds
    # against a far-region DB for near-zero new rows. Skip straight to
    # records until the history is in; the next sync picks up anything
    # added since. Category names ride along with accounts here for the
    # same reason — both are small, bounded pulls worth skipping mid-
    # backfill, unlike the unbounded records pull below.
    resuming_backfill = apply and _get_record_progress()[0] > 0

    conn = db_conn()
    try:
        summary = {
            "accounts": _empty_pull_result() if resuming_backfill
            else _pull_accounts(client, cursors.get(ENTITY_ACCOUNT), apply=apply),
            "categoryNames": _empty_pull_result() if resuming_backfill
            else _pull_category_names(client, apply=apply),
        }
        summary["records"] = _pull_records(
            client, cursors.get(ENTITY_RECORD), get_payroll_day(), conn, apply=apply, deadline=deadline
        )
    finally:
        conn.close()
    if apply:
        _record_run({"direction": "pull", "counts": {k: {"created": v["created"], "updated": v["updated"]} for k, v in summary.items()}})
    return summary


def preview() -> dict:
    """Dry run of the pull — identical resolve/skip logic to a real run,
    nothing written. Always call this before pull_all(apply=True) against
    real financial data. There is no push half: this app never writes to
    Wallet (see the module docstring)."""
    return {"pull": pull_all(apply=False)}




# ================================================================
# COMPARE — Wallet's own computed budget spend, next to compute.py's
# numbers. Approximate by construction: Wallet's calendar periods never
# align with our pay-cycle periods.
# ================================================================
def compare() -> dict:
    from features.budget import service

    client = WalletClient()
    if not client.configured():
        raise WalletNotConfigured("WALLET_API_TOKEN is not set.")

    local = service.build_period_view()
    remote_budgets = list(client.paginate("/v1/api/budgets", spending="current+5"))
    return {
        "local": None if local is None else {
            "freeMoney": local["free_money"], "dailyBudget": int(local["daily_budget"]),
            "daysLeft": local["days_left"], "statusLevel": local["status_level"],
        },
        "walletBudgets": [
            {
                "id": b.get("id"), "name": b.get("name"),
                "spending": (b.get("spending") or {}).get("current"),
            }
            for b in remote_budgets
        ],
        "note": "Wallet's budgets are calendar-anchored; they will not line up with this app's pay-cycle periods.",
    }
