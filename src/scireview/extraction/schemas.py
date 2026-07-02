from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from scireview.domain.studies import StudyRecord


class StudyExtractionResponse(StudyRecord):
    """LLM response schema for study extraction."""

    model_config = ConfigDict(extra="forbid")


class ChunkForExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    paper_id: str
    section: str | None
    page_start: int
    page_end: int
    chunk_type: str
    text: str
