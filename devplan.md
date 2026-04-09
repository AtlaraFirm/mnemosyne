# Vault CLI — Complete Design & Development Bible

## 1. Project Vision & Scope

Vault CLI is a personal, local-first tool for interacting with an Obsidian markdown vault through three surfaces: a Typer CLI for direct deterministic commands, a Textual TUI for interactive chat, and a python-telegram-bot v20 module for async access on the go. There is no server, no cloud dependency, no accounts, and no productization goal. All AI inference runs through Ollama on localhost.

The primary use cases are:
- **Talk to notes**: Ask natural language questions and get answers grounded in vault content
- **Search notes**: Exact keyword search and semantic similarity search
- **Add to notes**: Create new notes, append to existing ones, update frontmatter
- **Discover connections**: Find related notes not yet linked, suggest tags, surface orphans

### Non-Goals (for this version)
- No web UI, no REST API, no multi-user access
- No automatic writes without confirmation
- No deletion or rename of existing notes
- No Obsidian plugin (file-based only)

***

## 2. Technology Stack

Every choice here is deliberate. This table documents the rationale for each dependency.[^1][^2][^3][^4][^5]

| Layer | Technology | Version | Why |
|-------|-----------|---------|-----|
| CLI shell | `typer` | ≥0.12 | Type-hint-driven commands, auto-generated help, shell completion[^2][^3][^6] |
| TUI | `textual` | ≥0.60 | Async-native, widget-based, ships its own dark theme[^5][^7] |
| Telegram bot | `python-telegram-bot` | ≥20.0 | Fully async v20 API, `ApplicationBuilder`, `InlineKeyboardMarkup` callbacks[^4][^8][^9] |
| LLM + tool calling | `ollama` (Python SDK) | ≥0.3 | Local tool calling, streaming, embeddings — one SDK for everything[^1][^10][^11] |
| Lexical search | SQLite FTS5 | built-in | BM25 ranking, no dependencies, zero-latency on local files[^12][^13] |
| Vector store | `qdrant-client` | ≥1.9 | Already in existing stack; cosine search, Docker-ready[^14][^15] |
| Frontmatter R/W | `python-frontmatter` | ≥1.1 | Load, mutate, and dump YAML frontmatter without touching body[^16][^17] |
| Data validation | `pydantic` | ≥2.0 | Schema-validated tool I/O, write action previews, settings |
| Output formatting | `rich` | ≥13.0 | Syntax highlighting, tables, diffs in terminal output |
| Config | `python-dotenv` | ≥1.0 | Load `.env` at startup |
| Testing | `pytest` + `pytest-asyncio` | latest | CLI via `CliRunner`, async agent via `pytest-asyncio`[^18] |
| Package manager | `uv` | latest | Fast, lockfile-based, works well with `pyproject.toml` |

### Embedding Model Recommendation

Use `nomic-embed-text` as the default embedding model. It outperforms `text-embedding-ada-002` on short and long context tasks, is fully open-source with open training data, and is served locally through Ollama with no separate process. The newer `nomic-embed-text-v2-moe` uses a mixture-of-experts architecture with 305M active parameters and 768-dimensional output, offering strong multilingual performance at low latency.[^19][^20][^21][^22]

### Chat Model Recommendation

`llama3.2` is the reference model used in Ollama's own tool-calling documentation and works reliably. `qwen2.5` is a strong alternative with better tool-calling reliability in practice. Test both. Smaller models (3b) occasionally loop on tool calls — use a loop guard of 8 iterations maximum.[^23][^24][^1]

***

## 3. Project Structure

```
vault-cli/
├── pyproject.toml              # Build config, dependencies, scripts
├── .env.example                # All env vars documented with defaults
├── .env                        # Local config (gitignored)
├── README.md
├── RUNBOOK.md                  # Operational notes: reindex, troubleshoot, wipe
│
├── vault_cli/
│   ├── __init__.py
│   ├── __main__.py             # Enables `python -m vault_cli`
│   │
│   ├── config.py               # Settings dataclass, load_settings()
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── vault.py            # Crawl, read, chunk notes
│   │   ├── index.py            # SQLite schema + FTS5 search
│   │   ├── embed.py            # Ollama embeddings + Qdrant ops
│   │   ├── writes.py           # WritePlan + apply_plan()
│   │   └── related.py          # Cosine similarity for link suggestions
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── tools.py            # Tool function definitions + TOOLS registry
│   │   ├── loop.py             # Ollama chat + tool-calling agentic loop
│   │   └── schemas.py          # Pydantic models for all agent I/O
│   │
│   ├── frontends/
│   │   ├── __init__.py
│   │   ├── cli.py              # Typer app with all subcommands
│   │   ├── tui.py              # Textual ChatApp
│   │   └── telegram_bot.py     # python-telegram-bot v20 Application
│   │
│   └── db/
│       ├── __init__.py
│       └── connection.py       # SQLite connection, migrations, history ops
│
├── tests/
│   ├── conftest.py             # Fixtures: temp vault, mock Ollama, settings
│   ├── test_vault.py
│   ├── test_index.py
│   ├── test_embed.py
│   ├── test_writes.py
│   ├── test_agent.py
│   └── test_cli.py
│
├── deploy/
│   ├── docker-compose.yml      # Qdrant + optional Ollama
│   └── vault-cli.service       # systemd unit for Telegram bot daemon
│
└── db/
    └── vault.db                # Runtime SQLite (gitignored)
```

***

## 4. Configuration System

### `.env.example`

```env
# === Vault ===
VAULT_PATH=/Users/you/obsidian/my-vault
DAILY_NOTE_FOLDER=daily
IGNORE_GLOBS=.obsidian/**,templates/**,.trash/**

# === Ollama ===
OLLAMA_HOST=http://localhost:11434
CHAT_MODEL=llama3.2
EMBED_MODEL=nomic-embed-text
AGENT_MAX_ITERATIONS=8

# === Vector Store ===
VECTOR_BACKEND=qdrant        # "qdrant" or "sqlite-vec"
QDRANT_HOST=http://localhost:6333
QDRANT_COLLECTION=vault_chunks

# === SQLite ===
DB_PATH=./db/vault.db
HISTORY_MAX_TURNS=20

# === Telegram (optional) ===
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=   # Comma-separated; leave blank to allow all

# === Behavior ===
WRITE_CONFIRM_DEFAULT=true   # Require confirmation for all writes
AUDIT_LOG_PATH=./vault-cli-audit.log
```

### `config.py`

