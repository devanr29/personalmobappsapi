"""Pure fact extraction for the AI layer — no DB, no clock, no LLM, same
contract as insights.py. Every function takes the dicts service.py already
builds (build_insights / build_insights_history / build_category_patterns)
and returns facts:

    {"key": str, "text": str, "severity": 0..3, "tone": "good"|"watch"|"bad"|"info"}

`text` is a finished sentence with every number already computed and
formatted here. The model downstream (llm.py) only chooses and rephrases
facts — an 8B model is not trusted with arithmetic on someone's money, and
llm.numbers_grounded() rejects any reply quoting a figure not in a fact."""

# A category counts as spiking when its spend so far this period is at
# least this multiple of what it usually is by the same point...
SPIKE_RATIO = 1.5
# ...and the excess is at least this many rupiah, so a Rp 5.000 category
# doubling to Rp 10.000 isn't reported as an anomaly.
SPIKE_MIN_EXCESS = 50_000
# Spend-to-date this far above/below the usual pace is worth a mention.
PACE_DEVIATION = 0.15


def fmt_rp(n) -> str:
    """'Rp 150.000' / 'Rp -150.000' — the one rupiah formatter shared by
    alerts.py and the AI layer, so a figure the model quotes from a fact
    is character-identical to the one the alert inbox shows."""
    return f"Rp {int(n):,}".replace(",", ".")


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _fact(key, text, severity, tone):
    return {"key": key, "text": text, "severity": severity, "tone": tone}


def category_spikes(categories: list, patterns: dict, elapsed_days: int, total_days: int) -> list:
    """Categories whose spend so far this period is well above their usual
    spend by this point. `categories` is build_insights()['categories'];
    `patterns` is build_category_patterns(). The usual figure is the
    category's average per complete calendar month scaled by the period's
    elapsed fraction — an approximation (pay periods aren't calendar
    months), which is why the ratio and the rupiah floor are both
    deliberately conservative. Categories with fewer than two active
    months have no 'usual' yet and are skipped."""
    if total_days <= 0 or not patterns:
        return []
    usual_by_id = {
        c["categoryId"]: c["avgPerMonth"]
        for c in patterns.get("categories", [])
        if c["monthsActive"] >= 2 and c["avgPerMonth"] > 0
    }
    fraction = min(max(elapsed_days, 1) / total_days, 1)
    spikes = []
    for c in categories:
        usual_month = usual_by_id.get(c["categoryId"])
        if not usual_month:
            continue
        expected = round(usual_month * fraction)
        if expected <= 0:
            continue
        excess = c["spend"] - expected
        if c["spend"] >= expected * SPIKE_RATIO and excess >= SPIKE_MIN_EXCESS:
            spikes.append({
                "categoryId": c["categoryId"], "name": c["name"], "spend": c["spend"],
                "expected": expected, "excess": excess, "ratio": round(c["spend"] / expected, 1),
            })
    spikes.sort(key=lambda s: -s["excess"])
    return spikes


