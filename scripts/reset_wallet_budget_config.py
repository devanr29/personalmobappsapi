"""Delete the budget *bills* and *goals* that earlier Wallet pulls created,
so they can be set up by hand in the app instead.

Background: sync.py used to pull Wallet's standing-orders into budget_bills
and Wallet's goals into budget_goals. It no longer does — budget structure
is configured in the app now (see sync.py's module docstring) — but the
rows those pulls already created are still sitting in the DB. This clears
them once; nothing re-creates them.

Scope: bills and goals that have a budget_wallet_links row, i.e. the ones
a pull created. Deletes
  - budget_bills          linked via entity_type='standing_order'
  - budget_bill_payments  for those bills
  - budget_goals          linked via entity_type='goal'
  - budget_goal_contributions for those goals
  - budget_wallet_links   entity_type IN ('standing_order', 'goal')
and first NULLs budget_transactions.bill_id / .goal_id for the affected
rows, so the actual payments stay in the ledger as ordinary expenses —
that money really did leave the account, deleting the bill must not delete
its history.

Keeps, deliberately and completely:
  - budget_categories and their entity_type='category' links. They are
    inert (a pulled category has no monthly_limit, so it contributes
    nothing to the budget math) but they carry the display name for ~1,500
    already-pulled transactions, and their links are what let a future
    pull still file a new record under the right name.
  - budget_labels, budget_wallets, budget_transactions, periods, alert
    prefs, and every manually-created bill or goal (one with no link row).

Runs against whatever DB the process is pointed at:
    railway run python scripts/reset_wallet_budget_config.py --execute   # Railway prod (Neon)
    python scripts/reset_wallet_budget_config.py --execute               # local bot.db

Default is a dry run (counts only, no writes). Pass --execute to delete.
"""
import argparse
import os
import sys

from dotenv import load_dotenv
load_dotenv("environtment.env")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import db_conn, IS_PG  # noqa: E402
from features.budget.wallet import sync as wallet_sync  # noqa: E402

_STANDING_ORDER = wallet_sync.ENTITY_STANDING_ORDER  # "standing_order"
_GOAL = wallet_sync.ENTITY_GOAL                      # "goal"
_CATEGORY = wallet_sync.ENTITY_CATEGORY              # "category"


def _linked_ids(conn, entity_type, table):
    """local_ids of rows a pull created. A link whose row was deleted since
    (an orphan) is counted separately — the link still needs clearing, but
    it isn't a row this script is about to delete."""
    rows = conn.execute(
        f"SELECT l.local_id FROM budget_wallet_links l "
        f"WHERE l.entity_type = ? AND EXISTS (SELECT 1 FROM {table} x WHERE x.id = l.local_id)",
        (entity_type,),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM budget_wallet_links WHERE entity_type = ?", (entity_type,)
    ).fetchone()[0]
    ids = [r[0] for r in rows]
    return ids, total - len(ids)


def _scalar(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def _in_clause(ids):
    """Inline the ids — they're ints straight out of the DB, and the two
    dialects disagree on array params."""
    return "(" + ",".join(str(int(i)) for i in ids) + ")"


def main(execute: bool) -> int:
    conn = db_conn()
    try:
        bill_ids, orphan_bill_links = _linked_ids(conn, _STANDING_ORDER, "budget_bills")
        goal_ids, orphan_goal_links = _linked_ids(conn, _GOAL, "budget_goals")
        total_bills = _scalar(conn, "SELECT COUNT(*) FROM budget_bills")
        total_goals = _scalar(conn, "SELECT COUNT(*) FROM budget_goals")
        kept_categories = _scalar(conn, "SELECT COUNT(*) FROM budget_categories")
        category_links, _ = _linked_ids(conn, _CATEGORY, "budget_categories")
        category_links = len(category_links)

        payments = txns_bill = contributions = txns_goal = 0
        if bill_ids:
            b = _in_clause(bill_ids)
            payments = _scalar(conn, f"SELECT COUNT(*) FROM budget_bill_payments WHERE bill_id IN {b}")
            txns_bill = _scalar(conn, f"SELECT COUNT(*) FROM budget_transactions WHERE bill_id IN {b}")
        if goal_ids:
            g = _in_clause(goal_ids)
            contributions = _scalar(conn, f"SELECT COUNT(*) FROM budget_goal_contributions WHERE goal_id IN {g}")
            txns_goal = _scalar(conn, f"SELECT COUNT(*) FROM budget_transactions WHERE goal_id IN {g}")

        print("DB:   " + ("Postgres" if IS_PG else "SQLite (bot.db)"))
        print("Mode: " + ("EXECUTE (deletes rows)" if execute else "DRY RUN (no writes)"))
        print()
        print(f"  budget_bills          pulled from Wallet    {len(bill_ids):>6}   delete")
        print(f"  budget_bill_payments  for those bills       {payments:>6}   delete")
        print(f"  budget_goals          pulled from Wallet    {len(goal_ids):>6}   delete")
        print(f"  budget_goal_contributions for those goals   {contributions:>6}   delete")
        orphans = orphan_bill_links + orphan_goal_links
        print(f"  budget_wallet_links   standing_order + goal {len(bill_ids) + len(goal_ids) + orphans:>6}   delete"
              + (f"   (incl. {orphans} orphaned)" if orphans else ""))
        print()
        print(f"  budget_transactions   .bill_id -> NULL      {txns_bill:>6}   KEPT (real payments)")
        print(f"  budget_transactions   .goal_id -> NULL      {txns_goal:>6}   KEPT (real payments)")
        print(f"  budget_bills          created by hand       {total_bills - len(bill_ids):>6}   keep")
        print(f"  budget_goals          created by hand       {total_goals - len(goal_ids):>6}   keep")
        print(f"  budget_categories     (all of them)         {kept_categories:>6}   keep")
        print(f"  budget_wallet_links   entity_type='category'{category_links:>6}   keep")

        if not execute:
            print()
            print("Dry run only. Re-run with --execute to apply.")
            return 0

        if bill_ids:
            b = _in_clause(bill_ids)
            conn.execute(f"UPDATE budget_transactions SET bill_id = NULL WHERE bill_id IN {b}")
            conn.execute(f"DELETE FROM budget_bill_payments WHERE bill_id IN {b}")
            conn.execute(f"DELETE FROM budget_bills WHERE id IN {b}")
            conn.execute("DELETE FROM budget_wallet_links WHERE entity_type = ?", (_STANDING_ORDER,))
        if goal_ids:
            g = _in_clause(goal_ids)
            conn.execute(f"UPDATE budget_transactions SET goal_id = NULL WHERE goal_id IN {g}")
            conn.execute(f"DELETE FROM budget_goal_contributions WHERE goal_id IN {g}")
            conn.execute(f"DELETE FROM budget_goals WHERE id IN {g}")
            conn.execute("DELETE FROM budget_wallet_links WHERE entity_type = ?", (_GOAL,))
        conn.commit()

        print()
        print(f"Done. budget_bills now {_scalar(conn, 'SELECT COUNT(*) FROM budget_bills')}, "
              f"budget_goals now {_scalar(conn, 'SELECT COUNT(*) FROM budget_goals')}, "
              f"budget_categories still {_scalar(conn, 'SELECT COUNT(*) FROM budget_categories')}.")
        print("Next: add your own bills and goals in the app (Budget tab).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--execute", action="store_true", help="Actually delete (default: dry run)")
    sys.exit(main(execute=parser.parse_args().execute))
