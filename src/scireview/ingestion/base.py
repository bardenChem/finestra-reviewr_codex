from __future__ import annotations

from pathlib import Path
from typing import Protocol

from scireview.domain.documents import ParsedDocument


class ParserError(RuntimeError):
    """Raised when a PDF parser cannot parse a document."""


class DocumentParser(Protocol):
    """Parser interface implemented by replaceable PDF parsers."""

    name: str

    @property
    def version(self) -> str:
        """Human-readable parser package version."""

    def parse(self, path: Path, *, paper_id: str, sha256: str) -> ParsedDocument:
        """Parse a PDF into provenance-preserving chunks."""
