from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from scireview.domain.documents import ChunkType, DocumentChunk, DocumentMetadata, ParsedDocument
from scireview.ingestion.base import ParserError


class DoclingParser:
    """Primary PDF parser using Docling."""

    name = "docling"

    @property
    def version(self) -> str:
        try:
            return version("docling")
        except PackageNotFoundError:  # pragma: no cover
            return "unknown"

    def parse(self, path: Path, *, paper_id: str, sha256: str) -> ParsedDocument:
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as exc:  # pragma: no cover
            raise ParserError("Docling is not installed") from exc

        try:
            result = DocumentConverter().convert(path)
            document = result.document
        except Exception as exc:
            raise ParserError(f"Docling failed to parse {path}: {exc}") from exc

        text = _export_text(document)
        chunks = _chunks_from_text(text, paper_id=paper_id)
        title = _metadata_value(document, "title")
        return ParsedDocument(
            metadata=DocumentMetadata(
                paper_id=paper_id,
                filename=path.name,
                absolute_path=path,
                sha256=sha256,
                title=title,
                authors=[],
                year=None,
                journal=None,
                doi=None,
                parser_name=self.name,
                parser_version=self.version,
            ),
            chunks=chunks,
            warnings=[] if chunks else ["Docling returned no text chunks"],
        )


def _export_text(document: object) -> str:
    dynamic_document = cast(Any, document)
    if hasattr(dynamic_document, "export_to_markdown"):
        return str(dynamic_document.export_to_markdown()).strip()
    if hasattr(dynamic_document, "export_to_text"):
        return str(dynamic_document.export_to_text()).strip()
    return str(dynamic_document).strip()


def _metadata_value(document: object, name: str) -> str | None:
    metadata = getattr(document, "metadata", None)
    value = getattr(metadata, name, None) if metadata is not None else None
    return str(value) if value else None


def _chunks_from_text(text: str, *, paper_id: str) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    for raw in text.split("\n\n"):
        cleaned = raw.strip()
        if not cleaned:
            continue
        chunk_type = ChunkType.PARAGRAPH
        lowered = cleaned.lower()
        section = None
        if lowered.startswith("# references") or lowered == "references":
            chunk_type = ChunkType.REFERENCES
            section = "References"
        elif lowered.startswith("# abstract") or lowered == "abstract":
            chunk_type = ChunkType.ABSTRACT
            section = "Abstract"
        elif cleaned.startswith("#"):
            section = cleaned.strip("# ").splitlines()[0]
        chunks.append(
            DocumentChunk(
                paper_id=paper_id,
                section_title=section,
                page_start=1,
                page_end=1,
                text=cleaned,
                chunk_type=chunk_type,
            )
        )
    return chunks
