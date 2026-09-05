# backend/src/

## Responsibility
FastAPI application entry point and core runtime for the RAG Agent SaaS — a construction schedule comparison and predictive analysis platform. Owns HTTP routing, agent orchestration, vector store lifecycle, document ingestion (OCR/CSV/MPP), and HTML/PDF report rendering.

## Design
**FastAPI app factory** (`main.py`, lines 422–427) with `lifespan` startup handler that boots a JVM for MPXJ (`jvm_init.start_jvm_if_needed`) and initialises pgvector + chat-memory tables. A **`ThreadPoolExecutor`** (`_query_executor`, line 22) runs blocking OCR/embedding/LLM work off the event loop. Uploads and predictive analyses use **background tasks** with progress dictionaries (`_upload_progress`, `_predictive_progress`) polled via dedicated GET endpoints.

**RAG retrieval** is handled by `VectorStoreManager` (`vector_store.py`), which creates per-session pgvector tables, optionally generates embeddings via Azure OpenAI, and exposes `search` / `search_multiple_stores` / `fetch_all_from_stores`. Two storage modes exist: **embedding-based** (PDF → OCR → chunk → embed → store) and **zero-embedding** (CSV/MPP/MSPDI → chunk → store directly with a zero vector, relying on fetch-all retrieval).

**Agent system**: `agent.py` carries a ~900-line system prompt (`SYSTEM_PROMPT_BASE`) that defines the ten-section output format (DATA_TRUST → PROJECT_HEALTH), five auto-detected document formats (MS Project, Detailtidsplan, Unstructured, Plandisc, Mixed), and adaptive column mapping. The `rag_agent` object (defined in `agent.py` past the visible excerpt) handles comparison queries against two vector stores. `predictive_agent.py` defines a strict JSON schema (`NOVA_INSIGHT_SCHEMA`, 377 lines) and a detailed system prompt for single-schedule predictive analysis with forcing assessment. Two HTML formatters produce the final rendered output: `html_formatter.py` (comparison) and `predictive_html_formatter.py` (structured predictive). PDF export delegates to headless Chromium via Playwright (`pdf_export.py`).

## Data & Control Flow
1. **Upload flow**: `POST /upload` → reads two PDF/CSV/MPP/XML files → spawns background task → parallel OCR/extraction via `process_pdf_binary` / extractors → `VectorStoreManager.create_store_from_chunks` → pgvector tables → session metadata saved → progress pollable at `GET /upload/progress/{id}`.
2. **Comparison query flow**: `POST /query` → `rag_agent.query()` fetches all chunks from both vector stores via `fetch_all_from_stores` → LLM call with system prompt + retrieved context → structured markdown → `format_response_as_html` → HTML response.
3. **Predictive flow**: `POST /predictive` → single-file ingestion (OCR/CSV/MPP/MSPDI) → context built via `_build_predictive_context` → `predictive_agent.analyze()` → structured JSON → `format_predictive_as_html` → HTML response.
4. **PDF export**: `POST /export/pdf` → receives pre-rendered HTML → headless Chromium via Playwright renders to PDF bytes → returned as attachment.

## Integration Points
- **Database**: `database.py` → Supabase PostgreSQL with pgvector extension. Connection pool (`ThreadedConnectionPool`, min=2, max=8). Used by `vector_store.py` and `agent.py`.
- **Azure OpenAI**: `config.py` + `embeddings.py` → embedding model (`text-embedding-3-small`, 1536d) and chat models (`gpt-4.1`) via `AzureOpenAI` client.
- **Azure Document Intelligence**: `azure_ocr.py` → prebuilt-layout OCR model for PDF table extraction. Credentials checked at startup.
- **Ingestion pipeline (sibling)**: `ingestion/` (outside `backend/src/`) → `MPPExtractor`, `MspdiExtractor`, `IngestionPipeline` with NUSF normalization used by `main.py` for non-PDF file types.
- **Subdirectories**: `experimental/` and `version_1_0/` contain independent feature variants; each has its own codemap.
- **Consumer**: The front-end SPA calls `/upload`, `/query`, `/predictive`, `/export/pdf`, and polls progress endpoints.

## Public Surface
### `main.py`
- `app` — FastAPI application instance; mounted at root with CORS and lifespan.
- `lifespan(app)` — Async context manager; starts JVM, inits pgvector, creates chat-memory tables, validates Azure OCR credentials.
- `POST /upload` — Ingests two schedule files (old/new) into per-session vector stores.
- `GET /upload/progress/{upload_id}` — Poll upload pipeline progress.
- `POST /query` — Runs comparison query against two vector stores; returns HTML.
- `POST /predictive` — Runs single-schedule predictive analysis; returns HTML or dashboard.
- `POST /export/pdf` — Renders HTML to PDF via headless Chromium.
- `GET /` , `GET /health` — Root info and health check.

