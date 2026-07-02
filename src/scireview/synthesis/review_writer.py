from __future__ import annotations

from scireview.domain.reviews import ReviewSummary
from scireview.domain.studies import StudyRecord
from scireview.synthesis.claim_builder import ClaimBuilder


class ReviewWriter:
    """Minimal synthesis facade that never mutates extracted evidence."""

    def __init__(self, claim_builder: ClaimBuilder | None = None) -> None:
        self.claim_builder = claim_builder or ClaimBuilder()

    def summarize(self, records: list[StudyRecord]) -> ReviewSummary:
        return ReviewSummary(
            commonly_reported_limitations=self.claim_builder.limitation_claims(records)
        )
