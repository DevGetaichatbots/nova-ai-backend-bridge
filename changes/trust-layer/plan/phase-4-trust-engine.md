# Phase 4 — Trust Engine & propagation

**Goal.** One centralized engine that turns upstream evidence into a trust state, and
propagates uncertainty downstream so a confident-sounding conclusion cannot sit on
weak data.

**User-visible change.** Partly — analysis gating can now pause or partially degrade
an analysis, which the user must be told about.

**The rule this phase encodes** (brief §14): given OCR 67%, parsing 91%, match 58%,
the final analysis must **not** become 98% confident because an LLM finds the answer
plausible. *"The Trust Engine should calculate a final state based on the weakest
materially relevant dependency. Not necessarily a simple average."*

---

### TL-4.1 — `TrustEngine` module + `TrustState` model

**Brief:** §3 · **Blocked by:** TL-3.4 · **Blocks:** TL-4.2

**Why.** Brief §3 explicitly warns against treating confidence as an OCR feature
bolted on locally. It must be a centralized service every layer consults.

**Files.**
- create `rag-agent/backend/src/trust/engine.py`
- `rag-agent/backend/src/trust/vocabulary.py` (reuse `TrustState` from `TL-0.4`)

**Do.**
1. Define `TrustAssessment`: the resulting `TrustState`, the `reason`, the
   `weakest_link` (which dependency drove it), and the full `evidence_chain`.
2. `TrustEngine.assess(value_ref) -> TrustAssessment` is the single entry point.
3. Model the pipeline stages from brief §3 as explicit inputs: OCR confidence,
   parsing confidence, identity confidence, match confidence, calculation validation,
   analysis confidence.
4. Implement `Verifier` from `src/version_1_0/diffs.py` so the existing diff seam routes
   through the engine (ADR-002) — that seam was built for exactly this.

**Acceptance criteria.**
- [ ] `TrustEngine` is the only place a trust state is computed
- [ ] Every assessment names its weakest link
- [ ] `TrustEngine` satisfies the `Verifier` protocol and `diffs.py` accepts it
- [ ] `grep -rn "TrustState(" rag-agent/backend/src` shows construction only inside `src/trust/`

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_engine.py -q`

**Do not.** Do not let individual formatters or adapters compute trust states locally.
That is how the current `Provenance.confidence` became meaningless.

---

### TL-4.2 — Derive per-value trust state from upstream evidence

**Brief:** §5, §6, §7 · **Blocked by:** TL-4.1 · **Blocks:** TL-4.3, TL-4.5

**Why.** Connect Phase 1's provenance and Phase 3's match levels to an actual state.

**Files.**
- `rag-agent/backend/src/trust/engine.py`
- `rag-agent/backend/src/trust/fields.py`

**Do.**
1. For each value, combine: OCR confidence, column-mapping confidence, `is_ai_inferred`,
   validation issues, field criticality.
2. Apply the brief §7 band structure — GREEN ≥95, AMBER 80–94.9, RED <80 — as the
   **starting hypothesis**, with critical fields held to a stricter bar than secondary
   ones (brief §8). Mark the constants uncalibrated pending `TL-4.7`.
3. `is_ai_inferred=True` caps the achievable state below `VERIFIED` — an AI-inferred
   column mapping is not source truth.
4. `ocr_confidence is None` for an exact-read source (CSV/MPP/MSPDI) is **not** a
   penalty; `None` because the span was unresolvable **is**. Distinguish via
   `extraction_method`.

**Acceptance criteria.**
- [ ] Every critical field on every fixture receives a trust state
- [ ] AI-inferred fields never reach `VERIFIED`
- [ ] Exact-read sources are not penalised for having no OCR confidence
- [ ] Unresolvable OCR spans do reduce the state
- [ ] Thresholds are named constants marked uncalibrated

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_value_trust.py -q`

**Do not.** Do not treat missing evidence as good evidence. Absent data maps to
`UNVERIFIED`, never `VERIFIED`.

---

### TL-4.3 — Weakest-link propagation

