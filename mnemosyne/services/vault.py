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
    if tags is None or tags == "":
        tags = []
    elif isinstance(tags, str):
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
    """
    Improved: Split note body into heading-level chunks, or by paragraphs/lists if no headings, or fallback to MAX_CHUNK_CHARS.
    """
    import re
    settings = get_settings()
    max_len = getattr(settings, "max_chunk_chars", 1200)
    body = note.body.strip()
    # 1. Try headings
    heading_pattern = re.compile(r'^(#{1,6}\s+.+)$', re.MULTILINE)
    splits = heading_pattern.split(body)
    chunks = []
    if len(splits) > 1:
        # [intro, heading, content, heading, content...]
        if splits[0].strip():
            chunk_text = f"# {note.title}\n{splits[0].strip()}"
            chunks.append(_make_chunk(note, "Introduction", chunk_text, 0))
        offset = len(splits[0])
        for i in range(1, len(splits), 2):
            heading = splits[i].strip() if i < len(splits) else ""
            content = splits[i + 1].strip() if i + 1 < len(splits) else ""
            if heading or content:
                chunk_text = f"{heading}\n{content}".strip()
                chunks.append(_make_chunk(note, heading.lstrip('#').strip(), chunk_text, offset))
            offset += len(heading) + len(content)
        if chunks:
            return chunks
    # 2. Try splitting by bullet lists or paragraphs
    para_pattern = re.compile(r'(?:^|\n)([-*+]\s+.+)', re.MULTILINE)
    para_splits = para_pattern.split(body)
    if len(para_splits) > 1:
        offset = 0
        for part in para_splits:
            part = part.strip()
            if not part:
                continue
            if len(part) > max_len:
                # Further split long bullets/paras
                for i in range(0, len(part), max_len):
                    chunk = part[i:i+max_len]
                    chunks.append(_make_chunk(note, "Paragraph", chunk, offset))
                    offset += len(chunk)
            else:
                chunks.append(_make_chunk(note, "Paragraph", part, offset))
                offset += len(part)
        if chunks:
            return chunks
    # 3. Fallback: split by paragraphs
    paras = [p for p in body.split('\n\n') if p.strip()]
    if len(paras) > 1:
        offset = 0
        for p in paras:
            p = p.strip()
            if len(p) > max_len:
                for i in range(0, len(p), max_len):
                    chunk = p[i:i+max_len]
                    chunks.append(_make_chunk(note, "Paragraph", chunk, offset))
                    offset += len(chunk)
            else:
                chunks.append(_make_chunk(note, "Paragraph", p, offset))
                offset += len(p)
        if chunks:
            return chunks
    # 4. Fallback: split by max chars
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
