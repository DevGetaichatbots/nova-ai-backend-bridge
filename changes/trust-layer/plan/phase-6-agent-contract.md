# Phase 6 — Response contract & claim verification

**Goal.** No factual claim reaches a user unless it traces to verified source data or a
deterministic calculation.

**User-visible change.** Partly — narratives become more careful, some claims are
qualified or removed, and the agent will sometimes decline to answer.

**Brief §16 calls this "one of the biggest improvements I would build."** The example:

> "Electrical works in Building NK are the project's largest concentration of delay,
> with 17 activities behind schedule and three critical activities."

Nova should verify each claim independently — largest concentration? 17 delayed?
3 critical? — and only display after validation. If claim 3 cannot be validated, remove
it or say *"Critical status could not be verified for all activities."*

---

### TL-6.1 — Agent response contract structure

**Brief:** §33 · **Blocked by:** TL-5.6 · **Blocks:** TL-6.2

**Why.** Brief §33 specifies the internal structure every agent answer must carry.
The frontend need not expose it, but the backend must enforce it.

**Files.**
- create `rag-agent/backend/src/trust/response_contract.py`

**Do.**
1. Define `AgentResponse` with exactly the brief §33 fields:
   `answer`, `supporting_facts[]`, `source_references[]`, `confidence_state`,
   `inferences[]`, `unverified_claims[]`.
2. Enforce the brief's gate before rendering:
   `if unverified_claims: remove / qualify / reject`.
3. Make it structurally impossible to render a response that bypasses the gate — the
   renderer accepts only a validated response object, never a raw string.
4. Apply to the predictive agent and the health enrichment call alike.

**Acceptance criteria.**
- [ ] `AgentResponse` carries all six brief §33 fields
- [ ] The render path accepts only validated response objects
- [ ] A response with unresolved `unverified_claims` cannot be rendered
- [ ] Both agents produce responses through this contract

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_response_contract.py -q`

**Do not.** Do not add a bypass flag for "trusted" callers. A bypass will become the
default path within two sprints.

---

### TL-6.2 — Claim extraction from generated narrative

**Brief:** §16 · **Blocked by:** TL-6.1 · **Blocks:** TL-6.3

**Why.** You cannot verify claims you have not isolated.

**Files.**
- create `rag-agent/backend/src/trust/claims.py`

**Do.**
1. Extract atomic factual claims from narrative text. Prioritise the mechanically
   detectable, high-risk forms — these cover most of the real hallucination surface:
   - numeric quantity claims ("17 activities behind schedule")
   - superlative/ranking claims ("largest concentration")
   - activity ID references
   - date and duration claims
   - causal claims ("caused by…") — always suspect, per brief §20
2. Each `Claim` records its text span, kind, extracted values, and the fields it asserts.
3. Deterministic extraction (parsing/regex over a constrained generated format) is
   strongly preferred. If a model is used to assist extraction, its output is itself
   unverified and must not be trusted to *clear* a claim — only to find candidates.
4. Unparseable narrative that cannot be decomposed is treated as unverified, not as safe.

**Acceptance criteria.**
- [ ] All five claim kinds extracted, each with a test
- [ ] The brief §16 example decomposes into its three claims
- [ ] Claims record spans, enabling targeted removal or qualification
- [ ] Text that cannot be decomposed is marked unverified rather than passed through

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_claim_extraction.py -q`

**Do not.** Do not let a model be the arbiter of whether a claim is supported. It can
propose candidates; verification is `TL-6.3`'s deterministic job.

---

### TL-6.3 — Claim verification against the fact store

**Brief:** §16 · **Blocked by:** TL-6.2 · **Blocks:** TL-6.4, TL-6.5, TL-6.7

**Why.** This is the enforcement point that makes brief §34's "architecture, not prompts"
real.

**Files.**
- `rag-agent/backend/src/trust/claims.py`
- `rag-agent/backend/src/trust/engine.py`

