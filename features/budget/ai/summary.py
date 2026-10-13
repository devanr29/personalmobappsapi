"""Orchestration for the AI insights card and the weekly digest: gather
the already-computed views from service.py, turn them into facts, have the
model narrate them, fall back to the facts' own text when it can't.

The summary is cached in bot_state keyed by a hash of the facts it was
written from. Facts move whenever the ledger or the day changes (elapsed
days feed the pace and projection figures), so the hash doubles as the
invalidation rule: same facts -> same card, no model call."""
import datetime
import hashlib
import json

from config import now_jkt
from database import state_get, state_set
from db import integrity_errors
from features.budget import repo
from features.budget.ai import facts as facts_mod
from features.budget.ai import llm

_CACHE_KEY = "budget_ai_summary"
# Bump to invalidate every cached summary after a prompt change.
_PROMPT_VERSION = 1
# The model sees at most this many facts — more makes an 8B model ramble
# and start merging figures.
_MAX_FACTS = 8
_RULES_BULLETS = 5

_SUMMARY_INSTRUCTION = (
    "Write 3 to 5 bullet points, one per line, each starting with '- '. "
    "First what needs attention, then what is going well, and end with one concrete "
    "suggestion for the days left until payday based on the daily budget fact. "
    "At most 25 words per bullet."
)

_DIGEST_INSTRUCTION = (
    "Write a weekly money digest for a phone notification: at most 3 short sentences, "
    "plain text, no bullets. Lead with the most important fact, then one encouraging "
    "or practical note for the coming week."
)


def _gather():
    """(insights, history, patterns) — None insights means no ledger yet.
    Imported lazily for the same reason alerts.py does: service.py may
    import this package, and the reverse import must not be at load time."""
    from features.budget import service
    insights = service.build_insights()
    if insights is None:
        return None, None, None
    history = service.build_insights_history(periods=6)
    patterns = service.build_category_patterns(months=6)
    return insights, history, patterns


def _select(all_facts: list) -> list:
    """Top facts by severity, always keeping the daily-budget fact — the
    instruction's closing suggestion is built on it."""
    chosen = all_facts[:_MAX_FACTS]
    if not any(f["key"] == "daily_budget" for f in chosen):
        daily = next((f for f in all_facts if f["key"] == "daily_budget"), None)
        if daily:
            chosen = chosen[:_MAX_FACTS - 1] + [daily]
    return chosen


def _public_fact(f):
    return {"key": f["key"], "text": f["text"], "tone": f["tone"], "severity": f["severity"]}


def build_ai_summary(refresh: bool = False):
    """{bullets, facts, generatedAt, source: 'ai'|'rules'}, or None when the
    budget isn't set up. A rules fallback is never cached, so a transient
    model outage doesn't pin the plain version until the ledger changes."""
    insights, history, patterns = _gather()
    if insights is None:
        return None
    chosen = _select(facts_mod.build_facts(insights, history, patterns))
    digest = hashlib.sha1(
        json.dumps({"v": _PROMPT_VERSION, "facts": [f["text"] for f in chosen]}).encode()
    ).hexdigest()

    if not refresh:
        cached = state_get(_CACHE_KEY)
        if cached:
            try:
                entry = json.loads(cached)
                if entry.get("hash") == digest:
                    return entry["payload"]
            except (ValueError, KeyError):
                pass

    reply = llm.narrate(chosen, _SUMMARY_INSTRUCTION)
    bullets = llm.split_bullets(reply) if reply else []
    source = "ai"
    if len(bullets) < 2:
        bullets = [f["text"] for f in chosen[:_RULES_BULLETS]]
        source = "rules"

    payload = {
        "bullets": bullets,
        "facts": [_public_fact(f) for f in chosen],
        "generatedAt": str(now_jkt()),
        "source": source,
    }
    if source == "ai":
        state_set(_CACHE_KEY, json.dumps({"hash": digest, "payload": payload}))
    return payload


def _iso_week_key(today: datetime.date) -> str:
    year, week, _ = today.isocalendar()
    return f"week:{year}-W{week:02d}"


def run_weekly_digest(now=None):
    """Scheduler job (scheduler.py, Sunday evening). Same log-then-push
    contract as alerts.run_budget_alerts: the inbox row is the primary
    channel, UNIQUE(kind, ref_key) on the ISO week makes a restart or a
    double fire a no-op, and push failure never un-logs it. Returns the
    alert dict when one was newly logged, else None."""
    from push import send_push_notification

    now = now or now_jkt()
    if not repo.get_alert_prefs()["weekly_digest_enabled"]:
        return None
    insights, history, patterns = _gather()
    if insights is None:
        return None

    chosen = facts_mod.week_facts(insights["daily"]) + facts_mod.build_facts(insights, history, patterns)[:4]
    body = llm.narrate(chosen, _DIGEST_INSTRUCTION, max_tokens=200)
    if not body:
        body = " ".join(f["text"] for f in chosen[:3])

    alert = {
        "kind": "weekly_digest", "ref_key": _iso_week_key(now.date()),
        "title": "Your weekly budget digest", "body": body,
    }
    try:
        repo.create_alert_log(alert["kind"], alert["ref_key"], alert["title"], alert["body"])
    except integrity_errors():
        return None
    if send_push_notification(alert["title"], alert["body"]):
        repo.mark_alert_delivered(alert["kind"], alert["ref_key"])
    return alert
