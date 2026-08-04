"""Pay-cycle math: days-to-payday and period boundaries around a monthly
payroll day. Pure date arithmetic — no DB access except ensure_current_period,
which is the one function that reads/writes budget_periods."""
import calendar
import datetime

from config import now_jkt
from db import db_conn


def days_to_payday(today: int, payroll_day: int, days_in_month: int) -> int:
    """Same month-length-aware formula as the original features/budget.py's
    _compute_budget (features/budget.py:90-94) — carried over verbatim so
    the daily-budget number doesn't shift on extraction."""
    if today <= payroll_day:
        return payroll_day - today
    return (days_in_month - today) + payroll_day


def _clamp_day(year: int, month: int, day: int) -> int:
    """Payroll day 31 in a 30-day month becomes that month's last day."""
    last_day = calendar.monthrange(year, month)[1]
    return min(day, last_day)


def period_bounds(now: datetime.date, payroll_day: int) -> tuple[str, str]:
    """Returns (start_date, end_date) as 'YYYY-MM-DD' strings for the pay
    period containing `now`. A period runs [payroll_day, next payroll_day),
    e.g. [25th, next 25th)."""
    if now.day >= payroll_day:
        start_year, start_month = now.year, now.month
    elif now.month == 1:
        start_year, start_month = now.year - 1, 12
    else:
        start_year, start_month = now.year, now.month - 1

    if start_month == 12:
        end_year, end_month = start_year + 1, 1
    else:
        end_year, end_month = start_year, start_month + 1

    start_day = _clamp_day(start_year, start_month, payroll_day)
    end_day = _clamp_day(end_year, end_month, payroll_day)

    start = datetime.date(start_year, start_month, start_day)
    end = datetime.date(end_year, end_month, end_day)
    return start.isoformat(), end.isoformat()


def ensure_current_period(payroll_day: int, expected_income: int = 0, conn=None):
    """Fetch the budget_periods row covering today, creating it if absent.
    Returns a dict of the row. Accepts a caller-owned `conn` so callers
    that need this alongside several other budget reads (build_period_view)
    can share one connection instead of paying a separate round-trip
    per lookup — see repo.py's module docstring for why that matters
    against a remote DB."""
    now = now_jkt().date()
    start_date, end_date = period_bounds(now, payroll_day)

    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    row = conn.execute(
        "SELECT id, start_date, end_date, payroll_day, expected_income, opening_balance, closed_at "
        "FROM budget_periods WHERE start_date = ?",
        (start_date,),
    ).fetchone()

    if row is None:
        conn.execute(
            "INSERT INTO budget_periods (start_date, end_date, payroll_day, expected_income) "
            "VALUES (?, ?, ?, ?)",
            (start_date, end_date, payroll_day, expected_income),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, start_date, end_date, payroll_day, expected_income, opening_balance, closed_at "
            "FROM budget_periods WHERE start_date = ?",
            (start_date,),
        ).fetchone()
    if owns_conn:
        conn.close()

    return {
        "id": row[0],
        "start_date": row[1],
        "end_date": row[2],
        "payroll_day": row[3],
        "expected_income": row[4],
        "opening_balance": row[5],
        "closed_at": row[6],
    }
