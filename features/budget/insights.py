"""Pure math for the insights/graphs layer — no DB, no clock, no LLM.
Mirrors compute.py's contract: every function takes plain data and
returns plain data, so the hard parts (dense series, pace curve,
projection, top-N fold) stay unit-testable with zero DB setup.

This module must never import from db, repo, config, or call
datetime.now()/now_jkt() — every date is passed in by the caller
(service.py), which is where the clock and the DB queries live."""
import datetime

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def daily_series(rows: list, start_date: str, through_date: str) -> list:
    """One entry per calendar day from start_date through through_date
    inclusive. A real elapsed day with no transactions is filled with
    zeros, not omitted — charts need a dense series. Days after
    through_date are simply absent: through_date is caller-computed as
    min(today, period_end - 1 day), so future days never enter this
    function at all, and the chart draws a partial line against the
    full-width axis (period.totalDays) rather than flatlining to zero for
    the rest of the month."""
    by_date = {r["date"]: r for r in rows}
    start = datetime.date.fromisoformat(start_date)
    through = datetime.date.fromisoformat(through_date)
    out = []
    d = start
    while d <= through:
        key = d.isoformat()
        row = by_date.get(key)
        out.append({
            "date": key,
            "spend": row["spend"] if row else 0,
            "variableSpend": row["variable_spend"] if row else 0,
            "income": row["income"] if row else 0,
            "count": row["count"] if row else 0,
        })
        d += datetime.timedelta(days=1)
    return out


def cumulative_pace(daily: list, envelope: int, total_days: int) -> dict:
    """Cumulative actual (variable-category spend only — see daily_series'
    docstring on why fixed-category spend is excluded) vs an ideal
    straight-line pace against `envelope` (sum of variable monthlyLimit).
    aheadBy is ideal-minus-actual on the last point: negative means
    spending faster than pace."""
    ideal_per_day = round(envelope / total_days) if total_days > 0 else 0
    points = []
    running = 0
    for i, day in enumerate(daily):
        running += day["variableSpend"]
        ideal = round(envelope * (i + 1) / total_days) if total_days > 0 else 0
        points.append({"date": day["date"], "actual": running, "ideal": ideal})
    ahead_by = (points[-1]["ideal"] - points[-1]["actual"]) if points else 0
    return {"envelope": envelope, "idealPerDay": ideal_per_day, "points": points, "aheadBy": ahead_by}


def top_n_with_other(ranked: list, n: int = 4) -> list:
    """Top n by spend (already sorted desc, deterministically tie-broken
    by the SQL query), folding the rest into a synthetic 'Other' entry.
    n=4 -> at most 5 entries, matching theme.chart.sequential's 5 stops —
    the number 4 is a palette constant, encoded once here so no screen can
    disagree with another about what 'Other' contains."""
    if len(ranked) <= n:
        return [
            {"categoryId": r["category_id"], "name": r["name"] or "Uncategorized",
             "spend": r["spend"], "count": r["count"], "isOther": False}
            for r in ranked
        ]
    top = ranked[:n]
    rest = ranked[n:]
    out = [
        {"categoryId": r["category_id"], "name": r["name"] or "Uncategorized",
         "spend": r["spend"], "count": r["count"], "isOther": False}
        for r in top
    ]
    out.append({
        "categoryId": None, "name": "Other",
        "spend": sum(r["spend"] for r in rest), "count": sum(r["count"] for r in rest), "isOther": True,
    })
    return out


def budget_vs_actual(categories: list, spend_by_id: dict) -> list:
    """Every variable category that HAS a monthly limit, including ones
    with zero spend this period — a limit with no spend yet is still a
    real budget-vs-actual pair, not something to drop from the chart."""
    out = []
    for c in categories:
        limit = c.get("monthly_limit")
        if not limit:
            continue
        spent = spend_by_id.get(c["id"], 0)
        leftover = limit - spent
        out.append({
            "categoryId": c["id"], "name": c["name"], "budget": limit, "actual": spent,
            "remaining": max(leftover, 0), "overBudget": max(-leftover, 0),
            "pct": round(spent / limit, 4) if limit else 0,
        })
    return out


