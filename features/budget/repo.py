"""Raw CRUD over the budget ledger tables. No business logic — that lives
in compute.py (pure math) and service.py (orchestration). Every function
returns snake_case dicts; camelCase conversion happens once, in
serializers.py.

SQL text below is built by concatenation rather than f-strings/.format()
so it reads unambiguously as "identifiers from a fixed allowlist", never
as string-interpolated user input — every actual value still travels as a
bound parameter (the ? placeholders)."""
from config import now_jkt
from db import db_conn


def _int0(value) -> int:
    """SUM()/COALESCE() returns Decimal on Postgres (numeric) and int on
    SQLite. Flask's DefaultJSONProvider serializes Decimal as a JSON
    *string*, so an uncoerced aggregate would silently ship "350000"
    instead of 350000 and every client-side chart would render NaN.
    Coerce at the DB boundary, once, here."""
    return int(value or 0)


# ================================================================
# WALLETS
# ================================================================
_WALLET_COLS = "id, name, kind, opening_balance, spendable, is_default, archived, sort_order, created_at"


def _wallet_row(row):
    return {
        "id": row[0], "name": row[1], "kind": row[2], "opening_balance": row[3],
        "spendable": bool(row[4]), "is_default": bool(row[5]), "archived": bool(row[6]),
        "sort_order": row[7], "created_at": row[8],
    }


def create_wallet(name, kind="cash", opening_balance=0, spendable=True, is_default=False):
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO budget_wallets (name, kind, opening_balance, spendable, is_default, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, kind, opening_balance, int(spendable), int(is_default), str(now_jkt())),
    )
    wallet_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_wallet(wallet_id)


def get_wallets(include_archived=False, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    where = "" if include_archived else "WHERE archived = 0"
    sql = "SELECT " + _WALLET_COLS + " FROM budget_wallets " + where + " ORDER BY sort_order, id"
    rows = conn.execute(sql).fetchall()
    if owns_conn:
        conn.close()
    return [_wallet_row(r) for r in rows]


def get_wallet(wallet_id):
    conn = db_conn()
    sql = "SELECT " + _WALLET_COLS + " FROM budget_wallets WHERE id = ?"
    row = conn.execute(sql, (wallet_id,)).fetchone()
    conn.close()
    return _wallet_row(row) if row else None


def get_default_wallet():
    conn = db_conn()
    sql = "SELECT " + _WALLET_COLS + " FROM budget_wallets WHERE is_default = 1 AND archived = 0 LIMIT 1"
    row = conn.execute(sql).fetchone()
    conn.close()
    return _wallet_row(row) if row else None


_WALLET_UPDATABLE = {"name", "kind", "opening_balance", "spendable", "is_default", "archived", "sort_order"}
_WALLET_BOOL_FIELDS = {"spendable", "is_default", "archived"}


def update_wallet(wallet_id, **fields):
    if not fields:
        return get_wallet(wallet_id)
    sets, params = [], []
    for key, value in fields.items():
        if key not in _WALLET_UPDATABLE:
            continue
        if key in _WALLET_BOOL_FIELDS:
            value = int(value)
        sets.append(key + " = ?")
        params.append(value)
    if not sets:
        return get_wallet(wallet_id)
    params.append(wallet_id)
    conn = db_conn()
    sql = "UPDATE budget_wallets SET " + ", ".join(sets) + " WHERE id = ?"
    conn.execute(sql, params)
    conn.commit()
    conn.close()
    return get_wallet(wallet_id)


def wallet_in_use(wallet_id) -> bool:
    """Transactions, bills, or goals referencing this wallet. All three FKs
    are ON DELETE SET NULL, so a hard delete_wallet() call would silently
    orphan those rows instead of failing — this guard is the only thing
    standing between a mistap and unrecoverable balance corruption (the
    money in a deleted wallet's transactions just vanishes from
    money_in_hand(), since balances are summed per-wallet)."""
    conn = db_conn()
    in_txns = conn.execute(
        "SELECT 1 FROM budget_transactions WHERE (wallet_id = ? OR transfer_wallet_id = ?) AND deleted_at IS NULL LIMIT 1",
        (wallet_id, wallet_id),
    ).fetchone()
    in_bills = conn.execute(
        "SELECT 1 FROM budget_bills WHERE wallet_id = ? LIMIT 1", (wallet_id,)
    ).fetchone()
    in_goals = conn.execute(
        "SELECT 1 FROM budget_goals WHERE wallet_id = ? LIMIT 1", (wallet_id,)
    ).fetchone()
    conn.close()
    return in_txns is not None or in_bills is not None or in_goals is not None


def delete_wallet(wallet_id):
    conn = db_conn()
    conn.execute("DELETE FROM budget_wallets WHERE id = ?", (wallet_id,))
    conn.commit()
    conn.close()


def wallet_balances(conn=None) -> dict:
    """{wallet_id: balance} for every wallet (including archived — callers
    filter as needed) in 3 queries total, instead of 4 per wallet.

    'adjustment' is signed and applies at face value (positive tops up a
    wallet, negative reduces it — reconcile.py's contract); 'transfer'
    leaves wallet_id (debited) and lands in transfer_wallet_id (credited)."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    wallets = conn.execute("SELECT id, opening_balance FROM budget_wallets").fetchall()
    out = {row[0]: _int0(row[1]) for row in wallets}

    for wallet_id, delta in conn.execute(
        "SELECT wallet_id, "
        "SUM(CASE WHEN direction = 'income'     THEN  amount "
        "         WHEN direction = 'adjustment' THEN  amount "
        "         WHEN direction = 'expense'    THEN -amount "
        "         WHEN direction = 'transfer'   THEN -amount "
        "         ELSE 0 END) "
        "FROM budget_transactions "
        "WHERE deleted_at IS NULL AND wallet_id IS NOT NULL "
        "GROUP BY wallet_id"
    ).fetchall():
        if wallet_id in out:
            out[wallet_id] += _int0(delta)

    for wallet_id, delta in conn.execute(
        "SELECT transfer_wallet_id, SUM(amount) FROM budget_transactions "
        "WHERE deleted_at IS NULL AND direction = 'transfer' "
        "AND transfer_wallet_id IS NOT NULL GROUP BY transfer_wallet_id"
    ).fetchall():
        if wallet_id in out:
            out[wallet_id] += _int0(delta)

    if owns_conn:
        conn.close()
    return out


def wallet_balance(wallet_id) -> int:
    return wallet_balances().get(wallet_id, 0)


def money_in_hand(conn=None, wallets=None, balances=None) -> int:
    """Sum of every spendable, non-archived wallet's balance. Pass
    `wallets` when the caller already fetched the non-archived list (e.g.
    build_period_view() needs it anyway to check the "not set up" case),
    and `balances` when the caller also needs the full per-wallet dict for
    its own response (build_period_view() does, for the breakdown's
    wallet strip) — either skips a redundant identical query."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    if balances is None:
        balances = wallet_balances(conn=conn)
    if wallets is None:
        wallets = get_wallets(include_archived=False, conn=conn)
    if owns_conn:
        conn.close()
    return sum(balances.get(w["id"], 0) for w in wallets if w["spendable"])


# ================================================================
# CATEGORIES
# ================================================================
_CATEGORY_COLS = (
    "id, name, kind, monthly_limit, rollover, keywords, icon, color_index, "
    "archived, sort_order, created_at"
)


def _category_row(row):
    return {
        "id": row[0], "name": row[1], "kind": row[2], "monthly_limit": row[3],
        "rollover": bool(row[4]), "keywords": row[5], "icon": row[6], "color_index": row[7],
        "archived": bool(row[8]), "sort_order": row[9], "created_at": row[10],
    }


def create_category(name, kind, monthly_limit=None, rollover=False, keywords=None, icon=None, color_index=None):
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO budget_categories (name, kind, monthly_limit, rollover, keywords, icon, color_index, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, kind, monthly_limit, int(rollover), keywords, icon, color_index, str(now_jkt())),
    )
    category_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_category(category_id)


