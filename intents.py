import re

from ai.chat import ai_chat
from ai.brainstorm import ai_brainstorm
from features.reminders import parse_reminder_with_ai, save_reminder, get_reminders_list, delete_reminder
from features.notes import save_note, get_notes, delete_note, edit_note
from features.ideas import save_idea, get_ideas, delete_idea, edit_idea
from features.tasks import save_task, get_tasks, complete_task, delete_task, edit_task
from features.calendar import (
    parse_event_with_ai, parse_date_from_message,
    save_event, get_events, delete_event, edit_event,
)
from features.news import get_news
from features.quotes import generate_daily_quote
from features.budget import compute_and_persist_budget, _format_budget, _budget_interactive_prompt
from features.budget_config import handle_budget_config
from features.memory import semantic_search
from tracer import trace


def _safe_int(value):
    """Best-effort int parse; returns None for missing/non-numeric input instead of crashing."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value):
    return {"kind": "text", "text": value, "data": None}


@trace
def route_intent(intent: str, params: dict, incoming: str) -> dict:
    """Adapted from the old WhatsApp webhook's routing logic (app.py's
    /webhook, removed in Phase 0). Returns {"kind", "text", "data"} instead
    of a bare string so the mobile Chat tab can render rich bubbles."""
    lower = incoming.lower()

    if intent == "reminder":
        content, remind_at = parse_reminder_with_ai(incoming)
        return _text(save_reminder(content, remind_at))

    elif intent == "get_reminders":
        return _text(get_reminders_list(params.get("date")))

    elif intent == "complete_task":
        keyword = params.get("keyword") or re.sub(
            r"complete task|finish task|done task|selesai task", "", lower
        ).strip(" :?!")
        return _text(complete_task(keyword))

    elif intent == "get_tasks":
        return _text(get_tasks(
            range_start=params.get("range_start"),
            range_end=params.get("range_end"),
            count=params.get("count"),
            range_all=bool(params.get("range_all")),
        ))

    elif intent == "add_task":
        content = params.get("content") or re.sub(
            r"add task|new task|tambah task|create task|task:", "", lower
        ).strip(" :?!") or incoming
        text = save_task(content)
        return {"kind": "task", "text": text, "data": {"content": content}}

    elif intent == "get_notes":
        return _text(get_notes(
            range_start=params.get("range_start"),
            range_end=params.get("range_end"),
            count=params.get("count"),
            range_all=bool(params.get("range_all")),
        ))

    elif intent == "add_note":
        content = params.get("content") or re.sub(
            r"note:|notes:|add note|save note|catatan:|catat", "", lower
        ).strip(" :?!") or incoming
        return _text(save_note(content))

    elif intent == "get_ideas":
        return _text(get_ideas(
            range_start=params.get("range_start"),
            range_end=params.get("range_end"),
            count=params.get("count"),
            range_all=bool(params.get("range_all")),
        ))

    elif intent == "add_idea":
        content = params.get("content") or re.sub(
            r"idea:|save idea|add idea|ide:|simpan ide", "", lower
        ).strip(" :?!") or incoming
        return _text(save_idea(content))

    elif intent == "news":
        topic = params.get("content") or lower
        for w in ["news", "berita", "headline", "latest", "terbaru", "about", "tentang", "get", "show", "give me"]:
            topic = topic.replace(w, "").strip(" ?!.,")
        return _text(get_news(topic or "world"))

    elif intent == "brainstorm":
        topic = params.get("content") or re.sub(
            r"brainstorm|ide|ideas?|pikir|think about|think of", "", lower
        ).strip(" :?!") or incoming
        return _text(ai_brainstorm(topic))

    elif intent == "get_events":
        date_hint = params.get("date") or parse_date_from_message(incoming)
        return _text(get_events(date_hint, incoming))

    elif intent == "add_event":
        parsed = parse_event_with_ai(incoming)
        if parsed and parsed.get("title") and parsed.get("start"):
            text = save_event(
                parsed["title"].strip(),
                parsed["start"].strip(),
                parsed["end"].strip() if parsed.get("end") else None,
                parsed.get("description", ""),
            )
        else:
            text = (
                "⚠️ Could not understand the event.\n"
                "Try: *Add event Team lunch on April 22 at 1pm*\n"
                "Or: *New event Meeting tomorrow at 3pm for 2 hours*"
            )
        return _text(text)

    elif intent == "search_memory":
        results = semantic_search(incoming, top_k=5, min_score=0.45)
        if results:
            items = [
                f"{i+1}. {r['content']} _({r['source_type']}, {round(r['score']*100)}% match)_"
                for i, r in enumerate(results)
            ]
            text = "🔍 *Found in your memory:*\n\n" + "\n".join(items)
        else:
            text = "🔍 Nothing relevant found in your notes or ideas."
        return _text(text)

    elif intent == "quote":
        context = re.sub(
            r"quote|motivate me|inspire me|motivasi|inspirasi|give me a|berikan|kasih",
            "", lower
        ).strip(" :?!")
        return {"kind": "quote", "text": generate_daily_quote(context), "data": None}

    elif intent == "budget":
        data = compute_and_persist_budget(incoming)
        if data is None:
            return _text(_budget_interactive_prompt())
        text = _format_budget(data)
        # Line items that sum to total_deductions (same set _format_budget's
        # "Total deductions" summary lists) so the chat bubble can show what
        # the total is actually made of, not just the number.
        deduction_breakdown = (
            [{"name": e["name"], "amount": e["amount"]} for e in data["still_owed"]]
            + [{"name": e["name"], "amount": e["amount"]} for e in data["pending_amounts"]]
            + [{"name": v["name"], "amount": v["remaining"]} for v in data["remaining_var"]]
        )
        return {
            "kind": "budget",
            "text": text,
            "data": {
                "remaining":           data["remaining"],
                "deductions":          data["total_deductions"],
                "free":                data["free_money"],
                "dailyBudget":         data["daily_budget"],
                "daysToPayday":        data["days_left"],
                "statusLevel":         data["status_level"],
                "deductionBreakdown":  deduction_breakdown,
            },
        }

    elif intent == "budget_config":
        return _text(handle_budget_config(incoming))

    elif intent == "delete_note":
        idx = params.get("index")
        kw  = params.get("keyword") or params.get("content")
        return _text(delete_note(keyword=kw, index=_safe_int(idx)))

    elif intent == "edit_note":
        idx         = params.get("index")
        kw          = params.get("keyword")
        new_content = params.get("content") or ""
        return _text(edit_note(new_content, keyword=kw, index=_safe_int(idx)))

    elif intent == "delete_idea":
        idx = params.get("index")
        kw  = params.get("keyword") or params.get("content")
        return _text(delete_idea(keyword=kw, index=_safe_int(idx)))

    elif intent == "edit_idea":
        idx         = params.get("index")
        kw          = params.get("keyword")
        new_content = params.get("content") or ""
        return _text(edit_idea(new_content, keyword=kw, index=_safe_int(idx)))

    elif intent == "delete_task":
        idx = params.get("index")
        kw  = params.get("keyword") or params.get("content")
        return _text(delete_task(keyword=kw, index=_safe_int(idx)))

    elif intent == "edit_task":
        idx       = params.get("index")
        kw        = params.get("keyword")
        new_title = params.get("content") or ""
        return _text(edit_task(new_title, keyword=kw, index=_safe_int(idx)))

    elif intent == "delete_event":
        kw = params.get("keyword") or params.get("content") or incoming
        return _text(delete_event(kw))

    elif intent == "edit_event":
        kw     = params.get("keyword") or ""
        parsed = parse_event_with_ai(incoming)
        return _text(edit_event(
            keyword=kw,
            new_title=parsed.get("title") if parsed else None,
            new_start=parsed.get("start") if parsed else None,
            new_end=parsed.get("end") if parsed else None,
            new_description=parsed.get("description") if parsed else None,
        ))

    elif intent == "delete_reminder":
        kw = params.get("keyword") or params.get("content") or incoming
        return _text(delete_reminder(kw))

    else:
        return _text(ai_chat(incoming))
