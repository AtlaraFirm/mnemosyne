import subprocess
import sys
from pathlib import Path
import tempfile

CLI = [sys.executable, '-m', 'mnemosyne.frontends.cli']

def run_cli(args, cwd=None, input=None, env=None):
    import os
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    return subprocess.run(CLI + args, capture_output=True, text=True, cwd=cwd, input=input, env=env_vars)

def test_empty_note_title():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()
        result = run_cli(['new', '', '--vault', str(vault), '--yes', '--content', 'body'])
        assert result.returncode != 0
        assert 'title' in result.stderr.lower() or 'error' in result.stderr.lower()

def test_invalid_path_traversal():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()
        # Try to create a note with path traversal
        result = run_cli(['new', '../evil', '--vault', str(vault), '--yes', '--content', 'hack'])
        assert result.returncode != 0 or '..' not in (vault / '../evil.md').as_posix()

def test_large_note():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()
        large_body = 'A' * 10**6
        env = {"VAULT_PATH": str(vault), "AUDIT_LOG_PATH": str(vault/"audit.log")}
        result = run_cli(['new', 'BigNote', '--vault', str(vault), '--yes', '--content', large_body], env=env)
        assert result.returncode == 0
        note_path = vault / 'BigNote.md'
        assert note_path.exists()
        assert note_path.stat().st_size > 10**5

def test_unicode_title_and_body():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()
        title = '测试🧪'
        body = '内容 with emoji 🚀'
        env = {"VAULT_PATH": str(vault), "AUDIT_LOG_PATH": str(vault/"audit.log")}
        result = run_cli(['new', title, '--vault', str(vault), '--yes', '--content', body], env=env)
        assert result.returncode == 0
        note_path = vault / f'{title}.md'
        assert note_path.exists()
        assert body in note_path.read_text()

def test_shell_injection():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()
        # Try to inject shell code in title
        title = 'note; rm -rf /'
        result = run_cli(['new', title, '--vault', str(vault), '--yes', '--content', 'safe'])
        assert result.returncode != 0
        # The file should not be created
        note_path = vault / f'{title}.md'
        assert not note_path.exists()
        # The file should not be created outside the vault
        assert not Path('/note; rm -rf .md').exists()
