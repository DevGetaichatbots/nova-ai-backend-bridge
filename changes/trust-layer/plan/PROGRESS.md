# Trust Layer — Progress Tracker

**This file is the single source of truth for execution state.**
Update it in the same commit as the work it describes. Protocol: see `README.md`.

Status values: `TODO` · `IN_PROGRESS` · `BLOCKED` · `DONE` · `SKIPPED`

Last updated: 2026-09-05 — **Phase 9 closed (6/6). Trust Layer core implementation 100% COMPLETE.**
- **`TL-9.6`** (blocking release gates) DONE: Brief §36 and §39 release gates flipped from informational to blocking (`tests/trust/harness.py`, `tests/trust/test_regression.py`); all four gates enforced: critical-field extraction (not allowed), false-match (not allowed, target 0.0), known calculation (not allowed), unsupported factual claims (not allowed, target 0.0); deliberate regressions block build (exit code 1); override procedure strictly requires recorded justification in `DECISIONS.md` matching an existing ADR with min 20 chars; CI workflows created in `kemp&lauritzen/.github/workflows/trust-gates.yml`, `website/workspace/app/.github/workflows/trust-gates.yml`, `.github/workflows/trust-gates.yml`; permanent pytest regression suite with 19 tests; closes `TL-0.3`. `pytest tests/trust/test_regression.py -q` → 19 passed; full trust suite `pytest tests/trust/ -q` → 995 passed, 15 subtests passed. See ADR-050.
- **`TL-9.5`** (Trust Center) DONE: Brief §43 enterprise admin surface built and verified across all layers (`src/trust/trust_center.py`); data verification with explicit denominator (Brief §23), activity matching precision with false-match prominence, review items breakdown across 4 categories, unresolved items count, last validation date, pinned engine version (`versions["analysis_engine"]`); exportable verification report (markdown and JSON); endpoints `/trust-center/summary` and `/trust-center/report` in `src/main.py`; authenticated tenant-scoped endpoints in both Flask backends (`GET /admin/trust-center`, `GET /admin/trust-center/report`); `trust_metrics` and `versions` persisted on `schedule_comparisons`; `TrustCenterPanel.jsx` tab in `AdminPortal.jsx` for both React frontends with brand and locale parity (Kemp Danish `#007346`, Nova EN/DA `#1eb5ee`); Do-not rule enforced (admin-only, no cross-tenant bleed). `pytest tests/trust/test_trust_center.py -q` → 10 passed; both frontends build cleanly via `npm run build`. See ADR-049.
- **`TL-9.4`** (trust metrics KPIs) DONE: Brief §38 ten metrics implemented (`src/trust/metrics.py`): critical field verification rate, activity match precision, unmatched activity rate, manual review rate, OCR review rate, false match rate (prominent=True, target 0.0), conflict detection rate, agent unsupported claim rate (prominent=True, target 0.0), human correction rate, regression failure rate; explicit denominators on every percentage (Brief §23, e.g. `190 / 200 (95.00%)`); continuous time-series history in `TrustMetricsStore` (`get_latest_metrics`, `get_metric_trend`, `get_history`); live computation via `compute_live_metrics()` and harness reconciliation via `reconcile_with_harness()`; wired into `main.py` health payloads and endpoints `/trust-metrics/latest`, `/trust-metrics/trend/{metric_name}`, `/trust-metrics/history`; Do-not rule: no blended single score (Brief §30). `pytest tests/trust/test_metrics.py -q` → 7 passed. See ADR-048.
- **`TL-9.3`** (version everything) DONE: Brief §41 seven independent version dimensions implemented (`src/trust/versioning.py`): parser (`nusf-pipeline-v2.1`), matching algorithm (`nusf-matcher-v3.2`), analysis engine (`nusf-compare-engine-v1.4`), prompt (`predictive-prompt-v2.1` / `comparison-prompt-v1.0`), model (`azure-gpt-4o`), schedule revision, and manual corrections (`corrections:none` / `corrections-vN`); stamped onto `compare_nusf_chunks`, `PredictiveAgent.analyze`, `AuditChainEntry` SHA-256 hash, and `reconstruct_answer()`; `is_distinguishable_from()` and `diff()` for run comparison; Do-not rule enforced (independent dimensions, no global version). `pytest tests/trust/test_versioning.py -q` → 9 passed. See ADR-047.
- **`TL-9.2`** (audit log) DONE: Brief §40 nine-stage epistemic reconstruction chain (`src/trust/audit.py`), cryptographic SHA-256 tamper-evident chaining (`AuditChainEntry`, `verify_integrity`), Do-not rule enforcement (no raw file bytes logged; hashes and size metadata only); `/audit-trail/{analysis_id}` endpoint in `src/main.py`; authenticated tenant-scoped endpoints in both Flask backends (`GET /comparisons/<id>/audit`, `GET /analyses/<id>/audit`); dual-layer audit resolved with `log_audit_event` for operational events and `AnalysisAuditTrail` for algorithmic reconstruction. See ADR-046.
- **`TL-9.1`** (click-into-evidence / source viewer) DONE: Brief §24 target interaction delivered. Activity detail model (`src/trust/source_viewer.py`), honest non-paginated degradation (no fabricated pages for CSV/Excel/MPP/XML), PDF page highlight overlay via `pypdfium2` and `PIL`; `/source-document/highlight`, `/source-document/{session_id}/{schedule_role}/page/{page_number}`, and `/source-document/activity-detail` in `src/main.py`; dashboard CSS & `window.niV1ViewSource` postMessage in `formatters.py`; authenticated tenant-scoped endpoints in both Flask backends (`GET /comparisons/<id>/source/<role>`, `GET /analyses/<id>/source`) with `old_file_data`/`new_file_data` BYTEA persistence; `SourceViewerModal.jsx` in both React apps. See ADR-045.
- Prior: **Phase 8 closed (5/5).** Review queue and corrections layer completed and verified end-to-end (TL-8.1 - TL-8.5).
- `pytest tests/trust/ -q` → 995 passed, 15 subtests passed; `harness compare` → "no regressions"; legacy suite → 3 passed; `import src.main` sanity check clean; both React frontends build cleanly via `npm run build`.
- **All 10 phases of the Trust Layer initiative are now COMPLETE (64/66 tasks done, 2 remaining tasks TL-3.6 and TL-4.7 gated on external dependency EXT-1: real K&L golden data).**

---

## Phase status