def project_end_balance(*, money_in_hand: int, total_still_owed: int, cumulative_spend: int,
                        elapsed_days: int, days_left: int) -> dict:
    """Straight-line run-rate projection over ALL spend (unlike the pace
    chart, which is variable-only) — this is about cash, not a budget
    envelope. Deliberately does NOT also subtract the unspent portion of
    variable budgets (already folded into total_still_owed upstream via
    still-to-be-reserved amounts): that would reserve the same future
    rupiah twice, once as "still owed" and again as "projected spend".
    elapsed_days clamped to >= 1 (day one of a period can't divide by
    zero); days_left clamped to >= 0."""
    elapsed = max(elapsed_days, 1)
    avg_daily = round(cumulative_spend / elapsed)
    projected_remaining = avg_daily * max(days_left, 0)
    return {
        "avgDailySpend": avg_daily,
        "projectedRemainingSpend": projected_remaining,
        "projectedEndBalance": money_in_hand - total_still_owed - projected_remaining,
    }


def today_allowance(*, free_money: int, days_left: int, today_spend: int) -> dict:
    """free_money already reflects today's spend (money_in_hand() is
    live), so `free_money / days_left - today_spend` would double-count.
    Reconstruct this morning's position instead: add back today's spend,
    then divide across today + days_left (days_left itself does not
    include today — see service.build_period_view)."""
    days = max(days_left, 0) + 1
    start_of_day_free = free_money + today_spend
    allowance = round(start_of_day_free / days)
    return {"allowance": allowance, "remainingToday": allowance - today_spend}


def trailing_days(daily: list, n: int = 7) -> list:
    """Last n days' spend from a dense daily series, left-padded with 0
    when the period is younger than n days so the sparkline always has a
    fixed-width input."""
    values = [d["spend"] for d in daily]
    if len(values) >= n:
        return values[-n:]
    return [0] * (n - len(values)) + values


def heatmap_cells(daily: list) -> dict:
    """One cell per elapsed day, with weekday (Monday=0..Sunday=6) so the
    client can lay out a real calendar grid instead of a single
    non-wrapping row."""
    cells = []
    max_spend = 0
    max_count = 0
    for day in daily:
        d = datetime.date.fromisoformat(day["date"])
        cells.append({
            "date": day["date"], "label": str(d.day), "weekday": d.weekday(),
            "spend": day["spend"], "count": day["count"],
        })
        max_spend = max(max_spend, day["spend"])
        max_count = max(max_count, day["count"])
    return {"cells": cells, "maxSpend": max_spend, "maxCount": max_count}


def period_label(start_date: str, end_date: str) -> str:
    """'Jul 25 - Aug 25'. Built from a fixed month-abbreviation table
    rather than strftime('%-d'...) — the no-leading-zero day flag is a
    Unix-only strftime extension and this backend also runs on Windows."""
    start = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)
    return f"{_MONTH_ABBR[start.month - 1]} {start.day} - {_MONTH_ABBR[end.month - 1]} {end.day}"


def month_label(month_key: str) -> str:
    """'Jul 2026' from a 'YYYY-MM' key."""
    year, month = month_key.split("-")
    return f"{_MONTH_ABBR[int(month) - 1]} {year}"


def month_short_label(month_key: str) -> str:
    """'Jul' from a 'YYYY-MM' key — the column chart's axis tick."""
    _year, month = month_key.split("-")
    return _MONTH_ABBR[int(month) - 1]


def period_short_label(start_date: str, end_date: str) -> str:
    """'Jul 25' from a period's start_date — the column chart's axis tick
    for period mode. Deliberately just the start day, not the full range:
    the chart's tap-to-select readout already shows period_label() in
    full when a column is selected."""
    start = datetime.date.fromisoformat(start_date)
    return f"{_MONTH_ABBR[start.month - 1]} {start.day}"


def _month_index(month_key: str) -> int:
    """'YYYY-MM' -> an absolute month count, so adjacent months are
    adjacent integers. Used for dense-filling calendar months, where
    datetime's month arithmetic has no clean 'add one month' operation
    and naive implementations mishandle year boundaries (Dec -> Jan)."""
    year, month = month_key.split("-")
    return int(year) * 12 + (int(month) - 1)


def _month_key(index: int) -> str:
    """Inverse of _month_index."""
    year, month = divmod(index, 12)
    return f"{year:04d}-{month + 1:02d}"


def shift_month(month_key: str, delta: int) -> str:
    """'YYYY-MM' + delta months, correctly crossing year boundaries —
    exposes the _month_index/_month_key round-trip for callers (service.py)
    that need to compute a window's start month from its end month, rather
    than duplicating naive date-math that gets Dec -> Jan wrong."""
    return _month_key(_month_index(month_key) + delta)


