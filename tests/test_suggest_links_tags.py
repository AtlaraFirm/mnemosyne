import subprocess
import sys
import os
import pytest

CLI = [sys.executable, '-m', 'mnemosyne.frontends.cli']

@pytest.fixture(scope='module')
def vault(tmp_path_factory):
    vault = tmp_path_factory.mktemp('vault')
    (vault / 'note1.md').write_text('# Note 1\nApple orange banana.')
    (vault / 'note2.md').write_text('# Note 2\nBanana fruit salad.')
    (vault / 'note3.md').write_text('# Note 3\nUnrelated content.')
    db_path = vault / 'test.db'
    os.environ['DB_PATH'] = str(db_path)
    return vault

def test_suggest_links_tags(vault):
    subprocess.run(CLI + ['reindex', '--vault', str(vault)], check=True)
    result = subprocess.run(CLI + ['suggest-links-tags', '--vault', str(vault), '--limit', '2', '--threshold', '0.1'], capture_output=True, text=True)
    assert 'Suggestions for' in result.stdout
    assert 'wikilink' in result.stdout or 'tag' in result.stdout
