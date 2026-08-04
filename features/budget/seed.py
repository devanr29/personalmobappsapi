"""One-time backfill from Google Sheets (features/budget_config.py) plus
the legacy bot_state snapshot, so the ledger starts from real, current
numbers rather than fabricated defaults.

Deliberately does NOT call features.budget_config.get_fixed_expenses() /
get_variable_budgets() as its first move — those silently fall back to
config.py's hardcoded constants on any Sheets exception
(features/budget_config.py:145-147, :163-165). Calling get_google_services()
first and letting it raise means a Sheets outage aborts the seed loudly
instead of quietly importing placeholder numbers as if they were real."""
import json

from config import now_jkt, PAYROLL_DAY
from database import state_get, state_set
from google_auth import get_google_services
from features.budget import repo
from features.budget.errors import BudgetConflict
from features.budget.periods import ensure_current_period

DEFAULT_WALLETS = [
    {"name": "Cash", "kind": "cash", "spendable": True, "is_default": True},
    {"name": "Bank", "kind": "bank", "spendable": True, "is_default": False},
    {"name": "GoPay", "kind": "ewallet", "spendable": True, "is_default": False},
]


def _find_by_name(items, name, kind=None):
    for item in items:
        if item["name"] == name and (kind is None or item.get("kind") == kind):
            return item
    return None


def seed_from_sheets(force: bool = False) -> dict:
    if state_get("budget_seeded_at") and not force:
        raise BudgetConflict("Budget ledger has already been seeded. Pass force=true to re-run.")

    get_google_services()  # raises loudly on a Sheets/auth outage

    from features.budget_config import get_fixed_expenses, get_variable_budgets
    fixed_expenses = get_fixed_expenses()
    variable_budgets = get_variable_budgets()

    existing_wallets = repo.get_wallets(include_archived=True)
    wallets = []
    for spec in DEFAULT_WALLETS:
        found = _find_by_name(existing_wallets, spec["name"])
        wallets.append(found if found else repo.create_wallet(**spec))

    cash_wallet = _find_by_name(wallets, "Cash")
    opening_balance = 0
    snapshot_raw = state_get("last_budget_snapshot")
    if snapshot_raw:
        try:
            opening_balance = json.loads(snapshot_raw).get("remaining", 0) or 0
        except (ValueError, TypeError):
            opening_balance = 0
    repo.update_wallet(cash_wallet["id"], opening_balance=opening_balance)
    cash_wallet = repo.get_wallet(cash_wallet["id"])

    existing_categories = repo.get_categories(include_archived=True)
    categories = []
    for v in variable_budgets:
        found = _find_by_name(existing_categories, v["name"], kind="variable")
        categories.append(
            found if found else repo.create_category(v["name"], "variable", monthly_limit=v["budget"])
        )

    existing_bills = repo.get_bills(active_only=False)
    bills = []
    for e in fixed_expenses:
        category = _find_by_name(existing_categories, e["name"], kind="fixed")
        if not category:
            category = repo.create_category(e["name"], "fixed")
            existing_categories.append(category)
        categories.append(category)

        found_bill = _find_by_name(existing_bills, e["name"])
        bills.append(
            found_bill if found_bill else
            repo.create_bill(e["name"], e["amount"], due_day=e.get("due_day"), category_id=category["id"])
        )

    period = ensure_current_period(PAYROLL_DAY)
    repo.ensure_alert_prefs()

    state_set("budget_seeded_at", str(now_jkt()))

    return {
        "wallets": wallets,
        "categories": categories,
        "bills": bills,
        "periodId": period["id"],
        "openingBalance": opening_balance,
    }
