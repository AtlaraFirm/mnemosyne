import difflib
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

import frontmatter

from mnemosyne.agent.schemas import WritePlan
from mnemosyne.config import get_settings


def _vault() -> Path:
    return Path(get_settings().vault_path)


def _strip_empty_wikilinks(text: str) -> str:
    # Replace [[   ]] or [[\t]] or [[ ]] (empty/whitespace-only wikilinks) with a single space
    return re.sub(r"\[\[\s*\]\]", " ", text)

def _is_body_effectively_empty(body: str) -> bool:
    # Returns True if body is empty, whitespace, or only comments (lines starting with # or // or <!-- ... -->)
    if not body or not body.strip():
        return True
    # Remove HTML comments
    body_wo_html_comments = re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL)
    # Remove lines that are only comments
    lines = [line for line in body_wo_html_comments.splitlines() if line.strip() and not line.strip().startswith('#') and not line.strip().startswith('//')]
    # If nothing left, it's empty or only comments
    return not any(line.strip() for line in lines)

def create_note(
    title: str, body: str, folder: str = "", tags: list[str] = []
) -> WritePlan:
    # Suppress tags, related links, and Related section if body is empty or only comments
    if _is_body_effectively_empty(body):
        tags = []
        body = ""
        suppress_related = True
    else:
        suppress_related = False

    # Input validation
    if not title or not title.strip():
        raise ValueError("Note title cannot be empty.")
    if any(x in title for x in ["..", "/", "\\", ":", "|", "?", "*", "<", ">"]):
        raise ValueError("Invalid characters in note title.")
    if title.startswith("."):
        raise ValueError("Note title cannot start with a dot.")
    folder = folder or ""
    safe_title = (
        title.replace("/", "-")
        .replace("\\", "-")
        .replace("..", "-")
        .replace(";", "-")
        .replace(":", "-")
        .replace("|", "-")
        .replace("?", "-")
        .replace("*", "-")
        .replace("<", "-")
        .replace(">", "-")
    )
    rel_path = f"{folder}/{safe_title}.md".lstrip("/")
    abs_path = _vault() / rel_path

    # Tag normalization: lowercase, hyphenated
    def normalize_tag(tag):
        return tag.strip().lower().replace(" ", "-").replace("_", "-")

    # If body is empty/whitespace/comments, do not insert tags, related links, or Related section
    if _is_body_effectively_empty(body):
        norm_tags = []
        folder_tags = []
        auto_tags = []
        all_tags = []
        body_linked = ""
        fm = {"title": title, "created": datetime.utcnow().isoformat(), "tags": all_tags}
        post = frontmatter.Post(body_linked, **fm)
        preview = f"CREATE {rel_path}\n\n{frontmatter.dumps(post)}"
        return WritePlan(
            operation="create_note",
            path=rel_path,
            preview=preview,
            payload={"abs_path": str(abs_path), "content": frontmatter.dumps(post)},
        )

    norm_tags = [normalize_tag(t) for t in (tags or []) if t.strip()]

    # Folder tags: add all parent folders as tags (lowercased, hyphenated)
    folder_tags = []
    if folder:
        folder_tags = [normalize_tag(part) for part in folder.split("/") if part.strip()]
    
    # Suppress auto/folder tags for empty/trivial notes
    def is_trivial_note(text: str) -> bool:
        # Empty, whitespace, or only comments (lines starting with # or //)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return True
        return all(l.startswith('#') or l.startswith('//') for l in lines)

    if is_trivial_note(body):
        folder_tags = []
        auto_tags = []
    else:
        # Auto-tagging: extract top keywords from body (simple approach)
        STOPWORDS = set(
        [
            "the",
            "and",
            "for",
            "are",
            "but",
            "not",
            "you",
            "with",
            "that",
            "this",
            "was",
            "have",
            "from",
            "they",
            "his",
            "her",
            "she",
            "him",
            "all",
            "can",
            "had",
            "one",
            "has",
            "were",
            "their",
            "what",
            "when",
            "your",
            "out",
            "use",
            "how",
            "which",
            "will",
            "each",
            "about",
            "many",
            "then",
            "them",
            "these",
            "some",
            "would",
            "make",
            "like",
            "himself",
            "herself",
            "into",
            "more",
            "other",
            "could",
            "our",
            "there",
            "been",
            "if",
            "no",
            "than",
            "so",
            "may",
            "on",
            "in",
            "to",
            "of",
            "a",
            "an",
            "is",
            "it",
            "as",
            "at",
            "by",
            "be",
            "or",
            "we",
            "do",
            "did",
            "does",
            "up",
            "down",
            "over",
            "under",
            "again",
            "very",
            "just",
            "any",
            "now",
            "who",
            "where",
            "why",
            "because",
            "while",
            "between",
            "both",
            "few",
            "most",
            "such",
            "own",
            "same",
            "too",
            "s",
            "t",
            "can",
            "will",
            "don",
            "should",
            "ll",
            "d",
            "re",
            "ve",
            "m",
        ]
    )
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", body.lower())
    keywords = [w for w in words if w not in STOPWORDS]
    freq = Counter(keywords)
    auto_tags = [normalize_tag(w) for w, _ in freq.most_common(5) if w not in norm_tags]
    all_tags = sorted(set(norm_tags + folder_tags + auto_tags))

    # Auto-linking: add wikilinks for other note titles
    from mnemosyne.services.vault import get_note_titles

    note_titles = get_note_titles()

    IGNORE_LINK_TITLES = {'', ' '}
    def add_wikilinks(text):
        for t in sorted(note_titles, key=len, reverse=True):
            if not t or not t.strip() or t in IGNORE_LINK_TITLES:
                continue
            if t != title and t in text and f"[[{t}]]" not in text:
                text = re.sub(rf"(?<!\[\[)\b{re.escape(t)}\b(?!\]\])", f"[[{t}]]", text)
        return text

    # Strip empty/whitespace-only wikilinks before/after auto-linking
    body_cleaned = _strip_empty_wikilinks(body)
    body_linked = add_wikilinks(body_cleaned)

    # Final cleanup in case auto-linking introduced any empty wikilinks
    body_linked = _strip_empty_wikilinks(body_linked)

    fm = {"title": title, "created": datetime.utcnow().isoformat(), "tags": all_tags}
    post = frontmatter.Post(body_linked, **fm)
    preview = f"CREATE {rel_path}\n\n{frontmatter.dumps(post)}"
    return WritePlan(
        operation="create_note",
        path=rel_path,
        preview=preview,
        payload={"abs_path": str(abs_path), "content": frontmatter.dumps(post)},
    )


