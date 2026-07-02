from __future__ import annotations

from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from scireview.domain.documents import ChunkType, DocumentChunk, DocumentMetadata, ParsedDocument
from scireview.domain.evidence import EvidenceSpan
from scireview.domain.studies import MethodItem, QuantitativeResult, StudyRecord
from scireview.storage.models import (
    DocumentChunkORM,
    EvidenceSpanORM,
    MethodItemORM,
    PaperORM,
    QuantitativeResultORM,
    StudyRecordORM,
)


class PaperRepository(Protocol):
    def has_sha256(self, sha256: str) -> bool: ...
    def save_parsed_document(self, parsed: ParsedDocument) -> None: ...
    def list_papers(self) -> list[DocumentMetadata]: ...
    def get_paper(self, paper_id: str) -> DocumentMetadata | None: ...
    def get_chunks(self, paper_id: str | None = None) -> list[DocumentChunk]: ...


class StudyRepository(Protocol):
    def save_study_record(self, record: StudyRecord) -> None: ...
    def get_study_record(self, paper_id: str) -> StudyRecord | None: ...
    def list_study_records(self) -> list[StudyRecord]: ...


class SqlAlchemyPaperRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def has_sha256(self, sha256: str) -> bool:
        return (
            self.session.scalar(select(PaperORM.paper_id).where(PaperORM.sha256 == sha256))
            is not None
        )

    def save_parsed_document(self, parsed: ParsedDocument) -> None:
        metadata = parsed.metadata
        paper = PaperORM(
            paper_id=metadata.paper_id,
            filename=metadata.filename,
            absolute_path=str(metadata.absolute_path),
            sha256=metadata.sha256,
            title=metadata.title,
            authors=metadata.authors,
            year=metadata.year,
            journal=metadata.journal,
            doi=metadata.doi,
            parser_name=metadata.parser_name,
            parser_version=metadata.parser_version,
            schema_version=metadata.schema_version,
            warnings=parsed.warnings,
        )
        paper.chunks = [
            DocumentChunkORM(
                chunk_id=chunk.chunk_id,
                paper_id=chunk.paper_id,
                section_title=chunk.section_title,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                text=chunk.text,
                chunk_type=chunk.chunk_type.value,
                bounding_boxes=[box.model_dump() for box in chunk.bounding_boxes],
            )
            for chunk in parsed.chunks
        ]
        self.session.merge(paper)

    def list_papers(self) -> list[DocumentMetadata]:
        rows = self.session.scalars(select(PaperORM).order_by(PaperORM.paper_id)).all()
        return [_paper_to_domain(row) for row in rows]

    def get_paper(self, paper_id: str) -> DocumentMetadata | None:
        row = self.session.get(PaperORM, paper_id)
        return _paper_to_domain(row) if row else None

    def get_chunks(self, paper_id: str | None = None) -> list[DocumentChunk]:
        stmt = select(DocumentChunkORM).order_by(
            DocumentChunkORM.paper_id, DocumentChunkORM.page_start, DocumentChunkORM.chunk_id
        )
        if paper_id is not None:
            stmt = stmt.where(DocumentChunkORM.paper_id == paper_id)
        return [_chunk_to_domain(row) for row in self.session.scalars(stmt).all()]


class SqlAlchemyStudyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_study_record(self, record: StudyRecord) -> None:
        self.session.execute(delete(MethodItemORM).where(MethodItemORM.paper_id == record.paper_id))
        self.session.execute(
            delete(QuantitativeResultORM).where(QuantitativeResultORM.paper_id == record.paper_id)
        )
        orm = StudyRecordORM(
            paper_id=record.paper_id,
            research_question=record.research_question,
            study_design=record.study_design,
            studied_system=record.studied_system,
            sample_or_dataset_size=record.sample_or_dataset_size,
            comparator=record.comparator,
            main_conclusions=record.main_conclusions,
            limitations=record.limitations,
            extraction_warnings=record.extraction_warnings,
        )
        orm.methods = [
            MethodItemORM(
                paper_id=record.paper_id,
                category=method.category,
                description=method.description,
                parameters=method.parameters,
                evidence=[span.model_dump(mode="json") for span in method.evidence],
            )
            for method in record.methods
        ]
        orm.results = [
            QuantitativeResultORM(
                paper_id=record.paper_id,
                outcome=result.outcome,
                raw_value=result.raw_value,
                numeric_value=result.numeric_value,
                unit=result.unit,
                uncertainty=result.uncertainty,
                statistical_test=result.statistical_test,
                conditions=result.conditions,
                evidence=[span.model_dump(mode="json") for span in result.evidence],
            )
            for result in record.results
        ]
        self.session.merge(orm)
        for span in _unique_evidence(record):
            self.session.merge(
                EvidenceSpanORM(
                    evidence_id=span.evidence_id,
                    paper_id=span.paper_id,
                    chunk_id=span.chunk_id,
                    page=span.page,
                    section=span.section,
                    quote=span.quote,
                    support_type=span.support_type.value,
                )
            )

    def get_study_record(self, paper_id: str) -> StudyRecord | None:
        row = self.session.get(StudyRecordORM, paper_id)
        return _study_to_domain(row) if row else None

    def list_study_records(self) -> list[StudyRecord]:
        rows = self.session.scalars(select(StudyRecordORM).order_by(StudyRecordORM.paper_id)).all()
        return [_study_to_domain(row) for row in rows]


def _paper_to_domain(row: PaperORM) -> DocumentMetadata:
    return DocumentMetadata(
        paper_id=row.paper_id,
        filename=row.filename,
        absolute_path=row.absolute_path,
        sha256=row.sha256,
        title=row.title,
        authors=row.authors or [],
        year=row.year,
        journal=row.journal,
        doi=row.doi,
        parser_name=row.parser_name,
        parser_version=row.parser_version,
        schema_version=row.schema_version,
    )


def _chunk_to_domain(row: DocumentChunkORM) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=row.chunk_id,
        paper_id=row.paper_id,
        section_title=row.section_title,
        page_start=row.page_start,
        page_end=row.page_end,
        text=row.text,
        chunk_type=ChunkType(row.chunk_type),
        bounding_boxes=row.bounding_boxes or [],
    )


def _study_to_domain(row: StudyRecordORM) -> StudyRecord:
    return StudyRecord(
        paper_id=row.paper_id,
        research_question=row.research_question,
        study_design=row.study_design,
        studied_system=row.studied_system,
        sample_or_dataset_size=row.sample_or_dataset_size,
        comparator=row.comparator,
        methods=[
            MethodItem(
                category=method.category,
                description=method.description,
                parameters=method.parameters,
                evidence=[EvidenceSpan.model_validate(span) for span in method.evidence],
            )
            for method in row.methods
        ],
        results=[
            QuantitativeResult(
                outcome=result.outcome,
                raw_value=result.raw_value,
                numeric_value=result.numeric_value,
                unit=result.unit,
                uncertainty=result.uncertainty,
                statistical_test=result.statistical_test,
                conditions=result.conditions,
                evidence=[EvidenceSpan.model_validate(span) for span in result.evidence],
            )
            for result in row.results
        ],
        main_conclusions=row.main_conclusions or [],
        limitations=row.limitations or [],
        extraction_warnings=row.extraction_warnings or [],
    )


def _unique_evidence(record: StudyRecord) -> list[EvidenceSpan]:
    spans: dict[str, EvidenceSpan] = {}
    for method in record.methods:
        spans.update({span.evidence_id: span for span in method.evidence})
    for result in record.results:
        spans.update({span.evidence_id: span for span in result.evidence})
    return list(spans.values())