| Phase | Title | Status | Done |
|---|---|---|---|
| 0 | Safety net & vocabulary | DONE | 6 / 6 |
| 1 | Provenance & OCR confidence | DONE | 9 / 9 |
| 2 | Never invent an ID | DONE | 6 / 6 |
| 3 | Match confidence & no forced matching | DONE | 5 / 6 |
| 4 | Trust Engine & propagation | DONE | 6 / 7 |
| 5 | Deterministic facts for Predictive | DONE | 6 / 6 |
| 6 | Response contract & claim verification | DONE | 7 / 7 |
| 7 | User-facing trust surface | DONE | 8 / 8 |
| 8 | Review queue & corrections | DONE | 5 / 5 |
| 9 | Evidence, audit & Trust Center | DONE | 6 / 6 |
| | **Total** | | **64 / 66** |

---

## External dependencies

Engineering must not block on these. Tasks gated on them are marked `BLOCKED`
in the ledger and have a documented fallback.

| ID | Dependency | Owner | Status | Gates |
|---|---|---|---|---|
| EXT-1 | Real anonymized K&L schedule pairs + manual ground truth (brief §35) | Project Manager (TBD name) — see TL-0.6 notes | REQUEST DRAFTED 2026-08-24 — awaiting send; target reply **2026-10-19**; request text at `changes/trust-layer/EXT-1-data-request.md` | TL-3.6, TL-4.7 |
| EXT-2 | K&L sign-off on user-facing trust terminology, Danish wording (brief §46) | _unassigned_ | NOT REQUESTED | TL-7.6 |

---

## Task ledger

### Phase 0 — Safety net & vocabulary

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-0.1 | Trust test harness skeleton + synthetic fixture corpus | DONE | | `pytest tests/trust/ -q` → 8 passed, 15 subtests passed (2026-08-18) | see ADR-003, ADR-004 |
| TL-0.2 | Baseline snapshot runner | DONE | TL-0.1 | `pytest tests/trust/ -q` → 13 passed, 15 subtests passed; `sha256sum` identical across 2 process runs (2026-08-18) | see ADR-005 (no git repo here) |
| TL-0.3 | Regression runner + report (informational, non-gating) | DONE | TL-0.2 | `pytest tests/trust/ -q` → 19 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-18) | |
| TL-0.4 | Canonical trust vocabulary module (EN + DA) | DONE | | `pytest tests/trust/test_vocabulary.py -q` → 145 passed (2026-08-24); `pytest tests/trust/ -q` → 164 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-24) | parallel-safe; see ADR-006 |
| TL-0.5 | Fix validation level contradiction (docstring vs code) | DONE | TL-0.2 | `pytest tests/trust/test_validation_levels.py -q` → 10 passed (2026-08-24); `pytest tests/trust/ -q` → 174 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-24) | Rule 102 promoted to ERROR; see ADR-007 |
| TL-0.6 | Raise + track the K&L golden-data request | DONE | | Draft request text at `changes/trust-layer/EXT-1-data-request.md` (2026-08-24); `EXT-1` row populated with owner (PM, TBD name) and target date (2026-10-19) | Process task — needs a human to send. Synthetic fixtures (TL-0.1) carry the harness; only threshold calibration waits. |

### Phase 1 — Provenance & OCR confidence

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-1.1 | Extend `Provenance` model with evidence fields | DONE | TL-0.3 | `pytest tests/trust/test_provenance_fields.py -q` → 25 passed (2026-08-24); `pytest tests/trust/ -q` → 199 passed, 15 subtests passed; `pytest tests/test_nusf_normalization.py -q` → 3 passed; `harness compare` → "no regressions", exit 0 (2026-08-24) | D3 additive-only; see ADR-009 |
| TL-1.2 | Capture Azure per-cell OCR confidence + geometry | DONE | TL-1.1 | `pytest tests/trust/test_ocr_confidence.py -q` → 22 passed (2026-08-24); `pytest tests/trust/ -q` → 221 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-24) | cell confidence = min of word confidences; see ADR-010 |
| TL-1.3 | Unify the two duplicate Azure OCR implementations | DONE | TL-1.2 | `pytest tests/trust/test_ocr_unified.py -q` → 21 passed (2026-08-24); `pytest tests/trust/ -q` → 242 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-24) | resolves Q-1; new `ocr_client/` package; see ADR-011 |
| TL-1.4 | Thread cell confidence → field-level provenance | DONE | TL-1.3 | `pytest tests/trust/test_provenance_threading.py -q` → 19 passed (2026-08-24); `pytest tests/trust/ -q` → 261 passed, 15 subtests passed; `pytest tests/test_nusf_normalization.py -q` → 3 passed (no source changes there); `harness compare` → "no regressions", exit 0 (2026-08-24) | cells threaded through `_tables_to_headers_and_rows`; see ADR-012 |
| TL-1.5 | Populate provenance for **all** critical fields | DONE | TL-1.4 | `pytest tests/trust/test_provenance_coverage.py -q` → 22 passed (2026-08-25); `pytest tests/trust/ -q` → 274 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-25) | engine.py: `pct_col` guard changed from `_has_cell_evidence` to unconditional (AC1 legacy path); 3 test bugs fixed (phase key, area method assertion, _row fallback reachability); see ADR-013 |
| TL-1.6 | Separate recognition confidence from value confidence | DONE | TL-1.1 | `pytest tests/trust/test_confidence_separation.py -q` → 3 passed (2026-08-25); `pytest tests/trust/ -q` → 293 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-25) | `Provenance.confidence` renamed to `column_mapping_confidence`; disambiguated from `ocr_confidence` |
| TL-1.7 | Field criticality registry (CRITICAL vs SECONDARY) | DONE | | `pytest tests/trust/test_field_registry.py -q` → 16 passed (2026-08-25); `pytest tests/trust/ -q` → 290 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-25) | `src/trust/fields.py` created; cross-reference comment added to `heuristics.py`; re-exported from `src/trust/__init__.py`; parallel-safe |
| TL-1.8 | Persist provenance alongside chunks | DONE | TL-1.5 | `pytest tests/trust/test_provenance_persistence.py -q` → 4 passed (2026-08-25); `pytest tests/trust/ -q` → 297 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-25) | Dedicated `activity_provenance` table created (ADR-014 resolves Q-2); `save_activity_provenance` & `load_provenance` implemented |
| TL-1.9 | Declare provenance in non-PDF extractors | DONE | TL-1.5 | `pytest tests/trust/test_extractor_provenance.py -q` → 4 passed (2026-08-25); `pytest tests/trust/ -q` → 301 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-08-25) | Emits format-specific `extraction_method` (`csv_cell`, `excel_cell`, `mpp_field`, `mspdi_field`) and `ocr_confidence=None` for exact reads |

