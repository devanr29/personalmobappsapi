"""Orchestrates two-way sync between the local budget ledger and Wallet by
BudgetBakers. client.py is the HTTP transport, mapping.py is the pure field
conversion; this module is the only place that combines them with repo.py
reads/writes. features/budget/blueprint.py's /sync/wallet/* routes are the
only callers — manual-trigger only, no scheduler job (see docs/BUDGETBAKERS_API.md).

Pull order matters: accounts -> categories -> labels -> goals ->
standing-orders -> records. Records reference accounts/categories/labels by
remote id, so those must already have local links before records are
pulled, or every record would be skipped as "unknown account".

Push is scoped narrower than pull, for reasons documented inline at each
push function:
  - records:            create + update (budget_transactions.updated_at
                         makes "changed since last sync" detectable)
  - wallets/categories/labels: create-only — those local tables have no
                         updated_at column, so there is no reliable way to
                         detect "edited locally since last push" for them;
                         re-pushing every row every run would either spam
                         Wallet with redundant PATCHes or require guessing.
                         A local edit made after the first push simply
                         doesn't propagate — documented, not silent.
  - budgets/periods:     never pushed. Wallet's calendar-anchored budgets
                         cannot express our recurring pay cycle.
  - goals/standing-orders: never pushed — Wallet has no write endpoint for
                         either (see the write matrix in
                         docs/BUDGETBAKERS_API.md).
  - transfer/adjustment transactions: never pushed. 'adjustment' is a
                         local-only reconciliation concept. 'transfer'
                         would need Wallet's paired-mirror-record payload
                         shape, which wasn't confirmed against the live
                         schema (see mapping.py's module docstring) — safer
                         to skip than guess at a money-moving payload.

Conflict policy: Wallet wins on pull, EXCEPT a record isn't overwritten if
its local updated_at is newer than the link's local_synced_at (a local
edit that hasn't been pushed yet) — see _pull_records()'s local_newer
check. Push never touches a bank-synced account/record.
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
from features.budget.wallet.client import WalletClient, extract_created_id

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
def _period_id_for(date_str, payroll_day, conn):
    """Get-or-create the budget_periods row covering an arbitrary date —
    periods.ensure_current_period() only covers *today*, but a pull can
    backfill historical records that need their own (possibly already-
    closed) period. Duplicates ensure_current_period()'s small get-or-
    create query rather than changing that function's contract."""
    d = datetime.date.fromisoformat((date_str or "")[:10])
    start_date, end_date = period_bounds(d, payroll_day)
    row = conn.execute("SELECT id FROM budget_periods WHERE start_date = ?", (start_date,)).fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO budget_periods (start_date, end_date, payroll_day, expected_income) VALUES (?, ?, ?, 0)",
        (start_date, end_date, payroll_day),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM budget_periods WHERE start_date = ?", (start_date,)).fetchone()
    return row[0]


def _now() -> str:
    return str(config.now_jkt())


# ================================================================
# PULL — accounts, categories, labels, goals, standing-orders, records.
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