def _insert_or_update_related_section(content: str, related_links: list[dict], suppress: bool = False) -> str:
    """
    Insert or update a '## Related' section at the end of the note with wikilinks to related notes using their paths.
    related_links: list of dicts with at least 'title' and 'path' keys.
    Do NOT insert the Related section if it would be the only content in the note.
    """
    import re
    # Remove any existing Related section
    content_wo_related = re.sub(r"\n## Related\n(.|\n)*$", "", content, flags=re.MULTILINE).rstrip()
    # If the note would be empty or only whitespace, do not insert Related section
    if not content_wo_related.strip():
        return content_wo_related
    # Always use the note path for the link, not just the title
    related_section = "\n## Related\n" + "\n".join(f"- [[{link['path']}|{link['title']}]]" for link in related_links) + "\n"
    return content_wo_related + related_section

def append_note(path: str, text: str, section: Optional[str] = None, related_links: Optional[list[dict]] = None) -> WritePlan:
    abs_path = _vault() / path
    original = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
    # If text is empty/whitespace/comments, do not insert related links or Related section
    if _is_body_effectively_empty(text):
        new_content = original.rstrip() + f"\n\n{text}\n"
    else:
        new_content = original.rstrip() + f"\n\n{text}\n"
        if related_links is not None:
            new_content = _insert_or_update_related_section(new_content, related_links, suppress=_is_body_effectively_empty(text))
    diff = "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
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
    # Also strip empty wikilinks from body if present
    if isinstance(post.content, str):
        post.content = _strip_empty_wikilinks(post.content)
    new_content = frontmatter.dumps(post)
    diff = "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    return WritePlan(
        operation="update_frontmatter",
        path=path,
        preview=diff,
        payload={"abs_path": str(abs_path), "content": new_content},
    )


def flatten_vault() -> list[str]:
    """
    Move all .md notes (except index.md) to the vault root, delete all index.md files, and remove all empty folders.
    Update tags to remove old folder tags and add new ones.
    Returns a list of actions performed.
    """
    from pathlib import Path
    import os, shutil, frontmatter
    actions = []
    vault_root = _vault()
    # 1. Move all .md notes (except index.md) to root
    for md_file in vault_root.rglob("*.md"):
        if md_file.name == "index.md":
            continue
        if md_file.parent == vault_root:
            continue  # Already at root
        dest = vault_root / md_file.name
        orig_dest = dest
        i = 1
        while dest.exists():
            dest = vault_root / f"{md_file.stem}_{i}.md"
            i += 1
        shutil.move(str(md_file), str(dest))
        actions.append(f"Moved {md_file} -> {dest}")
    # 2. Delete all index.md files
    for idx_file in vault_root.rglob("index.md"):
        idx_file.unlink()
        actions.append(f"Deleted {idx_file}")
    # 3. Remove all empty folders (bottom up)
    for folder in sorted([p for p in vault_root.rglob("*") if p.is_dir()], key=lambda p: -len(str(p))):
        try:
            if not any(folder.iterdir()):
                folder.rmdir()
                actions.append(f"Removed empty folder {folder}")
        except Exception:
            pass
    return actions