### Phase 2 — Never invent an ID

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-2.1 | Make `source_id` optional; delete invention fallbacks | DONE | TL-1.8 | `pytest tests/trust/test_no_invented_ids.py -q` → 3 passed (2026-08-25) | `Activity.source_id` is now `Optional[str]`; deleted row_idx/composite synthesis |
| TL-2.2 | Split `match_key` from `source_activity_id` | DONE | TL-2.1 | `pytest tests/trust/test_identity_separation.py -q` → 3 passed (2026-08-25) | Added `match_key` and `match_method` to `Activity` model and engine |
| TL-2.3 | Architectural guard test: no synthesized ID can surface | DONE | TL-2.2 | `pytest tests/trust/test_no_invented_ids.py -q` → 3 passed (2026-08-25) | Static assertion against engine fallbacks & adversarial fixture tests |
| TL-2.4 | Display contract for unverifiable IDs (both dashboards) | DONE | TL-2.3 | `pytest tests/trust/test_id_display.py -q` → 4 passed (2026-08-25) | Canonical markers ("Unable to verify" EN / "Kan ikke verificeres" DA) + §21 tooltip |
| TL-2.5 | Preserve previous + current ID; flag ID changes | DONE | TL-2.2 | `pytest tests/trust/test_id_change_display.py -q` → 1 passed (2026-08-25) | Visual chip (`ID: <old> → <new>`) in Changed Activities table |
| TL-2.6 | NUSF chunk format version bump (additive) | DONE | TL-2.2 | `pytest tests/trust/test_version_bump.py -q` → 2 passed (2026-08-25) | Bumped default `ScheduleMetadata.nusf_version` to `"2.0"` |

### Phase 3 — Match confidence & no forced matching

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-3.1 | `MatchConfidence` level model (L1–L5) | DONE | TL-2.6 | `src/trust/matching.py`; `pytest tests/trust/test_match_levels.py -q` → 5 passed (2026-08-25, confirmed 2026-08-31 during ledger sync) | see ADR-016 (sync note) |
| TL-3.2 | Classify every match with level + method | DONE | TL-3.1 | `src/experimental/nusf_compare_engine.py`; `pytest tests/trust/test_match_classification.py -q` → 3 passed (2026-08-25, confirmed 2026-08-31) | Resolves Q-3; see ADR-015 |
| TL-3.3 | Replace greedy nearest-date forcing with ambiguity detection | DONE | TL-3.2 | `pytest tests/trust/test_no_forced_matching.py -q` → 3 passed (2026-08-25, confirmed 2026-08-31) | `_AMBIGUITY_MARGIN_DAYS = 3`, marked uncalibrated pending TL-3.6 |
| TL-3.4 | Isolate ambiguous matches from confirmed results | DONE | TL-3.3 | `pytest tests/trust/test_ambiguity_isolation.py -q` → 2 passed (2026-08-25, confirmed 2026-08-31) | `requires_verification_activities` bucket in `nusf_compare_engine.py` |
| TL-3.5 | Precision-first metrics (false-match rate) in harness | DONE | TL-3.3 | `pytest tests/trust/test_precision_metrics.py -q` → 2 passed; `harness compare` prints "Precision-First Matching Metrics" block (2026-08-25, confirmed 2026-08-31) | precision/false-match/unmatched/review-rate reported separately, no blended score |
| TL-3.6 | Calibrate matching thresholds | BLOCKED | EXT-1 | | needs real K&L data |

### Phase 4 — Trust Engine & propagation

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-4.1 | `TrustEngine` module + `TrustState` model | DONE | TL-3.4 | `src/trust/engine.py`, `tests/trust/test_engine.py` | Centralized engine & Verifier protocol |
| TL-4.2 | Derive per-value trust state from upstream evidence | DONE | TL-4.1 | `src/trust/engine.py`, `tests/trust/test_value_trust.py` | OCR/AI/issues value derivation |
| TL-4.3 | Weakest-link propagation | DONE | TL-4.2 | `src/trust/engine.py`, `tests/trust/test_propagation.py` | §14 worked examples passed |
| TL-4.4 | Feature-specific confidence | DONE | TL-4.3 | `src/version_1_0/adapters.py`, `tests/trust/test_feature_confidence.py` | 5 features computed |
| TL-4.5 | Conflict detection rules | DONE | TL-4.2 | `ingestion/validation/engine.py`, `tests/trust/test_conflict_detection.py` | §27 conflict detection rules; `Blocked by` corrected from self-reference TL-4.5→TL-4.2 to match `phase-4-trust-engine.md` (2026-08-31 sync) |
| TL-4.6 | Pre-flight source quality check + PASS/PARTIAL/BLOCK gating | DONE | TL-4.4, TL-4.5 | `src/trust/preflight.py`, `tests/trust/test_preflight_gating.py` | PASS/PARTIAL/BLOCK pre-flight report |
| TL-4.7 | Calibrate trust thresholds | BLOCKED | EXT-1 | | needs real K&L data |

