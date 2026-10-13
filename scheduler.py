from apscheduler.schedulers.background import BackgroundScheduler
from config import TZ_JKT

from tracer import trace
# ================================================================
# SCHEDULER INSTANCE — imported by app.py
# ================================================================
scheduler = BackgroundScheduler(timezone=TZ_JKT)

# ================================================================
# REGISTER ALL JOBS
# ================================================================
@trace
def register_jobs():
    from features.reminders import check_and_send_reminders
    from features.quotes import send_scheduled_quote
    from features.budget.alerts import run_budget_alerts

    # 5 min rather than 1: a reminder firing up to 4 minutes later than its
    # exact time is not user-visible, and this job was the single largest
    # source of background log volume (every run logs on entry/exit).
    scheduler.add_job(check_and_send_reminders, "interval", minutes=5,  id="reminder_check")

    # A polling interval, not a cron trigger: daily_checkin_time is
    # user-editable at runtime via PATCH /api/budget/alerts/prefs, and a
    # registered cron trigger would go stale the moment someone changed it.
    scheduler.add_job(run_budget_alerts, "interval", minutes=15, id="budget_alerts")

    # Quote push every 3 hours (Asia/Jakarta): 00, 03, 06, … 21.
    # The notification title is picked from the hour at fire time.
    scheduler.add_job(
        send_scheduled_quote, "cron",
        hour="*/3", minute=0,
        id="quote_3h",
    )