```python
from pydantic import BaseSettings, Field
from pathlib import Path
from typing import Literal
from functools import lru_cache

class Settings(BaseSettings):
    # Vault
    vault_path: Path
    daily_note_folder: str = "daily"
    ignore_globs: list[str] = Field(default_factory=lambda: [".obsidian/**", "templates/**"])

    # Ollama
    ollama_host: str = "http://localhost:11434"
    chat_model: str = "llama3.2"
    embed_model: str = "nomic-embed-text"
    agent_max_iterations: int = 8

    # Vector store
    vector_backend: Literal["qdrant", "sqlite-vec"] = "qdrant"
    qdrant_host: str = "http://localhost:6333"
    qdrant_collection: str = "vault_chunks"

    # SQLite
    db_path: Path = Path("./db/vault.db")
    history_max_turns: int = 20

    # Telegram
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: list[int] = Field(default_factory=list)

    # Behavior
    write_confirm_default: bool = True
    audit_log_path: Path = Path("./vault-cli-audit.log")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

***

## 5. Data Models

All shared models live in `agent/schemas.py`. These are used across services, agent, and all frontends.

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

# ── Vault primitives ──────────────────────────────────────────────

class Note(BaseModel):
    path: str                        # Relative to vault root
    title: str
    body: str                        # Full markdown body (post-frontmatter)
    frontmatter: dict                # Parsed YAML frontmatter
    tags: list[str]
    wikilinks: list[str]             # [[note titles]] found in body
    headings: list[str]              # ## heading text
    modified_at: datetime

class Chunk(BaseModel):
    id: str                          # SHA256 of (path + heading)
    note_path: str
    note_title: str
    heading: str                     # Section heading this chunk is under
    text: str                        # Heading + body text for this section
    tags: list[str]
    char_offset: int                 # Character offset in original note

# ── Search ───────────────────────────────────────────────────────

class SearchResult(BaseModel):
    chunk_id: str
    note_path: str
    note_title: str
    heading: str
    excerpt: str                     # 200-char snippet
    score: float
    source: Literal["fts", "semantic", "hybrid"]

# ── Write actions ─────────────────────────────────────────────────

class WritePlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    operation: Literal["create_note", "append_note", "prepend_note", "update_frontmatter"]
    path: str                        # Relative vault path
    preview: str                     # Human-readable diff/preview
    payload: dict                    # Data for apply_plan()
    created_at: datetime = Field(default_factory=datetime.utcnow)

# ── Agent ─────────────────────────────────────────────────────────

class AgentResponse(BaseModel):
    text: str
    messages: list[dict]             # Full conversation including tool calls
    write_plans: list[WritePlan]     # Pending write actions requiring approval
    tool_calls_made: list[str]       # Names of tools invoked this turn

# ── Conversation ──────────────────────────────────────────────────

class ConversationMessage(BaseModel):
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    tool_name: Optional[str] = None
    source: Literal["cli", "tui", "telegram"] = "cli"
    chat_id: str = "local"
    ts: datetime = Field(default_factory=datetime.utcnow)
```

***

## 6. Services Layer

### 6.1 `services/vault.py` — Filesystem

Responsible for all vault I/O. Never writes — that is `writes.py`'s job.

```python
import frontmatter
import re
import hashlib
from pathlib import Path
from fnmatch import fnmatch
from vault_cli.config import get_settings
from vault_cli.agent.schemas import Note, Chunk
from datetime import datetime

def _should_ignore(path: Path, vault_root: Path) -> bool:
    rel = str(path.relative_to(vault_root))
    for glob in get_settings().ignore_globs:
        if fnmatch(rel, glob):
            return True
    return False

def crawl_vault() -> list[Note]:
    settings = get_settings()
    vault = Path(settings.vault_path)
    notes = []
    for md_file in vault.rglob("*.md"):
        if _should_ignore(md_file, vault):
            continue
        notes.append(read_note(md_file))
    return notes

def read_note(path: Path) -> Note:
    settings = get_settings()
    vault = Path(settings.vault_path)
    post = frontmatter.load(str(path))
    body = post.content
    fm = dict(post.metadata)
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    wikilinks = re.findall(r'\[\[([^\]|#]+)', body)
    headings = re.findall(r'^#{1,6}\s+(.+)$', body, re.MULTILINE)
    return Note(
        path=str(path.relative_to(vault)),
        title=fm.get("title", path.stem),
        body=body,
        frontmatter=fm,
        tags=tags,
        wikilinks=wikilinks,
        headings=headings,
        modified_at=datetime.fromtimestamp(path.stat().st_mtime),
    )

def chunk_note(note: Note) -> list[Chunk]:
    """Split note body into heading-level chunks."""
    heading_pattern = re.compile(r'^(#{1,6}\s+.+)$', re.MULTILINE)
    splits = heading_pattern.split(note.body)
    chunks = []
    # splits alternates: [pre-heading content, heading, content, heading, content...]
    # Handle intro text before first heading
    if splits.strip():
        chunk_text = f"# {note.title}\n{splits.strip()}"
        chunks.append(_make_chunk(note, "Introduction", chunk_text, 0))
    offset = len(splits)
    for i in range(1, len(splits), 2):
        heading = splits[i].strip() if i < len(splits) else ""
        content = splits[i + 1].strip() if i + 1 < len(splits) else ""
        if heading or content:
            chunk_text = f"{heading}\n{content}".strip()
            chunks.append(_make_chunk(note, heading.lstrip('#').strip(), chunk_text, offset))
        offset += len(heading) + len(content)
    return chunks if chunks else [_make_chunk(note, note.title, note.body, 0)]

def _make_chunk(note: Note, heading: str, text: str, offset: int) -> Chunk:
    chunk_id = hashlib.sha256(f"{note.path}::{heading}".encode()).hexdigest()[:16]
    return Chunk(
        id=chunk_id,
        note_path=note.path,
        note_title=note.title,
        heading=heading,
        text=text,
        tags=note.tags,
        char_offset=offset,
    )
```

### 6.2 `services/index.py` — SQLite FTS5

FTS5 uses BM25 ranking internally. Note: SQLite FTS5's `rank` column returns negative values by default (more negative = better match), so sort ascending.

```python
import sqlite3
from pathlib import Path
from vault_cli.config import get_settings
from vault_cli.agent.schemas import Chunk, SearchResult

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
    with _conn() as conn:
        rows = conn.execute("""
            SELECT c.id, c.note_path, c.note_title, c.heading, c.text, rank
            FROM chunks_fts
            JOIN chunks c ON chunks_fts.rowid = c.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY rank          -- rank is negative BM25; ascending = best first
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
```

### 6.3 `services/embed.py` — Ollama Embeddings + Qdrant

```python
import ollama
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from vault_cli.config import get_settings
from vault_cli.agent.schemas import Chunk, SearchResult
import uuid

def _qdrant() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_host)

def _embed(text: str) -> list[float]:
    settings = get_settings()
    response = ollama.embed(model=settings.embed_model, input=text)
    return response.embeddings

def ensure_collection(dim: int = 768):
    client = _qdrant()
    settings = get_settings()
    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

def index_chunks(chunks: list[Chunk], batch_size: int = 50):
    settings = get_settings()
    client = _qdrant()
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        points = []
        for chunk in batch:
            vector = _embed(chunk.text)
            points.append(PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.id)),
                vector=vector,
                payload={
                    "chunk_id": chunk.id,
                    "note_path": chunk.note_path,
                    "note_title": chunk.note_title,
                    "heading": chunk.heading,
                    "text": chunk.text,
                    "tags": chunk.tags,
                }
            ))
        client.upsert(collection_name=settings.qdrant_collection, points=points)

def semantic_search(query: str, limit: int = 5) -> list[SearchResult]:
    settings = get_settings()
    client = _qdrant()
    query_vector = _embed(query)
    hits = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=limit,
        with_payload=True,
    )
    return [
        SearchResult(
            chunk_id=hit.payload["chunk_id"],
            note_path=hit.payload["note_path"],
            note_title=hit.payload["note_title"],
            heading=hit.payload["heading"],
            excerpt=hit.payload["text"][:200].replace("\n", " "),
            score=hit.score,
            source="semantic",
        )
        for hit in hits
    ]

def hybrid_search(query: str, limit: int = 5) -> list[SearchResult]:
    """Merge FTS and semantic results, deduplicate, re-rank by combined score."""
    from vault_cli.services.index import search_fts
    fts_results = search_fts(query, limit=limit)
    sem_results = semantic_search(query, limit=limit)
    seen = {}
    for r in fts_results + sem_results:
        if r.chunk_id not in seen:
            seen[r.chunk_id] = r
        else:
            # Boost score if found in both
            seen[r.chunk_id].score += r.score
            seen[r.chunk_id].source = "hybrid"
    return sorted(seen.values(), key=lambda x: x.score, reverse=True)[:limit]
```

