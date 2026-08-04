"""Dialect-neutral DB connection layer.

Uses Postgres when DATABASE_URL is set, else falls back to local SQLite
(DB_PATH). Every other module should get its connection from db_conn()
instead of calling sqlite3.connect() directly.
"""
import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "bot.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_PG = bool(DATABASE_URL)

if IS_PG:
    import psycopg2
    from psycopg2.pool import ThreadedConnectionPool

    # Every repo.py function opens-and-closes its own connection (by
    # design — see repo.py's docstring), and a single aggregate read like
    # GET /api/home or /api/budget fans out into 8-10 of them. Against a
    # remote Postgres host each fresh TCP+TLS handshake costs ~2-3s on
    # this network, so those endpoints were taking 20-30s (observed
    # hanging/timing out on the mobile app) even though every individual
    # query itself is trivial. Pooling reuses warm connections so repeat
    # db_conn() calls in the same process pay the handshake once, not
    # per-call.
    _pg_pool = ThreadedConnectionPool(1, 10, DATABASE_URL)


def q(sql: str) -> str:
    """Translate a sqlite-style '?' placeholder query to the active dialect."""
    return sql.replace("?", "%s") if IS_PG else sql


class _PGCursor:
    """Thin proxy around a psycopg2 cursor that adds a writable .lastrowid —
    psycopg2's own cursor exposes .lastrowid as a read-only C-level
    attribute, so it can't be set directly after an INSERT."""

    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    def __getattr__(self, name):
        return getattr(self._cur, name)


class _PGConn:
    """Wraps a psycopg2 connection so call sites can keep using the
    sqlite3.Connection shortcuts this codebase relies on everywhere:
    conn.execute(sql, params) returning a cursor with .lastrowid,
    conn.commit(), conn.close()."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(q(sql), params)
        return _PGCursor(cur, _pg_lastrowid(cur, sql))

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        """Returns the connection to the pool instead of closing the
        socket. A caller that hit an exception between db_conn() and
        close() (most repo.py functions have no try/finally — an
        INTEGRITY_ERROR mid-transaction is the realistic case) can leave
        the session in an aborted-transaction state; putconn() alone
        doesn't clear that, so the next borrower's first query would fail
        with 'current transaction is aborted'. Roll back first whenever
        the connection isn't idle. If the connection itself is broken,
        drop it from the pool entirely rather than recycling a dead
        socket."""
        try:
            if self._conn.closed:
                _pg_pool.putconn(self._conn, close=True)
                return
            if self._conn.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
                self._conn.rollback()
            _pg_pool.putconn(self._conn)
        except Exception:
            _pg_pool.putconn(self._conn, close=True)


def _pg_lastrowid(cur, sql):
    """Emulates sqlite3's cursor.lastrowid after an INSERT into a
    SERIAL/BIGSERIAL column. Relies on nothing else calling nextval()
    between the INSERT and this call within the same connection.

    lastval() raises ObjectNotInPrerequisiteState when the INSERT's table
    has no sequence-backed column (e.g. bot_state's TEXT primary key) —
    on a table with no sequence at all, or on the first statement of a
    fresh connection before any nextval() has run. Without a SAVEPOINT,
    that error aborts the whole transaction, and the caller's following
    conn.commit() then silently discards the INSERT with no exception
    raised — verified against a live Postgres instance. The SAVEPOINT
    contains the failure to just this probe."""
    if sql.strip().upper().startswith("INSERT"):
        try:
            cur.execute("SAVEPOINT _lastrowid_probe")
            cur.execute("SELECT lastval()")
            value = cur.fetchone()[0]
            cur.execute("RELEASE SAVEPOINT _lastrowid_probe")
            return value
        except Exception:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT _lastrowid_probe")
            except Exception:
                pass
            return None
    return None


def integrity_errors():
    """The exception tuple to catch for a UNIQUE/FK constraint violation,
    in whichever dialect is active — needed by any write that relies on a
    UNIQUE constraint as its concurrency guard (e.g. budget_bill_payments'
    UNIQUE(bill_id, period_id) for mark-paid)."""
    if IS_PG:
        return (psycopg2.IntegrityError,)
    return (sqlite3.IntegrityError,)


def db_conn():
    """Return a connection: Postgres when DATABASE_URL is set, else SQLite."""
    if IS_PG:
        return _PGConn(_pg_pool.getconn())
    conn = sqlite3.connect(DB_PATH)
    # ON DELETE SET NULL / CASCADE (used by the budget schema's foreign
    # keys) are silently inert on SQLite unless this is set per-connection.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