def build_facts(insights: dict, history: dict = None, patterns: dict = None) -> list:
    """Every fact worth knowing about the current period, most severe
    first (stable within a severity, so ordering is deterministic)."""
    if not insights:
        return []
    stats = insights["stats"]
    period = insights["period"]
    pace = insights["pace"]
    facts = []

    projected = stats["projectedEndBalance"]
    if projected < 0:
        facts.append(_fact(
            "projection",
            f"At the current average of {fmt_rp(stats['avgDailySpend'])}/day, the period is projected "
            f"to end {fmt_rp(-projected)} short before payday.",
            3, "bad",
        ))
    else:
        facts.append(_fact(
            "projection",
            f"At the current average of {fmt_rp(stats['avgDailySpend'])}/day, the period is projected "
            f"to end with {fmt_rp(projected)} to spare.",
            1, "good",
        ))

    if pace["envelope"] > 0 and pace["points"]:
        ahead_by = pace["aheadBy"]
        if ahead_by < 0:
            facts.append(_fact(
                "pace",
                f"Variable spending is {fmt_rp(-ahead_by)} ahead of the even pace for the "
                f"{fmt_rp(pace['envelope'])} variable budget.",
                2, "bad",
            ))
        elif ahead_by > 0:
            facts.append(_fact(
                "pace",
                f"Variable spending is {fmt_rp(ahead_by)} under the even pace for the "
                f"{fmt_rp(pace['envelope'])} variable budget.",
                1, "good",
            ))

    for b in insights["budgetVsActual"]:
        if b["overBudget"] > 0:
            facts.append(_fact(
                f"over:{b['categoryId']}",
                f"{b['name']} is over budget by {fmt_rp(b['overBudget'])} "
                f"({fmt_rp(b['actual'])} spent of {fmt_rp(b['budget'])}).",
                3, "bad",
            ))
        elif b["pct"] >= 0.8:
            facts.append(_fact(
                f"near:{b['categoryId']}",
                f"{b['name']} has used {_pct(b['pct'])} of its {fmt_rp(b['budget'])} budget, "
                f"{fmt_rp(b['remaining'])} left.",
                2, "watch",
            ))

    if stats["todayRemaining"] < 0:
        facts.append(_fact(
            "today",
            f"Today's spending is {fmt_rp(-stats['todayRemaining'])} over today's allowance of "
            f"{fmt_rp(stats['todayAllowance'])}.",
            2, "watch",
        ))
    else:
        facts.append(_fact(
            "today",
            f"{fmt_rp(stats['todayRemaining'])} is left of today's {fmt_rp(stats['todayAllowance'])} allowance.",
            0, "info",
        ))

    facts.append(_fact(
        "daily_budget",
        f"From tomorrow the daily budget is {fmt_rp(stats['dailyBudget'])} for "
        f"{period['daysLeft']} days until payday.",
        2 if stats["dailyBudget"] < 0 else 1,
        "bad" if stats["dailyBudget"] < 0 else "info",
    ))

    if history and history.get("averageSpend") and period["totalDays"] > 0:
        average = history["averageSpend"]
        expected = round(average * period["elapsedDays"] / period["totalDays"])
        diff = stats["spendToDate"] - expected
        if expected > 0 and diff > expected * PACE_DEVIATION:
            facts.append(_fact(
                "vs_usual",
                f"Spending so far ({fmt_rp(stats['spendToDate'])}) is {fmt_rp(diff)} above the usual "
                f"{fmt_rp(expected)} by this point in a period (average period: {fmt_rp(average)}).",
                2, "watch",
            ))
        elif expected > 0 and -diff > expected * PACE_DEVIATION:
            facts.append(_fact(
                "vs_usual",
                f"Spending so far ({fmt_rp(stats['spendToDate'])}) is {fmt_rp(-diff)} below the usual "
                f"{fmt_rp(expected)} by this point in a period (average period: {fmt_rp(average)}).",
                1, "good",
            ))

    for s in category_spikes(insights["categories"], patterns, period["elapsedDays"], period["totalDays"]):
        facts.append(_fact(
            f"spike:{s['categoryId']}",
            f"{s['name']} is at {fmt_rp(s['spend'])} so far, versus a usual {fmt_rp(s['expected'])} "
            f"by this point ({s['ratio']}x normal).",
            2, "watch",
        ))

    top = insights["categories"][0] if insights["categories"] else None
    if top and top["spend"] > 0:
        dominant = top["share"] >= 0.4
        facts.append(_fact(
            "top_category",
            f"{top['name']} is the biggest category at {_pct(top['share'])} of spending "
            f"({fmt_rp(top['spend'])}).",
            1 if dominant else 0, "watch" if dominant else "info",
        ))

    largest = stats.get("largestExpense")
    if largest:
        facts.append(_fact(
            "largest_expense",
            f"The largest single expense this period is {largest['name'] or 'an expense'} at "
            f"{fmt_rp(largest['amount'])}.",
            0, "info",
        ))

    facts.sort(key=lambda f: -f["severity"])
    return facts


def week_facts(daily: list) -> list:
    """Last-7-days spend from build_insights()['daily'], compared with the
    7 days before when the period is old enough to have them. Only covers
    the current period's days — a digest on day 3 of a period says 'since
    payday', not 'this week'."""
    if not daily:
        return []
    last = daily[-7:]
    spend = sum(d["spend"] for d in last)
    if len(daily) < 7:
        return [_fact("week", f"{fmt_rp(spend)} spent since payday ({len(daily)} days).", 1, "info")]
    facts = [_fact("week", f"{fmt_rp(spend)} spent in the last 7 days.", 1, "info")]
    if len(daily) >= 14:
        prev = sum(d["spend"] for d in daily[-14:-7])
        if prev > 0:
            diff = spend - prev
            direction = "more" if diff > 0 else "less"
            facts.append(_fact(
                "week_vs_prev",
                f"That is {fmt_rp(abs(diff))} {direction} than the 7 days before ({fmt_rp(prev)}).",
                2 if diff > prev * PACE_DEVIATION else 1, "watch" if diff > 0 else "good",
            ))
    return facts
