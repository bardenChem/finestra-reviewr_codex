# SciReview

SciReview is a local-first scientific literature analysis application. It reads PDFs from a folder, parses them with page-level provenance, extracts methods and results through a local LLM backend, stores structured evidence, and exports deterministic comparison tables.

## Architecture

The package is named `scireview`. Domain models are Pydantic v2 objects. PDF parsers, LLMs, embeddings, relational storage, and vector storage are isolated behind interfaces so implementations can be replaced without changing extraction or comparison logic.

Main components:

- `ingestion`: recursive PDF scanning, SHA-256 hashing, duplicate detection, Docling parsing, PyMuPDF fallback.
- `storage`: SQLite tables through SQLAlchemy 2.x and repository adapters.
- `llm`: Ollama backend with Pydantic JSON schema support.
- `extraction`: chunk selection and structured study extraction.
- `comparison`: deterministic pandas evidence matrix and CSV/JSON/Markdown exports.
- `api`: minimal FastAPI application.
- `cli`: Typer command-line interface.

## Installation

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Python 3.12 or newer is required.

## Ollama Setup

Install and start Ollama separately, then pull a model:

```bash
ollama pull llama3.1:8b
ollama serve
```

Example configuration:

```bash
SCIREVIEW_OLLAMA_BASE_URL=http://localhost:11434
SCIREVIEW_OLLAMA_MODEL=llama3.1:8b
```

The extraction temperature defaults to zero in the Ollama adapter.

## Basic CLI Workflow

```bash
scireview init-db
scireview ingest data/pdfs
scireview extract
scireview compare --format markdown
```

Other useful commands:

```bash
scireview ingest data/pdfs --force
scireview extract --paper-id PAPER_ID
scireview index
scireview compare --format csv
scireview serve
```

Vector indexing is disabled by default. Set `SCIREVIEW_VECTOR_INDEXING_ENABLED=true` to use Qdrant local mode and Sentence Transformers.

## API

Start the API:

```bash
scireview serve
```

Implemented endpoints:

- `GET /health`
- `GET /papers`
- `GET /papers/{paper_id}`
- `GET /papers/{paper_id}/chunks`
- `GET /papers/{paper_id}/study-record`
- `POST /ingest`
- `POST /extract/{paper_id}`
- `GET /comparisons`

## Evidence Traceability

Methods and quantitative results store one or more `EvidenceSpan` objects with paper ID, chunk ID, page, section, quote, and support type. Comparison-table rows include source page and evidence quotation. The extraction prompt instructs the model to prefer explicit evidence and avoid using references-section text as experimental evidence.

## Current Limitations

This is an initial working version, not a scientifically validated extraction system. Docling metadata and layout richness are normalized conservatively. PyMuPDF fallback extracts page text but does not recover rich table structure. No authentication, distributed workers, frontend, fine-tuning, or autonomous agents are included.

## Development

```bash
make install
make test
make lint
make format
make typecheck
make run-api
```

Equivalent direct commands:

```bash
pytest
ruff check .
ruff format .
mypy src/scireview
```

## Configuration

Settings can come from `.env`, environment variables with the `SCIREVIEW_` prefix, or an optional YAML file passed with `--config`.

See `config/settings.example.yaml` for all supported settings.

## Privacy

When using local backends, PDFs, parsed text, embeddings, and inference stay on the local machine. SciReview does not upload documents by itself. External behavior depends on the backends you configure.
