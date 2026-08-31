"""Reset the local mirror of Wallet by BudgetBakers *records* (transactions)
so the next `/sync/wallet/pull` re-pulls the full history from scratch.

Scope: records only. Deletes
  - budget_transactions WHERE source = 'wallet'   (the rows the pull created)
  - budget_transaction_labels for those rows      (associations only, not the labels)
  - budget_wallet_links WHERE entity_type = 'record'
  - the 'record' watermark + record_offset / record_running_max inside
    bot_state['wallet_sync_cursors']

Keeps: wallets, categories (and their monthly limits), labels, periods,
bills, goals, alert prefs, and every non-record link. The next pull re-links
records to the wallets/categories already present instead of trying to
recreate them (which would hit a UNIQUE constraint). Manually-entered
transactions (source = 'manual') are never touched.

Runs against whatever DB the process is pointed at:
    railway run python scripts/reset_wallet_records.py --execute   # Railway prod (Neon)
    python scripts/reset_wallet_records.py --execute               # local bot.db

Default is a dry run (counts only, no writes). Pass --execute to delete.
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv("environtment.env")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import db_conn, IS_PG  # noqa: E402
from database import state_get, state_set  # noqa: E402
from features.budget.wallet import sync as wallet_sync  # noqa: E402

_WALLET = "wallet"
_RECORD = wallet_sync.ENTITY_RECORD  # "record"
_LABELS_FOR_WALLET_TXNS = (
    "SELECT COUNT(*) FROM budget_transaction_labels WHERE transaction_id IN "
    "(SELECT id FROM budget_transactions WHERE source = ?)"
)


def _scalar(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def _clear_record_cursor():
    """Drop only the record keys from the cursors blob; leave the
    account/category/goal watermarks alone (those entities aren't being
    re-pulled)."""
    raw = state_get(wallet_sync._CURSOR_STATE_KEY)
    cursors = json.loads(raw) if raw else {}
    removed = {}
    for key in (_RECORD, wallet_sync._RECORD_OFFSET_KEY, wallet_sync._RECORD_RUNNING_MAX_KEY):
        if key in cursors:
            removed[key] = cursors.pop(key)
    state_set(wallet_sync._CURSOR_STATE_KEY, json.dumps(cursors))
    return removed, cursors


def main(execute: bool) -> int:
    conn = db_conn()
    try:
        total = _scalar(conn, "SELECT COUNT(*) FROM budget_transactions")
        wallet_txn = _scalar(conn, "SELECT COUNT(*) FROM budget_transactions WHERE source = ?", (_WALLET,))
        record_links = _scalar(conn, "SELECT COUNT(*) FROM budget_wallet_links WHERE entity_type = ?", (_RECORD,))
        txn_labels = _scalar(conn, _LABELS_FOR_WALLET_TXNS, (_WALLET,))
        cursors_before = json.loads(state_get(wallet_sync._CURSOR_STATE_KEY) or "{}")

        print("DB:   " + ("Postgres" if IS_PG else "SQLite (bot.db)"))
        print("Mode: " + ("EXECUTE (deletes rows)" if execute else "DRY RUN (no writes)"))
        print()
        print(f"  budget_transactions  source='wallet'       {wallet_txn:>8}   delete")
        print(f"  budget_transaction_labels  (for those)     {txn_labels:>8}   delete")
        print(f"  budget_wallet_links  entity_type='record'  {record_links:>8}   delete")
        print(f"  budget_transactions  source='manual'/other {total - wallet_txn:>8}   keep")
        print()
        print("  wallet_sync_cursors before: " + json.dumps(cursors_before))

        if not execute:
            print()
            print("Dry run only. Re-run with --execute to apply.")
            return 0

        conn.execute(
            "DELETE FROM budget_transaction_labels WHERE transaction_id IN "
            "(SELECT id FROM budget_transactions WHERE source = ?)",
            (_WALLET,),
        )
        conn.execute("DELETE FROM budget_wallet_links WHERE entity_type = ?", (_RECORD,))
        conn.execute("DELETE FROM budget_transactions WHERE source = ?", (_WALLET,))
        conn.commit()

        removed, cursors_after = _clear_record_cursor()

        print()
        print("  cleared from cursors:        " + json.dumps(removed))
        print("  wallet_sync_cursors after:  " + json.dumps(cursors_after))
        print()
        left_txn = _scalar(conn, "SELECT COUNT(*) FROM budget_transactions WHERE source = ?", (_WALLET,))
        left_links = _scalar(conn, "SELECT COUNT(*) FROM budget_wallet_links WHERE entity_type = ?", (_RECORD,))
        print(f"Done. source='wallet' transactions now {left_txn}, record links now {left_links}.")
        print("Next: trigger a wallet pull (app Sync now, or POST /api/budget/sync/wallet/pull).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--execute", action="store_true", help="Actually delete (default: dry run)")
    sys.exit(main(execute=parser.parse_args().execute))
