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


def get_wallets(include_archived=False):
    conn = db_conn()
    where = "" if include_archived else "WHERE archived = 0"
    sql = "SELECT " + _WALLET_COLS + " FROM budget_wallets " + where + " ORDER BY sort_order, id"
    rows = conn.execute(sql).fetchall()
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


def wallet_balances() -> dict:
    """{wallet_id: balance} for every wallet (including archived — callers
    filter as needed) in 3 queries total, instead of 4 per wallet.

    'adjustment' is signed and applies at face value (positive tops up a
    wallet, negative reduces it — reconcile.py's contract); 'transfer'
    leaves wallet_id (debited) and lands in transfer_wallet_id (credited)."""
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

    conn.close()
    return out


def wallet_balance(wallet_id) -> int:
    return wallet_balances().get(wallet_id, 0)


def money_in_hand() -> int:
    """Sum of every spendable, non-archived wallet's balance."""
    balances = wallet_balances()
    return sum(
        balances.get(w["id"], 0)
        for w in get_wallets(include_archived=False)
        if w["spendable"]
    )


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


def get_categories(include_archived=False, kind=None):
    conn = db_conn()
    clauses = [] if include_archived else ["archived = 0"]
    params = []
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = "SELECT " + _CATEGORY_COLS + " FROM budget_categories " + where + " ORDER BY sort_order, id"
    rows = conn.execute(sql, params).fetchall()
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
    conn.close()
    return in_txns is not None or in_bills is not None


def delete_category(category_id):
    conn = db_conn()
    conn.execute("DELETE FROM budget_categories WHERE id = ?", (category_id,))
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


def spend_by_category_for_period(period_id) -> list:
    """One query for every category's spend this period, in id-grouped
    rows — replaces the N-query per-category loop build_period_view() used
    to run. t.category_id IS NULL groups into a single row (the
    "uncategorized" bucket), which callers must not filter out. Every
    selected non-aggregate column is in GROUP BY — Postgres requires it,
    SQLite doesn't enforce it but accepts it identically."""
    conn = db_conn()
    rows = conn.execute(
        "SELECT t.category_id, c.name, COALESCE(SUM(t.amount), 0) "
        "FROM budget_transactions t "
        "LEFT JOIN budget_categories c ON c.id = t.category_id "
        "WHERE t.period_id = ? AND t.direction = 'expense' AND t.deleted_at IS NULL "
        "GROUP BY t.category_id, c.name",
        (period_id,),
    ).fetchall()
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


def get_bills(active_only=True):
    conn = db_conn()
    where = "WHERE active = 1" if active_only else ""
    sql = "SELECT " + _BILL_COLS + " FROM budget_bills " + where + " ORDER BY id"
    rows = conn.execute(sql).fetchall()
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


def get_paid_bill_ids(period_id) -> set:
    conn = db_conn()
    rows = conn.execute(
        "SELECT bill_id FROM budget_bill_payments WHERE period_id = ?", (period_id,)
    ).fetchall()
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


# ================================================================
# TRANSACTIONS
# ================================================================
_TXN_COLS = (
    "id, occurred_at, amount, direction, category_id, wallet_id, transfer_wallet_id, "
    "period_id, bill_id, goal_id, note, source, raw_input, created_at, deleted_at"
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
    }


def _txn_list_row(row):
    txn = _txn_row(row)
    txn["category_name"] = row[15]
    txn["wallet_name"] = row[16]
    return txn


def create_transaction(
    amount, direction, category_id=None, wallet_id=None, transfer_wallet_id=None,
    period_id=None, bill_id=None, goal_id=None, note=None, source="manual",
    raw_input=None, occurred_at=None,
):
    occurred_at = occurred_at or now_jkt().strftime("%Y-%m-%d %H:%M")
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO budget_transactions "
        "(occurred_at, amount, direction, category_id, wallet_id, transfer_wallet_id, "
        " period_id, bill_id, goal_id, note, source, raw_input, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (occurred_at, amount, direction, category_id, wallet_id, transfer_wallet_id,
         period_id, bill_id, goal_id, note, source, raw_input, str(now_jkt())),
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
    params.append(txn_id)
    conn = db_conn()
    sql = "UPDATE budget_transactions SET " + ", ".join(sets) + " WHERE id = ?"
    conn.execute(sql, params)
    conn.commit()
    conn.close()
    return get_transaction(txn_id)


def soft_delete_transaction(txn_id):
    conn = db_conn()
    conn.execute(
        "UPDATE budget_transactions SET deleted_at = ? WHERE id = ?",
        (str(now_jkt()), txn_id),
    )
    conn.commit()
    conn.close()
    return get_transaction(txn_id)


def restore_transaction(txn_id):
    conn = db_conn()
    conn.execute("UPDATE budget_transactions SET deleted_at = NULL WHERE id = ?", (txn_id,))
    conn.commit()
    conn.close()
    return get_transaction(txn_id)
