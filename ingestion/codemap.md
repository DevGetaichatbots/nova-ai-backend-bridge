# backend/ingestion/

## Responsibility
End-to-end ingestion pipeline for construction project management schedule data, from file detection through extraction, column-header recognition, normalization into the NUSF domain model, and rule-based validation. The pipeline accepts PDF, CSV, XLSX, MPP, and MSPDI formats and produces a `NormalizedSchedule` plus compact CSV chunks consumed by downstream LLM agents and vector stores.

## Design
**Pipeline orchestrator** (`IngestionPipeline` in `pipeline.py`) chains five stages via step-wise method calls in `run_from_bytes()`. Each stage is a dedicated class injected in `__init__`: `FormatDetector`, `ExtractorRegistry` dispatches to a self-registering plugin extractor, `HeuristicRecognizer` (with `AIFallbackRecognizer` for low-confidence cases), `NormalizationEngine`, and `ValidationEngine`. The extractors subdirectory follows a **Registry + Plugin** pattern — each format module (`csv.py`, `excel.py`, `pdf.py`, `mpp.py`, `mspdi.py`) registers itself with `ExtractorRegistry` at import time via a side-effecting import triggered in `pipeline.py` lines 29–33. Routes are exposed as a FastAPI `APIRouter` in `routes/ingestion.py`, configured via dependency injection at mount time to keep the ingestion package fully decoupled from `src/`.

## Data & Control Flow
1. **Detect** — `FormatDetector.detect_from_bytes()` (in `detector.py`) identifies MIME type and source system via `python-magic` or binary-header heuristics. Unsupported formats (`XLS_LEGACY`, `UNKNOWN`) raise `PipelineError`.
2. **Extract** — `ExtractorRegistry.get(source_system)` retrieves the appropriate extractor plugin (`extractors/`). Each extractor returns a dict with `headers` (column names) and `rows` (data).
3. **Recognize** — `HeuristicRecognizer.recognize(headers)` (in `recognition/heuristics.py`) maps extracted column names to NUSF roles. If critical fields are missing (`ai_needed=True`), `AIFallbackRecognizer.recognize()` (`recognition/ai_fallback.py`) supplements the mapping via LLM inference.
4. **Normalize** — `NormalizationEngine.normalize()` (in `normalization/engine.py`) transforms extracted rows + recognition map into a `NormalizedSchedule` domain object. Separately, `to_compact_csv_chunks()` produces raw table chunks for LLM agents even when structured normalization yields zero activities.
5. **Validate** — `ValidationEngine.validate()` (in `validation/engine.py`) runs four rules (101–104) against the schedule; error-level issues cause pipeline rejection, warnings are attached non-blocking.
6. **Return** — `(NormalizedSchedule, compact_csv_chunks)` tuple is returned to the route handler, which either stores results (upload flow) or returns them as a JSON inspection.

## Integration Points
- **`backend/src/`** — Downstream services (`vector_store_manager`, `predictive_agent`, `rag_agent`, `save_session_metadata`) are injected into the router at mount time via `RouterDependencies` (`routes/ingestion.py` line 62), keeping `ingestion/` free of `src/` imports.
- **`backend/config/mappings/`** — Heuristic-to-role mapping definitions consumed by `HeuristicRecognizer` in `recognition/heuristics.py`.
- **FastAPI app** — The router is mounted in `src/main.py` via `app.include_router(router, prefix="/v2")` after calling `configure(RouterDependencies(...))` (`routes/ingestion.py` lines 79–83).
- **`ingestion.models.nusf`** — Shared Pydantic domain schema consumed by all sub-modules (normalization, validation, routes).

## Sub-Module Map

| Subdirectory | Responsibility Summary | Detailed Map |
|---|---|---|
| `extractors/` | Self-registering plugin extractors for CSV, Excel, PDF, MPP, MSPDI formats dispatched via `ExtractorRegistry`. | [codemap](extractors/codemap.md) |
| `recognition/` | Column-header-to-NUSF-role mapping using heuristic matching with an AI LLM fallback for low-confidence cases. | [codemap](recognition/codemap.md) |
| `normalization/` | Transforms extracted rows and recognition maps into `NormalizedSchedule` domain entities; also produces compact CSV chunks for LLM consumption. | [codemap](normalization/codemap.md) |
| `validation/` | Rule-based structural/logical validation (rules 101–104) producing `ValidationIssue` objects attached to the schedule. | [codemap](validation/codemap.md) |
| `models/` | Pydantic `BaseModel` domain schema: `NormalizedSchedule`, `Activity`, `Relationship`, `ValidationIssue`, `ScheduleMetadata`, `Provenance`, `DependencyType`, `ActivityType`. | [codemap](models/codemap.md) |
| `routes/` | FastAPI `APIRouter` exposing `/v2/health`, `/v2/inspect`, `/v2/upload`, `/v2/upload/progress/{id}`, and `/v2/query` endpoints. Deps injected at mount time via `RouterDependencies`. | [codemap](routes/codemap.md) |
