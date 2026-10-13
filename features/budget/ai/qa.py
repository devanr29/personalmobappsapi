"""Free-form budget questions, answered from the ledger. Three steps:

1. plan    — the model maps the question onto ONE entry of a fixed query
             menu (_QUERIES) as JSON. Nothing on the menu writes, so the
             feature is read-only by construction, not by prompt.
2. execute — plain Python runs that query against repo/service and
             returns facts (facts.py's shape) with every number computed.
3. answer  — llm.narrate() phrases the facts as a reply to the question,
             under the same number-grounding guard as the insights card.

An unparseable plan falls back to 'overview' (the insights facts), and a
failed or ungrounded answer falls back to the facts' text."""
import difflib
import json
import re

from ai.groq_client import groq_complete
from features.budget import repo
from features.budget.ai import facts as facts_mod
from features.budget.ai import llm
from features.budget.ai.facts import fmt_rp
from tracer import logger

_QUERIES = {
    "category_spend": "spend in one category, this period and last period (needs category)",
    "period_compare": "total spending this period so far vs previous periods",
    "can_afford": "whether a purchase fits the budget and what it does to the daily budget (needs amount)",
    "top_categories": "which categories take the most money this period",
    "largest_expenses": "the biggest individual expenses this period",
    "daily_allowance": "how much can be spent today / per day until payday",
    "bill_status": "fixed bills still to pay and the next one due",
    "goal_progress": "progress on savings goals",
    "overview": "general 'how am I doing' questions, or anything else about the budget",
}

_PLAN_PROMPT = """Map a personal-budget question to exactly one query.

Queries:
{menu}

Reply ONLY with JSON, no markdown:
{{"query": "<one query name>", "category": "<category name or null>", "amount": <integer rupiah or null>}}

Amounts are Indonesian Rupiah: "500k" or "500rb" = 500000, "1.5jt" or "1,5 juta" = 1500000.

Question: {question}"""

_ANSWER_INSTRUCTION = (
    'Answer this question in 1 to 3 short sentences: "{question}". '
    "Use only the FACTS. If they don't fully answer it, say what they do show."
)

_MAX_LIST = 5

_AMOUNT = re.compile(r"(?i)(?:rp\.?\s*)?(\d+(?:[.,]\d+)*)\s*(k|rb|ribu|jt|juta)?\b")


def parse_amount(text: str):
    """First rupiah amount in `text` as an int, or None. Deterministic so a
    what-if never depends on the model's arithmetic: '500k' -> 500000,
    '1,5 juta' -> 1500000, 'Rp 250.000' -> 250000. Bare numbers under
    1000 without a unit ('2 days') are not amounts."""
    for m in _AMOUNT.finditer(text):
        number, unit = m.group(1), (m.group(2) or "").lower()
        if unit:
            value = float(number.replace(".", "").replace(",", ".") if "," in number else number)
            return round(value * (1_000_000 if unit in ("jt", "juta") else 1_000))
        value = int(re.sub(r"[.,]", "", number))
        if value >= 1000:
            return value
    return None


def plan(question: str) -> dict:
    """{query, category, amount}; 'overview' when the model's reply isn't
    usable. The amount is re-parsed from the question itself whenever one
    is present there — the model's number is only a last resort."""
    menu = "\n".join(f"  {name} — {desc}" for name, desc in _QUERIES.items())
    result = {"query": "overview", "category": None, "amount": None}
    try:
        raw = groq_complete(
            system_prompt="You are a query router. Always reply with valid JSON only.",
            user_prompt=_PLAN_PROMPT.format(menu=menu, question=question),
            max_tokens=128,
            temperature=0.0,
        )
        parsed = json.loads(re.sub(r"```json|```", "", raw).strip())
        if parsed.get("query") in _QUERIES:
            result["query"] = parsed["query"]
        if isinstance(parsed.get("category"), str) and parsed["category"].strip():
            result["category"] = parsed["category"].strip()
        if isinstance(parsed.get("amount"), (int, float)) and parsed["amount"] > 0:
            result["amount"] = int(parsed["amount"])
    except Exception as e:
        logger.warning(f"budget qa plan failed: {e}")
    result["amount"] = parse_amount(question) or result["amount"]
    return result


