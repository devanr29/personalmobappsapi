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

    scheduler.add_job(check_and_send_reminders, "interval", minutes=1,  id="reminder_check")

    # Daily quote — morning & night (Asia/Jakarta)
    scheduler.add_job(
        send_scheduled_quote, "cron",
        hour=6, minute=0,
        args=["Good Morning 🌅"],
        id="morning_quote",
    )
    scheduler.add_job(
        send_scheduled_quote, "cron",
        hour=23, minute=0,
        args=["Good Night 🌙"],
        id="night_quote",
    )
