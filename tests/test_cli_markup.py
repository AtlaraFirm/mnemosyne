import subprocess
import sys
import os
import pytest

CLI = [sys.executable, '-m', 'mnemosyne.frontends.cli']

def test_organize_handles_markup(tmp_path):
    # Create a vault and a note with tricky markup
    vault = tmp_path / 'vault'
    vault.mkdir()
    note_path = vault / 'markup_note.md'
    # This content will trigger Rich markup parsing if not disabled
    note_path.write_text('# Markup Test\nThis is a [foo] and a [/foo] tag.')
    os.environ['DB_PATH'] = str(vault / 'test.db')
    os.environ['AUDIT_LOG_PATH'] = str(vault / 'audit.log')
    # Run organize and ensure no MarkupError occurs
    result = subprocess.run(CLI + ['organize', '--vault', str(vault), '--yes'], capture_output=True, text=True)
    assert result.returncode == 0
    assert 'markup' in result.stdout.lower() or 'index' in result.stdout.lower()
    assert 'markuperror' not in result.stderr.lower()
    assert 'traceback' not in result.stderr.lower()
