import contextvars
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, request

from database import clear_conv_history, save_conv_turn
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
from features.budget.service import get_summary as get_budget_summary
from features.quotes import get_quote_of_day
from features.news import get_news_structured, summarize_article
from ai.brainstorm import ai_brainstorm
from features.memory import semantic_search
from push import register_push_token
from tracer import logger
from api_common import ok as _ok, err as _err, add_cors_headers as _add_cors_headers, check_auth as _http_check_auth, handle_unexpected_error as _http_handle_unexpected_error, start_timer as _http_start_timer, log_timing as _http_log_timing

api_bp = Blueprint("api", __name__)


@api_bp.before_request
def _start_timer():
    _http_start_timer()


@api_bp.after_request
def _log_timing(resp):
    return _http_log_timing(resp)


@api_bp.after_request
def _cors(resp):
    return _add_cors_headers(resp)


@api_bp.before_request
def _check_auth():
    return _http_check_auth(exempt_paths={"/api/health"})


@api_bp.errorhandler(Exception)
def _handle_unexpected_error(e):
    return _http_handle_unexpected_error(e, tag="api")


# ================================================================
# HEALTH
# ================================================================
@api_bp.route("/health", methods=["GET"])
def health():
    return _ok({"status": "ok"})


# ================================================================
# HOME — aggregate read for the dashboard tab. The 5 sources below don't
# depend on each other or on Flask's `request`, so they run concurrently
# instead of one-after-another — this used to be 2 live Google API calls
# (Calendar, Tasks — neither cached) plus a ~9-round-trip budget summary
# plus a reminders query plus a quote lookup, strictly sequential in one
# handler; wall time was the SUM of all five. A small pool is plenty —
# this is I/O-bound waiting, not CPU work, and the pool is scoped to a
# single request (`with` closes it once every result is collected).
# ================================================================
def _submit_with_context(executor, fn, *args, **kwargs):
    """ThreadPoolExecutor.submit() does not propagate contextvars to the
    worker thread on its own (unlike asyncio) — without this, every
    @trace log line from these 5 calls would show trace_id '-' instead of
    the request's actual id, breaking the /logs correlation Phase 1 of
    this fix was making useful again."""
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)


@api_bp.route("/home", methods=["GET"])
def home():
    with ThreadPoolExecutor(max_workers=5) as executor:
        events_future    = _submit_with_context(executor, get_events_structured)
        tasks_future     = _submit_with_context(executor, get_tasks_structured)
        budget_future    = _submit_with_context(executor, get_budget_summary)
        reminders_future = _submit_with_context(executor, get_reminders_structured, limit=2)
        quote_future     = _submit_with_context(executor, get_quote_of_day)

        events = events_future.result()
        return _ok({
            "tasks":         tasks_future.result(),
            "nextEvent":      events[0] if events else None,
            "budgetSummary":  budget_future.result(),
            "reminders":      reminders_future.result(),
            "quoteOfDay":     quote_future.result(),
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