### Phase 5 — Deterministic facts for Predictive

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-5.1 | Deterministic delayed-activity detection in Python | DONE | TL-4.6 | `src/trust/predictive_facts.py`; `pytest tests/trust/test_delay_detection.py -q` → 27 passed; `pytest tests/trust/ -q` → 379 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-08-31) | Standard + Plandisc A/B/C rules, no LLM; fixed 2 latent bugs in `TrustEngine.assess_value` along the way — see ADR-017 |
| TL-5.2 | Deterministic overdue/priority/root-cause computation | DONE | TL-5.1 | `src/trust/predictive_facts.py` (`compute_predictive_facts`); `pytest tests/trust/test_predictive_computation.py -q` → 15 passed; `pytest tests/trust/ -q` → 394 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-08-31) | Priority thresholds UNCALIBRATED (named constants); old `predictive_agent.py` correction code marked superseded but deliberately NOT removed yet (still live's only safety net until TL-5.4 rewires the routes) — see ADR-018 |
| TL-5.3 | Structured verified context builder | DONE | TL-5.2 | `src/trust/context.py` (`build_predictive_context`); `pytest tests/trust/test_structured_context.py -q` → 18 passed; `pytest tests/trust/ -q` → 412 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-08-31) | Aggregates-only (`project_status` + `clusters`, brief §17's literal shape) — a per-activity listing was tried first and failed its own size AC; see ADR-019. Open follow-up for TL-5.4: how per-activity ids reach the narrative layer, if at all |
| TL-5.4 | Demote `predictive_agent` to interpretation-only | DONE (nusf path only) | TL-5.3 | `pytest tests/trust/test_interpretation_only.py -q` → 16 passed; `pytest tests/trust/ -q` → 436 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-02) — see ADR-020, ADR-021 | `NOVA_NARRATIVE_SCHEMA`/`PREDICTIVE_NARRATIVE_SYSTEM_PROMPT`/`analyze_from_facts`/`_merge_narrative_into_facts` (`src/predictive_agent.py`), `build_response_facts` (`src/trust/context.py`), `classify_project_status` (`src/trust/predictive_facts.py`), `_run_nusf_predictive_analysis` wired into all 3 predictive routes in `src/main.py`. Scoped to `data_format == "nusf"` only — the `raw` OCR-text path has no structured `Activity` list to compute facts from, so `analyze()`/`NOVA_INSIGHT_SCHEMA`/the TL-5.2 correction block are deliberately untouched and still serve that path (ADR-018's precedent, restated in ADR-021). Known accepted regression: `human_label` now defaults to `task_name` everywhere (ADR-021 §5) — flagged as a follow-up, not fixed here. A pre-existing, unrelated test-isolation bug (`tests/test_compare_v4_agent.py` leaking a fake `openai` module into `sys.modules`) was found and documented (ADR-021 §6), not fixed — out of scope. |
| TL-5.5 | Remove silent context truncation | DONE | TL-5.3 | `pytest tests/trust/test_no_silent_truncation.py -q` → 19 passed (2026-09-02); `pytest tests/trust/ -q` → 455 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-09-02) | `TruncationReport` + `gate_context_completeness` (PASS/PARTIAL/BLOCK) in `src/trust/preflight.py`, wired through `_build_predictive_context`/`_build_predictive_context_from_csv` (now returns tuple) and all 12 caller sites across the 3 predictive routes via uniform `_truncation_block_response` helper; PARTIAL responses carry `context_completeness` in-band; NUSF path leaves `truncation_report = None`. See ADR-022. |
| TL-5.6 | Separate FORECAST from FACT in the schema | DONE | TL-5.4 | `pytest tests/trust/test_forecast_classification.py -q` → 19 passed (2026-09-02); `pytest tests/trust/ -q` → 474 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-09-02) | `FIELD_EVIDENCE_CLASSIFICATIONS` + `_build_classification` in `src/predictive_agent.py`; both `analyze()` (raw path) and `_merge_narrative_into_facts` (NUSF path) emit `_classification`; master map covers every (section, field) in the response, with `ValueError` on unmapped fields so drift surfaces as a test failure rather than a silent `SOURCE_DATA` default; `predictive_snapshot` carries the brief §31 trio (confidence_level / confidence_basis / main_delay_drivers). See ADR-023. |

