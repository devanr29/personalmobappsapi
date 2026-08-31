"""Routes for the standalone budget feature. Registered at /api/budget in
app.py. Blueprint hooks (before_request/after_request/errorhandler) do not
inherit from api_bp, so auth/CORS/error-mapping are wired independently
here via the shared functions in api_common.py."""
from flask import Blueprint, request

from api_common import ok, err, add_cors_headers, check_auth, handle_unexpected_error, start_timer, log_timing
from config import now_jkt
from db import db_conn
from features.budget import repo, service
from features.budget.errors import BudgetError
from features.budget.serializers import (
    camel_alert, camel_alert_prefs, camel_bill, camel_budget_breakdown, camel_category, camel_goal,
    camel_seed_result, camel_transaction, camel_wallet,
)
from features.budget.wallet import sync as wallet_sync

budget_bp = Blueprint("budget", __name__)


@budget_bp.before_request
def _start_timer():
    start_timer()


@budget_bp.after_request
def _log_timing(resp):
    return log_timing(resp)


@budget_bp.after_request
def _cors(resp):
    return add_cors_headers(resp)


@budget_bp.before_request
def _check_auth():
    return check_auth()


@budget_bp.errorhandler(BudgetError)
def _handle_budget_error(e):
    return err(e.code, e.message, e.status)


@budget_bp.errorhandler(Exception)
def _handle_unexpected(e):
    return handle_unexpected_error(e, tag="budget")


@budget_bp.route("/ping", methods=["GET"])
def ping():
    return ok({"pong": True})


@budget_bp.route("", methods=["GET"])
def summary():
    return ok(service.get_summary())


@budget_bp.route("/breakdown", methods=["GET"])
def breakdown():
    # One connection shared across both calls: build_period_view() is a
    # ~9-round-trip aggregate, and get_today_card() used to recompute it
    # from scratch internally — passing the already-computed `data` in as
    # `view` skips that second full pass entirely.
    #
    # Also carries wallets + unreadAlertCount now (see camel_budget_breakdown
    # and build_period_view's data["wallets"]) so the Budget tab's screen
    # load is one request instead of four (GET /breakdown was previously
    # joined by separate GET /api/budget, /wallets, /alerts calls — each
    # firing its own independent ~9-query build_period_view() on the
    # summary side alone).
    conn = db_conn()
    try:
        data = service.build_period_view(conn=conn)
        if not data:
            return ok(None)
        body = camel_budget_breakdown(data)
        body["computedAt"] = str(now_jkt())
        body["today"] = service.get_today_card(view=data, conn=conn)
        _, unread_count = repo.get_alerts(unread_only=True, limit=1)
        body["unreadAlertCount"] = unread_count
        return ok(body)
    finally:
        conn.close()


@budget_bp.route("/insights", methods=["GET"])
def insights_view():
    return ok(service.build_insights())


_MAX_HISTORY_PERIODS = 24


@budget_bp.route("/insights/history", methods=["GET"])
def insights_history():
    # Clamped, not 400'd: `periods` lands in a bare SQL LIMIT, where a
    # negative value is "no limit" on SQLite but a hard error (22023) on
    # Postgres. Clamping matches the house convention already set by
    # _MAX_TXN_LIMIT below.
    periods = max(1, min(_int_arg("periods") or 6, _MAX_HISTORY_PERIODS))
    group_by = request.args.get("groupBy", "period")
    if group_by not in ("period", "month"):
        return err("VALIDATION_ERROR", "groupBy must be 'period' or 'month'.", 400)
    return ok(service.build_insights_history(periods=periods, group_by=group_by))


_MAX_CATEGORY_MONTHS = 24


@budget_bp.route("/insights/categories", methods=["GET"])
def insights_categories():
    # Same clamp discipline as _MAX_HISTORY_PERIODS above — months feeds a
    # Python range() and a per-category list comprehension here rather than
    # a SQL LIMIT, but an unbounded value is still worth rejecting cheaply.
    months = max(1, min(_int_arg("months") or 12, _MAX_CATEGORY_MONTHS))
    return ok(service.build_category_patterns(months=months))


# ================================================================
# WALLETS
# ================================================================
@budget_bp.route("/wallets", methods=["GET"])
def wallets_list():
    wallets = repo.get_wallets(include_archived=bool(request.args.get("includeArchived")))
    balances = repo.wallet_balances()
    return ok({"items": [{**camel_wallet(w), "balance": balances.get(w["id"], 0)} for w in wallets]})


