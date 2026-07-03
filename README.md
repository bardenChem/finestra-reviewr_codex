# Finestra

Finestra is a local-first scientific literature analysis application. It reads PDFs from a folder, parses them with page-level provenance, extracts methods and results through a local LLM backend, stores structured evidence, and exports deterministic comparison tables.

## Architecture

The user-facing software name is Finestra. The Python package/import namespace is currently `scireview`. Domain models are Pydantic v2 objects. PDF parsers, LLMs, embeddings, relational storage, and vector storage are isolated behind interfaces so implementations can be replaced without changing extraction or comparison logic.

Main components:

- `ingestion`: recursive PDF scanning, SHA-256 hashing, duplicate detection, Docling parsing, PyMuPDF fallback.
- `storage`: SQLite tables through SQLAlchemy 2.x and repository adapters.
- `llm`: Ollama backend with Pydantic JSON schema support.
- `extraction`: chunk selection and structured study extraction.
- `comparison`: deterministic pandas evidence matrix and CSV/JSON/Markdown exports.
- `api`: minimal FastAPI application.
- `cli`: Typer command-line interface.

## Installation

Python 3.12 or newer is required. If the system only has Python 3.11, install
Python 3.12 first and create the virtual environment with that interpreter.

Debian or Ubuntu options:

```bash
# Option A: distro package, when available
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev

# Option B: pyenv, useful when the distro does not ship Python 3.12
curl https://pyenv.run | bash
pyenv install --list | grep " 3\.12\."
PYTHON_VERSION=3.12.11  # replace with the latest listed 3.12 patch release
pyenv install "$PYTHON_VERSION"
pyenv local "$PYTHON_VERSION"
```

macOS with Homebrew:

```bash
brew install python@3.12
python3.12 -m venv .venv
```

Windows:

```powershell
winget install Python.Python.3.12
py -3.12 -m venv .venv
```

Then install Finestra:

```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

If `python3.12 -m venv` fails on Debian or Ubuntu, install the matching
`python3.12-venv` package. If package installation is unavailable, use `pyenv`.

## Ollama Setup

Install and start Ollama separately, then pull a model:

```bash
ollama pull llama3.1:8b
ollama serve
```

Example configuration:

```bash
FINESTRA_OLLAMA_BASE_URL=http://localhost:11434
FINESTRA_OLLAMA_MODEL=llama3.1:8b
```

The extraction temperature defaults to zero in the Ollama adapter.

## Basic CLI Workflow

```bash
finestra init-db
finestra ingest data/pdfs
finestra extract
finestra compare --format markdown
```

Other useful commands:

```bash
finestra ingest data/pdfs --force
finestra extract --paper-id PAPER_ID
finestra index
finestra compare --format csv
finestra serve
```

The installed primary console command is `finestra`. The older `scireview`
console-script alias is still provided for compatibility with the package
namespace and earlier documentation.

Vector indexing is disabled by default. Set `FINESTRA_VECTOR_INDEXING_ENABLED=true` to use Qdrant local mode and Sentence Transformers.

Example output:

```text
$ finestra init-db
Initialized database at data/database/finestra.sqlite3

$ finestra ingest data/pdfs
Ingestion complete: discovered=3 parsed=2 skipped=0 duplicates=1

$ finestra ingest data/pdfs
Ingestion complete: discovered=3 parsed=0 skipped=2 duplicates=1

$ finestra compare --format markdown
Exported comparison table to data/exports/comparison.md
```

The exact counts depend on the PDFs present and whether their SHA-256 hashes
already exist in the database.

## Data Locations

Default local paths are relative to the project root:

- PDF input directory: `data/pdfs`
- Parsed-document directory setting: `data/parsed`
- Export directory: `data/exports`
- SQLite database: `data/database/finestra.sqlite3`
- Qdrant local storage: `data/database/qdrant`
- Extraction prompt: `config/prompts/extract_study.txt`
- Synthesis prompt: `config/prompts/synthesize_comparison.txt`

The current ingestion implementation stores parsed chunks directly in SQLite.
It does not yet write separate parsed-document files under `data/parsed`; that
directory is reserved for a future cache/export layer.

Override paths with `.env`, environment variables, or YAML:

```bash
FINESTRA_SQLITE_DATABASE_PATH=/absolute/path/finestra.sqlite3
FINESTRA_EXPORT_DIR=/absolute/path/exports
finestra init-db