def get_categories(include_archived=False, kind=None, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    clauses = [] if include_archived else ["archived = 0"]
    params = []
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = "SELECT " + _CATEGORY_COLS + " FROM budget_categories " + where + " ORDER BY sort_order, id"
    rows = conn.execute(sql, params).fetchall()
    if owns_conn:
        conn.close()
    return [_category_row(r) for r in rows]


def get_category(category_id):
    conn = db_conn()
    sql = "SELECT " + _CATEGORY_COLS + " FROM budget_categories WHERE id = ?"
    row = conn.execute(sql, (category_id,)).fetchone()
    conn.close()
    return _category_row(row) if row else None


_CATEGORY_UPDATABLE = {
    "name", "kind", "monthly_limit", "rollover", "keywords", "icon",
    "color_index", "archived", "sort_order",
}
_CATEGORY_BOOL_FIELDS = {"rollover", "archived"}


def update_category(category_id, **fields):
    if not fields:
        return get_category(category_id)
    sets, params = [], []
    for key, value in fields.items():
        if key not in _CATEGORY_UPDATABLE:
            continue
        if key in _CATEGORY_BOOL_FIELDS:
            value = int(value)
        sets.append(key + " = ?")
        params.append(value)
    if not sets:
        return get_category(category_id)
    params.append(category_id)
    conn = db_conn()
    sql = "UPDATE budget_categories SET " + ", ".join(sets) + " WHERE id = ?"
    conn.execute(sql, params)
    conn.commit()
    conn.close()
    return get_category(category_id)


def category_in_use(category_id) -> bool:
    conn = db_conn()
    in_txns = conn.execute(
        "SELECT 1 FROM budget_transactions WHERE category_id = ? AND deleted_at IS NULL LIMIT 1",
        (category_id,),
    ).fetchone()
    in_bills = conn.execute(
        "SELECT 1 FROM budget_bills WHERE category_id = ? LIMIT 1", (category_id,)
    ).fetchone()
    in_payments = conn.execute(
        "SELECT 1 FROM budget_category_payments WHERE category_id = ? LIMIT 1", (category_id,)
    ).fetchone()
    conn.close()
    return in_txns is not None or in_bills is not None or in_payments is not None


def delete_category(category_id):
    conn = db_conn()
    conn.execute("DELETE FROM budget_categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()


def get_paid_category_ids(period_id, conn=None) -> set:
    """Mirrors get_paid_bill_ids(): every category with a
    budget_category_payments row for this period, regardless of whether
    that row is backed by a real transaction."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute(
        "SELECT category_id FROM budget_category_payments WHERE period_id = ?", (period_id,)
    ).fetchall()
    if owns_conn:
        conn.close()
    return {r[0] for r in rows}


def create_category_payment(category_id, period_id, transaction_id, paid_at):
    """Mirrors create_bill_payment(): UNIQUE(category_id, period_id) is
    service.pay_variable_category()'s real concurrency guard against
    double-marking a category paid in one period."""
    conn = db_conn()
    try:
        cur = conn.execute(
            "INSERT INTO budget_category_payments (category_id, period_id, transaction_id, paid_at) VALUES (?, ?, ?, ?)",
            (category_id, period_id, transaction_id, paid_at),
        )
        payment_id = cur.lastrowid
        conn.commit()
        return payment_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_category_payment(category_id, period_id):
    conn = db_conn()
    row = conn.execute(
        "SELECT id, category_id, period_id, transaction_id, paid_at FROM budget_category_payments "
        "WHERE category_id = ? AND period_id = ?",
        (category_id, period_id),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {"id": row[0], "category_id": row[1], "period_id": row[2], "transaction_id": row[3], "paid_at": row[4]}


def delete_category_payment(category_id, period_id):
    conn = db_conn()
    conn.execute(
        "DELETE FROM budget_category_payments WHERE category_id = ? AND period_id = ?", (category_id, period_id)
    )
    conn.commit()
    conn.close()


def spend_by_category(category_id, period_id) -> int:
    conn = db_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions "
        "WHERE category_id = ? AND period_id = ? AND direction = 'expense' AND deleted_at IS NULL",
        (category_id, period_id),
    ).fetchone()
    conn.close()
    return _int0(row[0])


def spend_by_category_for_period(period_id, conn=None) -> list:
    """One query for every category's spend this period, in id-grouped
    rows — replaces the N-query per-category loop build_period_view() used
    to run. t.category_id IS NULL groups into a single row (the
    "uncategorized" bucket), which callers must not filter out. Every
    selected non-aggregate column is in GROUP BY — Postgres requires it,
    SQLite doesn't enforce it but accepts it identically."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute(
        "SELECT t.category_id, c.name, COALESCE(SUM(t.amount), 0) "
        "FROM budget_transactions t "
        "LEFT JOIN budget_categories c ON c.id = t.category_id "
        "WHERE t.period_id = ? AND t.direction = 'expense' AND t.deleted_at IS NULL "
        "GROUP BY t.category_id, c.name",
        (period_id,),
    ).fetchall()
    if owns_conn:
        conn.close()
    return [{"category_id": r[0], "category_name": r[1], "spend": _int0(r[2])} for r in rows]


# ================================================================
# BILLS
# ================================================================
_BILL_COLS = "id, name, amount, due_day, cadence, category_id, wallet_id, autopost, active, created_at"


def _bill_row(row):
    return {
        "id": row[0], "name": row[1], "amount": row[2], "due_day": row[3],
        "cadence": row[4], "category_id": row[5], "wallet_id": row[6],
        "autopost": bool(row[7]), "active": bool(row[8]), "created_at": row[9],
    }


def get_bills(active_only=True, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    where = "WHERE active = 1" if active_only else ""
    sql = "SELECT " + _BILL_COLS + " FROM budget_bills " + where + " ORDER BY id"
    rows = conn.execute(sql).fetchall()
    if owns_conn:
        conn.close()
    return [_bill_row(r) for r in rows]


def get_bill(bill_id):
    conn = db_conn()
    sql = "SELECT " + _BILL_COLS + " FROM budget_bills WHERE id = ?"
    row = conn.execute(sql, (bill_id,)).fetchone()
    conn.close()
    return _bill_row(row) if row else None


def create_bill(name, amount, due_day=None, category_id=None, wallet_id=None, cadence="monthly", autopost=False):
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO budget_bills (name, amount, due_day, cadence, category_id, wallet_id, autopost, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, amount, due_day, cadence, category_id, wallet_id, int(autopost), str(now_jkt())),
    )
    bill_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_bill(bill_id)


_BILL_UPDATABLE = {"name", "amount", "due_day", "cadence", "category_id", "wallet_id", "autopost", "active"}
_BILL_BOOL_FIELDS = {"autopost", "active"}


def update_bill(bill_id, **fields):
    if not fields:
        return get_bill(bill_id)
    sets, params = [], []
    for key, value in fields.items():
        if key not in _BILL_UPDATABLE:
            continue
        if key in _BILL_BOOL_FIELDS:
            value = int(value)
        sets.append(key + " = ?")
        params.append(value)
    if not sets:
        return get_bill(bill_id)
    params.append(bill_id)
    conn = db_conn()
    sql = "UPDATE budget_bills SET " + ", ".join(sets) + " WHERE id = ?"
    conn.execute(sql, params)
    conn.commit()
    conn.close()
    return get_bill(bill_id)


def bill_in_use(bill_id) -> bool:
    conn = db_conn()
    in_payments = conn.execute(
        "SELECT 1 FROM budget_bill_payments WHERE bill_id = ? LIMIT 1", (bill_id,)
    ).fetchone()
    in_txns = conn.execute(
        "SELECT 1 FROM budget_transactions WHERE bill_id = ? AND deleted_at IS NULL LIMIT 1", (bill_id,)
    ).fetchone()
    conn.close()
    return in_payments is not None or in_txns is not None


def delete_bill(bill_id):
    conn = db_conn()
    conn.execute("DELETE FROM budget_bills WHERE id = ?", (bill_id,))
    conn.commit()
    conn.close()


def get_paid_bill_ids(period_id, conn=None) -> set:
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute(
        "SELECT bill_id FROM budget_bill_payments WHERE period_id = ?", (period_id,)
    ).fetchall()
    if owns_conn:
        conn.close()
    return {r[0] for r in rows}


def create_bill_payment(bill_id, period_id, transaction_id, paid_at):
    """UNIQUE(bill_id, period_id) is service.pay_bill()'s real concurrency
    guard against double-paying a bill in one period — a pre-check SELECT
    would only narrow the race, not close it. On a violation the INSERT
    raises before conn.commit(); this still must roll back and close the
    connection explicitly (rather than leaving it to fall out of scope),
    or on Postgres the failed statement leaves an uncommitted transaction
    open on that connection until the server eventually reclaims it."""
    conn = db_conn()
    try:
        cur = conn.execute(
            "INSERT INTO budget_bill_payments (bill_id, period_id, transaction_id, paid_at) VALUES (?, ?, ?, ?)",
            (bill_id, period_id, transaction_id, paid_at),
        )
        payment_id = cur.lastrowid
        conn.commit()
        return payment_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_bill_payment(bill_id, period_id):
    conn = db_conn()
    row = conn.execute(
        "SELECT id, bill_id, period_id, transaction_id, paid_at FROM budget_bill_payments "
        "WHERE bill_id = ? AND period_id = ?",
        (bill_id, period_id),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {"id": row[0], "bill_id": row[1], "period_id": row[2], "transaction_id": row[3], "paid_at": row[4]}


def delete_bill_payment(bill_id, period_id):
    conn = db_conn()
    conn.execute(
        "DELETE FROM budget_bill_payments WHERE bill_id = ? AND period_id = ?", (bill_id, period_id)
    )
    conn.commit()
    conn.close()


def ensure_alert_prefs():
    """Idempotent insert of the singleton alert-prefs row. Shared by the
    Sheets seed and the setup wizard — both need the row to exist before
    GET/PATCH /budget/alerts/prefs works."""
    from db import IS_PG
    insert_sql = (
        "INSERT INTO budget_alert_prefs (id, updated_at) VALUES (1, ?) ON CONFLICT (id) DO NOTHING"
        if IS_PG else
        "INSERT OR IGNORE INTO budget_alert_prefs (id, updated_at) VALUES (1, ?)"
    )
    conn = db_conn()
    conn.execute(insert_sql, (str(now_jkt()),))
    conn.commit()
    conn.close()


_ALERT_PREFS_COLS = (
    "daily_checkin_enabled, daily_checkin_time, bill_due_lead_days, "
    "over_budget_enabled, over_budget_threshold_pct, low_daily_budget_threshold, updated_at"
)


def get_alert_prefs():
    ensure_alert_prefs()
    conn = db_conn()
    row = conn.execute("SELECT " + _ALERT_PREFS_COLS + " FROM budget_alert_prefs WHERE id = 1").fetchone()
    conn.close()
    return {
        "daily_checkin_enabled": bool(row[0]), "daily_checkin_time": row[1],
        "bill_due_lead_days": row[2], "over_budget_enabled": bool(row[3]),
        "over_budget_threshold_pct": row[4], "low_daily_budget_threshold": row[5],
        "updated_at": row[6],
    }


_ALERT_PREFS_UPDATABLE = {
    "daily_checkin_enabled", "daily_checkin_time", "bill_due_lead_days",
    "over_budget_enabled", "over_budget_threshold_pct", "low_daily_budget_threshold",
}
_ALERT_PREFS_BOOL_FIELDS = {"daily_checkin_enabled", "over_budget_enabled"}


def update_alert_prefs(**fields):
    ensure_alert_prefs()
    sets, params = [], []
    for key, value in fields.items():
        if key not in _ALERT_PREFS_UPDATABLE:
            continue
        if key in _ALERT_PREFS_BOOL_FIELDS:
            value = int(value)
        sets.append(key + " = ?")
        params.append(value)
    if sets:
        sets.append("updated_at = ?")
        params.append(str(now_jkt()))
        conn = db_conn()
        conn.execute("UPDATE budget_alert_prefs SET " + ", ".join(sets) + " WHERE id = 1", params)
        conn.commit()
        conn.close()
    return get_alert_prefs()


def create_alert_log(kind, ref_key, title, body):
    """Raises the dialect's IntegrityError on a UNIQUE(kind, ref_key)
    violation — that's the dedupe guard, callers (alerts.run_budget_alerts)
    catch it and treat it as 'already fired, skip'."""
    conn = db_conn()
    try:
        conn.execute(
            "INSERT INTO budget_alert_log (kind, ref_key, sent_at, title, body, delivered) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (kind, ref_key, str(now_jkt()), title, body),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_alert_delivered(kind, ref_key):
    conn = db_conn()
    conn.execute(
        "UPDATE budget_alert_log SET delivered = 1 WHERE kind = ? AND ref_key = ?", (kind, ref_key)
    )
    conn.commit()
    conn.close()


_ALERT_LOG_COLS = "id, kind, ref_key, sent_at, title, body, delivered, read_at"


def _alert_row(row):
    return {
        "id": row[0], "kind": row[1], "ref_key": row[2], "sent_at": row[3],
        "title": row[4], "body": row[5], "delivered": bool(row[6]), "read_at": row[7],
    }


def get_alerts(unread_only=False, limit=20):
    conn = db_conn()
    where = "WHERE read_at IS NULL" if unread_only else ""
    sql = (
        "SELECT " + _ALERT_LOG_COLS + " FROM budget_alert_log " + where +
        " ORDER BY sent_at DESC, id DESC LIMIT ?"
    )
    rows = conn.execute(sql, (limit,)).fetchall()
    unread = conn.execute("SELECT COUNT(*) FROM budget_alert_log WHERE read_at IS NULL").fetchone()[0]
    conn.close()
    return [_alert_row(r) for r in rows], unread


def mark_alert_read(alert_id):
    conn = db_conn()
    conn.execute(
        "UPDATE budget_alert_log SET read_at = ? WHERE id = ? AND read_at IS NULL",
        (str(now_jkt()), alert_id),
    )
    conn.commit()
    conn.close()


# ================================================================
# GOALS — sinking funds / savings targets. reserve_from_free drives
# whether service.goal_reservations() folds this goal into
# total_still_owed; contributions are tracked separately from the
# reservation math so "how much has actually been set aside" and "how
# much should still be reserved this period" never get conflated.
# ================================================================
_GOAL_COLS = (
    "id, name, kind, target_amount, target_date, monthly_contribution, "
    "reserve_from_free, wallet_id, archived, created_at"
)


def _goal_row(row):
    return {
        "id": row[0], "name": row[1], "kind": row[2], "target_amount": row[3],
        "target_date": row[4], "monthly_contribution": row[5],
        "reserve_from_free": bool(row[6]), "wallet_id": row[7],
        "archived": bool(row[8]), "created_at": row[9],
    }


def create_goal(name, target_amount, kind="sinking", target_date=None,
                monthly_contribution=None, reserve_from_free=True, wallet_id=None):
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO budget_goals "
        "(name, kind, target_amount, target_date, monthly_contribution, reserve_from_free, wallet_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, kind, target_amount, target_date, monthly_contribution,
         int(reserve_from_free), wallet_id, str(now_jkt())),
    )
    goal_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_goal(goal_id)


def get_goals(include_archived=False, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    where = "" if include_archived else "WHERE archived = 0"
    sql = "SELECT " + _GOAL_COLS + " FROM budget_goals " + where + " ORDER BY id"
    rows = conn.execute(sql).fetchall()
    if owns_conn:
        conn.close()
    return [_goal_row(r) for r in rows]


def get_goal(goal_id):
    conn = db_conn()
    sql = "SELECT " + _GOAL_COLS + " FROM budget_goals WHERE id = ?"
    row = conn.execute(sql, (goal_id,)).fetchone()
    conn.close()
    return _goal_row(row) if row else None


_GOAL_UPDATABLE = {
    "name", "kind", "target_amount", "target_date", "monthly_contribution",
    "reserve_from_free", "wallet_id", "archived",
}
_GOAL_BOOL_FIELDS = {"reserve_from_free", "archived"}


def update_goal(goal_id, **fields):
    if not fields:
        return get_goal(goal_id)
    sets, params = [], []
    for key, value in fields.items():
        if key not in _GOAL_UPDATABLE:
            continue
        if key in _GOAL_BOOL_FIELDS:
            value = int(value)
        sets.append(key + " = ?")
        params.append(value)
    if not sets:
        return get_goal(goal_id)
    params.append(goal_id)
    conn = db_conn()
    sql = "UPDATE budget_goals SET " + ", ".join(sets) + " WHERE id = ?"
    conn.execute(sql, params)
    conn.commit()
    conn.close()
    return get_goal(goal_id)


def goal_in_use(goal_id) -> bool:
    conn = db_conn()
    row = conn.execute(
        "SELECT 1 FROM budget_goal_contributions WHERE goal_id = ? LIMIT 1", (goal_id,)
    ).fetchone()
    conn.close()
    return row is not None


def delete_goal(goal_id):
    conn = db_conn()
    conn.execute("DELETE FROM budget_goals WHERE id = ?", (goal_id,))
    conn.commit()
    conn.close()


def goal_saved(goal_id, conn=None) -> int:
    """Total ever contributed to this goal, all-time."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM budget_goal_contributions WHERE goal_id = ?", (goal_id,)
    ).fetchone()
    if owns_conn:
        conn.close()
    return _int0(row[0])


def goal_contributed_in_period(goal_id, start_date, end_date, conn=None) -> int:
    """Contributed within [start_date, end_date) — same half-open
    convention as a budget period. occurred_at is TEXT; comparing against
    a 10-char date bound works the same way date_from/date_to do
    elsewhere (a bare date sorts before any same-day timestamp)."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM budget_goal_contributions "
        "WHERE goal_id = ? AND occurred_at >= ? AND occurred_at < ?",
        (goal_id, start_date, end_date),
    ).fetchone()
    if owns_conn:
        conn.close()
    return _int0(row[0])


def create_goal_contribution(goal_id, transaction_id, amount, occurred_at):
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO budget_goal_contributions (goal_id, transaction_id, amount, occurred_at) "
        "VALUES (?, ?, ?, ?)",
        (goal_id, transaction_id, amount, occurred_at),
    )
    contribution_id = cur.lastrowid
    conn.commit()
    conn.close()
    return contribution_id


