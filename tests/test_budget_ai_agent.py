"""The budget Q&A agent (features/budget/ai/agent.py): the calculator, the
read-only tools, the grounding guard and the loop. Gemini is always
replaced by a scripted stand-in at agent._generate."""
import importlib
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
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
    import features.budget.ai.agent as agent_module
    import features.budget.ai.qa as qa_module
    modules = (db_module, schema_module, database_module, repo_module, periods_module, compute_module,
               insights_module, service_module, llm_module, agent_module, qa_module)
    for m in modules:
        importlib.reload(m)

    database_module.init_db()
    yield {"repo": repo_module, "service": service_module, "llm": llm_module,
           "agent": agent_module, "qa": qa_module}

    for m in modules:
        importlib.reload(m)


def _seed(env):
    repo, service = env["repo"], env["service"]
    wallet = repo.create_wallet("Cash", opening_balance=3_000_000, is_default=True)
    food = repo.create_category("Food", "variable", monthly_limit=1_000_000)
    view = service.build_period_view()
    repo.create_transaction(250_000, "expense", wallet_id=wallet["id"], category_id=food["id"],
                            period_id=view["period_id"], note="Groceries")
    repo.create_transaction(40_000, "expense", wallet_id=wallet["id"], period_id=view["period_id"],
                            note="Shopee snack")
    return wallet, food


def _call(name, **args):
    return SimpleNamespace(name=name, args=args)


class _Gemini:
    """Stand-in for agent._generate. Each scripted step is a list of tool
    calls, a reply string, an Exception, or a callable(contents) -> one
    of those."""
    def __init__(self, *steps):
        self.steps = list(steps)
        self.models = []

    def __call__(self, contents, config, model=None):
        self.models.append(model)
        step = self.steps.pop(0)
        if callable(step):
            step = step(contents)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, list):
            return SimpleNamespace(function_calls=step, text=None, candidates=[])
        return SimpleNamespace(function_calls=None, text=step, candidates=[])


def _fmt(n):
    return f"Rp {int(n):,}".replace(",", ".")


# ================================================================
# calculator
# ================================================================
@pytest.mark.parametrize("expr, expected", [
    ("827195 - 80000 * 9", 107195),
    ("(1 + 2) * 3", 9),
    ("252868 / 502280 * 100", 50.344),
    ("max(80000 - 35080, 0)", 44920),
    ("round(10 / 3)", 3),
    ("1_000_000 // 3", 333333),
    ("-5 + 2 ** 3", 3),
])
def test_calculate(env, expr, expected):
    assert env["agent"].calculate(expr) == expected


@pytest.mark.parametrize("expr", [
    "__import__('os').system('true')", "open('x')", "x + 1", "(1).real", "2 ** 1000",
    "'a' * 3", "[1, 2]", "lambda: 1", "1; 2", "9" * 400, "True + 1",
])
def test_calculate_rejects(env, expr):
    with pytest.raises(ValueError):
        env["agent"].calculate(expr)


# ================================================================
# tools
# ================================================================
def test_tools_are_read_only_and_serializable(env):
    _seed(env)
    agent, repo = env["agent"], env["repo"]
    before, _ = repo.get_transactions(limit=500)
    wallets_before = repo.wallet_balances()
    ctx = agent._Context()
    args = {
        "get_budget_overview": {}, "get_bills": {}, "get_goals": {}, "get_wallets": {},
        "list_transactions": {"category": "food", "sort": "amount", "limit": 5},
        "get_category_spend": {"period": "current"},
        "get_period_history": {"periods": 3, "groupBy": "month"},
        "calculate": {"expression": "1 + 1"},
    }
    assert set(args) == set(agent.TOOLS)
    for name, a in args.items():
        result = agent.run_tool(name, a, ctx)
        assert "error" not in result, (name, result)
        json.dumps(result, default=str)
    assert repo.get_transactions(limit=500)[0] == before
    assert repo.wallet_balances() == wallets_before


def test_list_transactions_filters_and_totals(env):
    _seed(env)
    agent = env["agent"]
    ctx = agent._Context()
    result = agent.run_tool("list_transactions", {"search": "shopee"}, ctx)
    assert result["matched"] == 1 and result["totalAmount"] == 40_000
    result = agent.run_tool("list_transactions", {"category": "uncategorized"}, ctx)
    assert result["matched"] == 1 and result["transactions"][0]["note"] == "Shopee snack"
    result = agent.run_tool("get_category_spend", {}, ctx)
    assert result["totalSpend"] == 290_000
    assert result["categories"][0] == {"name": "Food", "spend": 250_000, "count": 1, "budgetLimit": 1_000_000}


