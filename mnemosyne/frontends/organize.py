import typer
from rich.console import Console
from mnemosyne.services import writes

app = typer.Typer()
console = Console()

@app.command()
def organize(
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply changes without confirmation"),
    vault_path: str = typer.Option(None, "--vault", "-v", help="Path to vault root"),
):
    """Organize, tag, link, and clean up notes automatically."""
    import os
    if vault_path:
        os.environ["VAULT_PATH"] = vault_path
    plans = writes.organize_notes()
    if not plans:
        console.print("[green]No changes needed. Vault is already organized.")
        raise typer.Exit()
    for plan in plans:
        console.print(plan.preview, markup=False)
        if yes or typer.confirm(f"Apply {plan.operation} to {plan.path}?"):
            console.print(writes.apply_plan(plan))

if __name__ == "__main__":
    app()
