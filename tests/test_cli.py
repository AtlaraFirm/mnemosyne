import subprocess
import sys
import pytest

CLI = [sys.executable, '-m', 'mnemosyne.frontends.cli']

@pytest.fixture(scope='module')
def vault(tmp_path_factory):
    vault = tmp_path_factory.mktemp('vault')
    (vault / 'note1.md').write_text('# Note 1\nHello world.')
    (vault / 'note2.md').write_text('# Note 2\nAnother note.')
    return vault

def test_search(vault):
    # Index notes before searching
    subprocess.run(CLI + ['reindex', '--vault', str(vault)], check=True)
    result = subprocess.run(CLI + ['search', 'Hello', '--vault', str(vault)], capture_output=True, text=True)
    # Check for table header and note title in output
    assert 'Score' in result.stdout
    assert 'Note' in result.stdout
    assert 'Note 1' in result.stdout

def test_new_note(vault):
    result = subprocess.run(CLI + ['new', 'Test Note', '--vault', str(vault), '--yes', '--content', 'This is a test.'], capture_output=True, text=True)
    assert 'Test Note' in result.stdout
