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
    # Ensure trivial tags are not suggested
    assert 'index' not in result.stdout
    # Only check for 'note' as a tag, not as a note title
    assert '| note |' not in result.stdout and '| note |' not in result.stderr
    assert 'the' not in result.stdout
    assert 'and' not in result.stdout

def test_suggest_tags_modes(vault):
    subprocess.run(CLI + ['reindex', '--vault', str(vault)], check=True)
    # Test suggest mode (default)
    result = subprocess.run(CLI + ['suggest-tags', '--vault', str(vault), '--limit', '2', '--threshold', '0.1'], capture_output=True, text=True)
    assert 'Tag suggestions for' in result.stdout
    # Should suggest tags from both similarity and keywords
    assert 'banana' in result.stdout or 'fruit' in result.stdout or 'apple' in result.stdout
    # Test apply mode (should prompt for confirmation, so use --yes)
    result = subprocess.run(CLI + ['suggest-tags', '--vault', str(vault), '--mode', 'apply', '--yes', '--limit', '2', '--threshold', '0.1'], capture_output=True, text=True)
    assert 'Tag suggestions for' in result.stdout
    # Should not error and should print applied changes or confirmation