# ================================================================
# TRANSACTIONS
# ================================================================
_TXN_COLS = (
    "id, occurred_at, amount, direction, category_id, wallet_id, transfer_wallet_id, "
    "period_id, bill_id, goal_id, note, source, raw_input, created_at, deleted_at, updated_at"
)
_TXN_COLS_LIST = [c.strip() for c in _TXN_COLS.split(",")]

# Joined variant for list queries: pulls category/wallet names in the same
# query instead of camel_transaction() issuing 2 extra lookups per row
# (each opening its own connection — 50 rows was 101 connections).
_TXN_LIST_SQL = (
    "SELECT " + ", ".join("t." + c for c in _TXN_COLS_LIST) + ", "
    "c.name AS category_name, w.name AS wallet_name "
    "FROM budget_transactions t "
    "LEFT JOIN budget_categories c ON c.id = t.category_id "
    "LEFT JOIN budget_wallets    w ON w.id = t.wallet_id "
)


def _txn_row(row):
    return {
        "id": row[0], "occurred_at": row[1], "amount": row[2], "direction": row[3],
        "category_id": row[4], "wallet_id": row[5], "transfer_wallet_id": row[6],
        "period_id": row[7], "bill_id": row[8], "goal_id": row[9], "note": row[10],
        "source": row[11], "raw_input": row[12], "created_at": row[13], "deleted_at": row[14],
        "updated_at": row[15],
    }