def test_tool_errors_go_back_to_the_model(env):
    _seed(env)
    agent = env["agent"]
    ctx = agent._Context()
    assert "error" in agent.run_tool("nope", {}, ctx)
    assert "error" in agent.run_tool("calculate", {"expression": "x"}, ctx)
    assert "error" in agent.run_tool("list_transactions", {"period": "banana"}, ctx)
    assert "error" in agent.run_tool("get_bills", {"bogus": 1}, ctx)


# ================================================================
# loop
# ================================================================
def test_daily_spend_projection(env, monkeypatch):
    _seed(env)
    view = env["service"].build_period_view()
    free, days = view["free_money"], view["days_left"]
    expected = free - 80_000 * days
    model = _Gemini(
        [_call("get_budget_overview")],
        [_call("calculate", expression=f"{free} - 80000 * {days}")],
        f"Spending Rp 80.000 a day for {days} days leaves you {_fmt(expected)}.",
    )
    monkeypatch.setattr(env["agent"], "_generate", model)

    result = env["qa"].answer("if i keep spending 80000 every day, how much is left at payday?")
    assert result["source"] == "ai"
    assert result["query"]["query"] == "agent"
    assert _fmt(expected) in result["answer"]
    assert [t["name"] for t in result["tools"]] == ["get_budget_overview", "calculate"]
    assert any(f"= {expected}" in f["text"] for f in result["facts"])


def test_ungrounded_reply_gets_one_correction(env, monkeypatch):
    _seed(env)
    model = _Gemini(
        [_call("list_transactions", category="food")],
        "You spent Rp 999.999 on food.",
        "You spent Rp 250.000 on food.",
    )
    monkeypatch.setattr(env["agent"], "_generate", model)

    result = env["qa"].answer("how much on food?")
    assert result["answer"] == "You spent Rp 250.000 on food."
    assert len(model.models) == 3


def test_still_ungrounded_falls_back_to_menu(env, monkeypatch):
    _seed(env)
    monkeypatch.setattr(env["agent"], "_generate", _Gemini("Rp 123.456 left.", "Rp 654.321 left."))
    monkeypatch.setattr(env["qa"], "groq_complete", lambda *a, **k: '{"query": "bill_status"}')
    monkeypatch.setattr(env["llm"], "groq_complete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))

    result = env["qa"].answer("how much is left?")
    assert result["source"] == "rules"
    assert result["query"]["query"] == "bill_status"


def test_model_error_falls_back_to_menu(env, monkeypatch):
    _seed(env)
    monkeypatch.setattr(env["agent"], "_generate", _Gemini(RuntimeError("503 UNAVAILABLE")))
    monkeypatch.setattr(env["qa"], "groq_complete", lambda *a, **k: '{"query": "goal_progress"}')
    monkeypatch.setattr(env["llm"], "groq_complete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))

    result = env["qa"].answer("goals?")
    assert result["source"] == "rules" and result["query"]["query"] == "goal_progress"


def test_rate_limit_switches_to_fallback_model(env, monkeypatch):
    _seed(env)
    agent = env["agent"]
    model = _Gemini(RuntimeError("429 RESOURCE_EXHAUSTED"), "You have a budget set up.")
    monkeypatch.setattr(agent, "_generate", model)

    result = agent.answer("anything?")
    assert result["answer"] == "You have a budget set up."
    assert model.models == [agent.MODEL_BUDGET_AGENT, agent.MODEL_FALLBACK]
    assert result["model"] == agent.MODEL_FALLBACK


def test_round_limit(env, monkeypatch):
    _seed(env)
    agent = env["agent"]
    model = _Gemini(*([[_call("get_bills")]] * (agent.MAX_ROUNDS + 1)))
    monkeypatch.setattr(agent, "_generate", model)
    assert agent.answer("loop forever") is None


def test_question_figures_are_quotable(env, monkeypatch):
    _seed(env)
    monkeypatch.setattr(env["agent"], "_generate", _Gemini("At 80k a day (Rp 80.000) you'd be fine."))
    assert env["agent"].answer("can I spend 80000 a day?")["source"] == "ai"
