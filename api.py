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
from features.quotes import get_quote_of_day
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
