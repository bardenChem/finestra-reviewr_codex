from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChunkType(StrEnum):
    """Controlled document chunk categories."""

    TITLE = "title"
    ABSTRACT = "abstract"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    TABLE_CAPTION = "table_caption"
    FIGURE_CAPTION = "figure_caption"
    EQUATION = "equation"
    REFERENCES = "references"
    UNKNOWN = "unknown"


class BoundingBox(BaseModel):
    """Optional source coordinates for a chunk."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1)
    x0: float
    y0: float
    x1: float
    y1: float


class DocumentMetadata(BaseModel):
    """Metadata attached to a parsed scientific PDF."""

    model_config = ConfigDict(extra="forbid")

    paper_id: str
    filename: str
    absolute_path: Path
    sha256: str = Field(min_length=64, max_length=64)
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    doi: str | None = None
    parser_name: str
    parser_version: str
    schema_version: str = "1.0"

    @field_validator("absolute_path")
    @classmethod
    def make_absolute(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class DocumentChunk(BaseModel):
    """A provenance-preserving section of parsed PDF text."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(default_factory=lambda: str(uuid4()))
    paper_id: str
    section_title: str | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    text: str = Field(min_length=1)
    chunk_type: ChunkType = ChunkType.UNKNOWN
    bounding_boxes: list[BoundingBox] = Field(default_factory=list)

    @field_validator("page_end")
    @classmethod
    def page_end_positive(cls, value: int) -> int:
        if value < 1:
            msg = "page_end must be positive"
            raise ValueError(msg)
        return value


class ParsedDocument(BaseModel):
    """A parsed document plus non-fatal parser warnings."""

    model_config = ConfigDict(extra="forbid")

    metadata: DocumentMetadata
    chunks: list[DocumentChunk]
    warnings: list[str] = Field(default_factory=list)