def _fact(key, text):
    return {"key": key, "text": text, "severity": 1, "tone": "info"}


def _match_category(name: str, categories: list):
    """Exact, then substring, then fuzzy match on category name."""
    if not name:
        return None
    wanted = name.lower()
    by_name = {c["name"].lower(): c for c in categories}
    if wanted in by_name:
        return by_name[wanted]
    for key, c in by_name.items():
        if wanted in key or key in wanted:
            return c
    close = difflib.get_close_matches(wanted, by_name.keys(), n=1, cutoff=0.6)
    return by_name[close[0]] if close else None


def _previous_period_id(current_id):
    rows = repo.period_totals(limit=2)
    earlier = [r for r in rows if r["period_id"] != current_id]
    return earlier[-1]["period_id"] if earlier else None


def _q_category_spend(p, view, insights, history, patterns):
    category = _match_category(p["category"], repo.get_categories())
    if category is None:
        names = ", ".join(c["name"] for c in repo.get_categories()[:12])
        return [_fact("no_category", f"No budget category matches '{p['category'] or 'that'}'. "
                                     f"Categories include: {names}.")]
    out = []
    for label, period_id in (("this period", view["period_id"]),
                             ("last period", _previous_period_id(view["period_id"]))):
        if period_id is None:
            continue
        row = next((r for r in repo.category_spend_ranked_for_period(period_id) if r["category_id"] == category["id"]), None)
        spend, count = (row["spend"], row["count"]) if row else (0, 0)
        out.append(_fact(f"cat:{label}", f"{category['name']}: {fmt_rp(spend)} spent {label} "
                                         f"across {count} transaction{'s' if count != 1 else ''}."))
    if category["monthly_limit"]:
        out.append(_fact("cat:limit", f"{category['name']} has a budget of {fmt_rp(category['monthly_limit'])} per period."))
    pattern = next((c for c in (patterns or {}).get("categories", []) if c["categoryId"] == category["id"]), None)
    if pattern and pattern["avgPerMonth"]:
        out.append(_fact("cat:avg", f"{category['name']} averages {fmt_rp(pattern['avgPerMonth'])} per month."))
    return out


def _q_period_compare(p, view, insights, history, patterns):
    out = [_fact("ptd", f"{fmt_rp(insights['stats']['spendToDate'])} spent so far this period "
                        f"({insights['period']['elapsedDays']} of {insights['period']['totalDays']} days).")]
    complete = [i for i in history["periods"] if not i["isCurrent"]]
    if complete:
        last = complete[-1]
        out.append(_fact("last", f"Last period ({last['label']}) total spending was {fmt_rp(last['spend'])}."))
    if history["averageSpend"]:
        out.append(_fact("avg", f"The average full period is {fmt_rp(history['averageSpend'])}."))
    return out + [f for f in facts_mod.build_facts(insights, history, patterns) if f["key"] == "vs_usual"]


def _q_can_afford(p, view, insights, history, patterns):
    amount = p["amount"]
    if not amount:
        return [_fact("no_amount", "No amount was given to check against the budget.")]
    free = int(view["free_money"])
    days = view["days_left"]
    after = free - amount
    out = [
        _fact("free", f"Free money after all bills and budgets is {fmt_rp(free)}."),
        _fact("after", f"After spending {fmt_rp(amount)}, free money would be {fmt_rp(after)}."),
    ]
    if days > 0:
        out.append(_fact("daily", f"The daily budget would go from {fmt_rp(round(free / days))} "
                                  f"to {fmt_rp(round(after / days))} for the {days} days until payday."))
    if after < 0:
        out.append(_fact("short", f"That is {fmt_rp(-after)} more than the free money available."))
    return out


