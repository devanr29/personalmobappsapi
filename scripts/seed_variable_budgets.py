"""One-time seed for the user's real variable budget envelopes.

Wallet-sync only ever writes name/kind/archived on a linked category
(features/budget/wallet/mapping.py:category_to_local_fields) and never
touches monthly_limit, so these rows are safe from being reverted by a
future sync — see service.py's build_period_view() comment on why
monthly_limit is the durable "this is a real budget" signal.

Idempotent: find-or-create by (name, kind='variable'), then set
monthly_limit if it differs. Safe to re-run.

Usage:
    python scripts/seed_variable_budgets.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from features.budget import repo  # noqa: E402

BUDGETS = [
    ("Ticket to go home", 600_000),
    ("Fuel", 70_000),
    ("Laundry", 60_000),
    ("Claude", 400_000),
    ("Sedekah", 50_000),
    ("Tidak terduga", 700_000),
]


def _find(existing, name):
    for c in existing:
        if c["name"] == name and c["kind"] == "variable":
            return c
    return None


def main():
    existing = repo.get_categories(include_archived=True, kind="variable")
    created, updated, unchanged = 0, 0, 0

    for name, limit in BUDGETS:
        found = _find(existing, name)
        if found is None:
            row = repo.create_category(name, "variable", monthly_limit=limit)
            existing.append(row)
            created += 1
            print(f"  created   {name:22} Rp {limit:,}".replace(",", "."))
        elif found["monthly_limit"] != limit or found["archived"]:
            repo.update_category(found["id"], monthly_limit=limit, archived=False)
            updated += 1
            print(f"  updated   {name:22} Rp {limit:,}".replace(",", "."))
        else:
            unchanged += 1
            print(f"  unchanged {name:22} Rp {limit:,}".replace(",", "."))

    total = sum(limit for _, limit in BUDGETS)
    print(f"\n{created} created, {updated} updated, {unchanged} unchanged — total Rp {total:,}".replace(",", "."))


if __name__ == "__main__":
    main()
