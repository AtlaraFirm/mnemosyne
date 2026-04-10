import sqlite3
from mnemosyne.config import get_settings

def _conn() -> sqlite3.Connection:
    db_path = get_settings().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Run once on startup to create tables if they don't exist."""
    from mnemosyne.services.index import init_db as init_index
    init_index()

def get_history(chat_id: str) -> list[dict]:
    settings = get_settings()
    limit = settings.history_max_turns * 2  # Each turn = user + assistant
    with _conn() as conn:
        rows = conn.execute("""
            SELECT role, content, tool_name FROM conversations
            WHERE chat_id = ?
            ORDER BY ts DESC
            LIMIT ?
        """, (chat_id, limit)).fetchall()
    messages = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    return messages

def save_messages(chat_id: str, source: str, messages: list[dict]):
    with _conn() as conn:
        conn.executemany("""
            INSERT INTO conversations (source, chat_id, role, content, tool_name)
            VALUES (?, ?, ?, ?, ?)
        """, [
            (source, chat_id, m["role"], m["content"], m.get("tool_name"))
            for m in messages
        ])

def clear_history(chat_id: str):
    with _conn() as conn:
        conn.execute("DELETE FROM conversations WHERE chat_id = ?", (chat_id,))