def dense_months(rows: list, through_month: str) -> list:
    """One entry per calendar month from the earliest row through
    through_month inclusive, zero-filling months with no transactions —
    same dense-series contract as daily_series() above. Without this a
    column chart draws Feb adjacent to Apr and silently claims March
    didn't exist. It also guarantees the current month is present even
    when nothing has been spent in it yet, which is what makes a partial
    (in-progress) column render at all instead of just being absent.

    rows must be oldest-first (repo.month_totals already reverses to this
    order) and each row is {"month", "spend", "income", "count"}. An
    empty `rows` returns an empty list — there is no 'earliest' to anchor
    on, and a ledger with zero history has nothing to chart."""
    if not rows:
        return []
    by_month = {r["month"]: r for r in rows}
    start_index = _month_index(rows[0]["month"])
    end_index = max(_month_index(rows[-1]["month"]), _month_index(through_month))
    out = []
    for i in range(start_index, end_index + 1):
        key = _month_key(i)
        row = by_month.get(key)
        out.append({
            "month": key,
            "spend": row["spend"] if row else 0,
            "income": row["income"] if row else 0,
            "count": row["count"] if row else 0,
        })
    return out


def dense_months_window(rows: list, from_month: str, through_month: str) -> list:
    """Zero-filled monthly series over an EXPLICIT window, unlike
    dense_months() which anchors its start on rows[0] — right for one
    aggregate series, but it would give each category a different,
    non-comparable start month here. Every category in a patterns view
    must share one x-axis. `rows` is a list of {"month", "spend"} for a
    single category, any order; empty is valid (a category with zero
    spend in the window still gets a fully-zero series)."""
    by_month = {r["month"]: r["spend"] for r in rows}
    start_index = _month_index(from_month)
    end_index = _month_index(through_month)
    return [by_month.get(_month_key(i), 0) for i in range(start_index, end_index + 1)]


def classify_pattern(series: list, *, months_active: int) -> str:
    """Spending-behavior tag for one category's dense monthly series.

    `series` must cover only COMPLETE months — the caller drops the
    current, still-accruing month before calling this, since a partial
    current month reads as a collapse against every category's norm and
    would tag the whole ledger 'falling'.

    Precedence — first match wins:
      1. 'new'        the only/first activity is in the last 2 months of
                       the window — too little history for a trend verdict
      2. 'one-off'     active in exactly 1 month of the window
      3. 'occasional'  active in fewer than half the window's months
      4. else, by trend (see below)

    Trend compares the MEAN of the last third of the window against the
    mean of the first third (k = max(2, len(series) // 3)), not the two
    endpoints — household spend is noisy, and a single one-off spike in
    the last month must not flip the verdict on its own. A window
    shorter than 4 months skips the trend comparison (a "third" is
    meaningless at that length) and returns 'recurring'. A >=25% shift
    between the two thirds is treated as a real trend, not noise."""
    n = len(series)
    if n == 0 or months_active == 0:
        return "new"

    active_indexes = [i for i, v in enumerate(series) if v > 0]
    first_active = active_indexes[0]
    if n - first_active <= 2:
        return "new"
    if months_active == 1:
        return "one-off"
    if months_active < n / 2:
        return "occasional"
    if n < 4:
        return "recurring"

    k = max(2, n // 3)
    first_mean = sum(series[:k]) / k
    last_mean = sum(series[-k:]) / k
    if first_mean == 0:
        return "rising" if last_mean > 0 else "recurring"
    change = (last_mean - first_mean) / first_mean
    if change >= 0.25:
        return "rising"
    if change <= -0.25:
        return "falling"
    return "recurring"


def category_pattern_stats(name: str, kind: str, monthly_limit, series: list, complete_series: list, count: int) -> dict:
    """Per-category summary for the patterns view. `series` is the full
    dense window (including the partial current month, for charting);
    `complete_series` excludes it (for classification and averages, so a
    half-elapsed current month doesn't drag every average down)."""
    total = sum(complete_series)
    months_active = sum(1 for v in complete_series if v > 0)
    months_in_window = len(complete_series)
    largest = max(range(len(series)), key=lambda i: series[i]) if series else None
    return {
        "name": name,
        "kind": kind,
        "monthlyLimit": monthly_limit,
        "total": total,
        "count": count,
        "avgPerMonth": round(total / months_in_window) if months_in_window else 0,
        "avgPerActiveMonth": round(total / months_active) if months_active else 0,
        "monthsActive": months_active,
        "monthsInWindow": months_in_window,
        "pattern": classify_pattern(complete_series, months_active=months_active),
        "largestMonthIndex": largest,
        "series": series,
    }
