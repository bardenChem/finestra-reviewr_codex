from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from scireview.domain.documents import ChunkType, DocumentChunk, DocumentMetadata, ParsedDocument
from scireview.domain.evidence import EvidenceSpan
from scireview.domain.studies import MethodItem, QuantitativeResult, StudyRecord
from scireview.llm.base import LLMMessage


class FakeLLM:
    def __init__(self, response: StudyRecord) -> None:
        self.response = response
        self.messages: list[LLMMessage] = []

    def generate(
        self,
        messages: list[LLMMessage],
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        self.messages = messages
        return json.dumps(self.response.model_dump(mode="json"))


@pytest.fixture
def synthetic_chunks() -> list[DocumentChunk]:
    return [
        DocumentChunk(
            chunk_id="chunk-1",
            paper_id="paper-1",
            section_title="Methods",
            page_start=2,
            page_end=2,
            text="Methods: We measured growth using dataset A with n=10 samples.",
            chunk_type=ChunkType.PARAGRAPH,
        ),
        DocumentChunk(
            chunk_id="chunk-2",
            paper_id="paper-1",
            section_title="Results",
            page_start=3,
            page_end=3,
            text="Results: Growth increased by 12 mg under condition B.",
            chunk_type=ChunkType.PARAGRAPH,
        ),
        DocumentChunk(
            chunk_id="chunk-3",
            paper_id="paper-1",
            section_title="References",
            page_start=9,
            page_end=9,
            text="References: Other authors reported unrelated results.",
            chunk_type=ChunkType.REFERENCES,
        ),
    ]


@pytest.fixture
def study_record() -> StudyRecord:
    method_evidence = EvidenceSpan(
        evidence_id="ev-method",
        paper_id="paper-1",
        chunk_id="chunk-1",
        page=2,
        section="Methods",
        quote="We measured growth using dataset A",
    )
    result_evidence = EvidenceSpan(
        evidence_id="ev-result",
        paper_id="paper-1",
        chunk_id="chunk-2",
        page=3,
        section="Results",
        quote="Growth increased by 12 mg",
    )
    return StudyRecord(
        paper_id="paper-1",
        research_question="Does condition B alter growth?",
        study_design="controlled experiment",
        studied_system="synthetic cells",
        sample_or_dataset_size="n=10",
        methods=[
            MethodItem(
                category="measurement",
                description="Measured growth using dataset A",
                parameters={"n": 10},
                evidence=[method_evidence],
            )
        ],
        results=[
            QuantitativeResult(
                outcome="growth",
                raw_value="12 mg",
                numeric_value=12.0,
                unit="mg",
                conditions="condition B",
                evidence=[result_evidence],
            )
        ],
        main_conclusions=["Condition B increased growth."],
        limitations=["Synthetic fixture only."],
    )


@pytest.fixture
def paper_metadata(tmp_path: Path) -> DocumentMetadata:
    return DocumentMetadata(
        paper_id="paper-1",
        filename="paper.pdf",
        absolute_path=tmp_path / "paper.pdf",
        sha256="a" * 64,
        title="Synthetic Paper",
        authors=["A. Author"],
        year=2024,
        journal="Synthetic Journal",
        doi=None,
        parser_name="fake",
        parser_version="1",
    )


@pytest.fixture
def parsed_document(
    paper_metadata: DocumentMetadata,
    synthetic_chunks: list[DocumentChunk],
) -> ParsedDocument:
    return ParsedDocument(metadata=paper_metadata, chunks=synthetic_chunks, warnings=[])
