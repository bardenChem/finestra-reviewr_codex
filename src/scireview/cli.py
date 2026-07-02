from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from scireview.comparison.evidence_matrix import EvidenceMatrixBuilder
from scireview.comparison.exporter import ComparisonExporter, ExportFormat
from scireview.config import Settings, configure_logging
from scireview.embeddings.sentence_transformers_backend import SentenceTransformersBackend
from scireview.extraction.service import ExtractionService
from scireview.extraction.study_extractor import StudyExtractor
from scireview.ingestion.deduplicator import HashDeduplicator
from scireview.ingestion.docling_parser import DoclingParser
from scireview.ingestion.pymupdf_parser import PyMuPDFParser
from scireview.ingestion.scanner import PdfScanner
from scireview.ingestion.service import IngestionService
from scireview.llm.ollama_backend import OllamaBackend
from scireview.storage.database import create_sqlite_engine, init_database, session_factory
from scireview.storage.repositories import SqlAlchemyPaperRepository, SqlAlchemyStudyRepository
from scireview.storage.vector_store import DisabledVectorStore, QdrantLocalVectorStore

app = typer.Typer(help="Local scientific literature analysis with evidence traceability.")
logger = logging.getLogger(__name__)
DEFAULT_PDF_DIR = Path("data/pdfs")


def _settings(config: Path | None = None) -> Settings:
    settings = Settings.from_yaml(config)
    configure_logging(settings.logging_level)
    return settings


@app.command("init-db")
def init_db(
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Optional YAML settings file."),
    ] = None,
) -> None:
    """Initialize the SQLite database."""

    settings = _settings(config)
    engine = create_sqlite_engine(settings.sqlite_database_path)
    init_database(engine)
    typer.echo(f"Initialized database at {settings.sqlite_database_path}")


@app.command()
def ingest(
    input_dir: Annotated[Path, typer.Argument(help="Directory containing PDFs.")] = DEFAULT_PDF_DIR,
    force: Annotated[
        bool,
        typer.Option("--force", help="Parse PDFs even if their hash exists."),
    ] = False,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Optional YAML settings file."),
    ] = None,
) -> None:
    """Discover, de-duplicate, parse, and store PDFs."""

    settings = _settings(config)
    engine = create_sqlite_engine(settings.sqlite_database_path)
    init_database(engine)
    factory = session_factory(engine)
    with factory() as session:
        service = IngestionService(
            PdfScanner(),
            HashDeduplicator(),
            DoclingParser(),
            PyMuPDFParser(),
            SqlAlchemyPaperRepository(session),
        )
        result = service.ingest(input_dir, force=force)
        session.commit()
    typer.echo(
        "Ingestion complete: "
        f"discovered={result.discovered_count} parsed={result.parsed_count} "
        f"skipped={result.skipped_count} duplicates={result.duplicate_count}"
    )
    for warning in result.warnings:
        logger.warning(warning)


@app.command()
def extract(
    paper_id: Annotated[str | None, typer.Option("--paper-id", help="Extract one paper.")] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Optional YAML settings file."),
    ] = None,
) -> None:
    """Extract structured study records using the configured local LLM."""

    settings = _settings(config)
    engine = create_sqlite_engine(settings.sqlite_database_path)
    init_database(engine)
    factory = session_factory(engine)
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
        if paper_id:
            service.extract_one(paper_id)
            count = 1
        else:
            count = service.extract_all()
        session.commit()
    typer.echo(f"Extracted {count} study record(s)")


@app.command()
def index(
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Optional YAML settings file."),
    ] = None,
) -> None:
    """Index chunks in Qdrant local mode when vector indexing is enabled."""

    settings = _settings(config)
    engine = create_sqlite_engine(settings.sqlite_database_path)
    init_database(engine)
    factory = session_factory(engine)
    with factory() as session:
        chunks = SqlAlchemyPaperRepository(session).get_chunks()
    if not settings.vector_indexing_enabled:
        DisabledVectorStore().upsert_chunks(chunks, [])
        typer.echo("Vector indexing is disabled")
        return
    embeddings = SentenceTransformersBackend(settings.embedding_model).embed(
        [chunk.text for chunk in chunks]
    )
    QdrantLocalVectorStore(settings.qdrant_storage_dir).upsert_chunks(chunks, embeddings)
    typer.echo(f"Indexed {len(chunks)} chunks")


@app.command()
def compare(
    format: Annotated[
        ExportFormat,
        typer.Option("--format", help="csv, json, or markdown."),
    ] = "csv",
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Optional YAML settings file."),
    ] = None,
) -> None:
    """Generate and export a deterministic evidence matrix."""

    settings = _settings(config)
    engine = create_sqlite_engine(settings.sqlite_database_path)
    init_database(engine)
    factory = session_factory(engine)
    with factory() as session:
        paper_repo = SqlAlchemyPaperRepository(session)
        study_repo = SqlAlchemyStudyRepository(session)
        papers_by_id = {paper.paper_id: paper for paper in paper_repo.list_papers()}
        frame = EvidenceMatrixBuilder().build(study_repo.list_study_records(), papers_by_id)
    output = ComparisonExporter().export(frame, settings.export_dir, export_format=format)
    typer.echo(f"Exported comparison table to {output}")


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8000,
) -> None:
    """Run the FastAPI application."""

    import uvicorn

    uvicorn.run("scireview.api.app:create_app", factory=True, host=host, port=port)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
