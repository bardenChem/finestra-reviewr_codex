# SciReview / Finestra Implementation Plan

## 1. Executive Summary

This plan is based on inspection of the current repository, not on README claims alone.
The repository product name is currently **Finestra** in `README.md`, `pyproject.toml`, and
`src/scireview/__init__.py`; the import namespace is `scireview`.

The MVP contains real foundations:

- Pydantic v2 domain models in `src/scireview/domain/`.
- Recursive PDF scanning and SHA-256 duplicate grouping in `src/scireview/ingestion/scanner.py`
  and `src/scireview/ingestion/deduplicator.py`.
- Parser classes for Docling and PyMuPDF in `src/scireview/ingestion/docling_parser.py`
  and `src/scireview/ingestion/pymupdf_parser.py`.
- SQLite persistence through SQLAlchemy 2.x in `src/scireview/storage/models.py`,
  `src/scireview/storage/database.py`, and `src/scireview/storage/repositories.py`.
- A generic Ollama chat backend in `src/scireview/llm/ollama_backend.py`.
- Sentence Transformers and Qdrant-local adapters in `src/scireview/embeddings/` and
  `src/scireview/storage/vector_store.py`.
- Generic structured study extraction in `src/scireview/extraction/`.
- Deterministic pandas comparison-table export in `src/scireview/comparison/`.
- Typer CLI in `src/scireview/cli.py`.
- Minimal FastAPI API in `src/scireview/api/app.py`.
- Unit tests using fake parsers and fake LLMs under `tests/`.

The MVP also has an immediate baseline blocker: both parser modules import
`scireview.ingestion.chunking.split_text_for_chunks`, but there is no
`src/scireview/ingestion/chunking.py` in the repository. Because both `src/scireview/cli.py`
and `src/scireview/api/app.py` import `DoclingParser` and `PyMuPDFParser` at module import
time, advertised CLI/API workflows can fail before execution. Phase 0 should fix and verify
that baseline before architecture expansion.

Current missing or immature capabilities are substantial:

- No complete question-answering workflow.
- No GUI.
- No review-project workflow or controlled review generation.
- No background job system.
- No multimodal processing or explicit OCR configuration.
- No domain plugin architecture.
- No extraction-run provenance, model registry, prompt versioning, or human correction history.
- No Alembic migrations.
- No integration tests for real PDFs, Docling, PyMuPDF, Ollama, Sentence Transformers, or Qdrant.

The recommended direction is to preserve the existing modular intent, but add an application
composition layer, versioned provenance, model routing, retrieval/QA services, review projects,
domain plugins, background jobs, and a GUI that calls stable APIs instead of reaching into the
scientific core.

## 2. Current As-Is Architecture

### Repository And Naming Facts

- Project metadata: `pyproject.toml` declares package name `finestra`, version `0.1.0`,
  and console scripts `finestra` and `scireview`.
- Import namespace: `src/scireview`.
- README states the user-facing name is Finestra and the package namespace is `scireview`.
- The requested future application name is SciReview. Before public release, decide whether
  to keep Finestra branding or rename metadata, commands, data paths, and documentation.

### Python And Dependency Compatibility

Current `pyproject.toml` declares `requires-python = ">=3.11"` and tool settings target
Python 3.11:

- Ruff target: `py311`.
- mypy `python_version = "3.11"`.
- Runtime code uses APIs available in Python 3.11: `enum.StrEnum`, `datetime.UTC`,
  `str.removeprefix`, modern union types, and `zip(..., strict=True)`.
- I did not find Python 3.12-only syntax.

Python 3.11 support is technically realistic for the current code. The primary risk is not
syntax; it is dependency availability and installation weight:

- Base dependencies include FastAPI, httpx, pandas, Pydantic, PyMuPDF, PyYAML, SQLAlchemy,
  Typer, and Uvicorn.
- Optional `pdf` extra installs Docling.
- Optional `vector` extra installs Qdrant client and Sentence Transformers.
- Optional ML packages can pull large transitive dependencies such as PyTorch.

Recommended development workflow on Debian:

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Optional, only when needed:
uv pip install -e ".[pdf]"
uv pip install -e ".[vector]"
```

Do not modify Debian's system Python. Do not use `sudo pip`, global dependency installation,
or `--break-system-packages`. If `/tmp` is space-constrained, use `TMPDIR` and `UV_CACHE_DIR`
pointing to a partition with enough space.

Recommended supported Python range after validation: Python 3.11 and 3.12 initially.
Python 3.13 should be allowed only after Docling, PyMuPDF, Sentence Transformers, Qdrant,
and GUI dependencies are verified.

### Ingestion Flow

Actual current code path:

```text
CLI ingest or API POST /ingest
-> Settings
-> create_sqlite_engine()
-> init_database()
-> IngestionService(
       PdfScanner(),
       HashDeduplicator(),
       DoclingParser(),
       PyMuPDFParser(),
       SqlAlchemyPaperRepository(session),
   )
-> PdfScanner.discover(input_dir)
-> calculate_sha256(path)
-> HashDeduplicator.group(files)
-> PaperRepository.has_sha256(sha256)
-> uuid5(NAMESPACE_URL, sha256) paper_id
-> primary_parser.parse(...)
-> fallback_parser.parse(...) on ParserError
-> ParsedDocument / DocumentMetadata / DocumentChunk
-> SqlAlchemyPaperRepository.save_parsed_document()
-> papers and document_chunks tables
```

Implementation details:

- `PdfScanner.discover()` recursively scans for suffix `.pdf` case-insensitively and sorts
  by resolved path.
- `calculate_sha256()` streams file content.
- `HashDeduplicator.group()` detects duplicates within the current discovery set.
- `IngestionService.ingest()` skips already stored hashes unless `force=True`.
- `DoclingParser` currently converts a document and exports Markdown/text, but assigns
  `page_start=1` and `page_end=1` to all chunks; it does not preserve Docling layout regions,
  tables, figures, captions, or page coordinates.
- `PyMuPDFParser` extracts page text and creates page-level chunks; it does not extract rich
  table structure, images, captions, or bounding boxes.
- Parser warnings are persisted into `PaperORM.warnings`.
- `IngestionRunORM` exists in `src/scireview/storage/models.py`, but no repository or service
  writes ingestion-run rows.
- Baseline blocker: `DoclingParser` and `PyMuPDFParser` import the missing
  `scireview.ingestion.chunking` module.

### Extraction Flow

Actual current code path:

```text
CLI extract or API POST /extract/{paper_id}
-> OllamaBackend(base_url, model, timeout)
-> ExtractionService(
       SqlAlchemyPaperRepository(session),
       SqlAlchemyStudyRepository(session),
       StudyExtractor(llm, Path("config/prompts/extract_study.txt")),
   )
-> PaperRepository.get_chunks(paper_id)
-> StudyExtractor._select_relevant_chunks()
-> prompt_path.read_text()
-> LLMMessage(system=prompt), LLMMessage(user=json chunks)
-> OllamaBackend.generate(response_schema=StudyExtractionResponse)
-> StudyExtractionResponse validation
-> StudyRecord validation warnings
-> SqlAlchemyStudyRepository.save_study_record()
-> study_records, method_items, quantitative_results, evidence_spans
```

Implementation details:

- `StudyExtractor` uses keyword scoring for chunk selection and excludes references chunks.
- `StudyExtractionResponse` is the same generic schema as `StudyRecord`.
- `OllamaBackend` sends Pydantic JSON schema through Ollama's `format` payload field.
- If the model returns a different `paper_id`, `StudyExtractor` corrects it and appends a
  warning.
- `SqlAlchemyStudyRepository.save_study_record()` deletes prior methods/results for the paper
  and merges a new `StudyRecordORM`.
- Evidence is duplicated: stored as JSON inside method/result rows and also merged into the
  `evidence_spans` table.
- Stale `EvidenceSpanORM` rows are not deleted when a later extraction removes evidence.
- No extraction-run table records model, prompt hash, schema version, raw output, validation
  errors, or timestamp.

### Indexing Flow

Actual current code path:

```text
CLI index
-> Settings
-> SqlAlchemyPaperRepository(session).get_chunks()
-> if vector_indexing_enabled is false:
       DisabledVectorStore().upsert_chunks(chunks, [])
       print "Vector indexing is disabled"
   else:
       SentenceTransformersBackend(settings.embedding_model).embed(chunk.text)
       QdrantLocalVectorStore(settings.qdrant_storage_dir).upsert_chunks(chunks, embeddings)