### 6.4 `services/writes.py` — Safe Vault Mutations

Writes are always two-phase: produce a `WritePlan` → frontend approves → `apply_plan()` executes.

```python
import frontmatter
import difflib
from pathlib import Path
from datetime import datetime
from vault_cli.config import get_settings
from vault_cli.agent.schemas import WritePlan

def _vault() -> Path:
    return Path(get_settings().vault_path)

def create_note(title: str, body: str, folder: str = "", tags: list[str] = None) -> WritePlan:
    folder = folder or ""
    safe_title = title.replace("/", "-").replace("\\", "-")
    rel_path = f"{folder}/{safe_title}.md".lstrip("/")
    abs_path = _vault() / rel_path
    fm = {"title": title, "created": datetime.utcnow().isoformat(), "tags": tags or []}
    post = frontmatter.Post(body, **fm)
    preview = f"CREATE {rel_path}\n\n{frontmatter.dumps(post)}"
    return WritePlan(
        operation="create_note",
        path=rel_path,
        preview=preview,
        payload={"abs_path": str(abs_path), "content": frontmatter.dumps(post)},
    )

def append_note(path: str, text: str, section: str = None) -> WritePlan:
    abs_path = _vault() / path
    original = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
    new_content = original.rstrip() + f"\n\n{text}\n"
    diff = "\n".join(difflib.unified_diff(
        original.splitlines(), new_content.splitlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
    ))
    return WritePlan(
        operation="append_note",
        path=path,
        preview=diff or f"APPEND to {path}:\n{text}",
        payload={"abs_path": str(abs_path), "content": new_content},
    )

def update_frontmatter(path: str, updates: dict) -> WritePlan:
    abs_path = _vault() / path
    post = frontmatter.load(str(abs_path))
    original = frontmatter.dumps(post)
    post.metadata.update(updates)
    new_content = frontmatter.dumps(post)
    diff = "\n".join(difflib.unified_diff(
        original.splitlines(), new_content.splitlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
    ))
    return WritePlan(
        operation="update_frontmatter",
        path=path,
        preview=diff,
        payload={"abs_path": str(abs_path), "content": new_content},
    )

def apply_plan(plan: WritePlan) -> str:
    settings = get_settings()
    abs_path = Path(plan.payload["abs_path"])
    content = plan.payload["content"]
    if plan.operation == "create_note":
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
    else:
        abs_path.write_text(content, encoding="utf-8")
    # Audit log
    with open(settings.audit_log_path, "a") as f:
        f.write(f"{datetime.utcnow().isoformat()}|{plan.operation}|{plan.path}\n")
    return f"✓ Applied: {plan.operation} → {plan.path}"
```

### 6.5 `services/related.py` — Link Suggestions

```python
from vault_cli.services.embed import _embed, _qdrant
from vault_cli.services.vault import read_note
from vault_cli.config import get_settings
from pathlib import Path

def find_related(path: str, limit: int = 5, threshold: float = 0.75) -> list[dict]:
    """Return semantically related notes not already wikilinked from source note."""
    settings = get_settings()
    abs_path = Path(settings.vault_path) / path
    note = read_note(abs_path)
    query_vector = _embed(note.title + " " + note.body[:500])
    client = _qdrant()
    hits = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=limit + 10,
        with_payload=True,
    )
    existing_links = {l.lower() for l in note.wikilinks}
    results = []
    for hit in hits:
        if hit.score < threshold:
            continue
        title = hit.payload.get("note_title", "")
        hit_path = hit.payload.get("note_path", "")
        if hit_path == path:
            continue
        if title.lower() in existing_links:
            continue
        results.append({
            "path": hit_path,
            "title": title,
            "heading": hit.payload.get("heading", ""),
            "score": round(hit.score, 3),
        })
        if len(results) >= limit:
            break
    return results
```

***

## 7. Agent Layer

### 7.1 `agent/tools.py` — Tool Registry

Ollama's Python SDK accepts plain callables with type hints and docstrings. The docstring content and parameter types determine how the model understands when to call the tool.

```python
from vault_cli.services import index as idx_svc
from vault_cli.services import embed as emb_svc
from vault_cli.services import vault as vault_svc
from vault_cli.services import writes as write_svc
from vault_cli.services import related as rel_svc
from vault_cli.config import get_settings
import json

# ── Read tools (freely callable from chat) ────────────────────────

def search_notes(query: str, limit: int = 5) -> str:
    """
    Search vault notes by exact keywords, tags, or note titles.
    Use for specific technical terms, proper nouns, exact phrases.
    Returns matching note paths and excerpts.

    Args:
        query: Search query string
        limit: Maximum results to return (default 5)
    """
    results = idx_svc.search_fts(query, limit)
    if not results:
        return "No notes found matching that query."
    lines = [f"[{r.score:.2f}] {r.note_title} ({r.note_path})\n  {r.excerpt}" for r in results]
    return "\n\n".join(lines)

def semantic_search(query: str, limit: int = 5) -> str:
    """
    Search notes by semantic meaning, not exact keywords.
    Use when the user is looking for conceptually related content.
    Returns note paths and excerpts ranked by semantic similarity.

    Args:
        query: Natural language description of what to find
        limit: Maximum results to return (default 5)
    """
    results = emb_svc.semantic_search(query, limit)
    if not results:
        return "No semantically related notes found."
    lines = [f"[{r.score:.3f}] {r.note_title} > {r.heading} ({r.note_path})\n  {r.excerpt}" for r in results]
    return "\n\n".join(lines)

def read_note(path: str) -> str:
    """
    Read the full content of a specific note by its vault path.
    Use after search to read complete note contents.

    Args:
        path: Relative vault path, e.g. 'ai/wisp-architecture.md'
    """
    from pathlib import Path
    abs_path = Path(get_settings().vault_path) / path
    if not abs_path.exists():
        return f"Note not found: {path}"
    note = vault_svc.read_note(abs_path)
    return f"# {note.title}\nTags: {', '.join(note.tags)}\n\n{note.body}"

def list_related_notes(path: str, limit: int = 5) -> str:
    """
    Find notes semantically related to the given note that are not yet wikilinked from it.
    Use to suggest backlinks or find relevant content the user hasn't connected yet.

    Args:
        path: Relative vault path of the source note
        limit: Maximum suggestions to return
    """
    related = rel_svc.find_related(path, limit)
    if not related:
        return "No closely related unlinked notes found."
    lines = [f"[{r['score']}] [[{r['title']}]] ({r['path']})" for r in related]
    return "\n".join(lines)

# ── Write tools (always return WritePlan JSON, never auto-apply) ──

def propose_append_to_note(path: str, text: str) -> str:
    """
    Propose appending text to an existing note. Returns a preview for user approval.
    NEVER auto-apply. Always ask the user to confirm before calling apply.

    Args:
        path: Relative vault path of the note to append to
        text: Markdown text to append
    """
    plan = write_svc.append_note(path, text)
    return plan.model_dump_json()

def propose_create_note(title: str, body: str, folder: str = "", tags: list[str] = None) -> str:
    """
    Propose creating a new note. Returns a preview for user approval.
    NEVER auto-apply. Always ask the user to confirm before calling apply.

    Args:
        title: Note title (becomes filename)
        body: Markdown body content
        folder: Optional subfolder within vault
        tags: Optional list of tags for frontmatter
    """
    plan = write_svc.create_note(title, body, folder, tags or [])
    return plan.model_dump_json()

def propose_update_frontmatter(path: str, updates_json: str) -> str:
    """
    Propose updating YAML frontmatter fields on an existing note.
    Returns a preview for user approval. NEVER auto-apply.

    Args:
        path: Relative vault path
        updates_json: JSON string of key-value pairs to set in frontmatter
    """
    updates = json.loads(updates_json)
    plan = write_svc.update_frontmatter(path, updates)
    return plan.model_dump_json()

# ── Tool registry ────────────────────────────────────────────────

TOOLS = [
    search_notes,
    semantic_search,
    read_note,
    list_related_notes,
    propose_append_to_note,
    propose_create_note,
    propose_update_frontmatter,
]

TOOL_MAP = {fn.__name__: fn for fn in TOOLS}

def dispatch(name: str, arguments: dict) -> str:
    fn = TOOL_MAP.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    return fn(**arguments)
```

