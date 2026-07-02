from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment and optional YAML."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SCIREVIEW_",
        extra="ignore",
    )

    pdf_input_dir: Path = Path("data/pdfs")
    parsed_document_dir: Path = Path("data/parsed")
    export_dir: Path = Path("data/exports")
    sqlite_database_path: Path = Path("data/database/scireview.sqlite3")
    qdrant_storage_dir: Path = Path("data/database/qdrant")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    request_timeout_seconds: int = Field(default=120, ge=1)
    logging_level: str = "INFO"
    chunk_target_chars: int = Field(default=3000, ge=500)
    chunk_overlap_chars: int = Field(default=250, ge=0)
    vector_indexing_enabled: bool = False

    @classmethod
    def from_yaml(cls, path: Path | None) -> Settings:
        if path is None or not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as handle:
            raw: dict[str, Any] = yaml.safe_load(handle) or {}
        return cls(**raw)

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_database_path}"


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
