import subprocess
import sys
from pathlib import Path
import tempfile
import shutil
import time

CLI = [sys.executable, '-m', 'mnemosyne.frontends.cli']

def run_cli(args, cwd=None, input=None):
    return subprocess.run(CLI + args, capture_output=True, text=True, cwd=cwd, input=input)

def test_e2e_cli():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()
        db_dir = Path(tmpdir) / "db"
        db_dir.mkdir()
        # Set up .env for this test
        env_path = Path(tmpdir) / ".env"
        env_path.write_text(f"VAULT_PATH={vault}\nDB_PATH={db_dir}/vault.db\n")
        # 1. Create a note
        result = run_cli(['new', 'E2E Note', '--vault', str(vault), '--yes', '--content', 'E2E test body'])
        assert result.returncode == 0
        assert 'E2E Note' in result.stdout
        # 2. Reindex after write
        result = run_cli(['reindex', '--vault', str(vault)])
        assert result.returncode == 0
        # 3. Search for the note
        result = run_cli(['search', 'E2E', '--vault', str(vault)])
        assert result.returncode == 0
        assert 'E2E Note' in result.stdout
        # 4. Append to the note
        result = run_cli(['append', 'E2E Note.md', 'Appended text', '--vault', str(vault), '--yes'])
        assert result.returncode == 0
        # 4. Check appended content
        note_path = vault / 'E2E Note.md'
        content = note_path.read_text()
        assert 'E2E test body' in content
        assert 'Appended text' in content
        # 5. Reindex and search again
        result = run_cli(['reindex', '--vault', str(vault)])
        assert result.returncode == 0
        result = run_cli(['search', 'Appended', '--vault', str(vault)])
        assert 'E2E Note' in result.stdout
