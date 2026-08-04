"""Routes for the standalone budget feature. Registered at /api/budget in
app.py. Blueprint hooks (before_request/after_request/errorhandler) do not
inherit from api_bp, so auth/CORS/error-mapping are wired independently
here via the shared functions in api_common.py."""
from flask import Blueprint, request

from api_common import ok, err, add_cors_headers, check_auth, handle_unexpected_error
from features.budget import repo, service
from features.budget.errors import BudgetError
from features.budget.serializers import camel_budget_breakdown, camel_category, camel_seed_result, camel_transaction, camel_wallet

budget_bp = Blueprint("budget", __name__)


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
    data = service.build_period_view()
    return ok(camel_budget_breakdown(data) if data else None)


@budget_bp.route("/import/sheets", methods=["POST"])
def import_sheets():
    from features.budget.seed import seed_from_sheets

    body = request.get_json(silent=True) or {}
    force = bool(body.get("force") or request.args.get("force"))
    result = seed_from_sheets(force=force)
    return ok(camel_seed_result(result))


# ================================================================
# WALLETS / CATEGORIES — read-only lists for now, so quick-add and the
# overview screen have something to pick from. Full CRUD is Phase 2 (B2.2).
# ================================================================
@budget_bp.route("/wallets", methods=["GET"])
def wallets_list():
    wallets = repo.get_wallets()
    return ok({"items": [{**camel_wallet(w), "balance": repo.wallet_balance(w["id"])} for w in wallets]})


@budget_bp.route("/categories", methods=["GET"])
def categories_list():
    kind = request.args.get("kind")
    categories = repo.get_categories(kind=kind)
    return ok({"items": [camel_category(c) for c in categories]})


# ================================================================
# TRANSACTIONS
# ================================================================
def _int_arg(name):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    return int(raw)


@budget_bp.route("/transactions", methods=["GET"])
def transactions_list():
    limit = _int_arg("limit") or 50
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
# QUICK-ADD — single-transaction NL parse (features/budget/quickadd.py)
# ================================================================
@budget_bp.route("/transactions/parse", methods=["POST"])
def transactions_parse():
    from features.budget.quickadd import parse as quickadd_parse

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return err("VALIDATION_ERROR", "message is required.", 400)

    parsed = quickadd_parse(message)
    return ok({"parsed": {
        "amount": parsed["amount"],
        "categoryId": parsed["category_id"],
        "walletId": parsed["wallet_id"],
        "direction": parsed["direction"],
        "note": parsed["note"],
        "confidence": parsed["confidence"],
        "source": parsed["source"],
    }})


@budget_bp.route("/transactions/quick", methods=["POST"])
def transactions_quick():
    from features.budget.quickadd import parse as quickadd_parse

    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return err("VALIDATION_ERROR", "message is required.", 400)

    parsed = quickadd_parse(message)
    if parsed["amount"] is None:
        return ok({"partial": {
            "categoryId": parsed["category_id"],
            "walletId": parsed["wallet_id"],
            "note": parsed["note"],
        }}, status=422)

    txn, summary = service.create_transaction(
        amount=parsed["amount"],
        direction=parsed["direction"],
        category_id=parsed["category_id"],
        wallet_id=body.get("walletId") or parsed["wallet_id"],
        note=parsed["note"],
        source=parsed["source"],
        raw_input=message,
        occurred_at=parsed.get("occurred_at"),
    )
    return ok({
        "transaction": camel_transaction(txn),
        "parse": {"source": parsed["source"], "confidence": parsed.get("confidence")},
        "summary": summary,
    }, status=201)