finestra ingest /path/to/pdfs --config config/settings.example.yaml
```

## Finding Paper IDs

After ingestion, paper IDs are stored in the `papers` table. A paper ID is
deterministically derived from the PDF SHA-256 hash, so re-ingesting the same
file produces the same ID.

Using SQLite:

```bash
sqlite3 data/database/finestra.sqlite3 \
  "select paper_id, filename, title, sha256 from papers order by filename;"
```

Using the API:

```bash
finestra serve
curl http://127.0.0.1:8000/papers
```

Current CLI commands do not include a dedicated `list-papers` command.

## API

Start the API:

```bash
finestra serve
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

Example API requests:

```bash
curl http://127.0.0.1:8000/health

curl http://127.0.0.1:8000/papers

curl http://127.0.0.1:8000/papers/PAPER_ID/chunks

curl -X POST http://127.0.0.1:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"input_dir": "data/pdfs", "force": false}'

curl -X POST http://127.0.0.1:8000/extract/PAPER_ID

curl http://127.0.0.1:8000/comparisons
```

## Evidence Traceability

Methods and quantitative results store one or more `EvidenceSpan` objects with paper ID, chunk ID, page, section, quote, and support type. Comparison-table rows include source page and evidence quotation. The extraction prompt instructs the model to prefer explicit evidence and avoid using references-section text as experimental evidence.

## Extraction Warnings

Extraction warnings are stored in the `study_records.extraction_warnings` JSON
column. They include local validation warnings such as methods or results with
no supporting evidence.

Inspect warnings with SQLite:

```bash
sqlite3 data/database/finestra.sqlite3 \
  "select paper_id, extraction_warnings from study_records;"
```

Inspect warnings with the API:

```bash
curl http://127.0.0.1:8000/papers/PAPER_ID/study-record
```

Parser warnings are stored in the `papers.warnings` JSON column:

```bash
sqlite3 data/database/finestra.sqlite3 \
  "select paper_id, filename, warnings from papers;"
```

## Resetting Local State

To rebuild only the relational database:

```bash
rm -f data/database/finestra.sqlite3
finestra init-db
finestra ingest data/pdfs --force
```

To rebuild vector indexes as well:

```bash
rm -rf data/database/qdrant
FINESTRA_VECTOR_INDEXING_ENABLED=true finestra index
```

To clear generated comparison exports:

```bash
rm -f data/exports/comparison.csv \
      data/exports/comparison.json \
      data/exports/comparison.md
```

Do not delete `data/pdfs` unless you also want to remove your source PDFs.

## Resource Requirements

Approximate local requirements depend mostly on PDF count, the embedding model,
and the Ollama model.

- Python application, scanning, SQLite, and comparison export: usually less
  than 1 GB RAM for small collections.
- Docling PDF parsing: plan for 2-4 GB RAM for typical PDFs; large scanned or
  layout-heavy documents may need more.
- Ollama extraction: depends on the model. A 7B or 8B quantized model commonly
  needs about 5-8 GB RAM or VRAM. Larger models need substantially more.
- Sentence Transformers indexing with `all-MiniLM-L6-v2`: usually 1-2 GB RAM
  for small to moderate collections.
- Disk: SQLite stores parsed text and extraction records. Qdrant stores vectors.
  Keep at least several GB free if indexing many papers.
- GPU: optional. Ollama and Sentence Transformers can run on CPU, but extraction
  and embedding generation will be slower.

Finestra does not download model files during `init-db`, `ingest`, or
`compare`. These components may download model files when used:

- `ollama pull MODEL_NAME`: downloads the Ollama model explicitly.
- `finestra index` with vector indexing enabled: Sentence Transformers may
  download the configured embedding model if it is not already cached.
- Docling dependencies may download or use model assets depending on the
  installed Docling configuration and parser features.

## Integration Testing

Unit tests use fake parsers and fake LLMs, so they do not require Ollama,
internet access, real PDFs, or a GPU:

```bash
pytest
```

A practical local integration smoke test uses one small non-sensitive PDF:

```bash
cp /path/to/sample.pdf data/pdfs/
finestra init-db
finestra ingest data/pdfs --force
sqlite3 data/database/finestra.sqlite3 \
  "select paper_id, filename, parser_name, json_array_length(warnings) from papers;"

PAPER_ID=$(sqlite3 data/database/finestra.sqlite3 \
  "select paper_id from papers order by filename limit 1;")
```

In another terminal, start Ollama if it is not already running:

```bash
ollama serve
```

Then run extraction and export:

