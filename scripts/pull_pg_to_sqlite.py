"""One-time (or occasional) data pull: copy every row from the Neon Postgres
database into the local bot.db (SQLite) — the mirror of
scripts/migrate_sqlite_to_pg.py, for the opposite direction. Exists because
local dev now runs against SQLite by default (see environtment.env's
DATABASE_URL comment) for speed, and this is how you get real production
data into that local copy when you want it.

Postgres is the source of truth here: every insert is INSERT OR REPLACE
keyed on whatever PRIMARY KEY/UNIQUE constraint bot.db already has for that
table (SQLite resolves this itself — unlike Postgres's ON CONFLICT, no
explicit conflict-target column list is needed), so a row that already
exists locally is overwritten with the Postgres version. Safe to re-run.

Reuses TABLES (and the FK-parent-first ordering it already encodes) from
migrate_sqlite_to_pg.py rather than re-declaring the same table/column list
a second time — one list, two scripts, so a future schema migration only
needs updating in one place.

Usage:
    python scripts/pull_pg_to_sqlite.py --dry-run   # counts only, no writes
    python scripts/pull_pg_to_sqlite.py             # actually copies

Requires:
    - NEON_DATABASE_URL (or DATABASE_URL) set to a reachable Postgres instance
    - bot.db already has the target schema (run once: `python -c "from
      database import init_db; init_db()"` with DATABASE_URL empty)
    - Port 5432 outbound reachable — some networks (notably some corporate
      ones) block it entirely; test with:
      `python -c "import socket; socket.create_connection(('<host>', 5432), 8)"`
"""
import argparse
import os
import sqlite3
import sys

from dotenv import load_dotenv
load_dotenv("environtment.env")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.migrate_sqlite_to_pg import TABLES, _select_sql  # noqa: E402

SQLITE_PATH = os.environ.get("DB_PATH", "bot.db")


def _assert_target_schema(sqlite_conn):
    cur = sqlite_conn.cursor()
    missing = []
    for table, _, _ in TABLES:
        row = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        if row is None:
            missing.append(table)
    if missing:
        raise SystemExit(
            "bot.db is missing table(s): " + ", ".join(missing) + ". "
            'Run `python -c "from database import init_db; init_db()"` '
            "(with DATABASE_URL empty, so it targets bot.db) first."
        )


def _insert_sql(table: str, columns: list[str]) -> str:
    col_list = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))
    return "INSERT OR REPLACE INTO " + table + " (" + col_list + ") VALUES (" + placeholders + ")"


def pull(dry_run: bool):
    database_url = (os.environ.get("NEON_DATABASE_URL", "").strip() or os.environ.get("DATABASE_URL", "").strip())
    if not database_url:
        print("Neither NEON_DATABASE_URL nor DATABASE_URL is set — nothing to pull from.")
        return 1

    import psycopg2
    src = psycopg2.connect(database_url)
    src_cur = src.cursor()

    dst = sqlite3.connect(SQLITE_PATH)
    if not dry_run:
        _assert_target_schema(dst)

    source_label = database_url.split("@")[-1] if "@" in database_url else "(hidden)"
    print("Source: " + source_label)
    print("Target: " + SQLITE_PATH)
    print("Mode:   " + ("DRY RUN (reads Postgres, writes nothing to bot.db)" if dry_run else "LIVE"))
    print()

    total_copied = 0
    for table, columns, blob_col in TABLES:
        src_cur.execute(_select_sql(table, columns))
        rows = src_cur.fetchall()
        insert_sql = _insert_sql(table, columns)

        copied = 0
        for row in rows:
            if not dry_run:
                values = list(row)
                if blob_col:
                    idx = columns.index(blob_col)
                    if values[idx] is not None and isinstance(values[idx], memoryview):
                        values[idx] = bytes(values[idx])
                dst.execute(insert_sql, values)
            copied += 1

        action = "would be copied" if dry_run else "copied"
        print("  " + table.ljust(24) + str(copied).rjust(5) + " row(s) " + action)
        total_copied += copied

    if not dry_run:
        dst.commit()

    src_cur.close()
    src.close()
    dst.close()

    print()
    print("Total: " + str(total_copied) + " row(s) across " + str(len(TABLES)) + " tables.")
    if dry_run:
        print("Dry run only — re-run without --dry-run to write.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count rows without writing to bot.db")
    args = parser.parse_args()
    sys.exit(pull(dry_run=args.dry_run))
