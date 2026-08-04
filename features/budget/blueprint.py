"""Routes for the standalone budget feature. Registered at /api/budget in
app.py. Blueprint hooks (before_request/after_request/errorhandler) do not
inherit from api_bp, so auth/CORS/error-mapping are wired independently
here via the shared functions in api_common.py."""
from flask import Blueprint, request

from api_common import ok, err, add_cors_headers, check_auth, handle_unexpected_error
from features.budget import repo, service
from features.budget.errors import BudgetError
from features.budget.serializers import (
    camel_bill, camel_budget_breakdown, camel_category, camel_seed_result, camel_transaction, camel_wallet,
)

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
    if not data:
        return ok(None)
    body = camel_budget_breakdown(data)
    body["today"] = service.get_today_card()
    return ok(body)


@budget_bp.route("/insights", methods=["GET"])
def insights_view():
    return ok(service.build_insights())


@budget_bp.route("/insights/history", methods=["GET"])
def insights_history():
    periods = _int_arg("periods") or 6
    group_by = request.args.get("groupBy", "period")
    if group_by not in ("period", "month"):
        return err("VALIDATION_ERROR", "groupBy must be 'period' or 'month'.", 400)
    return ok(service.build_insights_history(periods=periods, group_by=group_by))


@budget_bp.route("/import/sheets", methods=["POST"])
def import_sheets():
    from features.budget.seed import seed_from_sheets

    body = request.get_json(silent=True) or {}
    force = bool(body.get("force") or request.args.get("force"))
    result = seed_from_sheets(force=force)
    return ok(camel_seed_result(result))


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