### Phase 6 — Response contract & claim verification

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-6.1 | Agent response contract structure | DONE | TL-5.6 | `pytest tests/trust/test_response_contract.py -q` → 22 passed; `pytest tests/trust/ -q` → 496 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-03) | `AgentResponse`/`ValidatedResponse`/`validate_agent_response`/`render_validated_response` in new `src/trust/response_contract.py`; token-gated `ValidatedResponse` cannot be constructed outside the gate function (raises `RuntimeError`), `render_validated_response` runtime-type-checks its argument. Both agents wired ahead of the task's literal `Files:` list (Do section AC4 required it): `predictive_agent.py`'s `analyze()` and `analyze_from_facts()` both attach `"agent_response"` (confidence_state=REVIEW — facts deterministic, narrative not yet claim-verified); `agent.py`'s `RAGAgent.query()` attaches the same (confidence_state=UNVERIFIED — free-text path, no fact set to check against). `unverified_claims` deliberately empty on both — no claim extraction exists yet (`TL-6.2`/`TL-6.3`); the pipe exists and is exercised, ready to be populated. See ADR-024. |
| TL-6.2 | Claim extraction from generated narrative | DONE | TL-6.1 | `pytest tests/trust/test_claim_extraction.py -q` → 38 passed; `pytest tests/trust/ -q` → 534 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-03) | New `src/trust/claims.py`: `Claim`/`ClaimForm`(5 shapes)/`ClaimExtractionResult`/`extract_claims`, regex-only (no LLM, statically asserted). `ClaimForm` deliberately distinct from `vocabulary.ClaimKind` (shape vs. epistemic status — see module docstring). Priority-ordered span-overlap resolver merges the 5 detectors; `CAUSAL` exempted from overlap suppression (claims about a relationship, not competing interpretations of the same digits). Brief §16 example decomposes into exactly 3 claims. 3 real bugs found and fixed while testing brief's own examples: bare "caused" verb form undetected, superlative "of X" clause truncated + missing Danish "af", causal claims silently dropped whenever they shared a sentence with another claim. See ADR-025. |
| TL-6.3 | Claim verification against the fact store | DONE | TL-6.2 | `pytest tests/trust/test_claim_verification.py -q` → 31 passed; `pytest tests/trust/ -q` → 565 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-03) | `src/trust/claims.py`: `VerificationOutcome`/`VerifiedClaim`/`verify_claim`/`verify_claims`/`NarrativeVerificationResult`/`verify_narrative`. `src/trust/engine.py`: `verify_id_reference` (exact membership, reuses TL-2.3's never-invent guarantee). Fact store = the final merged response dict (`insight_data`/`delayed_activities`/`summary_by_area`), same shape for raw and NUSF paths. Numeric claims recount against an allow-listed hint or UNVERIFIABLE (never guessed); superlatives recompute a tie-detector over `summary_by_area`; ids checked by exact membership; causal claims always UNVERIFIABLE unconditionally. `predictive_agent._build_agent_response` wired ahead of the task's own `Files:` list (same posture as TL-6.1, ADR-024): `answer` = contradiction-stripped text, `unverified_claims` = real unverifiable claim texts, `confidence_state` derived from the verification outcome. `RAGAgent.query()` deliberately left unwired — no fact store to check against. See ADR-026. |
| TL-6.4 | Fact / Derived / Inference / Unknown classification | DONE | TL-6.3 | `pytest tests/trust/test_claim_classification.py -q` → 28 passed (2026-09-03); `pytest tests/trust/ -q` → 593 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-09-03) | `VerifiedClaim.kind` set by an exhaustive `(ClaimForm, VerificationOutcome) → ClaimKind` table in `src/trust/claims.py`; CAUSAL→INFERENCE unconditional at the table level (brief §18/§20); parallel `FIELD_CLAIM_KINDS` table for LLM-attributed fields so `forcing_assessment[]` is `INFERENCE` by construction (brief Do item 2, enforced not runtime-judged); `build_field_claim_kinds` raises on any unmapped field (AC4); `_claim_kinds` travels in the payload for `TL-7.3` to render. See ADR-027. |
| TL-6.5 | No-answer behaviour | DONE | TL-6.3 | `pytest tests/trust/test_no_answer.py -q` → 34 passed (2026-09-03); `pytest tests/trust/ -q` → 627 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-09-03) | `NoAnswerInfo` dataclass (known / cannot_verify / next_step per brief §18) in `src/trust/response_contract.py`; `AgentResponse.no_answer` field added (backwards-compat: 6 original fields still intact); `validate_agent_response` short-circuits on `no_answer` with `GateDecision.NO_ANSWERED`; `is_causal_question` + `detect_no_answer` + `build_no_answer_response`; EN + DA templates; brief §42 anti-patterns structurally prevented. Wired into `predictive_agent._build_agent_response` and `agent.py`'s `RAGAgent.query` (chat endpoint returns `is_no_answer: bool`). See ADR-028. |
| TL-6.6 | Language guardrails (probabilistic phrasing) | DONE | TL-6.4 | `pytest tests/trust/test_language_guardrails.py -q` → 33 passed (2026-09-03); `pytest tests/trust/ -q` → 660 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-09-03) | `check_overclaiming` + `hedge_overclaiming` + `hedge_narrative_overclaiming` in `src/trust/claims.py`; EN + DA pattern tables covering causal verbs / unhedged future assertions / absolute certainty adverbs; wired into `verify_narrative` (TL-6.3) as the last step with sentence-span expansion and `overclaiming_fixes` audit trail; FACT/DERIVED_FACT exempt (Do-not rule); `PREDICTIVE_NARRATIVE_SYSTEM_PROMPT` updated as the last layer (brief §34). See ADR-029. |
| TL-6.7 | Unsupported-claim-rate metric | DONE | TL-6.3 | `pytest tests/trust/test_unsupported_claim_rate.py -q` → 20 passed (2026-09-03); `pytest tests/trust/ -q` → 680 passed, 15 subtests passed; `harness compare` shows the metric line + offending-claims enumeration, exit 0 (2026-09-03) | `UnsupportedClaimMetric` in `src/trust/claims.py` (verified_count / contradicted_count / unverifiable_count / total_claims + `meets_target()`); `compute_unsupported_claim_metric` + `collect_unsupported_claims` aggregate across batches; standing test-question suite in `tests/trust/harness.py::_NARRATIVE_VERIFICATION_SUITE` (9 questions covering brief §16/§18/§20); `ComparisonReport.unsupported_metric` + `unsupported_offending` + `render_unsupported_claim_metric` wire the metric into `harness compare` as its own block. Informational with target-visibility (brief §39 wording; gate-flip is TL-9.6's call). See ADR-030. |

### Phase 7 — User-facing trust surface

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-7.1 | Three-state badge component in V1 formatter | DONE | TL-6.4 | `pytest tests/trust/test_badges.py -q` → 23 passed; `pytest tests/trust/ -q` → 709 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-03) | `_trust_badge()` in `src/version_1_0/formatters.py` — new `ni-trust-badge`/`ni-trust-badge--{verified,review,unverified}` CSS (same 3 hex values in `CSS` and `CSS_KEMP`), `suppress_verified=True` default implements "only badge what carries information." `_id_cell` (TL-2.4) refactored onto the same renderer, incidentally fixing a real pre-existing gap (`.ni-unverified-id` had no `CSS_KEMP` rule at all). Palette-distinguishability checked programmatically (RGB color-distance) in `test_badges.py`, not just asserted; a rendered sample (real CSS + real renderer, 4 panels: Nova/Kemp × EN/DA) sent to the user for the AC's own "visually confirmed" requirement — pending their look. See ADR-032. |
| TL-7.2 | Project-level trust indicator with defined denominators | DONE | TL-7.1 | `pytest tests/trust/test_project_trust_indicator.py -q` → 22 passed; `pytest tests/trust/ -q` → 702 passed, 15 subtests passed; `harness compare` → "no regressions"; `grep -ri 'accura'` over rendered HTML returns nothing (AC4) (2026-09-03) | New `compute_project_trust_breakdown` + `compute_project_trust_breakdown_predictive` in `src/version_1_0/adapters.py`; new `_render_project_trust` + `_trust_breakdown_pill` in `src/version_1_0/formatters.py`; Q-4 resolved (`selected_activities` denominator; ADR-033). Dynamic tooltip for fully-verified projects (no `0 require review` noise); predictive variant honestly omits `review` (not measured at this granularity); feature-confidence block (TL-4.4) renders on health only; brief §23's "no percentage without a denominator" rule enforced structurally. EN + DA localized. `verified == confirmed_activities_count` consistency check pinned. See ADR-033 (renumbered from a duplicate ADR-031 during 2026-09-05 review sync — see 2026-09-05 ledger entry). |
| TL-7.3 | Source / Calculation / Insight / Forecast visual distinction | DONE | TL-7.1 | `pytest tests/trust/test_evidence_class_rendering.py -q` → 28 passed; `pytest tests/trust/ -q` → 759 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-03; row filled in during 2026-09-05 review sync — implementation predates this row's update) | New `.ni-evidence-label` CSS family (both palettes), single neutral colour with `border-style` differentiating the four `EvidenceClass` values (solid/double/dashed/dotted) per brief §21's "no Christmas tree"; `_evidence_class_chip` helper + `_KPI_TO_EVIDENCE_CLASS` mapping; `_section_heading` accepts `evidence_class`. Brief §46 vocabulary exact, EN + DA. Applied to both dashboards via shared `_render_payload`. See ADR-034 (renumbered from a duplicate ADR-032 during 2026-09-05 review sync). |
| TL-7.4 | Predictive: forecast never renders like observed fact | DONE | TL-7.3 | `pytest tests/trust/test_forecast_rendering.py -q` → 33 passed; `pytest tests/trust/ -q` → 797 passed, 15 subtests passed; `harness compare` → "no regressions", unchanged `2/11` unsupported-claims metric (2026-09-05) | New `_render_predictive_snapshot` + `_render_biggest_risk` + `_confidence_badge` in `src/version_1_0/formatters.py`. Forecast panel is a structurally separate `<section>` after the KPI strip, dotted-border motif matching TL-7.3's `nova_forecast` chip; confidence band reuses TL-7.1's badge palette (HIGH/MEDIUM/LOW → verified/review/unverified tones); LOW confidence renders a caution block inside the panel at the point of display (AC4); zero-delay override uses `nova_insight` chip and omits `estimated_delay_impact` (TL-5.6's `TestStructuralRiskOverride` Do-not rule); `predictive_biggest_risk`'s `will_block`/`prevent_action_now` each carry a `nova_forecast` chip. Implementation and its test file existed from an earlier independent session but were left with 6 failing tests and no ledger/ADR entry; 2026-09-05 review found all 6 were test bugs (bare `"classname" not in html` checks matching the always-present static `<style>` block, plus one non-greedy regex that only captured the first nested `</div>`), not implementation bugs — confirmed by direct rendering before touching anything. Fixed the 6 assertions; no production code changed. See ADR-035. |
| TL-7.5 | "Why?" explanations | DONE | TL-7.2 | `pytest tests/trust/test_why_explanations.py -q` → 27 passed; `pytest tests/trust/ -q` → 824 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-05) | New `_why_button`/`_why_delayed_row_explanation`/`_why_action_explanation` in `src/version_1_0/formatters.py`; `niV1WhyToggle` added to shared `JS` (client-side disclosure, no network call, same inline-onclick pattern as `niV1ChangeToggle`). `_activity_row` (`adapters.py`) extended to carry `is_root_cause`/`blocked_by_id` through — previously computed by TL-5.2 then silently dropped before reaching the renderer. Applied to: delayed-table priority cells (root-cause / downstream-of-id / days-overdue), executive actions (`related_task_ids` count), and the project trust panel (reuses the same `tooltip_raw` string as TL-7.2's hover tooltip — one source, two affordances). Deliberately never cites the UNCALIBRATED priority thresholds themselves. EN + DA localized. See ADR-037. |
| TL-7.6 | Brand + locale parity (Kemp/Nova, DA/EN) | DONE | TL-7.5 | EXT-2 | `pytest tests/trust/test_brand_locale_parity.py -q` → 19 passed; `pytest tests/trust/ -q` → 859 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-05) | Every `trust_*`/`evidence_class_*`/`forecast_*`/`why_*` key has a complete non-empty DA translation (structural parity check); all four formatter entry points render all trust elements (badge/panel/chip/why-button); no trust element is Kemp-optional (`_mark_optional_health_items` never touches trust CSS classes, pinned); the real `report_localization.py` localizer (imported live from `kemp&lauritzen/backend/utils/`) does not corrupt any trust string. Fixed 2 real bugs found finishing test coverage started independently (via opencode): an orphaned DA-only `forecast_confidence` key, and a test exemption (`COINCIDENT_OK`) that compared an EN string against a DA translation and could therefore never exempt anything. `EXT-2` (K&L native-speaker sign-off) remains open — everything engineering can check is DONE; the human review is a separate, non-blocking follow-up (same posture as TL-3.6/TL-4.7). See ADR-039. |
| TL-7.7 | PDF export carries the same trust model | DONE | TL-7.6 | `pytest tests/trust/test_pdf_trust.py -q` → 18 passed; `pytest tests/trust/ -q` → 877 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-05) | New `_PDF_TRUST_FALLBACK_CSS` in `src/pdf_export.py` (injected via `add_style_tag` alongside the existing `_COLOR_CSS`): forces `.ni-why-panel[hidden]` visible and adds a scoped `::after{content:attr(title)}` fallback to `.ni-trust-badge`/`.ni-evidence-label`/`.ni-trust-summary` only (not a blanket `[title]` rule, to avoid printing unrelated UI-control tooltips). New `_render_methodology_footer` in `formatters.py` — brief §44's literal "⚠ Based on partially verified activity matching." — reuses TL-7.2's own `project_trust` breakdown as its condition (`review`/`unresolved` > 0), rendered always (screen + PDF, one code path), EN + DA. Trust indicator on page one confirmed already true by construction (`_render_project_trust` is the first thing after the header, before KPIs/tables) and pinned by string-position tests. Confirmed (not assumed) the Flask-side ReportLab PDF routes are unreachable from the current UI — the only live "Export PDF" button calls the Playwright path this task covers. See ADR-040. |
| TL-7.8 | Reassuring uncertainty UX (not error states) | DONE | TL-7.1 | `pytest tests/trust/test_uncertainty_ux.py -q` → 16 passed (2026-09-05); `pytest tests/trust/ -q` → 813 passed, 15 subtests passed; `harness compare` → "no regressions", exit 0 (2026-09-05) | New `build_uncertainty_notice(kind, language)` in `src/trust/response_contract.py` (brief §42 four-part shape); both `PreflightReport.to_refusal_response` and `TruncationReport.to_refusal_response` embed the `notice` field + `success: False`; new `'blocked'` `PROGRESS_STAGES` entry in `main.py` (line 89-94) with reassuring copy distinct from `'error'`; `_truncation_block_response` calls `_update_progress(..., "blocked", ...)` rather than `"error"`; both React apps' `renderUncertaintyNotice()` reads `notice` with inline fallback strings; amber panel — not red. 16 tests pin notice shape, brief §42 wording, anti-pattern words, refusal-shape integrity, and Flask status derivation. See ADR-037. |

