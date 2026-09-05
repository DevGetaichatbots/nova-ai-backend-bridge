# backend/

## Responsibility
FastAPI-based Nova Insights RAG agent for construction schedule comparison and predictive analysis. Provides an LLM-powered Q&A platform over project-management data (MPP, MSPDI, PDF, CSV, XLSX) with a multi-format ingestion pipeline, pgvector-backed retrieval, and self-contained HTML dashboard rendering with PDF export via Chromium.

## Top-Level System Entry Points
- `backend/main.py`: Empty placeholder; the actual FastAPI app lives at `src/main.py` and is served via `gunicorn src.main:app` (see `Dockerfile` line 35).
- `backend/pyproject.toml` / `backend/requirements.txt`: Define runtime dependencies — FastAPI, LangChain, OpenAI/Azure OpenAI, Supabase/pgvector, MPXJ/JPype, Playwright, openpyxl, tiktoken, uvicorn/gunicorn.
- `backend/Dockerfile`: Multi-stage container building on `eclipse-temurin:17-jdk`; installs Python 3.11, pip-installs dependencies, pre-installs Chromium via Playwright (so HTML→PDF works at runtime without install commands), and runs `gunicorn src.main:app` on port 8000.
- `backend/replit.nix`: Declares JDK 17 as a system dependency for Replit (required by MPXJ JVM bridge via JPype).

## Design
**Service architecture**: A FastAPI application (`src/main.py`) with three orthogonal subsystems — the RAG agent runtime (`src/`), the ingestion ETL pipeline (`ingestion/`), and static configuration (`config/`). The app follows an **agent + retriever** pattern: a `VectorStoreManager` (per-session pgvector tables, two storage modes — embedding-based via Azure OpenAI for PDFs, zero-embedding fetch-all for structured formats) feeds context into one of several LLM agents (`rag_agent` for comparison, `predictive_agent` for single-schedule analysis). The ingestion pipeline uses a **registry + plugin** design with five self-registering format extractors (CSV, Excel, PDF, MPP, MSPDI) chained through detection, extraction, heuristic+AI column recognition, NUSF normalization, and rule-based validation.

**Parallel module tracks**: Three parallel directories under `src/` coexist — `src/` (production runtime), `src/experimental/` (five generations of comparison agents with deterministic NUSF engine and progressive HTML formatters, explicitly excluded from default imports), and `src/version_1_0/` (legacy V1 dashboard rendering with adapter/formatter/localization pattern). The `/v2` ingestion routes (`ingestion/routes/`) are injected with dependencies at mount time to keep the ingestion package import-free of `src/`.

## Data & Control Flow
1. **HTTP query path**: Request → FastAPI route → `rag_agent.query()` or `predictive_agent.analyze()` → LLM call (Azure OpenAI `gpt-4.1`) with retrieved chunks from pgvector → structured markdown/JSON → HTML formatter (`html_formatter.py`, `predictive_html_formatter.py`, or dashboard formatters) → HTTP response. PDF variant: HTML → Playwright Chromium → PDF bytes.
2. **File upload / ingestion path**: Uploaded file → format detection (MIME/header heuristics) → `ExtractorRegistry` dispatches to format-specific extractor → `HeuristicRecognizer` maps columns to NUSF roles (with `AIFallbackRecognizer` for low-confidence cases) → `NormalizationEngine` produces `NormalizedSchedule` + compact CSV chunks → `ValidationEngine` runs rules 101–104 → chunks stored via `VectorStoreManager.create_store_from_chunks()` → progress tracked in in-memory dicts pollable via dedicated GET endpoints.
3. **Experimental v5 hybrid path** (when NUSF data is available): deterministic pure-Python comparison via `nusf_compare_engine` (nearest-date greedy pairing, progress/variance/PONR computation) → compact LLM enrichment packet (~4K tokens) → merge deterministic + LLM results → v5 graph HTML formatter with 4D client-side filter.

## Integration Points
- **Supabase PostgreSQL + pgvector**: `database.py` manages connection pool (`ThreadedConnectionPool` min=2, max=8), table lifecycle, embedding search, and session/chat memory persistence.
- **Azure OpenAI**: Embeddings (`text-embedding-3-small`, 1536d) and chat (`gpt-4.1`) via `AzureOpenAI` client configured through `Settings` pydantic model.
- **Azure Document Intelligence**: `AzureDocumentIntelligence` client for prebuilt-layout OCR on PDFs (`pdf.py` extractor, `azure_ocr.py` in src).
- **Playwright / Chromium**: Headless HTML-to-PDF rendering (`pdf_export.py`), baked into Docker image at build time.
- **MPXJ / JPype**: Java-based `.mpp` parsing via JVM bridge (`jvm_init.py`, `mpp.py` extractor).
- **Internal package boundaries**: `src/` (runtime agents, vector store, formatters), `ingestion/` (ETL pipeline with zero `src/` imports), `config/mappings/` (YAML column-mapping files consumed by normalization).

## Sub-Module Map
| Directory | Responsibility Summary | Detailed Map |
|---|---|---|
| `src/` | FastAPI app, RAG agents, vector store, LLM orchestration, HTML/PDF rendering | [codemap](src/codemap.md) |
| `src/experimental/` | Five generations of comparison agents (v2–v5) with deterministic NUSF engine and progressive dashboards; reference/archive, not production by default | [codemap](src/experimental/codemap.md) |
| `src/version_1_0/` | Legacy V1 dashboard pipeline: adapter + formatter + localization; superseded by newer dashboard versions | [codemap](src/version_1_0/codemap.md) |
| `ingestion/` | End-to-end ETL pipeline for schedule files: format detection, plugin extractors, heuristic+AI column recognition, NUSF normalization, rule-based validation | [codemap](ingestion/codemap.md) |
| `ingestion/models/` | Pydantic `BaseModel` domain schema: `NormalizedSchedule`, `Activity`, `Relationship`, `ValidationIssue`, `Provenance`, enums | [codemap](ingestion/models/codemap.md) |
| `ingestion/extractors/` | Self-registering plugin extractors (CSV, XLSX, PDF, MPP, MSPDI) via `BaseExtractor` ABC + `ExtractorRegistry` | [codemap](ingestion/extractors/codemap.md) |
| `ingestion/recognition/` | Column-header-to-NUSF-role mapping: heuristic matching (Jaro-Winkler, token map) with Azure OpenAI fallback | [codemap](ingestion/recognition/codemap.md) |
| `ingestion/normalization/` | Transforms extracted rows into `NormalizedSchedule` via `FieldMapper`, date/duration parsing, relationship builder; also emits compact CSV chunks for LLM consumption | [codemap](ingestion/normalization/codemap.md) |
| `ingestion/validation/` | Rule-based structural/logical validation (rules 101–104) using collector pattern; issues are warnings, not blocks | [codemap](ingestion/validation/codemap.md) |
| `ingestion/routes/` | `/v2` FastAPI `APIRouter` with 7 endpoints; dependencies injected at mount time; background tasks with progress polling | [codemap](ingestion/routes/codemap.md) |
| `config/` | Static YAML column-mapping profiles (`csv.yaml`, `pdf.yaml`) for Danish-to-semantic field names; consumed by normalization `FieldMapper` | [codemap](config/codemap.md) |
| `config/mappings/` | Per-format YAML lookup tables (13 key-value pairs each) mapping semantic roles to source-specific column headers | [codemap](config/mappings/codemap.md) |
