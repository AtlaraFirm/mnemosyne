from mnemosyne.services import index as idx_svc
from mnemosyne.services import embed as emb_svc
from mnemosyne.services import vault as vault_svc
from mnemosyne.services import writes as write_svc
from mnemosyne.services import related as rel_svc
from mnemosyne.config import get_settings
import json

def search_notes(query: str, limit: int = 5) -> str:
    # Final safety: coerce query to string if not already
    if isinstance(query, dict):
        import json
        query = json.dumps(query)
    elif not isinstance(query, str):
        query = str(query)
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

import inspect

def dispatch(name: str, arguments: dict) -> str:
    fn = TOOL_MAP.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    sig = inspect.signature(fn)
    filtered_args = {}
    import logging
    logging.basicConfig(filename='debug.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    logging.debug(f"Dispatching tool '{name}' with arguments: {arguments}")
    for k, v in arguments.items():
        if k in sig.parameters:
            param = sig.parameters[k]
            logging.debug(f"Param: {k}, Expected: {param.annotation}, Value: {v}, Type: {type(v)}")
            # Coerce argument to expected type if possible
            expected_type = param.annotation
            if expected_type is not inspect._empty and not isinstance(v, expected_type):
                try:
                    # Special handling: if expecting str and value is dict, use json.dumps
                    if expected_type is str and isinstance(v, dict):
                        import json
                        filtered_args[k] = json.dumps(v)
                    else:
                        filtered_args[k] = expected_type(v)
                except Exception:
                    filtered_args[k] = str(v) if expected_type is str else v  # fallback
            else:
                filtered_args[k] = v
    logging.debug(f"Filtered args for '{name}': {filtered_args}")
    return fn(**filtered_args)