def sweep_links(fix: bool = True) -> list[dict]:
    """
    Sweep all notes for broken links. If fix=True, attempt to fix or remove broken links.
    Returns a report of actions taken or issues found.
    """
    from mnemosyne.services.vault import crawl_vault, get_note_titles
    import frontmatter
    import os
    from pathlib import Path
    vault_root = _vault()
    notes = crawl_vault()
    note_titles = get_note_titles()
    note_paths = set(str(note.path)[:-3] if str(note.path).endswith('.md') else str(note.path) for note in notes)
    actions = []
    for note in notes:
        path = vault_root / note.path
        post = frontmatter.load(str(path))
        content = post.content if hasattr(post, 'content') else ""
        changed = False
        # Find all wikilinks
        wikilinks = set(re.findall(r"\[\[([^\]]+)\]\]", content))
        for wikilink in wikilinks:
            if wikilink not in note_titles and wikilink not in note_paths:
                if fix:
                    # Remove broken link
                    content_new = re.sub(rf"\[\[\s*{re.escape(wikilink)}\s*\]\]", "", content)
                    if content_new != content:
                        content = content_new
                        changed = True
                        actions.append({'action': 'removed', 'note': str(note.path), 'wikilink': wikilink})
                else:
                    actions.append({'action': 'broken', 'note': str(note.path), 'wikilink': wikilink})
        if changed and fix:
            post.content = content
            post.metadata['tags'] = [t for t in post.metadata.get('tags', [])]
            post_new = frontmatter.dumps(post)
            path.write_text(post_new, encoding="utf-8")
    return actions

def organize_notes(rules: dict = None) -> list[WritePlan]:
    """
    Scan all notes and propose WritePlans for tagging, linking, cleanup, index note creation, and rules-based folder organization.
    rules: dict, e.g. {"by": "tag"|"date"|"custom", ...}
    """
    from mnemosyne.services.vault import crawl_vault, get_note_titles
    import os
    from pathlib import Path
    import shutil
    import re
    import frontmatter

    notes = crawl_vault()
    note_titles = get_note_titles()
    note_paths = set(str(note.path)[:-3] if str(note.path).endswith('.md') else str(note.path) for note in notes)
    plans = []
    broken_links_report = []
    rules = rules or {"by": "tag", "major_tags": ["project", "journal", "reference"]}

    # Organize individual notes
    for note in notes:
        tags = [t.strip().lower().replace(" ", "-").replace("_", "-") for t in note.tags]
        body = note.body
        IGNORE_LINK_TITLES = {'', ' ', 'a', 'h', 'an', 'the', 'and', 'or', 'but', 'if', 'then', 'else', 'when', 'at', 'by', 'for', 'with', 'without', 'on', 'in', 'to', 'of', 'b'}
        # Only insert wikilinks into the body if not running suggest_links or suggest_links_tags in apply mode
        insert_links_in_body = not (os.environ.get("MNEMO_SUGGEST_LINKS_APPLY") == "1")
        if insert_links_in_body:
            for t in sorted(note_titles, key=len, reverse=True):
                if not t or not t.strip() or t in IGNORE_LINK_TITLES:
                    continue
                if t != note.title and t in body and f"[[{t}]]" not in body:
                    body = re.sub(rf"(?<!\[\[)\b{re.escape(t)}\b(?!\]\])", f"[[{t}]]", body)
        # Strip empty/whitespace-only wikilinks from body
        body = _strip_empty_wikilinks(body)
        tags = sorted(set(tags))
        changed = tags != note.tags or body != note.body
        if changed:
            fm_updates = {"tags": tags}
            plans.append(update_frontmatter(note.path, fm_updates))
            post = frontmatter.Post(body, **{**note.frontmatter, "tags": tags})
            preview = f"CLEANUP {note.path}\n\n{frontmatter.dumps(post)}"
            plans.append(
                WritePlan(
                    operation="append_note",
                    path=note.path,
                    preview=preview,
                    payload={
                        "abs_path": str(_vault() / note.path),
                        "content": frontmatter.dumps(post),
                    },
                )
            )
        # --- Broken wikilink detection ---
        for wikilink in getattr(note, 'wikilinks', []):
            if wikilink not in note_titles and wikilink not in note_paths:
                broken_links_report.append({'source': str(note.path), 'wikilink': wikilink})

    # Optionally, write broken links to a file or log for later fixing
    if broken_links_report:
        import json
        report_path = _vault() / "broken_wikilinks_report.json"
        report_path.write_text(json.dumps(broken_links_report, indent=2), encoding="utf-8")

    vault_root = _vault()

    # Create/update index note in every directory, linking only to subdirectory indexes
    for dirpath, dirnames, filenames in os.walk(vault_root):
        dirpath = Path(dirpath)
        subdirs = [d for d in dirnames if not d.startswith(".")]
        notes = [
            f for f in filenames if f.endswith(".md") and f != "index.md" and not f.startswith(".")
        ]
        if not notes and not subdirs:
            continue
        lines = []
        for note in sorted(notes):
            rel_note_path = (dirpath / note).relative_to(vault_root)
            rel_note_path_str = str(rel_note_path)[:-3]
            lines.append(f"- [[{rel_note_path_str}]]")
        # Group subdirectories by prefix (e.g., journal/2026/04)
        grouped = {}
        for subdir in sorted(subdirs):
            parts = subdir.split("-")
            prefix = parts[0] if len(parts) > 1 else subdir
            grouped.setdefault(prefix, []).append(subdir)
        for prefix, group in grouped.items():
            if len(group) > 1:
                lines.append(f"## {prefix}")
            for subdir in group:
                rel_subdir_index = (dirpath / subdir / "index").relative_to(vault_root)
                lines.append(f"- [[{rel_subdir_index}]]")
        index_body = "# Index\n\n" + "\n".join(lines)
        index_tags = ["index"]
        index_path = dirpath / "index.md"
        post = frontmatter.Post(index_body, **{"title": "Index", "tags": index_tags})
        preview = (
            f"UPDATE {index_path.relative_to(vault_root)}\n\n{frontmatter.dumps(post)}"
        )
        plans.append(
            WritePlan(
                operation="append_note",
                path=str(index_path.relative_to(vault_root)),
                preview=preview,
                payload={
                    "abs_path": str(index_path),
                    "content": frontmatter.dumps(post),
                },
            )
        )
    return plans


