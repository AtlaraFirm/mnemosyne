import frontmatter
import difflib
from pathlib import Path
from datetime import datetime
from mnemosyne.config import get_settings
from mnemosyne.agent.schemas import WritePlan

def _vault() -> Path:
    return Path(get_settings().vault_path)

def create_note(title: str, body: str, folder: str = "", tags: list[str] = None) -> WritePlan:
    # Input validation
    if not title or not title.strip():
        raise ValueError("Note title cannot be empty.")
    if any(x in title for x in ["..", "/", "\\", ":", "|", "?", "*", "<", ">"]):
        raise ValueError("Invalid characters in note title.")
    if title.startswith('.'):
        raise ValueError("Note title cannot start with a dot.")
    folder = folder or ""
    safe_title = title.replace("/", "-").replace("\\", "-").replace("..", "-").replace(";", "-").replace(":", "-").replace("|", "-").replace("?", "-").replace("*", "-").replace("<", "-").replace(">", "-")
    rel_path = f"{folder}/{safe_title}.md".lstrip("/")
    abs_path = _vault() / rel_path
    fm = {"title": title, "created": datetime.utcnow().isoformat(), "tags": tags or []}
    post = frontmatter.Post(body, **fm)
    preview = f"CREATE {rel_path}\n\n{frontmatter.dumps(post)}"
    return WritePlan(
        operation="create_note",
        path=rel_path,
        preview=preview,
        payload={"abs_path": str(abs_path), "content": frontmatter.dumps(post)},
    )

def append_note(path: str, text: str, section: str = None) -> WritePlan:
    abs_path = _vault() / path
    original = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
    new_content = original.rstrip() + f"\n\n{text}\n"
    diff = "\n".join(difflib.unified_diff(
        original.splitlines(), new_content.splitlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
    ))
    return WritePlan(
        operation="append_note",
        path=path,
        preview=diff or f"APPEND to {path}:\n{text}",
        payload={"abs_path": str(abs_path), "content": new_content},
    )

def update_frontmatter(path: str, updates: dict) -> WritePlan:
    abs_path = _vault() / path
    post = frontmatter.load(str(abs_path))
    original = frontmatter.dumps(post)
    post.metadata.update(updates)
    new_content = frontmatter.dumps(post)
    diff = "\n".join(difflib.unified_diff(
        original.splitlines(), new_content.splitlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
    ))
    return WritePlan(
        operation="update_frontmatter",
        path=path,
        preview=diff,
        payload={"abs_path": str(abs_path), "content": new_content},
    )

def apply_plan(plan: WritePlan) -> str:
    settings = get_settings()
    abs_path = Path(plan.payload["abs_path"])
    content = plan.payload["content"]
    if plan.operation == "create_note":
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
    else:
        abs_path.write_text(content, encoding="utf-8")
    # Audit log
    with open(settings.audit_log_path, "a") as f:
        f.write(f"{datetime.utcnow().isoformat()}|{plan.operation}|{plan.path}\n")
    return f"✓ Applied: {plan.operation} → {plan.path}"
