from __future__ import annotations

import json
from pathlib import Path

from scireview.comparison.evidence_matrix import EvidenceMatrixBuilder
from scireview.comparison.exporter import ComparisonExporter
from scireview.domain.documents import DocumentMetadata
from scireview.domain.studies import StudyRecord


def test_evidence_matrix_and_exports(
    tmp_path: Path,
    study_record: StudyRecord,
    paper_metadata: DocumentMetadata,
) -> None:
    frame = EvidenceMatrixBuilder().build([study_record], {"paper-1": paper_metadata})

    assert frame.loc[0, "paper ID"] == "paper-1"
    assert frame.loc[0, "source page"] == 2
    assert frame.loc[0, "evidence quotation"] == "We measured growth using dataset A"

    exporter = ComparisonExporter()
    csv_path = exporter.export(frame, tmp_path, export_format="csv")
    json_path = exporter.export(frame, tmp_path, export_format="json")
    markdown_path = exporter.export(frame, tmp_path, export_format="markdown")

    assert csv_path.read_text(encoding="utf-8").startswith("paper ID,title")
    assert json.loads(json_path.read_text(encoding="utf-8"))[0]["paper ID"] == "paper-1"
    assert "| paper ID" in markdown_path.read_text(encoding="utf-8")
