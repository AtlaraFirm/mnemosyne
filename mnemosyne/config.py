from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Vault
    vault_path: Path
    daily_note_folder: str = "daily"
    ignore_globs: list[str] = Field(
        default_factory=lambda: [".obsidian/**", "templates/**"]
    )

    # Ollama
    ollama_host: str = "http://localhost:11434"
    chat_model: str = "ministral-3:latest"
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
    audit_log_path: Path = Path("vault/audit.log")  # Must be inside vault_path
    max_chunk_chars: int = 1200

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    import os

    # Patch: if VAULT_PATH or AUDIT_LOG_PATH are set, override
    kwargs = {}
    if os.environ.get("VAULT_PATH"):
        kwargs["vault_path"] = os.environ["VAULT_PATH"]
    if os.environ.get("AUDIT_LOG_PATH"):
        kwargs["audit_log_path"] = os.environ["AUDIT_LOG_PATH"]
    if kwargs:
        # Patch: ensure audit_log_path is always a Path
        if "audit_log_path" in kwargs:
            kwargs["audit_log_path"] = str(kwargs["audit_log_path"])
        if "vault_path" in kwargs:
            kwargs["vault_path"] = str(kwargs["vault_path"])
        # Prevent loading user .env in tests/CLI subprocess
        class NoEnvConfig(Settings.Config):
            env_file = None
        return Settings(_env_file=None, **kwargs)
    return Settings()
