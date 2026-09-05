# backend/ingestion/routes/

## Responsibility
FastAPI `APIRouter` providing the `/v2/` HTTP endpoints for the NUSF (Nova Universal Schedule Format) ingestion pipeline. All downstream dependencies (`vector_store_manager`, `save_session_metadata`, `rag_agent`, etc.) are injected at configuration time via `configure()` before the router is mounted, keeping the `ingestion/` package fully self-contained with zero `src/` imports.

## Design
A single module (`ingestion.py`) defines a module-level `router = APIRouter(tags=["v2-nusf"])` with five routes. Dependencies are encapsulated in the `RouterDependencies` dataclass and stored in the global `_deps` variable via a `configure()` function; `_require_deps()` guards against unconfigured usage with a `RuntimeError`. CPU-bound pipeline work runs off the event loop through `ThreadPoolExecutor(max_workers=4)`. Long-running upload operations are dispatched as background `asyncio.create_task()` coroutines that mutate in-memory progress dicts (`_v2_upload_progress`) under `threading.Lock`. Stale progress entries are cleaned up by daemon threads after a TTL (120-600 s). File-type validation uses a built-in `_ALLOWED_EXTENSIONS` set (`{.pdf, .csv, .xlsx, .mpp, .xml}`). The `__init__.py` re-exports `router` and `__all__`.

## Data & Control Flow
1. HTTP request lands on a route handler (e.g. `v2_upload_schedules()`).
2. The handler validates the file extension, reads file bytes, and returns an immediate response with a tracking ID (`upload_id` / `analysis_id`).
3. A background coroutine calls `IngestionPipeline.run_from_bytes(file_bytes, filename)` in the executor thread pool.
4. The normalized `Schedule` object is converted to compact chunks via `to_nusf_chunks()` from `ingestion.normalization.engine`.
5. Chunks are persisted to the vector DB via the injected `deps.vector_store_manager.create_store_from_chunks()`.
6. For `/upload`, both schedules are processed concurrently (`asyncio.gather`) and `deps.save_session_metadata()` records the pairing.
7. Progress is written to the in-memory dict at each stage and served by the polling endpoint (`/upload/progress/{upload_id}`).

## Integration Points
- **`ingestion.pipeline.IngestionPipeline`** (`ingestion/pipeline.py`) — core ingestion runner called from every route except `/health`.
- **`ingestion.normalization.engine.to_nusf_chunks`** — converts `Schedule` objects into chunk dicts for vector storage.
- **`ingestion.extractors.registry.ExtractorRegistry`** — queried only by `GET /health` to list registered extractors.
- **Injected dependencies** (set via `configure(RouterDependencies(...))` from `src/main.py`):
  - `vector_store_manager` — persists chunks to the vector database.
  - `save_session_metadata` — records session file-pair metadata.
  - `rag_agent` — answers comparison queries against stored sessions.
  - `format_comparison_html` — renders comparison query responses as HTML.
  - `get_session_metadata` — retrieves stored session metadata for queries.

## Public Surface
- **`router`** (`APIRouter`) — The FastAPI router exported from `__init__.py`. Mounted at `/v2` prefix.
- **`configure(deps: RouterDependencies) → None`** — Dependency injection entry point; must be called before the router is used.
- **`RouterDependencies`** (`@dataclass`) — Container for all injected downstream services and callables.
- **`GET /health`** (`v2_health`) — Returns pipeline status, available extractors, and dependency configuration state.
- **`POST /inspect`** (`v2_inspect_file`) — Runs a file through the NUSF pipeline and returns metadata + validation issues without persisting anything.
- **`POST /upload`** (`v2_upload_schedules`) — Accepts two schedule files and session IDs, runs both through the pipeline, stores chunks, and returns an `upload_id` for progress polling.
- **`GET /upload/progress/{upload_id}`** (`v2_get_upload_progress`) — Returns the current progress dict for an upload, or 404 if not found.
- **`POST /query`** (`v2_query_agent`) — Runs a comparison query against two previously ingested NUSF sessions via `rag_agent.query()`, with optional HTML formatting.
