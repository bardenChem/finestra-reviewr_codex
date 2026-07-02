from __future__ import annotations

from pathlib import Path

from scireview.ingestion.deduplicator import HashDeduplicator
from scireview.ingestion.scanner import PdfFile


def test_sha256_duplicate_detection(tmp_path: Path) -> None:
    files = [
        PdfFile(tmp_path / "a.pdf", "same"),
        PdfFile(tmp_path / "b.pdf", "same"),
        PdfFile(tmp_path / "c.pdf", "different"),
    ]

    report = HashDeduplicator().group(files)

    assert [item.path.name for item in report.unique] == ["a.pdf", "c.pdf"]
    assert [item.path.name for item in report.duplicates["same"]] == ["a.pdf", "b.pdf"]
