# Phase 5 — Deterministic facts for Predictive

**Goal.** Remove the LLM from fact extraction in the Predictive Dashboard. The model
explains verified facts; it does not discover them.

**User-visible change.** None intended — the numbers should be the same or better.
Any change is a bug found, and must be explained.

**Why this phase is the largest architectural change in the plan.**

The Health Dashboard already largely satisfies brief §4: in NUSF mode, matching,
deltas, counts and classifications are computed in `nusf_compare_engine` in pure Python,
and the LLM is a narrow enrichment layer.

**The Predictive Dashboard does not.** Its `delayed_activities` array — the row-level
facts: which activities are delayed, their IDs, dates, `days_overdue`, priority — is
produced *by the model* from a text dump of the schedule. Python then prunes rows with
`days_overdue <= 0`, recounts totals, and regex-rewrites the narrative to match. That is
real defensive engineering, but it corrects arithmetic *about* a fact set the LLM invented.

Brief §4 is unambiguous:

> The AI/LLM should not independently "look at the schedule and decide" numerical facts
> whenever those facts can be determined programmatically. […] The LLM's job becomes:
> explain the truth, rather than discover/invent the truth.

Every delay rule the model is asked to apply is already written in deterministic prose in
`PREDICTIVE_SYSTEM_PROMPT` (`start < reference_date AND progress == 0%`, the Plandisc
conditions, the forcing rules). This phase moves them into code.

---

### TL-5.1 — Deterministic delayed-activity detection

**Brief:** §4, §15 · **Blocked by:** TL-4.6 · **Blocks:** TL-5.2

**Why.** The detection rule is already fully specified and entirely mechanical. Nothing
about it needs a language model.

**Files.**
- create `rag-agent/backend/src/trust/predictive_facts.py`
- `rag-agent/backend/src/predictive_agent.py` (reference for the rules being ported)

**Do.**
1. Port the standard rule to code: an activity is delayed when
   `planned_start < reference_date AND percent_complete == 0`.
2. Port the Plandisc conditions (A/B/C on `is_late`, actual completion, `inspectedType`),
   including the trap the prompt warns about: `planned_completion_pct` is always 100 and
   must never be read as progress.
3. Detection runs against normalized NUSF `Activity` objects, not text.
4. Every detected activity carries its provenance and trust state from Phases 1 and 4.
5. Validate against the prompt's own stated expectation: if 50 activities share a start
   date and all are 0%, all 50 must be detected — no sampling, no truncation.

**Acceptance criteria.**
- [ ] Detection is pure Python over `Activity` objects, no LLM call
- [ ] Standard and Plandisc rules both implemented, with fixtures for each
- [ ] The 50-shared-start-date case detects all 50
- [ ] `planned_completion_pct` is never used as progress — asserted by test
- [ ] Detected counts match or exceed the current LLM-derived counts on every fixture

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_delay_detection.py -q`

**Do not.** Do not keep the LLM detection as a fallback that silently activates. If
deterministic detection cannot run, that is a gating decision (`TL-4.6`), not a reason
to hand the job back to the model.

---

### TL-5.2 — Deterministic overdue, priority, and root-cause computation

**Brief:** §4, §15 · **Blocked by:** TL-5.1 · **Blocks:** TL-5.3

**Why.** Brief §15: *"Anything that can be mathematically calculated should NOT be
calculated by the LLM."* `days_overdue` is arithmetic. Priority bucketing is a threshold
rule. Root cause vs. downstream consequence is a dependency-graph question.

**Files.**
- `rag-agent/backend/src/trust/predictive_facts.py`

**Do.**
1. `days_overdue` computed from dates in code.
2. Priority (`CRITICAL_NOW` / `IMPORTANT_NEXT` / `MONITOR`) from documented thresholds.
3. Root cause vs. downstream consequence derived from the **relationship graph**
   (`predecessors` / `successors` already exist on `Activity`), not from model judgement.
   The prompt's own sanity rule — expect 3–10 root causes for 20–40 delays — becomes a
   verifiable property rather than a hope.
4. The existing Python post-hoc corrections in `predictive_agent.analyze()` (the
   `days_overdue <= 0` prune and the root-cause ratio fix) become **unnecessary**.
   Remove them and note in the commit that they are superseded, not forgotten.

**Acceptance criteria.**
- [ ] `days_overdue`, priority, and root-cause flags all computed in Python
- [ ] Root cause derived from the dependency graph, with a fixture proving the chain
- [ ] Post-hoc pruning and ratio-correction code removed as superseded
- [ ] Counts are stable across repeated runs on the same input (no model variance)

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_predictive_computation.py -q`

**Do not.** Do not leave the old correction code in place "just in case". Two
correction layers over a now-deterministic fact set will diverge and mask bugs.

---

### TL-5.3 — Structured verified context builder

**Brief:** §17 · **Blocked by:** TL-5.2 · **Blocks:** TL-5.4, TL-5.5

**Why.** Brief §17: *"Do not send huge raw OCR dumps to the LLM and ask 'What is
happening?' Instead generate structured verified context."* Today `_build_predictive_context`
concatenates table chunks into a ~1.9MB text blob.

**Files.**
- create `rag-agent/backend/src/trust/context.py`
- `rag-agent/backend/src/main.py` — `_build_predictive_context` (~L835–864)

**Do.**
1. Build a structured, verified JSON context from the Phase 5 fact set — the shape brief
   §17 illustrates: project status counts, clusters by location/trade with counts and
   confidence.
2. Include **only** values that passed the Trust Engine. `UNVERIFIED` values are either
   omitted or explicitly labelled unverified; they are never passed as plain facts.