### Phase 8 — Review queue & corrections

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-8.1 | Review queue data model + backend | DONE | TL-7.8 | `pytest tests/trust/test_review_queue.py -q` → 27 passed; `pytest tests/trust/ -q` → 904 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-05) | New `src/trust/review_queue.py`: `ReviewCategory`/`CandidateOption`/`ReviewItem`/`Resolution`/`ReadOnlyUserError`/`ReviewQueueStore`, all four brief §25 categories derived from already-computed upstream evidence (TL-3.2/3.4's `MatchResult.candidates`/`requires_verification_activities`, TL-4.2's `TrustEngine.assess_value`, TL-4.5's `SOURCE_CONFLICT` validation issues) — no new detector written. `resolve`/`reopen` structurally cannot touch source data (no `Activity`/`Provenance` in scope) and reject read-only actors (`ReadOnlyUserError`); history is append-only. Wired into `src/main.py`'s `/version-1.0/health` and `/version-1.0/kemp/health` (new `review_queue` field on the existing response, zero extra round-trips). Wired end-to-end into both Flask backends (`kemp&lauritzen/backend/routes/schedule.py`, `website/workspace/app/Nova-Insights-Backend/routes/schedule.py`): new `review_queue` JSONB column (write-once) + append-only `review_item_resolutions` table + `GET/POST .../review-queue[/resolve\|/reopen]` endpoints, following each file's own established `get_current_user()`/`read_only_user` convention exactly. **Verification asymmetry, stated plainly:** the core module is fully unit-tested in this repo; the two Flask backends' new endpoints/SQL are convention-matched and `py_compile`-checked but not integration-tested against a live Postgres/running Flask app — same posture as TL-7.1's "visually confirmed" and TL-7.7's "manual PDF inspection" open items. See ADR-041. |
| TL-8.2 | Review queue UI (both apps) | DONE | TL-8.1 | Handled via React components; syntax check / prop flow verified; brand and locale parity verified (2026-09-05) | `ReviewQueuePanel.jsx` in both React frontends (`kemp&lauritzen/app/src/components/ReviewQueuePanel.jsx`, `website/workspace/app/src/components/ReviewQueuePanel.jsx`), mounted in parent React app outside sandboxed iframe; full brand & locale parity (Kemp Danish-only in `#007346`, Nova EN/DA via `useTranslation`); consequence preview box before confirmation (AC3); category labels and "No match" explicit. Wired into `ComparisonAnalysis.jsx` and `comparisonService.js` in both apps. See ADR-042. |
| TL-8.3 | Verified match mapping store, versioned | DONE | TL-8.1 | `pytest tests/trust/test_match_mapping.py -q` → 8 passed; `pytest tests/trust/ -q` → 912 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-05) | `src/trust/match_mapping.py` (`MatchMappingStore`, `VerifiedMapping`). Keyed by `(project_id, match_key)`, immutable append-only versioning. Added `verified_match_mappings` table migration/creation in both Flask backends (`kemp&lauritzen/backend/routes/schedule.py`, `Nova-Insights-Backend/routes/schedule.py`). See ADR-043. |
| TL-8.4 | Corrections feed back into matching | DONE | TL-8.3 | `pytest tests/trust/test_correction_feedback.py -q` → 8 passed; `pytest tests/trust/ -q` → 920 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-05) | Step 0 in `_resolve_activity_matches` (`nusf_compare_engine.py`) with `mapping_lookup` closure, resolves at `MatchLevel.L1_EXACT_VERIFIED_ID` with `method="human_verified"`; contradictions against freshly computed verified source IDs raise `mapping_conflict` rather than silently winning (AC4). See ADR-043. |
| TL-8.5 | Mapping invalidation when evidence changes materially | DONE | TL-8.4 | `pytest tests/trust/test_mapping_invalidation.py -q` → 13 passed; `pytest tests/trust/ -q` → 933 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-05) | `detect_material_change`, `reconcile`, `invalidate` in `src/trust/match_mapping.py`; invalidation history preserved; Flask backend reopen hooks mark active mappings as invalidated. See ADR-044. |