@budget_bp.route("/wallets", methods=["POST"])
def wallets_create():
    body = request.get_json(silent=True) or {}
    if "name" not in body:
        return err("VALIDATION_ERROR", "name is required.", 400)
    wallet = service.create_wallet(
        body["name"], kind=body.get("kind", "cash"), opening_balance=body.get("openingBalance", 0),
        spendable=body.get("spendable", True), is_default=body.get("isDefault", False),
    )
    return ok({"wallet": {**camel_wallet(wallet), "balance": repo.wallet_balance(wallet["id"])}}, status=201)


@budget_bp.route("/wallets/<int:wallet_id>", methods=["PATCH"])
def wallets_edit(wallet_id):
    body = request.get_json(silent=True) or {}
    fields = {}
    for camel, snake in (
        ("name", "name"), ("kind", "kind"), ("openingBalance", "opening_balance"),
        ("spendable", "spendable"), ("isDefault", "is_default"), ("archived", "archived"),
    ):
        if camel in body:
            fields[snake] = body[camel]
    wallet = service.update_wallet(wallet_id, **fields)
    return ok({"wallet": {**camel_wallet(wallet), "balance": repo.wallet_balance(wallet["id"])}})


@budget_bp.route("/wallets/<int:wallet_id>", methods=["DELETE"])
def wallets_delete(wallet_id):
    service.delete_wallet(wallet_id)
    return ok({"id": wallet_id, "deleted": True})


@budget_bp.route("/wallets/transfer", methods=["POST"])
def wallets_transfer():
    body = request.get_json(silent=True) or {}
    for field in ("fromWalletId", "toWalletId", "amount"):
        if field not in body:
            return err("VALIDATION_ERROR", f"{field} is required.", 400)
    txn, summary = service.transfer_between_wallets(
        body["fromWalletId"], body["toWalletId"], body["amount"],
        occurred_at=body.get("occurredAt"), note=body.get("note"),
    )
    return ok({"transaction": camel_transaction(txn), "summary": summary}, status=201)


@budget_bp.route("/wallets/<int:wallet_id>/reconcile", methods=["POST"])
def wallets_reconcile(wallet_id):
    body = request.get_json(silent=True) or {}
    if "actualBalance" not in body:
        return err("VALIDATION_ERROR", "actualBalance is required.", 400)
    result, summary = service.reconcile_wallet(wallet_id, body["actualBalance"], note=body.get("note"))
    if result.get("transaction"):
        result = {**result, "transaction": camel_transaction(result["transaction"])}
    return ok({**result, "summary": summary})


# ================================================================
# CATEGORIES
# ================================================================
@budget_bp.route("/categories", methods=["GET"])
def categories_list():
    kind = request.args.get("kind")
    categories = repo.get_categories(kind=kind, include_archived=bool(request.args.get("includeArchived")))
    return ok({"items": [camel_category(c) for c in categories]})


@budget_bp.route("/categories", methods=["POST"])
def categories_create():
    body = request.get_json(silent=True) or {}
    if "name" not in body or "kind" not in body:
        return err("VALIDATION_ERROR", "name and kind are required.", 400)
    category = service.create_category(
        body["name"], body["kind"], monthly_limit=body.get("monthlyLimit"),
        rollover=body.get("rollover", False), icon=body.get("icon"), color_index=body.get("colorIndex"),
    )
    return ok({"category": camel_category(category)}, status=201)


@budget_bp.route("/categories/<int:category_id>", methods=["PATCH"])
def categories_edit(category_id):
    body = request.get_json(silent=True) or {}
    fields = {}
    for camel, snake in (
        ("name", "name"), ("kind", "kind"), ("monthlyLimit", "monthly_limit"),
        ("rollover", "rollover"), ("icon", "icon"), ("colorIndex", "color_index"), ("archived", "archived"),
    ):
        if camel in body:
            fields[snake] = body[camel]
    category = service.update_category(category_id, **fields)
    return ok({"category": camel_category(category)})


@budget_bp.route("/categories/<int:category_id>", methods=["DELETE"])
def categories_delete(category_id):
    service.delete_category(category_id)
    return ok({"id": category_id, "deleted": True})


