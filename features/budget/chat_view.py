"""Chat-facing view over the budget ledger. Read-only: formats a
build_period_view() dict (features/budget/service.py) into the text and
{kind, text, data} payload the chat intent returns. No LLM, no Sheets,
no writes — those all lived in the old whole-state parser this module
replaced, which is why this file imports nothing beyond stdlib."""
from tracer import trace


@trace
def format_budget_text(data: dict) -> str:
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
            'spend._\n'
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


def build_chat_budget_payload(data: dict) -> dict:
    """The {kind:'budget', text, data} body the chat 'budget' intent
    returns. Line items sum to total_deductions so the bubble can explain
    the number, not just show it."""
    deduction_breakdown = (
        [{"name": e["name"], "amount": e["amount"]} for e in data["still_owed"]]
        + [{"name": e["name"], "amount": e["amount"]} for e in data["pending_amounts"]]
        + [{"name": v["name"], "amount": v["remaining"]} for v in data["remaining_var"]]
    )
    return {
        "kind": "budget",
        "text": format_budget_text(data),
        "data": {
            "remaining":          data["remaining"],
            "deductions":         data["total_deductions"],
            "free":               data["free_money"],
            "dailyBudget":        int(data["daily_budget"]),
            "daysToPayday":       data["days_left"],
            "statusLevel":        data["status_level"],
            "deductionBreakdown": deduction_breakdown,
        },
    }
