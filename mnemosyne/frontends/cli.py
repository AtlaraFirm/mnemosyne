import os

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

# Delay .env/config loading until after argument parsing
# (see main guard below)

app = typer.Typer(name="mnemosyne", help="Obsidian vault assistant powered by Ollama.")
console = Console()


@app.command()
def history(
    chat_id: str = typer.Option("local", help="Chat/session ID to show history for"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of turns to show"),
    clear: bool = typer.Option(False, "--clear", help="Clear history for this chat ID"),
):
    """Show or clear conversation history for a chat/session."""
    from mnemosyne.db.connection import clear_history, get_history

    if clear:
        clear_history(chat_id)
        console.print(f"[green]✓ Cleared history for chat_id={chat_id}[/green]")
        raise typer.Exit()
    history = get_history(chat_id)[-limit * 2 :]
    if not history:
        console.print("[yellow]No history found.[/yellow]")
        raise typer.Exit()
    for msg in history:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        console.print(f"[bold]{role.title()}:[/bold] {content}")


@app.command()
def sort_inbox(
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
    threshold: float = typer.Option(0.7, "--threshold", help="Confidence threshold (0-1)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show actions without moving files"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Move files without confirmation"),
):
    """Sort files from the inbox folder into their most likely destination based on confidence score."""
    import os
    from pathlib import Path
    from rich.table import Table
    from mnemosyne.services.vault import crawl_vault
    from mnemosyne.services.embed import _embed
    from shutil import move

    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    settings = __import__("mnemosyne.config").config.get_settings()
    vault = Path(settings.vault_path)
    inbox = vault / "inbox"
    if not inbox.exists() or not inbox.is_dir():
        console.print(f"[red]Inbox folder not found: {inbox}[/red]")
        raise typer.Exit(1)

    files = list(inbox.glob("*"))
    if not files:
        console.print("[yellow]No files in inbox.[/yellow]")
        raise typer.Exit()

    notes = crawl_vault()
    note_vectors = {note.path: _embed(note.title + " " + note.body[:500]) for note in notes}
    folders = set(Path(note.path).parent for note in notes if Path(note.path).parent != inbox)

    for file in files:
        if not file.is_file():
            continue
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(1000)
        file_vec = _embed(file.stem + " " + content)
        best_folder = None
        best_score = -1
        for folder in folders:
            folder_vecs = [note_vectors[note.path] for note in notes if Path(note.path).parent == folder]
            if not folder_vecs:
                continue
            # Average similarity to all notes in folder
            import numpy as np
            sims = [np.dot(file_vec, vec) / (np.linalg.norm(file_vec) * np.linalg.norm(vec)) for vec in folder_vecs]
            score = float(np.mean(sims))
            if score > best_score:
                best_score = score
                best_folder = folder
        table = Table(title=f"{file.name}")
        table.add_column("Destination")
        table.add_column("Score")
        if best_folder and best_score >= threshold:
            try:
                rel_folder = str(best_folder.relative_to(vault))
            except ValueError:
                rel_folder = str(best_folder)
            table.add_row(rel_folder, f"{best_score:.2f}")
            console.print(table)
            if not dry_run:
                if yes or typer.confirm(f"Move {file.name} to {rel_folder}?"):
                    dest = best_folder / file.name
                    move(str(file), str(dest))
                    console.print(f"[green]Moved {file.name} to {rel_folder}[/green]")
        else:
            table.add_row("[yellow]No confident match[/yellow]", f"{best_score:.2f}")
            console.print(table)

@app.command()
def flatten(
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Flatten the vault: move all notes to root, delete all index.md files, and remove empty folders."""
    import os
    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from mnemosyne.services.writes import flatten_vault
    actions = flatten_vault()
    if not actions:
        console.print("[yellow]No changes made. Vault is already flat.[/yellow]")
        return
    for act in actions:
        console.print(act)
    if yes or typer.confirm("Apply these changes?"):
        console.print("[green]✓ Vault flattened.[/green]")
    else:
        console.print("[yellow]No changes applied.[/yellow]")

@app.command()
def reindex(
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
):
    """Crawl vault, rebuild FTS5 index and embeddings."""
    import os

    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from mnemosyne.db.connection import init_db
    from mnemosyne.services import index as idx
    from mnemosyne.services import vault as v

    init_db()
    notes = v.crawl_vault()
    console.print(f"[bold]Found {len(notes)} notes[/bold]")
    all_chunks = []
    for note in notes:
        all_chunks.extend(v.chunk_note(note))
    console.print(f"Indexing {len(all_chunks)} chunks...")
    idx.upsert_chunks(all_chunks)
    console.print("[green]✓ Reindex complete[/green]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (keyword or semantic)"),
    limit: int = typer.Option(5, "--limit", "-n"),
    semantic: bool = typer.Option(
        False, "--semantic", "-s", help="Use semantic search instead of keyword search."
    ),
    hybrid: bool = typer.Option(
        False,
        "--hybrid",
        help="Combine FTS and semantic results, deduplicated and re-ranked.",
    ),
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
):
    """Search vault notes by keyword (default), semantic embedding, or hybrid ranked mode."""
    import os

    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from mnemosyne.services import embed as emb
    from mnemosyne.services import index as idx

    results = []
    if hybrid:
        fts_results = idx.search_fts(query, limit)
        sem_results = emb.semantic_search(query, limit)
        seen_paths = set()
        for r in fts_results + sem_results:
            if (r.note_path, r.heading) not in seen_paths:
                seen_paths.add((r.note_path, r.heading))
                results.append(r)
        results = sorted(results, key=lambda r: r.score, reverse=True)[:limit]
    elif semantic:
        results = emb.semantic_search(query, limit)
    else:
        results = idx.search_fts(query, limit)
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
    question: str = typer.Argument(
        ..., help="Ask a question. LLM with note context will answer."
    ),
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
):
    """Ask a natural language question. Context will be gathered from vault and answered by LLM."""
    import os

    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from mnemosyne.agent import loop

    response = loop.run(question, history=[])
    if response and getattr(response, "text", None):
        console.print(response.text.strip())
    else:
        console.print(
            "[yellow]Could not answer the question. Try rephrasing or check vault indexing.[/yellow]"
        )


@app.command()
def related(
    path: str = typer.Argument(
        ..., help="Relative path of note (from vault root) to find related notes for."
    ),
    limit: int = typer.Option(5, "--limit", "-n"),
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
):
    """Find semantically related notes not yet wikilinked from the source note."""
    import os

    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from mnemosyne.services import related as rel

    try:
        results = rel.find_related(path, limit)
    except FileNotFoundError as e:
        console.print(f"[red]{str(e)}[/red]")
        raise typer.Exit(code=1)
    if not results:
        console.print("[yellow]No related notes found.[/yellow]")
        raise typer.Exit()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Score", width=6)
    table.add_column("Note Title", min_width=20)
    table.add_column("Heading", min_width=15)
    table.add_column("Path", min_width=20)
    for r in results:
        table.add_row(str(r["score"]), r["title"], r["heading"], r["path"])
    console.print(table)


@app.command()
def new(
    title: str = typer.Argument(..., help="Note title"),
    folder: str = typer.Option("", "--folder", "-f"),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags"),
    content: str = typer.Option(
        None, "--content", help="Note body (for scripting/tests)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
):
    """Create a new note. Opens $EDITOR if no --body provided."""
    import os

    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from mnemosyne.services.writes import apply_plan, create_note

    body = content if content is not None else typer.edit("") or ""
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
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
):
    """Append text to an existing note."""
    if vault_path:
        import os

        os.environ["VAULT_PATH"] = vault_path
    from mnemosyne.services.writes import append_note, apply_plan

    plan = append_note(path, text)
    console.print(Syntax(plan.preview, "diff", theme="ansi_dark"))
    if yes or typer.confirm("Apply?"):
        console.print(apply_plan(plan))


@app.command()
def chat():
    """Launch the TUI chat interface."""
    from mnemosyne.frontends.tui import run_tui

    run_tui()


@app.command()
def bot():
    """Launch the Telegram bot interface."""
    from mnemosyne.frontends.telegram_bot import run_bot

    run_bot()


@app.command()
def suggest_links(
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max link suggestions per note"),
    threshold: float = typer.Option(
        0.7, "--threshold", help="Semantic similarity threshold (0-1)"
    ),
    mode: str = typer.Option(
        "suggest", "--mode", "-m", help="Mode: 'suggest' to only suggest, 'apply' to auto-apply"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Apply suggestions without confirmation (only relevant if --mode apply)"
    ),
):
    """Suggest new wikilinks for notes using semantic similarity. Optionally auto-apply with --mode apply and --yes for no confirmation."""
    import os

    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from rich.table import Table
    from mnemosyne.services.embed import _embed
    from mnemosyne.services.vault import crawl_vault
    from mnemosyne.services.writes import apply_plan, append_note

    notes = crawl_vault()
    note_vectors = {
        note.path: _embed(note.title + " " + note.body[:500]) for note in notes
    }
    for note in notes:
        table = Table(
            title=f"Suggestions for {note.title} ({note.path})",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Score", width=6)
        table.add_column("Note Title", min_width=20)
        table.add_column("Path", min_width=20)
        table.add_column("Type", min_width=8)
        # Find related notes by cosine similarity
        import numpy as np
        from numpy import dot
        from numpy.linalg import norm

        v1 = np.array(note_vectors[note.path])
        related = []
        for other in notes:
            if other.path == note.path:
                continue
            v2 = np.array(note_vectors[other.path])
            sim = dot(v1, v2) / (norm(v1) * norm(v2) + 1e-8)
            # Suggest wikilink if not already present
            if other.title not in note.wikilinks and sim >= threshold:
                related.append((sim, other.title, other.path, "wikilink"))
        # Sort and limit
        related = sorted(related, key=lambda x: -x[0])[:limit]
        for sim, value, path, typ in related:
            table.add_row(f"{sim:.2f}", value, path, typ)
        if related:
            console.print(table)
            if mode == "apply":
                related_links = [
                    {"title": title, "path": path}
                    for _, title, path, typ in related if typ == "wikilink"
                ]
                # Always use the note path for related links
                for link in related_links:
                    if 'path' in link:
                        link['path'] = link['path']  # Ensure path is used, not title
                # In apply mode, only update the Related section at the end, do not insert links into the body
                if mode == "apply":
                    plan = append_note(note.path, "", related_links=related_links or [])
                    from rich.syntax import Syntax
                    console.print(Syntax(plan.preview, "diff", theme="ansi_dark"))
                    if yes or typer.confirm(f"Apply related links to {note.path}? [{', '.join([l['title'] for l in related_links])}]"):
                        console.print(apply_plan(plan))
                elif related_links:
                    if yes or typer.confirm(f"Apply related links to {note.path}? [{', '.join([l['title'] for l in related_links])}]"):
                        # Always use the note path for related links
for link in related_links:
    if 'path' in link:
        link['path'] = link['path']  # Ensure path is used, not title
plan = append_note(note.path, "", related_links=related_links)
                        from rich.syntax import Syntax
                        console.print(Syntax(plan.preview, "diff", theme="ansi_dark"))
                        if yes or typer.confirm("Apply?"):
                            console.print(apply_plan(plan))
        else:
            console.print(
                f"[yellow]No link suggestions for {note.title} ({note.path})[/yellow]"
            )

@app.command()
def suggest_links_tags(
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max suggestions per note"),
    threshold: float = typer.Option(
        0.7, "--threshold", help="Semantic similarity threshold (0-1)"
    ),
    mode: str = typer.Option(
        "suggest", "--mode", "-m", help="Mode: 'suggest' to only suggest, 'apply' to auto-apply"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Apply suggestions without confirmation (only relevant if --mode apply)"
    ),
):
    """Suggest new wikilinks and tags for notes using semantic similarity (no direct modification)."""
    import os

    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from rich.table import Table

    from mnemosyne.services.embed import _embed
    from mnemosyne.services.vault import crawl_vault

    notes = crawl_vault()
    note_vectors = {
        note.path: _embed(note.title + " " + note.body[:500]) for note in notes
    }
    suggestions = []
    for note in notes:
        table = Table(
            title=f"Suggestions for {note.title} ({note.path})",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Score", width=6)
        table.add_column("Note Title", min_width=20)
        table.add_column("Path", min_width=20)
        table.add_column("Type", min_width=8)
        # Find related notes by cosine similarity
        import numpy as np
        from numpy import dot
        from numpy.linalg import norm

        v1 = np.array(note_vectors[note.path])
        related = []
        TRIVIAL_TAGS = {"index", "note", "notes", "untitled", "test", "todo", "draft"}
        STOPWORDS = {
            "the", "and", "for", "are", "but", "not", "you", "with", "that", "this", "was", "have", "from", "they", "his", "her", "she", "him", "all", "can", "had", "one", "has", "were", "their", "what", "when", "your", "out", "use", "how", "which", "will", "each", "about", "many", "then", "them", "these", "some", "would", "make", "like", "himself", "herself", "into", "more", "other", "could", "our", "there", "been", "if", "no", "than", "so", "may", "on", "in", "to", "of", "a", "an", "is", "it", "as", "at", "by", "be", "or", "we", "do", "did", "does", "up", "down", "over", "under", "again", "very", "just", "any", "now", "who", "where", "why", "because", "while", "between", "both", "few", "most", "such", "own", "same", "too", "s", "t", "can", "will", "don", "should", "ll", "d", "re", "ve", "m"
        }
        for other in notes:
            if other.path == note.path:
                continue
            v2 = np.array(note_vectors[other.path])
            sim = dot(v1, v2) / (norm(v1) * norm(v2) + 1e-8)
            # Suggest wikilink if not already present
            if other.title not in note.wikilinks:
                related.append((sim, other.title, other.path, "wikilink"))
            # Suggest tag if not already present
            for tag in other.tags:
                if tag and tag not in note.tags and tag.lower() not in TRIVIAL_TAGS and tag.lower() not in STOPWORDS:
                    related.append((sim, tag, other.path, "tag"))
        # Sort and limit
        related = sorted(related, key=lambda x: -x[0])[:limit]
        for sim, value, path, typ in related:
            table.add_row(f"{sim:.2f}", value, path, typ)
        related_titles = [title for _, title, _, typ in related if typ == "wikilink"]
        if related:
            console.print(table)
        else:
            console.print(
                f"[yellow]No suggestions for {note.title} ({note.path})[/yellow]"
            )
        # In apply mode, only update the Related section at the end, do not insert links into the body
        if mode == "apply":
            from mnemosyne.services.writes import append_note, apply_plan
            related_links = [
                {"title": title, "path": path}
                for _, title, path, typ in related if typ == "wikilink"
            ]
            # Always use the note path for related links
            for link in related_links:
                if 'path' in link:
                    link['path'] = link['path']  # Ensure path is used, not title
            plan = append_note(note.path, "", related_links=related_links or [])
            from rich.syntax import Syntax
            console.print(Syntax(plan.preview, "diff", theme="ansi_dark"))
            if yes or typer.confirm(f"Apply related links to {note.path}? [{', '.join(related_titles)}]"):
                console.print(apply_plan(plan))

@app.command()
def suggest_tags(
    mode: str = typer.Option(
        "suggest", "--mode", "-m", help="Mode: 'suggest' to only suggest tags, 'apply' to auto-apply them"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Apply tag suggestions without confirmation (only relevant if --mode apply)"
    ),
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max tag suggestions per note"),
    threshold: float = typer.Option(
        0.7, "--threshold", help="Semantic similarity threshold (0-1)"
    ),
):
    """Suggest tags for notes using semantic similarity. Optionally auto-apply with --mode apply and --yes for no confirmation (like organize).
    Example: mnemosyne suggest-tags --mode apply --yes
    """
    import os
    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from rich.table import Table
    from mnemosyne.services.embed import _embed
    from mnemosyne.services.vault import crawl_vault
    from mnemosyne.services.writes import apply_plan, update_frontmatter
    notes = crawl_vault()
    note_vectors = {
        note.path: _embed(note.title + " " + note.body[:500]) for note in notes
    }
    for note in notes:
        import numpy as np
        from numpy import dot
        from numpy.linalg import norm
        v1 = np.array(note_vectors[note.path])
        import re
        from collections import Counter
        suggested_tags = set([t.strip().lower().replace(" ", "-").replace("_", "-") for t in note.tags])
        tag_sources = {}
        # 1. Semantic similarity to other notes' tags
        TRIVIAL_TAGS = {"index", "note", "notes", "untitled", "test", "todo", "draft"}
        STOPWORDS = set([
            "the", "and", "for", "are", "but", "not", "you", "with", "that", "this", "was", "have", "from", "they", "his", "her", "she", "him", "all", "can", "had", "one", "has", "were", "their", "what", "when", "your", "out", "use", "how", "which", "will", "each", "about", "many", "then", "them", "these", "some", "would", "make", "like", "himself", "herself", "into", "more", "other", "could", "our", "there", "been", "if", "no", "than", "so", "may", "on", "in", "to", "of", "a", "an", "is", "it", "as", "at", "by", "be", "or", "we", "do", "did", "does", "up", "down", "over", "under", "again", "very", "just", "any", "now", "who", "where", "why", "because", "while", "between", "both", "few", "most", "such", "own", "same", "too", "s", "t", "can", "will", "don", "should", "ll", "d", "re", "ve", "m"
        ])
        for other in notes:
            if other.path == note.path:
                continue
            v2 = np.array(note_vectors[other.path])
            sim = dot(v1, v2) / (norm(v1) * norm(v2) + 1e-8)

            if sim >= threshold:
                for tag in other.tags:
                    tag_norm = tag.strip().lower().replace(" ", "-").replace("_", "-")
                    if tag and tag_norm not in suggested_tags and tag_norm not in TRIVIAL_TAGS and tag_norm not in STOPWORDS:
                        suggested_tags.add(tag_norm)
                        tag_sources[tag_norm] = (sim, other.path)
        # 2. Keyword extraction from note content
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", (note.title + " " + note.body).lower())
        keywords = [w for w in words if w not in STOPWORDS and w not in TRIVIAL_TAGS]
        freq = Counter(keywords)
        for w, _ in freq.most_common(limit):
            if w not in suggested_tags:
                suggested_tags.add(w)
                tag_sources[w] = (None, "keyword")
        new_tags = [t for t in suggested_tags if t not in [x.strip().lower().replace(" ", "-").replace("_", "-") for x in note.tags]]
        if new_tags:
            table = Table(
                title=f"Tag suggestions for {note.title} ({note.path})",
                show_header=True,
                header_style="bold",
            )
            table.add_column("Tag", min_width=12)
            table.add_column("Score", width=6)
            table.add_column("Source", min_width=20)
            for tag in new_tags:
                sim, src = tag_sources.get(tag, ("", ""))
                table.add_row(tag, f"{sim:.2f}" if sim is not None and sim != "" else "", src)
            console.print(table)
            if mode == "apply":
                if yes or typer.confirm(f"Apply tags to {note.path}? [{', '.join(new_tags)}]"):
                    plan = update_frontmatter(note.path, {"tags": sorted(set(note.tags + new_tags))})
                    from rich.syntax import Syntax
                    console.print(Syntax(plan.preview, "diff", theme="ansi_dark"))
                    if yes or typer.confirm("Apply?"):
                        console.print(apply_plan(plan))
        else:
            console.print(f"[yellow]No new tag suggestions for {note.title} ({note.path})[/yellow]")


@app.command()
def organize(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Apply changes without confirmation"
    ),
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
):
    """Organize, tag, link, and clean up notes automatically."""
    import os

    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    from mnemosyne.services.writes import apply_plan, organize_notes

    plans = organize_notes()
    if not plans:
        console.print("[green]No changes needed. Vault is already organized.")
        raise typer.Exit()
    for plan in plans:
        console.print(plan.preview, markup=False)
        if yes or typer.confirm(f"Apply {plan.operation} to {plan.path}?"):
            console.print(apply_plan(plan))


@app.command()
def backup(
    dest: str = typer.Option(None, help="Backup destination directory (default: ./backups)"),
    vault: str = typer.Option(None, help="Vault path (overrides config)"),
):
    """Backup the entire vault to a timestamped archive."""
    import shutil, datetime
    vault_path = vault or os.environ.get("VAULT_PATH") or os.getcwd()
    vault_path = os.path.abspath(vault_path)
    backup_dir = dest or os.path.join(os.getcwd(), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_name = f"vault-backup-{ts}.zip"
    archive_path = os.path.join(backup_dir, archive_name)
    shutil.make_archive(archive_path[:-4], 'zip', vault_path)
    console.print(f"[green]✓ Vault backed up to {archive_path}[/green]")

@app.command()
def restore(
    archive: str = typer.Argument(..., help="Path to backup archive (.zip)"),
    vault: str = typer.Option(None, help="Vault path (overrides config)"),
    yes: bool = typer.Option(False, '--yes', '-y', help="Overwrite vault without confirmation"),
):
    """Restore the vault from a backup archive."""
    import shutil, zipfile
    vault_path = vault or os.environ.get("VAULT_PATH") or os.getcwd()
    vault_path = os.path.abspath(vault_path)
    if not yes and not typer.confirm(f"This will overwrite the vault at {vault_path}. Continue?"):
        raise typer.Exit()
    with zipfile.ZipFile(archive, 'r') as zip_ref:
        zip_ref.extractall(vault_path)
    console.print(f"[green]✓ Vault restored from {archive} to {vault_path}[/green]")

@app.command()
def rollback(
    backup_dir: str = typer.Option(None, help="Backup directory (default: ./backups)"),
    vault: str = typer.Option(None, help="Vault path (overrides config)"),
    yes: bool = typer.Option(False, '--yes', '-y', help="Overwrite vault without confirmation"),
):
    """Rollback the vault to the most recent backup archive."""
    import glob, os
    backup_dir = backup_dir or os.path.join(os.getcwd(), "backups")
    archives = sorted(glob.glob(os.path.join(backup_dir, "vault-backup-*.zip")), reverse=True)
    if not archives:
        console.print(f"[red]No backups found in {backup_dir}[/red]"); raise typer.Exit()
    archive = archives[0]
    vault_path = vault or os.environ.get("VAULT_PATH") or os.getcwd()
    vault_path = os.path.abspath(vault_path)
    if not yes and not typer.confirm(f"This will overwrite the vault at {vault_path} with {archive}. Continue?"):
        raise typer.Exit()
    import zipfile
    with zipfile.ZipFile(archive, 'r') as zip_ref:
        zip_ref.extractall(vault_path)
    console.print(f"[green]✓ Vault rolled back to {archive}[/green]")

if __name__ == "__main__":

    import argparse

    from dotenv import load_dotenv

    # Minimal arg parse to extract --vault before loading .env/config
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--vault", "-v", dest="vault_path", default=None)
    args, unknown = parser.parse_known_args()
    if args.vault_path:
        os.environ["VAULT_PATH"] = args.vault_path
    # Now load .env/config with correct VAULT_PATH
    # If running in test, skip loading user .env
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        load_dotenv(dotenv_path=os.environ.get("DOTENV_PATH", ".env"), override=True)
    else:
        # In test, do not print anything to stdout (avoid breaking CLI output tests)
        pass
    # Re-invoke Typer CLI with original args
    app()
