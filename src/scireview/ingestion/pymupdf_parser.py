from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from scireview.domain.documents import ChunkType, DocumentChunk, DocumentMetadata, ParsedDocument
from scireview.ingestion.base import ParserError
from scireview.ingestion.chunking import split_text_for_chunks


class PyMuPDFParser:
    """Fallback parser using PyMuPDF page text extraction."""

    name = "pymupdf"

    def __init__(self, *, chunk_target_chars: int = 3000, chunk_overlap_chars: int = 250) -> None:
        self.chunk_target_chars = chunk_target_chars
        self.chunk_overlap_chars = chunk_overlap_chars

    @property
    def version(self) -> str:
        try:
            return version("pymupdf")
        except PackageNotFoundError:  # pragma: no cover
            return "unknown"

    def parse(self, path: Path, *, paper_id: str, sha256: str) -> ParsedDocument:
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover
            raise ParserError("PyMuPDF is not installed") from exc

        try:
            doc = fitz.open(path)
        except Exception as exc:  # pragma: no cover
            raise ParserError(f"PyMuPDF failed to open {path}: {exc}") from exc

        chunks: list[DocumentChunk] = []
        warnings: list[str] = []
        metadata = doc.metadata or {}
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if not text:
                warnings.append(f"page {index} contained no extractable text")
                continue
            section_title = _guess_section(text)
            for chunk_text in split_text_for_chunks(
                text,
                target_chars=self.chunk_target_chars,
                overlap_chars=self.chunk_overlap_chars,
            ):
                chunks.append(
                    DocumentChunk(
                        paper_id=paper_id,
                        section_title=section_title,
                        page_start=index,
                        page_end=index,
                        text=chunk_text,
                        chunk_type=ChunkType.PARAGRAPH,
                    )
                )

        title = metadata.get("title") or None
        author_value = metadata.get("author") or ""
        authors = [part.strip() for part in author_value.split(";") if part.strip()]
        return ParsedDocument(
            metadata=DocumentMetadata(
                paper_id=paper_id,
                filename=path.name,
                absolute_path=path,
                sha256=sha256,
                title=title,
                authors=authors,
                year=None,
                journal=None,
                doi=None,
                parser_name=self.name,
                parser_version=self.version,
            ),
            chunks=chunks,
            warnings=warnings,
        )


def _guess_section(text: str) -> str | None:
    first_line = text.splitlines()[0].strip()
    if len(first_line) <= 80 and first_line.isupper():
        return first_line.title()
    return None