def _pull_categories(client, cursor, apply=True) -> dict:
    result = {"created": 0, "updated": 0, "skipped": []}
    params = {"updatedAt": f"gte.{cursor}"} if cursor else {}
    max_updated = cursor
    for category in client.paginate("/v1/api/categories", **params):
        remote_id = category["id"]
        updated_at = category.get("updatedAt")
        if updated_at and (not max_updated or updated_at > max_updated):
            max_updated = updated_at
        if mapping.is_restricted_category(remote_id):
            result["skipped"].append({"remoteId": remote_id, "name": category.get("name"), "reason": "system category"})
            continue

        fields = mapping.category_to_local_fields(category)
        link = repo.get_link_by_remote(ENTITY_CATEGORY, remote_id)
        if link:
            if apply:
                repo.update_category(link["local_id"], **fields)
                repo.upsert_link(ENTITY_CATEGORY, link["local_id"], remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull")
            result["updated"] += 1
        else:
            if apply:
                local_category = repo.create_category(fields["name"], fields["kind"])
                if fields["archived"]:
                    repo.update_category(local_category["id"], archived=True)
                repo.upsert_link(ENTITY_CATEGORY, local_category["id"], remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull")
            result["created"] += 1
    if apply:
        _set_cursor(ENTITY_CATEGORY, max_updated)
    return result


def _pull_labels(client, apply=True) -> dict:
    """No cursor — the /labels list params weren't confirmed to support
    updatedAt filtering, and label counts are small enough that a full
    fetch every run is cheap (unlike records)."""
    result = {"created": 0, "updated": 0, "skipped": []}
    for label in client.paginate("/v1/api/labels"):
        remote_id = label["id"]
        fields = mapping.label_to_local_fields(label)
        link = repo.get_link_by_remote(ENTITY_LABEL, remote_id)
        if link:
            if apply:
                repo.update_label(link["local_id"], **fields)
                repo.upsert_link(ENTITY_LABEL, link["local_id"], remote_id, remote_updated_at=label.get("updatedAt"), local_synced_at=_now(), last_direction="pull")
            result["updated"] += 1
        else:
            if apply:
                local_label = repo.create_label(fields["name"], color=fields["color"])
                if fields["archived"]:
                    repo.update_label(local_label["id"], archived=True)
                repo.upsert_link(ENTITY_LABEL, local_label["id"], remote_id, remote_updated_at=label.get("updatedAt"), local_synced_at=_now(), last_direction="pull")
            result["created"] += 1
    return result


def _pull_goals(client, cursor, apply=True) -> dict:
    result = {"created": 0, "updated": 0, "skipped": []}
    params = {"updatedAt": f"gte.{cursor}"} if cursor else {}
    max_updated = cursor
    for goal in client.paginate("/v1/api/goals", **params):
        remote_id = goal["id"]
        updated_at = goal.get("updatedAt")
        if updated_at and (not max_updated or updated_at > max_updated):
            max_updated = updated_at
        fields = mapping.goal_to_local_fields(goal)
        link = repo.get_link_by_remote(ENTITY_GOAL, remote_id)
        if link:
            if apply:
                repo.update_goal(link["local_id"], **fields)
                repo.upsert_link(ENTITY_GOAL, link["local_id"], remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull")
            result["updated"] += 1
        else:
            if apply:
                local_goal = repo.create_goal(fields["name"], fields["target_amount"], target_date=fields["target_date"], reserve_from_free=False)
                if fields["archived"]:
                    repo.update_goal(local_goal["id"], archived=True)
                repo.upsert_link(ENTITY_GOAL, local_goal["id"], remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull")
            result["created"] += 1
    if apply:
        _set_cursor(ENTITY_GOAL, max_updated)
    return result


def _pull_standing_orders(client, apply=True) -> dict:
    """No cursor — GET /standing-orders' filter params weren't confirmed;
    full fetch every run (standing orders are low-cardinality, unlike
    records)."""
    result = {"created": 0, "updated": 0, "skipped": []}
    for order in client.paginate("/v1/api/standing-orders"):
        remote_id = order["id"]
        fields = mapping.standing_order_to_bill_fields(order)
        category_remote_id = mapping.standing_order_category_id(order)
        category_link = repo.get_link_by_remote(ENTITY_CATEGORY, category_remote_id) if category_remote_id else None
        link = repo.get_link_by_remote(ENTITY_STANDING_ORDER, remote_id)
        if link:
            if apply:
                repo.update_bill(link["local_id"], **fields)
                repo.upsert_link(ENTITY_STANDING_ORDER, link["local_id"], remote_id, remote_updated_at=None, local_synced_at=_now(), last_direction="pull")
            result["updated"] += 1
        else:
            if apply:
                bill = repo.create_bill(
                    fields["name"], fields["amount"], due_day=fields["due_day"], cadence=fields["cadence"],
                    category_id=category_link["local_id"] if category_link else None,
                )
                repo.upsert_link(ENTITY_STANDING_ORDER, bill["id"], remote_id, remote_updated_at=None, local_synced_at=_now(), last_direction="pull")
            result["created"] += 1
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
    Two safeguards make a large first backfill survivable against the 20s
    mobile-client abort and gunicorn's --timeout:
      - `deadline` (a time.monotonic() value) stops the loop at a page
        boundary and returns hasMore=True, so one request stays short and
        the caller just calls again until hasMore is False;
      - progress persists by OFFSET after each fully-applied page (results
        aren't sorted by updatedAt, so the updatedAt watermark can't be a
        resume point). The real updatedAt watermark is advanced, and the
        offset cleared, only once the whole history has drained.
    """
    result = {"created": 0, "updated": 0, "skipped": [], "hasMore": False}
    params = {"recordDate": f"gte.{_RECORD_DATE_FLOOR}"}
    if cursor:
        params["updatedAt"] = f"gte.{cursor}"
    start_offset, carried_max = _get_record_progress() if apply else (0, None)
    max_updated = cursor or carried_max
    # Far smaller than the API's 200 max on purpose: the deadline is only
    # checked at page boundaries, and each row is ~8 DB round-trips (~50ms
    # each when the app and Postgres are in different regions), so a page
    # has to stay small enough that ONE of them finishes inside the request
    # budget and gunicorn's --timeout. ~30 rows ≈ 15s in the slow case.
    page_size = 30 if deadline is not None else 200
    for page, next_offset in client.paginate_pages(
        "/v1/api/records", convertTo="IDR", start_offset=start_offset, page_size=page_size, **params
    ):
        for record in page:
            remote_id = record["id"]
            updated_at = record.get("updatedAt")
            if updated_at and (not max_updated or updated_at > max_updated):
                max_updated = updated_at

            account_link = repo.get_link_by_remote(ENTITY_ACCOUNT, record.get("accountId"))
            if account_link is None:
                result["skipped"].append({"remoteId": remote_id, "reason": "unknown account — pull accounts first"})
                continue

            category_remote_id = mapping.record_category_id(record)
            category_id = None
            if category_remote_id and not mapping.is_restricted_category(category_remote_id):
                category_link = repo.get_link_by_remote(ENTITY_CATEGORY, category_remote_id)
                category_id = category_link["local_id"] if category_link else None

            try:
                fields = mapping.record_to_transaction_fields(record, category_id=category_id, wallet_id=account_link["local_id"])
            except ValueError as e:
                result["skipped"].append({"remoteId": remote_id, "reason": str(e)})
                continue

            label_ids = [
                l["local_id"] for l in (
                    repo.get_link_by_remote(ENTITY_LABEL, rlid) for rlid in mapping.record_label_ids(record)
                ) if l
            ]

            link = repo.get_link_by_remote(ENTITY_RECORD, remote_id)
            if link:
                existing = repo.get_transaction(link["local_id"])
                local_synced_at = link.get("local_synced_at")
                local_edited_since_sync = (
                    existing and existing.get("updated_at") and local_synced_at
                    and existing["updated_at"] > local_synced_at
                )
                if local_edited_since_sync:
                    result["skipped"].append({"remoteId": remote_id, "reason": "local edit not yet pushed — pull skipped to avoid overwriting it"})
                    continue
                if apply:
                    repo.update_transaction(
                        link["local_id"], occurred_at=fields["occurred_at"], amount=fields["amount"],
                        direction=fields["direction"], category_id=fields["category_id"], wallet_id=fields["wallet_id"],
                        note=fields["note"],
                    )
                    repo.set_transaction_labels(link["local_id"], label_ids)
                    # local_synced_at captured AFTER update_transaction() (which
                    # always stamps its own updated_at) — must be >= that
                    # stamp, or this row would look "locally edited" and get
                    # selected for push next run, ping-ponging the same pulled
                    # data straight back to Wallet.
                    repo.upsert_link(ENTITY_RECORD, link["local_id"], remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull")
                result["updated"] += 1
            else:
                if apply:
                    period_id = _period_id_for(fields["occurred_at"], payroll_day, conn)
                    txn = repo.create_transaction(
                        amount=fields["amount"], direction=fields["direction"], category_id=fields["category_id"],
                        wallet_id=fields["wallet_id"], period_id=period_id, note=fields["note"],
                        source="wallet", raw_input=remote_id, occurred_at=fields["occurred_at"],
                    )
                    repo.set_transaction_labels(txn["id"], label_ids)
                    repo.upsert_link(ENTITY_RECORD, txn["id"], remote_id, remote_updated_at=updated_at, local_synced_at=_now(), last_direction="pull")
                result["created"] += 1

        # Page fully applied. More to come -> persist offset + running max
        # so a killed/timed-out run resumes here; stop if the budget's spent.
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
    """Runs every entity pull in dependency order. Returns per-entity
    summaries; raises (rather than partially swallowing) on the first
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

    # Mid-backfill resume: accounts/categories/labels/goals/standing-orders
    # were all drained on the first call (their cursors are set), and
    # re-walking them every /pull round adds tens of seconds against a
    # far-region DB for near-zero new rows. Skip straight to records until
    # the history is in; the next full sync picks up anything added since.
    resuming_backfill = apply and _get_record_progress()[0] > 0

    conn = db_conn()
    try:
        if resuming_backfill:
            summary = {k: _empty_pull_result() for k in ("accounts", "categories", "labels", "goals", "bills")}
        else:
            summary = {
                "accounts": _pull_accounts(client, cursors.get(ENTITY_ACCOUNT), apply=apply),
                "categories": _pull_categories(client, cursors.get(ENTITY_CATEGORY), apply=apply),
                "labels": _pull_labels(client, apply=apply),
                "goals": _pull_goals(client, cursors.get(ENTITY_GOAL), apply=apply),
                "bills": _pull_standing_orders(client, apply=apply),
            }
        summary["records"] = _pull_records(
            client, cursors.get(ENTITY_RECORD), get_payroll_day(), conn, apply=apply, deadline=deadline
        )
    finally:
        conn.close()
    if apply:
        _record_run({"direction": "pull", "counts": {k: {"created": v["created"], "updated": v["updated"]} for k, v in summary.items()}})
    return summary


# ================================================================
# PUSH — records (create+update+delete), wallets/categories/labels
# (create-only). See this module's docstring for the full scoping
# rationale.
# ================================================================
def _push_records(client, apply=True) -> dict:
    result = {"created": 0, "updated": 0, "deleted": 0, "skipped": [], "errors": []}

    # New/edited: no link row, or local updated_at newer than the link's
    # last sync point.
    for txn in repo.get_active_transactions():
        link = repo.get_link_by_local(ENTITY_RECORD, txn["id"])
        if link and (not txn.get("updated_at") or not link.get("local_synced_at") or txn["updated_at"] <= link["local_synced_at"]):
            continue  # unchanged since last sync — the normal steady-state case, not worth reporting

        if txn["direction"] in ("transfer", "adjustment"):
            # Reported (not silently dropped) only because it reached
            # here — i.e. it's new or changed and would otherwise have
            # been pushed. See this module's docstring for why these two
            # directions never push. Never gets a link row, so it's
            # re-reported every run until the set of unpushed
            # transfers/adjustments stops growing.
            result["skipped"].append({"localId": txn["id"], "reason": f"direction={txn['direction']} is not pushed to Wallet"})
            continue

        wallet_link = repo.get_link_by_local(ENTITY_ACCOUNT, txn["wallet_id"]) if txn["wallet_id"] else None
        if wallet_link is None:
            result["skipped"].append({"localId": txn["id"], "reason": "wallet not linked to a Wallet account yet — push accounts first"})
            continue
        category_link = repo.get_link_by_local(ENTITY_CATEGORY, txn["category_id"]) if txn["category_id"] else None
        label_links = [repo.get_link_by_local(ENTITY_LABEL, lid) for lid in repo.get_transaction_label_ids(txn["id"])]
        label_remote_ids = [l["remote_id"] for l in label_links if l]

        try:
            if link:
                patch = mapping.transaction_to_record_patch(txn, category_id=category_link["remote_id"] if category_link else None, label_ids=label_remote_ids)
                if apply and patch:
                    client.patch("/v1/api/records", [{"id": link["remote_id"], **patch}])
                if apply:
                    repo.upsert_link(ENTITY_RECORD, txn["id"], link["remote_id"], remote_updated_at=link.get("remote_updated_at"), local_synced_at=_now(), last_direction="push")
                result["updated"] += 1
            else:
                payload = mapping.transaction_to_record_payload(
                    txn, account_id=wallet_link["remote_id"],
                    category_id=category_link["remote_id"] if category_link else None,
                    label_ids=label_remote_ids,
                )
                if apply:
                    body = client.post("/v1/api/records", [payload])
                    remote_id = extract_created_id(body)
                    if remote_id:
                        repo.upsert_link(ENTITY_RECORD, txn["id"], remote_id, remote_updated_at=None, local_synced_at=_now(), last_direction="push")
                    else:
                        result["errors"].append({"localId": txn["id"], "reason": f"could not read created record id from response: {body}"})
                        continue
                result["created"] += 1
        except Exception as e:
            result["errors"].append({"localId": txn["id"], "reason": str(e)})

    # Soft-deleted locally, still linked -> delete remotely.
    delete_remote_ids = []
    for local_id in repo.get_deleted_transaction_ids():
        link = repo.get_link_by_local(ENTITY_RECORD, local_id)
        if link:
            delete_remote_ids.append((local_id, link["remote_id"]))
    for i in range(0, len(delete_remote_ids), 10):
        batch = delete_remote_ids[i:i + 10]
        try:
            if apply:
                client.delete_batch("records", [remote_id for _, remote_id in batch])
                for local_id, _ in batch:
                    repo.delete_link(ENTITY_RECORD, local_id)
            result["deleted"] += len(batch)
        except Exception as e:
            result["errors"].append({"reason": str(e), "localIds": [local_id for local_id, _ in batch]})

    return result


def _push_new_wallets(client, apply=True) -> dict:
    result = {"created": 0, "skipped": []}
    for wallet in repo.get_wallets(include_archived=True):
        if repo.get_link_by_local(ENTITY_ACCOUNT, wallet["id"]):
            continue
        payload = mapping.wallet_to_account_payload(wallet)
        try:
            if apply:
                body = client.post("/v1/api/accounts", payload)
                remote_id = extract_created_id(body)
                if remote_id:
                    repo.upsert_link(ENTITY_ACCOUNT, wallet["id"], remote_id, remote_updated_at=None, local_synced_at=_now(), last_direction="push")
                else:
                    result["skipped"].append({"localId": wallet["id"], "reason": f"could not read created account id: {body}"})
                    continue
            result["created"] += 1
        except Exception as e:
            result["skipped"].append({"localId": wallet["id"], "reason": str(e)})
    return result


def _push_new_categories(client, apply=True) -> dict:
    """Custom categories need a system parentId (docs/BUDGETBAKERS_API.md) —
    there's no local field to derive one from, so this defaults every
    pushed category to Wallet's 'Uncategorized' parent isn't allowed
    (it's restricted) and no other safe default exists. Left as a
    documented gap: local-only categories aren't pushed until a parent-
    category mapping is added."""
    return {"created": 0, "skipped": [{"reason": "pushing new categories needs a parentId mapping not yet implemented — see _push_new_categories docstring"}]}


def _push_new_labels(client, apply=True) -> dict:
    result = {"created": 0, "skipped": []}
    for label in repo.get_labels(include_archived=True):
        if repo.get_link_by_local(ENTITY_LABEL, label["id"]):
            continue
        payload = mapping.local_label_to_payload(label)
        try:
            if apply:
                body = client.post("/v1/api/labels", payload)
                remote_id = extract_created_id(body)
                if remote_id:
                    repo.upsert_link(ENTITY_LABEL, label["id"], remote_id, remote_updated_at=None, local_synced_at=_now(), last_direction="push")
                else:
                    result["skipped"].append({"localId": label["id"], "reason": f"could not read created label id: {body}"})
                    continue
            result["created"] += 1
        except Exception as e:
            result["skipped"].append({"localId": label["id"], "reason": str(e)})
    return result


def push_all(apply=True) -> dict:
    client = WalletClient()
    if not client.configured():
        raise WalletNotConfigured("WALLET_API_TOKEN is not set.")
    summary = {
        "wallets": _push_new_wallets(client, apply=apply),
        "categories": _push_new_categories(client, apply=apply),
        "labels": _push_new_labels(client, apply=apply),
        "records": _push_records(client, apply=apply),
    }
    if apply:
        _record_run({"direction": "push", "counts": {
            k: {kk: vv for kk, vv in v.items() if kk not in ("skipped", "errors")} for k, v in summary.items()
        }})
    return summary


def preview() -> dict:
    """Dry run of both directions — identical resolve/skip logic to a real
    run, nothing written. Always call this before push_all(apply=True)
    against real financial data."""
    return {"pull": pull_all(apply=False), "push": push_all(apply=False)}


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