### 7.2 `agent/loop.py` — Agentic Chat Loop

The loop follows Ollama's official tool-calling pattern: send messages + tools, handle `tool_calls`, append tool results, repeat until the model produces a final response with no further calls. The iteration cap prevents infinite loops on smaller models.

```python
import ollama
import json
from vault_cli.config import get_settings
from vault_cli.agent.tools import TOOLS, dispatch
from vault_cli.agent.schemas import AgentResponse, WritePlan

SYSTEM_PROMPT = """You are a helpful assistant for an Obsidian markdown vault. 
You have tools to search notes, read note contents, find related notes, 
and propose write actions for the user to approve.

Rules:
- Always search before answering questions about note contents.
- For write operations, use propose_* tools. Never claim to have written something without proposing first.
- Cite specific note paths when referencing content.
- If you cannot find relevant notes, say so clearly rather than guessing.
- Keep responses focused and direct."""

def run(message: str, history: list[dict]) -> AgentResponse:
    settings = get_settings()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": message}
    ]
    tool_calls_made = []
    write_plans = []
    max_iters = settings.agent_max_iterations

    for iteration in range(max_iters):
        response = ollama.chat(
            model=settings.chat_model,
            messages=messages,
            tools=TOOLS,
        )
        messages.append(response.message)

        if not response.message.tool_calls:
            # Extract any WritePlan objects from tool results in this turn
            for msg in messages:
                if msg.get("role") == "tool":
                    try:
                        plan = WritePlan.model_validate_json(msg["content"])
                        write_plans.append(plan)
                    except Exception:
                        pass
            return AgentResponse(
                text=response.message.content or "",
                messages=messages,
                write_plans=write_plans,
                tool_calls_made=tool_calls_made,
            )

        for tc in response.message.tool_calls:
            name = tc.function.name
            args = tc.function.arguments
            tool_calls_made.append(name)
            result = dispatch(name, args)
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": str(result),
            })

    # Loop cap hit — force a final response
    messages.append({"role": "user", "content": "Please summarize what you found so far."})
    final = ollama.chat(model=settings.chat_model, messages=messages)
    return AgentResponse(
        text=final.message.content or "Reached iteration limit. Please refine your query.",
        messages=messages,
        write_plans=write_plans,
        tool_calls_made=tool_calls_made,
    )
```

***

## 8. Frontend: CLI (`frontends/cli.py`)

The CLI uses Typer subcommands. Direct commands call services without the agent loop for predictable, scriptable behavior. The `chat` command drops into TUI mode.

```python
import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from pathlib import Path

app = typer.Typer(name="vault", help="Obsidian vault assistant powered by Ollama.")
console = Console()

@app.command()
def reindex():
    """Crawl vault, rebuild FTS5 index and embeddings."""
    from vault_cli.services import vault as v, index as idx, embed as emb
    from vault_cli.db.connection import init_db
    init_db()
    notes = v.crawl_vault()
    console.print(f"[bold]Found {len(notes)} notes[/bold]")
    all_chunks = []
    for note in notes:
        all_chunks.extend(v.chunk_note(note))
    console.print(f"Indexing {len(all_chunks)} chunks...")
    idx.upsert_chunks(all_chunks)
    emb.ensure_collection()
    with console.status("Generating embeddings..."):
        emb.index_chunks(all_chunks)
    console.print("[green]✓ Reindex complete[/green]")

@app.command()
def search(
    query: str = typer.Argument(..., help="Keyword search query"),
    limit: int = typer.Option(5, "--limit", "-n"),
    semantic: bool = typer.Option(False, "--semantic", "-s", help="Use semantic search"),
):
    """Search vault notes by keyword or semantic similarity."""
    from vault_cli.services import index as idx, embed as emb
    results = emb.semantic_search(query, limit) if semantic else idx.search_fts(query, limit)
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        raise typer.Exit()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Score", width=6)
    table.add_column("Note", min_width=20)
    table.add_column("Heading", min_width=15)
    table.add_column("Excerpt")
    for r in results:
        table.add_row(f"{r.score:.2f}", r.note_title, r.heading, r.excerpt[:80])
    console.print(table)

@app.command()
def ask(
    query: str = typer.Argument(..., help="Question to ask the vault"),
    confirm_writes: bool = typer.Option(True, "--confirm/--yes"),
):
    """Ask a natural language question. Agent retrieves and answers from vault content."""
    from vault_cli.agent.loop import run
    from vault_cli.db.connection import get_history
    history = get_history("local")
    with console.status("[bold]Thinking...[/bold]"):
        response = run(query, history)
    _save_history("local", "cli", query, response)
    console.print(f"\n[bold cyan]Vault:[/bold cyan] {response.text}\n")
    if response.tool_calls_made:
        console.print(f"[dim]Tools used: {', '.join(response.tool_calls_made)}[/dim]")
    if response.write_plans:
        _handle_write_plans(response.write_plans, confirm_writes)

@app.command()
def new(
    title: str = typer.Argument(..., help="Note title"),
    folder: str = typer.Option("", "--folder", "-f"),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Create a new note. Opens $EDITOR if no --body provided."""
    from vault_cli.services.writes import create_note, apply_plan
    import subprocess, os
    body = typer.edit("") or ""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    plan = create_note(title, body, folder, tag_list)
    console.print(Syntax(plan.preview, "diff", theme="ansi_dark"))
    if yes or typer.confirm("Apply?"):
        console.print(apply_plan(plan))

@app.command()
def append(
    path: str = typer.Argument(..., help="Relative vault path"),
    text: str = typer.Argument(..., help="Text to append"),
    yes: bool = typer.Option(False, "--yes", "-y"),
):
    """Append text to an existing note."""
    from vault_cli.services.writes import append_note, apply_plan
    plan = append_note(path, text)
    console.print(Syntax(plan.preview, "diff", theme="ansi_dark"))
    if yes or typer.confirm("Apply?"):
        console.print(apply_plan(plan))

@app.command()
def related(
    path: str = typer.Argument(..., help="Relative vault path"),
    limit: int = typer.Option(5, "--limit", "-n"),
):
    """Find semantically related notes not yet linked."""
    from vault_cli.services.related import find_related
    results = find_related(path, limit)
    if not results:
        console.print("[yellow]No related notes found.[/yellow]")
        return
    for r in results:
        console.print(f"[{r['score']}] [[{r['title']}]] → {r['path']}")

@app.command()
def chat():
    """Launch interactive TUI chat mode."""
    from vault_cli.frontends.tui import run_tui
    run_tui()

@app.command()
def bot():
    """Start Telegram bot (requires TELEGRAM_BOT_TOKEN in .env)."""
    from vault_cli.frontends.telegram_bot import run_bot
    run_bot()

def _handle_write_plans(plans, confirm_writes):
    from vault_cli.services.writes import apply_plan
    for plan in plans:
        console.print(f"\n[bold yellow]Proposed: {plan.operation} → {plan.path}[/bold yellow]")
        console.print(Syntax(plan.preview, "diff", theme="ansi_dark"))
        if confirm_writes:
            if typer.confirm("Apply?"):
                console.print(apply_plan(plan))
        else:
            console.print(apply_plan(plan))

def _save_history(chat_id, source, user_msg, response):
    from vault_cli.db.connection import save_messages
    save_messages(chat_id, source, [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": response.text},
    ])

if __name__ == "__main__":
    app()
```

