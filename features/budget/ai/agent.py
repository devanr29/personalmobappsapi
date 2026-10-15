"""Free-form budget questions answered by a Gemini tool-calling loop.

The model gets read-only tools over the ledger (TOOLS below) plus a
calculator, calls whatever it needs, then answers. Two guarantees hold
regardless of what the model does:

1. read-only — every tool wraps a repo/service getter; nothing that writes
   is reachable from here (tests/test_budget_ai_agent.py checks the ledger
   is unchanged after every tool runs).
2. grounded numbers — the reply may only quote figures that appeared in a
   tool result, a calculate() result or the question itself
   (llm.ungrounded_figures). One corrective round is allowed; after that,
   or on any error, timeout or round limit, answer() returns None and
   qa.py falls back to the fixed query menu."""
import ast
import datetime
import json
import operator
import re
import time

from google.genai import types

from config import MODEL_BUDGET_AGENT, MODEL_FALLBACK, gemini_client, now_jkt
from features.budget import repo
from features.budget.ai import llm
from tracer import logger

MAX_ROUNDS = 6
DEADLINE_SECONDS = 45
_MAX_ROWS = 50
# Transactions scanned per lookup before filtering/aggregating in Python —
# a period is ~100-200 rows, so this only bites on unbounded date ranges.
_SCAN_ROWS = 2000
_MAX_EXPR_CHARS = 300

_SYSTEM_PROMPT = """You answer questions about one person's personal budget in Indonesia.
Today is {today}. Money is Indonesian Rupiah; write amounts like Rp 150.000.

Use the tools to look up whatever data the question needs, then answer.
Rules:
- Every number you state must come from a tool result, or from the calculate tool.
  Never do arithmetic in your head: call calculate for any sum, difference, product,
  average or percentage, then quote its result.
- Never invent transactions, categories, merchants or amounts.
- If the data can't answer the question, say what it does show.
- When a question involves assumptions (e.g. whether today counts), state the one you used.
- Reply in the language the question is asked in. 1 to 4 short sentences, warm and direct,
  no preamble, no markdown headings."""

_CORRECTION = (
    "Your answer quoted figures that appear in no tool result: {bad}. "
    "Use the calculate tool for any derived number and quote only tool results. "
    "Answer the question again."
)


# ================================================================
# calculator
# ================================================================
_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"round": round, "min": min, "max": max, "abs": abs}


def calculate(expression: str):
    """Arithmetic on numbers only, via the AST — no names, attributes or
    calls beyond round/min/max/abs. Raises ValueError on anything else."""
    if not isinstance(expression, str) or len(expression) > _MAX_EXPR_CHARS:
        raise ValueError("expression must be a string of at most 300 characters")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("exponent too large")
            return _BINOPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in _FUNCS and not node.keywords:
            return _FUNCS[node.func.id](*(ev(a) for a in node.args))
        raise ValueError("only numbers, + - * / // % **, parentheses and round/min/max/abs are allowed")

    try:
        tree = ast.parse(expression.replace("_", ""), mode="eval")
    except SyntaxError:
        raise ValueError("not a valid arithmetic expression")
    result = ev(tree)
    if isinstance(result, float):
        result = round(result, 4)
        if result.is_integer():
            result = int(result)
    return result


# ================================================================
# tools
# ================================================================
class _Context:
    """Lazily built service data shared by every tool call in one answer."""

    def __init__(self, view=None):
        from features.budget import service
        self._service = service
        self._view = view
        self._insights = None
        self._history = None

    @property
    def view(self):
        if self._view is None:
            self._view = self._service.build_period_view()
        return self._view

    @property
    def insights(self):
        if self._insights is None:
            self._insights = self._service.build_insights()
        return self._insights

    def history(self, periods=12, group_by="period"):
        if group_by == "period" and periods == 12:
            if self._history is None:
                self._history = self._service.build_insights_history(periods=12)
            return self._history
        return self._service.build_insights_history(periods=periods, group_by=group_by)

    def period(self, period):
        """'current' / 'previous' / a periodId -> that period's history row."""
        rows = self.history()["periods"]
        if period in (None, "", "current"):
            return next((r for r in rows if r["isCurrent"]), None) or \
                {"periodId": self.view["period_id"], "label": "current"}
        if period == "previous":
            earlier = [r for r in rows if not r["isCurrent"]]
            if not earlier:
                raise ValueError("there is no previous period")
            return earlier[-1]
        try:
            pid = int(period)
        except (TypeError, ValueError):
            raise ValueError("period must be 'current', 'previous' or a periodId from get_period_history")
        row = next((r for r in rows if r["periodId"] == pid), None)
        if row is None:
            raise ValueError(f"no period with periodId {pid} in the last 12 periods")
        return row


