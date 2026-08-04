import re, json, calendar as _calendar
from config import now_jkt, PAYROLL_DAY
from database import state_set
from features.budget_config import get_fixed_expenses, get_variable_budgets
from features.budget.compute import compute_budget
from features.budget.periods import days_to_payday
from ai.groq_client import groq_complete
from tracer import trace


# ================================================================
# AI BUDGET INPUT PARSER
# ================================================================
@trace
def _parse_budget_input(user_input: str) -> dict | None:
    now   = now_jkt()
    today = now.day
    month = now.strftime("%B")
    year  = now.year
    fixed_expenses  = get_fixed_expenses()
    variable_budgets = get_variable_budgets()
    fixed_names    = ", ".join(e["name"] for e in fixed_expenses)
    variable_names = ", ".join(v["name"] for v in variable_budgets)

    prompt = f"""You are a budget parser for a personal finance chatbot. Today is the {today}th of {month} {year}.

The user has these fixed monthly expenses: {fixed_names}
The user has these variable monthly budgets: {variable_names}

Extract:
1. "remaining_money": total money right now (integer IDR)
2. "paid_fixed": list of fixed expense names already paid this month
3. "spent_variable": dict of variable budget name → amount spent
4. "pending_conditional": list of conditional expense names still expected this month

Reply ONLY with valid JSON, no markdown:
{{"remaining_money": <int or null>, "paid_fixed": [<names>], "spent_variable": {{"<name>": <amount>}}, "pending_conditional": [<names>]}}

User message: {user_input}"""

    try:
        raw = groq_complete(
            system_prompt="You are a budget parser. Reply with valid JSON only.",
            user_prompt=prompt,
            max_tokens=300,
            temperature=0.0,
        )
        raw = re.sub(r"```json|```", "", raw).strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[Budget parse error] {e}")
        return None

# ================================================================
# INTERACTIVE PROMPT (when no numbers given)
# ================================================================
@trace
def _budget_interactive_prompt() -> str:
    now       = now_jkt()
    today     = now.day
    days_left = (PAYROLL_DAY - today) if today < PAYROLL_DAY else (31 - today + PAYROLL_DAY)
    fixed_expenses   = get_fixed_expenses()
    variable_budgets = get_variable_budgets()
    lines = [
        f"💰 *Budget Calculator* — {days_left} days until payday (25th)\n",
        "Please tell me:",
        "1️⃣ How much money do you have right now?",
        "2️⃣ Which fixed expenses have you already paid?",
        f"   Options: {', '.join(e['name'] for e in fixed_expenses)}",
        "3️⃣ How much have you spent from variable budgets?",
        f"   Options: {', '.join(v['name'] for v in variable_budgets)}",
        "4️⃣ Any conditional expenses still pending? (e.g. Internet)",
        "",
        "💡 *Example:*",
        "\"I have 2.500.000. Already paid: Rent, Zakat, House Maintenance.",
        "Spent: Ticket 300k, Fuel 35k, Laundry 35k. Internet still pending.\"",
    ]
    return "\n".join(lines)

# ================================================================
# COMPUTE — thin wrapper around the pure features.budget.compute module.
# Handles the bare-trigger short-circuit, the LLM parse of the freeform
# message, and gathering Sheets-backed config, then delegates all the
# actual math to compute_budget() (used by chat text output, the
# persisted Home snapshot, and the REST API alike).
# ================================================================
@trace
def _compute_budget(user_input: str) -> dict | None:
    """Returns the full budget breakdown as a dict, or None if the input
    was a bare trigger phrase or couldn't be parsed (caller should fall
    back to _budget_interactive_prompt() in either case)."""
    now = now_jkt()
    days_left = days_to_payday(now.day, PAYROLL_DAY, _calendar.monthrange(now.year, now.month)[1])

    bare_triggers = {"budget", "hitung budget", "kalkulasi budget", "budget calculator",
                     "budget harian", "sisa budget", "budget check"}
    if user_input.strip().lower() in bare_triggers:
        return None

    parsed = _parse_budget_input(user_input)
    if not parsed or parsed.get("remaining_money") is None:
        return None

    return compute_budget(
        days_left=days_left,
        remaining_money=parsed.get("remaining_money", 0),
        fixed_expenses=get_fixed_expenses(),
        variable_budgets=get_variable_budgets(),
        paid_fixed=parsed.get("paid_fixed"),
        spent_variable=parsed.get("spent_variable"),
        pending_conditional=parsed.get("pending_conditional"),
    )

