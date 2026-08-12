"""Pure-function coverage for evaluate_alerts() (no DB, no clock) plus
DB-backed coverage for run_budget_alerts() (dedupe, delivery marking)."""
import datetime
import importlib

import pytest

from features.budget.alerts import evaluate_alerts

DEFAULT_PREFS = {
    "daily_checkin_enabled": True, "daily_checkin_time": "20:00",
    "bill_due_lead_days": 2, "over_budget_enabled": True,
    "over_budget_threshold_pct": 80, "low_daily_budget_threshold": 50_000,
}
DEFAULT_VIEW = {"daily_budget": 100_000, "days_left": 10}
DEFAULT_PERIOD = {"id": 7, "start_date": "2026-07-25", "end_date": "2026-08-25"}


def _run(**overrides):
    kwargs = dict(
        now=datetime.datetime(2026, 8, 3, 21, 0),
        prefs=DEFAULT_PREFS, view=DEFAULT_VIEW, period=DEFAULT_PERIOD,
        bills_due=[], category_status=[],
    )
    kwargs.update(overrides)
    return evaluate_alerts(**kwargs)


# ================================================================
# daily_checkin
# ================================================================
def test_daily_checkin_fires_after_configured_time():
    alerts = _run(now=datetime.datetime(2026, 8, 3, 21, 0))
    kinds = [a["kind"] for a in alerts]
    assert "daily_checkin" in kinds


def test_daily_checkin_does_not_fire_before_configured_time():
    alerts = _run(now=datetime.datetime(2026, 8, 3, 10, 0))
    kinds = [a["kind"] for a in alerts]
    assert "daily_checkin" not in kinds


def test_daily_checkin_disabled_never_fires():
    prefs = {**DEFAULT_PREFS, "daily_checkin_enabled": False}
    alerts = _run(now=datetime.datetime(2026, 8, 3, 21, 0), prefs=prefs)
    assert "daily_checkin" not in [a["kind"] for a in alerts]


def test_daily_checkin_ref_key_is_the_date():
    alerts = _run(now=datetime.datetime(2026, 8, 3, 21, 0))
    checkin = next(a for a in alerts if a["kind"] == "daily_checkin")
    assert checkin["ref_key"] == "2026-08-03"


# ================================================================
# bill_due
# ================================================================
def test_bill_due_fires_within_lead_days():
    bills = [{"id": 1, "name": "House Rent", "amount": 955_000, "due_day": 25}]
    alerts = _run(now=datetime.datetime(2026, 8, 23, 10, 0), bills_due=bills)
    bill_alerts = [a for a in alerts if a["kind"] == "bill_due"]
    assert len(bill_alerts) == 1
    assert bill_alerts[0]["ref_key"] == "bill:1:period:7"


def test_bill_due_does_not_fire_outside_lead_days():
    bills = [{"id": 1, "name": "House Rent", "amount": 955_000, "due_day": 25}]
    alerts = _run(now=datetime.datetime(2026, 8, 1, 10, 0), bills_due=bills)
    assert not [a for a in alerts if a["kind"] == "bill_due"]


def test_bill_due_skips_bills_with_no_due_day():
    bills = [{"id": 1, "name": "Internet", "amount": 150_000, "due_day": None}]
    alerts = _run(bills_due=bills)
    assert not [a for a in alerts if a["kind"] == "bill_due"]


def test_bill_due_wraps_to_next_month():
    # today is the 30th, due_day is 5 -> wraps forward
    bills = [{"id": 1, "name": "Water", "amount": 50_000, "due_day": 5}]
    alerts = _run(now=datetime.datetime(2026, 8, 30, 10, 0), bills_due=bills)
    assert not [a for a in alerts if a["kind"] == "bill_due"]  # far outside lead_days=2


# ================================================================
# over_budget
# ================================================================
def test_over_budget_fires_at_threshold():
    categories = [{"id": 1, "name": "Fuel", "limit": 100_000, "spend": 85_000}]
    alerts = _run(category_status=categories)
    over = [a for a in alerts if a["kind"] == "over_budget"]
    assert len(over) == 1
    assert over[0]["ref_key"] == "cat:1:period:7:pct:80"


def test_over_budget_does_not_fire_below_threshold():
    categories = [{"id": 1, "name": "Fuel", "limit": 100_000, "spend": 50_000}]
    alerts = _run(category_status=categories)
    assert not [a for a in alerts if a["kind"] == "over_budget"]


def test_over_budget_skips_categories_with_no_limit():
    categories = [{"id": 1, "name": "Misc", "limit": None, "spend": 50_000}]
    alerts = _run(category_status=categories)
    assert not [a for a in alerts if a["kind"] == "over_budget"]


