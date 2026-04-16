import pytest
import os
import sys
import subprocess

CLI = [sys.executable, '-m', 'mnemosyne.frontends.cli']

@pytest.fixture(scope='module')
def vault(tmp_path_factory):
    vault = tmp_path_factory.mktemp('vault')
    (vault / 'note1.md').write_text('# Note 1\nApple orange banana.')
    (vault / 'note2.md').write_text('# Note 2\nBanana fruit salad.')
    (vault / 'note3.md').write_text('# Note 3\nUnrelated content.')
    (vault / 'empty.md').write_text('# Empty\n   \n')
    db_path = vault / 'test.db'
    os.environ['DB_PATH'] = str(db_path)
    return vault

def test_suggest_links_only_links(vault):
    import subprocess
    import sys
    CLI = [sys.executable, '-m', 'mnemosyne.frontends.cli']
    subprocess.run(CLI + ['reindex', '--vault', str(vault)], check=True)
    result = subprocess.run(CLI + ['suggest-links', '--vault', str(vault), '--limit', '2', '--threshold', '0.1', '--mode', 'apply', '--yes'], capture_output=True, text=True)
    assert 'Suggestions for' in result.stdout
    assert 'wikilink' in result.stdout
    assert 'tag' not in result.stdout
    # Ensure trivial tags are not suggested
    assert 'index' not in result.stdout
    assert '| note |' not in result.stdout and '| note |' not in result.stderr
    assert 'the' not in result.stdout
    assert 'and' not in result.stdout

    # Check that the Related section is present in the modified note
    note1_path = vault / 'note1.md'
    content = note1_path.read_text()
    assert '## Related' in content
    assert '[[' in content.split('## Related')[-1]  # At least one wikilink in Related section

    # Ensure no suggestions for empty note
    result_empty = subprocess.run(CLI + ['suggest-links', '--vault', str(vault), '--limit', '2', '--threshold', '0.1'], capture_output=True, text=True)
    assert 'Suggestions for Empty' not in result_empty.stdout