**Brief:** §14 · **Blocked by:** TL-4.2 · **Blocks:** TL-4.4

**Why.** The core anti-laundering rule. Without it, every downstream layer can silently
upgrade its own confidence.

**Files.**
- `rag-agent/backend/src/trust/engine.py`

**Do.**
1. Implement `propagate(dependencies) -> TrustAssessment` using a weakest-link rule over
   **materially relevant** dependencies, not an average.
2. "Materially relevant" must be explicit: a derived value depends on the specific
   fields that produced it, not on every field of the activity. Record the dependency
   set per derived value.
3. The resulting assessment names the weakest contributor so `TL-7.5`'s "Why?" can
   explain it.
4. Add the brief §14 worked example as a test: OCR 99 / parse 100 / match 96 / calc 100
   → high; OCR 67 / parse 91 / match 58 → must not be high.

**Acceptance criteria.**
- [ ] Propagation is weakest-link, not averaging — asserted by test
- [ ] Both brief §14 example chains produce the documented outcomes
- [ ] Every propagated assessment names its weakest link
- [ ] A strong LLM output over weak inputs cannot yield a `VERIFIED` result

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_propagation.py -q`

**Do not.** Do not average. Do not let an unrelated high-confidence dependency lift a
weak one.

---

### TL-4.4 — Feature-specific confidence

**Brief:** §30 · **Blocked by:** TL-4.3 · **Blocks:** TL-4.6

**Why.** Brief §30: *"'Nova trusts the project 93%' is less useful than telling users
which analyses are trustworthy."* Target shape:

```
Schedule Parsing       VERIFIED
Activity Matching      VERIFIED
Progress Comparison    VERIFIED
Critical Path          REVIEW
Forecast               UNAVAILABLE
```

**Files.**
- `rag-agent/backend/src/trust/engine.py`
- `rag-agent/backend/src/experimental/nusf_compare_engine.py`
- `rag-agent/backend/src/version_1_0/adapters.py`

**Do.**
1. Define the feature set: schedule parsing, activity matching, progress comparison,
   critical path, forecast.
2. Compute each independently from its own dependency set.
3. Add `UNAVAILABLE` as a distinct feature-level outcome — a feature with no usable
   input is not the same as one with poor input.
4. **Critical path deserves special handling**: the deterministic engine populates it
   only from explicit `critical_flag` / `total_float`; when absent, it is currently
   LLM-inferred. Inferred critical path must never be `VERIFIED` — it is an inference
   (brief §19) and this is where that gets enforced.

**Acceptance criteria.**
- [ ] Five feature confidences computed independently
- [ ] LLM-inferred critical path never reports `VERIFIED`
- [ ] A schedule with no float data reports critical path as `REVIEW` or `UNAVAILABLE`
- [ ] Feature confidences appear in the dashboard payload

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_feature_confidence.py -q`

**Do not.** Do not roll these into one project number. The single number arrives in
`TL-7.2` *in addition to*, never instead of, these.

---

### TL-4.5 — Conflict detection rules

**Brief:** §27 · **Blocked by:** TL-4.2

**Why.** Brief §27 wants Nova to actively hunt contradictions and **flag** them rather
than silently resolve them. Note that the pipeline currently *auto-resolves* one of the
listed conflicts: inverted start/finish dates are silently swapped during normalization.

**Files.**
- `rag-agent/backend/ingestion/validation/issues.py`
- `rag-agent/backend/ingestion/validation/engine.py`
- `rag-agent/backend/src/trust/engine.py`

**Do.**
1. Implement every conflict from brief §27:
   same ID → different names; same activity → multiple IDs; finish before start;
   progress > 100%; missing duration; duplicate activity IDs; impossible date parsing;
   activity marked removed but appearing elsewhere; large unexplained field changes.
2. Each emits a `SOURCE_CONFLICT` flag with the conflicting values attached.
3. **Keep the date auto-swap** (it is pragmatic and already flags `has_logic_warning`)
   but ensure the conflict is surfaced, not just logged — currently the swap happens
   and the user never learns the source was contradictory.
