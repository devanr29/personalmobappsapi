import importlib
import json
from unittest.mock import patch

import pytest

FIXED = [
    {"name": "House Rent", "amount": 955_000, "due_day": 25},
    {"name": "Internet", "amount": 150_000, "due_day": None},
]
VARIABLE = [
    {"name": "Fuel", "budget": 70_000},
    {"name": "Laundry", "budget": 60_000},
]


@pytest.fixture
def seed_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DATABASE_URL", "")

    import db as db_module
    import database as database_module
    import features.budget.schema as schema_module
    import features.budget.repo as repo_module
    import features.budget.periods as periods_module
    import features.budget.seed as seed_module
    modules = (db_module, schema_module, database_module, repo_module, periods_module, seed_module)
    for m in modules:
        importlib.reload(m)

    database_module.init_db()
    database_module.state_set("last_budget_snapshot", json.dumps({"remaining": 3_254_624}))

    yield seed_module, repo_module, database_module

    for m in modules:
        importlib.reload(m)


def _patched_seed(seed_module):
    return (
        patch("features.budget.seed.get_google_services", return_value=(None, None, None)),
        patch("features.budget_config.get_fixed_expenses", return_value=FIXED),
        patch("features.budget_config.get_variable_budgets", return_value=VARIABLE),
    )


def test_seed_creates_wallets_categories_bills_and_uses_snapshot_balance(seed_env):
    seed_module, repo, database_module = seed_env
    p1, p2, p3 = _patched_seed(seed_module)
    with p1, p2, p3:
        result = seed_module.seed_from_sheets()

    assert result["openingBalance"] == 3_254_624
    assert {w["name"] for w in result["wallets"]} == {"Cash", "Bank", "GoPay"}
    assert {c["name"] for c in result["categories"]} == {"Fuel", "Laundry", "House Rent", "Internet"}
    assert {b["name"] for b in result["bills"]} == {"House Rent", "Internet"}

    cash = next(w for w in repo.get_wallets() if w["name"] == "Cash")
    assert cash["opening_balance"] == 3_254_624
    assert cash["is_default"] is True

    assert database_module.state_get("budget_seeded_at") is not None


def test_seed_twice_without_force_raises_conflict(seed_env):
    seed_module, repo, database_module = seed_env
    p1, p2, p3 = _patched_seed(seed_module)
    with p1, p2, p3:
        seed_module.seed_from_sheets()
        from features.budget.errors import BudgetConflict
        with pytest.raises(BudgetConflict):
            seed_module.seed_from_sheets()


def test_seed_with_force_is_idempotent_no_duplicates(seed_env):
    seed_module, repo, database_module = seed_env
    p1, p2, p3 = _patched_seed(seed_module)
    with p1, p2, p3:
        seed_module.seed_from_sheets()
        seed_module.seed_from_sheets(force=True)

    wallets = repo.get_wallets(include_archived=True)
    assert len(wallets) == 3  # not 6
    categories = repo.get_categories(include_archived=True)
    assert len(categories) == 4  # Fuel, Laundry, House Rent, Internet — not doubled
    bills = repo.get_bills(active_only=False)
    assert len(bills) == 2


def test_seed_aborts_loudly_on_sheets_outage(seed_env):
    seed_module, repo, database_module = seed_env
    with patch("features.budget.seed.get_google_services", side_effect=RuntimeError("Sheets unreachable")):
        with pytest.raises(RuntimeError):
            seed_module.seed_from_sheets()

    # nothing should have been created
    assert repo.get_wallets(include_archived=True) == []
    assert database_module.state_get("budget_seeded_at") is None
