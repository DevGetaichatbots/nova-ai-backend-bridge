# Frontend Integration Guide

## API Overview

All endpoints use `multipart/form-data` (not JSON). The API returns JSON responses where the `response` field contains **ready-to-render HTML** — no parsing needed.

---

## Endpoints

### 1. `POST /upload` — Upload Two Schedules

**Request (form-data):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | yes | Unique session ID (you generate it, e.g. `session_` + random hex) |
| `old_session_id` | string | yes | Table name for old schedule (e.g. `table_old_` + random) |
| `new_session_id` | string | yes | Table name for new schedule (e.g. `table_new_` + random) |
| `old_schedule` | File | yes | PDF or CSV file (old/baseline schedule) |
| `new_schedule` | File | yes | PDF or CSV file (new/updated schedule) |

**Response:**
```json
{
  "status": "processing",
  "upload_id": "abc123",
  "session_id": "session_xyz",
  "message": "Upload started. Poll GET /upload/progress/{upload_id} for real-time progress."
}
```

**Important:** Upload is async. You must poll the progress endpoint.

---

### 2. `GET /upload/progress/{upload_id}` — Poll Upload Status

**Response (while processing):**
```json
{
  "status": "processing",
  "progress": 45,
  "stage": "Processing old schedule...",
  "old_chunks": 7,
  "new_chunks": 0
}
```

**Response (when complete):**
```json
{
  "status": "complete",
  "progress": 100,
  "stage": "Upload complete",
  "old_chunks": 14,
  "new_chunks": 14,
  "preloaded_context": "...large string...",
  "total_data_rows": 5500
}
```

Save `preloaded_context` and `total_data_rows` — you can pass them to `/query` for faster first query.

---

### 3. `POST /query` — Query Comparison Agent

**Request (form-data):**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | yes | — | User's question |
| `vs_table` | string | yes | — | The `session_id` from upload |
| `old_session_id` | string | yes | — | The `old_session_id` from upload |
| `new_session_id` | string | yes | — | The `new_session_id` from upload |
| `language` | string | no | `"en"` | `"en"` or `"da"` (Danish) |
| `format` | string | no | `"html"` | Always use `"html"` |

**Response:**
```json
{
  "response": "<div class=\"agent-response\" ...>...full HTML...</div>",
  "sources": ["table_old_xxx", "table_new_xxx"],
  "context_chunks": 1,
  "format": "html"
}
```

---

### 4. `POST /predictive` — Nova Insight Predictive Analysis

**Request (form-data):**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `schedule` | File | yes | — | Single PDF or CSV schedule |
| `language` | string | no | `"en"` | `"en"` or `"da"` |
| `format` | string | no | `"html"` | Always use `"html"` |
| `analysis_id` | string | no | auto-generated | Custom analysis ID |

**Response:**
```json
{
  "analysis_id": "abc123def456",
  "predictive_insights": "<div ...>...full HTML...</div>",
  "predictive_status": "success",
  "predictive_model": "gpt-4.1",
  "filename": "schedule.pdf",
  "reference_date": "2026-03-12",
  "format": "html",
  "processing_time_seconds": 45.2
}
```

---

## How to Render Responses

### The Simple Version

The `response` (comparison) and `predictive_insights` (predictive) fields contain **complete, self-contained HTML** with inline styles. Just inject it:

```javascript
// Comparison agent
const data = await fetch('/query', { method: 'POST', body: formData });
const json = await data.json();
document.getElementById('results').innerHTML = json.response;

// Predictive agent
const data = await fetch('/predictive', { method: 'POST', body: formData });
const json = await data.json();
document.getElementById('results').innerHTML = json.predictive_insights;
```

No CSS frameworks needed. No parsing needed. The HTML includes all styling inline.

---

## Two Response Types

### Type 1: Structured Analysis (90% of responses)

When the user asks any comparison/analysis question, the response is a **full 9-section report**:

```
┌─────────────────────────────────────────────┐
│  DECISION LAYER (4 cards)                   │
│  ┌─────────────────────────────────────┐    │
│  │ 1. Executive Overview               │    │
│  │    Status badge: AT RISK / CRITICAL  │    │
│  │    Biggest issue + why + focus       │    │
│  └─────────────────────────────────────┘    │
│  ┌──────────┬──────────┬──────────────┐    │
│  │ 2. Risk  │ 3.Impact │ 4.Confidence │    │
│  │  block   │  3-col   │  trust badge │    │
│  └──────────┴──────────┴──────────────┘    │
│                                             │
│  ANALYSIS LAYER (5 sections)                │
│  ┌─────────────────────────────────────┐    │
│  │ 5. Root Cause Analysis              │    │
│  │ 6. Recommended Actions (3-5 cards)  │    │
│  │ 7. Comparison Tables                │    │
│  │    (Delayed/Accelerated/Added/      │    │
│  │     Removed/Modified)               │    │
│  │ 8. Summary of Changes              │    │
│  │ 9. Project Health (score + badge)   │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**Root wrapper:**
```html
<style>
  .comparison-results .category-section table tr:hover { ... }
  ...
