from __future__ import annotations

from scireview.domain.studies import QuantitativeResult, StudyRecord


def test_study_record_warns_for_results_without_evidence() -> None:
    record = StudyRecord(
        paper_id="paper-1",
        results=[QuantitativeResult(outcome="mass", raw_value="5 kg")],
    )

    assert "result[0] has no supporting evidence" in record.extraction_warnings