### Complete Command Reference

| Command | Arguments | Options | Behavior |
|---------|-----------|---------|----------|
| `vault reindex` | — | — | Crawl vault → rebuild FTS + embeddings |
| `vault search QUERY` | `QUERY` | `--limit N`, `--semantic` | FTS or semantic search |
| `vault ask QUERY` | `QUERY` | `--confirm/--yes` | Agent Q&A with write confirmation |
| `vault new TITLE` | `TITLE` | `--folder`, `--tags`, `--yes` | Create note (opens $EDITOR) |
| `vault append PATH TEXT` | `PATH TEXT` | `--yes` | Append text, show diff, confirm |
| `vault related PATH` | `PATH` | `--limit N` | Related unlinked notes |
| `vault chat` | — | — | Launch Textual TUI |
| `vault bot` | — | — | Start Telegram bot daemon |

***

## 9. Frontend: TUI (`frontends/tui.py`)

Uses Textual's widget system and async support. The `ChatMessage` widget wraps Textual's `Markdown` widget to render responses properly. Tool call names are displayed inline as status indicators between user input and final response.

```python
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.widgets import Header, Footer, Input, Button, Markdown, Label, Static
from textual.reactive import reactive
from textual.binding import Binding
from textual.theme import Theme
from vault_cli.agent.loop import run as agent_run
from vault_cli.agent.schemas import WritePlan
from vault_cli.db.connection import get_history, save_messages

VAULT_THEME = Theme(
    name="vault",
    primary="#4f98a3",
    secondary="#81A1C1",
    accent="#6daa45",
    foreground="#cdccca",
    background="#171614",
    success="#6daa45",
    warning="#fdab43",
    error="#dd6974",
    surface="#1c1b19",
    panel="#201f1d",
    dark=True,
)

class ChatMessage(Static):
    DEFAULT_CSS = """
    ChatMessage {
        padding: 0 1;
        margin-bottom: 1;
    }
    ChatMessage.user {
        color: $accent;
        border-left: thick $accent;
        padding-left: 1;
    }
    ChatMessage.assistant {
        color: $foreground;
    }
    ChatMessage.tool-call {
        color: $text-muted;
        opacity: 60%;
    }
    """

class WritePlanWidget(Static):
    DEFAULT_CSS = """
    WritePlanWidget {
        border: round $warning;
        padding: 1;
        margin: 1 0;
    }
    """

class ChatApp(App):
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+r", "reindex", "Reindex"),
        Binding("ctrl+l", "clear", "Clear chat"),
        Binding("escape", "reject_plan", "Reject plan"),
    ]
    CSS = """
    #conversation { height: 1fr; }
    #input-row { height: 3; dock: bottom; }
    #message-input { width: 1fr; }
    """

    pending_plans: reactive[list[WritePlan]] = reactive([], init=False)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield VerticalScroll(id="conversation")
        with Horizontal(id="input-row"):
            yield Input(placeholder="Ask anything about your vault...", id="message-input")
            yield Button("Send", variant="primary", id="send-btn")
        yield Footer()

    def on_mount(self):
        self.register_theme(VAULT_THEME)
        self.theme = "vault"
        self.query_one("#message-input").focus()

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "send-btn":
            await self._send_message()

    async def on_input_submitted(self, event: Input.Submitted):
        await self._send_message()

    async def _send_message(self):
        input_widget = self.query_one("#message-input", Input)
        message = input_widget.value.strip()
        if not message:
            return
        input_widget.value = ""
        input_widget.disabled = True
        conv = self.query_one("#conversation", VerticalScroll)
        conv.mount(ChatMessage(f"**You:** {message}", classes="user"))
        conv.scroll_end(animate=False)

        def do_agent():
            history = get_history("local")
            return agent_run(message, history)

        response = await self.run_in_thread(do_agent)
        save_messages("local", "tui", [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response.text},
        ])

        if response.tool_calls_made:
            tool_line = "  ".join(f"[🔍 {t}]" for t in response.tool_calls_made)
            conv.mount(ChatMessage(tool_line, classes="tool-call"))

        conv.mount(ChatMessage(response.text, classes="assistant"))

        if response.write_plans:
            self.pending_plans = response.write_plans
            for plan in response.write_plans:
                widget = WritePlanWidget(
                    f"**Proposed: {plan.operation}** → `{plan.path}`\n\n"
                    f"```diff\n{plan.preview[:500]}\n```\n\n"
                    f"[Enter] to apply · [Escape] to reject"
                )
                conv.mount(widget)

        conv.scroll_end(animate=False)
        input_widget.disabled = False
        input_widget.focus()

    async def action_reindex(self):
        from vault_cli.services import vault as v, index as idx, embed as emb
        from vault_cli.db.connection import init_db
        conv = self.query_one("#conversation", VerticalScroll)
        conv.mount(ChatMessage("[dim]Reindexing vault...[/dim]", classes="tool-call"))
        def do_reindex():
            init_db()
            notes = v.crawl_vault()
            chunks = [c for note in notes for c in v.chunk_note(note)]
            idx.upsert_chunks(chunks)
            emb.ensure_collection()
            emb.index_chunks(chunks)
            return len(chunks)
        n = await self.run_in_thread(do_reindex)
        conv.mount(ChatMessage(f"[green]✓ Reindexed {n} chunks[/green]", classes="assistant"))
        conv.scroll_end(animate=False)

    async def action_clear(self):
        conv = self.query_one("#conversation", VerticalScroll)
        await conv.remove_children()

    async def on_key(self, event):
        if event.key == "enter" and self.pending_plans:
            from vault_cli.services.writes import apply_plan
            plan = self.pending_plans
            result = apply_plan(plan)
            conv = self.query_one("#conversation", VerticalScroll)
            conv.mount(ChatMessage(f"[green]{result}[/green]", classes="assistant"))
            self.pending_plans = self.pending_plans[1:]
            conv.scroll_end(animate=False)

    def action_reject_plan(self):
        if self.pending_plans:
            self.pending_plans = []
            conv = self.query_one("#conversation", VerticalScroll)
            conv.mount(ChatMessage("[yellow]Write plan rejected.[/yellow]", classes="tool-call"))

def run_tui():
    app = ChatApp()
    app.run()
```

