# Phase 1 — Provenance & OCR confidence

**Goal.** Stop discarding evidence. Every critical value should know where it came
from and how well it was read.

**User-visible change.** None. This phase only captures and stores; nothing is
displayed until Phase 7.

**Key finding this phase acts on.** Azure `prebuilt-layout` returns a `confidence`
value per word and a `boundingRegions[].polygon` per cell. `src/azure_ocr.py::_parse_tables`
reads only `content`, `rowIndex`, `columnIndex`, `rowSpan`, `columnSpan`, `kind`,
and `boundingRegions[].pageNumber`. **Every confidence value and every polygon is
discarded at the point of extraction.** Brief §6 opens with "you already discussed
this — now make it systematic"; in the code, none of it is captured at all.

---

### TL-1.1 — Extend the `Provenance` model with evidence fields ✅ DONE

**Brief:** §5, §6 · **Blocked by:** TL-0.3 · **Blocks:** TL-1.2, TL-1.6 · **Status:** DONE (2026-08-24) — see `PROGRESS.md`, ADR-009

**Why.** A `Provenance` model already exists (`ingestion/models/nusf.py`) with
`source_field`, `source_row`, `is_ai_inferred`, `confidence`. Brief §6 requires
`raw_value`, `normalized_value`, `ocr_confidence`, `page_number`, `bounding_box`,
`source_document`. Extend the existing model — see ADR-002, we adopt rather than replace.