**Do.**
1. Verify each claim against the Phase 5 deterministic fact set:
   - numeric claims → recount from the fact store
   - ID references → must exist in the source (reuse `TL-2.3`'s guarantee)
   - superlatives → recompute the ranking
   - causal claims → **cannot be verified from schedule data** and are always
     downgraded to inference or removed (brief §18's A142 example)
2. Outcomes: `VERIFIED`, `CONTRADICTED`, `UNVERIFIABLE`.
3. `CONTRADICTED` claims are removed, never merely flagged — displaying a claim the
   system knows is false is the worst outcome in the brief's hierarchy.
4. `UNVERIFIABLE` claims are qualified per brief §16.

**Acceptance criteria.**
- [ ] Numeric claims verified by recount, with a contradiction fixture proving detection
- [ ] Every referenced activity ID verified to exist
- [ ] Superlative claims recomputed, not accepted
- [ ] Causal claims never reach `VERIFIED`
- [ ] `CONTRADICTED` claims are removed from output

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_claim_verification.py -q`

**Do not.** Do not "fix" a contradicted number by rewriting it into the sentence.
`predictive_agent` already does regex renumbering of narrative prose; with deterministic
facts that patching is obsolete and actively harmful — a sentence whose numbers were
swapped underneath it can end up asserting something the corrected figures do not support.

---

### TL-6.4 — Fact / Derived / Inference / Unknown classification

**Brief:** §19 · **Blocked by:** TL-6.3 · **Blocks:** TL-6.6

**Why.** Brief §19: *"Never present inference as fact."*

**Files.**
- `rag-agent/backend/src/trust/claims.py`
- `rag-agent/backend/src/trust/vocabulary.py`

**Do.**
1. Classify every surviving statement using `ClaimKind` from `TL-0.4`:
   - `FACT` — directly from source ("finish date moved 18 days")
   - `DERIVED_FACT` — deterministically calculated ("31 of 73 delayed are in NK")
   - `INFERENCE` — evidence suggests, does not prove ("may indicate a coordination bottleneck")
   - `UNKNOWN` — insufficient evidence
2. LLM-inferred critical path (`TL-4.4`) and forcing assessment (`TL-5.4`) are
   `INFERENCE` by construction — enforce, do not rely on classification at runtime.
3. Classification travels in the payload for `TL-7.3` to render.

**Acceptance criteria.**
- [ ] Every statement carries exactly one `ClaimKind`
- [ ] Inferred critical path and forcing assessment always classify as `INFERENCE`
- [ ] All four brief §19 examples classify as documented
- [ ] No statement defaults to `FACT` implicitly

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_claim_classification.py -q`

**Do not.** Do not classify a `DERIVED_FACT` as `INFERENCE` out of caution. Over-hedging
verified arithmetic erodes trust in the labels themselves.

---

### TL-6.5 — No-answer behaviour

**Brief:** §18, §42 · **Blocked by:** TL-6.3

**Why.** Brief §18: the agent must be technically *allowed* to say "I cannot verify that
from the uploaded schedules." *"This is a feature, not a failure."*

**Files.**
- `rag-agent/backend/src/trust/response_contract.py`
- `rag-agent/backend/src/agent.py` (chat `/query` path, Nova app only)
- `rag-agent/backend/src/predictive_agent.py`

**Do.**
1. Make a structured no-answer a valid, first-class response — not an error, not an
   empty result.
2. Implement the brief §18 pattern: state what *is* known ("A142 is delayed by 18 days"),
   state what is not ("the uploaded data does not contain enough information to determine
   the cause"), then offer a constructive next step ("I can show you the predecessor
   activities and recent schedule changes").
3. Ensure both Flask backends and both React apps render a no-answer as a legitimate
   result rather than a failure state.

**Acceptance criteria.**
- [ ] No-answer is a distinct response type, not an error
- [ ] The brief §18 A142 scenario produces the documented three-part response
- [ ] Both apps render it as a normal result
- [ ] A test asserts a fabricated causal explanation is never returned for an unanswerable question

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_no_answer.py -q`

**Do not.** Do not render a no-answer as an error banner. Brief §42: it should feel
reassuring, not broken.

---

### TL-6.6 — Language guardrails

**Brief:** §20, §46 · **Blocked by:** TL-6.4

**Why.** Brief §20 is emphatic that phrasing matters to construction professionals:
"The project will be delayed" is wrong; "The current schedule pattern indicates increased
delay risk" is right. "Electrical work caused the delay" is wrong unless causality was
established; "The largest concentration of current delay is within electrical activities"
is right.

**Files.**
- `rag-agent/backend/src/trust/claims.py`
- `rag-agent/backend/src/predictive_agent.py` (prompt)

**Do.**
1. Add a deterministic post-generation check for overclaiming patterns: unhedged future
   assertions, unestablished causal verbs ("caused by", "due to", "because of"),
   certainty adverbs attached to inferences.
2. A statement classified `INFERENCE` or `NOVA_FORECAST` that uses fact-grade phrasing is
   rejected back or rewritten to hedged form.
3. Update the prompt too — but the prompt is the last layer, and the check is the
   enforcement (brief §34).
4. Guardrails must work in **Danish as well as English**. Both dashboards ship Danish,
   and Kemp is Danish-only.

**Acceptance criteria.**
- [ ] Overclaiming patterns detected in both EN and DA
- [ ] Both brief §20 wrong/right pairs handled as documented
- [ ] An inference phrased with fact-grade certainty is caught
- [ ] Verified facts are not over-hedged by the check

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_language_guardrails.py -q`

**Do not.** Do not implement this only in the prompt. And do not hedge `DERIVED_FACT`
statements — precision cuts both ways.

---

### TL-6.7 — Unsupported-claim-rate metric

**Brief:** §39 · **Blocked by:** TL-6.3

**Why.** Brief §39 singles this metric out: *"How often does Nova state a factual claim
that cannot be traced to verified source data? Target: 0 unsupported factual claims.
That is more strategically valuable than making the agent sound intelligent."*

**Files.**
- `rag-agent/backend/tests/trust/harness.py`
- `rag-agent/backend/src/trust/claims.py`

**Do.**
1. Instrument every claim verification and record the rate.
2. Add a standing set of test questions run against known fixtures (brief §39's method).
3. Report the rate in `harness compare`; target is zero.
4. Any non-zero rate must enumerate the offending claims for inspection.

**Acceptance criteria.**
- [ ] Rate computed across the full fixture corpus
- [ ] Test-question set defined and committed
- [ ] Non-zero rate lists the specific unsupported claims
- [ ] Metric appears in the regression report as its own line

**Verify.** `cd rag-agent/backend && python -m tests.trust.harness compare`

**Do not.** Do not average this away across many claims. One unsupported factual claim
is a defect, not a rounding error.
