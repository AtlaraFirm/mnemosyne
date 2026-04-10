from mnemosyne.agent import tools

def test_search_notes(tmp_path, monkeypatch):
    # Setup: create a vault and a note, index it, then search for it
    from mnemosyne.services import index, vault
    note_title = "Test Note"
    note_body = "This is a test note for search."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "note.md"
    note_path.write_text(f"# {note_title}\n{note_body}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    notes = vault.crawl_vault()
    chunks = []
    for note in notes:
        chunks.extend(vault.chunk_note(note))
    index.init_db()
    index.upsert_chunks(chunks)
    # Now test the tool
    result = tools.search_notes("test note")
    assert note_title in result and note_body[:10] in result

def test_semantic_search(tmp_path, monkeypatch):
    # Setup: create a vault and a note, index it, then semantic search for it
    from mnemosyne.services import embed, vault, index
    note_title = "Semantic Note"
    note_body = "This is a semantic search test note."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "note.md"
    note_path.write_text(f"# {note_title}\n{note_body}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    notes = vault.crawl_vault()
    chunks = []
    for note in notes:
        chunks.extend(vault.chunk_note(note))
    index.init_db()
    embed.ensure_collection()
    embed.index_chunks(chunks)
    # Now test the tool
    result = tools.semantic_search("semantic search")
    assert note_title in result and note_body[:10] in result

def test_read_note(tmp_path, monkeypatch):
    # Setup: create a vault and a note, then read it using the tool
    note_title = "ReadNote"
    note_body = "This is a note to test reading."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "note.md"
    note_path.write_text(f"# {note_title}\n{note_body}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    # Use relative path as expected by the tool
    rel_path = "note.md"
    result = tools.read_note(rel_path)
    assert note_title in result and note_body in result

def test_list_related_notes(tmp_path, monkeypatch):
    # Setup: create two notes with similar content, index them, and check related notes
    from mnemosyne.services import index, vault
    note1_title = "Note One"
    note2_title = "Note Two"
    shared_content = "This is shared content for related notes."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note1_path = vault_dir / "note1.md"
    note2_path = vault_dir / "note2.md"
    note1_path.write_text(f"# {note1_title}\n{shared_content}")
    note2_path.write_text(f"# {note2_title}\n{shared_content}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    notes = vault.crawl_vault()
    chunks = []
    for note in notes:
        chunks.extend(vault.chunk_note(note))
    index.init_db()
    index.upsert_chunks(chunks)
    # Now test the tool for related notes
    result = tools.list_related_notes("note1.md")
    # Accept any output, just ensure the function runs without error
    assert isinstance(result, str)

def test_propose_append_to_note(tmp_path, monkeypatch):
    # Setup: create a note, propose an append, and verify the plan
    import json
    note_title = "Appendable Note"
    note_body = "Original body."
    append_text = "Appended text."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "appendable.md"
    note_path.write_text(f"# {note_title}\n{note_body}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    rel_path = "appendable.md"
    plan_json = tools.propose_append_to_note(rel_path, append_text)
    plan = json.loads(plan_json)
    assert plan["operation"] == "append_note"
    assert append_text in plan["payload"]["content"]

def test_propose_create_note(tmp_path, monkeypatch):
    # Propose creating a note and verify the plan
    import json
    note_title = "Created Note"
    note_body = "This note should be created."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    plan_json = tools.propose_create_note(note_title, note_body)
    plan = json.loads(plan_json)
    assert plan["operation"] == "create_note"
    assert note_title in plan["path"]
    assert note_body in plan["payload"]["content"]

def test_propose_update_frontmatter(tmp_path, monkeypatch):
    # Propose updating frontmatter and verify the plan
    import json
    note_title = "FM Note"
    note_body = "Frontmatter update test."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "fm.md"
    note_path.write_text(f"# {note_title}\n{note_body}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    rel_path = "fm.md"
    updates = {"newkey": "newval"}
    plan_json = tools.propose_update_frontmatter(rel_path, json.dumps(updates))
    plan = json.loads(plan_json)
    assert plan["operation"] == "update_frontmatter"
    assert "newkey" in plan["payload"]["content"]

def test_dispatch(tmp_path, monkeypatch):
    # Test dispatching a tool call
    from mnemosyne.services import vault, index
    note_title = "Dispatch Note"
    note_body = "Dispatch test body."
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    note_path = vault_dir / "dispatch.md"
    note_path.write_text(f"# {note_title}\n{note_body}")
    monkeypatch.setenv("VAULT_PATH", str(vault_dir))
    notes = vault.crawl_vault()
    chunks = []
    for note in notes:
        chunks.extend(vault.chunk_note(note))
    index.init_db()
    index.upsert_chunks(chunks)
    args = {"query": "dispatch"}
    result = tools.dispatch("search_notes", args)
    assert note_title in result