def _txn_list_row(row):
    txn = _txn_row(row)
    txn["category_name"] = row[16]
    txn["wallet_name"] = row[17]
    return txn


def create_transaction(
    amount, direction, category_id=None, wallet_id=None, transfer_wallet_id=None,
    period_id=None, bill_id=None, goal_id=None, note=None, source="manual",
    raw_input=None, occurred_at=None,
):
    occurred_at = occurred_at or now_jkt().strftime("%Y-%m-%d %H:%M")
    now = str(now_jkt())
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO budget_transactions "
        "(occurred_at, amount, direction, category_id, wallet_id, transfer_wallet_id, "
        " period_id, bill_id, goal_id, note, source, raw_input, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (occurred_at, amount, direction, category_id, wallet_id, transfer_wallet_id,
         period_id, bill_id, goal_id, note, source, raw_input, now, now),
    )
    txn_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_transaction(txn_id)


def get_transaction(txn_id):
    conn = db_conn()
    sql = "SELECT " + _TXN_COLS + " FROM budget_transactions WHERE id = ?"
    row = conn.execute(sql, (txn_id,)).fetchone()
    conn.close()
    return _txn_row(row) if row else None


def get_active_transactions(conn=None) -> list:
    """Every non-deleted transaction, full rows — the push side
    (features/budget/wallet/sync.py) scans this to find local rows that
    need creating or updating remotely. Unlike get_transactions(), no
    pagination/filtering: a push run needs to see everything eligible."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute("SELECT " + _TXN_COLS + " FROM budget_transactions WHERE deleted_at IS NULL").fetchall()
    if owns_conn:
        conn.close()
    return [_txn_row(r) for r in rows]


def get_deleted_transaction_ids(conn=None) -> list:
    """Local ids soft-deleted here but possibly still linked to a Wallet
    record — the push side's delete pass."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute("SELECT id FROM budget_transactions WHERE deleted_at IS NOT NULL").fetchall()
    if owns_conn:
        conn.close()
    return [r[0] for r in rows]


