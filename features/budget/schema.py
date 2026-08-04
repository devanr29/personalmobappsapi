"""Schema for the budget ledger. Versioned via bot_state['budget_schema_version']
rather than PRAGMA user_version, which is database-wide and would make this
feature the silent owner of a shared SQLite counter.

All statements are idempotent (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF
NOT EXISTS) so re-running a partially-applied migration step is safe.
"""
from database import state_get, state_set
from db import db_conn, IS_PG

_PK = "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY"


def _migration_0():
    return [
        f"""
        CREATE TABLE IF NOT EXISTS budget_wallets (
            id              {_PK},
            name            TEXT    NOT NULL UNIQUE,
            kind            TEXT    NOT NULL DEFAULT 'cash',
            opening_balance BIGINT  NOT NULL DEFAULT 0,
            spendable       INTEGER NOT NULL DEFAULT 1,
            is_default      INTEGER NOT NULL DEFAULT 0,
            archived        INTEGER NOT NULL DEFAULT 0,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT    NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS budget_categories (
            id            {_PK},
            name          TEXT    NOT NULL,
            kind          TEXT    NOT NULL,
            monthly_limit BIGINT,
            rollover      INTEGER NOT NULL DEFAULT 0,
            keywords      TEXT,    -- reserved; was read only by the removed quick-add NL parser
            icon          TEXT,
            color_index   INTEGER,
            archived      INTEGER NOT NULL DEFAULT 0,
            sort_order    INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT    NOT NULL,
            UNIQUE(name, kind)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS budget_periods (
            id              {_PK},
            start_date      TEXT    NOT NULL UNIQUE,
            end_date        TEXT    NOT NULL,
            payroll_day     INTEGER NOT NULL,
            expected_income BIGINT  NOT NULL DEFAULT 0,
            opening_balance BIGINT,
            closed_at       TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS budget_bills (
            id          {_PK},
            name        TEXT    NOT NULL,
            amount      BIGINT  NOT NULL,
            due_day     INTEGER,
            cadence     TEXT    NOT NULL DEFAULT 'monthly',
            category_id INTEGER REFERENCES budget_categories(id) ON DELETE SET NULL,
            wallet_id   INTEGER REFERENCES budget_wallets(id)    ON DELETE SET NULL,
            autopost    INTEGER NOT NULL DEFAULT 0,
            active      INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS budget_goals (
            id                   {_PK},
            name                 TEXT    NOT NULL,
            kind                 TEXT    NOT NULL DEFAULT 'sinking',
            target_amount        BIGINT  NOT NULL,
            target_date          TEXT,
            monthly_contribution BIGINT,
            reserve_from_free    INTEGER NOT NULL DEFAULT 1,
            wallet_id            INTEGER REFERENCES budget_wallets(id) ON DELETE SET NULL,
            archived             INTEGER NOT NULL DEFAULT 0,
            created_at           TEXT    NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS budget_transactions (
            id                 {_PK},
            occurred_at        TEXT    NOT NULL,
            amount             BIGINT  NOT NULL,
            direction          TEXT    NOT NULL,
            category_id        INTEGER REFERENCES budget_categories(id) ON DELETE SET NULL,
            wallet_id          INTEGER REFERENCES budget_wallets(id)    ON DELETE SET NULL,
            transfer_wallet_id INTEGER REFERENCES budget_wallets(id)    ON DELETE SET NULL,
            period_id          INTEGER REFERENCES budget_periods(id)    ON DELETE SET NULL,
            bill_id            INTEGER REFERENCES budget_bills(id)      ON DELETE SET NULL,
            goal_id            INTEGER REFERENCES budget_goals(id)      ON DELETE SET NULL,
            note               TEXT,
            source             TEXT    NOT NULL DEFAULT 'manual',
            raw_input          TEXT,
            created_at         TEXT    NOT NULL,
            deleted_at         TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_budget_txn_occurred ON budget_transactions(occurred_at)",
        "CREATE INDEX IF NOT EXISTS idx_budget_txn_period   ON budget_transactions(period_id, category_id)",
        "CREATE INDEX IF NOT EXISTS idx_budget_txn_wallet   ON budget_transactions(wallet_id)",
        "CREATE INDEX IF NOT EXISTS idx_budget_txn_bill     ON budget_transactions(bill_id)",
        "CREATE INDEX IF NOT EXISTS idx_budget_txn_live     ON budget_transactions(deleted_at, period_id)",
        f"""
        CREATE TABLE IF NOT EXISTS budget_bill_payments (
            id             {_PK},
            bill_id        INTEGER NOT NULL REFERENCES budget_bills(id)        ON DELETE CASCADE,
            period_id      INTEGER NOT NULL REFERENCES budget_periods(id)      ON DELETE CASCADE,
            transaction_id INTEGER          REFERENCES budget_transactions(id) ON DELETE SET NULL,
            paid_at        TEXT    NOT NULL,
            UNIQUE(bill_id, period_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS budget_goal_contributions (
            id             {_PK},
            goal_id        INTEGER NOT NULL REFERENCES budget_goals(id)        ON DELETE CASCADE,
            transaction_id INTEGER          REFERENCES budget_transactions(id) ON DELETE SET NULL,
            amount         BIGINT  NOT NULL,
            occurred_at    TEXT    NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS budget_alert_prefs (
            id                         INTEGER PRIMARY KEY CHECK (id = 1),
            daily_checkin_enabled      INTEGER NOT NULL DEFAULT 1,
            daily_checkin_time         TEXT    NOT NULL DEFAULT '20:00',
            bill_due_lead_days         INTEGER NOT NULL DEFAULT 2,
            over_budget_enabled        INTEGER NOT NULL DEFAULT 1,
            over_budget_threshold_pct  INTEGER NOT NULL DEFAULT 80,
            low_daily_budget_threshold BIGINT  NOT NULL DEFAULT 50000,
            updated_at                 TEXT    NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS budget_alert_log (
            id      {_PK},
            kind    TEXT NOT NULL,
            ref_key TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE(kind, ref_key)
        )
        """,
    ]


def _add_column_if_missing(conn, table, column, decl):
    """ALTER TABLE ... ADD COLUMN is not idempotent on SQLite (no IF NOT
    EXISTS support, unlike Postgres) — and every statement above is
    written to be safely re-runnable if a migration step crashes halfway
    through and re-executes on next boot. Probe first, in whichever
    dialect is active, to preserve that guarantee."""
    if IS_PG:
        exists = conn.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            (table, column),
        ).fetchone() is not None
    else:
        exists = any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})").fetchall())
    if not exists:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _migration_1():
    """Adds the fields the in-app alert inbox needs: a human-readable
    title/body (the log row itself becomes the inbox item, not just a
    dedupe marker), whether push delivery actually succeeded, and when
    the user read it."""
    def _add_alert_log_columns(conn):
        _add_column_if_missing(conn, "budget_alert_log", "title", "TEXT")
        _add_column_if_missing(conn, "budget_alert_log", "body", "TEXT")
        _add_column_if_missing(conn, "budget_alert_log", "delivered", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "budget_alert_log", "read_at", "TEXT")

    return [_add_alert_log_columns]


# MIGRATIONS[i] upgrades schema version i -> i+1.
MIGRATIONS = [_migration_0(), _migration_1()]
BUDGET_SCHEMA_VERSION = len(MIGRATIONS)


def init_budget_schema():
    current = int(state_get("budget_schema_version") or 0)
    if current >= BUDGET_SCHEMA_VERSION:
        return
    conn = db_conn()
    for step in MIGRATIONS[current:]:
        for statement in step:
            if callable(statement):
                statement(conn)
            else:
                conn.execute(statement)
    conn.commit()
    conn.close()
    state_set("budget_schema_version", str(BUDGET_SCHEMA_VERSION))