def test_over_budget_disabled_never_fires():
    prefs = {**DEFAULT_PREFS, "over_budget_enabled": False}
    categories = [{"id": 1, "name": "Fuel", "limit": 100_000, "spend": 99_000}]
    alerts = _run(prefs=prefs, category_status=categories)
    assert not [a for a in alerts if a["kind"] == "over_budget"]


def test_over_budget_ref_key_includes_threshold_so_raising_it_rearms():
    categories = [{"id": 1, "name": "Fuel", "limit": 100_000, "spend": 85_000}]
    at_80 = _run(category_status=categories)
    prefs_90 = {**DEFAULT_PREFS, "over_budget_threshold_pct": 90}
    at_90 = _run(prefs=prefs_90, category_status=[{"id": 1, "name": "Fuel", "limit": 100_000, "spend": 95_000}])
    ref_80 = next(a["ref_key"] for a in at_80 if a["kind"] == "over_budget")
    ref_90 = next(a["ref_key"] for a in at_90 if a["kind"] == "over_budget")
    assert ref_80 != ref_90


# ================================================================
# low_daily_budget
# ================================================================
def test_low_daily_budget_fires_below_threshold():
    view = {"daily_budget": 30_000, "days_left": 10}
    alerts = _run(view=view)
    assert "low_daily_budget" in [a["kind"] for a in alerts]


def test_low_daily_budget_does_not_fire_above_threshold():
    view = {"daily_budget": 80_000, "days_left": 10}
    alerts = _run(view=view)
    assert "low_daily_budget" not in [a["kind"] for a in alerts]


# ================================================================
# run_budget_alerts — DB-backed
# ================================================================
@pytest.fixture
def budget_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATABASE_URL", "")

    import db as db_module
    import database as database_module
    import features.budget.schema as schema_module
    import features.budget.repo as repo_module
    import features.budget.periods as periods_module
    import features.budget.compute as compute_module
    import features.budget.service as service_module
    import features.budget.alerts as alerts_module
    modules = (db_module, schema_module, database_module, repo_module,
               periods_module, compute_module, service_module, alerts_module)
    for m in modules:
        importlib.reload(m)

    database_module.init_db()
    yield alerts_module, service_module, repo_module

    for m in modules:
        importlib.reload(m)


def test_run_budget_alerts_returns_empty_when_not_set_up(budget_env):
    alerts_module, service, repo = budget_env
    assert alerts_module.run_budget_alerts() == []


def test_run_budget_alerts_logs_and_dedupes(budget_env, monkeypatch):
    alerts_module, service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    monkeypatch.setattr("push.send_push_notification", lambda *a, **k: False)

    # Explicit now= (past daily_checkin_time) — the same reason
    # evaluate_alerts()'s own tests fix `now`, below: whether any alert
    # fires depends on wall-clock time, so leaving this to the real clock
    # made the test pass or fail depending only on what time it happened
    # to run.
    now = datetime.datetime(2026, 8, 3, 21, 0)
    first_run = alerts_module.run_budget_alerts(now=now)
    assert len(first_run) > 0

    second_run = alerts_module.run_budget_alerts(now=now)
    assert second_run == []  # every alert from the first run is now deduped

    logged, _ = repo.get_alerts(limit=50)
    assert len(logged) == len(first_run)


def test_run_budget_alerts_marks_delivered_on_push_success(budget_env, monkeypatch):
    alerts_module, service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    monkeypatch.setattr("push.send_push_notification", lambda *a, **k: True)

    alerts_module.run_budget_alerts()
    logged, _ = repo.get_alerts(limit=50)
    assert all(a["delivered"] for a in logged)


def test_run_budget_alerts_logs_even_when_push_fails(budget_env, monkeypatch):
    alerts_module, service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    monkeypatch.setattr("push.send_push_notification", lambda *a, **k: False)

    alerts_module.run_budget_alerts(now=datetime.datetime(2026, 8, 3, 21, 0))
    logged, _ = repo.get_alerts(limit=50)
    assert len(logged) > 0
    assert all(not a["delivered"] for a in logged)


def test_mark_alert_read_updates_unread_count(budget_env, monkeypatch):
    alerts_module, service, repo = budget_env
    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)
    monkeypatch.setattr("push.send_push_notification", lambda *a, **k: False)
    alerts_module.run_budget_alerts(now=datetime.datetime(2026, 8, 3, 21, 0))

    _, unread_before = repo.get_alerts()
    assert unread_before > 0

    logged, _ = repo.get_alerts(limit=1)
    repo.mark_alert_read(logged[0]["id"])
    _, unread_after = repo.get_alerts()
    assert unread_after == unread_before - 1