def get_transactions(period_id=None, category_id=None, wallet_id=None, direction=None,
                      date_from=None, date_to=None, limit=50, offset=0):
    clauses = ["t.deleted_at IS NULL"]
    params = []
    if period_id is not None:
        clauses.append("t.period_id = ?")
        params.append(period_id)
    if category_id is not None:
        clauses.append("t.category_id = ?")
        params.append(category_id)
    if wallet_id is not None:
        clauses.append("t.wallet_id = ?")
        params.append(wallet_id)
    if direction is not None:
        clauses.append("t.direction = ?")
        params.append(direction)
    if date_from is not None:
        clauses.append("t.occurred_at >= ?")
        params.append(date_from)
    if date_to is not None:
        clauses.append("t.occurred_at <= ?")
        params.append(date_to)
    where = "WHERE " + " AND ".join(clauses)

    conn = db_conn()
    count_sql = "SELECT COUNT(*) FROM budget_transactions t " + where
    total = conn.execute(count_sql, params).fetchone()[0]
    list_sql = (
        _TXN_LIST_SQL + where +
        " ORDER BY t.occurred_at DESC, t.id DESC LIMIT ? OFFSET ?"
    )
    rows = conn.execute(list_sql, params + [limit, offset]).fetchall()
    conn.close()
    return [_txn_list_row(r) for r in rows], total


