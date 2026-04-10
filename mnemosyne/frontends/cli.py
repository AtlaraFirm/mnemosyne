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
        console.print(plan.preview)
        if yes or typer.confirm(f"Apply {plan.operation} to {plan.path}?"):
            console.print(apply_plan(plan))


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
