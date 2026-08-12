"""One-time data migration: copy every row from the local bot.db (SQLite)
into the Postgres database named by DATABASE_URL.

bot.db is the source of truth: every insert is ON CONFLICT DO UPDATE
keyed on the source's primary key, so a row that already exists on the
Postgres side (e.g. from an earlier partial migration) is overwritten
with the bot.db version rather than skipped. Safe to re-run — re-copying
identical rows is a no-op.

Usage:
    python scripts/migrate_sqlite_to_pg.py --dry-run   # counts only, no writes
    python scripts/migrate_sqlite_to_pg.py             # actually copies

Requires:
    - bot.db present in the working directory (the SQLite source)
    - DATABASE_URL set to a reachable Postgres instance
    - The target schema already created (run `python -c "from database import
      init_db; init_db()"` against DATABASE_URL first, or just start the app
      once against it)

Table and column names below are a fixed, hardcoded allowlist (TABLES) — not
derived from any request or external input — so building the DDL/DML text by
concatenating them is safe; only row *values* ever cross the wire as bound
parameters.
"""
import argparse
import os
import sqlite3
import sys

from dotenv import load_dotenv
load_dotenv("environtment.env")

SQLITE_PATH = os.environ.get("DB_PATH", "bot.db")

# (table, columns-in-order, blob-column-name-or-None)
#
# The budget_* tables are listed in FK-parent-first order (wallets/categories/
# periods before the rows that reference them) because the Postgres target has
# real FK constraints and this script does not defer them.
#
# bot_state is deliberately copied BEFORE the budget_* tables even though it
# carries budget_schema_version: _assert_target_schema() below requires every
# budget_* table to already exist on the target, so by the time this script
# runs init_budget_schema() has already created them and copying bot_state's
# version marker afterwards is correct either way. The hazard this guards
# against is the *inverse* order on a fresh target — copying bot_state first
# via some other path, then booting the app, would make init_budget_schema()
# see a version marker already set and skip creating the tables entirely.
TABLES = [
    ("ideas",         ["id", "content", "timestamp"], None),
    ("reminders",     ["id", "content", "remind_at", "done"], None),
    ("notes",         ["id", "content", "timestamp"], None),
    ("tasks",         ["id", "content", "timestamp", "done"], None),
    ("conversations", ["id", "role", "content", "timestamp"], None),
    ("bot_state",     ["key", "value"], None),
    ("embeddings",    ["id", "source_type", "source_id", "content", "embedding", "timestamp"], "embedding"),
    ("budget_wallets", [
        "id", "name", "kind", "opening_balance", "spendable", "is_default",
        "archived", "sort_order", "created_at",
    ], None),
    ("budget_categories", [
        "id", "name", "kind", "monthly_limit", "rollover", "keywords", "icon",
        "color_index", "archived", "sort_order", "created_at",
    ], None),
    ("budget_periods", [
        "id", "start_date", "end_date", "payroll_day", "expected_income",
        "opening_balance", "closed_at",
    ], None),
    ("budget_bills", [
        "id", "name", "amount", "due_day", "cadence", "category_id",
        "wallet_id", "autopost", "active", "created_at",
    ], None),
    ("budget_goals", [
        "id", "name", "kind", "target_amount", "target_date",
        "monthly_contribution", "reserve_from_free", "wallet_id", "archived",
        "created_at",
    ], None),
    ("budget_transactions", [
        "id", "occurred_at", "amount", "direction", "category_id", "wallet_id",
        "transfer_wallet_id", "period_id", "bill_id", "goal_id", "note",
        "source", "raw_input", "created_at", "deleted_at", "updated_at",
    ], None),
    ("budget_bill_payments", [
        "id", "bill_id", "period_id", "transaction_id", "paid_at",
    ], None),
    ("budget_goal_contributions", [
        "id", "goal_id", "transaction_id", "amount", "occurred_at",
    ], None),
    ("budget_alert_prefs", [
        "id", "daily_checkin_enabled", "daily_checkin_time", "bill_due_lead_days",
        "over_budget_enabled", "over_budget_threshold_pct",
        "low_daily_budget_threshold", "updated_at",
    ], None),
    ("budget_alert_log", ["id", "kind", "ref_key", "sent_at", "title", "body", "delivered", "read_at"], None),
    # Added by schema.py migration 2 (features/budget/wallet/ sync support).
    # budget_labels has no FK dependents listed above it, so it can sit
    # anywhere; budget_transaction_labels depends on both budget_transactions
    # (already listed above) and budget_labels, so it must come after both.
    ("budget_labels", ["id", "name", "color", "archived", "created_at"], None),
    ("budget_transaction_labels", ["transaction_id", "label_id"], None),
    ("budget_wallet_links", [
        "id", "entity_type", "local_id", "remote_id",
        "remote_updated_at", "local_synced_at", "last_direction",
    ], None),
]

# (table -> composite PK columns) for the one junction table with no
# single "id"/"key" column — _insert_sql()'s default ON CONFLICT target
# doesn't apply to it.
_COMPOSITE_PK = {"budget_transaction_labels": ("transaction_id", "label_id")}

