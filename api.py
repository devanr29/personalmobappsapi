import hmac
import json

from flask import Blueprint, request, jsonify

from config import MOBILE_API_TOKEN
from database import clear_conv_history, save_conv_turn, state_get
from ai.classifier import classify_intent
from intents import route_intent
from features.tasks import get_tasks_structured, complete_task_by_id, delete_task_by_id
from features.calendar import get_events_structured
from features.reminders import get_reminders_structured
from features.notes import get_notes_structured
from features.ideas import get_ideas_structured
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
# EVENTS / REMINDERS / NOTES / IDEAS — read-only structured lists
# ================================================================
@api_bp.route("/events", methods=["GET"])
def events_list():
    return _ok(get_events_structured())


@api_bp.route("/reminders", methods=["GET"])
def reminders_list():
    return _ok(get_reminders_structured())


@api_bp.route("/notes", methods=["GET"])
def notes_list():
    return _ok(get_notes_structured(range_all=True))


@api_bp.route("/ideas", methods=["GET"])
def ideas_list():
    return _ok(get_ideas_structured(range_all=True))


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