***

## 10. Frontend: Telegram Bot (`frontends/telegram_bot.py`)

python-telegram-bot v20 is fully async. Free-text messages route to the agent loop. Write plans are presented via `InlineKeyboardMarkup` — the user taps ✅ or ❌ and a `CallbackQueryHandler` fires.

```python
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from vault_cli.config import get_settings
from vault_cli.agent.loop import run as agent_run
from vault_cli.agent.schemas import WritePlan
from vault_cli.services.writes import apply_plan
from vault_cli.db.connection import get_history, save_messages, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory plan store keyed by plan_id
_pending_plans: dict[str, WritePlan] = {}

def _is_allowed(chat_id: int) -> bool:
    settings = get_settings()
    if not settings.telegram_allowed_chat_ids:
        return True
    return chat_id in settings.telegram_allowed_chat_ids

# ── Command handlers ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "**Vault CLI** — your Obsidian vault assistant\n\n"
        "/ask *question* — Q&A over vault\n"
        "/search *query* — keyword search\n"
        "/new *title* — create a note (follow prompts)\n"
        "/related *path* — find related notes\n"
        "/reindex — rebuild search index\n\n"
        "Or just send a message to chat with your vault."
    )
    await update.message.reply_markdown(text)

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_chat.id):
        return
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return
    from vault_cli.services.index import search_fts
    results = search_fts(query, limit=5)
    if not results:
        await update.message.reply_text("No results found.")
        return
    lines = [f"• **{r.note_title}** ({r.note_path})\n  {r.excerpt[:120]}" for r in results]
    await update.message.reply_markdown("\n\n".join(lines))

async def cmd_related(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_chat.id):
        return
    path = " ".join(context.args)
    if not path:
        await update.message.reply_text("Usage: /related <path>")
        return
    from vault_cli.services.related import find_related
    results = find_related(path, limit=5)
    if not results:
        await update.message.reply_text("No related notes found.")
        return
    lines = [f"• [[{r['title']}]] ({r['path']}) — {r['score']}" for r in results]
    await update.message.reply_markdown("\n".join(lines))

async def cmd_reindex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_chat.id):
        return
    await update.message.reply_text("Reindexing vault...")
    from vault_cli.services import vault as v, index as idx, embed as emb
    loop = asyncio.get_event_loop()
    def do_reindex():
        notes = v.crawl_vault()
        chunks = [c for note in notes for c in v.chunk_note(note)]
        idx.upsert_chunks(chunks)
        emb.ensure_collection()
        emb.index_chunks(chunks)
        return len(chunks)
    n = await loop.run_in_executor(None, do_reindex)
    await update.message.reply_text(f"✓ Reindexed {n} chunks.")

# ── Message handler (routes to agent) ────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update.effective_chat.id):
        return
    chat_id = str(update.effective_chat.id)
    text = update.message.text
    await update.message.reply_text("⏳ Searching your vault...")
    loop = asyncio.get_event_loop()
    history = get_history(chat_id)
    def do_agent():
        return agent_run(text, history)
    response = await loop.run_in_executor(None, do_agent)
    save_messages(chat_id, "telegram", [
        {"role": "user", "content": text},
        {"role": "assistant", "content": response.text},
    ])
    reply = response.text
    if response.tool_calls_made:
        reply += f"\n\n_Tools: {', '.join(response.tool_calls_made)}_"
    await update.message.reply_markdown(reply)
    for plan in response.write_plans:
        _pending_plans[plan.plan_id] = plan
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Apply", callback_data=f"apply:{plan.plan_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{plan.plan_id}"),
        ]])
        preview = plan.preview[:400] + ("..." if len(plan.preview) > 400 else "")
        await update.message.reply_text(
            f"**Proposed: {plan.operation}**\n`{plan.path}`\n\n```\n{preview}\n```",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

# ── Callback handler for write approval ──────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, plan_id = query.data.split(":", 1)
    plan = _pending_plans.pop(plan_id, None)
    if not plan:
        await query.edit_message_text("This plan has already been handled or expired.")
        return
    if action == "apply":
        result = apply_plan(plan)
        await query.edit_message_text(f"✅ {result}")
    else:
        await query.edit_message_text("❌ Write rejected.")

# ── Entry point ───────────────────────────────────────────────────

def run_bot():
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in .env")
    init_db()
    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("search", cmd_search))
    application.add_handler(CommandHandler("related", cmd_related))
    application.add_handler(CommandHandler("reindex", cmd_reindex))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Vault bot starting...")
    application.run_polling()
```

***

## 11. Database Layer (`db/connection.py`)

```python
import sqlite3
from pathlib import Path
from vault_cli.config import get_settings

def _conn() -> sqlite3.Connection:
    db_path = get_settings().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Run once on startup to create tables if they don't exist."""
    from vault_cli.services.index import init_db as init_index
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
```

***

## 12. SQLite Schema (Complete)

```sql
-- Notes metadata (used for fast lookups without re-reading files)
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT UNIQUE NOT NULL,
    title       TEXT,
    tags        TEXT,           -- JSON array
    modified_at DATETIME,
    indexed_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Chunks (heading-level sections for fine-grained retrieval)
CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,   -- SHA256 of path::heading
    note_path   TEXT NOT NULL REFERENCES notes(path),
    note_title  TEXT NOT NULL,
    heading     TEXT NOT NULL,
    text        TEXT NOT NULL,
    tags        TEXT,               -- Comma-separated
    char_offset INTEGER DEFAULT 0,
    indexed_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- FTS5 virtual table over chunks
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

-- Conversation history (shared across all frontends)
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL DEFAULT 'cli',    -- 'cli' | 'tui' | 'telegram'
    chat_id     TEXT NOT NULL DEFAULT 'local',  -- Telegram chat_id or 'local'
    role        TEXT NOT NULL,                  -- 'user' | 'assistant' | 'tool' | 'system'
    content     TEXT NOT NULL,
    tool_name   TEXT,
    ts          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_note ON chunks(note_path);
CREATE INDEX IF NOT EXISTS idx_conv_chat   ON conversations(chat_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_conv_source ON conversations(source, ts DESC);
```

***

## 13. `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vault-cli"
version = "0.1.0"
description = "Local Obsidian vault assistant powered by Ollama"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "textual>=0.60",
    "python-telegram-bot>=20.0",
    "ollama>=0.3",
    "python-frontmatter>=1.1",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "qdrant-client>=1.9",
    "markdown-it-py>=3.0",
    "rich>=13.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.0",
]

[project.scripts]
vault = "vault_cli.frontends.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["vault_cli"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

***

## 14. Testing Strategy

### Test structure

