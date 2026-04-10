import frontmatter
import re
import hashlib
from pathlib import Path
from fnmatch import fnmatch
from mnemosyne.config import get_settings
from mnemosyne.agent.schemas import Note, Chunk
from datetime import datetime

def _should_ignore(path: Path, vault_root: Path) -> bool:
    try:
        rel = str(path.relative_to(vault_root))
    except ValueError:
        rel = path.name
    # Always ignore .git and .DS_Store directories/files
    if rel.startswith('.git') or rel == '.DS_Store':
        return True
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
        if md_file.is_file():
            notes.append(read_note(md_file))
    return notes

def get_note_titles() -> set[str]:
    """Return a set of all note titles in the vault."""
    return set(note.title for note in crawl_vault())

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
    try:
        rel_path = str(path.relative_to(vault))
    except ValueError:
        rel_path = path.name
    # Try to extract title from Markdown if not in frontmatter
    if "title" in fm:
        title = fm["title"]
    else:
        m = re.search(r"^# (.+)", body, re.MULTILINE)
        title = m.group(1) if m else path.stem
    return Note(
        path=rel_path,
        title=title,
        body=body,
        frontmatter=fm,
        tags=tags,
        wikilinks=wikilinks,
        headings=headings,
        modified_at=datetime.fromtimestamp(path.stat().st_mtime),
    )

def chunk_note(note: Note) -> list[Chunk]:
    """Split note body into heading-level chunks, or fallback to MAX_CHUNK_CHARS."""
    heading_pattern = re.compile(r'^(#{1,6}\s+.+)$', re.MULTILINE)
    splits = heading_pattern.split(note.body)
    chunks = []
    # splits alternates: [pre-heading content, heading, content, heading, content...]
    # Handle intro text before first heading
    if splits and splits[0].strip():
        chunk_text = f"# {note.title}\n{splits[0].strip()}"
        chunks.append(_make_chunk(note, "Introduction", chunk_text, 0))
    offset = len(splits[0]) if splits else 0
    for i in range(1, len(splits), 2):
        heading = splits[i].strip() if i < len(splits) else ""
        content = splits[i + 1].strip() if i + 1 < len(splits) else ""
        if heading or content:
            chunk_text = f"{heading}\n{content}".strip()
            chunks.append(_make_chunk(note, heading.lstrip('#').strip(), chunk_text, offset))
        offset += len(heading) + len(content)
    if chunks:
        return chunks
    # Fallback: no headings, split by MAX_CHUNK_CHARS
    settings = get_settings()
    max_len = getattr(settings, "max_chunk_chars", 1200)
    body = note.body.strip()
    fallback_chunks = []
    for i in range(0, len(body), max_len):
        part = body[i:i+max_len]
        heading = f"{note.title} (part {i//max_len+1})"
        fallback_chunks.append(_make_chunk(note, heading, part, i))
    return fallback_chunks if fallback_chunks else [_make_chunk(note, note.title, note.body, 0)]

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
