"""DB-backed coverage for the budget AI layer's orchestration — the
insights summary (cache, rules fallback), Q&A, the weekly digest, the
new routes and the budget_question chat intent. The model is always
monkeypatched; the pure parts are in test_budget_ai_facts.py."""
import datetime
import importlib
import json

import pytest


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
    import features.budget.insights as insights_module
    import features.budget.service as service_module
    import features.budget.ai.llm as llm_module
    import features.budget.ai.summary as summary_module
    import features.budget.ai.agent as agent_module
    import features.budget.ai.qa as qa_module
    modules = (db_module, schema_module, database_module, repo_module, periods_module,
               compute_module, insights_module, service_module, llm_module, summary_module,
               agent_module, qa_module)
    for m in modules:
        importlib.reload(m)
    # These tests cover the fixed-menu path, which only runs when the agent
    # gives up; tests/test_budget_ai_agent.py covers the agent itself.
    monkeypatch.setattr(agent_module, "answer", lambda question, view=None: None)

    database_module.init_db()
    yield {"repo": repo_module, "service": service_module, "llm": llm_module,
           "summary": summary_module, "qa": qa_module}

    for m in modules:
        importlib.reload(m)


def _seed(env):
    repo, service = env["repo"], env["service"]
    wallet = repo.create_wallet("Cash", opening_balance=3_000_000, is_default=True)
    food = repo.create_category("Food", "variable", monthly_limit=1_000_000)
    view = service.build_period_view()
    repo.create_transaction(250_000, "expense", wallet_id=wallet["id"], category_id=food["id"],
                            period_id=view["period_id"], note="Groceries")
    return wallet, food


class _Model:
    """Stand-in for groq_complete: records calls, replies from a script."""
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, system_prompt, user_prompt, **kwargs):
        self.calls.append(user_prompt)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply(user_prompt) if callable(reply) else reply


def _echo_first_two_facts(prompt):
    lines = [l for l in prompt.splitlines() if l.startswith("- ")]
    return "\n".join(lines[:2])


# ================================================================
# summary
# ================================================================
def test_summary_none_when_not_set_up(budget_env):
    assert budget_env["summary"].build_ai_summary() is None


def test_summary_ai_bullets_and_cache(budget_env, monkeypatch):
    _seed(budget_env)
    model = _Model(_echo_first_two_facts)
    monkeypatch.setattr(budget_env["llm"], "groq_complete", model)

    first = budget_env["summary"].build_ai_summary()
    assert first["source"] == "ai"
    assert len(first["bullets"]) == 2
    assert first["facts"]

    second = budget_env["summary"].build_ai_summary()
    assert second == first
    assert len(model.calls) == 1  # served from cache

    budget_env["summary"].build_ai_summary(refresh=True)
    assert len(model.calls) == 2


def test_summary_falls_back_to_rules_and_is_not_cached(budget_env, monkeypatch):
    _seed(budget_env)
    model = _Model("- You will have Rp 123.456.789 left!\n- Great job")
    monkeypatch.setattr(budget_env["llm"], "groq_complete", model)

    result = budget_env["summary"].build_ai_summary()
    assert result["source"] == "rules"
    assert result["bullets"] == [f["text"] for f in result["facts"][:len(result["bullets"])]]

    budget_env["summary"].build_ai_summary()
    assert len(model.calls) == 2  # rules results are never cached


# ================================================================
# Q&A
# ================================================================
def test_qa_category_spend(budget_env, monkeypatch):
    _seed(budget_env)
    model = _Model('{"query": "category_spend", "category": "food", "amount": null}', RuntimeError("down"))
    monkeypatch.setattr(budget_env["qa"], "groq_complete", model)
    monkeypatch.setattr(budget_env["llm"], "groq_complete", _Model(RuntimeError("down")))

    result = budget_env["qa"].answer("how much did I spend on fod?")
    assert result["query"]["query"] == "category_spend"
    assert result["source"] == "rules"
    assert "Food: Rp 250.000 spent this period across 1 transaction." in result["answer"]


def test_qa_can_afford_uses_parsed_amount_not_models(budget_env, monkeypatch):
    _seed(budget_env)
    monkeypatch.setattr(budget_env["qa"], "groq_complete",
                        _Model('{"query": "can_afford", "category": null, "amount": 5}'))
    monkeypatch.setattr(budget_env["llm"], "groq_complete", _Model(RuntimeError("down")))

    result = budget_env["qa"].answer("can I afford 500k?")
    assert result["query"]["amount"] == 500_000
    assert "After spending Rp 500.000" in result["answer"]


