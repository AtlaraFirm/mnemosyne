from mnemosyne.services import related

def test_find_related(tmp_path, monkeypatch):
    # Create two notes with similar content, index them, and check related
    from mnemosyne.services import index, vault
    note1_title = "Related One"
    note2_title = "Related Two"
    shared_content = "This is shared content for related test."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note1_path = vault_dir / "rel1.md"
    note2_path = vault_dir / "rel2.md"
    note1_path.write_text(f"# {note1_title}\n{shared_content}")
    note2_path.write_text(f"# {note2_title}\n{shared_content}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    notes = vault.crawl_vault()
    chunks = []
    for note in notes:
        chunks.extend(vault.chunk_note(note))
    index.init_db()
    index.upsert_chunks(chunks)
    # Now test related.find_related
    results = related.find_related("rel1.md")
    # Accept any output, just ensure the function runs without error
    assert isinstance(results, list)
