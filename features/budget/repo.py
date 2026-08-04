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
    conn = db_conn()
    row = conn.execute(
        "SELECT 1 FROM budget_transactions WHERE (wallet_id = ? OR transfer_wallet_id = ?) AND deleted_at IS NULL LIMIT 1",
        (wallet_id, wallet_id),
    ).fetchone()
    conn.close()
    return row is not None


def delete_wallet(wallet_id):
    conn = db_conn()
    conn.execute("DELETE FROM budget_wallets WHERE id = ?", (wallet_id,))
    conn.commit()
    conn.close()


def wallet_balance(wallet_id) -> int:
    wallet = get_wallet(wallet_id)
    if wallet is None:
        return 0
    conn = db_conn()
    income = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions "
        "WHERE wallet_id = ? AND direction = 'income' AND deleted_at IS NULL",
        (wallet_id,),
    ).fetchone()[0]
    expense = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions "
        "WHERE wallet_id = ? AND direction = 'expense' AND deleted_at IS NULL",
        (wallet_id,),
    ).fetchone()[0]
    transfers_in = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions "
        "WHERE transfer_wallet_id = ? AND direction = 'transfer' AND deleted_at IS NULL",
        (wallet_id,),
    ).fetchone()[0]
    transfers_out = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM budget_transactions "
        "WHERE wallet_id = ? AND direction = 'transfer' AND deleted_at IS NULL",
        (wallet_id,),
    ).fetchone()[0]
    conn.close()
    return wallet["opening_balance"] + income - expense + transfers_in - transfers_out


def money_in_hand() -> int:
    """Sum of every spendable, non-archived wallet's balance."""
    return sum(
        wallet_balance(w["id"])
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
    row = conn.execute(
        "SELECT 1 FROM budget_transactions WHERE category_id = ? AND deleted_at IS NULL LIMIT 1",
        (category_id,),
    ).fetchone()
    conn.close()
    return row is not None


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
    return row[0]


# ================================================================
# BILLS — read-only accessors for now; full CRUD (create/update/delete/
# pay/unpay) is Phase 2 work. Needed here because build_period_view()
# must know which fixed expenses exist and which are already paid.
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


def create_bill(name, amount, due_day=None, category_id=None, wallet_id=None, cadence="monthly"):
    conn = db_conn()
    cur = conn.execute(
        "INSERT INTO budget_bills (name, amount, due_day, cadence, category_id, wallet_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, amount, due_day, cadence, category_id, wallet_id, str(now_jkt())),
    )
    bill_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_bill(bill_id)


def get_paid_bill_ids(period_id) -> set:
    conn = db_conn()
    rows = conn.execute(
        "SELECT bill_id FROM budget_bill_payments WHERE period_id = ?", (period_id,)
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


# ================================================================
# TRANSACTIONS
# ================================================================
_TXN_COLS = (
    "id, occurred_at, amount, direction, category_id, wallet_id, transfer_wallet_id, "
    "period_id, bill_id, goal_id, note, source, raw_input, created_at, deleted_at"
)


def _txn_row(row):
    return {
        "id": row[0], "occurred_at": row[1], "amount": row[2], "direction": row[3],
        "category_id": row[4], "wallet_id": row[5], "transfer_wallet_id": row[6],
        "period_id": row[7], "bill_id": row[8], "goal_id": row[9], "note": row[10],
        "source": row[11], "raw_input": row[12], "created_at": row[13], "deleted_at": row[14],
    }


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
    clauses = ["deleted_at IS NULL"]
    params = []
    if period_id is not None:
        clauses.append("period_id = ?")
        params.append(period_id)
    if category_id is not None:
        clauses.append("category_id = ?")
        params.append(category_id)
    if wallet_id is not None:
        clauses.append("wallet_id = ?")
        params.append(wallet_id)
    if direction is not None:
        clauses.append("direction = ?")
        params.append(direction)
    if date_from is not None:
        clauses.append("occurred_at >= ?")
        params.append(date_from)
    if date_to is not None:
        clauses.append("occurred_at <= ?")
        params.append(date_to)
    where = "WHERE " + " AND ".join(clauses)

    conn = db_conn()
    count_sql = "SELECT COUNT(*) FROM budget_transactions " + where
    total = conn.execute(count_sql, params).fetchone()[0]
    list_sql = (
        "SELECT " + _TXN_COLS + " FROM budget_transactions " + where +
        " ORDER BY occurred_at DESC, id DESC LIMIT ? OFFSET ?"
    )
    rows = conn.execute(list_sql, params + [limit, offset]).fetchall()
    conn.close()
    return [_txn_row(r) for r in rows], total


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