def test_qa_bad_plan_json_falls_back_to_overview(budget_env, monkeypatch):
    _seed(budget_env)
    monkeypatch.setattr(budget_env["qa"], "groq_complete", _Model("not json"))
    monkeypatch.setattr(budget_env["llm"], "groq_complete", _Model(_echo_first_two_facts))

    result = budget_env["qa"].answer("how am I doing?")
    assert result["query"]["query"] == "overview"
    assert result["source"] == "ai"


def test_qa_none_when_not_set_up(budget_env):
    assert budget_env["qa"].answer("anything") is None


def test_qa_never_writes(budget_env, monkeypatch):
    _seed(budget_env)
    monkeypatch.setattr(budget_env["llm"], "groq_complete", _Model(RuntimeError("down")))
    before, _ = budget_env["repo"].get_transactions(limit=500)
    for query in ("category_spend", "period_compare", "can_afford", "top_categories", "largest_expenses",
                  "daily_allowance", "bill_status", "goal_progress", "overview"):
        plan = json.dumps({"query": query, "category": "Food", "amount": 100_000})
        monkeypatch.setattr(budget_env["qa"], "groq_complete", _Model(plan))
        result = budget_env["qa"].answer("q")
        assert result["query"]["query"] == query
        assert result["facts"]
    after, _ = budget_env["repo"].get_transactions(limit=500)
    assert after == before


# ================================================================
# weekly digest
# ================================================================
def test_weekly_digest_logs_once_per_week(budget_env, monkeypatch):
    _seed(budget_env)
    monkeypatch.setattr(budget_env["llm"], "groq_complete", _Model(RuntimeError("down")))
    monkeypatch.setattr("push.send_push_notification", lambda *a, **k: True)
    now = datetime.datetime(2026, 10, 11, 19, 0)

    alert = budget_env["summary"].run_weekly_digest(now=now)
    assert alert["kind"] == "weekly_digest"
    assert alert["ref_key"] == "week:2026-W41"
    assert budget_env["summary"].run_weekly_digest(now=now) is None

    logged, _ = budget_env["repo"].get_alerts(limit=50)
    digests = [a for a in logged if a["kind"] == "weekly_digest"]
    assert len(digests) == 1 and digests[0]["delivered"]


def test_weekly_digest_respects_pref(budget_env, monkeypatch):
    _seed(budget_env)
    budget_env["repo"].update_alert_prefs(weekly_digest_enabled=False)
    assert budget_env["summary"].run_weekly_digest() is None


# ================================================================
# routes + chat intent
# ================================================================
def test_ask_route_validation(budget_env, client, auth_headers):
    assert client.post("/api/budget/ask", headers=auth_headers, json={}).status_code == 400
    assert client.post("/api/budget/ask", headers=auth_headers, json={"question": "x" * 501}).status_code == 400


def test_ai_routes_return_null_when_not_set_up(budget_env, client, auth_headers):
    resp = client.get("/api/budget/insights/ai", headers=auth_headers)
    assert resp.status_code == 200 and resp.get_json()["data"] is None
    resp = client.post("/api/budget/ask", headers=auth_headers, json={"question": "how am I doing?"})
    assert resp.status_code == 200 and resp.get_json()["data"] is None


def test_alert_prefs_roundtrip_new_fields(budget_env, client, auth_headers):
    prefs = client.get("/api/budget/alerts/prefs", headers=auth_headers).get_json()["data"]
    assert prefs["anomalyEnabled"] is True and prefs["weeklyDigestEnabled"] is True
    resp = client.patch("/api/budget/alerts/prefs", headers=auth_headers, json={"anomalyEnabled": False})
    assert resp.get_json()["data"]["anomalyEnabled"] is False


def test_budget_question_intent(budget_env, monkeypatch):
    from intents import route_intent
    _seed(budget_env)
    monkeypatch.setattr(budget_env["qa"], "groq_complete", _Model('{"query": "bill_status"}'))
    monkeypatch.setattr(budget_env["llm"], "groq_complete", _Model(RuntimeError("down")))

    result = route_intent("budget_question", {}, "any bills left?")
    assert result["kind"] == "text"
    assert "Every fixed bill for this period is paid." in result["text"]