def _day_end(date_to):
    return f"{date_to} 23:59:59" if date_to and len(date_to) == 10 else date_to


def _scan_transactions(ctx, period=None, date_from=None, date_to=None, direction="expense"):
    """(rows, period label or None, truncated) — period is ignored when a
    date range is given."""
    period_id, label = None, None
    if not (date_from or date_to):
        p = ctx.period(period)
        period_id, label = p["periodId"], p.get("label")
    rows, total = repo.get_transactions(
        period_id=period_id, direction=None if direction in (None, "any") else direction,
        date_from=date_from or None, date_to=_day_end(date_to) or None, limit=_SCAN_ROWS,
    )
    return rows, label, total > len(rows)


def _txn_out(t):
    return {"date": t["occurred_at"], "amount": t["amount"], "direction": t["direction"],
            "category": t["category_name"] or "Uncategorized", "wallet": t["wallet_name"],
            "note": t["note"]}


def tool_get_budget_overview(ctx):
    view, ins = ctx.view, ctx.insights
    stats, period = ins["stats"], ins["period"]
    return {
        "today": now_jkt().date().isoformat(),
        "period": {k: period[k] for k in ("id", "label", "startDate", "endDate", "totalDays",
                                           "elapsedDays", "daysLeft", "payrollDay")},
        "moneyInHand": stats["moneyInHand"],
        "billsStillOwed": [{"name": e["name"], "amount": e["amount"], "dueDay": e.get("due_day")}
                           for e in view["still_owed"] + view["pending_amounts"]],
        "totalStillOwed": view["total_still_owed"],
        "variableBudgetsRemaining": [
            {"name": v["name"], "limit": v.get("limit"), "spent": v["spent"], "remaining": v["remaining"]}
            for v in view["remaining_var"]
        ],
        "totalVariableBudgetRemaining": view["total_var_remaining"],
        "freeMoney": stats["freeMoney"],
        "dailyBudget": stats["dailyBudget"],
        "todayAllowance": stats["todayAllowance"],
        "todaySpent": stats["todayAllowance"] - stats["todayRemaining"],
        "todayRemaining": stats["todayRemaining"],
        "spendToDate": stats["spendToDate"],
        "avgDailySpend": stats["avgDailySpend"],
        "notes": [
            "freeMoney = moneyInHand - totalStillOwed - totalVariableBudgetRemaining: money not yet "
            "reserved for anything. todaySpent is ALREADY deducted from it; never add todayRemaining "
            "or todayAllowance back to it.",
            "daysLeft counts the days from tomorrow up to the day before payday (endDate); today is "
            "not included. dailyBudget = freeMoney / daysLeft.",
            "Spending X per day until payday leaves freeMoney - X * daysLeft (today excluded). If today "
            "also counts as an X day, further subtract max(X - todaySpent, 0).",
            "spendToDate and avgDailySpend include bills and large one-off payments, so avgDailySpend "
            "is not a typical day's spending.",
        ],
    }


def tool_list_transactions(ctx, period=None, date_from=None, date_to=None, direction="expense",
                           category=None, search=None, sort="date", limit=20):
    rows, label, truncated = _scan_transactions(ctx, period, date_from, date_to, direction)
    if category:
        wanted = category.lower()
        rows = [t for t in rows if wanted in (t["category_name"] or "Uncategorized").lower()]
    if search:
        wanted = search.lower()
        rows = [t for t in rows
                if any(wanted in (t[k] or "").lower() for k in ("note", "category_name", "wallet_name"))]
    if sort == "amount":
        rows = sorted(rows, key=lambda t: -t["amount"])
    limit = max(1, min(int(limit or 20), _MAX_ROWS))
    return {
        "period": label, "dateFrom": date_from, "dateTo": date_to,
        "matched": len(rows), "totalAmount": sum(t["amount"] for t in rows),
        "returned": min(limit, len(rows)), "scanTruncated": truncated,
        "transactions": [_txn_out(t) for t in rows[:limit]],
    }


def tool_get_category_spend(ctx, period=None, date_from=None, date_to=None):
    rows, label, truncated = _scan_transactions(ctx, period, date_from, date_to, "expense")
    totals = {}
    for t in rows:
        name = t["category_name"] or "Uncategorized"
        spend, count = totals.get(name, (0, 0))
        totals[name] = (spend + t["amount"], count + 1)
    limits = {c["name"]: c["monthly_limit"] for c in repo.get_categories() if c["monthly_limit"]}
    ranked = sorted(totals.items(), key=lambda kv: -kv[1][0])
    return {
        "period": label, "dateFrom": date_from, "dateTo": date_to, "scanTruncated": truncated,
        "totalSpend": sum(s for s, _ in totals.values()),
        "categories": [
            {"name": name, "spend": spend, "count": count, "budgetLimit": limits.get(name)}
            for name, (spend, count) in ranked[:_MAX_ROWS]
        ],
    }