_TXN_UPDATABLE = {
    "occurred_at", "amount", "direction", "category_id", "wallet_id",
    "transfer_wallet_id", "period_id", "bill_id", "goal_id", "note",
}


def update_transaction(txn_id, **fields):
    if not fields:
        return get_transaction(txn_id)
    sets, params = [], []
    for key, value in fields.items():
        if key not in _TXN_UPDATABLE:
            continue
        sets.append(key + " = ?")
        params.append(value)
    if not sets:
        return get_transaction(txn_id)
    # updated_at drives the Wallet sync push side (features/budget/wallet/):
    # a row with no link row, or with updated_at newer than the link's
    # local_synced_at, is what "changed locally since last sync" means.
    # Stamped on every real field change, never on a no-op call.
    sets.append("updated_at = ?")
    params.append(str(now_jkt()))
    params.append(txn_id)
    conn = db_conn()
    sql = "UPDATE budget_transactions SET " + ", ".join(sets) + " WHERE id = ?"
    conn.execute(sql, params)
    conn.commit()
    conn.close()
    return get_transaction(txn_id)


def soft_delete_transaction(txn_id):
    now = str(now_jkt())
    conn = db_conn()
    conn.execute(
        "UPDATE budget_transactions SET deleted_at = ?, updated_at = ? WHERE id = ?",
        (now, now, txn_id),
    )
    conn.commit()
    conn.close()
    return get_transaction(txn_id)


# ================================================================
# AGGREGATES — for the insights/graphs layer. SQL only, no math (that
# lives in insights.py, kept pure and DB-free the same way compute.py is).
#
# Dual-dialect date bucketing: substr(col, 1, 10) is the day key and
# substr(col, 1, 7) is the month key — the only date-truncation construct
# that behaves identically on SQLite and Postgres (no strftime, no
# date_trunc/EXTRACT, no SUBSTRING(x FROM..FOR..)). Every SUM() goes
# through _int0(). Booleans compare against 1, never IS TRUE.
# ================================================================
def daily_buckets_for_period(period_id, conn=None) -> list:
    """One row per calendar day that has activity this period. spend and
    variable_spend are reported separately — variable_spend excludes
    'fixed'-kind category spend, which is what the pace chart needs (a
    big rent bill posting mid-period must not read as blowing the
    variable budget). transfer/adjustment fall through every CASE to 0."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute(
        "SELECT substr(t.occurred_at, 1, 10) AS day, "
        "SUM(CASE WHEN t.direction = 'expense' THEN t.amount ELSE 0 END), "
        "SUM(CASE WHEN t.direction = 'expense' AND c.kind = 'variable' THEN t.amount ELSE 0 END), "
        "SUM(CASE WHEN t.direction = 'income' THEN t.amount ELSE 0 END), "
        "COUNT(CASE WHEN t.direction = 'expense' THEN 1 END) "
        "FROM budget_transactions t "
        "LEFT JOIN budget_categories c ON c.id = t.category_id "
        "WHERE t.deleted_at IS NULL AND t.period_id = ? "
        "GROUP BY substr(t.occurred_at, 1, 10) "
        "ORDER BY substr(t.occurred_at, 1, 10)",
        (period_id,),
    ).fetchall()
    if owns_conn:
        conn.close()
    return [
        {"date": r[0], "spend": _int0(r[1]), "variable_spend": _int0(r[2]), "income": _int0(r[3]), "count": r[4]}
        for r in rows
    ]


def category_spend_ranked_for_period(period_id, conn=None) -> list:
    """Every category with expense spend this period, ranked desc, ties
    broken by category_id for a deterministic order across refetches
    (otherwise the sequential-ramp chart colors would flicker). t.category_id
    IS NULL groups into one 'Uncategorized' row and must not be filtered."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute(
        "SELECT t.category_id, c.name, c.kind, c.monthly_limit, SUM(t.amount), COUNT(*) "
        "FROM budget_transactions t "
        "LEFT JOIN budget_categories c ON c.id = t.category_id "
        "WHERE t.deleted_at IS NULL AND t.period_id = ? AND t.direction = 'expense' "
        "GROUP BY t.category_id, c.name, c.kind, c.monthly_limit "
        "ORDER BY SUM(t.amount) DESC, t.category_id",
        (period_id,),
    ).fetchall()
    if owns_conn:
        conn.close()
    return [
        {"category_id": r[0], "name": r[1], "kind": r[2], "monthly_limit": r[3], "spend": _int0(r[4]), "count": r[5]}
        for r in rows
    ]


