import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from pathlib import Path

app = typer.Typer(name="mnemosyne", help="Obsidian vault assistant powered by Ollama.")
console = Console()

@app.command()
def reindex(
    vault_path: str = typer.Option(None, '--vault', '-v', help='Path to vault root'),
):
    """Crawl vault, rebuild FTS5 index and embeddings."""
    import os
    if vault_path:
        os.environ['VAULT_PATH'] = vault_path
    from mnemosyne.services import vault as v, index as idx
    from mnemosyne.db.connection import init_db
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
    query: str = typer.Argument(..., help="Keyword search query"),
    limit: int = typer.Option(5, "--limit", "-n"),
    vault_path: str = typer.Option(None, '--vault', '-v', help='Path to vault root'),
):
    """Search vault notes by keyword."""
    import os
    if vault_path:
        os.environ['VAULT_PATH'] = vault_path
    from mnemosyne.services import index as idx
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
def new(
    title: str = typer.Argument(..., help="Note title"),
    folder: str = typer.Option("", "--folder", "-f"),
    tags: str = typer.Option("", "--tags", "-t", help="Comma-separated tags"),
    content: str = typer.Option(None, "--content", help="Note body (for scripting/tests)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    vault_path: str = typer.Option(None, '--vault', '-v', help='Path to vault root'),
):
    """Create a new note. Opens $EDITOR if no --body provided."""
    import os
    if vault_path:
        os.environ['VAULT_PATH'] = vault_path
    from mnemosyne.services.writes import create_note, apply_plan
    import subprocess
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
    vault_path: str = typer.Option(None, '--vault', '-v', help='Path to vault root'),
):
    """Append text to an existing note."""
    if vault_path:
        import os
        os.environ['VAULT_PATH'] = vault_path
    from mnemosyne.services.writes import append_note, apply_plan
    plan = append_note(path, text)
    console.print(Syntax(plan.preview, "diff", theme="ansi_dark"))
    if yes or typer.confirm("Apply?"):
        console.print(apply_plan(plan))

if __name__ == "__main__":
    app()
