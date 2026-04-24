# RAG Agent SaaS — Complete Backend Guide

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [File Structure](#3-file-structure)
4. [Configuration & Environment](#4-configuration--environment)
5. [Database Layer](#5-database-layer)
6. [File Processing Pipeline](#6-file-processing-pipeline)
7. [Vector Store Layer](#7-vector-store-layer)
8. [Comparison Agent (Schedule Diff)](#8-comparison-agent-schedule-diff)
9. [Predictive Agent (Nova Insight)](#9-predictive-agent-nova-insight)
10. [HTML Formatting Layer](#10-html-formatting-layer)
11. [API Endpoints Reference](#11-api-endpoints-reference)
12. [Data Flow: End-to-End Request Lifecycle](#12-data-flow-end-to-end-request-lifecycle)
13. [LLM Configuration & Token Management](#13-llm-configuration--token-management)
14. [Error Handling & Retry Logic](#14-error-handling--retry-logic)
15. [Key Design Decisions](#15-key-design-decisions)

---

## 1. System Overview

This backend is a FastAPI application that provides AI-powered analysis of construction project schedules. It has two independent agents:

| Agent | Purpose | Input | Output |
|-------|---------|-------|--------|
| **Comparison Agent** | Compares two schedules (old vs new) to find added, removed, delayed, accelerated, and modified tasks | Two PDF or CSV files | Structured HTML report with 6 mandatory sections |
| **Predictive Agent (Nova Insight)** | Analyzes a single schedule to detect delayed activities, perform root cause analysis, and provide decision support | One PDF or CSV file | Structured HTML report with 10 data cards |

Both agents use Azure OpenAI GPT-4.1 as the core LLM, with deterministic settings (`temperature=0`, `top_p=0.1`, `seed=42`) to ensure reproducible results. Both agents send as much schedule data as possible to the LLM (capped at 1.9MB to stay within the model's token limit).

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT (Frontend)                        │
└────────┬──────────────────┬──────────────────┬──────────────────┘
         │                  │                  │
    POST /upload       POST /query       POST /predictive
         │                  │                  │
┌────────▼──────────────────▼──────────────────▼──────────────────┐
│                     FastAPI (main.py)                           │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────────┐ │
│  │  Upload  │  │  Query       │  │  Predictive               │ │
│  │  Handler │  │  Handler     │  │  Handler                  │ │
│  └────┬─────┘  └──────┬───────┘  └─────────┬─────────────────┘ │
└───────┼────────────────┼───────────────────┼───────────────────┘
        │                │                   │
   ┌────▼────┐    ┌──────▼──────┐     ┌──────▼──────────┐
   │  File   │    │  Comparison │     │  Predictive     │
   │  Proc.  │    │  Agent      │     │  Agent          │
   │         │    │  (agent.py) │     │  (predictive_   │
   │ PDF:    │    └──────┬──────┘     │   agent.py)     │
   │  OCR →  │           │            └──────┬──────────┘
   │  Tables │    ┌──────▼──────┐            │
   │         │    │ Vector Store│     ┌──────▼──────────┐
   │ CSV:    │    │  Manager    │     │  Azure OpenAI   │
   │  Parse  │    │ (fetch all  │     │  GPT-4.1        │
   │  Direct │    │  chunks)    │     │  (JSON Schema)  │
   └────┬────┘    └──────┬──────┘     └─────────────────┘
        │                │
   ┌────▼────────────────▼────┐     ┌─────────────────────────┐
   │    Supabase PostgreSQL   │     │   HTML Formatter        │
   │    + pgvector extension  │     │   (comparison or        │
   │                          │     │    predictive)          │
   │  - Vector tables (one    │     └─────────────────────────┘
   │    per uploaded file)    │
   │  - chat_memory table    │
   │  - session_metadata     │
   └──────────────────────────┘
```

---

## 3. File Structure

```
src/
├── __init__.py                    # Empty init
├── main.py                (838 lines)  # FastAPI app, all endpoints, progress tracking, CSV parsing
├── config.py               (39 lines)  # Pydantic settings from environment variables
├── database.py            (327 lines)  # PostgreSQL connection pool, table creation, CRUD operations
├── embeddings.py          (123 lines)  # Azure OpenAI embedding generation with batching and retry
├── vector_store.py        (165 lines)  # VectorStoreManager: create stores, search, fetch all
├── azure_ocr.py           (302 lines)  # Azure Document Intelligence OCR client
├── pdf_processor.py       (487 lines)  # PDF → compact CSV chunks (OCR table extraction)
├── agent.py               (847 lines)  # Comparison Agent: system prompt + RAGAgent class
├── predictive_agent.py    (903 lines)  # Predictive Agent: JSON schema + PredictiveAgent class
├── html_formatter.py     (1176 lines)  # Comparison report → structured HTML
└── predictive_html_formatter.py (778 lines)  # Predictive JSON → structured HTML
```

**Total: ~5,986 lines of Python**

---

## 4. Configuration & Environment

**File: `src/config.py`**

Uses Pydantic `BaseSettings` to load configuration from environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `SUPABASE_URL` | Supabase project URL | — |
| `SUPABASE_SERVICE_KEY` | Supabase service role key | — |
| `SUPABASE_DB_HOST` | Direct database host | — |
| `SUPABASE_DB_PASSWORD` | Database password | — |
| `SUPABASE_POOLER_URL` | Connection pooler URL (preferred) | — |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | — |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | — |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding model name | `text-embedding-3-small` |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | Comparison agent model | `gpt-4.1` |
| `AZURE_OPENAI_PREDICTIVE_DEPLOYMENT` | Predictive agent model | `gpt-4.1` |
| `AZURE_OPENAI_API_VERSION` | API version | `2025-04-01-preview` |
| `EMBEDDING_DIMENSION` | Vector dimension | `1536` |

**Database URL resolution** (`get_database_url()`):
1. If `SUPABASE_POOLER_URL` is set → use it (preferred for connection pooling)
2. Else if `DATABASE_URL` is set → use it
3. Else → construct from individual `SUPABASE_DB_*` fields

---

## 5. Database Layer

**File: `src/database.py`**

### Connection Pooling

Uses `psycopg2.pool.ThreadedConnectionPool` with:
- **Min connections:** 2
- **Max connections:** 8
- **SSL mode:** `require`
- **Thread-safe:** Uses `threading.Lock` for pool initialization

The pool is lazily initialized on first use via `_get_pool()` with double-checked locking.

```python
@contextmanager
def get_db_connection():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
```

### Database Tables

**1. Vector tables** (dynamically created per uploaded file):
```sql
CREATE TABLE IF NOT EXISTS {table_name} (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- HNSW index for cosine similarity search
CREATE INDEX IF NOT EXISTS {table_name}_embedding_idx
    ON {table_name} USING hnsw (embedding vector_cosine_ops);
```

**2. `chat_memory`** — stores conversation history per session:
```sql
CREATE TABLE IF NOT EXISTS chat_memory (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**3. `session_metadata`** — stores original filenames for each upload session:
```sql
CREATE TABLE IF NOT EXISTS session_metadata (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    old_filename VARCHAR(500),
    new_filename VARCHAR(500),
    old_table_name VARCHAR(255),
    new_table_name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Key Functions

| Function | Purpose |
|----------|---------|
| `sanitize_table_name(name)` | Converts arbitrary strings to valid PostgreSQL identifiers (max 63 chars) |
| `create_vector_table(name, dim)` | Creates a vector table with HNSW index |
| `insert_embeddings(table, docs)` | Batch inserts documents with embeddings (100 per batch) |
| `similarity_search(table, embedding, top_k)` | Cosine similarity search using pgvector |
| `fetch_all_chunks(table, chunk_type)` | Fetches ALL chunks of a given type (used for table data) |
| `save_session_metadata(...)` | Stores original PDF/CSV filenames for reference in AI responses |
| `get_session_metadata(session_id)` | Retrieves filenames for a session |
| `save_chat_message(session_id, role, content)` | Saves a message to chat history |
| `get_chat_history(session_id, limit)` | Retrieves last N messages for a session |

---

## 6. File Processing Pipeline

### Overview

Both PDF and CSV files go through a unified processing pipeline that converts them to the same compact CSV format:

```
PDF  ──→  Azure OCR  ──→  Structured Tables  ──→  Compact CSV Chunks
CSV  ──→  Parse directly  ────────────────────→  Compact CSV Chunks
```

The output format is identical: semicolon-separated values, header row repeated per chunk, 250 rows per chunk.

### PDF Processing

**Files: `src/azure_ocr.py` + `src/pdf_processor.py`**

**Step 1: Azure Document Intelligence OCR** (`azure_ocr.py`)
- Submits PDF bytes to Azure's `prebuilt-layout` model (API version `2024-11-30`)
- Polls for completion (up to 180 seconds, 3-second intervals)
- Extracts structured table data: cell positions, row/column spans, merged cells
- Returns raw markdown + structured table objects

**Step 2: Table to Compact CSV** (`pdf_processor.py`)

The function `_ocr_tables_to_compact_csv_chunks()` converts OCR tables to compact CSV:

1. **Header detection** — scans first 5 rows, scores each row against known Danish schedule column names (`Id`, `Opgavenavn`, `Varighed`, `Startdato`, `Slutdato`, etc.). If no good match, falls back to MS Project header templates.

2. **Gantt noise filtering** — removes non-data columns (quarter labels like `Kvt1`, week numbers, date range headers) using `GANTT_HEADER_RE` regex.

3. **Row serialization** — converts each data row to semicolon-separated CSV format:
   ```
   FORMAT: CSV — each row = one activity. Columns separated by semicolon (values with semicolons are quoted).
   Id;Opgavenavn;Varighed;Startdato;Slutdato;% arbejde færdigt
   41;Placering af vinduer;10d;ma 05-01-26;fr 17-01-26;0%
   42;Montage af facade;15d;on 07-01-26;fr 24-01-26;12%
   ```

4. **Chunking** — groups rows into chunks of 250 rows each (`MAX_CHUNK_ROWS`), with the header row repeated at the top of each chunk.

5. **Metadata** — each chunk gets `type: "table"` and `row_count` metadata.

### Quality-Based Selection (`process_pdf_binary`)

The PDF processor doesn't just use structured OCR tables blindly. It tries **two extraction paths** and picks the better one:

1. **Structured tables** — from Azure's table cell objects (`_ocr_tables_to_compact_csv_chunks`)
2. **Raw markdown tables** — parsed from Azure's raw markdown output (`_parse_raw_markdown_tables`)

Both paths produce the same compact CSV format. The system scores each using `_data_quality_score()` (checks header recognition, date format validity, duration format validity) and selects:
- Structured tables if quality ≥ 0.6
- Raw markdown if its quality beats structured tables
- Structured tables as default if both are low quality
- Whichever is available if only one path produced data

### CSV Processing

**In `main.py`: `_parse_csv_to_chunks()`**

1. Detects encoding (UTF-8-BOM or Latin-1)
2. Auto-detects delimiter (`;`, `,`, `\t`, `|`) using `csv.Sniffer`
3. Parses into rows
4. Calls `rows_to_compact_csv_chunks()` from `pdf_processor.py` — same output format as PDF path

### Storage Format

Both paths produce chunks with this structure:
```python
{
    "content": "Id;Opgavenavn;Varighed;Startdato;Slutdato;% arbejde færdigt\n41;Placering...;10d;ma 05-01-26;fr 17-01-26;0%\n...",
    "metadata": {
        "type": "table",
        "row_count": 250,
        "source": "filename.pdf",
        "chunk_index": 0
    }
}
```

**Important: No embeddings are generated for table chunks.** They are stored with zero-vector placeholders (`[0.0] * 1536`) because the system uses fetch-all retrieval, not similarity search. All data is sent to the LLM.

---

## 7. Vector Store Layer

**File: `src/vector_store.py`**

### VectorStoreManager

The central class that bridges file processing and database storage.

**Two creation methods:**

| Method | Used For | Embeddings? |
|--------|----------|-------------|
| `create_store_from_pdf()` | Legacy PDF path | Yes (real embeddings via Azure) |
| `create_store_from_chunks()` | Current path (both PDF and CSV) | No (zero vectors) |

The current system exclusively uses `create_store_from_chunks()` for both PDF and CSV uploads. The `create_store_from_pdf()` method exists but is not called from any endpoint.

**Retrieval methods:**

| Method | Purpose | Used By |
|--------|---------|---------|
| `search(table, query, top_k)` | Cosine similarity search | Not currently used |
| `search_multiple_stores(tables, query, top_k)` | Multi-store similarity search | Not currently used |
| `fetch_all_from_stores(tables, chunk_type)` | Fetch ALL chunks of a type | Comparison Agent |

**Key insight:** The system does NOT use similarity search for schedule data. It fetches ALL table chunks and sends as much as possible to the LLM (capped at 1.9MB per agent). This is because construction schedule comparison requires seeing every single row — you can't skip rows based on relevance. If the schedule data exceeds the 1.9MB budget, chunks are trimmed from the end and a warning is logged.

---

## 8. Comparison Agent (Schedule Diff)

**File: `src/agent.py`**

### RAGAgent Class

Handles two types of queries:
1. **Comparison queries** — triggers full six-section analysis
2. **Conversational queries** — greetings, help requests, general questions

Detection logic (`_is_comparison_query()`): Matches against a list of non-comparison patterns (greetings, acknowledgments). If not matched and the query has more than 2 words or contains schedule-related keywords, it's treated as a comparison query.

### System Prompt (~485 lines)

The system prompt instructs GPT-4.1 to:

1. **Auto-detect document type:**
   - MS Project Export (Id-based matching)
   - Detailtidsplan (Entydigt id-based matching)
   - Unstructured week-based schedules
   - Mixed/Hybrid formats

2. **Adaptive column mapping:** Fuzzy-matches column names to semantic roles (task ID, name, duration, dates, progress, etc.)

3. **Produce mandatory 6-section output:**

| Section | Header | Content |
|---------|--------|---------|
| 1. Executive Actions | `## EXECUTIVE_ACTIONS` | 3-5 prioritized recommendations with WHY, ROLE, EFFORT, RELATED IDs |
| 2. Comparison Tables | `### Delayed Tasks`, `### Added Tasks`, etc. | Separate markdown table per category (delayed, accelerated, added, removed, modified) |
| 3. Root Cause Analysis | `## ROOT_CAUSE_ANALYSIS` | Why changes/delays occurred, grouped by cause category |
| 4. Impact Assessment | `## IMPACT_ASSESSMENT` | Downstream consequences of critical findings |
| 5. Summary of Changes | `## SUMMARY_OF_CHANGES` | Statistics overview with counts |
| 6. Project Health | `## PROJECT_HEALTH` | Health score (🟢/🟡/🔴), impact breakdown, hidden `HEALTH_DATA` JSON |

### Context Retrieval

`_retrieve_context()`:
1. Fetches ALL `type="table"` chunks from both vector stores
2. Splits budget equally between stores: `MAX_CONTEXT_BYTES (1.9MB) / 2`
3. Includes chunks sequentially until budget is exhausted
4. Logs warnings if any chunks are omitted

### Token Budget Management

```python
MAX_CONTEXT_BYTES = 1_900_000    # ~1.9 MB context cap
MAX_MODEL_TOKENS = 1_047_576     # GPT-4.1 model limit
TOKENS_PER_BYTE = 0.50           # Estimated conversion ratio
RESERVED_TOKENS = 50_000         # Reserved for system prompt + output
```

Chat history fitting:
- Calculates remaining token budget after context + system prompt
- Fits as many recent messages as possible within budget
- Truncates assistant messages to 500 chars to preserve more history

### Auto-Retry on Token Overflow

If the LLM returns a `context_length_exceeded` error:
1. Re-fetches context with 85% of original byte budget
2. Strips ALL chat history
3. Retries the request

---

## 9. Predictive Agent (Nova Insight)

**File: `src/predictive_agent.py`**

### JSON Schema Output

Unlike the Comparison Agent (which produces markdown), the Predictive Agent uses GPT-4.1's **structured output** feature with a strict JSON schema (`NOVA_INSIGHT_SCHEMA`). The schema has 11 required top-level fields:

| Field | Type | Description |
|-------|------|-------------|
| `executive_actions` | array[3] | Top 3 most critical actions with WHO, WHAT, WHEN, manpower assessment |
| `management_conclusion` | string | 3-5 sentence briefing for project director |
| `schedule_overview` | object | Schedule name, reference date, total activities, delayed count |
| `delayed_activities` | array | ALL delayed activities sorted by priority then days overdue |
| `root_cause_analysis` | array | One entry per root cause task |
| `downstream_consequences` | array | Tasks delayed because of a root cause |
| `priority_actions` | array | Up to 7 specific practical actions |
| `resource_assessment` | array | One entry per CRITICAL_NOW task |
| `forcing_assessment` | array | Acceleration viability for each critical/important task |
| `summary_by_area` | array | One entry per area/discipline |
| `insight_data` | object | Aggregate statistics for the hero card |

### Four-Phase Analysis

**Phase 1 — Detection (Module A):**
Delayed activity detection rule: `Startdato < reference_date AND progress = 0%`
- Scans every single row
- Excludes only grouping/summary headers (Omr. X, E100.XX, Globals)
- Extracts real task IDs from the data

**Phase 2 — Decision Support:**
- Classifies tasks by type (Coordination, Design, Bygherre, Production, Procurement, Milestone)
- Determines root causes vs downstream consequences
- Assigns priority (CRITICAL_NOW / IMPORTANT_NEXT / MONITOR)
- Generates action recommendations

**Phase 3 — Forcing Assessment (Module F):**
Rule-based evaluation of whether delayed tasks can be accelerated:

| Rule | Condition | is_forceable |
|------|-----------|-------------|
| Rule 1 | Coordination/Design/Bygherre constraint | `not_recommended` |
| Rule 2 | Procurement delay | `not_recommended` |
| Rule 3 | Production with >3 downstream deps | `limited` |
| Rule 4 | Production with ≤3 downstream deps | `possible` |
| Rule 5 | Milestone/zero-duration | `not_recommended` |

Each assessment includes: constraint type, reason, risk if forced, recommendation, coordination cost (k-factor), parallelizability (p-factor), max speedup (Amdahl's law), optimal team size, and point-of-no-return status.

**Phase 4 — Executive Actions:**
Synthesizes all analysis into exactly 3 concrete actions with:
- WHO (responsible role)
- WHAT (direct instruction)
- WHEN (real calendar date with day name)
- Manpower indicator (helps or useless, with explanation)

### Reference Date Extraction

`_extract_reference_date()` in `main.py` tries multiple filename patterns:
- `YYYY-MM-DD`, `DD-MM-YYYY`, `DD.MM.YYYY`
- `YYYY.MM.DD`, `DD_MM_YYYY`, `YYYY_MM_DD`
- `YYYYMMDD` (compact)

If no date is found in the filename, today's date is used.

### Post-Processing Validation

After receiving the JSON response, the agent performs:
1. **Schema validation** — checks all 11 required keys exist
2. **False positive removal** — removes delayed activities with `days_overdue ≤ 0`
3. **Cascading cleanup** — removes downstream consequences, forcing assessments, and executive action references linked to false positives
4. **Recount statistics** — recalculates `delayed_count`, `critical_count`, `important_count`, `monitor_count`, `forceable_count`, `not_forceable_count`

---

## 10. HTML Formatting Layer

### Comparison HTML Formatter

**File: `src/html_formatter.py`**

Converts the Comparison Agent's markdown response into a structured HTML report.

**Processing pipeline:**
```
Markdown → parse_structured_response() → extract sections + tables
                                       → generate section HTML
                                       → generate table cards
                                       → generate health dashboard
                                       → count actual table rows
                                       → fix summary/health counts
                                       → assemble final HTML
```

**Key functions:**

| Function | Purpose |
|----------|---------|
| `parse_structured_response()` | Splits markdown into 6 named sections + extracts health JSON |
| `_parse_tables_from_markdown()` | Extracts category-grouped tables from markdown |
| `generate_executive_html()` | Renders Executive Actions as styled cards |
| `generate_section_html()` | Renders Root Cause / Impact / Summary as formatted cards |
| `generate_health_html()` | Renders Project Health dashboard with stat cards |
| `_count_actual_table_rows()` | Counts real rows per category from parsed tables |
| `_fix_summary_counts()` | Replaces LLM-claimed counts with actual row counts in text |

**Count consistency fix:**
The LLM may claim "50 added tasks" in summary/health text but only output 25 rows in the actual table (due to output token limits). The formatter:
1. Counts actual parsed table rows per category
2. Overrides health_data JSON values with real counts
3. Regex-replaces count numbers in summary and health text

**Design theme:**
- Light/white background
- Teal accent color (`#0d9488`)
- SVG icons for each section and category
- Color-coded category cards (green=added, red=removed/delayed, amber=modified, etc.)
- Priority badges: 🔴 CRITICAL, 🟠 IMPORTANT, 🟢 LOW

### Predictive HTML Formatter

**File: `src/predictive_html_formatter.py`**

Converts the Predictive Agent's JSON output into a structured HTML report with 10 sections:

| Card | Content |
|------|---------|
| Hero Section | Delayed count, priority dots, progress bar, root cause count |
| Executive Actions | Top 3 actions with manpower indicators |
| Management Conclusion | Director-level briefing text |
| Schedule Overview | Total activities, format, areas |
| Delayed Activities | Sortable table with priority/type badges |
| Root Cause Analysis | Cause cards with affected task lists |
| Downstream Consequences | Link visualization |
| Priority Actions | Numbered step cards |
| Resource Assessment | Resource type badges |
| Forcing Assessment | Forceable/not-forceable cards with speedup gauges |
| Summary by Area | Area severity bars |

**Design theme:**
- Same light/white theme with teal accents
- Priority badges: red=CRITICAL NOW, amber=IMPORTANT NEXT, cyan=MONITOR
- Task type badges: purple=Coordination, blue=Design, etc.
- Severity-colored overdue indicators

---

## 11. API Endpoints Reference

### `GET /`
Returns API description and available endpoints.

### `GET /health`
Returns `{"status": "healthy"}`.

### `POST /upload`
Upload two schedule files (old + new) for comparison analysis.

**Form fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | Session identifier |
| `old_session_id` | string | Yes | Table name for old schedule |
| `new_session_id` | string | Yes | Table name for new schedule |
| `old_schedule` | File | Yes | Old schedule (PDF or CSV) |
| `new_schedule` | File | Yes | New schedule (PDF or CSV) |

**Response:**
```json
{
    "status": "processing",
    "upload_id": "abc12345",
    "session_id": "...",
    "message": "Upload started. Poll GET /upload/progress/{upload_id} for real-time progress."
}
```

**Processing:** Runs asynchronously. Both files are processed in parallel using `ThreadPoolExecutor`. Each file goes through: OCR/parse → chunk creation → vector store insertion.

### `GET /upload/progress/{upload_id}`
Poll upload status.

**Response (processing):**
```json
{
    "status": "processing",
    "upload_id": "abc12345",
    "old_schedule": {"step": "ocr", "detail": "...", "progress": 30},
    "new_schedule": {"step": "embedding", "detail": "...", "progress": 60},
    "overall_progress": 45
}
```

**Response (complete):**
```json
{
    "status": "complete",
    "overall_progress": 100,
    "elapsed_seconds": 42.3,
    "old_schedule": {"step": "complete", "chunks": 5, "table_name": "..."},
    "new_schedule": {"step": "complete", "chunks": 4, "table_name": "..."}
}
```

### `POST /query`
Query the comparison agent.

**Form fields:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | — | User's question |
| `vs_table` | string | Yes | — | Session ID (same as upload session_id) |
| `old_session_id` | string | Yes | — | Old schedule table name |
| `new_session_id` | string | Yes | — | New schedule table name |
| `language` | string | No | `en` | Response language (`en` or `da`) |
| `format` | string | No | `html` | Output format (`html` or `markdown`) |

**Response:**
```json
{
    "response": "<div class='comparison-results'>...</div>",
    "sources": ["old_table_name", "new_table_name"],
    "context_chunks": 12,
    "format": "html"
}
```

### `POST /predictive`
Upload a single schedule for Nova Insight predictive analysis.

**Form fields:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `schedule` | File | Yes | — | Schedule file (PDF or CSV) |
| `language` | string | No | `en` | Response language (`en` or `da`) |
| `format` | string | No | `html` | Output format (`html` or `json`) |
| `analysis_id` | string | No | auto-generated | Custom analysis ID for progress tracking |

**Response:**
```json
{
    "analysis_id": "abc123def456",
    "predictive_insights": "<div class='nova-insight'>...</div>",
    "predictive_status": "success",
    "predictive_model": "gpt-4.1",
    "filename": "schedule_2026-04-01.pdf",
    "reference_date": "01-04-2026",
    "format": "html",
    "processing_time_seconds": 65.2
}
```

### `GET /predictive/progress/{analysis_id}`
Poll predictive analysis status.

**Progress stages:** `received` → `reading` → `extracting` → `analyzing` → `formatting` → `complete`

The `analyzing` stage has 9 rotating sub-messages that cycle on each poll (e.g., "Nova is reading every row — detecting all delayed activities...", "Checking each activity against the reference date and progress...").

**Response:**
```json
{
    "analysis_id": "abc123def456",
    "stage": "analyzing",
    "step": 4,
    "total_steps": 6,
    "message": "Identifying root causes and downstream consequences...",
    "detail": "350 activities",
    "timestamp": 1713000000.0
}
```

---

## 12. Data Flow: End-to-End Request Lifecycle

### Comparison Flow

```
1. Client sends POST /upload with two PDF/CSV files
   ├─ Returns upload_id immediately
   └─ Background task starts

2. Background processing (parallel per file):
   ├─ If PDF:  azure_ocr → structured tables → compact CSV chunks
   ├─ If CSV:  parse → compact CSV chunks
   └─ Store chunks in Supabase vector table (zero embeddings)

3. Client polls GET /upload/progress/{upload_id} until status="complete"

4. Client sends POST /query with comparison question
   ├─ Fetch session metadata (original filenames)
   ├─ Detect query type (comparison vs conversational)
   ├─ If comparison:
   │   ├─ Fetch ALL table chunks from both vector stores
   │   ├─ Build context string (capped at 1.9MB)
   │   ├─ Load chat history (fits within remaining token budget)
   │   ├─ Build system prompt + user message
   │   ├─ Call Azure OpenAI GPT-4.1 (temperature=0, seed=42)
   │   ├─ Save conversation to chat_memory
   │   ├─ Convert markdown → HTML (html_formatter.py)
   │   └─ Return HTML response
   └─ If conversational:
       ├─ Skip vector store retrieval
       ├─ Call GPT-4.1 with conversational prompt
       └─ Return simple wrapped response
```

### Predictive Flow

```
1. Client sends POST /predictive with one PDF/CSV file
   ├─ Extract reference date from filename
   └─ Begin synchronous processing

2. File processing:
   ├─ If PDF:  azure_ocr → compact CSV chunks → context string
   └─ If CSV:  parse → compact CSV chunks → context string

3. Build context (capped at 1.9MB)

4. Call Azure OpenAI GPT-4.1 with:
   ├─ System prompt (Nova Insight personality + schema)
   ├─ User message (schedule data + analysis instructions)
   ├─ response_format = json_schema (strict mode)
   └─ Returns structured JSON matching NOVA_INSIGHT_SCHEMA

5. Post-processing validation:
   ├─ Schema validation (all 11 keys present)
   ├─ Remove false positives (days_overdue ≤ 0)
   ├─ Cascade cleanup (downstream consequences, forcing assessments)
   └─ Recount statistics

6. Format JSON → HTML (predictive_html_formatter.py)

7. Write debug file (analysis_debug.txt) with complete anatomy:
   ├─ Request metadata
   ├─ OCR output (PDF only — complete chunk dump; skipped for CSV)
   ├─ Context sent to LLM
   ├─ System prompt + user message
   ├─ Raw LLM response (pretty-printed JSON)
   └─ Result summary with delayed activity table

8. Return HTML response
```

---

## 13. LLM Configuration & Token Management

### Model Settings (Both Agents)

```python
temperature = 0       # Fully deterministic
top_p = 0.1           # Narrow sampling
seed = 42             # Fixed seed for reproducibility
max_tokens = 32768    # Max output tokens
```

**These values must NOT be changed** — they ensure consistent, reproducible analysis results.

### Context Budget

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `MAX_CONTEXT_BYTES` | 1,900,000 (~1.9 MB) | Max schedule data sent to LLM |
| `MAX_MODEL_TOKENS` | 1,047,576 | GPT-4.1 context window |
| `TOKENS_PER_BYTE` | 0.50 | Estimated byte-to-token ratio |
| `RESERVED_TOKENS` | 50,000 | Reserved for system prompt + output |

### Embedding Settings

| Parameter | Value |
|-----------|-------|
| Model | `text-embedding-3-small` |
| Dimension | 1536 |
| Max tokens per text | 8,000 |
| Batch size | 16 texts per API call |
| Rate limit retry | 10s × attempt number |

**Note:** Embeddings are currently NOT used for schedule data retrieval. All chunks are stored with zero vectors and retrieved via `fetch_all_chunks()`. The embedding infrastructure exists for future use cases (e.g., semantic search over schedules).

---

## 14. Error Handling & Retry Logic

### LLM Context Overflow

**Comparison Agent:** If GPT-4.1 returns `context_length_exceeded`:
1. Re-fetches context at 85% of original budget
2. Strips all chat history
3. Retries the request
4. If still fails → raises HTTP 500

**Predictive Agent:** No automatic retry — the 1.9MB context cap prevents overflow in practice.

### Embedding Rate Limits

`generate_embeddings()`:
- Max 3 retries per batch
- On HTTP 429: waits 10s × attempt number
- On other errors: waits 2s then retries
- 0.5s pause between batches to avoid rate limits

### Azure OCR Timeouts

- Submit timeout: 60 seconds
- Poll timeout: 180 seconds (3 minutes)
- Poll interval: 3 seconds

### Progress Cleanup

Predictive analysis progress entries are automatically cleaned up:
- On success: cleaned after 300 seconds (5 minutes)
- On error: cleaned after 120 seconds (2 minutes)
- Upload progress: not automatically cleaned (stored in-memory dict)

---

## 15. Key Design Decisions

### 1. Fetch-All vs Similarity Search

**Decision:** All schedule data is fetched and sent to the LLM, rather than using vector similarity search.

**Why:** Construction schedule comparison requires seeing every single row. If you use similarity search, you'll miss tasks that aren't "similar" to the query but are critical for a complete comparison (e.g., a task that was silently removed).

### 2. Compact CSV Format

**Decision:** Both PDF and CSV inputs are normalized to the same compact CSV chunk format.

**Why:** This ensures identical LLM behavior regardless of input format. The LLM sees the same data structure whether the user uploads a PDF or CSV.

### 3. Zero-Vector Storage

**Decision:** Table chunks are stored with `[0.0] * 1536` placeholder embeddings.

**Why:** Since we fetch all chunks (no similarity search), generating real embeddings would be a waste of API calls and time. The zero vectors satisfy the database schema without incurring cost.

### 4. Strict JSON Schema (Predictive Agent)

**Decision:** The Predictive Agent uses GPT-4.1's `response_format: json_schema` with `strict: True`.

**Why:** This guarantees the output exactly matches the expected structure, enabling reliable HTML rendering without fragile regex parsing. The Comparison Agent uses markdown because its output is more free-form (tables, analysis text).

### 5. Count Consistency Override

**Decision:** The HTML formatter counts actual parsed table rows and overrides LLM-claimed counts.

**Why:** The LLM may analyze 50 tasks internally but only output 25 rows in the table due to output token limits. The formatter ensures all displayed numbers (stat cards, summary text, health text) match the actual rendered data.

### 6. Session Metadata for Filename Preservation

**Decision:** Original PDF filenames are stored in `session_metadata` and injected into AI prompts.

**Why:** The LLM uses filenames as schedule labels (e.g., "Schedule_2026-03-15" vs "Schedule_2026-04-01") instead of generic "Version A/B" labels. This makes reports immediately understandable.

### 7. Deterministic LLM Settings

**Decision:** `temperature=0`, `top_p=0.1`, `seed=42` for all LLM calls.

**Why:** Same schedule files + same query should produce the same analysis every time. This is critical for a professional tool — project managers need consistent results they can trust and reference.

### 8. Bilingual Support (English + Danish)

**Decision:** Both agents support English and Danish, with language-specific section headers and field instructions.

**Why:** The primary users are Danish construction professionals. The system uses Danish headers (`LEDELSESHANDLINGER`, `ÅRSAGSANALYSE`) when `language=da`, but keeps task names in their original language from the PDF.

### 9. Debug Anatomy File

**Decision:** Every predictive analysis writes a complete `analysis_debug.txt` file.

**Why:** This captures the entire request lifecycle (input → OCR → context → system prompt → raw LLM response → result) for debugging and quality assurance. If results look wrong, this file reveals exactly what the LLM saw and produced.

### 10. Async Upload with Progress Polling

**Decision:** File uploads return immediately with an `upload_id`, and the client polls for progress.

**Why:** PDF OCR can take 30-60+ seconds. Blocking the HTTP request would cause timeouts. The polling pattern lets the frontend show real-time progress bars (step-by-step: queued → OCR → chunking → embedding → storing → complete).
