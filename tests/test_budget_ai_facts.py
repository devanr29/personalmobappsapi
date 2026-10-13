"""Pure coverage for the AI layer's deterministic parts — facts.py,
llm.py's grounding guard, qa.parse_amount — plus the category_spike alert
evaluator. No DB, no clock, no model."""
import pytest

from features.budget.ai import facts, llm, qa
from features.budget.alerts import evaluate_anomalies


def _insights(**stats_overrides):
    stats = {
        "projectedEndBalance": 400_000, "avgDailySpend": 80_000, "dailyBudget": 120_000,
        "todayAllowance": 100_000, "todayRemaining": 40_000, "spendToDate": 800_000,
        "freeMoney": 1_200_000, "largestExpense": {"name": "Groceries", "amount": 350_000},
    }
    stats.update(stats_overrides)
    return {
        "period": {"elapsedDays": 10, "totalDays": 31, "daysLeft": 20, "label": "Jul 25 - Aug 25"},
        "stats": stats,
        "pace": {"envelope": 1_550_000, "aheadBy": 0, "points": [{"actual": 500_000, "ideal": 500_000}]},
        "budgetVsActual": [],
        "categories": [
            {"categoryId": 1, "name": "Food", "spend": 600_000, "share": 0.75},
            {"categoryId": 2, "name": "Transport", "spend": 200_000, "share": 0.25},
        ],
    }


def _patterns(food_avg=600_000, months_active=5):
    return {"categories": [
        {"categoryId": 1, "name": "Food", "avgPerMonth": food_avg, "monthsActive": months_active},
        {"categoryId": 2, "name": "Transport", "avgPerMonth": 600_000, "monthsActive": 5},
    ]}


def _keys(fs):
    return [f["key"] for f in fs]


# ================================================================
# facts.build_facts
# ================================================================
def test_build_facts_none_insights_is_empty():
    assert facts.build_facts(None) == []


def test_negative_projection_is_top_severity():
    fs = facts.build_facts(_insights(projectedEndBalance=-150_000))
    assert fs[0]["key"] == "projection"
    assert fs[0]["tone"] == "bad"
    assert "Rp 150.000 short" in fs[0]["text"]


def test_facts_sorted_by_severity_desc():
    ins = _insights()
    ins["budgetVsActual"] = [{"categoryId": 1, "name": "Food", "budget": 500_000, "actual": 600_000,
                              "remaining": 0, "overBudget": 100_000, "pct": 1.2}]
    fs = facts.build_facts(ins)
    severities = [f["severity"] for f in fs]
    assert severities == sorted(severities, reverse=True)
    assert fs[0]["key"] == "over:1"
    assert "over budget by Rp 100.000" in fs[0]["text"]


def test_near_limit_category_is_watch():
    ins = _insights()
    ins["budgetVsActual"] = [{"categoryId": 2, "name": "Transport", "budget": 250_000, "actual": 210_000,
                              "remaining": 40_000, "overBudget": 0, "pct": 0.84}]
    fact = next(f for f in facts.build_facts(ins) if f["key"] == "near:2")
    assert "84%" in fact["text"] and "Rp 40.000 left" in fact["text"]


def test_pace_ahead_is_bad_and_behind_is_good():
    ins = _insights()
    ins["pace"]["aheadBy"] = -120_000
    assert next(f for f in facts.build_facts(ins) if f["key"] == "pace")["tone"] == "bad"
    ins["pace"]["aheadBy"] = 120_000
    assert next(f for f in facts.build_facts(ins) if f["key"] == "pace")["tone"] == "good"


def test_vs_usual_fires_only_beyond_deviation():
    # expected by day 10 of 31 with a 2.48M average = 800k -> on pace, no fact
    assert "vs_usual" not in _keys(facts.build_facts(_insights(), history={"averageSpend": 2_480_000}))
    fs = facts.build_facts(_insights(spendToDate=1_200_000), history={"averageSpend": 2_480_000})
    assert next(f for f in fs if f["key"] == "vs_usual")["tone"] == "watch"


def test_category_spike_fact_from_patterns():
    # Food usual 600k/month -> ~193.5k by day 10 of 31; 600k spent is ~3x
    fs = facts.build_facts(_insights(), patterns=_patterns())
    assert "spike:1" in _keys(fs)
    assert "spike:2" not in _keys(fs)  # Transport: 200k vs ~193k expected


