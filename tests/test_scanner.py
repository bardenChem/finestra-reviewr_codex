from __future__ import annotations

from pathlib import Path

from scireview.ingestion.scanner import PdfScanner, calculate_sha256


def test_recursive_pdf_scanning_is_case_insensitive_and_sorted(tmp_path: Path) -> None:
    nested = tmp_path / "b"
    nested.mkdir()
    pdf_b = nested / "B.PDF"
    pdf_a = tmp_path / "a.pdf"
    ignored = tmp_path / "note.txt"
    pdf_b.write_bytes(b"b")
    pdf_a.write_bytes(b"a")
    ignored.write_text("not a pdf", encoding="utf-8")

    files = PdfScanner().discover(tmp_path)

    assert [item.path.name for item in files] == ["a.pdf", "B.PDF"]
    assert files[0].sha256 == calculate_sha256(pdf_a)
