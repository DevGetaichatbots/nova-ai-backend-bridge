# RAG Agent SaaS - Backend Architecture & Deployment Guide

## System Overview

A Python-based RAG (Retrieval-Augmented Generation) backend that compares construction schedules. It accepts two PDF files (old vs new schedule), extracts content using Azure AI services, stores embeddings in a vector database, and provides AI-powered comparison analysis with structured output.

---

## Architecture Diagram

```
 Client (n8n / Frontend)
        │
        ▼
 ┌──────────────────────────┐
 │   FastAPI Application    │
 │   (Gunicorn + Uvicorn)   │
 │   Port 5000              │
 └──────┬───────────────────┘
        │
        ├── POST /upload ──────────────────────────────────┐
        │                                                   │
        │   ┌─────────────────────────────────────┐        │
        │   │  1. Azure Document Intelligence     │        │
        │   │     (OCR + Table Extraction)         │        │
        │   │     API v2024-11-30                  │        │
        │   │     - Reads binary PDF               │        │
        │   │     - Extracts text per page          │        │
        │   │     - Extracts structured tables      │        │
        │   │     - Handles merged cells            │        │
        │   └──────────────┬──────────────────────┘        │
        │                  ▼                                │
        │   ┌─────────────────────────────────────┐        │
        │   │  2. Text Chunking                    │        │
        │   │     - Table chunks (markdown + JSON) │        │
        │   │     - Row-level chunks               │        │
        │   │     - Page text chunks (1000 chars)   │        │
        │   └──────────────┬──────────────────────┘        │
        │                  ▼                                │
        │   ┌─────────────────────────────────────┐        │
        │   │  3. Azure OpenAI Embeddings          │        │
        │   │     Model: text-embedding-3-small    │        │
        │   │     Dimension: 1536                  │        │
        │   │     Batch size: 16                   │        │
        │   └──────────────┬──────────────────────┘        │
        │                  ▼                                │
        │   ┌─────────────────────────────────────┐        │
        │   │  4. Supabase PostgreSQL + pgvector   │        │
        │   │     - Session-specific tables         │        │
        │   │     - IVFFlat index (100 lists)       │        │
        │   │     - Cosine similarity search        │        │
        │   └─────────────────────────────────────┘        │
        │                                                   │
        ├── POST /query ───────────────────────────────────┐
        │                                                   │
        │   ┌─────────────────────────────────────┐        │
        │   │  5. Dual Vector Store Search         │        │
        │   │     - Query embedding generated       │        │
        │   │     - Search OLD schedule table       │        │
        │   │     - Search NEW schedule table       │        │
        │   │     - Top-K results (default: 10)     │        │
        │   └──────────────┬──────────────────────┘        │
        │                  ▼                                │
        │   ┌─────────────────────────────────────┐        │
        │   │  6. Azure OpenAI Chat (GPT-4o)       │        │
        │   │     - System prompt: Schedule Analyst │        │
        │   │     - Context from both stores        │        │
        │   │     - Chat history (last 10 msgs)     │        │
        │   │     - Language: Danish / English       │        │
        │   │     - Temperature: 0.3                │        │
        │   │     - Max tokens: 16,000              │        │
        │   └──────────────┬──────────────────────┘        │
        │                  ▼                                │
        │   ┌─────────────────────────────────────┐        │
        │   │  7. Response Formatting               │        │
        │   │     - Markdown (dev/n8n webhook)      │        │
        │   │     - Styled HTML (production API)    │        │
        │   │       • Category-grouped tables       │        │
        │   │       • Status badges & SVG icons     │        │
        │   │       • CSV export button             │        │
        │   │       • Health metrics dashboard      │        │
        │   └─────────────────────────────────────┘        │
        │                                                   │
        └── GET /health ── Returns 200 OK ─────────────────┘
```

---

## Processing Pipeline Detail

### Step 1: PDF Upload & OCR
- Binary PDF received via multipart form upload
- Validated for file type and size
- Sent to **Azure Document Intelligence** (Layout model)
- Asynchronous polling until extraction completes (~3-7 seconds)
- Returns: page text, structured tables with cell coordinates, merged cell handling

### Step 2: Intelligent Chunking
- **Table chunks**: Full table as markdown + embedded structured JSON with cell coordinates
- **Row chunks**: Individual rows with page number and cell data for granular search
- **Text chunks**: Page content split at 1000 characters with 200 char overlap
- Each chunk tagged with metadata (source file, page number, chunk type)