# ================================================================
# facts.category_spikes
# ================================================================
def test_spike_needs_two_active_months():
    cats = _insights()["categories"]
    assert facts.category_spikes(cats, _patterns(months_active=1), 10, 31) == []


def test_spike_needs_minimum_rupiah_excess():
    cats = [{"categoryId": 1, "name": "Food", "spend": 40_000, "share": 1}]
    # 3x usual, but only ~27k over -> below SPIKE_MIN_EXCESS
    assert facts.category_spikes(cats, _patterns(food_avg=40_000), 10, 31) == []


def test_spike_no_patterns_is_empty():
    assert facts.category_spikes(_insights()["categories"], None, 10, 31) == []


# ================================================================
# facts.week_facts
# ================================================================
def test_week_facts_short_period_says_since_payday():
    fs = facts.week_facts([{"spend": 10_000}] * 3)
    assert fs[0]["text"].startswith("Rp 30.000 spent since payday")


def test_week_facts_compares_previous_week():
    daily = [{"spend": 10_000}] * 7 + [{"spend": 20_000}] * 7
    fs = facts.week_facts(daily)
    assert fs[0]["text"] == "Rp 140.000 spent in the last 7 days."
    assert "Rp 70.000 more than the 7 days before (Rp 70.000)" in fs[1]["text"]


# ================================================================
# llm grounding
# ================================================================
FACTS = [{"text": "Food is over budget by Rp 100.000 (Rp 600.000 spent of Rp 500.000)."},
         {"text": "Transport has used 84% of its budget."}]


@pytest.mark.parametrize("reply", [
    "Food is over by Rp 100.000 — you've spent Rp 600.000.",
    "Food went 100k over budget.",
    "Transport is at 84% already.",
    "Keep an eye on food this week.",
])
def test_grounded_replies_pass(reply):
    assert llm.numbers_grounded(reply, FACTS)


@pytest.mark.parametrize("reply", [
    "Food is over by Rp 150.000.",
    "You have about 250k left.",
    "Transport is at 90%.",
    "You spent 1.100.000 in total.",
])
def test_invented_figures_fail(reply):
    assert not llm.numbers_grounded(reply, FACTS)


def test_narrate_returns_none_on_ungrounded_reply(monkeypatch):
    monkeypatch.setattr(llm, "groq_complete", lambda *a, **k: "You will save Rp 999.999!")
    assert llm.narrate(FACTS, "summarize") is None


def test_narrate_returns_none_when_model_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("429 rate_limit")
    monkeypatch.setattr(llm, "groq_complete", boom)
    assert llm.narrate(FACTS, "summarize") is None


def test_narrate_passes_grounded_reply(monkeypatch):
    monkeypatch.setattr(llm, "groq_complete", lambda *a, **k: " - Food is Rp 100.000 over. ")
    assert llm.narrate(FACTS, "summarize") == "- Food is Rp 100.000 over."


def test_split_bullets_strips_markers():
    text = "- **Food** is over\n2) Transport ok\n\n• Save more"
    assert llm.split_bullets(text) == ["Food is over", "Transport ok", "Save more"]


# ================================================================
# qa.parse_amount
# ================================================================
@pytest.mark.parametrize("text,expected", [
    ("can I afford 500k?", 500_000),
    ("bisa beli 750rb ga", 750_000),
    ("a 1.5jt phone", 1_500_000),
    ("1,5 juta", 1_500_000),
    ("Rp 250.000 dinner", 250_000),
    ("spend 300000 tonight", 300_000),
    ("in 2 days", None),
    ("how am I doing", None),
])
def test_parse_amount(text, expected):
    assert qa.parse_amount(text) == expected


# ================================================================
# alerts.evaluate_anomalies
# ================================================================
SPIKE = {"categoryId": 1, "name": "Food", "spend": 600_000, "expected": 200_000, "excess": 400_000, "ratio": 3.0}


def test_anomaly_alert_shape_and_ref_key():
    [alert] = evaluate_anomalies(prefs={"anomaly_enabled": True}, period={"id": 7}, spikes=[SPIKE])
    assert alert["kind"] == "category_spike"
    assert alert["ref_key"] == "cat:1:period:7:spike"
    assert "Rp 600.000" in alert["body"] and "Rp 200.000" in alert["body"]


def test_anomaly_disabled_never_fires():
    assert evaluate_anomalies(prefs={"anomaly_enabled": False}, period={"id": 7}, spikes=[SPIKE]) == []