def tool_get_period_history(ctx, periods=6, group_by="period"):
    periods = max(1, min(int(periods or 6), 12))
    if group_by not in ("period", "month"):
        group_by = "period"
    h = ctx.history(periods=periods, group_by=group_by)
    keys = ("periodId", "label", "startDate", "endDate", "spend", "income", "net", "count", "isCurrent")
    return {
        "groupBy": group_by,
        "periods": [{k: r.get(k) for k in keys} for r in h["periods"]],
        "averageSpendPerCompletePeriod": h.get("averageSpend"),
    }


def tool_get_bills(ctx):
    paid = repo.get_paid_bill_ids(ctx.view["period_id"])
    return {"bills": [
        {"name": b["name"], "amount": b["amount"], "dueDay": b["due_day"], "cadence": b["cadence"],
         "paidThisPeriod": b["id"] in paid}
        for b in repo.get_bills()
    ]}


def tool_get_goals(ctx):
    return {"goals": [
        {"name": g["name"], "targetAmount": g["target_amount"], "saved": repo.goal_saved(g["id"]),
         "targetDate": g.get("target_date"), "kind": g.get("kind")}
        for g in repo.get_goals()
    ]}


def tool_get_wallets(ctx):
    return {"wallets": [
        {"name": w["name"], "kind": w["kind"], "balance": w["balance"],
         "spendable": w["spendable"]}
        for w in ctx.view["wallets"] if not w.get("archived")
    ]}


def tool_calculate(ctx, expression=""):
    return {"expression": expression, "result": calculate(expression)}


_PERIOD_ARG = {"type": "string", "description": "'current' (default), 'previous', or a periodId from get_period_history. Ignored when dateFrom/dateTo is given."}
_DATE_FROM = {"type": "string", "description": "Inclusive start date YYYY-MM-DD."}
_DATE_TO = {"type": "string", "description": "Inclusive end date YYYY-MM-DD."}

# name -> (function, description, JSON-schema properties); argument names
# are camelCase in the schema and mapped to the functions' snake_case.
TOOLS = {
    "get_budget_overview": (
        tool_get_budget_overview,
        "Current pay period snapshot: dates and days left to payday, money in hand, bills still owed, "
        "remaining variable budgets, free money, daily budget, today's allowance and spending. "
        "Start here for any 'how much left / can I afford / until payday' question.",
        {},
    ),
    "list_transactions": (
        tool_list_transactions,
        "Transactions matching filters, with the total count and total amount of ALL matches "
        "(the list itself is capped at 50).",
        {
            "period": _PERIOD_ARG, "dateFrom": _DATE_FROM, "dateTo": _DATE_TO,
            "direction": {"type": "string", "enum": ["expense", "income", "transfer", "any"],
                          "description": "Default 'expense'."},
            "category": {"type": "string", "description": "Case-insensitive substring of the category name."},
            "search": {"type": "string", "description": "Case-insensitive text in note, category or wallet."},
            "sort": {"type": "string", "enum": ["date", "amount"], "description": "Newest first, or largest first."},
            "limit": {"type": "integer", "description": "Rows to return, 1-50 (default 20)."},
        },
    ),
    "get_category_spend": (
        tool_get_category_spend,
        "Expense totals per category for a period or date range, largest first, with each "
        "category's budget limit when it has one.",
        {"period": _PERIOD_ARG, "dateFrom": _DATE_FROM, "dateTo": _DATE_TO},
    ),
    "get_period_history": (
        tool_get_period_history,
        "Spend, income and net per pay period (or calendar month), oldest first, including periodIds.",
        {"periods": {"type": "integer", "description": "How many, 1-12 (default 6)."},
         "groupBy": {"type": "string", "enum": ["period", "month"]}},
    ),
    "get_bills": (tool_get_bills, "All active fixed bills and whether each is paid this period.", {}),
    "get_goals": (tool_get_goals, "Savings goals with target and amount saved.", {}),
    "get_wallets": (tool_get_wallets, "Wallet/account balances and whether each counts as spendable.", {}),
    "calculate": (
        tool_calculate,
        "Exact arithmetic. Use it for EVERY derived number. Supports + - * / // % ** parentheses "
        "and round/min/max/abs, e.g. '827195 - 80000 * 9'.",
        {"expression": {"type": "string"}},
    ),
}

_TOOL_DECLARATIONS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name=name, description=desc,
        parameters_json_schema={"type": "object", "properties": props},
    )
    for name, (_, desc, props) in TOOLS.items()
])


