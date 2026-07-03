from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_alias(field_name: str) -> AliasChoices:
    env_name = field_name.upper()
    return AliasChoices(f"FINESTRA_{env_name}", f"SCIREVIEW_{env_name}", field_name)


class Settings(BaseSettings):
    """Application settings loaded from environment and optional YAML."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    pdf_input_dir: Path = Field(
        default=Path("data/pdfs"), validation_alias=_env_alias("pdf_input_dir")
    )
    parsed_document_dir: Path = Field(
        default=Path("data/parsed"), validation_alias=_env_alias("parsed_document_dir")
    )
    export_dir: Path = Field(
        default=Path("data/exports"), validation_alias=_env_alias("export_dir")
    )
    sqlite_database_path: Path = Field(
        default=Path("data/database/finestra.sqlite3"),
        validation_alias=_env_alias("sqlite_database_path"),
    )
    qdrant_storage_dir: Path = Field(
        default=Path("data/database/qdrant"),
        validation_alias=_env_alias("qdrant_storage_dir"),
    )
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        validation_alias=_env_alias("embedding_model"),
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias=_env_alias("ollama_base_url"),
    )
    ollama_model: str = Field(
        default="llama3.1:8b",
        validation_alias=_env_alias("ollama_model"),
    )
    request_timeout_seconds: int = Field(
        default=120, ge=1, validation_alias=_env_alias("request_timeout_seconds")
    )
    logging_level: str = Field(default="INFO", validation_alias=_env_alias("logging_level"))
    chunk_target_chars: int = Field(
        default=3000, ge=500, validation_alias=_env_alias("chunk_target_chars")
    )
    chunk_overlap_chars: int = Field(
        default=250, ge=0, validation_alias=_env_alias("chunk_overlap_chars")
    )
    vector_indexing_enabled: bool = Field(
        default=False, validation_alias=_env_alias("vector_indexing_enabled")
    )

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