@budget_bp.route("/categories/<int:category_id>/pay", methods=["POST"])
def categories_pay(category_id):
    body = request.get_json(silent=True) or {}
    txn, summary = service.pay_variable_category(
        category_id, wallet_id=body.get("walletId"), amount=body.get("amount"),
        occurred_at=body.get("occurredAt"), create_transaction=body.get("createTransaction", True),
    )
    return ok({"transaction": camel_transaction(txn) if txn else None, "summary": summary}, status=201)


@budget_bp.route("/categories/<int:category_id>/pay", methods=["DELETE"])
def categories_unpay(category_id):
    category, summary = service.unpay_variable_category(category_id)
    return ok({"category": camel_category(category), "summary": summary})


# ================================================================
# BILLS
# ================================================================
@budget_bp.route("/bills", methods=["GET"])
def bills_list():
    active_only = request.args.get("activeOnly", "1") not in ("0", "false", "False")
    bills = repo.get_bills(active_only=active_only)
    return ok({"items": [camel_bill(b) for b in bills]})


@budget_bp.route("/bills", methods=["POST"])
def bills_create():
    body = request.get_json(silent=True) or {}
    if "name" not in body or "amount" not in body:
        return err("VALIDATION_ERROR", "name and amount are required.", 400)
    bill = service.create_bill(
        body["name"], body["amount"], due_day=body.get("dueDay"), category_id=body.get("categoryId"),
        wallet_id=body.get("walletId"), cadence=body.get("cadence", "monthly"), autopost=body.get("autopost", False),
    )
    return ok({"bill": camel_bill(bill)}, status=201)


@budget_bp.route("/bills/<int:bill_id>", methods=["PATCH"])
def bills_edit(bill_id):
    body = request.get_json(silent=True) or {}
    fields = {}
    for camel, snake in (
        ("name", "name"), ("amount", "amount"), ("dueDay", "due_day"), ("cadence", "cadence"),
        ("categoryId", "category_id"), ("walletId", "wallet_id"), ("autopost", "autopost"), ("active", "active"),
    ):
        if camel in body:
            fields[snake] = body[camel]
    bill = service.update_bill(bill_id, **fields)
    return ok({"bill": camel_bill(bill)})


@budget_bp.route("/bills/<int:bill_id>", methods=["DELETE"])
def bills_delete(bill_id):
    service.delete_bill(bill_id)
    return ok({"id": bill_id, "deleted": True})


@budget_bp.route("/bills/<int:bill_id>/pay", methods=["POST"])
def bills_pay(bill_id):
    body = request.get_json(silent=True) or {}
    txn, summary = service.pay_bill(
        bill_id, wallet_id=body.get("walletId"), amount=body.get("amount"), occurred_at=body.get("occurredAt"),
    )
    return ok({"transaction": camel_transaction(txn), "summary": summary}, status=201)


@budget_bp.route("/bills/<int:bill_id>/pay", methods=["DELETE"])
def bills_unpay(bill_id):
    bill, summary = service.unpay_bill(bill_id)
    return ok({"bill": camel_bill(bill), "summary": summary})


# ================================================================
# SETUP WIZARD
# ================================================================
@budget_bp.route("/setup/status", methods=["GET"])
def setup_status():
    status = service.get_setup_status()
    return ok({
        "seeded": status["seeded"],
        "walletCount": status["wallet_count"],
        "categoryCount": status["category_count"],
        "billCount": status["bill_count"],
    })


@budget_bp.route("/setup", methods=["POST"])
def setup_run():
    body = request.get_json(silent=True) or {}
    result = service.run_setup(
        payroll_day=body.get("payrollDay"), wallets=body.get("wallets"),
        categories=body.get("categories"), bills=body.get("bills"), force=bool(body.get("force")),
    )
    return ok(camel_seed_result(result), status=201)


# ================================================================
# TRANSACTIONS
# ================================================================
_MAX_TXN_LIMIT = 200


def _int_arg(name):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@budget_bp.route("/transactions", methods=["GET"])
def transactions_list():
    limit = min(_int_arg("limit") or 50, _MAX_TXN_LIMIT)
    offset = _int_arg("offset") or 0
    items, total = service.list_transactions(
        category_id=_int_arg("categoryId"),
        wallet_id=_int_arg("walletId"),
        direction=request.args.get("direction"),
        date_from=request.args.get("from"),
        date_to=request.args.get("to"),
        limit=limit,
        offset=offset,
    )
    meta = {"total": total, "limit": limit, "offset": offset, "hasMore": offset + len(items) < total}
    return ok({"items": [camel_transaction(t) for t in items]}, meta=meta)


