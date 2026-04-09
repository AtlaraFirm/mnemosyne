from mnemosyne.services import index as idx_svc
from mnemosyne.services import embed as emb_svc
from mnemosyne.services import vault as vault_svc
from mnemosyne.services import writes as write_svc
from mnemosyne.services import related as rel_svc
from mnemosyne.config import get_settings
import json

def search_notes(query: str, limit: int = 5) -> str:
    results = idx_svc.search_fts(query, limit)
    if not results:
        return "No notes found matching that query."
    lines = [f"[{r.score:.2f}] {r.note_title} ({r.note_path})\n  {r.excerpt}" for r in results]
    return "\n\n".join(lines)

def semantic_search(query: str, limit: int = 5) -> str:
    results = emb_svc.semantic_search(query, limit)
    if not results:
        return "No semantically related notes found."
    lines = [f"[{r.score:.3f}] {r.note_title} > {r.heading} ({r.note_path})\n  {r.excerpt}" for r in results]
    return "\n\n".join(lines)

def read_note(path: str) -> str:
    from pathlib import Path
    abs_path = Path(get_settings().vault_path) / path
    if not abs_path.exists():
        return f"Note not found: {path}"
    note = vault_svc.read_note(abs_path)
    return f"# {note.title}\nTags: {', '.join(note.tags)}\n\n{note.body}"

def list_related_notes(path: str, limit: int = 5) -> str:
    related = rel_svc.find_related(path, limit)
    if not related:
        return "No closely related unlinked notes found."
    lines = [f"[{r['score']}] [[{r['title']}]] ({r['path']})" for r in related]
    return "\n".join(lines)

def propose_append_to_note(path: str, text: str) -> str:
    plan = write_svc.append_note(path, text)
    return plan.model_dump_json()

def propose_create_note(title: str, body: str, folder: str = "", tags: list[str] = None) -> str:
    plan = write_svc.create_note(title, body, folder, tags or [])
    return plan.model_dump_json()

def propose_update_frontmatter(path: str, updates_json: str) -> str:
    updates = json.loads(updates_json)
    plan = write_svc.update_frontmatter(path, updates)
    return plan.model_dump_json()

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