def period_totals(limit=6) -> list:
    """The most recent `limit` periods, ascending (oldest first — reversed
    after the DESC/LIMIT so the limit applies to the right end of the
    range). The deleted_at filter lives in the JOIN condition, not WHERE —
    putting it in WHERE would degrade the LEFT JOIN to an INNER JOIN and
    drop periods with zero transactions from the history entirely."""
    conn = db_conn()
    rows = conn.execute(
        "SELECT p.id, p.start_date, p.end_date, "
        "SUM(CASE WHEN t.direction = 'expense' THEN t.amount ELSE 0 END), "
        "SUM(CASE WHEN t.direction = 'income' THEN t.amount ELSE 0 END), "
        "COUNT(CASE WHEN t.direction = 'expense' THEN 1 END) "
        "FROM budget_periods p "
        "LEFT JOIN budget_transactions t ON t.period_id = p.id AND t.deleted_at IS NULL "
        "GROUP BY p.id, p.start_date, p.end_date "
        "ORDER BY p.start_date DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    rows = [
        {"period_id": r[0], "start_date": r[1], "end_date": r[2], "spend": _int0(r[3]), "income": _int0(r[4]), "count": r[5]}
        for r in rows
    ]
    return list(reversed(rows))


def month_totals(limit=6) -> list:
    """Same shape as period_totals() but bucketed by calendar month — the
    alternate axis for the month-over-month chart. Straightforward
    GROUP BY substr(...), no period join needed."""
    conn = db_conn()
    rows = conn.execute(
        "SELECT substr(t.occurred_at, 1, 7) AS month, "
        "SUM(CASE WHEN t.direction = 'expense' THEN t.amount ELSE 0 END), "
        "SUM(CASE WHEN t.direction = 'income' THEN t.amount ELSE 0 END), "
        "COUNT(CASE WHEN t.direction = 'expense' THEN 1 END) "
        "FROM budget_transactions t "
        "WHERE t.deleted_at IS NULL "
        "GROUP BY substr(t.occurred_at, 1, 7) "
        "ORDER BY substr(t.occurred_at, 1, 7) DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    rows = [{"month": r[0], "spend": _int0(r[1]), "income": _int0(r[2]), "count": r[3]} for r in rows]
    return list(reversed(rows))


def category_month_totals(from_month: str, conn=None) -> list:
    """Every category's expense spend bucketed by calendar month, from
    from_month ('YYYY-MM') forward — the category x time axis nothing
    else in this file provides (spend_by_category_for_period() and
    category_spend_ranked_for_period() are both single-period; period_totals()/
    month_totals() are multi-period but have no category dimension).

    Bounded by a month floor rather than a LIMIT: a LIMIT on a category x
    month grid would truncate mid-category and hand back a ragged series,
    and it sidesteps the negative-LIMIT dialect trap (blueprint.py's
    _MAX_HISTORY_PERIODS comment). t.category_id IS NULL groups into one
    'Uncategorized' row and must not be filtered out, same rule as
    category_spend_ranked_for_period(). Both kinds are returned —
    'fixed'-kind categories have spending patterns too."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute(
        "SELECT t.category_id, c.name, c.kind, c.monthly_limit, "
        "substr(t.occurred_at, 1, 7) AS month, SUM(t.amount), COUNT(*) "
        "FROM budget_transactions t "
        "LEFT JOIN budget_categories c ON c.id = t.category_id "
        "WHERE t.deleted_at IS NULL AND t.direction = 'expense' "
        "AND substr(t.occurred_at, 1, 7) >= ? "
        "GROUP BY t.category_id, c.name, c.kind, c.monthly_limit, substr(t.occurred_at, 1, 7) "
        "ORDER BY t.category_id, substr(t.occurred_at, 1, 7)",
        (from_month,),
    ).fetchall()
    if owns_conn:
        conn.close()
    return [
        {"category_id": r[0], "name": r[1], "kind": r[2], "monthly_limit": r[3],
         "month": r[4], "spend": _int0(r[5]), "count": r[6]}
        for r in rows
    ]


def largest_expense_for_period(period_id, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    row = conn.execute(
        "SELECT t.id, t.note, t.amount, t.occurred_at, c.name "
        "FROM budget_transactions t LEFT JOIN budget_categories c ON c.id = t.category_id "
        "WHERE t.period_id = ? AND t.direction = 'expense' AND t.deleted_at IS NULL "
        "ORDER BY t.amount DESC, t.id LIMIT 1",
        (period_id,),
    ).fetchone()
    if owns_conn:
        conn.close()
    if row is None:
        return None
    return {"id": row[0], "name": row[1] or row[4] or "Expense", "amount": row[2], "occurred_at": row[3]}


def bills_due_for_period(period_id, conn=None) -> list:
    """Active bills not yet marked paid this period. NOT IN (subquery) is
    safe here only because bill_id is NOT NULL on budget_bill_payments —
    a NULL in that subquery would make NOT IN match nothing at all."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute(
        "SELECT b.id, b.name, b.amount, b.due_day, b.category_id, b.wallet_id "
        "FROM budget_bills b "
        "WHERE b.active = 1 "
        "AND b.id NOT IN (SELECT bp.bill_id FROM budget_bill_payments bp WHERE bp.period_id = ?) "
        "ORDER BY b.due_day, b.id",
        (period_id,),
    ).fetchall()
    if owns_conn:
        conn.close()
    return [{"id": r[0], "name": r[1], "amount": r[2], "due_day": r[3], "category_id": r[4], "wallet_id": r[5]} for r in rows]


