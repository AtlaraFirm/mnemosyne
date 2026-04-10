from mnemosyne.services import index

def test_init_db():
    result = index.init_db()
    assert result is None or result is not False

def test_upsert_chunks(tmp_path, monkeypatch):
    # Create a note, chunk it, and upsert the chunk
    from mnemosyne.services import vault
    note_title = "Chunked Note"
    note_body = "Chunk test body."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "chunked.md"
    note_path.write_text(f"# {note_title}\n{note_body}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    notes = vault.crawl_vault()
    chunks = []
    for note in notes:
        chunks.extend(vault.chunk_note(note))
    index.init_db()
    index.upsert_chunks(chunks)
    # Check that upserted chunk is in the DB via search_fts
    results = index.search_fts("chunk test")
    assert any(note_title in r.note_title for r in results)

def test_search_fts(tmp_path, monkeypatch):
    # Create a note, chunk it, upsert, and search
    from mnemosyne.services import vault
    note_title = "FTS Note"
    note_body = "Full text search body."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "fts.md"
    note_path.write_text(f"# {note_title}\n{note_body}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    notes = vault.crawl_vault()
    chunks = []
    for note in notes:
        chunks.extend(vault.chunk_note(note))
    index.init_db()
    index.upsert_chunks(chunks)
    results = index.search_fts("full text search")
    assert any(note_title in r.note_title for r in results)
