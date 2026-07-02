from __future__ import annotations

from scireview.domain.reviews import SynthesisClaim
from scireview.domain.studies import StudyRecord


class ClaimBuilder:
    """Build simple evidence-referenced claims from validated records."""

    def limitation_claims(self, records: list[StudyRecord]) -> list[SynthesisClaim]:
        claims: list[SynthesisClaim] = []
        for record in records:
            evidence_ids = [
                span.evidence_id for method in record.methods for span in method.evidence
            ] or [span.evidence_id for result in record.results for span in result.evidence]
            for limitation in record.limitations:
                if evidence_ids:
                    claims.append(SynthesisClaim(claim=limitation, evidence_ids=evidence_ids[:3]))
        return claims