```bash
ollama pull llama3.1:8b
finestra extract --paper-id "$PAPER_ID"
finestra compare --format markdown
cat data/exports/comparison.md
```

Optional API integration check:

```bash
finestra serve
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/papers
curl http://127.0.0.1:8000/comparisons
```

This integration path exercises installed PDF parsing libraries, the real
SQLite database, Ollama connectivity, and export generation.

## Troubleshooting

Docling failures:

- Confirm the file is a readable PDF and not encrypted.
- Run with more logging: `FINESTRA_LOGGING_LEVEL=DEBUG finestra ingest data/pdfs --force`.
- Check parser warnings in SQLite: `select filename, warnings from papers;`.
- If Docling raises an error, Finestra logs the failure and tries PyMuPDF.
- If PyMuPDF also fails, ingestion fails for that file instead of silently
  discarding the error.
- For scanned image-only PDFs, see the OCR section below.

Ollama failures:

- Confirm Ollama is running: `curl http://localhost:11434/api/tags`.
- Confirm the configured model exists: `ollama list`.
- Pull the model if missing: `ollama pull llama3.1:8b`.
- Check `.env` values for `FINESTRA_OLLAMA_BASE_URL`,
  `FINESTRA_OLLAMA_MODEL`, and `FINESTRA_REQUEST_TIMEOUT_SECONDS`.
- Extraction raises a clear backend error when Ollama is unavailable or returns
  an unexpected response.

Common database issues:

- `no such table`: run `finestra init-db`.
- Extraction finds no chunks: ingest PDFs first and confirm paper IDs.
- Ingestion skips files: their SHA-256 hashes are already present; use
  `finestra ingest data/pdfs --force` to parse again.

## Tested Scope

Unit-tested in this repository:

- Recursive PDF discovery and deterministic ordering.
- SHA-256 duplicate detection.
- Domain validation and extraction warnings for unsupported evidence.
- Structured extraction using a fake LLM response.
- Evidence matrix construction.
- CSV, JSON, and Markdown export.
- Primary-parser to fallback-parser behavior.
- FastAPI health route registration.

Implemented but not covered by local unit tests as real integrations:

- Real Docling PDF conversion.
- Real PyMuPDF extraction on arbitrary PDFs.
- Real Ollama model responses.
- Real Sentence Transformers model loading.
- Real Qdrant local indexing and semantic search.

Run the integration smoke test above before relying on a specific machine,
model, or PDF corpus.

## Prompt, Model, and Parser Versions

Parser name and parser package version are persisted in the `papers` table as
`parser_name` and `parser_version`.

The active extraction prompt is read from `config/prompts/extract_study.txt`.
The active Ollama model comes from `FINESTRA_OLLAMA_MODEL` or the YAML
configuration. In this initial version, prompt hashes, prompt versions, Ollama
model tags, and embedding model names are not yet persisted with each
`study_record`. Record those externally in experiment notes if exact extraction
reproducibility is required.

Recommended near-term improvement: add extraction-run metadata with prompt hash,
prompt file path, LLM backend, LLM model tag, embedding model, and created-at
timestamp.

## OCR

Finestra does not explicitly enable or configure OCR in this initial version.
`DoclingParser` uses Docling's default `DocumentConverter`, and the PyMuPDF
fallback extracts embedded text only. Image-only scanned PDFs may therefore
produce empty or incomplete text.

OCR behavior depends on the Docling installation and any OCR engines or model
assets available on the machine. This repository does not declare OCR-specific
runtime extras. If OCR is required, install and configure the OCR dependencies
supported by your Docling version, such as Tesseract, EasyOCR and its Torch
dependencies, or the OCR model assets used by your chosen Docling pipeline, then
extend `DoclingParser` to pass explicit OCR options. That parser configuration
is intentionally not hard-coded yet.

## Current Limitations

This is an initial working version, not a scientifically validated extraction system. Docling metadata and layout richness are normalized conservatively. PyMuPDF fallback extracts page text but does not recover rich table structure. No authentication, distributed workers, frontend, fine-tuning, autonomous agents, explicit OCR configuration, or persisted prompt/model version metadata are included.

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

Settings can come from `.env`, environment variables with the `FINESTRA_` prefix, or an optional YAML file passed with `--config`. Legacy `SCIREVIEW_` variables are still accepted by the current settings loader.

See `config/settings.example.yaml` for all supported settings.

## Privacy

When using local backends, PDFs, parsed text, embeddings, and inference stay on the local machine. Finestra does not upload documents by itself. External behavior depends on the backends you configure.
