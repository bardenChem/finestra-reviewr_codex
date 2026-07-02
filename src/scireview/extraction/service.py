from __future__ import annotations

from scireview.extraction.study_extractor import StudyExtractor
from scireview.storage.repositories import PaperRepository, StudyRepository


class ExtractionService:
    """Loads chunks, runs extraction, and persists validated study records."""

    def __init__(
        self,
        paper_repository: PaperRepository,
        study_repository: StudyRepository,
        extractor: StudyExtractor,
    ) -> None:
        self.paper_repository = paper_repository
        self.study_repository = study_repository
        self.extractor = extractor

    def extract_one(self, paper_id: str) -> None:
        chunks = self.paper_repository.get_chunks(paper_id)
        if not chunks:
            msg = f"No chunks found for paper_id={paper_id}"
            raise ValueError(msg)
        record = self.extractor.extract(paper_id, chunks)
        self.study_repository.save_study_record(record)

    def extract_all(self) -> int:
        count = 0
        for paper in self.paper_repository.list_papers():
            self.extract_one(paper.paper_id)
            count += 1
        return count
