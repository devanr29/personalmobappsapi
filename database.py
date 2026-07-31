import sqlite3
from config import now_jkt, CONV_WINDOW

DB_PATH = "bot.db"

# ================================================================
# SCHEMA SETUP
# ================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS ideas     (id INTEGER PRIMARY KEY, content TEXT, timestamp TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY, content TEXT, remind_at TEXT, done INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS notes     (id INTEGER PRIMARY KEY, content TEXT, timestamp TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS tasks     (id INTEGER PRIMARY KEY, content TEXT, timestamp TEXT, done INTEGER DEFAULT 0)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id        INTEGER PRIMARY KEY,
            role      TEXT,
            content   TEXT,
            timestamp TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id          INTEGER PRIMARY KEY,
            source_type TEXT,
            source_id   INTEGER,
            content     TEXT,
            embedding   BLOB,
            timestamp   TEXT
        )
    """)
    conn.commit()
    conn.close()

# ================================================================
# BOT STATE — generic key/value store (budget snapshot, quote cache, push tokens)
# ================================================================
def state_get(key: str) -> str | None:
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("SELECT value FROM bot_state WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None

def state_set(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def state_del(key: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM bot_state WHERE key = ?", (key,))
    conn.commit()
    conn.close()

# ================================================================
# CONVERSATION HISTORY — rolling window for multi-turn context
# ================================================================
def save_conv_turn(role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT role, content FROM conversations ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def clear_conv_history():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()