4. Conflicts cap the affected value's trust state.

**Acceptance criteria.**
- [ ] All nine conflict types from brief §27 detected
- [ ] Each conflict records both conflicting values
- [ ] Auto-swapped dates surface a visible conflict, not a silent correction
- [ ] Conflicted values cannot report `VERIFIED`
- [ ] The conflict fixture from `TL-0.1` triggers the expected set

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_conflict_detection.py -q`

**Do not.** Do not auto-resolve a conflict without recording it. Brief §27's whole point
is "instead of silently resolving: FLAG THEM."

---

### TL-4.6 — Pre-flight source quality check + PASS/PARTIAL/BLOCK gating

**Brief:** §28, §29 · **Blocked by:** TL-4.4, TL-4.5 · **Blocks:** Phase 5

**Why.** Brief §28 wants a quality report *before* analysis; §29 wants three graduated
outcomes so one bad field does not stop a project, but half an unparseable schedule does.

**Files.**
- create `rag-agent/backend/src/trust/preflight.py`
- `rag-agent/backend/src/main.py` — both health routes, both predictive routes
- `rag-agent/backend/ingestion/pipeline.py`

**Do.**
1. Produce the brief §28 report shape: activities detected, confidently parsed,
   requiring review, unresolved.
2. Decide `PASS` / `PARTIAL` / `BLOCK` per brief §29 (10 unreadable IDs with strong
   alternative matches → `PARTIAL`; half the schedule unparseable → `BLOCK`).
3. On `PARTIAL`, analysis proceeds with affected activities excluded or marked, and the
   response states what was excluded.
4. On `BLOCK`, return a structured refusal — *"Nova has paused analysis to avoid
   producing unreliable results"* — not an HTTP 500. This must be a first-class product
   state that both Flask backends and both React apps render properly.
5. Thresholds are placeholders pending `TL-4.7`.

**Acceptance criteria.**
- [ ] Every analysis produces a pre-flight report before the LLM is called
- [ ] All three outcomes reachable, each with a fixture
- [ ] `BLOCK` returns a structured, renderable refusal — never a 500
- [ ] `PARTIAL` responses enumerate what was excluded and why
- [ ] Both Flask backends persist and surface the gating outcome

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_preflight_gating.py -q`

**Do not.** Do not implement `BLOCK` as an exception. The Flask layer currently marks a
run `'completed'` on HTTP 200 alone — an exception-shaped block will be recorded as a
failure rather than as the deliberate protective decision it is.

---

### TL-4.7 — Calibrate trust thresholds

**Brief:** §7, §23, §35 · **Blocked by:** EXT-1 · **Status: BLOCKED**

**Why.** Same reasoning as `TL-3.6`. The 95/80 bands are the brief's own starting
hypotheses and are explicitly labelled as such.

**Files.**
- `rag-agent/backend/src/trust/engine.py`
- `rag-agent/backend/src/trust/fields.py`
- `rag-agent/backend/src/trust/preflight.py`

**Do (once `EXT-1` lands).**
1. Measure actual OCR confidence distributions per field across real K&L documents.
2. Determine the confidence level at which a value is genuinely likely wrong — the band
   edges must be empirical, not inherited from the brief's illustration.
3. Calibrate per-criticality separately (brief §8).
4. Calibrate the `PARTIAL`/`BLOCK` boundaries against real document quality.
5. Record distributions, chosen thresholds, and reasoning in `DECISIONS.md`; remove the
   uncalibrated markers.

**Acceptance criteria.**
- [ ] Confidence distributions measured per critical field on real documents
- [ ] Band edges justified empirically, not by inheritance from the brief
- [ ] Critical and secondary fields calibrated separately
- [ ] Gating boundaries validated against real documents
- [ ] All uncalibrated markers removed

**Verify.** `cd rag-agent/backend && python -m tests.trust.harness calibrate --real`

**Do not.** Do not describe any threshold as calibrated until this task is `DONE`.
Do not publish an accuracy percentage anywhere — brief §23: confidence ≠ accuracy.