def spend_today(period_id, date_str, conn=None) -> int:
    """Sum of expense spend on a single calendar day (date_str = the
    first-10-chars date key), scoped to the current period."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions "
        "WHERE period_id = ? AND direction = 'expense' AND deleted_at IS NULL "
        "AND substr(occurred_at, 1, 10) = ?",
        (period_id, date_str),
    ).fetchone()
    if owns_conn:
        conn.close()
    return _int0(row[0])


# ================================================================
# LABELS — local mirror of Wallet's labels; nothing used these before
# the Wallet sync (features/budget/wallet/) existed.
# ================================================================
_LABEL_COLS = "id, name, color, archived, created_at"


def _label_row(row):
    return {"id": row[0], "name": row[1], "color": row[2], "archived": bool(row[3]), "created_at": row[4]}


def create_label(name, color=None):
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO budget_labels (name, color, created_at) VALUES (?, ?, ?)",
        (name, color, str(now_jkt())),
    )
    label_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_label(label_id)


def get_labels(include_archived=False, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    where = "" if include_archived else "WHERE archived = 0"
    sql = "SELECT " + _LABEL_COLS + " FROM budget_labels " + where + " ORDER BY name"
    rows = conn.execute(sql).fetchall()
    if owns_conn:
        conn.close()
    return [_label_row(r) for r in rows]


def get_label(label_id):
    conn = db_conn()
    row = conn.execute("SELECT " + _LABEL_COLS + " FROM budget_labels WHERE id = ?", (label_id,)).fetchone()
    conn.close()
    return _label_row(row) if row else None


_LABEL_UPDATABLE = {"name", "color", "archived"}
_LABEL_BOOL_FIELDS = {"archived"}


def update_label(label_id, **fields):
    if not fields:
        return get_label(label_id)
    sets, params = [], []
    for key, value in fields.items():
        if key not in _LABEL_UPDATABLE:
            continue
        if key in _LABEL_BOOL_FIELDS:
            value = int(value)
        sets.append(key + " = ?")
        params.append(value)
    if not sets:
        return get_label(label_id)
    params.append(label_id)
    conn = db_conn()
    conn.execute("UPDATE budget_labels SET " + ", ".join(sets) + " WHERE id = ?", params)
    conn.commit()
    conn.close()
    return get_label(label_id)


def get_transaction_label_ids(transaction_id, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute(
        "SELECT label_id FROM budget_transaction_labels WHERE transaction_id = ?", (transaction_id,)
    ).fetchall()
    if owns_conn:
        conn.close()
    return [r[0] for r in rows]


def set_transaction_labels(transaction_id, label_ids):
    """Replaces the full label set for a transaction — mirrors Wallet's
    own PATCH .../labelIds semantics (array = replace-all), so the pull
    side can apply a remote record's labelIds directly without diffing."""
    conn = db_conn()
    conn.execute("DELETE FROM budget_transaction_labels WHERE transaction_id = ?", (transaction_id,))
    for label_id in label_ids:
        conn.execute(
            "INSERT INTO budget_transaction_labels (transaction_id, label_id) VALUES (?, ?)",
            (transaction_id, label_id),
        )
    conn.commit()
    conn.close()


# ================================================================
# WALLET SYNC LINKS — maps our int PKs to Wallet by BudgetBakers' UUIDs,
# one row per (entity_type, local row). Kept as its own table rather than
# a column on each ledger table so the core schema stays vendor-agnostic
# (see schema.py's migration 2 docstring). Used exclusively by
# features/budget/wallet/sync.py.
# ================================================================
_LINK_COLS = "id, entity_type, local_id, remote_id, remote_updated_at, local_synced_at, last_direction"


def _link_row(row):
    return {
        "id": row[0], "entity_type": row[1], "local_id": row[2], "remote_id": row[3],
        "remote_updated_at": row[4], "local_synced_at": row[5], "last_direction": row[6],
    }


def get_link_by_local(entity_type, local_id, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    row = conn.execute(
        "SELECT " + _LINK_COLS + " FROM budget_wallet_links WHERE entity_type = ? AND local_id = ?",
        (entity_type, local_id),
    ).fetchone()
    if owns_conn:
        conn.close()
    return _link_row(row) if row else None


def get_link_by_remote(entity_type, remote_id, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    row = conn.execute(
        "SELECT " + _LINK_COLS + " FROM budget_wallet_links WHERE entity_type = ? AND remote_id = ?",
        (entity_type, remote_id),
    ).fetchone()
    if owns_conn:
        conn.close()
    return _link_row(row) if row else None


def list_links(entity_type, conn=None) -> dict:
    """{remote_id: link_row} for every linked row of this entity type —
    the shape the pull loop needs to check 'have I seen this remote id
    before' without a query per record."""
    owns_conn = conn is None
    if owns_conn:
        conn = db_conn()
    rows = conn.execute(
        "SELECT " + _LINK_COLS + " FROM budget_wallet_links WHERE entity_type = ?", (entity_type,)
    ).fetchall()
    if owns_conn:
        conn.close()
    return {r[3]: _link_row(r) for r in rows}


def upsert_link(entity_type, local_id, remote_id, remote_updated_at=None, local_synced_at=None, last_direction=None):
    """Insert-or-update on the (entity_type, local_id) identity — a local
    row links to at most one remote row and vice versa (both are UNIQUE
    in the schema), so 'the same local row synced again' must update the
    existing link in place, never create a second one."""
    from db import IS_PG

    conn = db_conn()
    if IS_PG:
        conn.execute(
            "INSERT INTO budget_wallet_links "
            "(entity_type, local_id, remote_id, remote_updated_at, local_synced_at, last_direction) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (entity_type, local_id) DO UPDATE SET "
            "remote_id = EXCLUDED.remote_id, remote_updated_at = EXCLUDED.remote_updated_at, "
            "local_synced_at = EXCLUDED.local_synced_at, last_direction = EXCLUDED.last_direction",
            (entity_type, local_id, remote_id, remote_updated_at, local_synced_at, last_direction),
        )
    else:
        conn.execute(
            "INSERT OR REPLACE INTO budget_wallet_links "
            "(id, entity_type, local_id, remote_id, remote_updated_at, local_synced_at, last_direction) "
            "VALUES ("
            "  (SELECT id FROM budget_wallet_links WHERE entity_type = ? AND local_id = ?), "
            "  ?, ?, ?, ?, ?, ?)",
            (entity_type, local_id, entity_type, local_id, remote_id, remote_updated_at, local_synced_at, last_direction),
        )
    conn.commit()
    conn.close()
    return get_link_by_local(entity_type, local_id)


def delete_link(entity_type, local_id):
    conn = db_conn()
    conn.execute(
        "DELETE FROM budget_wallet_links WHERE entity_type = ? AND local_id = ?", (entity_type, local_id)
    )
    conn.commit()
    conn.close()
