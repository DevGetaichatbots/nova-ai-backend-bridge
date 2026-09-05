# Session Summary — Activity Identity Fix + Smart Reference-Date (2026-07-27)

Related reading: `V1_DASHBOARD_PIPELINE_AUDIT.md` documents the same underlying
architectural split (an ad-hoc "OG" `nusf_compare_engine.py` header guesser vs.
the real `ingestion/` recognition pipeline) from a different angle (percent-complete
detection). This session hit the identity/id-matching side of that same split.

Two separate fixes in this session: (1) activity identity assignment (below),
and (2) a smart default for `reference_date` (see "Part 2" near the end) that
came out of testing part 1 against the H8 PDFs and noticing 0 activities ever
showed "ahead of schedule."

## How this started

User ran Azure Document Intelligence OCR on two "Holm 8" construction-schedule
PDFs (`sample-inputs/H8_K20_C11.02_6 ugers plan_Uge 20-27.pdf` and `...Uge 22-29.pdf`)
to inspect pipeline output. That led to inspecting what data looks like right
before the NUSF comparison step, which surfaced a real bug: **activity identity
was being assigned from a column that isn't actually a stable identifier.**

## Root cause

MS Project schedules have two different fields that look similar but aren't:

- **`ID`** — row/display position. Renumbers whenever tasks are added, removed,
  or reordered. Not safe as a cross-version join key.
- **`Unique ID`** (Danish: **`Entydigt ID`**) — assigned once, permanent, safe
  to match across snapshot exports.

The H8 PDF's "6 Ugers plan" Gantt export only prints the transient `Id` column,
never `Entydigt Id`. Proven empirically: cross-referencing the old vs. new PDF
snapshots by raw `Id` showed **40 of 57 shared ids (70%) pointing to a
completely different task** in the new file than in the old one.

By contrast, `sample-inputs/old_holm8.csv` / `new_holm8.csv` do have a genuine
`Entydigt_Id` column — but a separate bug (below) meant it wasn't being
recognized either, causing 100% silent data loss for that format.

## The actual production path (important — discovered mid-session)

Initially assumed the "OG" path was: OCR/CSV → `src/pdf_processor.py` or
`src/main.py:_parse_csv_to_chunks` → raw headers preserved → `nusf_compare_engine.py`.

Backend logs from a real `/version-1.0/health` run proved otherwise: the chunk
headers seen at compare time were the **canonical NUSF field names**
(`source_id;stable_key;name;planned_start;...`), which only
`ingestion/normalization/engine.py::to_nusf_chunks()` (the "v2" ingestion
pipeline) produces. So **production data goes through v2 ingestion before it
ever reaches `nusf_compare_engine.py`**, and v2 was the one erasing the
"was this id actually durable?" signal — writing the raw positional `Id` value
into `stable_key` unconditionally, regardless of source reliability.

## Files changed

### 1. `src/experimental/nusf_compare_engine.py`
The comparison engine used by `/version-1.0/health` (via `compare_v5_graph_agent.py`).

- **`_norm_header()`**: added `entydigt_id`, `unique id`, `unique_id`,
  `unique task id` as aliases for the canonical `source_id` field (fixes the
  `Entydigt_Id` underscore-vs-space mismatch that caused 100% row loss for the
  holm8 CSVs — `old.csv`: 0→311 rows, `new.csv`: 0→407 rows, 0 mismatches
  across 284 shared identities after the fix).
- **`_STABLE_ID_HEADERS`** / **`_POSITIONAL_ID_HEADERS`**: split headers into
  "genuinely durable" (`entydigt id`, `unique id`, ...) vs. "positional, not
  safe to trust" (`id`, `d i`, `source_id`). Note: **`source_id` is
  intentionally in the *positional* set** — it's the literal column name v2
  always uses regardless of underlying reliability, so the name alone can't be
  trusted.
- **`parse_nusf_chunks()`**: tracks whether the detected id column came from a
  stable header; if not, `_identity` (used for old/new activity matching)
  falls back to `name|location_path|planned_start` instead of the raw id.
  Added `_identity_label` (human-readable: `"Faldbeton — 19-05-2022"` instead
  of `"48"`) used by the dashboard's `id` column — this is what a PM now sees
  instead of a meaningless row number.
- **`_dashboard_meta()`**: `"id"` field now returns `_identity_label` (falls
  back to `source_id` only if no label was computed).
- **Bug introduced then caught+fixed in this same session**: an early version
  of the `_STABLE_ID_HEADERS` set included `"stable_key"`, which made
  `_norm_header("stable_key")` return `"source_id"` instead of `"stable_key"` —
  collapsing both CSV columns onto the same dict key. Fixed by removing
  `"stable_key"` from that set (it's a distinct canonical field, handled
  separately in the identity-priority chain, not a header alias).
- **Logging added** (prefixed `[nusf_compare_engine]`, tagged with marker
  `IDENTITY_FIX_2026_07_27`): module-load marker, per-header-detection log
  (`[parse:header]`), per-parse summary (`[parse:summary]` — row counts,
  stable-vs-fallback split, sample id/label), and match-stage summary
  (`[compare:match]` — old/new/matched/added/removed counts).