```python
# tests/conftest.py
import pytest
import tempfile
from pathlib import Path

@pytest.fixture
def temp_vault(tmp_path):
    """Create a minimal vault fixture with a few notes."""
    (tmp_path / "daily").mkdir()
    (tmp_path / "ai").mkdir()
    (tmp_path / "daily" / "2026-04-08.md").write_text(
        "---\ntags: [daily]\n---\n# 2026-04-08\n\n## Journal\nWorked on vault-cli today.\n"
    )
    (tmp_path / "ai" / "wisp.md").write_text(
        "---\ntags: [ai, assistant]\n---\n# Wisp\n\n## Architecture\nWisp uses Ollama and SQLite.\n"
    )
    return tmp_path

@pytest.fixture
def settings_override(temp_vault, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(temp_vault))
    monkeypatch.setenv("DB_PATH", str(temp_vault / "test.db"))
    monkeypatch.setenv("QDRANT_HOST", "http://localhost:6333")

# tests/test_vault.py
def test_crawl_finds_all_notes(temp_vault, settings_override):
    from vault_cli.services.vault import crawl_vault
    notes = crawl_vault()
    assert len(notes) == 2

def test_chunk_splits_on_headings(temp_vault, settings_override):
    from vault_cli.services.vault import crawl_vault, chunk_note
    notes = crawl_vault()
    wisp_note = next(n for n in notes if "wisp" in n.path)
    chunks = chunk_note(wisp_note)
    assert any(c.heading == "Architecture" for c in chunks)

# tests/test_writes.py
def test_append_plan_does_not_write(temp_vault, settings_override):
    from vault_cli.services.writes import append_note
    plan = append_note("ai/wisp.md", "New thought.")
    assert plan.operation == "append_note"
    content = (temp_vault / "ai" / "wisp.md").read_text()
    assert "New thought." not in content  # Not applied yet

def test_apply_plan_writes_file(temp_vault, settings_override):
    from vault_cli.services.writes import append_note, apply_plan
    plan = append_note("ai/wisp.md", "New thought.")
    apply_plan(plan)
    content = (temp_vault / "ai" / "wisp.md").read_text()
    assert "New thought." in content

# tests/test_cli.py
from typer.testing import CliRunner
from vault_cli.frontends.cli import app

runner = CliRunner()

def test_reindex_command(temp_vault, settings_override, mocker):
    mocker.patch("vault_cli.services.embed.ensure_collection")
    mocker.patch("vault_cli.services.embed.index_chunks")
    result = runner.invoke(app, ["reindex"])
    assert result.exit_code == 0
    assert "Reindex complete" in result.output
```

***

## 15. Obsidian-Specific Conventions

### Frontmatter Standard

For consistent indexing, use this frontmatter template for all notes created by vault-cli:

```yaml
---
title: Note Title Here
tags:
  - primary-tag
  - secondary-tag
created: 2026-04-08T12:00:00
modified: 2026-04-08T12:00:00
type: note        # note | journal | project | resource | moc
---
```

### Daily Note Format

The `DAILY_NOTE_FOLDER` setting controls where daily notes land. The recommended format:

```yaml
---
title: 2026-04-08
tags:
  - daily
created: 2026-04-08
---
# 2026-04-08

## Morning

## Journal

## Tasks
- [ ] 

## Notes
```

### Tag Conventions

- Tags should be lowercase, hyphenated: `ai-tools`, `daily`, `project-wisp`
- Avoid spaces in tags — use hyphens
- Use a consistent type tag: `daily`, `project`, `resource`, `moc`, `fleeting`

### Ignore Patterns

The default `IGNORE_GLOBS` excludes:
- `.obsidian/**` — plugin config, workspace state
- `templates/**` — note templates (not notes themselves)
- `.trash/**` — Obsidian's deleted notes
- `*.canvas` — Obsidian canvas files (not markdown)

***

## 16. Safety Model

| Operation | Behavior |
|-----------|----------|
| `search_notes` | Free — callable directly, no confirmation |
| `semantic_search` | Free — callable directly, no confirmation |
| `read_note` | Free — callable directly, no confirmation |
| `list_related_notes` | Free — callable directly, no confirmation |
| `propose_append_to_note` | Returns `WritePlan` JSON — never auto-applied |
| `propose_create_note` | Returns `WritePlan` JSON — never auto-applied |
| `propose_update_frontmatter` | Returns `WritePlan` JSON — never auto-applied |
| `apply_plan()` | Only callable by frontend after explicit user confirmation |
| Delete / rename | Not exposed to agent at all in v1 |
| Bulk retag | Only via `vault append --yes` with a reviewed script |

Every `apply_plan()` call appends to `vault-cli-audit.log`:
```
2026-04-08T12:00:00|append_note|ai/wisp.md
2026-04-08T12:01:00|create_note|daily/2026-04-08.md
```

***

## 17. Deployment

### Docker Compose (Qdrant + optional Ollama)

```yaml
# deploy/docker-compose.yml
services:
  qdrant:
    image: qdrant/qdrant
    container_name: vault-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

  # Only include if you want Ollama in Docker (M1 Mac: run Ollama natively)
  # ollama:
  #   image: ollama/ollama
  #   ports:
  #     - "11434:11434"
  #   volumes:
  #     - ollama_data:/root/.ollama

volumes:
  qdrant_data:
```

Run with: `docker compose up -d`

### Telegram Bot as systemd Service

```ini
# deploy/vault-cli.service
[Unit]
Description=Vault CLI Telegram Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/home/your-user/vault-cli
ExecStart=/home/your-user/vault-cli/.venv/bin/vault bot
Restart=on-failure
RestartSec=5s
EnvironmentFile=/home/your-user/vault-cli/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp deploy/vault-cli.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vault-cli
sudo systemctl start vault-cli
```

### Initial Setup (from scratch)

```bash
# 1. Clone / create project
cd ~/vault-cli

# 2. Install with uv
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 3. Copy and edit env
cp .env.example .env
# Edit VAULT_PATH, TELEGRAM_BOT_TOKEN, etc.

# 4. Start Qdrant
docker compose up -d qdrant

# 5. Pull models in Ollama
ollama pull llama3.2
ollama pull nomic-embed-text

# 6. Initialize DB and index vault
vault reindex

# 7. Test
vault search "test"
vault ask "What notes do I have about AI?"

# 8. Start bot (optional)
vault bot
```

***

## 18. Common Pitfalls and Solutions

| Problem | Cause | Fix |
|---------|-------|-----|
| Agent loops infinitely | Small model (3b) confused by tool schema | Set `AGENT_MAX_ITERATIONS=6`; switch to `qwen2.5` |
| FTS5 returns no results for fuzzy terms | FTS5 is exact-match | Use `MATCH 'term*'` for prefix search, or fall back to semantic |
| Qdrant dimension mismatch | Changed embedding model without wiping collection | Delete collection in Qdrant, re-run `vault reindex` |
| Telegram bot stops after sleep | PTB v20 polling drops on network changes | Use `application.run_polling(drop_pending_updates=True)` |
| Frontmatter write scrambles note | YAML dump reorders keys | Use `python-frontmatter` not raw `yaml.dump` — it preserves order |
| Chunk too large for context | Notes without headings become one big chunk | Add a `MAX_CHUNK_CHARS=2000` split as fallback in `chunk_note()` |
| `nomic-embed-text` slow on first query | Model cold-start on Ollama | Pre-warm: run `ollama run nomic-embed-text ""` at startup |
| `vault chat` crashes on import | `textual` not installed | Confirm `uv pip install -e .` — textual is a main dep, not optional |

***

## 19. Build Sequence (Phased MVP)

### Phase 1 — Core services + direct CLI (Days 1–3)
Goal: `vault reindex`, `vault search`, `vault new`, `vault append` all working.

