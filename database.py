from config import now_jkt, CONV_WINDOW
from db import db_conn, IS_PG, DB_PATH  # noqa: F401 — DB_PATH re-exported, other modules import it from here

# ================================================================
# SCHEMA SETUP
# ================================================================
_PK      = "SERIAL PRIMARY KEY"    if IS_PG else "INTEGER PRIMARY KEY"
_BLOB    = "BYTEA"                 if IS_PG else "BLOB"
_UPSERT  = (
    "INSERT INTO bot_state (key, value) VALUES (?, ?) "
    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
) if IS_PG else "INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)"

def init_db():
    conn = db_conn()
    conn.execute(f"CREATE TABLE IF NOT EXISTS ideas     (id {_PK}, content TEXT, timestamp TEXT)")
    conn.execute(f"CREATE TABLE IF NOT EXISTS reminders (id {_PK}, content TEXT, remind_at TEXT, done INTEGER DEFAULT 0)")
    conn.execute(f"CREATE TABLE IF NOT EXISTS notes     (id {_PK}, content TEXT, timestamp TEXT)")
    conn.execute(f"CREATE TABLE IF NOT EXISTS tasks     (id {_PK}, content TEXT, timestamp TEXT, done INTEGER DEFAULT 0)")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS conversations (
            id        {_PK},
            role      TEXT,
            content   TEXT,
            timestamp TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS embeddings (
            id          {_PK},
            source_type TEXT,
            source_id   INTEGER,
            content     TEXT,
            embedding   {_BLOB},
            timestamp   TEXT
        )
    """)
    conn.commit()
    conn.close()

    from features.budget.schema import init_budget_schema
    init_budget_schema()

# ================================================================
# BOT STATE — generic key/value store (budget snapshot, quote cache, push tokens)
# ================================================================
def state_get(key: str) -> str | None:
    conn = db_conn()
    row  = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None

def state_set(key: str, value: str):
    conn = db_conn()
    conn.execute(_UPSERT, (key, value))
    conn.commit()
    conn.close()

def state_del(key: str):
    conn = db_conn()
    conn.execute("DELETE FROM bot_state WHERE key = ?", (key,))
    conn.commit()
    conn.close()

# ================================================================
# CONVERSATION HISTORY — rolling window for multi-turn context
# ================================================================
def save_conv_turn(role: str, content: str):
    conn = db_conn()
    conn.execute(
        "INSERT INTO conversations (role, content, timestamp) VALUES (?, ?, ?)",
        (role, content, str(now_jkt()))
    )
    conn.execute("""
        DELETE FROM conversations
        WHERE id NOT IN (
            SELECT id FROM conversations ORDER BY id DESC LIMIT ?
        )
    """, (CONV_WINDOW * 2,))
    conn.commit()
    conn.close()

def load_conv_history() -> list[dict]:
    conn = db_conn()
    rows = conn.execute(
        "SELECT role, content FROM conversations ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def clear_conv_history():
    conn = db_conn()
    conn.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()
