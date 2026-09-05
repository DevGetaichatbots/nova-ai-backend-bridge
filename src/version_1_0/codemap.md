# backend/src/version_1_0/

## Responsibility

Implements the Version 1.0 dashboard rendering pipeline for the Nova Insight RAG agent. It adapts raw schedule-analysis data into a structured normalized payload and renders it as fully self-contained HTML with inline CSS and JavaScript for client-side interactive filtering and sorting. Also provides localized (English/Danish) string tables for all UI labels.

## Design

**Adapter pattern** — `adapters.py` exposes `adapt_health_dashboard` and `adapt_predictive_dashboard`, each of which transforms a raw `dict` (produced by upstream analysis) into a normalized dashboard payload with uniform KPIs, graph data, tables, filters, and summary fields. The adapters are pure data transformations with no side effects.

**Template/View separation** — `formatters.py` receives the normalized payload from an adapter and passes it into `_render_payload`, which assembles the final HTML document. The renderer is composed of focused private functions: `_render_kpis`, `_render_sidebar`, `_render_progress_graph` (SVG with three line-series and a bar-chart variant), `_render_area_progress`, `_render_table` (four variants: progress, changed, critical_path, delayed), `_render_actions`, `_render_summary`, and `_render_payload` (the top-level layout orchestrator).

**Localization via key lookup** — `localization.py` defines a `LABELS` dictionary keyed by language code (`"en"`, `"da"`) with ~90 UI string keys each. The helper `t(language, key)` resolves a key for a requested language, falling back to English.

**Client-side interactivity** — `formatters.py` embeds ~200 lines of vanilla JavaScript (`JS` constant) that implements filter-button toggling and table-column sorting by reading `data-*` attributes on rendered rows. The normalized payload is also inlined as `window.__novaV1Data` for dynamic re-rendering of the area-progress list.

## Data & Control Flow

1. A caller invokes either `format_health_v1_as_html(data, language)` or `format_predictive_v1_as_html(data, language)` from the package's public API (`__init__.py`).
2. The chosen `format_*` function calls its corresponding adapter (`adapt_health_dashboard` or `adapt_predictive_dashboard` in `adapters.py`), which normalizes raw input into a structured dashboard `dict` containing keys like `"kpis"`, `"graph"`, `"tables"`, `"summary"`, `"filters"`, `"warnings"`, etc.
3. The normalized payload is passed to `_render_payload` in `formatters.py`, which composes the full HTML document: inline `<style>`, inline `<script>`, header with status badge, KPI grid, sidebar with filter buttons, graph card (SVG), area-progress list, summary section, and data tables.
4. `localize_v1_html(html, language)` extracts the JSON payload from an existing rendered HTML via regex (`_PAYLOAD_SCRIPT_RE`), deserializes it, and re-renders it with a different language — used for server-side locale switching without re-adapting the source data.

## Integration Points

- **Consumers**: The parent RAG agent (code outside this directory) calls `format_health_v1_as_html`, `format_predictive_v1_as_html`, and `localize_v1_html`. These are the only crossing points.
- **Dependencies**: None beyond the Python standard library (`math`, `re`, `collections`, `datetime`, `html`, `json`).
- **Supersession**: Newer dashboard versions in sibling directories under `backend/src/` (e.g. `version_2_0/`) extend or replace this module. This directory represents the legacy V1 rendering path.

## Public Surface

| Symbol | File | Description |
|---|---|---|
| `adapt_health_dashboard(data, language)` | `adapters.py` | Normalizes raw health-analysis data into a structured dashboard payload dict. |
| `adapt_predictive_dashboard(data, language)` | `adapters.py` | Normalizes raw predictive-analysis data into a structured dashboard payload dict. |
| `format_health_v1_as_html(data, language)` | `formatters.py` | Full pipeline: adapts health data and renders as self-contained HTML. |
| `format_predictive_v1_as_html(data, language)` | `formatters.py` | Full pipeline: adapts predictive data and renders as self-contained HTML. |
| `localize_v1_html(html, language)` | `formatters.py` | Re-renders existing V1 HTML in a different locale by extracting and re-rendering the inline payload. |