### `config.py`
- `Settings` — Pydantic `BaseSettings` subclass loading `.env`; holds all Azure OpenAI, Supabase, and database credentials.
- `settings` — Singleton `Settings()` instance.
- `get_database_url()` — Composes a PostgreSQL connection string from settings.

### `database.py`
- `sanitize_table_name(name)` — Strips invalid characters, truncates to 63 chars, lowercases.
- `parse_database_url(url)` — Decomposes a PostgreSQL URL into host/port/database/user/password.
- `init_pgvector_extension()` — Enables the pgvector extension.
- `create_vector_table(table_name, dimension)` — Creates a pgvector-capable table with HNSW index.
- `insert_embeddings(table_name, documents)` — Batch-inserts content + embedding + metadata.
- `similarity_search(table_name, query_embedding, top_k)` — Cosine-similarity search.
- `fetch_all_chunks(table_name, chunk_type)` — Retrieves all chunks, optionally filtered by metadata type.
- `create_chat_memory_table()` — Creates `chat_memory` and `session_metadata` tables.
- `save_session_metadata(...)` / `get_session_metadata(session_id)` / `get_session_metadata_history(session_id)` — CRUD for session metadata.
- `save_chat_message(session_id, role, content)` / `get_chat_history(session_id, limit)` — Chat persistence.

### `embeddings.py`
- `get_azure_openai_client()` — Returns configured `AzureOpenAI` client.
- `count_tokens(text)` — Token count via `tiktoken`.
- `truncate_text(text, max_tokens)` — Truncates to max tokens.
- `split_oversized_text(text, max_tokens)` — Splits text by line boundaries under token limit.
- `generate_embeddings(texts, progress_callback)` — Batch embedding with retry and rate-limit handling.
- `generate_single_embedding(text)` — Single-text embedding.

### `vector_store.py`
- `VectorStoreManager` — Class managing pgvector table lifecycle and search.
- `vector_store_manager` — Singleton instance.
- `create_store_from_pdf(session_id, file_name, pdf_bytes, ...)` — Full pipeline: creates table, OCRs PDF, embeds, stores.
- `create_store_from_chunks(session_id, file_name, chunks, ...)` — Stores pre-made chunks with zero embeddings.
- `search(table_name, query, top_k)` — Embed query + vector search.
- `search_multiple_stores(table_names, query, top_k)` — Parallel search across stores.
- `fetch_all_from_stores(table_names, chunk_type)` — Bulk-fetch all chunks from multiple stores.

### `agent.py`
- `SYSTEM_PROMPT_BASE` — ~900-line system prompt encoding ten-section output format, five document types, adaptive column mapping, root cause analysis, and decision engine JSON structure.
- `rag_agent` — Agent object (defined later in file) with `query()` method supporting comparison queries.

### `predictive_agent.py`
- `NOVA_INSIGHT_SCHEMA` — Strict JSON schema for structured LLM output (14 top-level sections including root cause analysis, forcing assessment, resource assessment).
- `PREDICTIVE_SYSTEM_PROMPT` — Detailed analysis instructions for single-schedule predictive analysis.
- `predictive_agent` — Agent object with `analyze()` method.

### `azure_ocr.py`
- `AzureDocumentIntelligence` — Client wrapping Azure Document Intelligence REST API.
- `extract_from_pdf(pdf_bytes, filename, timeout)` — Returns `{success, raw_markdown, tables, pages, error}`.
- `check_credentials()` — Static method returning `(bool, message)`.

### `pdf_processor.py`
- `extract_from_pdf(pdf_bytes, filename)` — Wrapper around `AzureDocumentIntelligence` extraction.
- `process_pdf_binary(pdf_bytes, filename)` — Full pipeline: OCR → table/raw-markdown parsing → compact CSV chunks (250 rows each).
- `rows_to_compact_csv_chunks(headers, data_rows, source)` — Converts header+rows to semicolon-separated CSV chunks.

### `html_formatter.py`
- `parse_structured_response(markdown)` — Extracts 10 sections + DECISION_ENGINE/HEALTH_DATA JSON from agent markdown.
- `parse_tables_by_section(markdown)` — Groups markdown tables by detected category (delayed, added, removed, etc.).
- `generate_table_html(tables_section, language)` — Renders category-grouped HTML tables with SVG icons, badges, and CSV export button.

### `predictive_html_formatter.py`
- `format_predictive_as_html(predictive_json, language)` — Renders full predictive report HTML including project status card, hero metrics, delayed activities table, root cause analysis, priority actions, resource assessment, forcing assessment cards.

### `pdf_export.py`
- `html_to_pdf(html, page_width_px)` — Renders HTML to PDF via headless Playwright Chromium with timeout and external-resource blocking.

### `jvm_init.py`
- `start_jvm_if_needed()` — Starts JPype JVM with MPXJ JARs on classpath; must be called after Gunicorn fork.
