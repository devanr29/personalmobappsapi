"""The chat 'budget' intent must be read-only: it reports live ledger
numbers and never calls an LLM or writes anything. Guards the Phase 1
chat rewire (features/budget/chat_view.py, intents.py)."""
import importlib

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
    import features.budget.service as service_module
    modules = (db_module, schema_module, database_module, repo_module,
               periods_module, compute_module, service_module)
    for m in modules:
        importlib.reload(m)

    database_module.init_db()
    yield service_module, repo_module

    for m in modules:
        importlib.reload(m)


def test_budget_intent_with_no_wallets_returns_text_no_crash(budget_env):
    from intents import route_intent

    result = route_intent("budget", {}, "budget")
    assert result["kind"] == "text"
    assert "isn't set up" in result["text"].lower()
    assert result["data"] is None


def test_budget_intent_with_ledger_matches_service_summary(budget_env):
    from intents import route_intent
    service, repo = budget_env

    repo.create_wallet("Cash", opening_balance=1_000_000, is_default=True)

    result = route_intent("budget", {}, "budget")
    assert result["kind"] == "budget"

    summary = service.get_summary()
    assert result["data"]["dailyBudget"] == summary["dailyBudget"]
    assert result["data"]["free"] == summary["free"]
    assert result["data"]["statusLevel"] == summary["statusLevel"]


def test_budget_module_exposes_no_write_or_llm_surface():
    import features.budget as budget_pkg

    assert not hasattr(budget_pkg, "compute_and_persist_budget")
    assert not hasattr(budget_pkg, "calculate_budget")
    assert not hasattr(budget_pkg, "_budget_interactive_prompt")
    assert budget_pkg.__all__ == ["budget_bp"]


def test_budget_intent_never_calls_groq(budget_env, monkeypatch):
    from intents import route_intent

    def _boom(*args, **kwargs):
        raise AssertionError("groq_complete must not be called by the read-only budget intent")

    monkeypatch.setattr("ai.groq_client.groq_complete", _boom)

    result = route_intent("budget", {}, "budget")
    assert result["kind"] == "text"
