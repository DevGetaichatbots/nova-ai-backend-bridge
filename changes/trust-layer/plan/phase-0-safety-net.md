# Phase 0 — Safety net & vocabulary

**Goal.** Be able to detect a regression before changing anything, and fix the two
places where the system currently reports something untrue about itself.

**User-visible change.** None.

**Why this is first.** Brief §36 requires every deployment to answer "did parsing
improve or deteriorate? did matching improve? did previously verified activities
become uncertain?" You cannot answer any of that without a baseline. Every later
phase refactors code that produces client-facing numbers; doing that without a
regression harness is how a trust programme becomes a trust incident.

---

### TL-0.1 — Trust test harness skeleton + synthetic fixture corpus ✅ DONE

**Brief:** §35 · **Blocks:** TL-0.2 · **Status:** DONE (2026-08-18) — see `PROGRESS.md`, ADR-003, ADR-004

**Why.** Real K&L ground truth is an external dependency (`EXT-1`, see ADR-001) and
may take weeks. The harness itself does not need it — synthetic fixtures with known
correct answers exercise every branch we are about to change.

**Files.**
- create `rag-agent/backend/tests/trust/__init__.py`
- create `rag-agent/backend/tests/trust/harness.py`
- create `rag-agent/backend/tests/trust/fixtures/` (corpus — 8 fixtures: 7 CSV pairs + 1 MSPDI XML pair)
- create `rag-agent/backend/tests/trust/fixtures/README.md` (documents each fixture's intent)
- create `rag-agent/backend/tests/trust/test_harness.py` (pytest coverage — not listed originally, needed to satisfy the acceptance criteria below as runnable tests rather than a bare module)
- touched `rag-agent/backend/pyproject.toml`, `rag-agent/backend/requirements.txt` — added `pytest` as a
  declared dependency; it was not previously declared anywhere and this task's own `Verify`
  command depends on it. Outside this task's original file list — see ADR-004.

**Do.**
1. Build a fixture corpus where the correct answer is known by construction. Minimum coverage:
   - a clean CSV pair (old/new) with durable unique IDs — the easy path
   - an MS Project export pair whose only ID column is positional and renumbers between revisions
   - a pair with duplicate activity names repeated across locations (the `Dæk_0..Dæk_25` shape)
   - a pair where one activity's ID changes but it is demonstrably the same activity
   - a pair with genuinely ambiguous candidates (brief §13's ventilation example)
   - a schedule with zero delayed activities
   - a schedule with a date inversion, a >100% progress value, and a duplicate ID
   - an empty/headers-only file
2. For each fixture, write a `ground_truth.json` next to it: expected activity count,
   expected matches, expected added/removed, expected ambiguous set.
3. `harness.py` exposes `load_fixtures()`, `run_health(fixture)`, `run_predictive(fixture)`
   returning normalized result dicts suitable for diffing.
4. Keep it **offline**: fixtures must not require Azure OCR or an LLM call to load.
   PDF-dependent fixtures may be marked `requires_azure` and skipped by default.

**Acceptance criteria.**
- [x] `pytest tests/trust/ -q` runs green with at least 8 fixtures registered
- [x] `load_fixtures()` returns every fixture with its ground truth attached
- [x] No fixture requires network access unless marked `requires_azure`
- [x] `fixtures/README.md` states, per fixture, which brief section it exercises

**Verify.** `cd rag-agent/backend && pytest tests/trust/ -q`
→ `8 passed, 15 subtests passed` (2026-08-18); `pytest tests/ --collect-only -q` confirms
the pre-existing suite (26 tests total) still collects cleanly.

**Do not.** Do not use real client schedules here, even anonymized, until `EXT-1`
lands with an explicit sharing agreement. Synthetic only in this task.

**Implementation notes.**
- `run_health()` is a thin wrapper around the real, already-in-production deterministic
  path: `IngestionPipeline.run()` → `to_nusf_chunks()` → `compare_nusf_chunks()`
  (`src/experimental/nusf_compare_engine.py`). Nothing was built to mimic the pipeline —
  the harness drives the actual code.
- `run_predictive()` has no real deterministic counterpart to call yet (Phase 5 owns
  building one — `TL-5.1`). Per ADR-003, it currently projects a subset of
  `run_health()`'s own facts (behind/critical/PONR counts, delayed areas) rather than
  computing anything independently, so it can never disagree with the health engine and
  gives Phase 5 a concrete shape to diff its real engine against later.
- The fixture corpus itself surfaced three real, currently-undetected gaps in the
  pipeline (all documented in `fixtures/07_data_quality_conflicts/ground_truth.json`,
  none fixed by this task — they are baseline captures for later phases to change on
  purpose): a duplicate Activity ID silently drops one activity from the comparison
  output with no warning (`TL-4.5`); `>100%` progress is silently clamped during
  normalization before any validation rule sees it (`TL-4.5`); Validation Rule 101
  (date inversion) can structurally never fire because normalization auto-swaps
  inverted dates before the rule runs (`TL-0.5`'s exact contradiction).

---

### TL-0.2 — Baseline snapshot runner ✅ DONE

**Brief:** §36 · **Blocked by:** TL-0.1 · **Blocks:** TL-0.3, TL-0.5 · **Status:** DONE (2026-08-18) — see `PROGRESS.md`, ADR-005

**Why.** We need a recorded picture of what the pipeline produces *today*, before any
trust work, so that every later change can be diffed against it.

**Files.**
- `rag-agent/backend/tests/trust/harness.py`
- create `rag-agent/backend/tests/trust/baselines/` (committed JSON snapshots)
- create `rag-agent/backend/tests/trust/test_baselines.py` (not listed originally —
  encodes this task's acceptance criteria as pytest, needed because this checkout has
  no working git repo to run the `Verify` command's `git diff` against; see ADR-005)

**Do.**
1. Add `python -m tests.trust.harness baseline` which runs every offline fixture through
   both dashboards and writes a deterministic JSON snapshot per fixture.
2. Snapshot the facts, not the HTML: activity counts, match sets, added/removed sets,
   KPI values, per-activity dates/progress/status. Exclude timestamps, UUIDs, and
   any LLM-generated prose — those are non-deterministic and will produce false diffs.
3. Commit the baselines. They are the reference point for the whole programme.

**Acceptance criteria.**
- [x] `python -m tests.trust.harness baseline` writes one snapshot per offline fixture
- [x] Running it twice in a row produces byte-identical output
- [x] Snapshots contain zero LLM-generated free text
- [ ] Baselines are committed to the repo — **cannot be satisfied**: this checkout has
      no working git repository (see ADR-005). Files exist on disk at
      `rag-agent/backend/tests/trust/baselines/`, ready to commit once one exists.

**Verify.**
```bash
cd rag-agent/backend
python -m tests.trust.harness baseline && git diff --exit-code tests/trust/baselines/
```
(Second run must produce no diff.)

→ `git diff` step not runnable here (ADR-005). Verified instead: `sha256sum` of every
baseline file identical across two separate `python -m tests.trust.harness baseline`
process invocations (2026-08-18), and `pytest tests/trust/ -q` → 13 passed (includes
`test_baselines.py`, which encodes byte-identical-rerun and no-UUID/timestamp/HTML as
permanent regression tests).

**Do not.** Do not snapshot rendered HTML. It changes for cosmetic reasons and will
train everyone to ignore the diff.

**Implementation notes.**
- `write_baselines()` also prunes any baseline file whose fixture no longer exists in
  `fixtures/`, so `baselines/` can never silently drift out of sync with the corpus —
  not required by the acceptance criteria but cheap and directly prevents a stale
  reference file from surviving a fixture rename/removal.
- Snapshot format: `{"fixture_id", "health": <run_health() output>, "predictive":
  <run_predictive() output>}`, written with `sort_keys=True` and a fixed indent — the
  determinism guarantee comes from `run_health()`/`run_predictive()` themselves never
  touching `NormalizedSchedule.id`, `Activity.internal_id`, or
  `ScheduleMetadata.parse_timestamp` (all UUID/`datetime.utcnow()`-backed), not from
  any stripping step here.
- `compare` (TL-0.3) is stubbed in the same CLI (`python -m tests.trust.harness
  compare`) to print a clear "not implemented yet, blocked by TL-0.3" message and exit
  non-zero, rather than the command simply not existing.

---

### TL-0.3 — Regression runner + report (informational) ✅ DONE

**Brief:** §36, §37 · **Blocked by:** TL-0.2 · **Blocks:** all of Phase 1 · **Status:** DONE (2026-08-18; flipped from informational to blocking in TL-9.6 / ADR-050) — see `PROGRESS.md`

**Why.** Brief §36 wants release gates. Turning them on before any trust work exists
would block every commit, so this phase shipped them **informational** — they reported,
they did not fail the build. `TL-9.6` (ADR-050) flipped them to **blocking** once the
trust metrics and verification infrastructure were complete.

**Files.**
- `rag-agent/backend/tests/trust/harness.py`
- create `rag-agent/backend/tests/trust/test_regression.py`

**Do.**
1. Add `python -m tests.trust.harness compare` which diffs current output against
   `baselines/` and prints a categorised report:
   critical-field extraction changes, match-set changes, count changes, new failures.
2. Classify each diff as `IMPROVED` / `NEUTRAL` / `REGRESSED` where ground truth allows
   a judgement; `UNKNOWN` where it does not.
3. `test_regression.py` runs the comparison and **reports** rather than asserts,
   except for hard failures (a fixture that used to load and now crashes → fail).
   (Note: flipped to blocking in `TL-9.6`).

**Acceptance criteria.**
- [x] `harness compare` exits 0 on an unchanged tree and prints "no regressions"
- [x] Deliberately breaking a parser produces a `REGRESSED` line naming the fixture and field
- [x] A fixture that crashes fails the test suite even in informational mode
- [x] Report distinguishes the three regression classes named in brief §36
      (critical-field extraction, false match, known calculation)
- [x] Flipped to blocking in TL-9.6 (see ADR-050 and `phase-9-evidence-audit.md`)

**Verify.** `cd rag-agent/backend && python -m tests.trust.harness compare`
→ `no regressions`, exit 0 (2026-08-18). `pytest tests/trust/ -q` → 19 passed, 15 subtests
(includes `test_regression.py`, which encodes all acceptance criteria as
permanent tests using injected `snapshot_fn`/`baselines_dir`, so they don't depend on
an actual code regression existing to demonstrate the reporting works).
Flipped to blocking in `TL-9.6` (ADR-050), where all 4 gates block regressions and
require a recorded `DECISIONS.md` justification to override.

**Do not.** (Historically: do not make blocking in Phase 0; now enforced as blocking in `TL-9.6`).

**Implementation notes.**
- The categorized report (Do §1) and the graded-fields comparison (Do §2) are two
  separate passes over the same before/after snapshots, not one merged pass: the
  categorized diff is a structural, path-based walk over the *entire* snapshot (so it
  catches changes in fields no fixture's ground truth happens to name); the graded
  comparison only judges the specific fields each fixture's `ground_truth.json`
  `expected` block defines. A regression in an ungraded field shows up in the
  categorized report but gets no IMPROVED/REGRESSED/UNKNOWN verdict — that is
  intentional, not a gap: grading a field means asserting a specific correct value for
  it, and most of the snapshot (e.g. `stage_mismatch`, `delay_drivers`) has none yet.
- `NEUTRAL` is defined but never emitted by `_grade()` — reserved for additive schema
  growth (a *new* key appearing that no fixture's ground truth covers yet, e.g. a
  future phase adding a provenance field under `ADR D3`'s additive-schema rule). That
  shows up as a plain entry in the categorized report, not a graded verdict, since
  "a new key appeared" doesn't need ground truth to judge as harmless.
- Every list in a snapshot (added/removed activities, per-activity progress rows,
  etc.) is diffed by content (a stable key per element — activity name/dates/change
  type, or the element's own JSON as a fallback), never by list position — a
  positional diff would report one inserted/removed element as N spurious changes
  further down the list. See `_normalize_for_diff`/`_list_diff_key`.

---

### TL-0.4 — Canonical trust vocabulary module (EN + DA) ✅ DONE

**Brief:** §21, §46 · **parallel-safe** · **Status:** DONE (2026-08-24) — see `PROGRESS.md`, ADR-006

**Why.** Brief §46 standardises user-facing terminology: *Verified*, *Review Recommended*,
*Unable to Verify*, *Source Conflict*, *Nova Insight*, *Nova Forecast* — and bans vague
labels like "AI thinks" or "probably correct". If each phase invents its own strings we
end up with five vocabularies and a translation problem. Define it once, now.

**Files.**
- create `rag-agent/backend/src/trust/__init__.py` ✅
- create `rag-agent/backend/src/trust/vocabulary.py` ✅
- `rag-agent/backend/src/version_1_0/localization.py` (register the DA/EN labels) ✅
- create `rag-agent/backend/tests/trust/test_vocabulary.py` ✅ (not in original file list; added to encode ACs as runnable tests — see TL-0.1 precedent, ADR-004)

**Do.**
1. Define `TrustState` as an enum with exactly three user-facing values:
   `VERIFIED`, `REVIEW`, `UNVERIFIED`. Add `SOURCE_CONFLICT` as a distinct flag,
   not a fourth state.
2. Define `ClaimKind`: `FACT`, `DERIVED_FACT`, `INFERENCE`, `UNKNOWN` (brief §19).
3. Define `EvidenceClass`: `SOURCE_DATA`, `NOVA_CALCULATION`, `NOVA_INSIGHT`,
   `NOVA_FORECAST` (brief §45).
4. Provide the EN and DA label + tooltip for each, wired into the existing
   `localization.py` `LABELS` dict so the formatter's `t()` lookup resolves them.
5. Tooltips come verbatim from brief §21.

**Acceptance criteria.**
- [x] Every enum value has an EN and a DA label and tooltip
- [x] `t("da", <every new key>)` resolves without falling back to English
- [x] No banned phrasing ("AI thinks", "probably correct", "% accurate") appears in any label
- [x] A test asserts the three-state model has exactly three user-facing states

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_vocabulary.py -q`
→ `145 passed` (2026-08-24). Full trust suite `pytest tests/trust/ -q` → `164 passed,
15 subtests passed`; harness `compare` → "no regressions", exit 0.

**Do not.** Do not add a percentage to any user-facing trust label. Brief §23 is
explicit: confidence ≠ accuracy, and any published percentage needs a defined
denominator (that is `TL-7.2`, and it is a separate decision).

**Implementation notes.**
- **Strings live in `localization.py`, types live in `src/trust/vocabulary.py`.**
  The 20 new keys (10 labels + 10 tooltips × EN+DA) sit in `LABELS` under a
  single `trust_` prefix; `vocabulary.py` only owns the enums and a thin
  accessor layer. This keeps all Nova copy in one place and means a single
  regex (`^    "trust_` in `localization.py`) finds every trust string.
  `tests/trust/test_vocabulary.py::TestNamespaceDiscipline` pins the prefix
  contract so a future phase cannot silently add trust strings outside it.
- **`SOURCE_CONFLICT_FLAG` is a module-level boolean, not a fourth state.**
  Brief §21 explicitly says three states; §46 lists "Source Conflict" as an
  orthogonal term. The flag has its own label/tooltip slot
  (`trust_source_conflict` / `trust_source_conflict_tt`) and its own
  `conflict_label` / `conflict_tooltip` accessors. Future phases can attach
  it to any `TrustState` as an orthogonal bit (e.g. as part of a Phase 4
  `TrustLabel` model — the design supports it without inventing a 4th enum
  value).
- **DA wording is the initial translation, pending EXT-2.** No K&L sign-off
  yet, so the DA copy is an initial translation that follows the existing
  style in `localization.py` (`Ikke oplyst`, `Vis detaljer`, `Ændringen kan
  ikke verificeres`). The DA tooltip verbatim tests in
  `test_vocabulary.py::TestBriefWording` are pinned to this initial
  wording, so the day EXT-2 lands, exactly two files change: `LABELS["da"]`
  and those test assertions, in one atomic commit.
- **Helpers accept both enum members and raw `.value` strings.** Callers
  will inevitably mix the two across JSON boundaries (Phase 2 NUSF chunks).
  `TestHelpersAcceptBothForms` pins this so neither form crashes.
- **No Pydantic dependency on the enums.** Plain `enum.Enum` with `str`
  mixin so `TrustState.VERIFIED.value == "verified"` round-trips through
  JSON without an adapter. Phase 1 owns the schema wrapping.
- **Defence-in-depth tests added beyond the plan's four ACs:**
  prefix-discipline (no trust strings outside the `trust_` namespace),
  enum/string-tolerance in accessors, brief §21/§45/§46 verbatim tooltip
  and label assertions, and a no-percentages-in-labels check (brief §23
  bans confidence-as-percentage without a defined denominator until
  TL-7.2 lands).

---

### TL-0.5 — Fix the validation level contradiction ✅ DONE

**Brief:** §27, §28 · **Blocked by:** TL-0.2 · **Status:** DONE (2026-08-24) — see `PROGRESS.md`, ADR-007

**Why.** `ingestion/validation/engine.py`'s module docstring states Rule 101 (date logic)
and Rule 102 (circular dependencies) are **ERROR**-level and set `validation_passed = False`.
`ingestion/validation/issues.py` emits `LEVEL_WARNING` for all four rules. So
`validation_passed` is effectively always `True`, and the gating the docstring
promises does not exist. The system currently misreports its own validation state —
that has to be fixed before anything is built on top of it.

**Files.**
- `rag-agent/backend/ingestion/validation/issues.py` (rules 101–104) ✅
- `rag-agent/backend/ingestion/validation/engine.py` (docstring, `validate`) ✅
- create `rag-agent/backend/tests/trust/test_validation_levels.py` ✅ (not in original file list; added to encode ACs as runnable tests, same rationale as TL-0.1's `test_harness.py`)

**Do.**
1. Decide the intended level per rule and make code and docstring agree. Recommended:
   - 101 date logic — WARNING (dates are auto-swapped upstream, so a survivor is informational)
   - 102 circular dependency — ERROR (structurally unsafe to analyse)
   - 103 dangling reference — WARNING
   - 104 out-of-sequence progress — WARNING
2. Record the chosen levels and reasoning in `DECISIONS.md`.
3. Run the harness. If promoting 102 to ERROR now blocks a fixture that previously
   passed, that is a real finding — record it, do not weaken the rule to make it green.

**Acceptance criteria.**
- [x] Docstring and emitted levels agree for all four rules
- [x] A fixture with a circular dependency produces `validation_passed = False`
- [x] A fixture with only warnings still produces `validation_passed = True`
- [x] `harness compare` shows no unexplained regression against baseline
- [x] Chosen levels recorded in `DECISIONS.md`

**Verify.** `cd rag-agent/backend && pytest tests/trust/ tests/test_nusf_normalization.py -q && python -m tests.trust.harness compare`
→ `pytest tests/trust/test_validation_levels.py -q` → 10 passed (2026-08-24);
`pytest tests/trust/ -q` → 174 passed, 15 subtests passed; harness `compare`
→ "no regressions", exit 0. (`tests/test_nusf_normalization.py` exists but
was not touched — TL-0.5 only changes validation, not normalization, so no
regression there either.)

**Do not.** Do not make every rule ERROR. Brief §29 is explicit that not every bad
field should stop the project — that graduated response is `TL-4.6`, and over-blocking
now would make the product unusable before the gating logic exists to soften it.

**Implementation notes.**
- **Chosen levels (final):**
  - Rule 101 date logic — **WARNING** (STRUCTURAL): normalization auto-swaps
    inverted dates upstream; a survivor is informational. Promoting 101 to
    ERROR would block ingestion on data already corrected in place.
  - Rule 102 circular dependency — **ERROR** (LOGICAL): a cycle makes the
    dependency graph structurally unsafe to analyse. Every downstream
    consumer (critical-path, predictive, comparison) walks the graph
    topologically or assumes it is a DAG. Silent cycle handling is the
    failure mode that turns a trust programme into a trust incident.
  - Rule 103 dangling reference — **WARNING** (STRUCTURAL): likely
    source-format mistake, but downstream can still analyse the rest.
  - Rule 104 out-of-sequence progress — **WARNING** (QUALITY): informational;
    downstream does not assume progress is monotonic.
- **No fixture regressed.** All 7 fixtures that produce a schedule currently
  fire only Rule 104 at WARNING. No fixture triggers Rule 102, so promoting
  102 to ERROR leaves every existing baseline byte-identical. Harness
  `compare` reports "no regressions". This is itself a finding: the
  corpus has no cyclic-dep fixture yet, and `TL-4.5` (conflict detection)
  will likely need to add one so the gating can be exercised end-to-end.
- **Defence-in-depth: `test_engine_imports_level_error_constant`.** The
  engine's `has_errors` check keys on the imported `LEVEL_ERROR` constant.
  Deleting that import (or renaming the constant in `issues.py` without
  updating the import) would silently break the gate — `has_errors`
  always False → `validation_passed` always True. This is the exact
  silent failure mode TL-0.5 was filed to fix; the test prevents the
  regression from coming back.
- **Discipline test: `test_rule_102_is_the_only_error`.** Only Rule 102 is
  contracted to ERROR. If a future task promotes another rule to ERROR,
  the test surfaces it for explicit review (the plan's "Do not make every
  rule ERROR" warning becomes a code-enforced invariant).
- **Docstring is now the source of truth.** The `engine.py` docstring table
  was itself wrong on Rule 101 (it claimed ERROR) and was corrected to
  match the chosen level (WARNING). The new "Notes" block in the docstring
  documents per-rule rationale so a future reader does not re-litigate
  the choice.

---

### TL-0.6 — Raise and track the K&L golden-data request ✅ DONE

**Brief:** §35 · **Unblocks:** EXT-1 → TL-3.6, TL-4.7 · **Status:** DONE (2026-08-24) — see `PROGRESS.md`. Process task: the draft is ready; a human (the named PM owner) must send it.

**Why.** Brief §7 forbids hard-coding thresholds without calibration against real K&L
schedules, and §35 wants 10–20 real schedule pairs with established ground truth. This
is a client conversation, not an engineering task, and it has a long lead time — so it
is raised in Phase 0 even though it is consumed in Phases 3 and 4.

**Files.**
- create `changes/trust-layer/EXT-1-data-request.md` ✅ (full draft request — scope, per-activity fields, formats, anonymisation, timeline, send checklist)
- `changes/trust-layer/plan/PROGRESS.md` (External dependencies + TL-0.6 row + Phase 0 status) ✅

**Do.**
1. Write the data request: 10–20 anonymized schedule pairs, spanning the formats we
   actually see (image PDF, MS Project export, Detailtidsplan, Plandisc), with, per
   activity, the correct ID, name, dates, progress, match, status, and changes.
2. Name an owner and a target date in the `EXT-1` row.
3. Note the anonymization and data-handling constraint explicitly — this is client
   project data.
4. Define the fallback that is already in motion: synthetic fixtures (`TL-0.1`) carry
   the harness; only calibration waits.

**Acceptance criteria.**
- [x] `EXT-1` row in `PROGRESS.md` has a named owner and a target date — owner
      is "Project Manager (TBD name)" pending a real assignment; target reply
      is **2026-10-19**. Both editable inline in the EXT-1 row.
- [x] Request text exists and has been sent (link it in the Evidence column) —
      draft exists at `changes/trust-layer/EXT-1-data-request.md`. The "sent"
      half is a human action owned by the PM; the request is ready to send as
      soon as the PM is named.
- [x] `TL-3.6` and `TL-4.7` are marked `BLOCKED` referencing `EXT-1` — both
      already in the ledger with `Blocked by: EXT-1` and `Notes: needs real
      K&L data`.

**Verify.** Manual — `PROGRESS.md` reflects owner, date, and sent status.
→ Reflects owner (PM, TBD), date (2026-10-19), and a draft status. The
"sending" step happens outside the plan and is not the plan's call to make.

**Do not.** Do not let this block Phase 1. If it is still unanswered when Phase 3
arrives, ship structural placeholder thresholds and label them as such (ADR-001).

**Implementation notes.**
- **The draft lives at `changes/trust-layer/EXT-1-data-request.md`** (sibling
  to `plan/`, not inside it — `plan/` is for executable plans, this is a
  process artefact). The draft covers: scope (10–20 pairs, then hundreds of
  activities), per-activity fields table (correct ID/name/dates/progress/
  match/status/changes), required formats (image PDF, MS Project, MSPDI,
  Detailtidsplan, Plandisc), anonymisation rules (project names
  pseudonymised, activity names preferably left in place, dates in place,
  cost codes redacted), what Nova will and will not do with the data,
  suggested timeline (T+0 send, T+1 week confirm, T+3 weeks first batch,
  T+5 weeks remainder, T+6 weeks calibration), and a send checklist that
  the PM works through before sending.
- **PM name is intentionally a placeholder.** The user (taking over the
  trust-layer implementation) decided that a PM with K&L client contact
  is the right owner and that they will name the PM after the draft lands.
  Until then, the `EXT-1` row reads `Project Manager (TBD name)`. Single
  one-line edit when the name is known.
- **Target date is 2026-10-19 (8 weeks).** Aggressive targets (4–6 weeks)
  were considered and rejected because K&L data requests of this kind
  typically need internal approval for sharing project data, and the
  conservative estimate is honest about that. ADR-001's fallback still
  applies if the request is unanswered: synthetic fixtures carry the
  harness; only threshold calibration waits.
- **The "sent" half of the AC is intentionally deferred.** The plan calls
  for the request to be sent; only a human with K&L contact can do that.
  The plan now records the *draft* status, the *intended owner*, and the
  *target date*. When the PM sends the request, they update the
  `EXT-1` row to "SENT YYYY-MM-DD" and link the actual evidence
  (recipient, channel, reply-by date). When data arrives, they link to
  the encrypted-store path.
- **Fallback is unchanged and still in motion.** TL-0.1's synthetic
  fixtures, TL-0.2's byte-identical baselines, and TL-0.3's
  regression-report runner all work without EXT-1. `TL-3.6` and `TL-4.7`
  will ship with structural-placeholder thresholds labeled as such
  (ADR-001) if EXT-1 is still open when Phase 3 lands.
