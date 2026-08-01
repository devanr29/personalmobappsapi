import hmac
import json

from flask import Blueprint, request, jsonify

from config import MOBILE_API_TOKEN
from database import clear_conv_history, save_conv_turn, state_get
from ai.classifier import classify_intent
from intents import route_intent
from features.tasks import get_tasks_structured, complete_task_by_id, delete_task_by_id
from features.calendar import (
    get_events_structured,
    save_event,
    parse_event_with_ai,
    edit_event_by_id,
    delete_event_by_id,
)
from features.reminders import (
    get_reminders_structured,
    save_reminder,
    parse_reminder_with_ai,
    delete_reminder_by_id,
)
from features.notes import get_notes_structured, save_note, edit_note, delete_note
from features.ideas import get_ideas_structured, save_idea, edit_idea, delete_idea
from features.budget import compute_and_persist_budget
from features.budget_config import (
    get_fixed_expenses,
    get_variable_budgets,
    add_fixed_expense,
    edit_fixed_expense,
    remove_fixed_expense,
    add_variable_budget,
    edit_variable_budget,
    remove_variable_budget,
)
from features.quotes import get_quote_of_day
from features.news import get_news_structured, summarize_article
from ai.brainstorm import ai_brainstorm
from features.memory import semantic_search
from push import register_push_token
from tracer import logger

api_bp = Blueprint("api", __name__)


# ================================================================
# RESPONSE ENVELOPE
# ================================================================
def _ok(data, status=200):
    return jsonify({"data": data, "meta": {}}), status


def _err(code, message, status):
    return jsonify({"error": {"code": code, "message": message}, "meta": {}}), status


# ================================================================
# CORS — needed for the Expo *web* build, which runs in the browser
# at a different origin (localhost:8081) than the API. Native (Expo
# Go / device) fetches have no origin and are unaffected. Token auth
# rides in the Authorization header (not cookies), so a wildcard
# origin is safe — we're not using credentialed requests.
# ================================================================
def _add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return resp


@api_bp.after_request
def _cors(resp):
    return _add_cors_headers(resp)


# ================================================================
# AUTH — bearer token, constant-time compare (avoids a timing
# side-channel on a URL that's publicly reachable on Railway)
# ================================================================
@api_bp.before_request
def _check_auth():
    # CORS preflight carries no Authorization header — let Flask's
    # automatic OPTIONS handler answer it; after_request adds headers.
    if request.method == "OPTIONS":
        return None
    if request.path == "/api/health":
        return None
    auth  = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if not MOBILE_API_TOKEN or not hmac.compare_digest(token, MOBILE_API_TOKEN):
        return _err("UNAUTHORIZED", "Missing or invalid bearer token.", 401)


@api_bp.errorhandler(Exception)
def _handle_unexpected_error(e):
    logger.warning(f"[api] unhandled error: {e}")
    return _err("INTERNAL_ERROR", "Something went wrong.", 500)


# ================================================================
# HEALTH
# ================================================================
@api_bp.route("/health", methods=["GET"])
def health():
    return _ok({"status": "ok"})


# ================================================================
# HOME — aggregate read for the dashboard tab
# ================================================================
@api_bp.route("/home", methods=["GET"])
def home():
    events     = get_events_structured()
    snapshot   = state_get("last_budget_snapshot")
    return _ok({
        "tasks":         get_tasks_structured(),
        "nextEvent":      events[0] if events else None,
        "budgetSummary":  json.loads(snapshot) if snapshot else None,
        "reminders":      get_reminders_structured(limit=2),
        "quoteOfDay":     get_quote_of_day(),
    })


# ================================================================
# CHAT
# ================================================================
@api_bp.route("/chat", methods=["POST"])
def chat():
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return _err("VALIDATION_ERROR", "message is required.", 400)

    classified = classify_intent(message)
    intent     = classified.get("intent", "chat")
    params     = classified.get("params", {})
    result     = route_intent(intent, params, message)

    if intent != "chat" and result.get("text"):
        save_conv_turn("user", message)
        save_conv_turn("assistant", result["text"])

    return _ok(result)


@api_bp.route("/chat/reset", methods=["POST"])
def chat_reset():
    clear_conv_history()
    return _ok({"cleared": True})


# ================================================================
# TASKS
# ================================================================
@api_bp.route("/tasks", methods=["GET"])
def tasks_list():
    return _ok(get_tasks_structured())


