from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from scireview.domain.documents import ParsedDocument
from scireview.ingestion.base import DocumentParser, ParserError
from scireview.ingestion.deduplicator import HashDeduplicator
from scireview.ingestion.scanner import PdfScanner
from scireview.storage.repositories import PaperRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    discovered_count: int
    parsed_count: int
    skipped_count: int
    duplicate_count: int
    warnings: list[str] = field(default_factory=list)


class IngestionService:
    """Coordinates discovery, duplicate checks, primary parsing, and fallback parsing."""

    def __init__(
        self,
        scanner: PdfScanner,
        deduplicator: HashDeduplicator,
        primary_parser: DocumentParser,
        fallback_parser: DocumentParser,
        paper_repository: PaperRepository,
    ) -> None:
        self.scanner = scanner
        self.deduplicator = deduplicator
        self.primary_parser = primary_parser
        self.fallback_parser = fallback_parser
        self.paper_repository = paper_repository

    def ingest(self, input_dir: Path, *, force: bool = False) -> IngestionResult:
        files = self.scanner.discover(input_dir)
        duplicate_report = self.deduplicator.group(files)
        parsed_count = 0
        skipped_count = 0
        warnings: list[str] = []
        for pdf in duplicate_report.unique:
            if not force and self.paper_repository.has_sha256(pdf.sha256):
                skipped_count += 1
                logger.info("Skipping already ingested PDF: %s", pdf.path)
                continue
            paper_id = str(uuid5(NAMESPACE_URL, pdf.sha256))
            parsed = self._parse_with_fallback(pdf.path, paper_id=paper_id, sha256=pdf.sha256)
            self.paper_repository.save_parsed_document(parsed)
            parsed_count += 1
            warnings.extend(parsed.warnings)
        duplicate_count = sum(len(items) - 1 for items in duplicate_report.duplicates.values())
        return IngestionResult(
            discovered_count=len(files),
            parsed_count=parsed_count,
            skipped_count=skipped_count,
            duplicate_count=duplicate_count,
            warnings=warnings,
        )

    def _parse_with_fallback(self, path: Path, *, paper_id: str, sha256: str) -> ParsedDocument:
        try:
            return self.primary_parser.parse(path, paper_id=paper_id, sha256=sha256)
        except ParserError as exc:
            logger.warning("Primary parser failed for %s: %s", path, exc)
            parsed = self.fallback_parser.parse(path, paper_id=paper_id, sha256=sha256)
            parsed.warnings.append(f"Primary parser failed: {exc}")
            return parsed
