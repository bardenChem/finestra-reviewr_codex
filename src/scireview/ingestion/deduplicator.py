from __future__ import annotations

from dataclasses import dataclass

from scireview.ingestion.scanner import PdfFile


@dataclass(frozen=True)
class DuplicateReport:
    """Unique and duplicate discovered PDFs."""

    unique: list[PdfFile]
    duplicates: dict[str, list[PdfFile]]


class HashDeduplicator:
    """Detect duplicate files by SHA-256 hash."""

    def group(self, files: list[PdfFile]) -> DuplicateReport:
        seen: dict[str, PdfFile] = {}
        duplicates: dict[str, list[PdfFile]] = {}
        unique: list[PdfFile] = []
        for file in files:
            if file.sha256 in seen:
                duplicates.setdefault(file.sha256, [seen[file.sha256]]).append(file)
                continue
            seen[file.sha256] = file
            unique.append(file)
        return DuplicateReport(unique=unique, duplicates=duplicates)