def _snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def run_tool(name, args, ctx):
    """A tool's result, or {'error': ...} — errors go back to the model
    rather than ending the answer, so it can retry with better arguments."""
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    fn = TOOLS[name][0]
    try:
        return fn(ctx, **{_snake(k): v for k, v in (args or {}).items()})
    except (TypeError, ValueError) as e:
        return {"error": str(e)}
    except Exception as e:
        logger.warning(f"budget agent tool {name} failed: {e}")
        return {"error": "lookup failed"}


# ================================================================
# grounding
# ================================================================
def _collect_numbers(value, money: set, pct: set):
    """Every number anywhere in a tool result. A fraction like 0.35 also
    allows '35%'; any number is allowed as a percentage too, since
    calculate() results are often already percentages."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        money.add(round(abs(value)))
        pct.add(abs(value))
        if abs(value) <= 1:
            pct.add(abs(value) * 100)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_numbers(v, money, pct)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _collect_numbers(v, money, pct)


def _question_numbers(question: str, money: set, pct: set):
    from features.budget.ai.qa import parse_amount
    exact, short, percents = llm.extract_figures(question)
    money.update(exact + short)
    pct.update(percents)
    amount = parse_amount(question)
    if amount:
        money.add(amount)
    money.update(int(re.sub(r"[.,]", "", n)) for n in re.findall(r"\d[\d.,]*", question)
                 if re.sub(r"[.,]", "", n))


# ================================================================
# loop
# ================================================================
def _generate(contents, config, model=MODEL_BUDGET_AGENT):
    """The one Gemini call — a seam tests replace."""
    return gemini_client.models.generate_content(model=model, contents=contents, config=config)


def _rate_limited(e) -> bool:
    return getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e)


def _summary(name, args, result):
    if "error" in result:
        return f"{name}: error — {result['error']}"
    if name == "calculate":
        return f"{result['expression']} = {result['result']}"
    shown = ", ".join(f"{k}={v}" for k, v in (args or {}).items())
    return f"Looked up {name}({shown})"


def answer(question: str, view=None):
    """{answer, query, facts, tools, source: 'ai'}, or None when the agent
    couldn't produce a grounded answer (caller falls back)."""
    ctx = _Context(view)
    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_PROMPT.format(today=now_jkt().strftime("%A %Y-%m-%d")),
        tools=[_TOOL_DECLARATIONS],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        thinking_config=types.ThinkingConfig(thinking_level="low"),
        temperature=0.2,
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]
    money, pct = set(), set()
    _question_numbers(question, money, pct)
    trace = []
    corrected = False
    started = time.monotonic()
    model = MODEL_BUDGET_AGENT

    try:
        for _ in range(MAX_ROUNDS + 1):
            if time.monotonic() - started > DEADLINE_SECONDS:
                logger.warning("budget agent: deadline reached")
                return None
            try:
                response = _generate(contents, config, model)
            except Exception as e:
                # The free tier allows only a few requests a minute per model;
                # the lighter model has its own quota, so finish on it.
                if not _rate_limited(e) or model == MODEL_FALLBACK:
                    raise
                logger.warning(f"budget agent: {model} rate-limited, switching to {MODEL_FALLBACK}")
                model = MODEL_FALLBACK
                response = _generate(contents, config, model)
            calls = response.function_calls or []
            if response.candidates and response.candidates[0].content:
                contents.append(response.candidates[0].content)

            if not calls:
                reply = (response.text or "").strip()
                if not reply:
                    return None
                bad = llm.ungrounded_figures(reply, money, pct)
                if not bad:
                    return {
                        "answer": reply,
                        "query": {"query": "agent", "category": None, "amount": None},
                        "facts": [{"key": f"tool:{i}:{t['name']}", "text": t["summary"]}
                                  for i, t in enumerate(trace)],
                        "tools": [{"name": t["name"], "args": t["args"]} for t in trace],
                        "model": model,
                        "source": "ai",
                    }
                logger.warning(f"budget agent reply ungrounded {bad}: {reply!r}")
                if corrected:
                    return None
                corrected = True
                contents.append(types.Content(role="user", parts=[types.Part.from_text(
                    text=_CORRECTION.format(bad=", ".join(str(b) for b in bad)))]))
                continue

            parts = []
            for call in calls:
                args = dict(call.args or {})
                result = run_tool(call.name, args, ctx)
                _collect_numbers(result, money, pct)
                trace.append({"name": call.name, "args": args, "summary": _summary(call.name, args, result)})
                parts.append(types.Part.from_function_response(
                    name=call.name, response={"result": json.loads(json.dumps(result, default=str))}))
            contents.append(types.Content(role="user", parts=parts))
    except Exception as e:
        logger.warning(f"budget agent failed: {e}")
        return None

    logger.warning("budget agent: round limit reached")
    return None