```

Implementation details:

- This flow is connected only to the CLI.
- It is not called automatically after ingestion.
- There is no API endpoint for indexing.
- `QdrantLocalVectorStore.search()` implements dense vector search with optional filters for
  `paper_id`, `section`, `page`, and `chunk_type`, but no current service calls it.
- One default collection name, `"chunks"`, is used.
- Embedding model name, vector size, embedding run, and chunk version are not persisted in
  SQLite.
- Coexistence of multiple embedding models is not supported.
- Reindexing is a full upsert over all chunks; deletion and changed-paper cleanup are not
  handled.
- Qdrant point IDs are `chunk.chunk_id`; current parser chunk IDs are random UUIDs unless
  explicitly supplied, so re-ingesting can create new point IDs for unchanged text.

### Comparison Flow

Actual current code path:

```text
CLI compare or API GET /comparisons
-> SqlAlchemyPaperRepository.list_papers()
-> SqlAlchemyStudyRepository.list_study_records()
-> EvidenceMatrixBuilder.build(studies, papers_by_id)
-> pandas DataFrame with deterministic columns
-> ComparisonExporter.export(...), for CLI only
```

Implementation details:

- `EvidenceMatrixBuilder` creates a cartesian product of methods and results per study.
- It emits one evidence quotation and page, choosing the first method/result evidence span.
- Export formats are CSV, JSON, and Markdown.
- API returns the DataFrame as JSON records; it does not write export files.
- `config/prompts/synthesize_comparison.txt` exists, but no code loads or uses it.

### API Flow

Current FastAPI app in `src/scireview/api/app.py`:

- `GET /health`
- `GET /papers`
- `GET /papers/{paper_id}`
- `GET /papers/{paper_id}/chunks`
- `GET /papers/{paper_id}/study-record`
- `POST /ingest`
- `POST /extract/{paper_id}`
- `GET /comparisons`

The API constructs settings, engine, database tables, repositories, parsers, and Ollama backend
directly inside `create_app()` and route handlers. Long-running ingestion and extraction are
synchronous HTTP request handlers.

### CLI Flow

Current Typer commands in `src/scireview/cli.py`:

- `init-db`
- `ingest`
- `extract`
- `index`
- `compare`
- `serve`

The CLI repeats dependency construction already present in the API. There is no central
application container or factory for services, backends, settings, prompts, jobs, or database
sessions.

## 3. Verified Implementation Status

| Component | Current files | Current status | Evidence from code | Main limitations | Recommended next action |
|---|---|---:|---|---|---|
| Python package | `src/scireview`, `pyproject.toml` | Implemented | `packages = ["scireview"]`, scripts point to `scireview.cli:app` | Project name is `finestra`, future product request says SciReview | Decide naming before public API stability |
| Settings | `src/scireview/config.py`, `.env.example`, `config/settings.example.yaml` | Implemented, shallow | `Settings` supports env aliases and YAML | Flat config only; relative paths assume launch from repo root; no model profiles | Introduce typed nested config and path resolver |
| Pydantic document models | `domain/documents.py` | Implemented and unit-used | `DocumentMetadata`, `DocumentChunk`, `ParsedDocument`, `BoundingBox` | No document role, section hierarchy, figure/table entities, parser run | Extend via versioned models, not one giant object |
| Evidence model | `domain/evidence.py` | Implemented and unit-used | `EvidenceSpan` with paper, chunk, page, section, quote | No bounding box, run ID, claim linkage, citation validation status | Promote evidence to first-class normalized table |
| Generic study model | `domain/studies.py` | Implemented and unit tested | `StudyRecord`, `MethodItem`, `QuantitativeResult`; warning validator | Generic fields are too coarse for chemistry/biology; no raw/normalized value split beyond result | Keep as generic layer; add domain plugins |
| Review domain model | `domain/reviews.py` | Placeholder/minimal | `SynthesisClaim`, `ReviewSummary` | No projects, outlines, sections, review requests, revisions | Replace with staged review-generation models |
| Scanner | `ingestion/scanner.py` | Implemented and unit tested | `PdfScanner.discover()`, `calculate_sha256()` | No file size limits, permission handling, malicious PDF guardrails | Add import validation and job reporting |
| Deduplicator | `ingestion/deduplicator.py` | Implemented and unit tested | Hash grouping | Only content hash; no document identity/version policy | Add repository-level duplicate and version handling |
| Chunking | Expected by parsers | Missing | Parser imports `scireview.ingestion.chunking` | Import-time failure for parser users | Phase 0 baseline fix |
| Docling parser | `ingestion/docling_parser.py` | Partially implemented, currently blocked | `DoclingParser.parse()` calls Docling and exports text | Missing chunking module; page provenance collapses to page 1; no layout/tables/figures | Restore chunking; then add structured Docling extraction |
| PyMuPDF parser | `ingestion/pymupdf_parser.py` | Partially implemented, currently blocked | Page text extraction loop | Missing chunking module; no layout; weak section guessing | Restore chunking; add page/region extraction and tests |
| Ingestion service | `ingestion/service.py` | Implemented and unit tested with fake parser | Primary/fallback parser flow is tested | No persistent ingestion runs; no jobs; synchronous; no per-file error records | Add job-backed ingestion and run tables |
| SQLAlchemy schema | `storage/models.py` | Implemented, no migrations | Tables for papers, chunks, study records, methods, results, evidence spans, ingestion runs | `create_all` only; study record keyed by paper prevents extraction versions; evidence duplicated | Add Alembic and versioned normalized schema |
| Database helpers | `storage/database.py` | Implemented | `create_sqlite_engine`, `init_database`, `session_scope` | Always creates parent dirs/tables; no migrations; no pragmas | Add migration-aware initialization and SQLite pragmas |
| Repositories | `storage/repositories.py` | Implemented, not repository-tested | Paper and study protocols plus SQLAlchemy implementations | No tests for DB round trips; stale evidence spans; no transaction boundary abstraction | Add repository tests and run-aware methods |
| LLM interface | `llm/base.py` | Implemented but too broad | Single `LLMBackend.generate()` protocol | Blends chat and structured extraction; no capabilities, streaming, token accounting | Split into task interfaces and route through model router |
| Ollama backend | `llm/ollama_backend.py` | Implemented, not integration-tested | `POST /api/chat`, schema in `format` | Only Ollama; no model listing/capabilities; no provenance | Keep as adapter; wrap in model registry |
| Embeddings | `embeddings/base.py`, `sentence_transformers_backend.py` | Implemented, not integration-tested | `EmbeddingBackend.embed()`, ST `encode()` | No batching config, model metadata, cache, offline handling | Add model-aware embedding service |
| Vector store | `storage/vector_store.py` | Implemented, not integration-tested | Qdrant local upsert/search with filters | No lifecycle/versioning/deletion; no hybrid search; no service consumer | Move into retrieval package and version indexes |
| Structured extraction | `extraction/study_extractor.py`, `extraction/service.py` | Implemented and unit tested with fake LLM | Prompt loading, chunk selection, schema validation | Generic schema; no extraction runs; no raw output storage; prompt path hard-coded | Add provenance, prompt registry, domain plugins |
| Comparison | `comparison/evidence_matrix.py`, `comparison/exporter.py` | Implemented and unit tested | pandas table and CSV/JSON/Markdown export | No domain-specific columns; evidence selection simplistic | Retain as generic export; make plugin-extensible |
| Synthesis | `synthesis/claim_builder.py`, `synthesis/review_writer.py` | Placeholder | Builds limitation claims only | Not wired to CLI/API; no LLM review generation | Supersede with review-generation package |
| CLI | `cli.py` | Implemented but import-blocked by missing chunking | Commands for init/ingest/extract/index/compare/serve | Duplicated construction; synchronous; no diagnostics, QA, review | Add application container and new commands |
| API | `api/app.py` | Minimal, import-blocked by missing chunking | CRUD-like paper/chunk/study routes plus ingest/extract/compare | Synchronous long tasks; no jobs, QA, review, models, GUI endpoints | Rebuild around service layer and jobs |
| Tests | `tests/` | Unit tests only | Fake LLM/parser tests | No real integration tests; current test imports likely exposed to missing chunking | Add import smoke tests and optional integrations |
| Prompt templates | `config/prompts/*.txt` | Present, partially used | Extraction prompt used; synthesis prompt unused | Not packaged/versioned/hashed; paths are relative | Move to packaged prompt registry |
| GUI | None | Missing | No GUI files | No user-facing import/view/QA/review workflows | Add GUI after API/job foundation |
| QA | None | Missing | No `/ask`, no QA service | Vector search unused by user workflow | Build complete RAG workflow |
| Multimodal | None | Missing | No image/figure/table models or vision backend | Cannot process figures or scanned PDFs intentionally | Add optional multimodal pipeline |
| Domain plugins | None | Missing | No `domains/` package | One generic study schema only | Add plugin registry and schemas |
| Background jobs | None | Missing | No job table/service | Long HTTP calls; no progress/cancel/retry | Add local job table and worker |
| Fine-tuning | None | Missing | No training data or adapters | Not appropriate before evaluation | Postpone until Phase 9 |

## 4. Gap Analysis

### Immediate Baseline Gaps

1. `src/scireview/ingestion/chunking.py` is missing.
2. CLI and API import parser modules eagerly, so the missing module can prevent even unrelated
   commands or route registration.
3. Prompt paths are hard-coded as `Path("config/prompts/extract_study.txt")`.
4. Dependency construction is duplicated between `src/scireview/cli.py` and
   `src/scireview/api/app.py`.
5. `init_database()` uses `Base.metadata.create_all()` directly; there is no migration history.

### Scientific Traceability Gaps

- Parser name/version are stored on papers, but parser settings, prompt hash, model backend,
  model identifier, quantization, raw LLM output, validation errors, and extraction timestamp
  are not stored.
- Human corrections cannot be represented without overwriting the model output.
- Evidence is stored as nested JSON and as standalone spans, but claim-level provenance is not
  normalized or versioned.
- Page provenance is only page-level for PyMuPDF and mostly incorrect for Docling chunks.

### Retrieval And QA Gaps

- Qdrant and Sentence Transformers are wired only to `finestra index`.
- No query model, retriever, fusion, reranker, evidence packet, answer generator, or citation
  validator exists.
- Indexing is not idempotent across parser versions and embedding models.
- Deleted/changed papers are not removed from vector storage.

### Review Generation Gaps

- Current `ReviewWriter` is a minimal non-LLM facade for limitation claims.
- No review projects, requests, outlines, editable sections, paragraph regeneration, citation
  validation, contradiction checks, or exports exist.
- The synthesis prompt exists but is not wired into code.

### Domain And Multimodal Gaps

- There is no domain plugin system.
- Current schemas cannot represent computational chemistry, QM/MM, molecular simulation,
  enzymology, structural biology, or biomolecular assay detail without uncontrolled dictionaries.
- No figure/image/table/caption entities exist.
- No vision-language backend, OCR backend, or specialized image-processing adapter exists.

### Operations Gaps

- No background jobs, progress tracking, cancellation, retry, resumability, or GPU/model resource
  locking.
- No GUI.
- No evaluation framework.
- No security layer for local file imports, path traversal, PDF sanitization, prompt injection,
  or model-server exposure warnings.

## 5. Target Architecture

The target architecture should separate stable scientific concepts from replaceable local
backends:

- **Core domain models**: papers, chunks, evidence, extraction runs, normalized scientific fields,
  review projects, claims, figures, tables, human revisions.
- **Application services**: ingestion, parsing, extraction, indexing, QA, review generation,
  comparison, exports, evaluation.
- **Backends**: parsers, OCR, text generation, structured extraction, embeddings, reranking,
  vision-language inference, specialized scientific image tools.
- **Routing/configuration**: model registry, execution profiles, hardware discovery, task router.
- **Interfaces**: CLI, FastAPI API, GUI, optional background worker.

The current `LLMBackend` should be retained only as a compatibility adapter, then split into
task-specific protocols. A single chat-generation interface is not enough for embeddings,
reranking, structured extraction, vision inference, OCR, and specialized scientific tools.

### Model Backend Architecture

Separate interfaces should exist for:

- Text generation.
- Structured extraction.
- Embeddings.
- Reranking.
- Vision-language inference.
- OCR.
- Optional specialized scientific image processing.

Backend implementations to plan:

- Ollama.
- llama.cpp server.
- Local OpenAI-compatible servers.
- Hugging Face Transformers.
- vLLM for workstation profiles.
- Optional future remote providers, disabled by default and clearly labeled.

Do not hard-code model names as architectural dependencies. Model identifiers belong in
configuration, the model registry, or profile defaults.

Routing should initially be static through configuration and execution profiles. Dynamic routing
based on hardware, document complexity, and observed failures should be a later enhancement after
metrics exist.

### Hardware And Execution Profiles

Profiles should be typed configuration records:

- `light`
- `balanced`
- `workstation`
- `high_memory`
- `gpu`
- `multimodal`

Each profile defines:

- Text model.
- Extraction model.
- Synthesis model.
- Embedding model.
- Reranker.
- Vision model.
- Context limits.
- Chunk limits.
- Parallel job count.
- Batch size.
- CPU/GPU preference.
- Quantization.
- Multimodal enablement.
- Verification pass enablement.

The program must assume CPU-only operation by default. Hardware discovery should detect available
RAM, CPU cores, CUDA/ROCm availability when libraries are present, Ollama availability, and model
server reachability. Explicit user overrides must win over discovery.

Fallback behavior:

- Missing model: mark capability unavailable, return actionable error, do not download implicitly.
- Out-of-memory or model load failure: reduce batch size, lower context/chunk limits, or fall
  back to CPU/light profile when configured.
- GPU unavailable: run CPU-capable tasks only; show multimodal/large-model features as disabled.
- Job cancellation: store cancellation state, stop after current safe checkpoint, release model
  locks.

### Background Jobs

Long-running operations must not run directly inside HTTP request handlers. Initial local
implementation should use a SQLite-backed job table plus an in-process worker loop or thread pool.
This is simpler than Celery/RQ and still evolves cleanly toward external workers later.

Job states:

- `pending`
- `queued`
- `running`
- `parsing`
- `indexing`
- `extracting`
- `synthesizing`
- `verifying`
- `completed`
- `failed`
- `cancelled`

Jobs should support progress, cancellation, retries, resumability, error logs, dependencies,
model resource locks, and GPU concurrency limits.

```python
class Job(BaseModel):
    job_id: str
    job_type: str
    state: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress_current: int = 0
    progress_total: int | None = None
    status_message: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    retry_count: int = 0
    parent_job_id: str | None = None
    cancel_requested: bool = False
    resource_locks: list[str] = Field(default_factory=list)
```

### Domain Plugin Architecture

Use plugin registration and composition rather than inheritance-heavy schemas. Each plugin should
declare its schemas, prompts, validators, comparison columns, and retrieval helpers. Persisted
records can use discriminated unions keyed by domain and schema version, but runtime behavior
should come from registered plugin objects.

Avoid one giant Pydantic model containing every scientific field. The generic `StudyRecord`
should remain a small cross-domain summary. Domain plugins should add structured records for
fields that are actually meaningful to that domain.

Suggested structure:

```text
src/scireview/domains/
    base.py
    registry.py
    generic/
    computational_chemistry/
    biomolecular_sciences/
```

```python
class DomainPlugin(Protocol):
    domain_id: str
    display_name: str
    schema_version: str

    def extraction_schema(self) -> type[BaseModel]: ...
    def prompt_template_ids(self) -> list[str]: ...
    def select_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    def controlled_vocabularies(self) -> dict[str, list[str]]: ...
    def validate_record(self, record: BaseModel) -> list[str]: ...
    def normalize_record(self, record: BaseModel) -> BaseModel: ...
    def comparison_columns(self) -> list[str]: ...
    def query_expansion_terms(self, query: str) -> list[str]: ...
    def evidence_checks(self, record: BaseModel) -> list[str]: ...
```

### Configuration And Dependency Architecture

Settings should be nested and typed for:

- Storage.
- Database.
- Parsing.
- OCR.
- Embeddings.
- Vector store.
- Model backends.
- Execution profiles.
- Domain plugins.
- Jobs.
- GUI.
- Export.
- Logging.

Current relative paths should be resolved against an explicit project/data root, not the process
current working directory. Prompt templates should be packaged and versioned, preferably through
`importlib.resources`, with prompt IDs, semantic versions, and hashes persisted in run records.

Optional dependency groups should evolve toward:

- `core`
- `dev`
- `parser-pymupdf`
- `parser-docling`
- `embeddings`
- `qdrant`
- `ollama`
- `vision`
- `gui`
- `training`
- `all`

The lightweight install must not require multimodal or training dependencies.

## 6. Proposed Source Tree

Proposed tree, related to current files:

```text
src/scireview/
    api/
        app.py
        routes/
        schemas.py
    application/
        container.py
        factories.py
        services.py
    cli.py
    config.py
    models/
        documents.py
        evidence.py
        studies.py
        extraction.py
        review.py
        jobs.py
        models.py
    ingestion/
        base.py
        scanner.py
        deduplicator.py
        chunking.py
        service.py
        docling_parser.py
        pymupdf_parser.py
    parsing/
        layout.py
        sections.py
        tables.py
    storage/
        database.py
        models.py
        repositories.py
        migrations/
    provenance/
        runs.py
        prompts.py
        audit.py
    models_backends/
        capabilities.py
        registry.py
        router.py
        text.py
        structured.py
        vision.py
        ollama.py
        openai_compatible.py
        llama_cpp.py
        transformers.py
        vllm.py
    embeddings/
        base.py
        sentence_transformers_backend.py
    retrieval/
        indexing.py
        vector_store.py
        sparse.py
        fusion.py
        reranking.py
        evidence_packets.py
    qa/
        service.py
        schemas.py
        citation_validator.py
    extraction/
        service.py
        study_extractor.py
        schemas.py
        chunk_selection.py
    domains/
        base.py
        registry.py
        generic/
        computational_chemistry/
        biomolecular_sciences/
    normalization/
        units.py
        terminology.py
        values.py
    comparison/
        evidence_matrix.py
        exporter.py
    review_generation/
        requests.py
        projects.py
        outline.py
        sections.py
        verification.py
        style_retrieval.py
    multimodal/
        page_rendering.py
        image_extraction.py
        figure_detection.py
        table_regions.py
        vision_service.py
        specialized_tools.py
    jobs/
        models.py
        repository.py
        worker.py
        scheduler.py
    evaluation/
        datasets.py
        metrics.py
        runners.py
        reports.py
    exports/
        comparison.py
        review.py
        citations.py
    gui/
        README.md
```

Responsibilities and migration notes:

- `application/`: new composition layer to remove duplicated construction from `cli.py` and
  `api/app.py`.
- `models/`: can initially wrap or re-export current `domain/` models; long-term, either rename
  `domain/` to `models/` or keep `domain/` as stable core. Do not duplicate both indefinitely.
- `ingestion/`: retain current scanner, deduplicator, and service; add missing `chunking.py`;
  keep parser interfaces here until richer layout extraction justifies `parsing/`.
- `parsing/`: future layout/section/table helpers separate from import orchestration.
- `storage/`: retain SQLAlchemy code; add Alembic migrations and normalized tables.
- `provenance/`: new prompt, run, and audit utilities; current provenance is spread across
  paper metadata and warnings.
- `models_backends/`: better name may be `backends/` or `model_backends/`; it should hold model
  registry/router and runtime adapters. Current `llm/` can be moved or wrapped here.
- `retrieval/`: move Qdrant implementation out of generic `storage/vector_store.py` when hybrid
  retrieval and indexing lifecycle are added.
- `qa/`: new RAG workflow and citation validation.
- `domains/`: new plugin architecture; current `StudyRecord` becomes the generic plugin output.
- `normalization/`: unit and terminology normalization isolated from extraction prompts.
- `review_generation/`: replaces minimal `synthesis/` for controlled review projects.
- `multimodal/`: optional heavy pipeline with graceful skip behavior.
- `jobs/`: local asynchronous execution and progress tracking.
- `evaluation/`: gold datasets and metrics before fine-tuning.
- `exports/`: isolate CSV/JSON/Markdown/Excel/DOCX/LaTeX/BibTeX/PDF export logic.
- `gui/`: GUI source should remain separate from scientific core. If the first GUI is Streamlit,
  this can contain only a small app and documentation; long-term web UI may live outside the
  Python package or under a top-level `frontend/`.

## 7. Data Model Evolution

### Current Schema Assessment

Current ORM classes:

- `PaperORM`
- `DocumentChunkORM`
- `StudyRecordORM`
- `MethodItemORM`
- `QuantitativeResultORM`
- `EvidenceSpanORM`
- `IngestionRunORM`

Current design choices that will make future additions difficult:

- `StudyRecordORM.paper_id` is the primary key. This prevents multiple extraction runs,
  schema versions, model comparisons, and human-reviewed revisions per paper.
- `MethodItemORM.evidence` and `QuantitativeResultORM.evidence` store nested evidence JSON,
  while `EvidenceSpanORM` stores separate evidence rows. This creates duplication and stale-row
  risk.
- `DocumentChunkORM.chunk_id` is not explicitly versioned by parser, chunker, or source hash.
- Parser warnings are stored on `PaperORM`, but no parser settings or run records are linked.
- `IngestionRunORM` lacks status, finished time, per-file records, parser settings, and is not
  used.
- No Alembic migration history exists.
- Flexible JSON is used for `parameters`, warnings, and bounding boxes. Some JSON is acceptable,
  but stable scientific concepts should become normalized fields/tables.

### Required Future Tables

Add Alembic and schema versioning first. Then introduce normalized tables:

- `schema_versions`
- `document_imports`
- `ingestion_runs`
- `paper_versions`
- `document_roles`
- `document_sections`
- `document_chunks`
- `chunk_regions`
- `figures`
- `figure_regions`
- `figure_captions`
- `tables`
- `table_regions`
- `table_cells`
- `model_backends`
- `model_registry`
- `model_capabilities`
- `prompt_templates`
- `prompt_versions`
- `extraction_runs`
- `extraction_records`
- `extraction_field_values`
- `normalized_values`
- `evidence_spans`
- `claim_evidence_links`
- `embedding_models`
- `embedding_runs`
- `chunk_embeddings`
- `vector_collections`
- `review_projects`
- `review_project_versions`
- `review_requests`
- `review_outlines`
- `review_outline_nodes`
- `review_sections`
- `review_paragraphs`
- `review_claims`
- `review_citations`
- `human_revisions`
- `jobs`
- `job_events`
- `exports`

Use JSON only for genuinely flexible metadata:

- Raw parser-specific metadata.
- Raw model responses.
- Backend-specific model details.
- Domain plugin extension payloads when the schema is explicitly versioned.

Do not use one large JSON blob for all scientific extraction fields. Stable fields such as
activation energy, force field, assay concentration, `Kd`, `Ki`, and structural resolution need
queryable normalized representation plus linked raw text and evidence.

## 8. Model Backend And Hardware-Profile Plan

### Interface Sketches

Architectural sketches only; do not add these directly without adapting names to the codebase.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class ModelTask(StrEnum):
    METADATA_EXTRACTION = "metadata_extraction"
    SECTION_CLASSIFICATION = "section_classification"
    STRUCTURED_STUDY_EXTRACTION = "structured_study_extraction"
    QUESTION_ANSWERING = "question_answering"
    REVIEW_PLANNING = "review_planning"
    REVIEW_WRITING = "review_writing"
    VERIFICATION = "verification"
    FIGURE_INTERPRETATION = "figure_interpretation"
    EMBEDDINGS = "embeddings"
    RERANKING = "reranking"
    OCR = "ocr"


class ModelCapabilities(BaseModel):
    model_identifier: str
    backend_type: str
    supported_tasks: set[ModelTask]
    structured_output: bool = False
    vision_support: bool = False
    context_window_tokens: int | None = None
    quantization: str | None = None
    cpu_support: bool = True
    gpu_support: bool = False
    estimated_memory_gb: float | None = None
    batch_support: bool = False
    concurrency_limit: int = 1
    tokenizer: str | None = None
    license_name: str | None = None
    license_url: str | None = None
    local_path: str | None = None
    digest: str | None = None


class TextGenerationBackend(Protocol):
    def generate_text(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str: ...


class StructuredExtractionBackend(Protocol):
    def generate_structured(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
    ) -> BaseModel: ...


class VisionBackend(Protocol):
    def interpret_image(
        self,
        prompt: str,
        image_path: str,
        *,
        model: str,
        schema: type[BaseModel] | None = None,
    ) -> str | BaseModel: ...


class EmbeddingBackend(Protocol):
    def embed(self, texts: list[str], *, model: str, batch_size: int = 32) -> list[list[float]]: ...


class RerankerBackend(Protocol):
    def rerank(
        self,
        query: str,
        passages: list[str],
        *,
        model: str,
        top_k: int,
    ) -> list[tuple[int, float]]: ...


class ExecutionProfile(BaseModel):
    name: str
    text_model: str | None = None
    extraction_model: str | None = None
    synthesis_model: str | None = None
    embedding_model: str | None = None
    reranker_model: str | None = None
    vision_model: str | None = None
    context_limit_tokens: int
    max_chunks_per_task: int
    parallel_jobs: int = 1
    batch_size: int = 8
    device_preference: str = "cpu"
    quantization: str | None = None
    multimodal_enabled: bool = False
    verification_enabled: bool = True


class ModelRouter(Protocol):
    def resolve(self, task: ModelTask, *, profile: str | None = None) -> ModelCapabilities: ...
    def backend_for(self, capabilities: ModelCapabilities) -> object: ...
```

### Routing Policy

Initial routing:

- Static configuration maps task to model identifier and backend.
- Execution profile supplies default choices and limits.
- The router validates model capabilities at task start.
- The router records selected model, backend, digest, quantization, prompt version, and settings
  in run provenance.

Later routing:

- Prefer a stronger model for harder papers, long contexts, or failed verification.
- Use observed memory and latency to adjust chunk limits.
- Use multimodal model only when figures/tables require interpretation and profile permits it.

### Profile Defaults

Example policy, without hard-coding exact models:

| Profile | Target machine | Defaults |
|---|---|---|
| `light` | Laptop/desktop CPU | Small text model, compact embeddings, no reranker, no vision, low chunk limits, one job |
| `balanced` | Moderate workstation | Medium text/extraction model, embeddings, optional reranker, verification on selected tasks |
| `workstation` | High-memory CPU | Larger context, larger extraction model, reranker enabled, higher batch size |
| `high_memory` | Large RAM CPU | Long-context synthesis, broad retrieval, more verification, no GPU assumption |
| `gpu` | Single GPU | GPU-capable extraction/synthesis, embedding batching, GPU concurrency limit |
| `multimodal` | GPU/heavy workstation | Vision-language model, page rendering, figure/table interpretation, OCR fallback |

The GUI should show unsupported capabilities as disabled with concrete reasons, such as
"vision model not configured", "profile disables multimodal processing", or "configured model
requires GPU but no GPU was detected".

## 9. Retrieval And Question-Answering Plan

### Current Qdrant And Sentence Transformers Assessment

Current implementation:

- `SentenceTransformersBackend` loads a configured model and embeds a list of texts.
- `QdrantLocalVectorStore.upsert_chunks()` creates a collection if missing and upserts points.
- `QdrantLocalVectorStore.search()` supports dense search and filters.
- CLI `index` wires repository chunks to embeddings and Qdrant.

Current limitations:

- Indexing is not connected to ingestion.
- Indexing is not versioned by parser, chunker, embedding model, or embedding parameters.
- Idempotency is weak because parser-generated chunk IDs may change across re-ingestion.
- Metadata filters exist in Qdrant search, but no service or API exposes them.
- Reindexing, changed-paper cleanup, deleted-paper cleanup, and multiple embedding models are
  not supported.
- Sparse retrieval, fusion, reranking, evidence packets, and answer generation are missing.

### RAG Workflow

Support scopes:

- One selected paper.
- Multiple selected papers.
- Entire collection.

Workflow:

```text
QuestionAnsweringRequest
-> query validation
-> prompt-injection and policy boundary check
-> optional query decomposition
-> metadata filters by paper/document role/domain/year/section/page
-> sparse keyword retrieval
-> dense semantic retrieval
-> result fusion
-> optional reranking
-> evidence-packet construction
-> answer generation with immutable grounding prompt
-> citation validation
-> insufficient-evidence handling
-> response with model and retrieval provenance
```

Sparse retrieval can initially use SQLite FTS5 over chunk text. Dense retrieval can continue using
Qdrant local mode. Fusion can start with reciprocal rank fusion. Reranking should be optional and
profile-controlled.

### Request And Response Models

```python
class EvidencePacket(BaseModel):
    paper_id: str
    chunk_id: str
    page: int
    section: str | None = None
    quote: str
    retrieval_score: float | None = None
    reranking_score: float | None = None
    source_kind: str = "primary_evidence"
    parser_version: str | None = None
    chunk_version: str | None = None


class QuestionAnsweringRequest(BaseModel):
    question: str
    paper_ids: list[str] | None = None
    scope: str = "selected"  # one_paper, selected_papers, collection
    domain: str | None = None
    max_evidence: int = 12
    require_citations: bool = True
    retrieval_mode: str = "hybrid"
    rerank: bool | None = None
    model_overrides: dict[str, str] = Field(default_factory=dict)


class QuestionAnsweringResponse(BaseModel):
    answer: str
    cited_evidence: list[EvidencePacket]
    warnings: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False
    model_provenance: dict[str, str]
    retrieval_provenance: dict[str, str | int | float]


class Retriever(Protocol):
    def retrieve(self, request: QuestionAnsweringRequest) -> list[EvidencePacket]: ...


class QuestionAnsweringService(Protocol):
    def answer(self, request: QuestionAnsweringRequest) -> QuestionAnsweringResponse: ...
```

### Citation Validation

Citation validation should ensure:

- Every factual answer sentence has at least one cited evidence packet.
- Each citation points to an existing paper/chunk/page.
- Quoted text appears in the cited chunk.
- The answer does not cite style/review-corpus documents as primary evidence.
- If retrieved evidence is insufficient, the model must return an insufficient-evidence response
  instead of speculating.

### GUI Clickable Citations

Each citation should carry:

- `paper_id`
- `chunk_id`
- `page`
- optional `bounding_box`
- quote
- section

The GUI can open the PDF viewer at the page and highlight the chunk or region when coordinates
exist; otherwise it should scroll to extracted text and show the quote.

## 10. Review-Generation Plan

### Instruction Layers

Review generation must use three instruction layers:

1. Immutable scientific grounding rules. These are system-level and cannot be overridden by
   paper text or user instructions.
2. Structured review configuration. This includes review type, selected papers, length,
   language, citation style, and required sections.
3. User-provided custom instructions. These guide emphasis and organization but cannot bypass
   evidence requirements.

Document text must be treated as untrusted input. A paper instruction such as "ignore previous
rules" must remain quoted evidence only, never an instruction.

### Review Models

```python
class ReviewRequest(BaseModel):
    title: str
    topic: str
    selected_paper_ids: list[str]
    review_type: str  # narrative, critical, methodological, state_of_the_art, systematic_style, evidence_summary
    output_language: str = "en"
    target_length: str | None = None
    target_audience: str | None = None
    required_sections: list[str] = Field(default_factory=list)
    focus_topics: list[str] = Field(default_factory=list)
    excluded_topics: list[str] = Field(default_factory=list)
    comparison_criteria: list[str] = Field(default_factory=list)
    citation_style: str = "numeric"
    custom_instructions: str | None = None


class ReviewPlan(BaseModel):
    project_id: str
    request_id: str
    outline_version: int
    sections: list["ReviewSection"]
    evidence_matrix_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ReviewSection(BaseModel):
    section_id: str
    heading: str
    purpose: str
    locked: bool = False
    status: str = "planned"
    target_evidence_ids: list[str] = Field(default_factory=list)
    text: str | None = None
```

### Staged Workflow

Do not implement review generation as a single unrestricted "generate complete review" call.

Required staged workflow:

```text
review request
-> evidence retrieval
-> study selection
-> evidence matrix
-> topic grouping
-> outline generation
-> human outline editing
-> section generation
-> paragraph-level citation attachment
-> citation verification
-> contradiction check
-> terminology consistency check
-> final assembly
-> export
```

User capabilities:

- Regenerate one section without rewriting the full review.
- Regenerate one paragraph.
- Edit an outline.
- Lock approved sections.
- Change selected papers.
- Change emphasis.
- Request alternative organization.
- Inspect supporting evidence.
- Mark text as accepted or rejected.

### Review-Paper Style Learning

Review papers should be stored in a separate style corpus, not mixed with primary factual
evidence. Document classifications:

- `primary_study`
- `review`
- `systematic_review`
- `methods_paper`
- `protocol`
- `supplementary_information`
- `thesis`
- `unknown`

Use review papers for:

- Rhetorical structure.
- Section organization.
- Comparison style.
- Critical discussion style.
- Transitions.
- Limitation framing.

Prevent silent fact import from style documents by:

- Separate vector collections for primary evidence and style examples.
- Distinct `source_kind` in evidence/style packets.
- Prompt language that labels style snippets as non-factual examples.
- Citation validator that rejects style-corpus citations for factual claims.
- Review claims linked only to primary-study evidence unless the claim is explicitly about the
  review literature itself.

Fine-tuning is a later optional phase. Plan only after evaluation:

- Dataset construction.
- Licensing checks.
- Prompt/completion examples.
- LoRA training.
- Evaluation before and after fine-tuning.
- Adapter management.
- Compatibility checks for local runtimes.

### Exports

Support:

- CSV.
- JSON.
- Markdown.
- Excel.
- DOCX.
- LaTeX.
- BibTeX.
- PDF.

Review exports should preserve citation identifiers. Citation rendering should be isolated in
`exports/citations.py` so CSL or BibTeX handling does not leak into review-generation logic.

## 11. Multimodal Plan

The multimodal pipeline should be optional and profile-controlled.

Pipeline:

```text
PDF
-> rendered pages
-> embedded image extraction
-> figure/table region detection
-> caption association
-> nearby text association
-> bounding boxes and page coordinates
-> OCR fallback if needed
-> optional vision-language interpretation
-> optional specialized scientific image adapters
-> human review queue
```

Entity types:

- Ordinary figures.
- Quantitative plots.
- Workflow diagrams.
- Microscopy images.
- Molecular structures.
- Reaction schemes.
- Protein structure figures.
- Spectra.
- Multidimensional free-energy surfaces.
- Sequence alignments.
- Complex tables.

A general vision model must not be treated as a chemically exact parser. It can describe a figure,
identify likely axes, and summarize visible labels, but exact chemistry should be delegated to
specialized tools where available.

Specialized extension points:

- Plot digitization.
- Chemical structure recognition.
- Optical chemical structure recognition.
- Reaction scheme parsing.
- Spectral data extraction.
- Scientific table extraction.

Each multimodal result must store:

- `paper_id`
- page
- figure/table ID
- image path
- bounding box
- caption
- related chunks
- model used
- prompt version
- raw response
- normalized result
- warnings
- human-review status

Light profiles should still extract captions and embedded images when available, but skip visual
interpretation with clear warnings such as "vision processing disabled by profile".

```python
class MultimodalResult(BaseModel):
    paper_id: str
    page: int
    item_id: str
    item_type: str
    image_path: str | None
    bounding_box: dict[str, float] | None
    caption: str | None
    related_chunk_ids: list[str]
    model_identifier: str | None
    prompt_version: str | None
    raw_response: str | None
    normalized_result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    human_review_status: str = "machine_extracted"
```

## 12. Computational-Chemistry Domain Plan

Use a domain plugin rather than expanding `StudyRecord` into a giant universal schema.
Every normalized value must preserve raw reported text and exact evidence.

### Domain Schema Categories

System identity:

- Molecular system.
- Protein or enzyme.
- Ligand.
- Substrate.
- Product.
- Mutation.
- Residue identifiers.
- Protonation states.
- Charge.
- Multiplicity.
- Number of atoms.
- Periodicity.
- Structural source.
- PDB identifier.
- Conformational state.

Electronic structure:

- Method family.
- Density functional.
- Wavefunction method.
- Semiempirical Hamiltonian.
- Basis set.
- Auxiliary basis.
- Pseudopotential.
- Dispersion correction.
- Solvation model.
- Relativistic treatment.
- SCF settings.
- Convergence thresholds.
- Geometry optimization.
- Frequency calculation.
- Excited-state method.
- Single-point calculations.

Molecular dynamics:

- Software.
- Software version.
- Force field.
- Water model.
- Ion parameters.
- Box type.
- Box size.
- Boundary conditions.
- Minimization.
- Equilibration stages.
- Thermostat.
- Barostat.
- Temperature.
- Pressure.
- Timestep.
- Constraints.
- Trajectory duration.
- Number of replicas.
- Sampling interval.
- Enhanced sampling.

QM/MM:

- QM method.
- MM method.
- QM region definition.
- QM atom count.
- Link atoms.
- Embedding method.
- Boundary treatment.
- Electrostatic treatment.
- Reaction coordinate.
- Restraints.
- Umbrella sampling.
- String methods.
- Metadynamics.
- Free-energy method.
- Transition-state search.

Results:

- Activation energy.
- Free-energy barrier.
- Reaction energy.
- Binding energy.
- Interaction energy.
- Electronic descriptors.
- Orbital energies.
- Fukui functions.
- Softness.
- Hardness.
- Local descriptors.
- Uncertainty.
- Replicate variation.
- Convergence analysis.
- Experimental comparison.

Reproducibility:

- Software inputs available.
- Parameter files available.
- Code repository.
- DOI.
- Random seed.
- Hardware.
- Calculation settings.
- Supplementary material.

### Extraction Logic

The computational chemistry plugin should provide:

- Domain-specific chunk selectors for methods, computational details, supporting information,
  tables, captions, and results.
- Controlled vocabularies for method families, basis sets, force fields, water models, sampling
  methods, and software names.
- Validators that distinguish activation energy, free-energy barrier, binding energy, and
  interaction energy.
- Unit normalization for kcal/mol, kJ/mol, eV, Hartree, ns, ps, fs, K, atm, bar, M, mM, angstrom.
- Evidence checks requiring exact pages/quotes for every normalized field.

Suggested value model:

```python
class NormalizedScientificValue(BaseModel):
    raw_value: str
    parsed_numeric_value: float | None = None
    raw_unit: str | None = None
    normalized_unit: str | None = None
    normalized_value: float | None = None
    uncertainty: str | None = None
    conditions: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str]
    normalization_warnings: list[str] = Field(default_factory=list)
```

## 13. Biomolecular-Sciences Domain Plan

### Domain Schema Categories

Biological identity:

- Organism.
- Tissue.
- Cell line.
- Gene.
- Protein.
- Isoform.
- Sequence identifier.
- PDB identifier.
- Mutation.
- Construct.
- Domain.
- Ligand.
- Substrate.
- Inhibitor.
- Cofactor.

Experimental preparation:

- Expression system.
- Vector.
- Plasmid.
- Host.
- Purification method.
- Buffer.
- pH.
- Ionic strength.
- Temperature.
- Storage conditions.
- Sample concentration.

Assays:

- Assay type.
- Substrate concentration.
- Enzyme concentration.
- Detection method.
- Controls.
- Replicates.
- Normalization.
- Kinetic model.
- Statistical analysis.

Structural biology:

- Crystallography.
- Cryo-EM.
- NMR.
- Structure resolution.
- Refinement metrics.
- Missing residues.
- Oligomeric state.
- Conformational state.
- Bound ligands.
- Confidence measures.

Quantitative results:

- `Kd`
- `Ki`
- `IC50`
- `EC50`
- `Km`
- `Vmax`
- `kcat`
- Catalytic efficiency.
- Melting temperature.
- Activity.
- Yield.
- Confidence intervals.
- Standard deviation.
- Standard error.
- p-values.

### Validation Rules

The biomolecular plugin must distinguish related but non-equivalent measurements:

- `Ki` is not interchangeable with `IC50`.
- `Kd` is not interchangeable with `Km`.
- `EC50` and `IC50` require assay context.
- `kcat/Km` is catalytic efficiency, not a rate constant alone.
- Melting temperature requires method and conditions.
- Structural resolution must be associated with structure method and model.
- p-values, confidence intervals, standard deviation, and standard error must retain sample size
  and condition context where available.

### Units, Terminology, And Normalization

Normalization must preserve author terminology and raw scientific text. Every normalized value
should support:

- Raw value.
- Parsed numeric value.
- Raw unit.
- Normalized unit.
- Normalized numeric value.
- Uncertainty.
- Conditions.
- Evidence.
- Normalization warnings.

Support these unit families early:

- Energy units: kcal/mol, kJ/mol, eV, Hartree.
- Time units: fs, ps, ns, us, ms, s, min, h.
- Temperature: K and deg C.
- Pressure: atm, bar, Pa.
- Concentration: M, mM, uM, nM, mass/volume units where applicable.
- Affinity measurements: Kd, Ki, IC50, EC50 with assay context.
- Simulation duration and timestep.
- Structural resolution: angstrom and nm.
- Rate constants and catalytic constants.

Terminology normalization should map aliases without erasing original text:

- molecular dynamics / MD
- quantum mechanics/molecular mechanics / QM/MM
- density functional theory / DFT
- activation energy versus free-energy barrier
- Ki versus IC50
- explicit versus implicit solvent

Introduce a dedicated unit library only behind `normalization/units.py`. `pint` is a reasonable
candidate for general units, but domain-specific validators still need to decide whether a
quantity is scientifically comparable. Keep the dependency optional until Phase 5.

## 14. GUI Plan

The GUI must remain separate from the scientific core and should call API/service boundaries
instead of importing parser/model internals directly.

Initial GUI recommendation: **Streamlit backed by the service layer or API** for fast local MVP
validation. It is practical for import, job progress, paper list, QA, and review configuration,
but will be limited for a polished PDF viewer and complex editing.

Long-term GUI recommendation: **React or Vue frontend with FastAPI backend**, optionally wrapped
as a desktop app. This better supports an integrated PDF viewer, citation highlighting, editable
tables, review outline editing, model settings, and long-running job progress.

GUI areas:

- Library: import files/folders, drag and drop, paper list, duplicate status, parser status,
  document-type classification, extraction status, filters, search.
- Paper view: PDF viewer, page navigation, extracted text, section tree, figures, tables,
  study record, extraction warnings, clickable evidence, editable fields.
- Question answering: selected papers, question box, prompt options, retrieval settings, model
  selection, answer, citations, retrieved chunks, open cited page.
- Comparison: field selection, paper filters, editable table, raw/normalized values, evidence
  inspection, export.
- Review builder: topic, paper selection, review type, language, length, custom prompt, focus
  topics, excluded topics, comparison criteria, outline generation, outline editor, section
  generation, paragraph regeneration, evidence inspector, citation validation, export.
- Settings: execution profile, model backend, model per task, model availability, context size,
  GPU settings, multimodal toggle, storage paths, privacy settings, model download management.

The GUI should never hide scientific warnings. It should show unsupported features as disabled
based on the selected execution profile and model capabilities.

## 15. Provenance And Correction Plan

Every extraction and generated claim should preserve:

- Parser name and version.
- Parser settings.
- Model backend.
- Model identifier.
- Model digest when available.
- Quantization.
- Prompt identifier and version.
- Schema version.
- Extraction timestamp.
- Source chunks.
- Source pages.
- Evidence quotations.
- Generated raw output.
- Validation warnings.
- Human review status.

Use immutable extraction runs or versioned revisions. Human corrections must not silently
overwrite original model output.

Statuses:

- `machine_extracted`
- `human_reviewed`
- `human_corrected`
- `approved`
- `rejected`
- `superseded`

```python
class ExtractionRun(BaseModel):
    run_id: str
    paper_id: str
    domain: str
    schema_version: str
    parser_name: str
    parser_version: str
    parser_settings_hash: str
    backend_type: str
    model_identifier: str
    model_digest: str | None = None
    quantization: str | None = None
    prompt_id: str
    prompt_version: str
    prompt_hash: str
    started_at: datetime
    completed_at: datetime | None = None
    source_chunk_ids: list[str]
    raw_output_ref: str | None = None
    validation_warnings: list[str] = Field(default_factory=list)
    status: str = "machine_extracted"


class HumanRevision(BaseModel):
    revision_id: str
    target_type: str
    target_id: str
    previous_value: dict[str, Any] | None
    revised_value: dict[str, Any]
    rationale: str | None = None
    reviewer: str | None = None
    created_at: datetime
    status: str = "human_corrected"
```

Audit history should allow:

- Comparing two extraction runs for one paper.
- Seeing which prompt/model produced each field.
- Reverting a human correction by creating a superseding revision.
- Reporting unreviewed, corrected, approved, and rejected fields.

## 16. Evaluation Plan

Build the evaluation framework before fine-tuning.

### Parsing Metrics

- Section detection.
- Reading order.
- Page provenance.
- Table-cell recovery.
- Caption association.

### Retrieval Metrics

- Recall@k.
- Precision.
- MRR.
- nDCG.
- Exact-term retrieval.
- Domain-term retrieval.

### Extraction Metrics

- Field precision.
- Field recall.
- Numeric accuracy.
- Unit accuracy.
- Evidence-page accuracy.
- Hallucination rate.
- Missing-value behavior.

### QA Metrics

- Answer support.
- Citation correctness.
- Insufficient-evidence correctness.
- Completeness.

### Review Metrics

- Supported-claim percentage.
- Incorrect-citation rate.
- Contradiction coverage.
- Study coverage.
- Redundancy.
- Terminology consistency.

### Gold Dataset

Create a small licensed, manually annotated corpus:

- 5 to 10 computational chemistry papers.
- 5 to 10 biomolecular sciences papers.
- Include PDFs with normal text, tables, figures, and supplementary-method details.
- Annotate sections, key fields, units, evidence pages, and expected QA answers.
- Keep tests small enough for CI without model downloads; integration benchmarks can be optional.

Benchmark across:

- Light models.
- Medium models.
- Workstation models.
- Prompt versions.
- Embedding models.
- Rerankers.

## 17. Testing Plan

Unit tests must remain runnable without internet, GPU, Ollama, Qdrant, or large model downloads.

Test levels:

- Unit tests: scanners, chunking, selectors, validators, unit normalization, prompt assembly,
  citation validation.
- Repository tests: SQLite round trips, migrations, extraction runs, revisions, stale evidence
  cleanup.
- Parser integration tests: real tiny PDFs for PyMuPDF and optional Docling.
- Ollama integration tests: marked optional, require local server and configured model.
- Vector-store integration tests: marked optional, require Qdrant local extra.
- End-to-end tests: import -> parse -> extract with fake backend -> index with fake embeddings
  -> ask -> compare/export.
- Scientific validation tests: gold corpus metrics.
- GUI tests: Playwright or Streamlit smoke tests, depending on chosen GUI.
- Performance tests: ingestion/indexing/extraction timing, memory, cancellation behavior.

Required immediate tests:

- Import smoke tests for `scireview.cli` and `scireview.api.app`.
- Unit tests for the restored `split_text_for_chunks`.
- Repository tests for `SqlAlchemyPaperRepository` and `SqlAlchemyStudyRepository`.
- Test that evidence spans do not remain stale after re-extraction.
- Test that prompt path resolution works outside the repository root.

Fixtures:

- Synthetic chunks and fake LLMs already exist in `tests/conftest.py`.
- Add synthetic PDF fixtures and a small licensed corpus outside unit-test defaults.

## 18. Security And Privacy Plan

SciReview is local-first, but scientific PDFs are untrusted input.

Security requirements:

- API binds to `127.0.0.1` by default, as current CLI `serve` does.
- Validate import paths; prevent path traversal and arbitrary filesystem reads from GUI/API.
- Enforce file size limits and allowed suffixes.
- Treat malicious PDFs as possible parser crash vectors; isolate parsing in jobs and record errors.
- Disable script execution or HTML rendering from extracted content.
- Escape extracted text in GUI.
- Detect prompt injection inside papers and keep document text below immutable system rules.
- Warn clearly when remote model providers are enabled.
- Warn if model servers bind to non-local interfaces.
- Avoid logging full sensitive paper content by default.
- Make export paths explicit and restricted.
- Support deletion of local data, including PDF copies, parsed text, embeddings, Qdrant
  collections, images, and generated reviews.

Scientific documents must never override grounding or provenance rules. Paper text is data, not
instruction.

## 19. Phased Roadmap

### Phase 0: Baseline Validation

Purpose: verify the existing MVP on real PDFs before expanding it.

- Objectives: restore importability, validate installation, ingest real PDFs, run real parser
  smoke tests, run real Ollama extraction, inspect SQLite rows, export comparison, create baseline
  bug list and test corpus.
- Repository changes: add missing chunking implementation; add import smoke tests; add minimal
  parser smoke fixtures if licensing allows.
- New modules: `src/scireview/ingestion/chunking.py`.
- Modified modules: parser imports only if needed; tests.
- Database changes: none beyond existing schema.
- Configuration changes: document `uv` workflow and optional extras; no Python requirement change.
- API changes: none, except confirming existing routes import and run.
- CLI changes: none, except confirming commands import and run.
- GUI implications: none.
- Tests: `pytest`; import smoke; one manual/optional integration path with a real PDF, PyMuPDF,
  Docling if installed, Ollama if available.
- Completion criteria: CLI/API import cleanly; `finestra init-db`, `ingest`, `extract`, `compare`
  work on one sample PDF; baseline limitations documented.
- Dependencies: none.
- Risks: dependency installation space; Docling behavior differs by version; local Ollama absent.
- Complexity: low.

### Phase 1: Foundation And Provenance

- Objectives: create application composition layer, path-safe prompt packaging, Alembic migrations,
  extraction-run provenance, document roles, configuration cleanup, integration-test scaffolding.
- Repository changes: introduce service/container factories; package prompts; add migrations.
- New modules: `application/container.py`, `application/factories.py`, `provenance/prompts.py`,
  `provenance/runs.py`, Alembic environment.
- Modified modules: `cli.py`, `api/app.py`, `config.py`, `storage/models.py`,
  `storage/repositories.py`, `extraction/service.py`, `study_extractor.py`.
- Database changes: extraction runs, prompt versions, model-run metadata, document type/role,
  schema version table.
- Configuration changes: nested config, project root/data root, prompt IDs.
- API changes: expose structured errors and run IDs for extraction.
- CLI changes: add diagnostics and explicit prompt/model display.
- GUI implications: enables progress/provenance display later.
- Tests: repository migrations, prompt hash tests, extraction-run fake LLM tests.
- Completion criteria: every extraction record links to a run, prompt, model, chunks, and raw output.
- Dependencies: Phase 0.
- Risks: migration from existing SQLite files; avoiding JSON overuse.
- Complexity: medium.

### Phase 2: Model Profiles And Routing

- Objectives: split model interfaces, add capabilities, model registry, hardware profiles,
  static task routing, runtime checks, task-specific models.
- Repository changes: add backend abstractions and router.
- New modules: `model_backends/capabilities.py`, `model_backends/registry.py`,
  `model_backends/router.py`, backend adapters for Ollama and future OpenAI-compatible servers.
- Modified modules: `llm/base.py`, `ollama_backend.py`, `embeddings/base.py`,
  `sentence_transformers_backend.py`, extraction service.
- Database changes: model registry and model capability tables.
- Configuration changes: execution profile config and per-task model overrides.
- API changes: `/models`, `/models/{id}`, `/settings/profile`.
- CLI changes: `models list`, `models inspect`, `profiles list`, `profiles select`,
  `doctor`.
- GUI implications: settings screen can show available models and unsupported capabilities.
- Tests: fake routers, capability validation, profile fallback tests.
- Completion criteria: extraction, embeddings, and synthesis resolve models through router.
- Dependencies: Phase 1.
- Risks: model metadata availability varies by backend.
- Complexity: medium.

### Phase 3: Retrieval And Paper Question Answering

- Objectives: indexing lifecycle, hybrid search, reranking, evidence packets, `/ask`, citations,
  retrieval evaluation.
- Repository changes: move vector store behind retrieval service; add sparse index.
- New modules: `retrieval/indexing.py`, `retrieval/sparse.py`, `retrieval/fusion.py`,
  `retrieval/evidence_packets.py`, `qa/service.py`, `qa/citation_validator.py`.
- Modified modules: `storage/vector_store.py`, `cli.py`, `api/routes`, repositories.
- Database changes: embedding models, embedding runs, chunk embeddings, vector collection metadata,
  chunk version metadata.
- Configuration changes: retrieval settings, top-k, fusion weights, reranker toggle.
- API changes: `/indexes`, `/ask`.
- CLI changes: `index`, `reindex`, `ask`.
- GUI implications: QA screen, citations, retrieved chunk inspector.
- Tests: fake embeddings/vector store, FTS retrieval tests, citation validator, optional Qdrant.
- Completion criteria: answer one paper, selected papers, or collection with validated citations
  and insufficient-evidence behavior.
- Dependencies: Phases 1 and 2.
- Risks: retrieval misses exact scientific terms; chunk provenance quality limits citations.
- Complexity: high.

### Phase 4: Controlled Review Generation

- Objectives: review projects, review requests, evidence selection, outlines, section generation,
  claim validation, revisions, exports.
- Repository changes: replace placeholder synthesis with staged review-generation services.
- New modules: `review_generation/requests.py`, `projects.py`, `outline.py`, `sections.py`,
  `verification.py`, `exports/review.py`, `exports/citations.py`.
- Modified modules: `domain/reviews.py` or new `models/review.py`, API, CLI, storage.
- Database changes: review projects, requests, outlines, sections, paragraphs, claims, citations,
  revisions, exports.
- Configuration changes: review defaults, citation style settings.
- API changes: review project and generation endpoints.
- CLI changes: `review create`, `review outline`, `review section`, `review export`.
- GUI implications: review builder and outline editor.
- Tests: fake model review generation, section locking, citation verification, export tests.
- Completion criteria: generate and revise an outline and one section with verified citations.
- Dependencies: Phase 3.
- Risks: hallucinated synthesis, long-context limits, contradiction detection quality.
- Complexity: high.

### Phase 5: Domain Plugins

- Objectives: generic plugin, computational chemistry plugin, biomolecular sciences plugin,
  unit normalization, validators, domain comparison tables.
- Repository changes: introduce plugin registry and domain schemas.
- New modules: `domains/base.py`, `domains/registry.py`, `domains/generic/`,
  `domains/computational_chemistry/`, `domains/biomolecular_sciences/`,
  `normalization/units.py`, `normalization/terminology.py`.
- Modified modules: extraction service, comparison matrix, QA query expansion.
- Database changes: domain extraction records, normalized values, controlled vocabulary versions.
- Configuration changes: enabled domains and default domain per project/import.
- API changes: domain listing, domain extraction retrieval/correction.
- CLI changes: `domains list`, `extract --domain`, `compare --domain`.
- GUI implications: editable domain-specific study record screens.
- Tests: validators, unit normalization, domain fixture extraction with fake LLM.
- Completion criteria: domain-specific fields extracted with raw value, normalized value, unit,
  conditions, and evidence.
- Dependencies: Phases 1 and 2; benefits from Phase 3.
- Risks: schema explosion; ambiguous scientific terminology.
- Complexity: very high.

### Phase 6: GUI MVP

- Objectives: import, paper browser, question answering, evidence display, review configuration,
  job progress.
- Repository changes: add initial GUI app and API endpoints needed by GUI.
- New modules: `gui/` or top-level frontend; API route modules if not already split.
- Modified modules: API schemas, job services, settings.
- Database changes: none beyond earlier phases.
- Configuration changes: GUI bind host/port, privacy settings.
- API changes: ensure all GUI workflows are backed by stable endpoints.
- CLI changes: `gui` or `serve --with-gui`.
- GUI implications: first usable local application.
- Tests: GUI smoke tests, API contract tests.
- Completion criteria: user can import, inspect, ask, compare, and configure a review from GUI.
- Dependencies: Phases 1, 2, 3; Phase 4 partial for review builder.
- Risks: GUI/backend coupling; large PDF viewer complexity.
- Complexity: high.

### Phase 7: Multimodal Processing

- Objectives: image extraction, page rendering, vision backend, figure interpretation,
  specialized adapters, heavy hardware profiles.
- Repository changes: add multimodal pipeline and optional dependencies.
- New modules: `multimodal/page_rendering.py`, `image_extraction.py`, `figure_detection.py`,
  `vision_service.py`, `specialized_tools.py`.
- Modified modules: parsers, storage, model router, jobs, GUI paper view.
- Database changes: figures, figure regions, tables, table cells, multimodal results.
- Configuration changes: OCR/vision settings, retention policy, profile toggles.
- API changes: figures/tables retrieval, multimodal job endpoints.
- CLI changes: `multimodal extract`, `figures list`.
- GUI implications: figure/table panes and visual evidence.
- Tests: image extraction fixtures, fake vision backend, optional OCR/vision tests.
- Completion criteria: figures/tables have page, region, caption, image path, warnings, and
  optional interpretation.
- Dependencies: Phases 1, 2, jobs foundation.
- Risks: inaccurate figure interpretation; high hardware demand; OCR variability.
- Complexity: very high.

### Phase 8: Review-Style Retrieval

- Objectives: review corpus, style indexing, style retrieval, document-role separation,
  evaluation.
- Repository changes: add style corpus ingestion and separate retrieval.
- New modules: `review_generation/style_retrieval.py`, document role classifiers.
- Modified modules: retrieval/indexing, review generation, storage.
- Database changes: style collections, document roles, style retrieval logs.
- Configuration changes: style corpus paths and allowed document roles.
- API changes: style corpus management endpoints.
- CLI changes: `style ingest`, `style index`, `style search`.
- GUI implications: style-source settings and review organization suggestions.
- Tests: ensure style facts cannot be cited as primary evidence.
- Completion criteria: review generation uses style examples only for organization/rhetoric.
- Dependencies: Phases 3 and 4.
- Risks: fact leakage from review papers; copyright restrictions.
- Complexity: medium-high.

### Phase 9: Optional Fine-Tuning

- Objectives: dataset builder, human ratings, LoRA, adapter registry, benchmark comparison,
  licensing controls.
- Repository changes: add training dataset and adapter management modules.
- New modules: `training/datasets.py`, `training/lora.py`, `training/adapters.py`.
- Modified modules: model registry, evaluation.
- Database changes: training datasets, license records, adapter registry, evaluation runs.
- Configuration changes: training profiles and local runtime compatibility.
- API changes: optional training/evaluation endpoints, disabled by default.
- CLI changes: `train dataset`, `train lora`, `adapters list`.
- GUI implications: advanced settings only.
- Tests: dataset validation and licensing guardrails; no training in unit tests.
- Completion criteria: fine-tuned adapter beats baseline on held-out evaluation without losing
  citation discipline.
- Dependencies: Evaluation framework, Phase 8.
- Risks: copyrighted review text, overfitting, adapter/runtime incompatibility.
- Complexity: very high.

## 20. File-Level Implementation Map

| Current file | Future action |
|---|---|
| `src/scireview/cli.py` | Keep Typer entrypoint, but delegate construction to `application/container.py`; add diagnostics, model, retrieval, review, eval, GUI commands |
| `src/scireview/api/app.py` | Split route modules; use application container; make long operations job-backed |
| `src/scireview/config.py` | Convert flat settings to nested typed config; add root path resolver; add execution profiles |
| `config/prompts/extract_study.txt` | Package/version as prompt template; persist hash in extraction runs |
| `config/prompts/synthesize_comparison.txt` | Either wire into review generation or remove until needed; version if retained |
| `src/scireview/domain/documents.py` | Extend or migrate to document roles, sections, regions, figures, tables |
| `src/scireview/domain/evidence.py` | Add region/run/claim linkage; normalize persistence |
| `src/scireview/domain/studies.py` | Keep as generic schema; do not expand into all domain fields |
| `src/scireview/domain/reviews.py` | Replace minimal review objects with project/outline/section/claim models |
| `src/scireview/ingestion/scanner.py` | Add file validation limits and import source records |
| `src/scireview/ingestion/deduplicator.py` | Add repository-aware duplicate/version policy |
| `src/scireview/ingestion/service.py` | Add job progress, per-file errors, persistent ingestion runs |
| `src/scireview/ingestion/docling_parser.py` | Restore importability; then use Docling layout/page/region data instead of text-only export |
| `src/scireview/ingestion/pymupdf_parser.py` | Restore importability; add region extraction and optional image extraction |
| `src/scireview/storage/models.py` | Add Alembic migrations and normalized provenance/review/domain tables |
| `src/scireview/storage/repositories.py` | Split repositories by aggregate; add run-aware and revision-aware methods |
| `src/scireview/storage/vector_store.py` | Move behind retrieval package; add collection/version management |
| `src/scireview/llm/base.py` | Split into task-specific interfaces |
| `src/scireview/llm/ollama_backend.py` | Keep as one backend adapter; add model metadata and structured-output handling through router |
| `src/scireview/embeddings/base.py` | Keep protocol but include model/batch/provenance parameters |
| `src/scireview/embeddings/sentence_transformers_backend.py` | Add batching, device config, offline/cache controls |
| `src/scireview/extraction/study_extractor.py` | Move chunk selection out; add domain plugin prompts and run provenance |
| `src/scireview/extraction/service.py` | Store extraction runs, raw outputs, validation warnings, and model provenance |
| `src/scireview/comparison/evidence_matrix.py` | Keep generic matrix; allow domain plugins to supply columns |
| `src/scireview/comparison/exporter.py` | Move richer export handling to `exports/` while retaining compatibility |
| `src/scireview/synthesis/*` | Treat as placeholder; supersede with `review_generation/` |
| `tests/*` | Keep current unit coverage; add import smoke, repository, parser, retrieval, QA, review, and optional integration tests |
| `pyproject.toml` | Later add optional dependency groups and Alembic/GUI/eval deps; do not change Python requirement until approved |
| `Makefile` | Later switch install examples to `uv`; avoid destructive clean beyond caches |

## 21. API Plan

| Method | Path | Request model | Response model | Behavior | Main service |
|---|---|---|---|---|---|
| `POST` | `/imports/files` | multipart files + options | `JobResponse` | async | Import/Ingestion service |
| `POST` | `/imports/folder` | `ImportFolderRequest` | `JobResponse` | async | Ingestion service |
| `GET` | `/jobs` | query filters | `JobSummaryList` | sync | Job repository |
| `GET` | `/jobs/{job_id}` | none | `JobDetail` | sync | Job repository |
| `GET` | `/jobs/{job_id}/events` | none | `JobEventList` | sync/stream later | Job repository |
| `POST` | `/jobs/{job_id}/cancel` | none | `JobDetail` | sync request, async effect | Job service |
| `GET` | `/papers` | filters | `PaperListResponse` | sync | Paper repository |
| `GET` | `/papers/{paper_id}` | none | `PaperDetailResponse` | sync | Paper repository |
| `GET` | `/papers/{paper_id}/chunks` | filters | `ChunkListResponse` | sync | Paper repository |
| `GET` | `/papers/{paper_id}/figures` | filters | `FigureListResponse` | sync | Multimodal repository |
| `GET` | `/papers/{paper_id}/tables` | filters | `TableListResponse` | sync | Table repository |
| `GET` | `/papers/{paper_id}/extractions` | domain/run filters | `ExtractionListResponse` | sync | Extraction repository |
| `GET` | `/extractions/{record_id}` | none | `ExtractionRecordResponse` | sync | Extraction repository |
| `POST` | `/extractions/{record_id}/corrections` | `CorrectionRequest` | `HumanRevisionResponse` | sync | Human revision service |
| `POST` | `/indexes` | `IndexRequest` | `JobResponse` | async | Indexing service |
| `POST` | `/ask` | `QuestionAnsweringRequest` | `QuestionAnsweringResponse` | sync initially, async for long tasks | QA service |
| `GET` | `/models` | filters | `ModelListResponse` | sync | Model registry |
| `GET` | `/models/{model_id}` | none | `ModelDetailResponse` | sync | Model registry |
| `GET` | `/profiles` | none | `ExecutionProfileList` | sync | Settings/profile service |
| `PUT` | `/profiles/active` | `SelectProfileRequest` | `ExecutionProfile` | sync | Settings/profile service |
| `POST` | `/reviews` | `CreateReviewProjectRequest` | `ReviewProjectResponse` | sync | Review project service |
| `POST` | `/reviews/{project_id}/outline` | `GenerateOutlineRequest` | `JobResponse` | async | Review generation service |
| `PUT` | `/reviews/{project_id}/outline` | `UpdateOutlineRequest` | `ReviewPlan` | sync | Review project service |
| `POST` | `/reviews/{project_id}/sections/{section_id}/generate` | `GenerateSectionRequest` | `JobResponse` | async | Review generation service |
| `POST` | `/reviews/{project_id}/paragraphs/{paragraph_id}/regenerate` | `RegenerateParagraphRequest` | `JobResponse` | async | Review generation service |
| `POST` | `/reviews/{project_id}/validate-citations` | none/options | `CitationValidationResponse` | async or sync | Citation validator |
| `POST` | `/reviews/{project_id}/export` | `ExportReviewRequest` | `JobResponse` | async | Export service |

Existing routes can remain during transition but should be versioned or deprecated once richer
schemas exist.

## 22. CLI Plan

Future commands:

```text
scireview doctor
scireview init-db
scireview migrate
scireview models list
scireview models inspect MODEL_ID
scireview profiles list
scireview profiles select PROFILE
scireview ingest PATH [--recursive] [--force] [--domain DOMAIN]
scireview extract [--paper-id ID] [--domain DOMAIN] [--model MODEL]
scireview index [--paper-id ID] [--embedding-model MODEL] [--rebuild]
scireview ask "QUESTION" [--paper-id ID ...] [--scope collection]
scireview review create --title TITLE --topic TOPIC --paper-id ID ...
scireview review outline PROJECT_ID
scireview review section PROJECT_ID SECTION_ID
scireview review export PROJECT_ID --format docx
scireview eval run --suite SUITE
scireview serve [--host 127.0.0.1] [--port 8000]
scireview gui
```

Diagnostics should report:

- Python version.
- Installed optional extras.
- SQLite path and migration status.
- Prompt/template availability.
- Parser availability.
- Ollama/model server reachability.
- Model registry and profile validity.
- Qdrant storage status.
- GPU detection, when relevant.

## 23. Risks

- Poor PDF parsing: scientific PDFs, supplements, multi-column layouts, scanned pages, and tables
  can break text order and provenance.
- Hallucinated extraction: LLMs can fill missing methods/results unless prompts, schemas, and
  validators enforce absence and evidence.
- Incorrect page provenance: current Docling parser assigns page 1 to all chunks; citations can
  be misleading until fixed.
- Context-window limitations: long methods sections and supplements may exceed light-model limits.
- Small-model limitations: local light models may fail nuanced domain extraction.
- Large-model hardware limits: model loading can exceed RAM/VRAM, especially with multimodal
  models.
- Model license restrictions: model and embedding licenses must be recorded before distribution
  or fine-tuning.
- Prompt injection from PDFs: document text must never override immutable system rules.
- Inaccurate figure interpretation: vision models may misread plots, axes, symbols, structures,
  or spectra.
- Chemical-structure recognition errors: OCSR and reaction parsing require specialized tools and
  human review.
- Schema explosion: computational chemistry and biomolecular domains are broad; plugin
  composition is safer than one universal schema.
- Database migration complexity: existing primary-key choices and JSON evidence duplication need
  careful migration.
- Long-running task failures: ingestion, OCR, indexing, extraction, and review generation need
  resumable jobs.
- GUI/backend coupling: a GUI that imports internals directly will slow backend evolution.
- Scientific validation: correctness must be measured against annotated corpora before users rely
  on synthesis.
- Copyrighted review text used for fine-tuning: licensing must be checked before any training
  dataset is built.

## 24. Architectural Decisions Requiring User Approval

| Decision | Options | Recommendation | Rationale | Consequences |
|---|---|---|---|---|
| Python minimum | Keep 3.11; raise to 3.12; support 3.11-3.12 | Keep 3.11 for now | Current code and Debian environment support 3.11 | Broader compatibility; must validate dependencies |
| Product naming | SciReview; Finestra; dual names | Decide before public release | Current repo uses Finestra while request says SciReview | Renaming affects CLI, docs, env vars, data paths |
| Initial GUI framework | Streamlit; Gradio; Qt/PySide; React/Vue | Streamlit for MVP, React/Vue long-term | Fast validation now; richer PDF/editor later | Possible rewrite from MVP GUI to mature GUI |
| Initial additional backend | llama.cpp server; OpenAI-compatible local; Transformers; vLLM | OpenAI-compatible local server after Ollama | Common API surface covers LM Studio, llama.cpp-compatible servers, vLLM variants | Need capability probing and schema-output differences |
| Background jobs | In-process worker; thread/process executor; SQLite job loop; Celery/RQ | SQLite job table plus in-process worker | Simple local-first implementation with future evolution | Not distributed initially |
| Hybrid search technology | SQLite FTS5 + Qdrant; external search engine; Qdrant only | SQLite FTS5 + Qdrant | Local, minimal dependencies, supports exact scientific terms | Need fusion and index lifecycle |
| Relational database | SQLite only; optional PostgreSQL later | SQLite only through Phase 6 | Local-first and simpler deployment | Must design migrations carefully for SQLite limits |
| Domain plugin selection | Per project; per paper; automatic classifier; manual override | Manual per project/paper with classifier suggestion | Avoid wrong domain schemas silently | GUI must expose domain selection |
| Review project versioning | Mutable only; immutable versions; Git-like snapshots | Immutable versions with editable latest draft | Scientific traceability and rollback | More tables and UI complexity |
| Primary/review vector collections | Shared; separate collections | Separate primary evidence and style collections | Prevent fact leakage from style documents | More index management |
| Page image retention | Keep all; keep generated on demand; user-configurable | User-configurable with default cache cleanup | Images consume disk and may contain sensitive content | GUI may re-render pages when cache is absent |
| Raw LLM output storage | Store always; store optionally; never store | Store by default with privacy setting | Reproducibility and audit require raw outputs | Sensitive text may be stored; deletion controls needed |
| Remote providers | Disallow; allow opt-in | Disabled by default, explicit opt-in | Local-first privacy | Extra warning/config burden |
| Fine-tuning corpus | Use all imported reviews; curated licensed corpus only | Curated licensed corpus only | Avoid copyright and contamination | Slower but safer |

## 25. Recommended First Implementation Milestone

Recommended first milestone: **Phase 0 baseline validation and importability repair**.

Scope:

1. Restore `src/scireview/ingestion/chunking.py` with deterministic overlap chunking.
2. Add import smoke tests for `scireview.cli` and `scireview.api.app`.
3. Run unit tests in an isolated `uv` Python 3.11 environment.
4. Ingest one small real PDF with PyMuPDF fallback and Docling if installed.
5. Run one real Ollama extraction if Ollama and a configured model are available.
6. Inspect SQLite rows for papers, chunks, study records, methods, results, and evidence spans.
7. Export a comparison table.
8. Record a baseline bug list before adding new architecture.

Completion criteria:

- The advertised CLI/API workflows import and execute.
- Current features are verified on at least one real PDF.
- Known limitations are documented as issues.
- No GUI, RAG, review generation, multimodal work, or schema expansion starts until the baseline
  is reproducible.