def _q_top_categories(p, view, insights, history, patterns):
    return [
        _fact(f"top:{i}", f"{c['name']}: {fmt_rp(c['spend'])} ({round(c['share'] * 100)}% of spending this period).")
        for i, c in enumerate(insights["categories"][:_MAX_LIST])
    ] or [_fact("none", "No expenses recorded this period yet.")]


def _q_largest_expenses(p, view, insights, history, patterns):
    txns, _ = repo.get_transactions(period_id=view["period_id"], direction="expense", limit=500)
    txns.sort(key=lambda t: -t["amount"])
    return [
        _fact(f"big:{t['id']}", f"{fmt_rp(t['amount'])} on {t['occurred_at'][:10]}"
                                f"{' — ' + t['note'] if t['note'] else ''}"
                                f"{' (' + t['category_name'] + ')' if t['category_name'] else ''}.")
        for t in txns[:_MAX_LIST]
    ] or [_fact("none", "No expenses recorded this period yet.")]


def _q_daily_allowance(p, view, insights, history, patterns):
    stats = insights["stats"]
    return [
        _fact("today", f"Today's allowance is {fmt_rp(stats['todayAllowance'])}, "
                       f"with {fmt_rp(stats['todayRemaining'])} of it left."),
        _fact("daily", f"From tomorrow the daily budget is {fmt_rp(stats['dailyBudget'])} "
                       f"for {insights['period']['daysLeft']} days until payday."),
        _fact("free", f"Free money after all bills and budgets is {fmt_rp(stats['freeMoney'])}."),
    ]


def _q_bill_status(p, view, insights, history, patterns):
    owed = view["still_owed"] + view["pending_amounts"]
    if not owed:
        return [_fact("bills", "Every fixed bill for this period is paid.")]
    out = [_fact(f"bill:{i}", f"{e['name']}: {fmt_rp(e['amount'])} still to pay.") for i, e in enumerate(owed)]
    out.append(_fact("bills_total", f"Total still owed is {fmt_rp(view['total_still_owed'])}."))
    return out


def _q_goal_progress(p, view, insights, history, patterns):
    goals = repo.get_goals()
    if not goals:
        return [_fact("goals", "No savings goals are set up.")]
    out = []
    for g in goals:
        saved = repo.goal_saved(g["id"])
        pct = round(saved / g["target_amount"] * 100) if g["target_amount"] else 0
        out.append(_fact(f"goal:{g['id']}", f"{g['name']}: {fmt_rp(saved)} saved of {fmt_rp(g['target_amount'])} ({pct}%)."))
    return out


def _q_overview(p, view, insights, history, patterns):
    return facts_mod.build_facts(insights, history, patterns)[:6]


_EXECUTORS = {
    "category_spend": _q_category_spend, "period_compare": _q_period_compare,
    "can_afford": _q_can_afford, "top_categories": _q_top_categories,
    "largest_expenses": _q_largest_expenses, "daily_allowance": _q_daily_allowance,
    "bill_status": _q_bill_status, "goal_progress": _q_goal_progress, "overview": _q_overview,
}


def answer(question: str):
    """{answer, query, facts, source: 'ai'|'rules'}, or None when the
    budget isn't set up."""
    from features.budget import service

    view = service.build_period_view()
    if view is None:
        return None
    insights = service.build_insights()
    history = service.build_insights_history(periods=6)
    patterns = service.build_category_patterns(months=6)

    p = plan(question)
    result_facts = _EXECUTORS[p["query"]](p, view, insights, history, patterns)

    reply = llm.narrate(result_facts, _ANSWER_INSTRUCTION.format(question=question.replace('"', "'")),
                        max_tokens=250)
    return {
        "answer": reply or "\n".join(f["text"] for f in result_facts),
        "query": p,
        "facts": [{"key": f["key"], "text": f["text"]} for f in result_facts],
        "source": "ai" if reply else "rules",
    }