</style>
<div class="agent-response" style="font-family:-apple-system,...">
  <!-- Section 1: Executive Overview card -->
  <!-- Section 2: Biggest Risk card -->
  <!-- Section 3: Estimated Impact card -->
  <!-- Section 4: Confidence card -->
  <!-- Section 5: Root Cause Analysis -->
  <!-- Section 6: Recommended Actions -->
  <!-- Section 7: Comparison Tables -->
  <!-- Section 8: Summary of Changes -->
  <!-- Section 9: Project Health -->
</div>
```

### Type 2: Conversational (simple follow-ups)

Short answers like "summarize in 2 sentences" get a clean wrapper:

```html
<div style="font-family: -apple-system, ...; padding: 20px; color: #0f172a; line-height: 1.6; font-size: 15px;">
  <p style="margin:8px 0;line-height:1.6;">Answer text here...</p>
  <ul style="margin:8px 0;padding-left:20px;">
    <li style="margin:4px 0;">Bullet point...</li>
  </ul>
</div>
```

---

## Color / Theme Reference

| Element | Color | Hex |
|---------|-------|-----|
| Primary accent (teal) | Teal | `#0d9488` |
| Status: STABLE | Green | `#059669` |
| Status: AT RISK | Amber | `#d97706` |
| Status: CRITICAL | Red | `#dc2626` |
| Confidence: HIGH | Green | `#059669` |
| Confidence: MEDIUM | Amber | `#d97706` |
| Confidence: LOW | Red | `#dc2626` |
| Background | White | `#ffffff` |
| Text primary | Dark slate | `#0f172a` |
| Text secondary | Slate | `#64748b` |
| Card borders | Light gray | `#e2e8f0` |
| Card background | Off-white | `#f8fafc` |

---

## Frontend Flow (Step by Step)

### Comparison Agent Flow

```
1. Generate IDs
   ├── session_id = "session_" + randomHex(20)
   ├── old_session_id = "table_old_" + randomId()
   └── new_session_id = "table_new_" + randomId()

2. POST /upload  (with both files + IDs)
   └── Returns: upload_id

3. Poll GET /upload/progress/{upload_id}  (every 2-3 seconds)
   ├── Show progress bar using: progress (0-100)
   ├── Show stage text: "Processing old schedule..."
   └── When status = "complete" → stop polling, save preloaded_context

4. POST /query  (user asks a question)
   ├── Send: query, vs_table, old_session_id, new_session_id
   └── Returns: { response: "<html>..." }

5. Inject response HTML into your container
   └── document.getElementById('results').innerHTML = json.response
```

### Predictive Agent Flow

```
1. POST /predictive  (with single file)
   └── Returns: { predictive_insights: "<html>...", ... }

2. Inject HTML into container
   └── document.getElementById('results').innerHTML = json.predictive_insights
```

---

## Example: Minimal React Integration

```jsx
function ComparisonAgent() {
  const [html, setHtml] = useState('');
  const [loading, setLoading] = useState(false);
  const sessionRef = useRef({
    session_id: `session_${crypto.randomUUID().replace(/-/g, '').slice(0, 20)}`,
    old_session_id: `table_old_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 12)}`,
    new_session_id: `table_new_${Date.now().toString(36)}_${Math.random().toString(16).slice(2, 12)}`
  });

  // Step 1: Upload files
  async function uploadFiles(oldFile, newFile) {
    const form = new FormData();
    form.append('session_id', sessionRef.current.session_id);
    form.append('old_session_id', sessionRef.current.old_session_id);
    form.append('new_session_id', sessionRef.current.new_session_id);
    form.append('old_schedule', oldFile);
    form.append('new_schedule', newFile);

    const res = await fetch('/upload', { method: 'POST', body: form });
    const { upload_id } = await res.json();

    // Step 2: Poll progress
    while (true) {
      await new Promise(r => setTimeout(r, 2500));
      const prog = await fetch(`/upload/progress/${upload_id}`);
      const status = await prog.json();
      if (status.status === 'complete') break;
      // Update progress bar: status.progress (0-100)
    }
  }

  // Step 3: Send query
  async function sendQuery(question) {
    setLoading(true);
    const form = new FormData();
    form.append('query', question);
    form.append('vs_table', sessionRef.current.session_id);
    form.append('old_session_id', sessionRef.current.old_session_id);
    form.append('new_session_id', sessionRef.current.new_session_id);
    form.append('language', 'en');
    form.append('format', 'html');

    const res = await fetch('/query', { method: 'POST', body: form });
    const data = await res.json();
    setHtml(data.response);
    setLoading(false);
  }

  return (
    <div>
      {loading && <div>Analyzing schedules...</div>}
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
}
```

---

## Suggested Default Queries

For the best first-time experience, send one of these as the initial query after upload:

| Query | What it produces |
|-------|-----------------|
| `"Compare these two schedules and give me the full analysis"` | Complete 9-section report with all tables |
| `"Show me all delayed, added, and modified tasks"` | Focused on change categories with detailed tables |
| `"What are the biggest risks and recommended actions?"` | Decision-focused output |

Follow-up queries in the same session retain context (chat memory).

---

## Response Timing

| Schedule size | Upload time | Query time |
|--------------|-------------|------------|
| Small (< 500 rows) | 5-15s | 15-30s |
| Medium (500-2000 rows) | 15-30s | 30-60s |
| Large (2000-5500 rows) | 30-60s | 60-120s |

Set your fetch timeout to at least **3 minutes** for large schedules.
