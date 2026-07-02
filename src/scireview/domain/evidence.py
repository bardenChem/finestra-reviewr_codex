from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class SupportType(StrEnum):
    """Whether evidence was directly stated or inferred from context."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"


class EvidenceSpan(BaseModel):
    """A quotation that supports an extracted method, result, or claim."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    paper_id: str
    chunk_id: str
    page: int = Field(ge=1)
    section: str | None = None
    quote: str = Field(min_length=1)
    support_type: SupportType = SupportType.EXPLICIT