@api_bp.route("/tasks/<task_id>/complete", methods=["PATCH"])
def tasks_complete(task_id):
    if not complete_task_by_id(task_id):
        return _err("NOT_FOUND", f"No task with id {task_id}.", 404)
    return _ok({"id": task_id, "status": "completed"})


@api_bp.route("/tasks/<task_id>", methods=["DELETE"])
def tasks_delete(task_id):
    if not delete_task_by_id(task_id):
        return _err("NOT_FOUND", f"No task with id {task_id}.", 404)
    return _ok({"id": task_id, "deleted": True})


# ================================================================
# EVENTS
# ================================================================
@api_bp.route("/events", methods=["GET"])
def events_list():
    days_raw = request.args.get("days")
    if days_raw is None:
        return _ok(get_events_structured())
    try:
        days = int(days_raw)
    except ValueError:
        return _err("VALIDATION_ERROR", "days must be an integer.", 400)
    return _ok(get_events_structured(days_ahead=days))


@api_bp.route("/events", methods=["POST"])
def events_create():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()

    if message:
        parsed = parse_event_with_ai(message)
        if parsed is None:
            return _err("VALIDATION_ERROR", "Could not parse an event from that message.", 400)
        save_event(parsed["title"], parsed["start"], parsed.get("end") or None, parsed.get("description", ""))
        return _ok({"created": True})

    title = (body.get("title") or "").strip()
    start = (body.get("start") or "").strip()
    if not title or not start:
        return _err("VALIDATION_ERROR", "message, or title and start, is required.", 400)
    save_event(title, start, body.get("end") or None, body.get("description", ""))
    return _ok({"created": True})


@api_bp.route("/events/<event_id>", methods=["PATCH"])
def events_edit(event_id):
    body = request.get_json(silent=True) or {}
    if not edit_event_by_id(
        event_id,
        title=body.get("title"),
        start=body.get("start"),
        end=body.get("end"),
        description=body.get("description"),
    ):
        return _err("NOT_FOUND", f"No event with id {event_id}.", 404)
    return _ok({"id": event_id, "updated": True})


@api_bp.route("/events/<event_id>", methods=["DELETE"])
def events_delete(event_id):
    if not delete_event_by_id(event_id):
        return _err("NOT_FOUND", f"No event with id {event_id}.", 404)
    return _ok({"id": event_id, "deleted": True})


# ================================================================
# REMINDERS — read-only structured list
# ================================================================
@api_bp.route("/reminders", methods=["GET"])
def reminders_list():
    return _ok(get_reminders_structured())


@api_bp.route("/reminders", methods=["POST"])
def reminders_create():
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()

    if message:
        content, remind_at = parse_reminder_with_ai(message)
        save_reminder(content, remind_at)
        return _ok({"created": True})

    content   = (body.get("content") or "").strip()
    remind_at = (body.get("remindAt") or "").strip()
    if not content or not remind_at:
        return _err("VALIDATION_ERROR", "message, or content and remindAt, is required.", 400)
    save_reminder(content, remind_at)
    return _ok({"created": True})


@api_bp.route("/reminders/<int:reminder_id>", methods=["DELETE"])
def reminders_delete(reminder_id):
    if not delete_reminder_by_id(reminder_id):
        return _err("NOT_FOUND", f"No reminder with id {reminder_id}.", 404)
    return _ok({"id": reminder_id, "deleted": True})


# ================================================================
# NOTES — index-addressed (Google Sheets rows have no stable id;
# clients must refetch after any mutation instead of reordering
# their local list). See features/notes.py's get_notes_structured().
# ================================================================
@api_bp.route("/notes", methods=["GET"])
def notes_list():
    return _ok(get_notes_structured(range_all=True))


@api_bp.route("/notes", methods=["POST"])
def notes_create():
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return _err("VALIDATION_ERROR", "message is required.", 400)
    save_note(message)
    return _ok({"created": True})


@api_bp.route("/notes/<int:index>", methods=["PATCH"])
def notes_edit(index):
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return _err("VALIDATION_ERROR", "message is required.", 400)
    edit_note(message, index=index)
    return _ok({"index": index, "updated": True})


@api_bp.route("/notes/<int:index>", methods=["DELETE"])
def notes_delete(index):
    result = delete_note(index=index)
    if not result.startswith("🗑️"):
        return _err("NOT_FOUND", f"No note at index {index}.", 404)
    return _ok({"index": index, "deleted": True})