### Step 3: Embedding Generation
- Azure OpenAI `text-embedding-3-small` model (1536 dimensions)
- Batch processing (16 texts per API call) for efficiency
- Each chunk converted to a dense vector representation

### Step 4: Vector Storage
- Each PDF stored in its own PostgreSQL table with pgvector extension
- Table schema: `id`, `content`, `embedding (vector 1536)`, `metadata (JSONB)`, `created_at`
- IVFFlat index with 100 lists for fast cosine similarity search
- Connected via Supabase connection pooler (port 6543)

### Step 5: Query & Retrieval
- User query embedded using same model
- Cosine similarity search across BOTH schedule tables
- Top-K most relevant chunks retrieved from each store
- Context assembled with source labels (OLD vs NEW)

### Step 6: AI Analysis
- GPT-4o with Construction Schedule Comparison Analyst prompt
- Mandatory 3-section output: Comparison Table, Summary, Project Health
- Chat memory persisted in `chat_memory` PostgreSQL table
- Supports Danish and English output

### Step 7: Response Formatting
- **Production API**: Styled HTML with gradient headers, category badges, CSV export, health dashboard
- **Dev/Webhook**: Raw markdown for n8n or custom rendering
- Auto-detected by request host, overridable via `format` parameter

---

## Azure Services Used

| Service | Purpose | Model/Version |
|---------|---------|---------------|
| **Azure Document Intelligence** | PDF OCR & table extraction | Layout model, API v2024-11-30 |
| **Azure OpenAI - Embeddings** | Text vectorization | text-embedding-3-small (1536d) |
| **Azure OpenAI - Chat** | AI analysis & comparison | GPT-4o |

---

## API Endpoints

### POST /upload
Accepts two PDF schedules and processes them into vector stores.
```
Fields: session_id, old_session_id, old_schedule (file), new_session_id, new_schedule (file)
```

### POST /query
Queries the AI agent to compare schedules.
```
Fields: query, vs_table, old_session_id, new_session_id, language (da/en), format (markdown/html)
```

### GET /health
Returns 200 OK for health checks.

---

## Deployment Configuration

### Production Server
```
gunicorn --bind=0.0.0.0:5000 --workers=2 --worker-class=uvicorn.workers.UvicornWorker --timeout=120 src.main:app
```

### Environment Variables Required
```
# Supabase (Vector Database)
SUPABASE_URL                        # Supabase project URL
SUPABASE_SERVICE_KEY                # Service role key
SUPABASE_DB_HOST                    # Database host
SUPABASE_DB_PASSWORD                # Database password
SUPABASE_POOLER_URL                 # Connection pooler URL (port 6543)

# Azure OpenAI (Embeddings + Chat)
AZURE_OPENAI_API_KEY                # API key
AZURE_OPENAI_ENDPOINT               # e.g. https://azurenordicgpt.cognitiveservices.azure.com/
AZURE_OPENAI_EMBEDDING_DEPLOYMENT   # e.g. text-embedding-3-small
AZURE_OPENAI_CHAT_DEPLOYMENT        # e.g. gpt-4o

# Azure Document Intelligence (OCR)
AZURE_DOC_INTELLIGENCE_ENDPOINT     # Document Intelligence endpoint
AZURE_DOC_INTELLIGENCE_KEY          # Document Intelligence key
```

---

## Project Structure
```
src/
├── main.py              # FastAPI app, /upload, /query, /health endpoints
├── config.py            # Environment config via Pydantic Settings
├── database.py          # PostgreSQL + pgvector operations (SQL injection protected)
├── azure_ocr.py         # Azure Document Intelligence OCR client
├── pdf_processor.py     # PDF parsing, table extraction, text chunking
├── embeddings.py        # Azure OpenAI embedding generation (batch)
├── vector_store.py      # Vector store CRUD + similarity search
├── agent.py             # RAG agent with dual-store retrieval + chat memory
└── html_formatter.py    # Premium HTML output (tables, badges, CSV, health)
```

---

## Security
- SQL injection protection via `psycopg2.sql` parameterized queries
- Table names sanitized (alphanumeric + underscore only)
- All secrets stored as environment variables, never logged
- CORS configured for allowed origins
