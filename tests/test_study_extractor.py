from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from scireview.domain.documents import DocumentChunk, DocumentMetadata, ParsedDocument
from scireview.domain.studies import StudyRecord
from scireview.extraction.study_extractor import StudyExtractor
from scireview.ingestion.base import ParserError
from scireview.ingestion.deduplicator import HashDeduplicator
from scireview.ingestion.scanner import PdfScanner
from scireview.ingestion.service import IngestionService
from scireview.llm.base import LLMMessage
from scireview.storage.repositories import PaperRepository


class MemoryPaperRepository:
    def __init__(self) -> None:
        self.saved: list[ParsedDocument] = []
        self.existing_hashes: set[str] = set()

    def has_sha256(self, sha256: str) -> bool:
        return sha256 in self.existing_hashes

    def save_parsed_document(self, parsed: ParsedDocument) -> None:
        self.saved.append(parsed)

    def list_papers(self) -> list[DocumentMetadata]:
        return []

    def get_paper(self, paper_id: str) -> DocumentMetadata | None:
        return None

    def get_chunks(self, paper_id: str | None = None) -> list[DocumentChunk]:
        return []


class FailingParser:
    name = "failing"
    version = "1"

    def parse(self, path: Path, *, paper_id: str, sha256: str) -> ParsedDocument:
        raise ParserError("boom")


class SuccessfulParser:
    name = "successful"
    version = "1"

    def __init__(self, parsed: ParsedDocument) -> None:
        self.parsed = parsed

    def parse(self, path: Path, *, paper_id: str, sha256: str) -> ParsedDocument:
        return self.parsed


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
        return self.response.model_dump_json()


def test_structured_extraction_with_fake_llm(
    tmp_path: Path,
    synthetic_chunks: list[DocumentChunk],
    study_record: StudyRecord,
) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Use only supplied text.", encoding="utf-8")
    extractor = StudyExtractor(FakeLLM(study_record), prompt)

    record = extractor.extract("paper-1", synthetic_chunks)

    assert record.methods[0].evidence[0].quote == "We measured growth using dataset A"
    assert record.results[0].raw_value == "12 mg"


def test_primary_parser_falls_back_to_secondary(
    tmp_path: Path,
    parsed_document: ParsedDocument,
) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF synthetic")
    repo: PaperRepository = MemoryPaperRepository()
    service = IngestionService(
        PdfScanner(),
        HashDeduplicator(),
        FailingParser(),
        SuccessfulParser(parsed_document),
        repo,
    )

    result = service.ingest(tmp_path)

    assert result.parsed_count == 1
    assert repo.saved[0].warnings == ["Primary parser failed: boom"]
