# Version 1.0 Health Dashboard — Pipeline Audit

Status: analysis complete, no code changed yet.
Scope: `POST /upload` → NUSF generation → `POST /version-1.0/health` → analysis → HTML render.
Trigger: "the version-1/health dashboard generation is flawed all of a sudden — it doesn't detect ahead activities at all, its very inconsistent."

---

## 0. TL;DR

The v1.0 health dashboard's "ahead of schedule" detection is not one code path, it's **up to three independent implementations** of the same classification, silently selected at runtime by data quality, and the one that actually runs by default is barely deterministic:

1. **`/upload` defaults to `data_format="raw"`** (`src/main.py:505`). This is the form default the frontend gets unless it explicitly opts into NUSF mode. Under "raw" mode, files are chunked with their **original column headers preserved** (Danish, Plandisc, MS Project, whatever the source system called them) — not normalized to the canonical NUSF schema.
2. At analysis time, `/version-1.0/health` (`src/main.py:1885`) runs those chunks through `parse_nusf_chunks()` (`src/experimental/nusf_compare_engine.py:113`), which has its **own small, ad-hoc header-guessing function** (`_norm_header`, lines 11-25) — a duplicate, and *inferior*, copy of the real header-recognition logic that already exists in `ingestion/recognition/heuristics.py`.
3. That ad-hoc guesser's `percent_complete` detection is `if "%" in raw or "færdigt" in raw or "erdigt" in raw or "complete" in raw` — it does **not** recognize "fremdrift" (Danish for "progress") or several other synonyms that the real recognizer (`ingestion/recognition/heuristics.py:110-115`) already knows about. When it misses the column, every row's `percent_complete` reads as empty → parses to `0.0` → an activity can never be "ahead" (variance = `actual − expected` = `0 − expected`, which is never positive), but easily reads as "behind". **This exactly reproduces the reported symptom**: ahead detection silently disappears, behind detection still fires (and over-fires), and it depends entirely on which literal column name the source file happened to use — hence "very inconsistent."
4. Independently, whenever `parse_nusf_chunks()` comes back empty (different failure mode, same root cause: raw headers it can't recognize at all), the pipeline **silently falls back** to an LLM-prompt-driven classifier (`CompareV4Agent`/`CompareV3Agent`) that re-implements the same ±5pp threshold *in a system prompt*, with no server-side verification that the model actually followed it. Two runs of the same files can silently execute different classifiers.

None of this is a recent regression in the sense of "someone broke working code" — it's a structural gap between a well-specified canonical NUSF pipeline (`ingestion/`) that most uploads never go through, and an older, ad-hoc, header-guessing shortcut (`nusf_compare_engine.py` + `src/pdf_processor.py`) that most uploads *do* go through. "All of a sudden" most likely means a source file (or a new schedule export tool/column naming convention) started hitting the gap that was always there.

See §5 for the full bug list and §6 for the recommended refactor.

---

## 1. Architecture — end to end

### 1.1 High-level flow

```
POST /upload  (file upload, data_format form field, default "raw")
   │
   ├─ data_format == "nusf"  ──────────────────────────────────────┐
   │                                                                │
   ├─ data_format == "raw" (DEFAULT) ─────────┐                    │
   │                                          │                    │
   │                          ┌───────────────▼──────────────┐     │
   │                          │ Format-specific "compact CSV"│     │
   │                          │ chunkers — ORIGINAL headers  │     │
   │                          │ preserved as-is:             │     │
   │                          │  _parse_csv_to_chunks()      │     │
   │                          │  _process_mpp_to_chunks()    │     │
   │                          │  _process_mspdi_to_chunks()  │     │
   │                          │  process_pdf_binary()        │     │
   │                          └───────────────┬───────────────┘    │
   │                                          │                    │
   │                          ┌───────────────▼──────────────┐     │
   │                          │ IngestionPipeline.run_from_   │◄────┘
   │                          │ bytes() → detector → extractor│
   │                          │ → HeuristicRecognizer (Jaro-  │
   │                          │ Winkler, threshold 0.85) → AI │
   │                          │ fallback → NormalizationEngine│
   │                          │ → to_nusf_chunks()            │
   │                          │ (canonical field names)       │
   │                          └───────────────┬───────────────┘
   │                                          │
   │            vector_store_manager.create_store_from_chunks()
   │            save_session_metadata(..., data_format=data_format)
   ▼
Supabase/pgvector table (one per uploaded file, zero-vector placeholders,
data fetched in full later — no similarity search is used for schedule data)


POST /version-1.0/health  (session_id, old_session_id, new_session_id,
                            reference_date, data_format, language, ...)
   │
   ├─ get_session_metadata(session_id) → effective_data_format
   │  require_nusf = (effective_data_format == "nusf")
   │
   ▼
compare_v5_graph_agent.analyze(...)   [src/experimental/compare_v5_graph_agent.py:188]
   │
   ├─ vector_store_manager.fetch_all_from_stores(table_names) — pulls ALL stored
   │  chunks for old + new schedule (+ history tables)
   │
   ├─ parse_nusf_chunks(old_chunks), parse_nusf_chunks(new_chunks)
   │  [src/experimental/nusf_compare_engine.py:113]
   │  — re-guesses headers via its OWN _norm_header(), independent of the
   │    ingestion/recognition heuristics used at upload time
   │
   ├─ IF both parse to non-empty rows:
   │     compare_nusf_chunks(old_chunks, new_chunks, reference_date)
   │     [nusf_compare_engine.py:385] ── DETERMINISTIC PATH
   │       → computes progress_vs_expected[].status ("ahead"/"behind"/"on_schedule")
   │       → then an LLM enrichment call may overlay project_health /
   │         critical_path_activities / location data (does not touch status)
   │
   ├─ ELSE (parse failed, require_nusf is False):
   │     super().analyze(...) = CompareV4Agent.analyze(...)
   │     [src/experimental/compare_v4_agent.py:367] ── LLM PATH
   │       → GPT-4.1 is given a system-prompt SPEC of the same ±5pp rule and
   │         asked to compute progress_vs_expected itself; nothing server-side
   │         re-derives or checks the "status" field it returns
   │     → falls back further to CompareV3Agent machinery for count post-
   │       processing only (does not touch "status" either)
   │
   ▼
json_data = result["json"]
   │
   ▼
format_health_v1_as_html(json_data, language)   [src/version_1_0/__init__.py:3]
   │
   ├─ adapt_health_dashboard(data, language)   [src/version_1_0/adapters.py:284]
   │     behind = [rows where status == "behind"]
   │     ahead  = [rows where status == "ahead"]
   │     → builds kpis, tables, graph, summary, filters
   │
   ▼
_render_payload(payload, language)   [src/version_1_0/formatters.py:780]
   → _render_table() per section (behind_table, ahead_table, changed_table,
     stage_table, critical_path_table)   [formatters.py:672]
   → final HTML string returned in the API response
```

### 1.2 Call chain with file:line references

| Step | File:Line | Function |
|---|---|---|
| Upload endpoint | `src/main.py:498` | `upload_schedules` |
| Upload mode default | `src/main.py:505` | `data_format: str = Form("raw")` |
| Raw-mode CSV chunking | `src/main.py:947-…` | `_parse_csv_to_chunks` |
| Raw-mode MPP chunking | `src/main.py:889-899` | `_process_mpp_to_chunks` (uses `rows_to_compact_csv_chunks`, **not** `to_nusf_chunks`) |
| Raw-mode MSPDI chunking | `src/main.py:902-912` | `_process_mspdi_to_chunks` (same) |
| Explicit NUSF-mode chunking | `src/main.py:915-945` | `_process_file_to_nusf_chunks` → `IngestionPipeline.run_from_bytes` → `to_nusf_chunks` |
| Canonical ingestion pipeline | `ingestion/pipeline.py:75-220` | `IngestionPipeline.run_from_bytes` |
| Canonical header recognition | `ingestion/recognition/heuristics.py:216-267` | `HeuristicRecognizer.recognize` (Jaro-Winkler, 0.85 threshold) |
| Canonical NUSF serialization | `ingestion/normalization/engine.py:463-544` | `to_nusf_chunks` |
| Health dashboard endpoint | `src/main.py:1885-1994` | `version_1_health_dashboard` |
| Effective format resolution | `src/main.py:1922-1923` | `effective_data_format = data_format or session_meta.get("data_format") or "raw"` |
| Analysis dispatch | `src/experimental/compare_v5_graph_agent.py:188-270` | `CompareV5GraphAgent.analyze` |
| Ad-hoc header re-guessing | `src/experimental/nusf_compare_engine.py:11-25` | `_norm_header` |
| NUSF chunk parsing | `src/experimental/nusf_compare_engine.py:113-144` | `parse_nusf_chunks` |
| Deterministic comparison | `src/experimental/nusf_compare_engine.py:385-652` | `compare_nusf_chunks` |
| **Ahead/behind classification (deterministic)** | `src/experimental/nusf_compare_engine.py:254-268` | `_expected_progress`, `_progress_status` |
| LLM-path fallback | `src/experimental/compare_v4_agent.py:367-645` | `CompareV4Agent.analyze` |
| **Ahead/behind classification (LLM prompt spec)** | `src/experimental/compare_v4_agent.py:477-487` | system-prompt text, not code |
| Count post-processing (LLM path) | `src/experimental/compare_v3_agent.py:158-230` | `_postprocess_v3` |
| JSON → dashboard shape | `src/version_1_0/adapters.py:284-395` | `adapt_health_dashboard` |
| Ahead/behind table split | `src/version_1_0/adapters.py:293-294` | filters on `status.lower() == "ahead"/"behind"` |
| HTML render entry | `src/version_1_0/__init__.py:3` (re-export) | `format_health_v1_as_html` |
| HTML render | `src/version_1_0/formatters.py:780-838` | `_render_payload` |
| Table render | `src/version_1_0/formatters.py:672-718` | `_render_table` |

### 1.3 Local dashboard modules

- `src/version_1_0/adapters.py` (457 lines) — reshapes the analysis JSON into the dashboard payload (kpis/tables/graph/summary).
- `src/version_1_0/formatters.py` (858 lines) — pure HTML/CSS string rendering from the adapted payload. Has an uncommitted local WIP change (`_change_type_cell`, stacked multi-line rendering for the "changed" table's change-type column) — cosmetic, unrelated to the ahead-detection bug.
- `src/version_1_0/localization.py` (196 lines) — en/da string tables. Verified consistent for status labels (`"ahead"/"Ahead"/"Foran"`); not a source of the bug (see §4).
- `src/version_1_0/__init__.py` — re-exports `format_health_v1_as_html`, `format_predictive_v1_as_html`, `localize_v1_html`.

---

## 2. Data model at each stage

### 2.1 Canonical NUSF `Activity` (spec, `ingestion/models/nusf.py:29-64`)

Key fields relevant to this bug: `planned_start`, `planned_finish` (datetime), `percent_complete` (float 0-100), `is_late` (Optional[bool], **Plandisc-only**, `None` elsewhere), `critical_flag`, `total_float`, `area`/`floor`/`phase`, `discipline`.

### 2.2 Canonical NUSF CSV row on the wire (`ingestion/normalization/engine.py:475-544`, `to_nusf_chunks`)

Fixed column order:
```
source_id, stable_key, name, planned_start, planned_finish, percent_complete,
activity_type, wbs_code, discipline, location_path, area, floor, phase,
duration_hours, actual_start, actual_finish, is_late, inspected_status,
critical_flag, total_float, predecessors, successors
```
Dates formatted `%d-%m-%Y`. This is only what gets written when a file is uploaded with `data_format=nusf`.

### 2.3 "Raw" mode CSV row on the wire (`src/pdf_processor.py`, via `rows_to_compact_csv_chunks`)

**Original source headers, unmodified** — e.g. Danish MS-Project exports keep `Id;Opgavenavn;Varighed;Startdato;Slutdato;% arbejde færdigt`; Plandisc exports keep `name | location_path | task_group_name | planned_start_date | planned_end_date | planned_shift_duration | planned_completion_pct | actual_start_date | actual_end_date | actual_completion_pct | actual_by | is_late | inspectedType | inspected_by | has_constraint | is_flagged`. This is what most uploads produce today, since `data_format` defaults to `"raw"`.

### 2.4 Re-parsed row at analysis time (`parse_nusf_chunks`, `nusf_compare_engine.py:113-144`)

Re-normalizes whatever header string is present (canonical or raw-original) through its own `_norm_header`, builds a `dict` per row, adds a synthetic `_identity` key, deduplicates by identity (**last occurrence wins**, insertion-order dependent — see §4.3).

### 2.5 `progress_vs_expected` item (deterministic engine output, `nusf_compare_engine.py:469-479`)

```python
item = {
    "activity": name, "start_date": ..., "finish_date": ...,
    "actual_pct": actual, "expected_pct": expected,
    "variance_pct": variance, "status": status, "late_flag": late_flag,
    **_dashboard_meta(row),
}
```
Only kept if `abs(variance) >= 1 or late_flag` (line 480).

### 2.6 Final HTML table row (`src/version_1_0/adapters.py:72-104`, `_activity_row`)

Reshapes into `task_name`, `phase`, `area`, `trade`, `actual_pct`, `expected_pct`, `deviation`, `status`, plus `old_start/new_start/old_finish/new_finish` used only by the "changed" table variant.

---

## 3. "Ahead" detection — the exact code, in all three places it exists

### 3.1 Deterministic path (`nusf_compare_engine.py:254-268`)

```python
def _expected_progress(start: date, finish: date, ref: date) -> float:
    total_days = max((finish - start).days, 1)
    elapsed_days = (ref - start).days
    return round(max(0.0, min(100.0, (elapsed_days / total_days) * 100.0)), 1)


def _progress_status(actual: float, expected: float, late_flag: bool) -> str:
    if late_flag:
        return "behind"
    variance = actual - expected
    if variance < -5:
        return "behind"
    if variance > 5:
        return "ahead"
    return "on_schedule"
```

This is fine **in isolation**. The problem is upstream: what feeds `actual` into this function.

```python
# nusf_compare_engine.py:441
actual = round(_parse_float(row.get("percent_complete")), 1)
```

`row` here is the dict produced by `parse_nusf_chunks()`, keyed by whatever `_norm_header()` decided each column header meant.

### 3.2 The header-recognition divergence — root cause of the "ahead never detected" symptom

`nusf_compare_engine.py:11-25`:
```python
def _norm_header(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("id", "d i", "entydigt id", "source_id"):
        return "source_id"
    if raw in ("opgavenavn", "opg.navn", "task name", "name", "opgavenavn/aktivitet"):
        return "name"
    if "slutdato" in raw or "planned_finish" in raw or ("finish" in raw and "actual" not in raw) or "end date" in raw:
        return "planned_finish"
    if "startdato" in raw or "planned_start" in raw or ("start" in raw and "actual" not in raw):
        return "planned_start"
    if "varighed" in raw or "duration" in raw:
        return "duration_hours"
    if "%" in raw or "færdigt" in raw or "erdigt" in raw or "complete" in raw:
        return "percent_complete"
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
```

Compare to the **canonical, already-existing** recognizer used at upload time for NUSF-mode uploads, `ingestion/recognition/heuristics.py:110-115`:
```python
"percent_complete": [
    "% arbejde færdigt", "% færdigt", "% complete", "percent complete",
    "fremdrift", "completion", "progress", "actual_completion_pct",
    "pct complete", "pct_complete", "completion %", "fuldført %",
    "fuldfort %", "fuldført", "fuldfort",
],
```
plus fuzzy (Jaro-Winkler, 0.85 threshold) matching on top of the token list.

`_norm_header`'s crude substring check (`"%" in raw or "færdigt" in raw or "erdigt" in raw or "complete" in raw`) **does not match "fremdrift"**, **"progress"**, or any fuzzy variant — it is a literal-substring check with a much smaller vocabulary and no fuzzy matching at all. When the source file's progress column is named something this check doesn't catch:

1. The column keeps its raw, un-normalized key in the row dict (e.g. `row["fremdrift"] = "62"`), and `row.get("percent_complete")` returns `None`.
2. `_parse_float(None)` → default `0.0` (`nusf_compare_engine.py:36-40`).
3. `actual = 0.0` for every row in that schedule.
4. `variance = 0.0 - expected`, which is **never positive** (since `expected` is clamped to `[0, 100]`) → `_progress_status` can only return `"behind"` or `"on_schedule"`, **never `"ahead"`**.
5. Meanwhile `"behind"` detection still fires — often over-aggressively, since every activity now looks like it has 0% actual progress regardless of the truth.

This precisely reproduces the reported symptom: ahead detection silently disappears, behind detection still works (and looks worse than reality), and it is inherently inconsistent — it depends entirely on the literal column name a given source file happens to use. A file whose export tool calls the column `"% Complete"` works fine (matches `"complete" in raw`); a file that calls it `"Fremdrift"` (a common Danish scheduling term) or any of the other canonical-recognizer synonyms silently breaks.

**This same divergence pattern exists for every field `_norm_header` tries to recognize** (`planned_start`, `planned_finish`, `duration_hours`, `name`, `source_id`) — it is a smaller, independently-maintained, non-fuzzy subset of `ingestion/recognition/heuristics.py`'s token lists. Any of them can silently fail the same way; `percent_complete` is simply the one whose failure mode maps directly onto "ahead never appears."

### 3.3 A second, related header bug: `planned_end_date` vs `planned_finish`

Plandisc-format files (confirmed real column name, `src/predictive_agent.py:418`) use **`planned_end_date`** literally as a header. Walk it through `_norm_header`:

- `"planned_finish" in raw`? No (`"planned_end_date"` does not contain the substring `"planned_finish"`).
- `("finish" in raw and "actual" not in raw)`? No (`"finish"` is not a substring of `"planned_end_date"`).
- `"end date"` (**with a space**) `in raw`? No — the actual header has an **underscore**, `"planned_end_date"`, not a space.

So none of the `planned_finish` branches match, and `_norm_header` falls through to its generic slugifier, returning the header unchanged as `"planned_end_date"`.

But `_is_nusf_header()` (`nusf_compare_engine.py:95-101`) explicitly whitelists `"planned_end_date"` as an acceptable literal alongside `"planned_finish"` when deciding whether a chunk *looks like* NUSF:
```python
def _is_nusf_header(parts: list[str]) -> bool:
    headers = {_norm_header(part) for part in parts}
    return "name" in headers and (
        "stable_key" in headers or "source_id" in headers
    ) and (
        "planned_finish" in headers or "planned_end_date" in headers
    )
```
So the chunk **passes** the "is this NUSF?" gate — but every row dict built afterward stores the value under the key `"planned_end_date"`, not `"planned_finish"`. Every downstream consumer (`compare_nusf_chunks`, e.g. `nusf_compare_engine.py:440`: `finish = _parse_date(row.get("planned_finish"))`) looks up `"planned_finish"` and gets `None`. Since `if start and finish:` gates almost everything (§2.5, line 465 `if start and finish and start <= ref:`), **the entire `progress_vs_expected` list stays empty for that schedule** — not just "ahead" rows, everything. This is a distinct but related failure from §3.2, triggered specifically by Plandisc-sourced raw-mode uploads.

### 3.4 LLM-prompt path (used whenever `parse_nusf_chunks` returns empty rows and `require_nusf` is false)

`src/experimental/compare_v4_agent.py:477-487` — this is **prompt text sent to the model**, not code:
```
=== SECTION 4: progress_vs_expected — MANDATORY, DO NOT SKIP ===
For EVERY in-scope activity in the NEW schedule that has a start_date and finish_date:
  Step 1: Parse reference_date, start_date, finish_date as DD-MM-YYYY.
  Step 2: elapsed_days = reference_date - start_date (in calendar days).
  Step 3: total_days = finish_date - start_date (in calendar days).
  Step 4: expected_pct = (elapsed_days / total_days) × 100, clamped to [0, 100].
  Step 5: actual_pct = the % complete value from the NEW schedule data.
  Step 6: variance_pct = actual_pct - expected_pct (negative means behind schedule).
  Step 7: status = "behind" if variance_pct < -5, "ahead" if variance_pct > 5, else "on_schedule".
```
Same threshold semantics as the deterministic engine — but **nothing in Python re-derives or checks this**. `_postprocess_v3` (`src/experimental/compare_v3_agent.py:158-230`) only re-filters by scope and re-counts; the `status` string on each row is trusted verbatim from the LLM's JSON output. Any prompt drift, date-parsing mistake (explicitly flagged as a risk at `compare_v4_agent.py:444-445`, DD-MM-YYYY vs MM-DD-YYYY ambiguity), or plain model inconsistency across runs (even with `temperature=0, seed=42` — Azure OpenAI's `seed` is best-effort, not a hard determinism guarantee) changes what "ahead" means from one run to the next.

### 3.5 What's confirmed *not* the bug

- **Tone/CSS mapping**: `_tone_class` (`formatters.py:23-32`) maps `"green"` correctly to `.ni-green`, which exists in the CSS block; the `ahead_table` section icon is configured green (`formatters.py:296`). No rendering-layer bug.
- **Localization**: `localization.py` and `formatters.py:223-248` (`_display_status`) both have consistent `"ahead"/"Ahead"/"Foran"` entries; every status lookup site normalizes with `.lower()` before comparing. No en/da string-matching bug (unlike the pattern that motivated the earlier Danish-localization commit for v5/v5-graph — this was specifically checked for and ruled out here).
- **KPI computation**: `adapters.py:294` (`ahead = [...]`) and `adapters.py:375` (`"ahead_schedule"` KPI) correctly derive from whatever `status` values are present — they are a faithful downstream reflection of whatever the upstream analysis produced, not an independent source of error.

---

## 4. Why it's *inconsistent* (not just "ahead is broken")

1. **Three independent classifiers, runtime-selected.** Whether the deterministic engine (§3.1-3.3) or the LLM path (§3.4) executes depends on whether `parse_nusf_chunks()` happens to recognize enough of a given file's headers — which depends entirely on that file's specific column-naming convention. Two schedules from different export tools (or even the same tool with a slightly different locale/version) can take different code paths for what the user experiences as "the same feature."
2. **LLM non-determinism in the fallback path.** `temperature=0, top_p=0.1, seed=42` is set (`compare_v4_agent.py:578-581`) but Azure OpenAI does not guarantee bit-identical output across calls even with a fixed seed; borderline activities near the ±5pp threshold can flip between runs.
3. **Deduplication order-dependence.** `_deduplicate_rows` (`nusf_compare_engine.py:104-111`) keeps the **last** occurrence of a duplicate `_identity` key, with no explicit ordering contract from `vector_store_manager.fetch_all_from_stores`. If chunk fetch order isn't stable across requests, which row's `percent_complete`/dates "win" for a duplicate activity can vary between otherwise-identical runs.
4. **`reference_date` defaults to `"Unknown"` and silently falls back to data-inference.** `src/main.py:1891` (`Form(None)`) → `nusf_compare_engine.py:392-393`: `ref = _parse_date(reference_date) or _infer_ref_date_from_data(new_rows)`. A wrong, stale, or missing `reference_date` systematically skews `expected_pct` for every activity project-wide, silently — no error, no warning, just quietly wrong `variance_pct` and therefore wrong `status`.
5. **Global fractional-progress rescale heuristic.** `_rescale_progress_if_fractional` (`nusf_compare_engine.py:281-294`) scans **all rows in a schedule together** and multiplies every `percent_complete` by 100 if the max nonzero value across the whole file is `≤ 1.0`. A single legitimately-low value (e.g. `1.0` meaning "1% complete") among mostly-zero rows can falsely trigger a global rescale that corrupts every activity's `actual_pct` at once.
6. **Asymmetric error handling around LLM enrichment.** `compare_v5_graph_agent.py:238-249` calls an LLM enrichment step after the deterministic facts are computed; if it throws, the exception is caught and logged server-side only (line 248-249) — the dashboard silently reverts to "deterministic-only" content with no indication to the caller that enrichment (project-health override, critical-path inference) didn't run that time.

---

## 5. Concrete bug list

| # | File:Line | Bug |
|---|---|---|
| 1 | `src/experimental/nusf_compare_engine.py:23-24` (`_norm_header`) | `percent_complete` recognition is a small substring check missing synonyms (`"fremdrift"`, `"progress"`, etc.) that the canonical `ingestion/recognition/heuristics.py:110-115` already knows. When missed, `actual_pct` reads as `0.0` for the whole schedule → "ahead" becomes mathematically impossible while "behind" still fires. **Primary suspect for the reported symptom.** |
| 2 | `src/experimental/nusf_compare_engine.py:11-25` vs `ingestion/recognition/heuristics.py` | Two independently-maintained header-recognition implementations for the same concept (NUSF field mapping) — one fuzzy (Jaro-Winkler 0.85) with a rich token list, one crude substring-only with a small list. Structural cause of #1 and of general inconsistency. |
| 3 | `src/experimental/nusf_compare_engine.py:17-20,95-101` | `_norm_header` doesn't map the real-world header `"planned_end_date"` (Plandisc format, confirmed at `src/predictive_agent.py:418`) to `"planned_finish"`, but `_is_nusf_header` explicitly accepts `"planned_end_date"` as a valid NUSF signal. Result: chunk passes the NUSF gate, but every row's `finish` resolves to `None` downstream, and `progress_vs_expected` stays empty for the entire schedule (not just "ahead" — everything). |
| 4 | `src/main.py:505` (`data_format: str = Form("raw")`) + `src/main.py:1922-1923` | Upload defaults to `"raw"` mode, not `"nusf"`. The deterministic, testable engine (`nusf_compare_engine.py`) is opt-in, not the default — most uploads are eligible to fall into the LLM-prompt path or the raw-header-guessing gap above unless the frontend explicitly requests NUSF mode. |
| 5 | `src/experimental/compare_v5_graph_agent.py:204-259` | Silent fallback from the deterministic path to the LLM-prompt path whenever `parse_nusf_chunks` returns empty rows for either schedule and `require_nusf` is `False` — no warning surfaced in the API response about which engine actually ran. |
| 6 | `src/experimental/compare_v4_agent.py:477-487` (prompt) vs `nusf_compare_engine.py:260-268` (code) | Same ±5pp threshold logic duplicated once as Python, once as an LLM instruction with zero server-side verification of the LLM's `status` output. Drift between the two is inevitable and undetectable without cross-checking. |
| 7 | `src/experimental/nusf_compare_engine.py:443,260-262` | `is_late` (Plandisc-only field) unconditionally forces `"behind"` regardless of variance. If the fuzzy recognizer at upload time (`ingestion/recognition/heuristics.py:154-156`, tokens `["is_late","late","forsinket flag"]`, 0.85 threshold) mismaps an unrelated column onto `is_late`, any truthy value there silently overrides a legitimate "ahead" classification. |
| 8 | `src/experimental/nusf_compare_engine.py:104-111` (`_deduplicate_rows`) | "Last occurrence wins" with no guaranteed fetch ordering from `vector_store_manager.fetch_all_from_stores` — reproducibility issue for schedules with duplicate identity keys. |
| 9 | `src/experimental/nusf_compare_engine.py:392-393` | `reference_date` silently falls back to `_infer_ref_date_from_data` (max date in the new schedule) instead of failing loudly on a missing/bad input — skews every activity's expected-progress calculation without any visible warning. |
| 10 | `src/experimental/nusf_compare_engine.py:281-294` (`_rescale_progress_if_fractional`) | Whole-schedule heuristic rescale triggered by a single low value among the rows; can corrupt `actual_pct` for an entire schedule at once. |
| 11 | `src/experimental/compare_v3_agent.py:158-230` | No server-side recomputation of the LLM-produced `status` field in the fallback path — only counts are re-derived; the actual "ahead"/"behind" label is 100% LLM-trusted. |

---

## 6. What can be improved (refactor direction)

The user's instinct to refactor "upload → NUSF generation → analysis → dashboard" as one coherent flow is correct — right now it's two flows (raw-mode ad-hoc chunking vs. canonical `ingestion/` NUSF pipeline) that both feed into one analysis layer that itself has two more branches (deterministic vs. LLM). Recommended direction:

1. **One header-recognition implementation.** Delete `nusf_compare_engine._norm_header` and its duplicated logic; make every upload path — raw or explicit-NUSF — go through `ingestion/recognition/heuristics.py` (+ AI fallback) before it's ever stored. `parse_nusf_chunks` should only ever have to read canonical, already-normalized field names, never guess again.
2. **Make NUSF the only storage format**, or at minimum flip the default (`src/main.py:505` and siblings) so canonical normalization is the default and "raw passthrough" is the deliberate exception, not the other way around.
3. **Single source of truth for ahead/behind classification.** Keep `_progress_status`/`_expected_progress` as the only implementation; if an LLM path is still wanted for narrative enrichment, have it consume already-computed deterministic facts (the way `compare_v5_graph_agent._analyze_nusf_with_llm` already does for `project_health`/`critical_path_activities`) rather than re-deriving `status` itself in a prompt.
4. **Fail loudly, not silently.** Any point where the pipeline currently falls back (NUSF parse failure → LLM path; missing `reference_date` → inferred date; enrichment LLM call throws) should surface a visible `data_quality_warning` in the dashboard response (the mechanism already exists at `nusf_compare_engine.py:575-580` — extend its coverage) instead of just logging server-side.
5. **Add contract tests** for `to_nusf_chunks(schedule) → parse_nusf_chunks(chunks)` round-tripping, and golden tests for `_progress_status` covering the ±5 boundary, `late_flag` interaction, and the fractional-rescale heuristic. None of this currently appears to have automated coverage — verify before refactoring so regressions are caught immediately rather than reported by users again.
6. **Scope the fractional-rescale heuristic** per-row-confidence or require a minimum sample size, instead of a single global `max()` check across an entire schedule.
7. **Consolidate row-shaping logic.** `_dashboard_meta` (`nusf_compare_engine.py:219-234`) and `_activity_row` (`adapters.py:72-104`) both independently guess/fallback across similarly-named fields (`resource`/`responsible`/`discipline`, etc.) — build the final row shape once, at analysis time, not twice.

---

## 7. Running the server locally (for testing this refactor)

- **Entrypoint**: `src.main:app` (the FastAPI app). Note: there is an empty `main.py` at the repo root — that is *not* the entrypoint, don't confuse it with `src/main.py`.
- **Python**: 3.12 works with the existing `.venv`; `pyproject.toml` requires `>=3.11`; Docker/Replit use 3.11 explicitly. Minor version mismatch between local `.venv` and deployment target — not blocking for local dev/test, but keep in mind if you hit a dependency incompatibility.
- **⚠️ Known-broken `.venv`**: this repo's `.venv` was copied from a different project (`nova-ai-backend-bridge`) rather than created fresh here. `source .venv/bin/activate` and the `pip`/`pip3` console scripts have hardcoded shebangs pointing at that other project's (now-deleted) venv path, so activation silently falls through to the **system** Python/pip, which then hits PEP 668's `externally-managed-environment` guard. Worse: even `python3` alone can silently resolve to a *different* broken environment (e.g. `~/.local/lib/python3.12/site-packages`, a stray user-level pip install) that has some but not all deps (`ModuleNotFoundError: No module named 'fastapi'` even though `uvicorn` imports fine) — always use the **explicit path** `.venv/bin/python`, never bare `python`/`python3`/`pip` after activating, and don't rely on `source .venv/bin/activate` for PATH correctness. (Fix properly later by recreating the venv in place: `rm -rf .venv && python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`.)
- **⚠️ JVM required at startup, not just for `.mpp` uploads**: `src/main.py`'s FastAPI `lifespan` hook unconditionally calls `start_jvm_if_needed()` (`src/jvm_init.py:22-38`), which starts a JVM via `jpype` using JAR files bundled with the `mpxj` package (used to parse MS Project `.mpp` files). If no JVM is installed, **the app fails to start at all** — every endpoint, not just MPP-related ones — with `jpype._jvmfinder.JVMNotFoundException: No JVM shared library file (libjvm.so) found`. The `Dockerfile` avoids this by building on `eclipse-temurin:17-jdk-jammy`; locally you need a JDK installed: `sudo apt install -y openjdk-17-jdk` (or matching version), then verify with `java -version` before starting the server.

### 7.1 One-time setup

```bash
cd /home/abaan/work/gac/nova/projects/nova-insights/rag-agent/backend
sudo apt install -y openjdk-17-jdk                     # required — app won't boot without a JVM, see above
.venv/bin/python -m pip install -r requirements.txt    # do NOT use bare `pip` or `source .venv/bin/activate`
```

### 7.2 Environment variables

`.env` already exists at the repo root with the required values. Variables the app needs at minimum:
```
SUPABASE_URL
SUPABASE_SERVICE_KEY
SUPABASE_DB_HOST
SUPABASE_DB_PASSWORD
SUPABASE_POOLER_URL
DATABASE_URL
AZURE_OPENAI_API_KEY
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_EMBEDDING_DEPLOYMENT
AZURE_OPENAI_CHAT_DEPLOYMENT
AZURE_OPENAI_PREDICTIVE_DEPLOYMENT
AZURE_DOC_INTELLIGENCE_ENDPOINT
AZURE_DOC_INTELLIGENCE_KEY
SESSION_SECRET
JWT_SECRET
```

### 7.3 Run (dev, with autoreload — matches the Replit workflow config in `.replit`)

```bash
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 5000 --reload
```

### 7.4 Run (production-style, matches `Dockerfile` / gunicorn — what the user meant by "unicorn server")

```bash
.venv/bin/python -m gunicorn src.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 2 \
  --bind 0.0.0.0:8000 \
  --timeout 180 \
  --keep-alive 5
```
(`Dockerfile` uses port 8000; `.replit` deployment config uses port 5000, 1 worker, 300s timeout — either works locally, pick a free port. Same broken-`.venv` caveat as §7.1 applies — invoke as `.venv/bin/python -m gunicorn`, not bare `gunicorn`.)

### 7.5 Smoke-testing the bug

1. Start the server (§7.3).
2. `POST /upload` twice (old + new schedule) — first with the default form (`data_format` omitted → `"raw"`), then repeat with `data_format=nusf` explicitly set, using the **same two source files**.
3. Poll `GET /upload/progress/{upload_id}` until `status == "complete"` for both.
4. Call `POST /version-1.0/health` for each session, once with no `data_format` override (inherits whatever was stored at upload) and once with `data_format=nusf` forced.
5. Compare the two `json_data.progress_vs_expected` arrays — under the bug described in §3.2/§3.3, the "raw" run should show zero or unexpectedly few "ahead" entries (or an empty `progress_vs_expected` entirely, for Plandisc-style headers) while the "nusf" run should classify correctly. This isolates whether a given source file is hitting the header-recognition gap.
6. Cross-check by adding a temporary log line at `nusf_compare_engine.py:441` (`actual = round(_parse_float(row.get("percent_complete")), 1)`) to print the raw header list from `parse_nusf_chunks` alongside `row.keys()` for the first few rows — if `"percent_complete"` isn't a key, that's the confirmation.