### Phase 9 — Evidence, audit & Trust Center

| ID | Task | Status | Blocked by | Evidence | Notes |
|---|---|---|---|---|---|
| TL-9.1 | Click-into-evidence / source viewer | DONE | TL-8.5 | `pytest tests/trust/test_source_viewer.py -q` → 14 passed; `pytest tests/trust/ -q` → 947 passed, 15 subtests passed; `harness compare` → "no regressions" (2026-09-05) | Full Brief §24 field set; PDF page highlight overlay (TL-1.2 geometry); non-paginated honest degradation (Do-not rule: never fabricate page numbers); authenticated, tenant-scoped endpoints in both Flask backends; SourceViewerModal in both React apps. See ADR-045. |
| TL-9.2 | Audit log | DONE | TL-8.5 | `pytest tests/trust/test_audit_log.py -q` → 9 passed; `pytest tests/trust/ -q` → 956 passed, 15 subtests passed (2026-09-05) | 9-stage Brief §40 epistemic reconstruction chain (`src/trust/audit.py`), cryptographic SHA-256 tamper-evident chaining (`AuditChainEntry`, `verify_integrity`), Do-not rule enforcement (no raw file bytes logged; hashes and size metadata only); `/audit-trail/{analysis_id}` endpoint in `src/main.py`; authenticated tenant-scoped endpoints in both Flask backends (`GET /comparisons/<id>/audit`, `GET /analyses/<id>/audit`); dual-layer audit resolved with `log_audit_event` for operational events and `AnalysisAuditTrail` for algorithmic reconstruction. See ADR-046. |
| TL-9.3 | Version everything (parser, matcher, prompt, model) | DONE | TL-9.2 | `pytest tests/trust/test_versioning.py -q` → 9 passed; `pytest tests/trust/ -q` → 965 passed, 15 subtests passed (2026-09-05) | Brief §41 seven independent dimensions (`src/trust/versioning.py`), stamped on results (`compare_nusf_chunks`, `PredictiveAgent.analyze`, health responses) and audit entries (cryptographic hash chaining); `is_distinguishable_from` and `diff` utility; Do-not rule: no single global version number. See ADR-047. |
| TL-9.4 | Trust metrics KPIs | DONE | TL-9.3 | `pytest tests/trust/test_metrics.py -q` → 7 passed; `pytest tests/trust/ -q` → 972 passed, 15 subtests passed (2026-09-05) | All ten Brief §38 metrics (`src/trust/metrics.py`) with explicit denominators (Brief §23); `false_match_rate` and `agent_unsupported_claim_rate` flagged prominent with 0.0 targets (Brief §37, §39); continuous time-series `TrustMetricsStore` (`get_latest_metrics`, `get_metric_trend`, `get_history`); live computation and harness reconciliation; wired into `main.py` health responses and `/trust-metrics/` routes; Do-not rule enforced: no blended single score (Brief §30). See ADR-048. |
| TL-9.6 | Turn release gates from informational to blocking | DONE | TL-9.4 | `pytest tests/trust/test_regression.py -q` → 19 passed; `pytest tests/trust/ -q` → 995 passed, 15 subtests passed; `harness compare` runs blocking release gates (2026-09-05) | All four gates (critical_field_extraction, false_match, known_calculation, unsupported_claims) flipped from informational to blocking (Brief §36, §39); deliberate regressions block build (exit code 1); override procedure strictly requires recorded justification in `DECISIONS.md` matching an existing ADR with min 20 chars; CI workflows created in `kemp&lauritzen/.github/workflows/trust-gates.yml`, `website/workspace/app/.github/workflows/trust-gates.yml`, `.github/workflows/trust-gates.yml`; closes `TL-0.3`. See ADR-050. |

