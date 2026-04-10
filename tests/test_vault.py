from mnemosyne.services import vault

def test_should_ignore(tmp_path, monkeypatch):
    vault_root = tmp_path
    (vault_root / ".git").mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault_root))
    ignored = vault._should_ignore(vault_root / ".git", vault_root)
    assert ignored

def test_crawl_vault(tmp_path, monkeypatch):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "note.md"
    note_path.write_text("# Title\nBody")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    notes = vault.crawl_vault()
    assert isinstance(notes, list) and len(notes) > 0

def test_read_note(tmp_path, monkeypatch):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "note.md"
    note_path.write_text("# Title\nBody")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    note = vault.read_note(note_path)
    assert note.title == "Title"
    assert note.path == "note.md"


def test_chunk_note(tmp_path, monkeypatch):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "note.md"
    note_path.write_text("# Title\nBody")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    note = vault.read_note(note_path)
    assert note.path == "note.md"
    chunks = vault.chunk_note(note)
    assert isinstance(chunks, list) and len(chunks) > 0