3. Attach a trust state to every supplied fact so the model can be instructed to
   qualify accordingly.
4. Context becomes dramatically smaller — which resolves the truncation problem
   structurally rather than by raising a limit (`TL-5.5`).

**Acceptance criteria.**
- [ ] Context is structured data, not concatenated raw rows
- [ ] Every supplied fact carries a trust state
- [ ] `UNVERIFIED` values are never presented as plain facts
- [ ] Context size for the largest fixture drops by at least an order of magnitude
- [ ] Context is deterministic for a given input

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_structured_context.py -q`

**Do not.** Do not include raw OCR text as a "just in case" appendix. That reopens the
hallucination surface this task closes.

---

### TL-5.4 — Demote `predictive_agent` to interpretation-only

**Brief:** §4, §17 · **Blocked by:** TL-5.3 · **Blocks:** TL-5.6

**Why.** With facts computed and supplied, the model's remaining job is explanation,
prioritisation of actions, and narrative — brief §4's "explain the truth" role.

**Files.**
- `rag-agent/backend/src/predictive_agent.py` — `NOVA_INSIGHT_SCHEMA`, `PREDICTIVE_SYSTEM_PROMPT`, `analyze()`
- `rag-agent/backend/src/main.py` — both predictive routes

**Do.**
1. Split `NOVA_INSIGHT_SCHEMA` into a **facts** half (supplied by us, echoed back
   unchanged or not returned at all) and a **narrative** half (the model's actual output).
2. Remove fact-extraction instructions from the prompt; replace with brief §17's
   directive: *"Explain only the supplied facts. Do not introduce facts not contained in
   the structured context."*
3. Any activity ID, date, or count in the model's output must be traceable to the
   supplied context. This is checked in Phase 6 (`TL-6.3`), but the schema must be shaped
   to make checking possible now.
4. Keep `temperature=0, top_p=0.1, seed=42`.
5. The forcing assessment stays with the model for now — it is genuinely judgemental —
   but it must be explicitly classified as `INFERENCE` (brief §19) in `TL-6.4`.

**Acceptance criteria.**
- [ ] Schema separates supplied facts from generated narrative
- [ ] Prompt contains no fact-extraction instructions
- [ ] Model output contains no activity ID absent from the supplied context
- [ ] Determinism settings unchanged
- [ ] Predictive counts on every fixture match Phase 5's deterministic values exactly

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_interpretation_only.py -q && python -m tests.trust.harness compare`

**Do not.** Do not rely on the prompt alone to prevent fact invention (brief §34). The
prompt change is necessary and insufficient; `TL-6.3` provides the enforcement.

---

### TL-5.5 — Remove silent context truncation

**Brief:** §17, §28 · **Blocked by:** TL-5.3

**Why.** `_build_predictive_context` caps context at 1,900,000 bytes and drops
everything beyond with only a `logger.warning`. A user receives a confident report over
a partial schedule with no indication anything was omitted — a textbook case of the
failure the brief exists to prevent.

**Files.**
- `rag-agent/backend/src/main.py` — `_build_predictive_context`
- `rag-agent/backend/src/trust/context.py`
- `rag-agent/backend/src/trust/preflight.py`

**Do.**
1. With structured context (`TL-5.3`), the cap should rarely bind. Keep a limit as a
   backstop — but make hitting it a **gating event**, not a silent drop.
2. Hitting the limit routes to `PARTIAL` (analysis proceeds, omission is stated) or
   `BLOCK` (too much omitted to be meaningful) per `TL-4.6`.
3. The response must state what was omitted and why.
4. Add a fixture that exceeds any plausible limit and assert it never silently truncates.

**Acceptance criteria.**
- [ ] Truncation is impossible without a corresponding gating outcome
- [ ] Oversized fixture produces `PARTIAL` or `BLOCK`, never a silent partial result
- [ ] Response enumerates what was omitted
- [ ] A test asserts no code path drops context with only a log line

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_no_silent_truncation.py -q`

**Do not.** Do not simply raise the byte limit. Raising it moves the cliff; it does not
remove it.

---

### TL-5.6 — Separate FORECAST from FACT in the schema

**Brief:** §31, §45 · **Blocked by:** TL-5.4

**Why.** Brief §31 holds predictive features to a higher standard: *"Never make a
prediction visually indistinguishable from an observed fact."* Currently observed facts
(an activity is 44 days overdue) and forecasts (elevated risk of further delay) sit in
one flat schema with identical status.

**Files.**
- `rag-agent/backend/src/predictive_agent.py` — schema
- `rag-agent/backend/src/trust/vocabulary.py` — `EvidenceClass`

**Do.**
1. Tag every output element with an `EvidenceClass` (from `TL-0.4`):
   `SOURCE_DATA`, `NOVA_CALCULATION`, `NOVA_INSIGHT`, `NOVA_FORECAST`.
2. Forecast elements additionally carry: confidence band/category, the evidence behind
   them, and key drivers (brief §31's required set).
3. `predictive_snapshot.what_will_happen` and `estimated_delay_impact` are forecasts and
   must be classified as such — they are currently indistinguishable from observations.
4. The classification travels in the payload so `TL-7.4` can render the distinction.

**Acceptance criteria.**
- [ ] Every schema element carries an `EvidenceClass`
- [ ] Forecasts carry confidence band, evidence, and key drivers
- [ ] No element defaults to `SOURCE_DATA` implicitly — classification is explicit
- [ ] A test asserts total classification coverage

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_forecast_classification.py -q`

**Do not.** Do not classify the zero-delay structural-risk narrative as a forecast about
delay. It is an inference about structure — brief §20 is precise about not overclaiming
predictive authority.