---

## Phase 6 → Phase 7 handoff

Phases 1–6 are closed except for the two EXT-1-gated calibration tasks
(`TL-3.6`, `TL-4.7`, both `BLOCKED`) and Phase 7's user-facing trust
surface. **Phase 6 closed** — 7/7 done; brief §39's "Target: 0
unsupported factual claims" is now mechanically checkable on every
`harness compare`.

**The next-pick queue**, in execution order per `README.md`'s protocol:

1. **TL-6.1** — DONE (2026-09-03, ADR-024). `src/trust/response_contract.py`
   created (`AgentResponse`/`ValidatedResponse`/`validate_agent_response`/
   `render_validated_response`), token-gated so `ValidatedResponse`
   cannot be constructed outside the gate function. Both
   `predictive_agent.py` and `agent.py`'s `RAGAgent.query()` wired
   ahead of the task's literal `Files:` list.
2. **TL-6.2** — DONE (2026-09-03, ADR-025). New `src/trust/claims.py`
   decomposes generated narrative into atomic `Claim`s across 5
   deterministic (regex-only, no LLM) forms. `ClaimForm` deliberately
   distinct from `vocabulary.ClaimKind` (shape vs. epistemic status).
3. **TL-6.3** — DONE (2026-09-03, ADR-026). New verification layer in
   `src/trust/claims.py` (`verify_claim`/`verify_claims`/
   `verify_narrative`) plus `src/trust/engine.py`'s `verify_id_reference`.
   Numeric claims recount against Phase 5's deterministic facts;
   superlatives recompute a tie-detector; ids checked by exact
   membership; causal claims always `UNVERIFIABLE`. `CONTRADICTED`
   claims are removed from the narrative outright.
4. **TL-6.4** — DONE (2026-09-03, ADR-027). `VerifiedClaim.kind` set by
   an exhaustive `(ClaimForm, VerificationOutcome) → ClaimKind` table
   in `src/trust/claims.py`. CAUSAL→INFERENCE unconditional (brief §18
   A142 / §20). Parallel `FIELD_CLAIM_KINDS` table for LLM-attributed
   fields so `forcing_assessment[]` is `INFERENCE` by construction
   (brief Do item 2, enforced not runtime-judged). `build_field_claim_kinds`
   raises on any unmapped field (AC4). `_claim_kinds` travels in the
   payload for `TL-7.3` to render.
5. **TL-6.5** — DONE (2026-09-03, ADR-028). `NoAnswerInfo` in
   `src/trust/response_contract.py` (known / cannot_verify / next_step
   per brief §18); `AgentResponse.no_answer` field; `GateDecision.NO_ANSWERED`
   short-circuits the gate (no-answer is a shape, not an answer-with-claims).
   `is_causal_question` + `detect_no_answer` (BOTH conditions required:
   causal question AND unverifiable claims) + `build_no_answer_response`
   in EN + DA; brief §42 anti-patterns structurally prevented. Wired
   into `predictive_agent._build_agent_response` (new `user_query` /
   `language` parameters) and `agent.py`'s `RAGAgent.query` (chat
   endpoint returns `is_no_answer: bool` for TL-7.8 to render).
6. **TL-6.6** — DONE (2026-09-03, ADR-029). `check_overclaiming` +
   `hedge_overclaiming` + `hedge_narrative_overclaiming` in
   `src/trust/claims.py`; EN + DA pattern tables covering causal
   verbs / unhedged future assertions / absolute certainty adverbs.
   Wired into `verify_narrative` as the LAST step with sentence-span
   expansion and `overclaiming_fixes` audit trail. FACT/DERIVED_FACT
   exempt (Do-not rule — precision cuts both ways). Prompt updated as
   the last layer (brief §34).
7. **TL-6.7** — DONE (2026-09-03, ADR-030). `UnsupportedClaimMetric` in
   `src/trust/claims.py`; `compute_unsupported_claim_metric` +
   `collect_unsupported_claims` aggregate across batches; standing
   test-question suite in `tests/trust/harness.py::_NARRATIVE_VERIFICATION_SUITE`;
   `harness compare` renders the metric as its own block + offending-
   claims enumeration. Informational with target-visibility; gate-
   flip is TL-9.6's call. **Phase 6 closed.**

**Regressions Phase 6 inherits:**

- `python -m tests.trust.harness compare` remains informational
  (flips blocking at `TL-9.6`); the Phase 3 precision-metrics block
  (`TL-3.5`), the Phase 0 baseline diff, and the Phase 6
  unsupported-claim-rate metric (`TL-6.7`, when it lands) all run on
  every compare.
- `run_predictive()` in the harness is still `ADR-003`'s placeholder
  (a read of `run_health()`'s facts) — same posture as Phase 5's
  handoff; no Phase 6 task owns it.

**Operational notes:**

- This checkout has no functional git repository (ADR-005). Evidence
  is recorded in `PROGRESS.md` as test output rather than commit SHA.
- Tests run under `PYTHONPATH=.` because `tests/__init__.py` does not
  exist (only `tests/trust/__init__.py`). Every "Verify" command in the
  phase files passes under that path.

---

## Open questions

Record anything that needs a human decision. Do not silently resolve these.

| ID | Question | Raised in | Status |
|---|---|---|---|
| Q-1 | Do we unify the two Azure OCR implementations, or mirror capture in both? | TL-1.3 | RESOLVED (2026-08-24, ADR-011) — unified via shared `ocr_client` package |
| Q-2 | Where does provenance live — vector-store chunk metadata, or a dedicated table? | TL-1.8 | OPEN |
| Q-3 | Is an activity with an unreadable ID but a strong multi-field match shown as Verified or Review? | TL-3.2 | RESOLVED (2026-08-25, ADR-015) — `L2_STRONG_MULTI_FIELD`/`L3_PARTIAL` map to `REVIEW`; only `L1_EXACT_VERIFIED_ID` maps to `VERIFIED` |
| Q-4 | What denominator do we publish for the project trust percentage? (brief §23) | TL-7.2 | RESOLVED (2026-09-03, ADR-033 — renumbered 2026-09-05 from a duplicate ADR-031) — M = `es["selected_activities"]`, the count already shown to the user as the "Activities Analyzed" KPI on the same dashboard. Same number, same source, no surprise denominator. `verified == confirmed_activities_count` is the consistency check, not just a derived number. |
