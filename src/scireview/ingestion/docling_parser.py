from __future__ import annotations

import importlib.util
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from scireview.domain.documents import ChunkType, DocumentChunk, DocumentMetadata, ParsedDocument
from scireview.ingestion.base import ParserError
from scireview.ingestion.chunking import split_text_for_chunks


class DoclingParser:
    """Primary PDF parser using Docling."""

    name = "docling"

    def __init__(self, *, chunk_target_chars: int = 3000, chunk_overlap_chars: int = 250) -> None:
        self.chunk_target_chars = chunk_target_chars
        self.chunk_overlap_chars = chunk_overlap_chars

    @property
    def version(self) -> str:
        try:
            return version("docling")
        except PackageNotFoundError:  # pragma: no cover
            return "unknown"

    def parse(self, path: Path, *, paper_id: str, sha256: str) -> ParsedDocument:
        DocumentConverter = _document_converter_class()

        try:
            result = DocumentConverter().convert(path)
            document = result.document
        except Exception as exc:
            raise ParserError(f"Docling failed to parse {path}: {exc}") from exc

        text = _export_text(document)
        chunks = _chunks_from_text(
            text,
            paper_id=paper_id,
            target_chars=self.chunk_target_chars,
            overlap_chars=self.chunk_overlap_chars,
        )
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


def _document_converter_class() -> type[Any]:
    if importlib.util.find_spec("docling") is None:
        raise ParserError("Docling is not installed")
    try:
        module = import_module("docling.document_converter")
    except Exception as exc:
        raise ParserError(
            "Docling is installed but docling.document_converter failed to import. "
            f"Original error: {type(exc).__name__}: {exc}"
        ) from exc
    converter = getattr(module, "DocumentConverter", None)
    if converter is None:
        raise ParserError("Docling import succeeded but DocumentConverter was not found")
    return cast(type[Any], converter)


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


def _chunks_from_text(
    text: str,
    *,
    paper_id: str,
    target_chars: int = 3000,
    overlap_chars: int = 250,
) -> list[DocumentChunk]:
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
        for chunk_text in split_text_for_chunks(
            cleaned,
            target_chars=target_chars,
            overlap_chars=overlap_chars,
        ):
            chunks.append(
                DocumentChunk(
                    paper_id=paper_id,
                    section_title=section,
                    page_start=1,
                    page_end=1,
                    text=chunk_text,
                    chunk_type=chunk_type,
                )
            )
    return chunks
