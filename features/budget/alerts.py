"""Budget alerts. evaluate_alerts() is pure — no DB, no delivery, so every
threshold is unit-testable with plain dicts. run_budget_alerts() is the
orchestration: gather from repo, evaluate, dedupe against budget_alert_log,
deliver (push, best-effort), and log every alert that fired regardless of
whether push succeeded — the in-app inbox is the primary channel, push is
on top of it, and only the in-app read state should ever suppress a repeat,
never a push failure (otherwise a broken push token would re-fire the same
alert every tick, forever)."""
import calendar
import datetime

from config import now_jkt
from database import state_get
from db import integrity_errors
from features.budget import repo


def _days_until_due_day(today: datetime.date, due_day: int) -> int:
    """Same wrap-to-next-month arithmetic as service._next_bill_due —
    duplicated rather than imported to keep this module free of any
    dependency on service.py (avoids a circular import; service.py will
    import this module for the scheduler wiring)."""
    if due_day >= today.day:
        return due_day - today.day
    next_month = today.month % 12 + 1
    next_year = today.year + (1 if today.month == 12 else 0)
    days_in_next_month = calendar.monthrange(next_year, next_month)[1]
    clamped_due_day = min(due_day, days_in_next_month)
    days_in_this_month = calendar.monthrange(today.year, today.month)[1]
    return (days_in_this_month - today.day) + clamped_due_day


def _fmt(n: int) -> str:
    return f"Rp {int(n):,}".replace(",", ".")


def evaluate_alerts(*, now: datetime.datetime, prefs: dict, view: dict, period: dict,
                    bills_due: list, category_status: list) -> list:
    """Decides what SHOULD fire right now. Returns a list of
    {kind, ref_key, title, body} — ref_key is the dedupe key
    (UNIQUE(kind, ref_key) on budget_alert_log)."""
    today = now.date()
    today_str = today.isoformat()
    alerts = []

    if prefs["daily_checkin_enabled"] and now.strftime("%H:%M") >= prefs["daily_checkin_time"]:
        alerts.append({
            "kind": "daily_checkin",
            "ref_key": today_str,
            "title": "Daily budget check-in",
            "body": f"{_fmt(view['daily_budget'])}/day left, {view['days_left']} days to payday.",
        })

    for bill in bills_due:
        if bill["due_day"] is None:
            continue
        days_until = _days_until_due_day(today, bill["due_day"])
        if days_until <= prefs["bill_due_lead_days"]:
            alerts.append({
                "kind": "bill_due",
                "ref_key": f"bill:{bill['id']}:period:{period['id']}",
                "title": f"{bill['name']} due soon",
                "body": f"{_fmt(bill['amount'])} due in {days_until} day{'s' if days_until != 1 else ''}.",
            })

    if prefs["over_budget_enabled"]:
        threshold = prefs["over_budget_threshold_pct"]
        for cat in category_status:
            if not cat.get("limit"):
                continue
            pct = (cat["spend"] / cat["limit"]) * 100
            if pct >= threshold:
                alerts.append({
                    "kind": "over_budget",
                    "ref_key": f"cat:{cat['id']}:period:{period['id']}:pct:{threshold}",
                    "title": f"{cat['name']} at {int(pct)}% of budget",
                    "body": f"Spent {_fmt(cat['spend'])} of {_fmt(cat['limit'])}.",
                })

    if view["daily_budget"] < prefs["low_daily_budget_threshold"]:
        alerts.append({
            "kind": "low_daily_budget",
            "ref_key": f"period:{period['id']}:day:{today_str}",
            "title": "Daily budget is tight",
            "body": f"Only {_fmt(view['daily_budget'])}/day left.",
        })

    return alerts


def run_budget_alerts(now=None) -> list:
    """Orchestration: gather live data, evaluate, dedupe, deliver
    (best-effort push), log. Returns the alerts that were newly logged
    this run (already-seen ref_keys are silently skipped, not returned)."""
    from features.budget.service import build_period_view, get_payroll_day
    from features.budget.periods import ensure_current_period
    from push import send_push_notification

    now = now or now_jkt()
    view = build_period_view()
    if view is None:
        return []

    period = ensure_current_period(get_payroll_day())
    prefs = repo.get_alert_prefs()
    bills_due = repo.bills_due_for_period(period["id"])

    variable = repo.get_categories(kind="variable")
    spend_rows = repo.category_spend_ranked_for_period(period["id"])
    spend_by_id = {r["category_id"]: r["spend"] for r in spend_rows}
    category_status = [
        {"id": c["id"], "name": c["name"], "limit": c["monthly_limit"], "spend": spend_by_id.get(c["id"], 0)}
        for c in variable
    ]

    candidates = evaluate_alerts(now=now, prefs=prefs, view=view, period=period,
                                 bills_due=bills_due, category_status=category_status)

    fired = []
    for alert in candidates:
        try:
            repo.create_alert_log(alert["kind"], alert["ref_key"], alert["title"], alert["body"])
        except integrity_errors():
            continue  # already fired — UNIQUE(kind, ref_key) is the dedupe guard
        delivered = send_push_notification(alert["title"], alert["body"])
        if delivered:
            repo.mark_alert_delivered(alert["kind"], alert["ref_key"])
        fired.append(alert)
    return fired
