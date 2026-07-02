from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class PaperORM(Base):
    __tablename__ = "papers"

    paper_id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    absolute_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(Integer)
    journal: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String)
    parser_name: Mapped[str] = mapped_column(String, nullable=False)
    parser_version: Mapped[str] = mapped_column(String, nullable=False)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)

    chunks: Mapped[list[DocumentChunkORM]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )
    study_record: Mapped[StudyRecordORM | None] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class DocumentChunkORM(Base):
    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.paper_id"), index=True)
    section_title: Mapped[str | None] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String, nullable=False)
    bounding_boxes: Mapped[list[dict[str, float | int]]] = mapped_column(JSON, default=list)

    paper: Mapped[PaperORM] = relationship(back_populates="chunks")


class StudyRecordORM(Base):
    __tablename__ = "study_records"

    paper_id: Mapped[str] = mapped_column(ForeignKey("papers.paper_id"), primary_key=True)
    research_question: Mapped[str | None] = mapped_column(Text)
    study_design: Mapped[str | None] = mapped_column(Text)
    studied_system: Mapped[str | None] = mapped_column(Text)
    sample_or_dataset_size: Mapped[str | None] = mapped_column(Text)
    comparator: Mapped[str | None] = mapped_column(Text)
    main_conclusions: Mapped[list[str]] = mapped_column(JSON, default=list)
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list)
    extraction_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)

    paper: Mapped[PaperORM] = relationship(back_populates="study_record")
    methods: Mapped[list[MethodItemORM]] = relationship(cascade="all, delete-orphan")
    results: Mapped[list[QuantitativeResultORM]] = relationship(cascade="all, delete-orphan")


class MethodItemORM(Base):
    __tablename__ = "method_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("study_records.paper_id"), index=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict[str, str | int | float | bool | None]] = mapped_column(
        JSON, default=dict
    )
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)


class QuantitativeResultORM(Base):
    __tablename__ = "quantitative_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(ForeignKey("study_records.paper_id"), index=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    numeric_value: Mapped[float | None]
    unit: Mapped[str | None] = mapped_column(Text)
    uncertainty: Mapped[str | None] = mapped_column(Text)
    statistical_test: Mapped[str | None] = mapped_column(Text)
    conditions: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)


class EvidenceSpanORM(Base):
    __tablename__ = "evidence_spans"

    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    paper_id: Mapped[str] = mapped_column(String, index=True)
    chunk_id: Mapped[str] = mapped_column(String, index=True)
    page: Mapped[int] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    support_type: Mapped[str] = mapped_column(String)


class IngestionRunORM(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    input_dir: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False)
    parsed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