@budget_bp.route("/transactions", methods=["POST"])
def transactions_create():
    body = request.get_json(silent=True) or {}
    if "amount" not in body or "direction" not in body:
        return err("VALIDATION_ERROR", "amount and direction are required.", 400)
    txn, summary = service.create_transaction(
        amount=body.get("amount"),
        direction=body.get("direction"),
        category_id=body.get("categoryId"),
        wallet_id=body.get("walletId"),
        transfer_wallet_id=body.get("transferWalletId"),
        occurred_at=body.get("occurredAt"),
        note=body.get("note"),
        goal_id=body.get("goalId"),
    )
    return ok({"transaction": camel_transaction(txn), "summary": summary}, status=201)


@budget_bp.route("/transactions/<int:txn_id>", methods=["PATCH"])
def transactions_edit(txn_id):
    body = request.get_json(silent=True) or {}
    fields = {}
    if "amount" in body:
        fields["amount"] = body["amount"]
    if "direction" in body:
        fields["direction"] = body["direction"]
    if "categoryId" in body:
        fields["category_id"] = body["categoryId"]
    if "walletId" in body:
        fields["wallet_id"] = body["walletId"]
    if "transferWalletId" in body:
        fields["transfer_wallet_id"] = body["transferWalletId"]
    if "occurredAt" in body:
        fields["occurred_at"] = body["occurredAt"]
    if "note" in body:
        fields["note"] = body["note"]

    txn, summary = service.update_transaction(txn_id, **fields)
    return ok({"transaction": camel_transaction(txn), "summary": summary})


@budget_bp.route("/transactions/<int:txn_id>", methods=["DELETE"])
def transactions_delete(txn_id):
    txn, summary = service.delete_transaction(txn_id)
    return ok({"id": txn_id, "deleted": True, "summary": summary})


# ================================================================
# GOALS
# ================================================================
@budget_bp.route("/goals", methods=["GET"])
def goals_list():
    include_archived = bool(request.args.get("includeArchived"))
    goals = repo.get_goals(include_archived=include_archived)
    return ok({"items": [{**camel_goal(g), "saved": repo.goal_saved(g["id"])} for g in goals]})


@budget_bp.route("/goals", methods=["POST"])
def goals_create():
    body = request.get_json(silent=True) or {}
    if "name" not in body or "targetAmount" not in body:
        return err("VALIDATION_ERROR", "name and targetAmount are required.", 400)
    goal = service.create_goal(
        body["name"], body["targetAmount"], kind=body.get("kind", "sinking"),
        target_date=body.get("targetDate"), monthly_contribution=body.get("monthlyContribution"),
        reserve_from_free=body.get("reserveFromFree", True), wallet_id=body.get("walletId"),
    )
    return ok({"goal": {**camel_goal(goal), "saved": 0}}, status=201)


@budget_bp.route("/goals/<int:goal_id>", methods=["PATCH"])
def goals_edit(goal_id):
    body = request.get_json(silent=True) or {}
    fields = {}
    for camel, snake in (
        ("name", "name"), ("kind", "kind"), ("targetAmount", "target_amount"),
        ("targetDate", "target_date"), ("monthlyContribution", "monthly_contribution"),
        ("reserveFromFree", "reserve_from_free"), ("walletId", "wallet_id"), ("archived", "archived"),
    ):
        if camel in body:
            fields[snake] = body[camel]
    goal = service.update_goal(goal_id, **fields)
    return ok({"goal": {**camel_goal(goal), "saved": repo.goal_saved(goal_id)}})


@budget_bp.route("/goals/<int:goal_id>", methods=["DELETE"])
def goals_delete(goal_id):
    service.delete_goal(goal_id)
    return ok({"id": goal_id, "deleted": True})


@budget_bp.route("/goals/<int:goal_id>/contribute", methods=["POST"])
def goals_contribute(goal_id):
    body = request.get_json(silent=True) or {}
    if "amount" not in body:
        return err("VALIDATION_ERROR", "amount is required.", 400)
    result, summary = service.contribute_to_goal(
        goal_id, body["amount"], wallet_id=body.get("walletId"), occurred_at=body.get("occurredAt"),
    )
    return ok({
        "goal": {**camel_goal(result["goal"]), "saved": result["saved"]},
        "transaction": camel_transaction(result["transaction"]) if result["transaction"] else None,
        "summary": summary,
    }, status=201)


