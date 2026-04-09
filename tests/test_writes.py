import pytest
from mnemosyne.services import writes

def test_create_note(tmp_path):
    plan = writes.create_note("TestTitle", "TestBody", folder="", tags=["tag1"])
    assert plan.operation == "create_note"
    assert plan.path.endswith("TestTitle.md")
    assert "TestBody" in plan.payload["content"]

def test_append_note(tmp_path):
    plan = writes.create_note("AppendTitle", "Body")
    path = tmp_path / "AppendTitle.md"
    path.write_text("Body")
    plan2 = writes.append_note(str(path), "Appended text")
    assert plan2.operation == "append_note"
    assert "Appended text" in plan2.payload["content"]

def test_update_frontmatter(tmp_path):
    plan = writes.create_note("FMTitle", "Body")
    path = tmp_path / "FMTitle.md"
    path.write_text("Body")
    plan2 = writes.update_frontmatter(str(path), {"newkey": "newval"})
    assert plan2.operation == "update_frontmatter"
    assert "newkey" in plan2.payload["content"]

def test_apply_plan(tmp_path):
    plan = writes.create_note("PlanTitle", "Body")
    path = tmp_path / "PlanTitle.md"
    plan2 = writes.append_note(str(path), "Appended text")
    # Actually apply the create plan first
    writes.apply_plan(plan)
    result = writes.apply_plan(plan2)
    assert isinstance(result, str)