1. `config.py` + `.env.example` — freeze settings schema first
2. `db/connection.py` + SQLite schema migration
3. `services/vault.py` — crawl, read, chunk
4. `services/index.py` — FTS5 schema, upsert, search
5. `services/writes.py` — WritePlan model, `create_note`, `append_note`, `apply_plan`
6. `frontends/cli.py` — `reindex`, `search`, `new`, `append` subcommands
7. Smoke tests: crawl temp vault, FTS search returns results, write plan applies correctly

### Phase 2 — Embeddings + agent (Days 4–6)
Goal: `vault ask "..."` works end-to-end with tool calling.

8. `services/embed.py` — Ollama embed calls, Qdrant upsert/search
9. `services/related.py` — cosine similarity link suggestions
10. `agent/schemas.py` — all Pydantic models
11. `agent/tools.py` — tool function definitions, TOOLS list
12. `agent/loop.py` — Ollama chat + tool loop with iteration cap
13. `frontends/cli.py` — add `ask` and `related` subcommands
14. Tests: mock Ollama, verify tool dispatch, verify WritePlan extraction

### Phase 3 — TUI (Days 7–9)
Goal: `vault chat` launches a working Textual chat window.

15. `frontends/tui.py` — `ChatApp` with message history
16. Tool call status display inline
17. `WritePlanWidget` with Enter/Escape approval
18. Theme registration and dark mode

### Phase 4 — Telegram (Days 10–11)
Goal: Bot runs, responds to messages and commands, write approval via inline keyboard.

19. `frontends/telegram_bot.py` — all command handlers
20. Per-chat history from SQLite
21. `WritePlan` InlineKeyboard callback handler
22. `deploy/vault-cli.service` systemd unit

### Phase 5 — Polish (Ongoing)
- Streaming Ollama responses into TUI (use `stream=True` and `call_later`)
- `/history` Telegram command — show last N turns
- Rate limiting in Telegram bot
- `vault history` CLI command to show and clear conversation
- `MAX_CHUNK_CHARS` fallback chunking for heading-free notes
- Tag normalization on `create_note`

***

## 20. Extension Points

Future capabilities that can be added without breaking the current architecture:

- **Automatic tagging**: after `reindex`, run a batch Ollama pass over untagged notes and propose frontmatter updates
- **MOC generation**: cluster notes by BERTopic/K-means, auto-generate a Map of Content from each cluster
- **Note splitting**: detect notes with ≥3 headings of sufficient length, propose splits into child notes
- **Obsidian MCP server**: replace file-based vault access with a Model Context Protocol server for stricter permission boundaries
- **Voice capture**: pipe speech-to-text into `vault append daily "..."` for quick capture
- **Scheduled digests**: daily cron/systemd timer to run `vault ask "Summarize what I wrote this week"` and post to Telegram
- **Git integration**: auto-commit vault changes after each `apply_plan()` with a structured commit message

---

## References

1. [Tool calling - Ollama's documentation](https://docs.ollama.com/capabilities/tool-calling)

2. [Command CLI Options - Typer](https://typer.tiangolo.com/tutorial/commands/options/) - Commands can also have their own CLI options. In fact, each command can have different CLI arguments...

3. [Commands - Typer](https://typer.tiangolo.com/tutorial/commands/) - Typer allows you to create CLI programs with several commands (also known as subcommands). For examp...

4. [Python telegram bot v20 run asynchronously](https://stackoverflow.com/questions/76625766/python-telegram-bot-v20-run-asynchronously) - from telegram import Update from telegram.ext import ApplicationBuilder, CommandHandler, ContextType...

5. [Textual](https://textual.textualize.io) - Textual is a Rapid Application Development framework for Python, built by Textualize.io. Build sophi...

6. [Typer](https://typer.tiangolo.com) - Typer is a library for building CLI applications that users will love using and developers will love...

7. [Python Textual: Build Beautiful UIs in the Terminal](https://realpython.com/python-textual/) - Welcome to Textual, a Python toolkit and framework for creating beautiful, functional text-based use...

8. [How to Build and Deploy a python-telegram-bot v20 Webhook](https://www.freecodecamp.org/news/how-to-build-and-deploy-python-telegram-bot-v20-webhooks/) - By Chua Hui Shun The python-telegram-bot v20 release introduced major structural changes. According ...

9. [PTB goes asyncio in v20! · python-telegram-bot ...](https://github.com/python-telegram-bot/python-telegram-bot/discussions/2351) - We are embracing the future: asyncio support is on its way and it's gonna be legen, wait for it, -da...

10. [Tool support · Ollama Blog](https://ollama.com/blog/tool-support) - Ollama now supports tool calling with popular models such as Llama 3.1. This enables a model to answ...

11. [Using Ollama with Python: Step-by-Step Guide - Cohorte Projects](https://www.cohorte.co/blog/using-ollama-with-python-step-by-step-guide) - Ollama makes it easy to integrate local LLMs into your Python projects with just a few lines of code...

12. [Getting started with SQLite Full-text Search By Examples](https://www.sqlitetutorial.net/sqlite-full-text-search/) - Summary: in this tutorial, you will learn how to use the SQLite full-text search feature by using th...

13. [SQLite FTS5 Extension](https://www.sqlite.org/fts5.html) - Overview of FTS5. FTS5 is an SQLite virtual table module that provides full-text search functionalit...

14. [Qdrant Vector Database: Fast and Efficient Similarity Search](https://michaeljohnpena.com/blog/2023-01-29-qdrant-basics/) - Qdrant Vector Database: Fast and Efficient Similarity Search - A blog post by Michael John Peña

15. [Qdrant | DeepEval by Confident AI - The LLM Evaluation Framework](https://deepeval.com/integrations/vector-databases/qdrant) - Quick Summary

16. [python-frontmatter - PyPI](https://pypi.org/project/python-frontmatter/) - Python Frontmatter. Jekyll-style YAML front matter offers a useful way to add arbitrary, structured ...

17. [Working with Front Matter in Python - Raymond Camden](https://www.raymondcamden.com/2022/01/06/working-with-frontmatter-in-python) - Keys in front matter can be addressed in dictionary-style in the result and .content can be used to ...

18. [Testing - Typer](https://typer.tiangolo.com/tutorial/testing/) - Typer, build great CLIs. Easy to code. Based on Python type hints.

19. [nomic-embed-text-v2-moe - Ollama](https://ollama.com/library/nomic-embed-text-v2-moe) - High Performance: SoTA Multilingual performance compared to ~300M parameter models, competitive with...

20. [toshk0/nomic-embed-text-v2-moe - Ollama](https://ollama.com/toshk0/nomic-embed-text-v2-moe) - High Performance: SoTA Multilingual performance compared to ~300M parameter models, competitive with...

21. [Finding the Best Open-Source Embedding Model for RAG - Tiger Data](https://www.tigerdata.com/blog/finding-the-best-open-source-embedding-model-for-rag) - This blog post will walk you through an easy-to-replicate workflow for comparing open-source embeddi...

22. [Nomic's New Embedding Model | nomic-embed-text - YouTube](https://www.youtube.com/watch?v=LpcaeQZDVB8) - and text-embedding-3-small performance on short and long context ... ollama #nomicembedtext #embeddi...

23. [realpython.com › ollama-python](https://realpython.com/ollama-python/) - Learn how to integrate your Python projects with local models (LLMs) using Ollama for enhanced priva...

24. [Ollama models endlessly loop instead of respond · Issue #81 · google/adk-python](https://github.com/google/adk-python/issues/81) - I have tried multiple models through ollama but all of them end up in a recursive loop where they en...