# ================================================================
# IDEAS — index-addressed, same caveats as NOTES above.
# ================================================================
@api_bp.route("/ideas", methods=["GET"])
def ideas_list():
    return _ok(get_ideas_structured(range_all=True))


@api_bp.route("/ideas", methods=["POST"])
def ideas_create():
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return _err("VALIDATION_ERROR", "message is required.", 400)
    save_idea(message)
    return _ok({"created": True})


@api_bp.route("/ideas/<int:index>", methods=["PATCH"])
def ideas_edit(index):
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return _err("VALIDATION_ERROR", "message is required.", 400)
    edit_idea(message, index=index)
    return _ok({"index": index, "updated": True})


@api_bp.route("/ideas/<int:index>", methods=["DELETE"])
def ideas_delete(index):
    result = delete_idea(index=index)
    if not result.startswith("🗑️"):
        return _err("NOT_FOUND", f"No idea at index {index}.", 404)
    return _ok({"index": index, "deleted": True})


# ================================================================
# BUDGET
# ================================================================
@api_bp.route("/budget", methods=["GET"])
def budget_get():
    snapshot = state_get("last_budget_snapshot")
    return _ok(json.loads(snapshot) if snapshot else None)


@api_bp.route("/budget", methods=["POST"])
def budget_post():
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return _err("VALIDATION_ERROR", "message is required.", 400)

    data = compute_and_persist_budget(message)
    if data is None:
        return _err("VALIDATION_ERROR", "Could not parse a budget from that message.", 400)

    snapshot = state_get("last_budget_snapshot")
    return _ok(json.loads(snapshot))


def _camel_budget_breakdown(data: dict) -> dict:
    # _compute_budget() builds a snake_case dict — normalize to camelCase
    # like every other structured endpoint (get_events_structured,
    # get_notes_structured, the /api/search fix, etc.) rather than leaking
    # Python naming into the mobile client.
    return {
        "remaining": data["remaining"],
        "stillOwed": [
            {"name": e["name"], "amount": e["amount"], "dueDay": e.get("due_day")} for e in data["still_owed"]
        ],
        "pendingAmounts": [
            {"name": e["name"], "amount": e["amount"], "dueDay": e.get("due_day")} for e in data["pending_amounts"]
        ],
        "remainingVar": [
            {"name": v["name"], "remaining": v["remaining"], "spent": v["spent"], "overBudget": v["over_budget"]}
            for v in data["remaining_var"]
        ],
        "unmatchedSpending": [{"name": u["name"], "amount": u["amount"]} for u in data["unmatched_spending"]],
        "totalStillOwed": data["total_still_owed"],
        "totalVarRemaining": data["total_var_remaining"],
        "totalDeductions": data["total_deductions"],
        "freeMoney": data["free_money"],
        "dailyBudget": data["daily_budget"],
        "daysLeft": data["days_left"],
        "statusLevel": data["status_level"],
    }


@api_bp.route("/budget/breakdown", methods=["GET"])
def budget_breakdown_get():
    # Read-through only — compute_and_persist_budget() (chat's budget intent
    # or POST /api/budget above) is what refreshes this; there is no
    # standalone recompute here, since _compute_budget() needs the same
    # freeform NL message either route already requires.
    breakdown = state_get("last_budget_breakdown")
    return _ok(_camel_budget_breakdown(json.loads(breakdown)) if breakdown else None)


# ================================================================
# BUDGET CONFIG — fixed expenses & variable budgets (Google Sheets).
# Structured CRUD for the Settings UI; the chat intents in
# features/budget_config.py (handle_budget_config) still exist
# separately for NL commands and are unaffected by these routes.
# ================================================================
@api_bp.route("/budget/config", methods=["GET"])
def budget_config_get():
    fixed    = get_fixed_expenses()
    variable = get_variable_budgets()
    return _ok({
        "fixedExpenses":   [{"name": e["name"], "amount": e["amount"], "dueDay": e["due_day"]} for e in fixed],
        "variableBudgets": [{"name": v["name"], "budget": v["budget"]} for v in variable],
    })


@api_bp.route("/budget/config/fixed", methods=["POST"])
def budget_config_fixed_add():
    body   = request.get_json(silent=True) or {}
    name   = (body.get("name") or "").strip()
    amount = body.get("amount")
    if not name or not isinstance(amount, (int, float)):
        return _err("VALIDATION_ERROR", "name and amount are required.", 400)
    result = add_fixed_expense(name, int(amount), body.get("dueDay"))
    if not result.startswith("✅"):
        return _err("INTERNAL_ERROR", result, 500)
    return _ok({"created": True})


