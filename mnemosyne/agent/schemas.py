from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid

class Note(BaseModel):
    path: str
    title: str
    body: str
    frontmatter: dict
    tags: list[str]
    wikilinks: list[str]
    headings: list[str]
    modified_at: datetime

class Chunk(BaseModel):
    id: str
    note_path: str
    note_title: str
    heading: str
    text: str
    tags: list[str]
    char_offset: int

class SearchResult(BaseModel):
    chunk_id: str
    note_path: str
    note_title: str
    heading: str
    excerpt: str
    score: float
    source: Literal["fts", "semantic", "hybrid"]

class WritePlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    operation: Literal["create_note", "append_note", "prepend_note", "update_frontmatter", "move_note"]
    path: str
    preview: str
    payload: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AgentResponse(BaseModel):
    text: str
    messages: list[dict]
    write_plans: list[WritePlan]
    tool_calls_made: list[str]

class ConversationMessage(BaseModel):
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    tool_name: Optional[str] = None
    source: Literal["cli", "tui", "telegram"] = "cli"
    chat_id: str = "local"
    ts: datetime = Field(default_factory=datetime.utcnow)
