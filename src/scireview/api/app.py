from __future__ import annotations

from pathlib import Path
from typing import cast

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from scireview.comparison.evidence_matrix import EvidenceMatrixBuilder
from scireview.config import Settings, configure_logging
from scireview.extraction.service import ExtractionService
from scireview.extraction.study_extractor import StudyExtractor
from scireview.ingestion.deduplicator import HashDeduplicator
from scireview.ingestion.docling_parser import DoclingParser
from scireview.ingestion.pymupdf_parser import PyMuPDFParser
from scireview.ingestion.scanner import PdfScanner
from scireview.ingestion.service import IngestionService
from scireview.llm.base import LLMGenerationError, LLMUnavailableError
from scireview.llm.ollama_backend import OllamaBackend
from scireview.storage.database import create_sqlite_engine, init_database, session_factory
from scireview.storage.repositories import SqlAlchemyPaperRepository, SqlAlchemyStudyRepository


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_dir: Path
    force: bool = False


def create_app() -> FastAPI:
    settings = Settings()
    configure_logging(settings.logging_level)
    engine = create_sqlite_engine(settings.sqlite_database_path)
    init_database(engine)
    factory = session_factory(engine)
    app = FastAPI(title="Finestra", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/papers")
    def papers() -> list[dict[str, object]]:
        with factory() as session:
            return [
                paper.model_dump(mode="json")
                for paper in SqlAlchemyPaperRepository(session).list_papers()
            ]

    @app.get("/papers/{paper_id}")
    def paper(paper_id: str) -> dict[str, object]:
        with factory() as session:
            found = SqlAlchemyPaperRepository(session).get_paper(paper_id)
            if found is None:
                raise HTTPException(status_code=404, detail="Paper not found")
            return found.model_dump(mode="json")

    @app.get("/papers/{paper_id}/chunks")
    def chunks(paper_id: str) -> list[dict[str, object]]:
        with factory() as session:
            return [
                chunk.model_dump(mode="json")
                for chunk in SqlAlchemyPaperRepository(session).get_chunks(paper_id)
            ]

    @app.get("/papers/{paper_id}/study-record")
    def study_record(paper_id: str) -> dict[str, object]:
        with factory() as session:
            found = SqlAlchemyStudyRepository(session).get_study_record(paper_id)
            if found is None:
                raise HTTPException(status_code=404, detail="Study record not found")
            return found.model_dump(mode="json")

    @app.post("/ingest")
    def ingest(request: IngestRequest) -> dict[str, object]:
        with factory() as session:
            service = IngestionService(
                PdfScanner(),
                HashDeduplicator(),
                DoclingParser(
                    chunk_target_chars=settings.chunk_target_chars,
                    chunk_overlap_chars=settings.chunk_overlap_chars,
                ),
                PyMuPDFParser(
                    chunk_target_chars=settings.chunk_target_chars,
                    chunk_overlap_chars=settings.chunk_overlap_chars,
                ),
                SqlAlchemyPaperRepository(session),
            )
            result = service.ingest(request.input_dir, force=request.force)
            session.commit()
            return result.__dict__

    @app.post("/extract/{paper_id}")
    def extract(paper_id: str) -> dict[str, str]:
        with factory() as session:
            llm = OllamaBackend(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                timeout_seconds=settings.request_timeout_seconds,
            )
            service = ExtractionService(
                SqlAlchemyPaperRepository(session),
                SqlAlchemyStudyRepository(session),
                StudyExtractor(llm, Path("config/prompts/extract_study.txt")),
            )
            try:
                service.extract_one(paper_id)
            except LLMUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except LLMGenerationError as exc:
                raise HTTPException(status_code=504, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            session.commit()
            return {"status": "ok"}

    @app.get("/comparisons")
    def comparisons() -> list[dict[str, object]]:
        with factory() as session:
            paper_repo = SqlAlchemyPaperRepository(session)
            study_repo = SqlAlchemyStudyRepository(session)
            papers_by_id = {paper.paper_id: paper for paper in paper_repo.list_papers()}
            frame = EvidenceMatrixBuilder().build(study_repo.list_study_records(), papers_by_id)
            return cast("list[dict[str, object]]", frame.to_dict(orient="records"))

    return app
