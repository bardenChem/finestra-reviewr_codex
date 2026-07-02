from __future__ import annotations

import pandas as pd

from scireview.domain.documents import DocumentMetadata
from scireview.domain.studies import MethodItem, QuantitativeResult, StudyRecord


class EvidenceMatrixBuilder:
    """Build deterministic comparison rows from validated study records."""

    def build(
        self,
        studies: list[StudyRecord],
        papers: dict[str, DocumentMetadata],
    ) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for study in sorted(studies, key=lambda item: item.paper_id):
            paper = papers.get(study.paper_id)
            methods: list[MethodItem | None] = list(study.methods) or [None]
            results: list[QuantitativeResult | None] = list(study.results) or [None]
            for method in methods:
                for result in results:
                    rows.append(self._row(study, paper, method, result))
        return pd.DataFrame(rows, columns=self.columns())

    def columns(self) -> list[str]:
        return [
            "paper ID",
            "title",
            "year",
            "studied system",
            "study design",
            "methodology",
            "important parameters",
            "measured or calculated outcome",
            "numerical result",
            "unit",
            "conditions",
            "conclusion",
            "limitations",
            "source page",
            "evidence quotation",
        ]

    def _row(
        self,
        study: StudyRecord,
        paper: DocumentMetadata | None,
        method: MethodItem | None,
        result: QuantitativeResult | None,
    ) -> dict[str, object]:
        evidence = []
        if method:
            evidence.extend(method.evidence)
        if result:
            evidence.extend(result.evidence)
        first_evidence = evidence[0] if evidence else None
        return {
            "paper ID": study.paper_id,
            "title": paper.title if paper else None,
            "year": paper.year if paper else None,
            "studied system": study.studied_system,
            "study design": study.study_design,
            "methodology": method.description if method else None,
            "important parameters": method.parameters if method else {},
            "measured or calculated outcome": result.outcome if result else None,
            "numerical result": result.raw_value if result else None,
            "unit": result.unit if result else None,
            "conditions": result.conditions if result else None,
            "conclusion": "; ".join(study.main_conclusions),
            "limitations": "; ".join(study.limitations),
            "source page": first_evidence.page if first_evidence else None,
            "evidence quotation": first_evidence.quote if first_evidence else None,
        }
