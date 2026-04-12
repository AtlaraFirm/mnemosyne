import sqlite3
from mnemosyne.config import get_settings
from mnemosyne.agent.schemas import Chunk, SearchResult

def _conn() -> sqlite3.Connection:
    db_path = get_settings().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                id          TEXT PRIMARY KEY,
                note_path   TEXT NOT NULL,
                note_title  TEXT NOT NULL,
                heading     TEXT NOT NULL,
                text        TEXT NOT NULL,
                tags        TEXT,
                char_offset INTEGER DEFAULT 0,
                indexed_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                id UNINDEXED,
                note_path UNINDEXED,
                note_title,
                heading,
                text,
                tags,
                content=chunks,
                content_rowid=rowid
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT DEFAULT 'cli',
                chat_id     TEXT DEFAULT 'local',
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                tool_name   TEXT,
                ts          DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_conv_chat ON conversations(chat_id, ts DESC);
        """)

def upsert_chunks(chunks: list[Chunk]):
    with _conn() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO chunks (id, note_path, note_title, heading, text, tags, char_offset)
            VALUES (:id, :note_path, :note_title, :heading, :text, :tags, :char_offset)
        """, [
            {**c.dict(), "tags": ",".join(c.tags)}
            for c in chunks
        ])
        # Rebuild FTS index
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")

def search_fts(query: str, limit: int = 5) -> list[SearchResult]:
    import logging
    logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    logging.debug(f"search_fts called with query type: {type(query)}, value: {query}")
    assert isinstance(query, str), f"search_fts: query must be str, got {type(query)}: {query}"
    with _conn() as conn:
        rows = conn.execute("""
            SELECT c.id, c.note_path, c.note_title, c.heading, c.text, rank
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()
    results = []
    for row in rows:
        excerpt = row["text"][:200].replace("\n", " ")
        results.append(SearchResult(
            chunk_id=row["id"],
            note_path=row["note_path"],
            note_title=row["note_title"],
            heading=row["heading"],
            excerpt=excerpt,
            score=abs(row["rank"]),
            source="fts",
        ))
    return results