### 2. `ingestion/normalization/engine.py` (the "v2" pipeline)
- `stable_key` is now only populated when `recognition.match_key` is
  `"entydigt_id"`, `"tbs"`, or `"name_location"` (genuinely durable sources).
  For `"id"`/`"row_index"` match keys (bare positional column, e.g. the H8
  PDF's `Id`), `stable_key` is left empty — `source_id` still keeps the raw
  value for display only.
- `to_nusf_chunks()`: removed the `act.stable_key or act.source_id` fallback
  that was silently re-filling the CSV's `stable_key` column with the
  positional id whenever `stable_key` was empty.

### 3. `src/version_1_0/adapters.py` and `src/version_1_0/formatters.py`
- Logging only (no behavior change), same `IDENTITY_FIX_2026_07_27` marker:
  module-load marker; `_activity_row()` logs first 8 calls (input id/source_id
  → output id); `adapt_health_dashboard()` logs per-section input counts and
  the `changed_activities` grouping-by-`act_id` step; `_render_table()` logs
  row count + first 5 rendered `id` values per table variant (the literal
  values about to be written into `<td>`).
- Also documented (not changed): `adapt_health_dashboard()` groups
  `changed_activities.changes` by `act_id` (`item.get("id") or
  item.get("activity")`, collapsing repeat change-records per activity into
  one row with a `changes_list`) — `progress_vs_expected`/`stage_mismatch`/
  `critical_path_activities` do **not** do this grouping, they pass through
  1:1. This is a real structural difference between "changed activities" and
  other tables, independent of the identity bug.

## Verified

- Full backend test suite: 21/22 pass (`.venv/bin/python -m unittest discover
  -s tests`). The 1 failure (`tests/test_v4.py`,
  `ModuleNotFoundError: src.html_formatter_v4`) is **pre-existing and
  unrelated** — wrong import path, should be `src.experimental.html_formatter_v4`.
- Simulated the exact H8 PDF scenario (bare `Id` column, id `48` = different
  tasks old vs. new) through the real v2-normalize → `to_nusf_chunks` →
  `parse_nusf_chunks` → `compare_nusf_chunks` pipeline: `stable_key` correctly
  empty, identity correctly falls back to name+date, **zero false matches**,
  dashboard `id` field correctly shows `"Faldbeton — 19-05-2022"`.
- Existing test `test_unstable_positional_ids_fall_back_to_name_location_date_matching`
  (predates this session) already covered part of this scenario at the
  `_resolve_activity_matches()` grouping level (name+location, greedy
  date-distance pairing) — that mechanism was already robust independent of
  this fix. This session's fix closes the gap **upstream of it**: getting a
  correct, informative `_identity`/display label in the first place, and
  fixing the two paths (v2 ingestion + holm8 CSV parsing) that were producing
  wrong or totally-dropped data before matching ever ran.

## Known remaining issues (not fixed, out of scope this session)

- `H8_K20_C11.02_6 ugers plan_Uge 20-27.pdf` (the "old" H8 snapshot) still
  parses to **0 rows** end-to-end. Separate bug: Azure OCR embedded literal
  newlines inside a header cell (`"%\ni\nfærdigt"`), and both
  `parse_nusf_chunks()` (line-by-line `content.splitlines()`) and the
  `_data_quality_score()` diagnostic in `src/pdf_processor.py` aren't
  quote-aware across embedded newlines, so the header is never fully
  recognized. Confirmed via `csv.reader` over the whole blob (quote-aware)
  parsing it fine — the bug is in the naive line-split, not the OCR output
  itself.
- `tests/test_v4.py` has a stale import (`from src.html_formatter_v4 import
  format_compare_v4_as_html`); the real module is at
  `src/experimental/html_formatter_v4.py`. Pre-existing, unrelated to this
  session.
- The `changed_activities` grouping-by-`act_id` behavior in
  `adapters.py:adapt_health_dashboard()` (see above) was documented but not
  changed — flagged as a structural quirk worth revisiting if "changed
  activities" ever needs to show every individual field-change as its own row
  instead of grouped-per-activity.

## Test artifacts / reference outputs

Saved under `test_outputs/` (repo-relative, `rag-agent/backend/test_outputs/`):
- `holm8_h8_pipeline/01_raw_ocr/` — raw Azure OCR output (markdown, tables.json, pages.json) for both H8 PDFs.
- `holm8_h8_pipeline/02_extraction_compare/` — structured-table vs. raw-markdown extraction comparison + quality scores.
- `holm8_h8_pipeline/03_csv/` — actual `.csv` files as stored.
- `holm8_h8_pipeline/04_pre_nusf_analysis/` — parsed NUSF rows (post-fix) + `IDENTITY_FIX_SUMMARY.txt`.
- `holm8_csv_pipeline/03_csv_chunks/`, `04_pre_nusf_analysis/` — same stages for `old_holm8.csv`/`new_holm8.csv`, plus `identity_check_summary.txt` (0 mismatches across 284 shared identities post-fix).

## How to spot-check this fix is live in a running deployment

Grep the logs for `IDENTITY_FIX_2026_07_27` — it fires once per process on
import of `nusf_compare_engine.py`, `version_1_0/adapters.py`, and
`version_1_0/formatters.py`. If it never appears, the running process
predates these changes. Then follow `[parse:summary]`'s `sample_identity_label`
through `[_render_table]`'s `sample_ids` for the same request to see the value
at each stage.

---

## Part 2 — Smart default for `reference_date` (same session, later)

### How this started

While spot-checking the identity fix against the two H8 PDFs, noticed
`progress_vs_expected` showed **0 activities "ahead of schedule"** for both
files, every time. Investigated whether that's a bug.

### Root cause

Both H8 PDFs are 2022-dated demo/test schedules. `/version-1.0/health`
(`src/main.py:1885`) accepts an optional `reference_date` form field and
passes `reference_date or "Unknown"` into `compare_v5_graph_agent.analyze()`.
When the caller (e.g. a UI date-picker defaulting to "today") sends an
explicit, parseable date, it was used unconditionally — even when that date
has nothing to do with the schedule being analyzed.

`_progress_status()` (`nusf_compare_engine.py:315`) classifies "ahead" only
when `actual_pct - expected_pct > 5`, and `_expected_progress()`
(line 309) clamps expected progress at 100% once the planned window has
closed relative to the reference date. With `reference_date` = today
(2026) against 2022-dated activities, every activity's window closed years
ago, `expected` clamps to 100% everywhere, and "ahead" becomes mathematically
unreachable — nothing to do with actual project performance. Confirmed by
re-running the classification with a reference date that actually falls
inside the schedule's window: ahead correctly showed 18 activities instead of 0.

There was already a partial smart-default, `_infer_ref_date_from_data()`
(pre-existing), but it only activated when `reference_date` was missing or
unparseable (`ref = _parse_date(reference_date) or _infer_ref_date_from_data(...)`)
— any parseable explicit date, however wrong for the dataset, always won.

### Fix — `src/experimental/nusf_compare_engine.py`

- **`_schedule_date_range(rows)`** (new): earliest `planned_start` .. latest
  `planned_finish` across a schedule.
- **`_resolve_reference_date(reference_date, rows)`** (new): honors an
  explicit `reference_date` only if it falls within the schedule's own date
  range. If it falls outside that range (the UI-default-vs-historical-data
  case), logs it (`[nusf_compare_engine][reference_date]`) and substitutes an
  inferred date instead. Wired in at `compare_nusf_chunks()` in place of the
  old `_parse_date(reference_date) or _infer_ref_date_from_data(new_rows)` line.
  This was a deliberate design choice — asked the user whether an
  out-of-range explicit date should always win, always be overridden, or only
  overridden when out of range; chose the last (out-of-range override).
- **`_infer_ref_date_from_data(rows)`** (rewritten, not just extended):
  previously returned the schedule-wide **max** finish/start date. That's a
  poor anchor for a rolling look-ahead schedule — a handful of long-running
  summary/parent tasks (e.g. one spanning `01-02-22` to `29-06-23`) drag the
  max far past when most short tasks have already finished, so even the
  "smart" fallback still produced `ahead=0`. Now instead computes, per
  activity with `0 < percent_complete < 100`, the date implied by
  `planned_start + percent_complete% × duration`, and takes the **median**
  of those implied "as of" dates — a much better proxy for "when was this
  schedule actually current." Falls back to the old max-date behavior, then
  `date.today()`, only when no activity has usable in-progress data.

### Verified

- H8 PDF `Uge_22-29`, `reference_date="27-07-2026"` (out of range for this
  2022-dated schedule): log confirms override —
  `explicit=2026-07-27 falls outside schedule range [2022-02-01, 2023-12-15]
  — using inferred date 2022-07-16 instead` — and `ahead` goes from **0 → 10**
  out of 350 progress rows, `behind` 347 → 334. Median-based inference
  (2022-07-16) vs. old max-date fallback (2023-12-15) was directly compared;
  the max-date fallback alone still produced `ahead=0` even after the
  out-of-range override fired, confirming the rewrite of
  `_infer_ref_date_from_data` (not just the override logic) was necessary.
- Full test suite: still 21/22 (same pre-existing unrelated `test_v4.py`
  failure as Part 1).
- `build_progress_history_from_nusf_sources()` (`nusf_compare_engine.py:375`)
  has its own, separate `ref = _parse_date(reference_date) or date.today()` —
  intentionally left unchanged. There, `ref` is only a last-resort sort-key
  fallback when a source label has no parseable date; it does not feed into
  any `_expected_progress`/ahead-behind math (that function uses each
  source's own `point_date`, parsed from its label/filename), so it wasn't
  part of this bug.