**Files.**
- `rag-agent/backend/ingestion/models/nusf.py` ✅
- create `rag-agent/backend/tests/trust/test_provenance_fields.py` ✅ (not in original file list; added to encode ACs as runnable tests, same rationale as TL-0.1's `test_harness.py`)

**Do.**
1. Add to `Provenance`, all optional with defaults so nothing existing breaks (D3):
   - `raw_value: Optional[str]` — exactly what was read, pre-normalization
   - `normalized_value: Optional[str]` — what we turned it into
   - `ocr_confidence: Optional[float]` — `None` when not OCR-derived
   - `page_number: Optional[int]`
   - `bounding_box: Optional[list[float]]` — polygon as flat coords
   - `source_document: Optional[str]`
   - `extraction_method: str` — e.g. `ocr_table`, `ocr_text_layer`, `csv_cell`,
     `mpp_field`, `mspdi_field`, `ai_inferred`, `derived`
2. Keep the existing `confidence` field for now — `TL-1.6` disambiguates it.
3. `ocr_confidence is None` must mean "not applicable", never "unknown, assume good".

**Acceptance criteria.**
- [x] All new fields optional with safe defaults; existing construction sites still valid
- [x] `pytest tests/test_nusf_normalization.py -q` still green with no source changes there
- [x] A test asserts `Provenance()` with only the old fields still constructs
- [x] `harness compare` shows no diff

**Verify.** `cd rag-agent/backend && pytest tests/ -q && python -m tests.trust.harness compare`
→ `pytest tests/trust/test_provenance_fields.py -q` → 25 passed (2026-08-24);
`pytest tests/trust/ -q` → 199 passed, 15 subtests passed;
`pytest tests/test_nusf_normalization.py -q` → 3 passed (no source changes there);
`harness compare` → "no regressions", exit 0.

**Do not.** Do not make any new field required. D3 is additive-only.

**Implementation notes.**
- **Field shapes (final):**
  - `raw_value: Optional[str]` — default `None`.
  - `normalized_value: Optional[str]` — default `None`.
  - `ocr_confidence: Optional[float]` — default `None`; bounded `ge=0.0,
    le=1.0` so a supplied out-of-range value is rejected at construction.
    `None` is the load-bearing "not OCR-derived" sentinel; it is never
    coerced to a numeric default. Pinned by
    `TestOcrConfidenceNoneSemantics::test_legacy_construction_does_not_invent_a_confidence`.
  - `page_number: Optional[int]` — default `None`; bounded `ge=1`. Page 0
    is not a page; the model rejects it. Pinned by
    `TestGeometryAndPageFields::test_page_number_must_be_positive`.
  - `bounding_box: Optional[list]` (not `list[float]`) — typed `list` so
    Pydantic accepts whatever shape Azure or test fixtures emit. No arity
    enforcement here; TL-9.1 owns geometry validation. Pinned by
    `TestGeometryAndPageFields::test_bounding_box_accepts_flat_polygon`.
  - `source_document: Optional[str]` — default `None`.
  - `extraction_method: str` — default `"unknown"` (not `None`, not `""`).
    `"unknown"` is the canonical "not yet classified" sentinel per TL-1.5;
    pre-TL-1.5 rows that never set this field will read `"unknown"` after
    this change, flagging them for the TL-1.5 cleanup pass without
    breaking them. The field is `str`, not `Optional[str]`, so `None` is
    not a legal value. Pinned by
    `TestExtractionMethod::test_default_is_unknown` and
    `test_canonical_values_round_trip`.
- **`confidence` is *not* renamed in this task.** `TL-1.6` owns the
  rename to `column_mapping_confidence` and the recognition-vs-value
  disambiguation (the ADR-002 trap). Doing it here would couple two
  tasks that the plan deliberately sequenced (`TL-1.6: Blocked by
  TL-1.1`) and would force this task to update every consumer in the
  same commit. After this task: `confidence` (column-mapping
  recognition confidence) and `ocr_confidence` (per-cell value
  confidence) coexist as independent signals.
- **No call sites touched.** `ingestion/normalization/engine.py`
  constructs `Provenance` objects indirectly through dict-merge and
  keyword arguments; none of those call sites break because every
  new field defaults. `tests/test_nusf_normalization.py` passes
  without source changes (3 passed), confirming the integration
  surface is intact.
- **JSON round-trip is byte-identical** for both new and legacy
  payloads. `TestRoundTripCompatibility` pins this so the D3
  additive-only invariant survives even after future schema growth.
  A pre-TL-1.1 payload (only the four original fields) loads
  cleanly under the new model — Phase 7, 8, 9 will rely on this
  when reading legacy sessions.
- **Discipline tests added beyond the plan's four ACs:**
  `TestNewFieldsAreAdditive` (parametrised per-field round-trip),
  `TestOcrConfidenceNoneSemantics` (boundary, range, and the
  critical `None`-not-invented regression guard),
  `TestGeometryAndPageFields` (page-number positivity, bounding-box
  polygon acceptance), `TestExtractionMethod` (canonical values
  round-trip, extensibility), and `TestRoundTripCompatibility`
  (legacy-payload loadability).

---

### TL-1.2 — Capture Azure per-cell OCR confidence and geometry ✅ DONE

**Brief:** §6 · **Blocked by:** TL-1.1 · **Blocks:** TL-1.3 · **Status:** DONE (2026-08-24) — see `PROGRESS.md`, ADR-010

**Why.** This is the single highest-leverage task in the phase — it is the moment the
evidence currently gets thrown away.

**Files.**
- `rag-agent/backend/src/azure_ocr.py` (`_parse_tables`, `_word_confidences_in_span`, `_derive_cell_confidence`) ✅
- create `rag-agent/backend/tests/trust/test_ocr_confidence.py` ✅ (not in original file list; added to encode ACs as runnable tests, same rationale as TL-0.1's `test_harness.py`)

**Do.**
1. In `_parse_tables`, for each cell also capture:
   - `spans` (offset/length into the document content string)
   - `boundingRegions[].pageNumber` **and** `boundingRegions[].polygon`
2. Azure reports `confidence` on **words**, not table cells. Derive a per-cell
   confidence by resolving the cell's `spans` against `analyzeResult.pages[].words[]`
   and taking the **minimum** word confidence in the span, not the mean — a single
   misread digit in a date ruins the field, and averaging hides it.
3. Where a cell's spans resolve to no words, set `ocr_confidence = None`
   (unknown), never `1.0`.
4. Carry this through the returned table dicts without changing their existing keys.

**Acceptance criteria.**
- [x] Each returned cell carries `ocr_confidence`, `page_number`, `bounding_box`
- [x] Cell confidence is the minimum of its constituent word confidences
- [x] Unresolvable spans yield `None`, and a test asserts this specifically
- [x] Existing consumers of `_parse_tables` are unaffected (`harness compare` clean)

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_ocr_confidence.py -q`
(use a recorded Azure response fixture — do not call the live API in tests)
→ `22 passed` (2026-08-24). Full trust suite `pytest tests/trust/ -q` → `221 passed,
15 subtests passed` (was 199; +22 new). Harness `compare` → "no regressions", exit 0.

**Do not.** Do not average word confidences. Do not default a missing confidence to 1.0 —
that is precisely the "confidently wrong" failure the brief exists to prevent.

**Implementation notes.**
- **Where word confidences come from.** Flattened into a single
  `pages_words` list at the start of `_parse_tables` by iterating
  `analyzeResult.pages[].words[]`. The helper
  `_word_confidences_in_span(offset, length, pages_words)` resolves
  each cell span against this list and returns the word confidences
  whose spans overlap the half-open interval
  `[offset, offset + length)`. The half-open convention means a word
  ending exactly at the span's start (or starting exactly at the
  span's end) is *not* counted — pinned by
  `TestDeriveCellConfidenceHelper::test_word_at_boundary_not_counted`.
- **Why MIN, not MEAN.** The brief's Do-not rule names the failure
  mode: a single misread digit in a date ruins the field, and averaging
  hides it. `TestConfidenceIsMin::test_min_among_mixed_confidences`
  pins this with a cell spanning three words at confidences 0.99 /
  0.71 / 0.85 — the cell reports 0.71, the worst one.
  `TestDeriveCellConfidenceHelper::test_min_is_taken_not_mean` is a
  direct helper-level pin.
- **Why MIN, not MAX either.** MAX would over-trust an isolated clean
  read surrounded by garbage. MIN is the conservative choice that
  surfaces any single degraded word — the right policy for a trust
  layer. The Trust Engine (`TL-4.3`) owns the cross-field combination
  policy; TL-1.2 only produces the per-cell value-level signal.
- **`None` is load-bearing.** Five distinct "unresolvable" cases all
  return `None`, never `0.0` or `1.0`. Pinned by
  `TestUnresolvableYieldsNone` and `test_none_is_never_coerced_to_one`:
  (1) no `spans` on the cell, (2) spans resolve to no words, (3) every
  overlapping word omitted its confidence, (4) the page has no
  `words[]` at all, and (5) zero-length span. The brief's "Do not
  default a missing confidence to 1.0" rule is the explicit failure
  mode this avoids.
- **Cell shape is additive (D3).** Every new key (`spans`,
  `page_number`, `bounding_box`, `ocr_confidence`) is a fresh key on
  the cell dict; no existing key was renamed, removed, or retyped.
  `test_cell_keeps_all_pre_tl_1_2_keys` and
  `test_table_envelope_keeps_all_keys` pin this. The harness `compare`
  runner is the end-to-end check that downstream consumers (none of
  which were touched in this task) still work — `compare` reports
  "no regressions" because every existing field on every baseline
  fixture's parsed table still has the same value.
- **`bounding_box` is the cell-level polygon, not the table-level.**
  Azure reports `boundingRegions` at both levels. The cell-level one
  is what `TL-9.1` (Click-into-evidence) will draw a rectangle
  around. If the cell has no `boundingRegions`, both `page_number`
  and `bounding_box` are `None` rather than falling back to the
  table-level `boundingRegions` — table-level fallback would imply
  cells inherit the table's polygon, which is not true for
  multi-table pages.
- **`_word_confidences_in_span` is a separate helper.** Unit-tested
  directly in `TestDeriveCellConfidenceHelper`, which is the right
  level for the half-open interval decision and the "word without
  `confidence` is silently skipped" rule. The integration tests in
  `TestConfidenceIsMin` and `TestUnresolvableYieldsNone` confirm the
  helper composes correctly under the public API.
- **Multi-span cells.** Azure can return a cell with multiple
  `spans[]` entries (non-contiguous content). The min is taken
  across *all* spans, not per-span — pinned by
  `TestConfidenceIsMin::test_min_across_multiple_spans`.
- **No live Azure calls in tests.** Every test drives `_parse_tables`
  against a synthetic recorded-response dict. The
  `AzureDocumentIntelligence.__new__` constructor bypass in
  `_make_instance()` is intentional: `_parse_tables` is a method
  that touches `self` only via the static helpers, so no Azure
  credentials are needed for these tests. The live-API check in
  `__init__` stays exactly where it is; future tests that need to
  exercise `_submit_pdf` / `_poll_results` are out of scope for
  this task.

---

### TL-1.3 — Unify the two duplicate Azure OCR implementations ✅ DONE

**Brief:** §6, §41 · **Blocked by:** TL-1.2 · **Blocks:** TL-1.4 · **ADR required (Q-1)** · **Status:** DONE (2026-08-24) — see `PROGRESS.md`, ADR-011. Resolves Q-1.

**Why.** There are two independent Azure Document Intelligence implementations:
`src/azure_ocr.py` (used by the raw path) and `ingestion/extractors/pdf.py` (used by
the NUSF pipeline, deliberately not importing from `src/`). They duplicate submit,
poll, and table-parsing logic. Adding confidence capture to only one means half the
pipeline stays blind, and the two will drift.

**Files.**
- create `rag-agent/backend/ocr_client/__init__.py` ✅
- create `rag-agent/backend/ocr_client/azure.py` ✅ (shared submit / poll / parse / confidence helpers)
- `rag-agent/backend/src/azure_ocr.py` ✅ (now a thin wrapper with shim methods for backwards compat)
- `rag-agent/backend/ingestion/extractors/pdf.py` ✅ (now imports from `ocr_client`; `_extract_text_layer` rewritten to emit rich cells)
- create `rag-agent/backend/tests/trust/test_ocr_unified.py` ✅ (not in original file list; added to encode ACs as runnable tests, same rationale as TL-0.1's `test_harness.py`)

**Do.**
1. Decide and record in `DECISIONS.md` (resolves `Q-1`): extract a shared OCR client
   module both can depend on, **or** deliberately mirror the capture logic in both.
   Recommended: extract a shared module placed so `ingestion/` can import it without
   depending on `src/` — that import boundary exists on purpose.
2. Implement the decision so both paths emit identical provenance-bearing cell dicts.
3. The text-layer fallback (`_extract_text_layer`, pdfplumber) has no OCR confidence.
   Mark those fields `extraction_method="ocr_text_layer"`, `ocr_confidence=None`,
   and record that this path is unrated rather than trusted.

**Acceptance criteria.**
- [x] Both OCR paths produce cells carrying the same provenance fields
- [x] A test runs one recorded response through both paths and asserts identical provenance
- [x] The pdfplumber fallback emits `ocr_confidence=None`, never a fabricated value
- [x] ADR recorded resolving `Q-1`; `Q-1` marked resolved in `PROGRESS.md`

**Verify.** `cd rag-agent/backend && pytest tests/trust/ -q && python -m tests.trust.harness compare`
→ `pytest tests/trust/test_ocr_unified.py -q` → 21 passed (2026-08-24).
Full trust suite `pytest tests/trust/ -q` → 242 passed, 15 subtests passed
(was 221; +21 new). Harness `compare` → "no regressions", exit 0.

**Do not.** Do not make `ingestion/` import from `src/`. That boundary is intentional
(the v2 router is dependency-injected specifically to preserve it).

**Implementation notes.**
- **Shared `ocr_client` package at the top level.** `ocr_client/`
  sits at `rag-agent/backend/` (next to `src/`, `ingestion/`,
  `tests/`), not under either of those two. This placement is the
  whole point of the package: `src.azure_ocr` and
  `ingestion.extractors.pdf` both depend on it, and neither
  depends on the other. The dependency graph stays acyclic —
  `ocr_client` knows nothing about either consumer, and the v2
  router's intentional `ingestion/ → no → src/` boundary is
  preserved. Pinned by `TestBothPathsUseOcrClient` (structural
  import assertions) and `TestNoInverseDependency` (defence-in-depth
  that `ocr_client` does not import either consumer).
- **`AzureDocumentIntelligence` keeps shim methods.** Pre-TL-1.3
  tests and any external caller of `AzureDocumentIntelligence` use
  the instance method `_parse_tables`, `_word_confidences_in_span`,
  `_derive_cell_confidence`, `_submit_pdf`, and `_poll_results`.
  These methods now delegate to `ocr_client.*` (the same function
  objects) so pre-TL-1.3 tests pass without churn. The class's
  public API (`extract_from_pdf`, `check_credentials`) is unchanged.
  The shim layer is a thin pass-through — no behaviour divergence.
- **`_extract_text_layer` returns rich cells, not just strings.**
  Previously it returned `(headers, rows)` of strings. After TL-1.3
  it returns `(headers, rows, cells)` where `cells` is a parallel
  2D grid of provenance-bearing cell dicts. Each cell carries
  `extraction_method="ocr_text_layer"`, `ocr_confidence=None`,
  `page_number`, `bounding_box=None`, `spans=None`, plus the source
  field, raw value, and source document. Downstream
  `Provenance` construction (TL-1.4) reads `cells` to populate the
  right `extraction_method` and `None` `ocr_confidence` for
  unrated values.
- **`PDFExtractor.extract_from_bytes` return shape gains `cells`.**
  When OCR succeeds, `cells` is `None` (OCR cells live in the OCR
  table dict, not in the BaseExtractor return shape). When the
  text-layer fallback fires, `cells` is the rich grid. This is
  additive; pre-TL-1.3 consumers that read `headers` / `rows` /
  `source_system` / `file_name` / `raw_text` are unaffected.
- **`_make_textlayer_cell` is the helper.** Direct unit tests in
  `TestTextLayerFallbackEmitsNone` pin the provenance fields
  regardless of input. The "no fabricated confidence" guard is
  explicit: `test_no_fabricated_confidence_anywhere` checks every
  canonical `source_field` and confirms `ocr_confidence` is `None`
  and not in `{0.0, 0.5, 0.99, 1.0}`. This is the regression guard for
  the same anti-pattern TL-1.2 caught for OCR cells.
- **Integration tests via `monkeypatch.setattr` on
  `ingestion.extractors.pdf.{submit_pdf, poll_results}` and
  `monkeypatch.setitem(sys.modules, "pdfplumber", ...)` were
  explored but proved flaky under pytest. The standalone
  `_extract_text_layer` tests in `TestTextLayerIntegration` cover
  the same contract — cells are populated correctly when the
  text-layer path runs — without going through layered
  monkeypatching. A code comment in `test_ocr_unified.py`
  documents this and points future tests at the better pattern
  (stubbing `_extract_text_layer` directly).
- **No live Azure calls in tests.** Existing
  `AzureDocumentIntelligence.__new__` constructor bypass is
  preserved; the new `tests/trust/test_ocr_unified.py` adds
  structural identity tests (`TestBothPathsUseOcrClient`) that
  confirm both paths route through `ocr_client` without calling
  any HTTP layer.
- **No schema change.** TL-1.3 is a refactor; `Provenance` is
  unchanged from TL-1.1's extended form. The cell dict shape that
  flows out of `parse_tables` is identical to TL-1.2's. The
  text-layer cell dict shape is new but is *internal to
  `_extract_text_layer`'s return value*, not part of `Provenance`
  — TL-1.4 is what decides how those keys map into `Provenance`
  fields.

---

### TL-1.4 — Thread cell confidence into field-level provenance ✅ DONE

**Brief:** §6, §14 · **Blocked by:** TL-1.3 · **Blocks:** TL-1.5 · **Status:** DONE (2026-08-24) — see `PROGRESS.md`, ADR-012

**Why.** Cell-level confidence is useless until it is attached to the *semantic field*
it became. The join point is the normalization engine, where a raw row plus a column
map becomes an `Activity`.

**Files.**
- `rag-agent/backend/ingestion/extractors/pdf.py` (`_detect_header_row`, `_tables_to_headers_and_rows`, `_build_unified_ocr_cell`, `extract_from_bytes`) ✅
- `rag-agent/backend/ingestion/normalization/engine.py` (`_build_field_provenance` helper, `normalize()` cell-aware Provenance construction) ✅
- create `rag-agent/backend/tests/trust/test_provenance_threading.py` ✅ (not in original file list; added to encode ACs as runnable tests, same rationale as TL-0.1's `test_harness.py`)

**Do.**
1. Make extractors return, alongside `rows`, a parallel structure of per-cell provenance
   (or rows of cell objects rather than bare strings — pick one and record it).
2. In `normalize()`, when writing each field, populate `Provenance` with the originating
   cell's `ocr_confidence`, `page_number`, `bounding_box`, `raw_value`, plus the
   `normalized_value` actually stored.
3. Non-OCR sources (CSV/MPP/MSPDI) set `ocr_confidence=None` with the appropriate
   `extraction_method` — handled fully in `TL-1.9`.

**Acceptance criteria.**
- [x] For a PDF fixture, `activity.provenance["planned_start"].ocr_confidence` is a real number
- [x] `raw_value` differs from `normalized_value` wherever normalization changed it (e.g. date reformatting)
- [x] `page_number` and `bounding_box` are populated for OCR-derived fields
- [x] `harness compare` shows no change to any computed result

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_provenance_threading.py -q`
→ `19 passed` (2026-08-24). Full trust suite `pytest tests/trust/ -q` →
`261 passed, 15 subtests passed` (was 242; +19 new). `harness compare` →
"no regressions", exit 0.

**Do not.** Do not let provenance construction throw. A missing cell reference degrades
to `None` provenance; it must never fail an otherwise good ingest.

**Implementation notes.**
- **Cells are a parallel 2D grid to `rows`.** TL-1.4 picks the
  `rows[output_row_idx][col_idx] → cell_dict | None` shape over a
  flat `[(row_idx, col_idx, cell_dict)]` shape because it matches
  what `_extract_text_layer` already produces (TL-1.3) and it lets
  the normalization engine use `cells[row_idx][col_idx]` as a
  single lookup, mirroring how `rows[row_idx][col_idx]` is read.
  Trade-off: empty positions must be explicitly `None` (rather
  than "missing"), but Pydantic-friendly and trivially indexable.
- **`_tables_to_headers_and_rows` now returns 3-tuple.** The merge
  logic was extended to build `all_cells` in parallel to
  `all_data_rows`. The cell at `(output_row_idx, canonical_col_idx)`
  is computed by: (a) tracking which input row produced each
  contributed row via the merge loop, (b) reconstructing the
  original row index using `header_row_idx` (which `_detect_header_row`
  now exposes as a third return value), and (c) placing each
  cell from `table["cells"]` at the canonical column position
  via a reverse-mapped `col_map`. Pinned by `test_provenance_threading.py`'s
  harness compare (`no regressions`) — the merge change is
  non-trivial and any drift would surface there.
- **`_detect_header_row` exposes `header_row_idx`.** TL-1.4 changed
  the signature from 2-tuple to 3-tuple `(header_row, data_rows,
  header_row_idx)`. The other caller of `_detect_header_row` lives
  in `src/pdf_processor.py` and is a separate function (this PDF
  helper is local to `ingestion/extractors/pdf.py`); only the
  one in-pipeline caller needed updating.
- **`_build_unified_ocr_cell` is the cell-shape transformer.**
  Defined in `pdf.py`, takes an OCR cell dict from `parse_tables`
  and produces the unified shape that flows into
  `_tables_to_headers_and_rows`. The output mirrors
  `_make_textlayer_cell`'s shape (TL-1.3), so the normalization
  engine looks up cells from either path with the same logic.
  TL-1.2 evidence fields (`ocr_confidence`, `page_number`,
  `bounding_box`, `spans`) pass through verbatim, including
  load-bearing `None` sentinels (ADR-010).
- **`_build_field_provenance` is the engine-side helper.** Module-
  level, so the closure does not get recreated per loop iteration.
  Returns a cell-evidence Provenance when the cell at
  `(row_idx, col_idx)` exists; otherwise the legacy four-field
  shape (plus `raw_value` / `normalized_value` so AC2 always
  holds). Critically: never throws. A missing cell, a missing
  column, or a missing `cells` array all degrade silently.
  Pinned by `TestBuildFieldProvenanceHelper`.
- **Graceful degradation is layered.** Three failure modes, each
  handled: (a) `cells` is `None` (non-OCR sources pre-TL-1.9,
  legacy data) → legacy fallback; (b) `cells[row_idx][col_idx]`
  is `None` (empty cell position in the merged grid) → legacy
  fallback for that field only, other fields keep cell evidence;
  (c) `field_col` is not in `headers` → legacy fallback. All
  three are explicit tests.
- **`raw_value` / `normalized_value` carry the AC2 invariant.**
  Even on the legacy fallback path, both fields are populated
  with the pre- vs post-normalization distinction. AC2
  ("raw_value differs from normalized_value wherever
  normalization changed it") is satisfied for date reformatting:
  `raw_value="15-01-2026"` → `normalized_value=datetime(2026, 1, 15,
  tzinfo=UTC).isoformat()`. Pinned by
  `TestRawValueVsNormalizedValue::test_date_format_normalization`.
- **Text-layer cells thread the same way.** Text-layer cells
  (TL-1.3) carry `extraction_method="ocr_text_layer"` and
  `ocr_confidence=None`. The `Provenance` carries those values
  verbatim — the "unrated" path is a load-bearing distinction
  (brief §45, ADR-011). Pinned by
  `TestTextLayerCellsThreading`.
- **No harness regression.** The merge-logic changes are the
  riskiest part of this task (every existing fixture runs through
  the merge). `harness compare` → "no regressions" because
  `all_cells` is an additive parallel structure — pre-existing
  fields on every baseline fixture's normalized schedule are
  byte-identical to before. Pinned by
  `TestExistingFixturesStillWork::test_no_cells_no_raw_value_set_to_none_consistently`
  for the model-level invariant.
- **TL-1.5 scope.** This task threads cells into the three fields
  that already got Provenance (`name`, `planned_start`,
  `planned_finish`). TL-1.5 will extend to all critical fields
  (`source_id`, `name`, `planned_start`, `planned_finish`,
  `duration_hours`, `percent_complete` per the spec). The
  `_build_field_provenance` helper is generic over the field; the
  scope extension in TL-1.5 is mechanical.

---

### TL-1.5 — Populate provenance for all critical fields

**Brief:** §6, §8 · **Blocked by:** TL-1.4 · **Blocks:** TL-1.8, TL-1.9

**Why.** Provenance is currently written for exactly three fields — `name`,
`planned_start`, `planned_finish` (`engine.py` ~L295–313) — and falls back to a single
`_row` entry when none of those resolve. Brief §6 names Activity ID, Activity Name,
Start, Finish, Duration and Progress as critical, and §8 insists critical fields carry
stricter requirements than descriptions.

**Files.**
- `rag-agent/backend/ingestion/normalization/engine.py`

**Do.**
1. Write provenance for every critical field: `source_id`, `name`, `planned_start`,
   `planned_finish`, `duration_hours`, `percent_complete`.
2. Write it for secondary fields too where a source cell exists (`discipline`,
   `location_path`, `area`, `floor`, `phase`, `critical_flag`, `total_float`).
3. Fields that were *computed* rather than read (e.g. duration derived from a date
   delta) get `extraction_method="derived"` and must record what they were derived from.
4. Remove the `_row` catch-all fallback, or keep it only as a genuine last resort with
   `extraction_method="unknown"` — it must not look like real provenance.

**Acceptance criteria.**
- [ ] Every critical field on every activity in every fixture has a provenance entry
- [ ] A test asserts no critical field has provenance with `extraction_method="unknown"` for a clean fixture
- [ ] Derived fields are distinguishable from read fields
- [ ] `harness compare` clean

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_provenance_coverage.py -q`

**Do not.** Do not copy one field's provenance to another for convenience. That is how
the existing `confidence` field became meaningless (ADR-002).

---

### TL-1.6 — Separate recognition confidence from value confidence

**Brief:** §6, §8, §14 · **Blocked by:** TL-1.1

**Why.** `Provenance.confidence` is currently set to `recognition.confidence`
(`engine.py` L300/306/312), which is `mapped_critical / len(CRITICAL_FIELDS)` —
a **column-mapping** score with only four possible values (0, 0.33, 0.67, 1.0),
copied identically to all three fields. It answers "did we recognise which column
this is?", not "did we read this value correctly?". Conflating them means a perfectly
recognised column full of garbled OCR reads as high confidence.

**Files.**
- `rag-agent/backend/ingestion/models/nusf.py`
- `rag-agent/backend/ingestion/normalization/engine.py`
- `rag-agent/backend/ingestion/recognition/heuristics.py`

**Do.**
1. Rename the existing field to `column_mapping_confidence` and document its meaning.
2. Keep `ocr_confidence` (from `TL-1.2`) as the distinct value-level signal.
3. Where the AI fallback recogniser supplied the mapping, `is_ai_inferred=True` must
   already be set — verify it is, and that it survives into the final `Activity`.
4. Update every consumer. There should be no remaining reference to a bare `confidence`
   that could mean either thing.

**Acceptance criteria.**
- [ ] `grep -rn "provenance.*\.confidence" rag-agent/backend` returns no ambiguous uses
- [ ] Both scores are independently readable per field
- [ ] A fixture with a well-recognised column but low OCR quality shows high mapping confidence and low OCR confidence
- [ ] `is_ai_inferred` is true for every field mapped by the AI fallback

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_confidence_separation.py -q`

**Do not.** Do not blend the two into one number here. Combining them is the Trust
Engine's job in `TL-4.3`, and it must be a weakest-link rule, not an average.

---

### TL-1.7 — Field criticality registry

**Brief:** §8 · **parallel-safe**

**Why.** Brief §8: 90% confidence on a description is not equivalent to 90% on an
Activity ID. Criticality must be data, not scattered conditionals.

**Files.**
- create `rag-agent/backend/src/trust/fields.py`

**Do.**
1. Declare `CRITICAL_FIELDS` (Activity ID, name, start, finish, duration, progress) and
   `SECONDARY_FIELDS` (descriptions, notes, metadata), as an explicit registry.
2. Expose `criticality(field) -> Criticality` and per-criticality threshold *hooks*
   (values themselves are calibrated later in `TL-4.7`).
3. Note that `ingestion/recognition/heuristics.py` has its own narrower
   `CRITICAL_FIELDS = {"name", "planned_start", "planned_finish"}` used for
   AI-fallback triggering. Do not silently merge them — they answer different
   questions. Cross-reference both in comments.

**Acceptance criteria.**
- [ ] Registry covers every field in the NUSF `Activity` model
- [ ] Each field maps to exactly one criticality
- [ ] Relationship to the recogniser's `CRITICAL_FIELDS` documented in both places
- [ ] Thresholds are hooks with placeholder values, clearly marked uncalibrated

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_field_registry.py -q`

**Do not.** Do not hard-code final threshold numbers here (brief §7).

---

### TL-1.8 — Persist provenance alongside chunks

**Brief:** §5, §40 · **Blocked by:** TL-1.5 · **ADR required (Q-2)**

**Why.** Provenance computed at ingest and then dropped before storage buys nothing.
Comparison runs later, from stored chunks, and needs the evidence.

**Files.**
- `rag-agent/backend/src/vector_store.py` (`create_store_from_chunks`)
- `rag-agent/backend/src/database.py` (schema)
- `rag-agent/backend/ingestion/normalization/engine.py` (`to_nusf_chunks`, ~L482–563)

**Do.**
1. Decide and record (resolves `Q-2`): provenance in the existing chunk `metadata` JSON
   column, or a dedicated `activity_provenance` table keyed by session + internal_id.
   Recommendation: dedicated table — provenance is per-field and per-activity, and
   stuffing it into chunk metadata will bloat rows the retrieval path reads in full.
2. Implement, keeping the existing chunk format readable by existing code (D3).
3. Provide `load_provenance(session_table, internal_id)` for downstream phases.

**Acceptance criteria.**
- [ ] Provenance survives an ingest → store → fetch round trip
- [ ] Existing sessions without provenance still load and analyse normally
- [ ] Storage cost measured and recorded for the largest fixture
- [ ] ADR recorded resolving `Q-2`

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_provenance_persistence.py -q`

**Do not.** Do not make comparison require provenance. Sessions ingested before this
phase must keep working (D3).

---

### TL-1.9 — Declare provenance in non-PDF extractors

**Brief:** §5, §6 · **Blocked by:** TL-1.5

**Why.** CSV, Excel, MPP and MSPDI read exact values — there is no OCR uncertainty.
That is a *higher* trust state and should be recorded as such, not left blank and
later mistaken for missing evidence.

**Files.**
- `rag-agent/backend/ingestion/extractors/csv.py`
- `rag-agent/backend/ingestion/extractors/excel.py`
- `rag-agent/backend/ingestion/extractors/mpp.py`
- `rag-agent/backend/ingestion/extractors/mspdi.py`

**Do.**
1. Each extractor emits provenance with `ocr_confidence=None` and its own
   `extraction_method` (`csv_cell`, `excel_cell`, `mpp_field`, `mspdi_field`).
2. Record source coordinates that make sense per format: CSV/Excel row + column,
   MPP task UID + field name, MSPDI XML path.
3. `source_document` is the original filename in all cases.

**Acceptance criteria.**
- [ ] Each of the four extractors emits provenance for every field it produces
- [ ] `extraction_method` is distinct per format
- [ ] A test asserts exact-read sources never carry a fabricated `ocr_confidence`
- [ ] `harness compare` clean

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_extractor_provenance.py -q`

**Do not.** Do not set `ocr_confidence=1.0` for exact reads. `None` plus an explicit
method is the honest encoding; `1.0` implies an OCR measurement that never happened.
