from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from scireview.domain.documents import ChunkType, DocumentChunk
from scireview.domain.studies import StudyRecord
from scireview.extraction.schemas import ChunkForExtraction, StudyExtractionResponse
from scireview.llm.base import LLMBackend, LLMMessage


class StudyExtractor:
    """Hierarchical extractor that limits model input to relevant chunks."""

    def __init__(self, llm: LLMBackend, prompt_path: Path, *, max_chunks: int = 24) -> None:
        self.llm = llm
        self.prompt_path = prompt_path
        self.max_chunks = max_chunks

    def extract(self, paper_id: str, chunks: list[DocumentChunk]) -> StudyRecord:
        selected = self._select_relevant_chunks(chunks)
        payload = [
            ChunkForExtraction(
                chunk_id=chunk.chunk_id,
                paper_id=chunk.paper_id,
                section=chunk.section_title,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                chunk_type=chunk.chunk_type.value,
                text=chunk.text,
            ).model_dump()
            for chunk in selected
        ]
        prompt = self.prompt_path.read_text(encoding="utf-8")
        response = self.llm.generate(
            [
                LLMMessage(role="system", content=prompt),
                LLMMessage(
                    role="user",
                    content=(
                        f"Extract a study record for paper_id={paper_id}. "
                        f"Use these provenance-preserving chunks:\n{json.dumps(payload)}"
                    ),
                ),
            ],
            response_schema=StudyExtractionResponse,
        )
        try:
            record = StudyExtractionResponse.model_validate_json(response)
        except ValidationError:
            record = StudyExtractionResponse.model_validate(json.loads(response))
        if record.paper_id != paper_id:
            record.paper_id = paper_id
            record.extraction_warnings.append(
                "LLM returned a different paper_id; corrected locally"
            )
        return StudyRecord.model_validate(record.model_dump())

    def _select_relevant_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        scored = sorted(chunks, key=lambda chunk: self._score_chunk(chunk), reverse=True)
        selected = [
            chunk
            for chunk in scored
            if chunk.chunk_type != ChunkType.REFERENCES and self._score_chunk(chunk) > 0
        ][: self.max_chunks]
        if selected:
            return sorted(selected, key=lambda chunk: (chunk.page_start, chunk.chunk_id))
        return [chunk for chunk in chunks if chunk.chunk_type != ChunkType.REFERENCES][
            : self.max_chunks
        ]

    def _score_chunk(self, chunk: DocumentChunk) -> int:
        text = f"{chunk.section_title or ''}\n{chunk.text}".lower()
        score = 0
        for token in (
            "method",
            "materials",
            "experiment",
            "dataset",
            "sample",
            "result",
            "finding",
        ):
            if token in text:
                score += 3
        if chunk.chunk_type in {ChunkType.TABLE, ChunkType.TABLE_CAPTION, ChunkType.FIGURE_CAPTION}:
            score += 4
        if chunk.chunk_type == ChunkType.REFERENCES:
            score -= 20
        return score
