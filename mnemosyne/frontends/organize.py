import typer
from rich.console import Console
from mnemosyne.services import writes

app = typer.Typer()
console = Console()

@app.command()
def organize(
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply changes without confirmation"),
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
    by: str = typer.Option("tag", "--by", help="Organization rule: tag, date, or custom"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
):
    """Organize, tag, link, split, and clean up notes automatically. Supports rules-based organization."""
    import os
    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    rules = {"by": by}
    plans = writes.organize_notes(rules)
    if not plans:
        console.print("[green]No changes needed. Vault is already organized.")
        raise typer.Exit()
    for plan in plans:
        console.print(plan.preview, markup=False)
        if dry_run:
            continue
        if yes or typer.confirm(f"Apply {plan.operation} to {plan.path}?"):
            console.print(writes.apply_plan(plan))

if __name__ == "__main__":
    app()