# ================================================================
# FORMAT — turns a _compute_budget() dict into the chat-facing string
# ================================================================
@trace
def _format_budget(data: dict) -> str:
    def fmt(n):
        return f"Rp {int(n):,}".replace(",", ".")

    remaining           = data["remaining"]
    still_owed          = data["still_owed"]
    pending_amounts     = data["pending_amounts"]
    remaining_var       = data["remaining_var"]
    unmatched_spending  = data["unmatched_spending"]
    total_still_owed    = data["total_still_owed"]
    total_var_remaining = data["total_var_remaining"]
    total_deductions    = data["total_deductions"]
    free_money          = data["free_money"]
    daily_budget        = data["daily_budget"]
    days_left           = data["days_left"]

    lines = [f"💰 *Budget Breakdown* — {days_left} days to payday (25th)\n"]
    lines.append(f"💵 Current money: *{fmt(remaining)}*\n")

    if still_owed or pending_amounts:
        lines.append("📋 *Fixed expenses still to pay:*")
        for e in still_owed:
            lines.append(f"  • {e['name']}: {fmt(e['amount'])}")
        for e in pending_amounts:
            lines.append(f"  • {e['name']} (pending): {fmt(e['amount'])}")
        lines.append(f"  ➤ Total: {fmt(total_still_owed)}\n")

    if remaining_var:
        lines.append("🗂️ *Remaining variable budgets:*")
        for v in remaining_var:
            if v["over_budget"] > 0:
                lines.append(f"  • {v['name']}: ⚠️ over by {fmt(v['over_budget'])} (spent {fmt(v['spent'])})")
            else:
                lines.append(f"  • {v['name']}: {fmt(v['remaining'])} (spent {fmt(v['spent'])})")
        lines.append(f"  ➤ Total: {fmt(total_var_remaining)}\n")

    if unmatched_spending:
        lines.append("🔸 *Spent but not tracked as a budget category:*")
        for item in unmatched_spending:
            lines.append(f"  • {item['name']}: {fmt(item['amount'])}")
        lines.append(
            "  _Not counted in Total deductions below — your current money already reflects this "
            'spend. Say "add variable <name> <amount>" if you want it tracked going forward._\n'
        )

    lines.append("📊 *Summary:*")
    lines.append(f"  Money in hand:      {fmt(remaining)}")
    lines.append(f"  Total deductions:   -{fmt(total_deductions)}")
    for e in still_owed:
        lines.append(f"    - {e['name']}: {fmt(e['amount'])}")
    for e in pending_amounts:
        lines.append(f"    - {e['name']} (pending): {fmt(e['amount'])}")
    for v in remaining_var:
        lines.append(f"    - {v['name']} (remaining): {fmt(v['remaining'])}")
    lines.append(f"  Free money left:    {fmt(free_money)}")
    lines.append(f"  Days until payday:  {days_left} days\n")

    if daily_budget < 0:
        lines.append(f"⚠️ *You're short by {fmt(abs(free_money))}!*")
        lines.append("Consider reducing variable spending.")
    else:
        lines.append(f"✅ *Daily budget: {fmt(daily_budget)}/day*")
        if daily_budget < 50_000:
            lines.append("⚠️ Tight! Keep non-essentials minimal.")
        elif daily_budget < 100_000:
            lines.append("🟡 Manageable. Watch your spending.")
        else:
            lines.append("🟢 You're in a comfortable position!")

    return "\n".join(lines)

# ================================================================
# MAIN CALCULATOR — thin wrapper, unchanged output
# ================================================================
@trace
def calculate_budget(user_input: str) -> str:
    data = _compute_budget(user_input)
    if data is None:
        return _budget_interactive_prompt()
    return _format_budget(data)

# ================================================================
# COMPUTE + PERSIST — used by the budget intent and the mobile
# REST API so Home's Budget card survives between chat turns
# ================================================================
@trace
def compute_and_persist_budget(user_input: str) -> dict | None:
    data = _compute_budget(user_input)
    if data is None:
        return None
    snapshot = {
        "remaining":     data["remaining"],
        "deductions":    data["total_deductions"],
        "free":          data["free_money"],
        "dailyBudget":   data["daily_budget"],
        "daysToPayday":  data["days_left"],
        "statusLevel":   data["status_level"],
        "computedAt":    str(now_jkt()),
    }
    state_set("last_budget_snapshot", json.dumps(snapshot))
    # Full breakdown (still_owed, remaining_var, unmatched_spending, ...) for
    # the mobile app's Budget screen — the flattened snapshot above only
    # carries the 7 summary fields GET /api/budget has always returned.
    state_set("last_budget_breakdown", json.dumps(data))
    return data