# Tables whose "id" column is backed by a Postgres SERIAL sequence. Copying
# explicit id values via INSERT never advances that sequence, so the first
# unrelated INSERT after a migration collides on the primary key. Excludes
# budget_alert_prefs: its id is `INTEGER PRIMARY KEY CHECK (id = 1)`, a plain
# singleton column with no sequence — pg_get_serial_sequence returns NULL for
# it and setval(NULL, ...) raises.
SERIAL_TABLES = [
    table for table, columns, _ in TABLES
    if "id" in columns and table not in ("bot_state", "budget_alert_prefs")
]


def _pk_column(columns: list[str]) -> str:
    return "key" if "key" in columns else "id"


def _select_sql(table: str, columns: list[str]) -> str:
    return "SELECT " + ", ".join(columns) + " FROM " + table


def _insert_sql(table: str, columns: list[str]) -> str:
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))

    if table in _COMPOSITE_PK:
        pk_cols = _COMPOSITE_PK[table]
        conflict_target = ", ".join(pk_cols)
        update_cols = [c for c in columns if c not in pk_cols]
    else:
        pk_cols = (_pk_column(columns),)
        conflict_target = pk_cols[0]
        update_cols = [c for c in columns if c != pk_cols[0]]

    if update_cols:
        set_clause = ", ".join([c + " = EXCLUDED." + c for c in update_cols])
        conflict_action = "DO UPDATE SET " + set_clause
    else:
        conflict_action = "DO NOTHING"
    return (
        "INSERT INTO " + table + " (" + col_list + ") VALUES (" + placeholders + ") "
        "ON CONFLICT (" + conflict_target + ") " + conflict_action
    )


def _assert_target_schema(dst_cur):
    """Every table this script writes to must already exist on the target —
    i.e. init_db() (which calls init_budget_schema()) has been run against
    DATABASE_URL. Failing loudly here is much cheaper than debugging a
    migration that silently skipped every budget_* insert because the tables
    weren't there yet."""
    missing = []
    for table, _, _ in TABLES:
        dst_cur.execute("SELECT to_regclass(%s)", (table,))
        if dst_cur.fetchone()[0] is None:
            missing.append(table)
    if missing:
        raise SystemExit(
            "Target is missing table(s): " + ", ".join(missing) + ". "
            "Run `python -c \"from database import init_db; init_db()\"` "
            "against DATABASE_URL first."
        )


def _resync_sequences(dst_cur):
    """Advance every SERIAL sequence past the highest id just copied in, so
    the next INSERT that doesn't specify an id doesn't collide with one of
    the rows we just wrote."""
    for table in SERIAL_TABLES:
        dst_cur.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
            "COALESCE((SELECT MAX(id) FROM " + table + "), 1), true)",
            (table,),
        )


def migrate(dry_run: bool):
    if not os.path.exists(SQLITE_PATH):
        print("No SQLite source found at " + repr(SQLITE_PATH) + " — nothing to migrate.")
        return 1

    # Local dev now runs with DATABASE_URL empty (see environtment.env) so
    # db.py falls back to SQLite — this script still needs the real Neon
    # URL to migrate *into*, so it falls back to NEON_DATABASE_URL when
    # DATABASE_URL isn't set.
    database_url = (os.environ.get("DATABASE_URL", "").strip() or os.environ.get("NEON_DATABASE_URL", "").strip())
    if not database_url and not dry_run:
        print("Neither DATABASE_URL nor NEON_DATABASE_URL is set — nothing to migrate into.")
        return 1

    src = sqlite3.connect(SQLITE_PATH)
    dst = None
    dst_cur = None
    if not dry_run:
        import psycopg2
        dst = psycopg2.connect(database_url)
        dst_cur = dst.cursor()
        _assert_target_schema(dst_cur)

    target_label = "(not connected — dry run)"
    if database_url:
        target_label = database_url.split("@")[-1] if "@" in database_url else "(hidden)"
    print("Source: " + SQLITE_PATH)
    print("Target: " + target_label)
    print("Mode:   " + ("DRY RUN (no writes, no connection to target)" if dry_run else "LIVE"))
    print()

    total_copied = 0
    for table, columns, blob_col in TABLES:
        rows = src.execute(_select_sql(table, columns)).fetchall()
        insert_sql = _insert_sql(table, columns)

        copied = 0
        for row in rows:
            if not dry_run:
                values = list(row)
                if blob_col:
                    idx = columns.index(blob_col)
                    if values[idx] is not None:
                        import psycopg2
                        values[idx] = psycopg2.Binary(values[idx])
                dst_cur.execute(insert_sql, values)
            copied += 1

        action = "would be copied" if dry_run else "copied"
        print("  " + table.ljust(14) + str(copied).rjust(5) + " row(s) " + action)
        total_copied += copied

    if not dry_run:
        _resync_sequences(dst_cur)
        dst.commit()

    src.close()
    if dst is not None:
        dst_cur.close()
        dst.close()

    print()
    print("Total: " + str(total_copied) + " row(s) across " + str(len(TABLES)) + " tables.")
    if dry_run:
        print("Dry run only — re-run without --dry-run to write.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count rows without writing to Postgres")
    args = parser.parse_args()
    sys.exit(migrate(dry_run=args.dry_run))
