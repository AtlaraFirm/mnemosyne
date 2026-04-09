from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
from typing import Literal
from functools import lru_cache

class Settings(BaseSettings):
    # Vault
    vault_path: Path
    daily_note_folder: str = "daily"
    ignore_globs: list[str] = Field(default_factory=lambda: [".obsidian/**", "templates/**"])

    # Ollama
    ollama_host: str = "http://localhost:11434"
    chat_model: str = "llama3.2"
    embed_model: str = "nomic-embed-text"
    agent_max_iterations: int = 8

    # Vector store
    vector_backend: Literal["qdrant", "sqlite-vec"] = "qdrant"
    qdrant_host: str = "http://localhost:6333"
    qdrant_collection: str = "vault_chunks"

    # SQLite
    db_path: Path = Path("./db/vault.db")
    history_max_turns: int = 20

    # Telegram
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: list[int] = Field(default_factory=list)

    # Behavior
    write_confirm_default: bool = True
    audit_log_path: Path = Path("./vault-cli-audit.log")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