# ================================================================
# ALERTS — in-app inbox (primary channel) + preferences. Push, when
# tokens are registered, is delivered on top by the scheduler job
# (features/budget/alerts.py); the inbox works with zero push infra.
# ================================================================
@budget_bp.route("/alerts", methods=["GET"])
def alerts_list():
    unread_only = bool(request.args.get("unreadOnly"))
    limit = min(_int_arg("limit") or 20, 100)
    alerts, unread_count = repo.get_alerts(unread_only=unread_only, limit=limit)
    return ok({"items": [camel_alert(a) for a in alerts]}, meta={"unreadCount": unread_count})


@budget_bp.route("/alerts/<int:alert_id>/read", methods=["POST"])
def alerts_mark_read(alert_id):
    repo.mark_alert_read(alert_id)
    return ok({"id": alert_id, "read": True})


@budget_bp.route("/alerts/prefs", methods=["GET"])
def alert_prefs_get():
    return ok(camel_alert_prefs(repo.get_alert_prefs()))


@budget_bp.route("/alerts/prefs", methods=["PATCH"])
def alert_prefs_edit():
    body = request.get_json(silent=True) or {}
    fields = {}
    for camel, snake in (
        ("dailyCheckinEnabled", "daily_checkin_enabled"), ("dailyCheckinTime", "daily_checkin_time"),
        ("billDueLeadDays", "bill_due_lead_days"), ("overBudgetEnabled", "over_budget_enabled"),
        ("overBudgetThresholdPct", "over_budget_threshold_pct"),
        ("lowDailyBudgetThreshold", "low_daily_budget_threshold"),
    ):
        if camel in body:
            fields[snake] = body[camel]
    return ok(camel_alert_prefs(repo.update_alert_prefs(**fields)))


# ================================================================
# WALLET SYNC — two-way sync against Wallet by BudgetBakers' REST API.
# Manual-trigger only, no scheduler job — see features/budget/wallet/ and
# docs/BUDGETBAKERS_API.md. sync.py's dicts are already camelCase-keyed,
# so routes return them straight through ok() without a serializer.
# ================================================================
@budget_bp.route("/sync/wallet/status", methods=["GET"])
def wallet_sync_status():
    return ok(wallet_sync.get_status())


@budget_bp.route("/sync/wallet/preview", methods=["POST"])
def wallet_sync_preview():
    """Dry run of both directions — nothing written. Always call this
    before /pull or /push against real financial data."""
    return ok(wallet_sync.preview())


# One synchronous request must finish well inside the mobile client's 20s
# abort (mobile/src/api/client.ts) and gunicorn's --timeout. The records
# pull stops at a page boundary once this budget is spent and reports
# {"records": {"hasMore": true}}; the caller re-POSTs until it's false,
# each call resuming from the persisted per-page cursor.
_SYNC_PULL_BUDGET_SECONDS = 10


@budget_bp.route("/sync/wallet/pull", methods=["POST"])
def wallet_sync_pull():
    pull = wallet_sync.pull_all(apply=True, max_seconds=_SYNC_PULL_BUDGET_SECONDS)
    return ok({"pull": pull, "summary": service.get_summary()})


@budget_bp.route("/sync/wallet/push", methods=["POST"])
def wallet_sync_push():
    return ok({"push": wallet_sync.push_all(apply=True)})


@budget_bp.route("/sync/wallet", methods=["POST"])
def wallet_sync_run():
    pull_result = wallet_sync.pull_all(apply=True, max_seconds=_SYNC_PULL_BUDGET_SECONDS)
    # While the historical backfill is still paging in, there is nothing
    # local to push yet — skip the (DB-heavy) push enumeration until the
    # pull side has fully caught up.
    push_result = None
    if not pull_result["records"].get("hasMore"):
        push_result = wallet_sync.push_all(apply=True)
    return ok({"pull": pull_result, "push": push_result, "summary": service.get_summary()})


@budget_bp.route("/sync/wallet/compare", methods=["GET"])
def wallet_sync_compare():
    return ok(wallet_sync.compare())