def apply_plan(plan: WritePlan) -> str:
    settings = get_settings()
    if plan.operation == "move_note":
        import shutil
        src = Path(plan.payload["src"])
        dst = Path(plan.payload["dst"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        # Audit log for move
        vault_dir = Path(settings.vault_path).expanduser().resolve(strict=False)
        try:
            audit_log_path = Path(settings.audit_log_path)
            if not audit_log_path.is_absolute():
                audit_log_path = (vault_dir / audit_log_path).resolve(strict=False)
            else:
                audit_log_path = audit_log_path.expanduser().resolve(strict=False)
            with open('/tmp/mnemosyne_audit_debug.log', 'a') as dbg:
                dbg.write(f"vault_dir={vault_dir}\naudit_log_path={audit_log_path}\n")
            audit_log_path.relative_to(vault_dir)
        except Exception:
            raise ValueError("audit_log_path must be inside the vault directory")
        try:
            audit_log_path.relative_to(vault_dir)
        except ValueError:
            raise ValueError("audit_log_path must be inside the vault directory")
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_log_path, "a") as f:
            f.write(f"{datetime.utcnow().isoformat()}|move_note|{src}→{dst}\n")
        return f"✓ Moved: {src} → {dst}"
    abs_path = Path(plan.payload["abs_path"])
    content = plan.payload["content"]
    if plan.operation == "create_note":
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
    else:
        abs_path.write_text(content, encoding="utf-8")
    # Audit log
    # Restrict audit log path to vault directory for safety
    vault_dir = Path(settings.vault_path).expanduser().resolve(strict=False)
    try:
        audit_log_path = Path(settings.audit_log_path)
        if not audit_log_path.is_absolute():
            audit_log_path = (vault_dir / audit_log_path).resolve(strict=False)
        else:
            audit_log_path = audit_log_path.expanduser().resolve(strict=False)
        with open('/tmp/mnemosyne_audit_debug.log', 'a') as dbg:
            dbg.write(f"vault_dir={vault_dir}\naudit_log_path={audit_log_path}\n")
        audit_log_path.relative_to(vault_dir)
    except Exception:
        raise ValueError("audit_log_path must be inside the vault directory")
    try:
        audit_log_path.relative_to(vault_dir)
    except ValueError:
        raise ValueError("audit_log_path must be inside the vault directory")
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_log_path, "a") as f:
        f.write(f"{datetime.utcnow().isoformat()}|{plan.operation}|{plan.path}\n")
    return f"✓ Applied: {plan.operation} → {plan.path}"