@api_bp.route("/budget/config/fixed/<string:name>", methods=["PATCH"])
def budget_config_fixed_edit(name):
    body = request.get_json(silent=True) or {}
    result = edit_fixed_expense(
        name,
        new_name=(body.get("newName") or None),
        new_amount=int(body["newAmount"]) if body.get("newAmount") is not None else None,
        new_due_day=body["newDueDay"] if "newDueDay" in body else ...,
    )
    if result.startswith("❌"):
        return _err("NOT_FOUND", result, 404)
    if not result.startswith("✏️"):
        return _err("INTERNAL_ERROR", result, 500)
    return _ok({"name": name, "updated": True})


@api_bp.route("/budget/config/fixed/<string:name>", methods=["DELETE"])
def budget_config_fixed_delete(name):
    result = remove_fixed_expense(name)
    if result.startswith("❌"):
        return _err("NOT_FOUND", result, 404)
    if not result.startswith("🗑️"):
        return _err("INTERNAL_ERROR", result, 500)
    return _ok({"name": name, "deleted": True})


@api_bp.route("/budget/config/variable", methods=["POST"])
def budget_config_variable_add():
    body   = request.get_json(silent=True) or {}
    name   = (body.get("name") or "").strip()
    budget = body.get("budget")
    if not name or not isinstance(budget, (int, float)):
        return _err("VALIDATION_ERROR", "name and budget are required.", 400)
    result = add_variable_budget(name, int(budget))
    if not result.startswith("✅"):
        return _err("INTERNAL_ERROR", result, 500)
    return _ok({"created": True})


@api_bp.route("/budget/config/variable/<string:name>", methods=["PATCH"])
def budget_config_variable_edit(name):
    body = request.get_json(silent=True) or {}
    result = edit_variable_budget(
        name,
        new_name=(body.get("newName") or None),
        new_budget=int(body["newBudget"]) if body.get("newBudget") is not None else None,
    )
    if result.startswith("❌"):
        return _err("NOT_FOUND", result, 404)
    if not result.startswith("✏️"):
        return _err("INTERNAL_ERROR", result, 500)
    return _ok({"name": name, "updated": True})


@api_bp.route("/budget/config/variable/<string:name>", methods=["DELETE"])
def budget_config_variable_delete(name):
    result = remove_variable_budget(name)
    if result.startswith("❌"):
        return _err("NOT_FOUND", result, 404)
    if not result.startswith("🗑️"):
        return _err("INTERNAL_ERROR", result, 500)
    return _ok({"name": name, "deleted": True})


# ================================================================
# NEWS
# ================================================================
@api_bp.route("/news", methods=["GET"])
def news_list():
    topic = (request.args.get("topic") or "").strip()
    if not topic:
        return _err("VALIDATION_ERROR", "topic is required.", 400)
    return _ok(get_news_structured(topic))


@api_bp.route("/news/article", methods=["GET"])
def news_article():
    url   = (request.args.get("url") or "").strip()
    title = (request.args.get("title") or "").strip()
    if not url or not title:
        return _err("VALIDATION_ERROR", "url and title are required.", 400)
    source      = request.args.get("source", "")
    published   = request.args.get("publishedAt", "")
    description = request.args.get("description", "")
    return _ok({"summary": summarize_article(title, url, source, published, description)})


# ================================================================
# BRAINSTORM
# ================================================================
@api_bp.route("/brainstorm", methods=["POST"])
def brainstorm():
    body  = request.get_json(silent=True) or {}
    topic = (body.get("topic") or "").strip()
    if not topic:
        return _err("VALIDATION_ERROR", "topic is required.", 400)
    return _ok({"text": ai_brainstorm(topic)})


# ================================================================
# SEARCH — semantic search over notes/ideas memory
# ================================================================
@api_bp.route("/search", methods=["GET"])
def search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return _err("VALIDATION_ERROR", "q is required.", 400)
    results = semantic_search(query)
    return _ok([
        {"sourceType": r["source_type"], "content": r["content"], "score": r["score"]}
        for r in results
    ])


# ================================================================
# PUSH
# ================================================================
@api_bp.route("/push/register", methods=["POST"])
def push_register():
    body  = request.get_json(silent=True) or {}
    token = (body.get("token") or "").strip()
    if not token:
        return _err("VALIDATION_ERROR", "token is required.", 400)
    register_push_token(token)
    return _ok({"registered": True})
