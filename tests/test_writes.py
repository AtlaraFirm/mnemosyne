from mnemosyne.services import writes

def test_create_note(tmp_path):
    plan = writes.create_note("TestTitle", "TestBody", folder="", tags=["tag1"])
    assert plan.operation == "create_note"
    assert plan.path.endswith("TestTitle.md")
    assert "TestBody" in plan.payload["content"]

def test_append_note(tmp_path):
    writes.create_note("AppendTitle", "Body")
    path = tmp_path / "AppendTitle.md"
    path.write_text("Body")
    plan2 = writes.append_note(str(path), "Appended text")
    assert plan2.operation == "append_note"
    assert "Appended text" in plan2.payload["content"]

def test_update_frontmatter(tmp_path):
    writes.create_note("FMTitle", "Body")
    path = tmp_path / "FMTitle.md"
    path.write_text("Body")
    plan2 = writes.update_frontmatter(str(path), {"newkey": "newval"})
    assert plan2.operation == "update_frontmatter"
    assert "newkey" in plan2.payload["content"]

def test_wikilink_cleanup(tmp_path):
    import os
    os.environ["VAULT_PATH"] = str(tmp_path)
    # Test that empty or whitespace-only wikilinks are removed
    text_with_empty = "This is a test [[ ]] and [[   ]] and [[ValidLink]]."
    plan = writes.create_note("TestTitle", text_with_empty)
    cleaned = plan.payload["content"]
    assert "[[ ]]" not in cleaned
    assert "[[   ]]" not in cleaned
    assert "[[ValidLink]]" in cleaned

    # Test that auto-linking uses correct relative path for subfolder notes
    writes.create_note("NoteB", "Body", folder="folder1")
    # Force crawl_vault to see the new note by actually writing it to disk
    note_b_path = tmp_path / "folder1" / "NoteB.md"
    note_b_path.parent.mkdir(parents=True, exist_ok=True)
    note_b_path.write_text("---\ntitle: NoteB\n---\n\nBody")
    plan2 = writes.create_note("NoteA", "See NoteB", folder="folder1")
    content2 = plan2.payload["content"]
    assert "[[NoteB]]" in content2

    # Test that index note links use correct relative path
    # Simulate organize_notes output for a folder with a note and a subfolder
    # (This is a simplified check, as organize_notes walks the vault)
    from mnemosyne.services import writes as w
    import os
    os.makedirs(tmp_path / "folder2", exist_ok=True)
    (tmp_path / "folder2" / "NoteC.md").write_text("---\ntitle: NoteC\n---\n\nBody")
    (tmp_path / "folder2" / "index.md").write_text("")
    plans = w.organize_notes()
    found_index = False
    for plan in plans:
        if plan.path.endswith("index.md"):
            found_index = True
            content = plan.payload["content"]
            # Should link to subfolder notes or indexes
            assert any(link in content for link in ["[[folder2/NoteC]]", "[[folder2/index]]", "[[folder1/NoteB]]", "[[folder1/index]]"])
    assert found_index

def test_sweep_links(tmp_path):
    import os
    os.environ["VAULT_PATH"] = str(tmp_path)
    from mnemosyne.services import writes
    # Create notes
    note_a = tmp_path / "NoteA.md"
    note_a.write_text("---\ntitle: NoteA\n---\n\nSee [[NoteB]] and [[MissingNote]].")
    note_b = tmp_path / "NoteB.md"
    note_b.write_text("---\ntitle: NoteB\n---\n\nBody")
    # Sweep with fix
    actions = writes.sweep_links(fix=True)
    # MissingNote link should be removed
    content_a = note_a.read_text()
    assert "[[MissingNote]]" not in content_a
    assert any(a['wikilink'] == 'MissingNote' and a['action'] == 'removed' for a in actions)
    # Sweep with fix=False (should find no broken links now)
    actions2 = writes.sweep_links(fix=False)
    assert not any(a['action'] == 'broken' for a in actions2)

def test_apply_plan(tmp_path):
    import os
    os.environ["VAULT_PATH"] = str(tmp_path)
    os.environ["AUDIT_LOG_PATH"] = str(tmp_path/"audit.log")
    plan = writes.create_note("PlanTitle", "Body")
    path = tmp_path / "PlanTitle.md"
    plan2 = writes.append_note(str(path), "Appended text")
    # Actually apply the create plan first
    writes.apply_plan(plan)
    result = writes.apply_plan(plan2)
    assert isinstance(result, str)
