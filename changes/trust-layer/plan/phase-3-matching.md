# Phase 3 — Match confidence & no forced matching

**Goal.** Every cross-revision match carries a confidence level and a method, and Nova
refuses to guess when the evidence is insufficient.

**User-visible change.** Yes — a "requires verification" bucket appears, and some
activities move out of the confirmed comparison results into it.

**The finding this phase exists to fix.** `nusf_compare_engine._resolve_activity_matches`
(~L578–635) handles duplicate-name groups with **greedy nearest-date matching**: it
computes a date distance for every old×new pair in the group, sorts ascending, and
greedily consumes the closest pairs. That is a thoughtful heuristic — and it is
precisely what brief §13 prohibits:

> If Nova cannot confidently determine which is the corresponding activity:
> **DO NOT PICK ONE.** Return: *Match requires verification*.
> This prevents one uncertain match from contaminating every downstream calculation.

The current behaviour always produces a pairing and presents it with the same
visual authority as an exact ID match.

---

### TL-3.1 — `MatchConfidence` level model

**Brief:** §12 · **Blocked by:** TL-2.6 · **Blocks:** TL-3.2

**Why.** Brief §12 defines a five-level hierarchy. Encode it as data before applying it.

**Files.**
- create `rag-agent/backend/src/trust/matching.py`

**Do.**
1. Define `MatchLevel` exactly per brief §12:
   - `L1_EXACT_VERIFIED_ID` — same verified source identifier — very high
   - `L2_STRONG_MULTI_FIELD` — name + location + trade + building/floor all align — high
   - `L3_PARTIAL` — name + location align, other fields differ or missing — medium
   - `L4_FUZZY` — similarity exists, evidence insufficient — low
   - `L5_NO_RELIABLE_MATCH` — **must not match**
2. Define `MatchResult` carrying `level`, `method`, `evidence` (which fields aligned),
   `candidates` (for ambiguity), and `requires_verification: bool`.
3. Map `L4` and `L5` to `requires_verification = True` by default.
4. Provide `to_trust_state(level)` mapping into `TrustState` from `TL-0.4`.

**Acceptance criteria.**
- [ ] All five levels defined with the brief's semantics
- [ ] `MatchResult` records which fields provided the evidence
- [ ] `L5` cannot be constructed with a non-null matched counterpart (enforce in the type)
- [ ] Mapping to `TrustState` is total

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_match_levels.py -q`

**Do not.** Do not add a numeric percentage to match confidence. Levels are categorical
by design (brief §23 — avoid unsupported precision).

---

### TL-3.2 — Classify every match with level and method

**Brief:** §12 · **Blocked by:** TL-3.1 · **Blocks:** TL-3.3 · **Resolves Q-3**

**Why.** Today matching produces a pairing with no confidence attached, so downstream
code cannot distinguish an exact-ID match from a name-similarity guess.

**Files.**
- `rag-agent/backend/src/experimental/nusf_compare_engine.py` — `_resolve_activity_matches`, `_group_key`, identity resolution

**Do.**
1. Classify each match into a `MatchLevel` using the evidence actually available:
   - durable `stable_key` / verified `source_id` equality → `L1`
   - name + location + trade + floor all align → `L2`
   - name + location align only → `L3`
   - similarity below the multi-field bar → `L4`
   - nothing credible → `L5`
2. Attach the `MatchResult` to every matched pair, and to every unmatched row
   (as `L5` with candidates listed).
3. Resolve `Q-3` and record it: an activity with an unreadable ID but a strong
   multi-field match — is it `VERIFIED` or `REVIEW`? Recommendation: `L2` → `REVIEW`,
   because brief §37 says a wrong confident match is worse than no match, and precision
   comes first. Whatever is chosen, write it in `DECISIONS.md`.
4. Preserve `_identity_label` as the human-readable explanation of the method.

**Acceptance criteria.**
- [ ] Every match in every fixture carries a level and a method
- [ ] Fixture with durable IDs yields `L1` for all matches
- [ ] Fixture with positional-only IDs yields no `L1` matches at all
- [ ] `Q-3` resolved in `DECISIONS.md` and reflected in the level→state mapping

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_match_classification.py -q`

**Do not.** Do not assign `L1` on `source_id` equality unless that ID column was
verified durable. MS Project's positional ID compares equal by accident constantly —
the existing `_STABLE_ID_HEADERS` / `_POSITIONAL_ID_HEADERS` distinction exists for
exactly this reason and must be respected.

---

### TL-3.3 — Replace greedy nearest-date forcing with ambiguity detection

**Brief:** §13 · **Blocked by:** TL-3.2 · **Blocks:** TL-3.4, TL-3.5

**Why.** This is the phase's core change, and the most behaviour-affecting task in the
whole plan. See the finding at the top of this file.

**Files.**
- `rag-agent/backend/src/experimental/nusf_compare_engine.py` — `_resolve_activity_matches` (~L578–635), `_date_distance`

**Do.**
1. Keep the date-distance computation — it is good evidence. Change what is done with it.
2. Within a duplicate-name group, a pairing is accepted only when it is **unambiguous**:
   the best candidate must be separated from the runner-up by a clear margin. Where the
   best and second-best are close, emit `L4` + `requires_verification` for **both**
   rather than consuming the pair.
3. Define the margin as a named, documented constant with a placeholder value, marked
   uncalibrated pending `TL-3.6`.
4. Unmatched-but-plausible rows must record their `candidates` so the review queue
   (Phase 8) can offer "Option A / Option B / No match" as brief §25 describes.
5. Expect the added/removed counts to rise. That is correct behaviour, not a regression —
   but every fixture's delta must be explainable against ground truth.

**Acceptance criteria.**
- [ ] The ambiguous-candidates fixture produces `requires_verification`, not an arbitrary pairing
- [ ] The unique-name fixture is unaffected (still matches cleanly)
- [ ] Every ambiguous row records its candidate list
- [ ] Margin constant is named, documented, and marked uncalibrated
- [ ] `harness compare` deltas are fully explained in the commit message

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_no_forced_matching.py -q && python -m tests.trust.harness compare`

**Do not.** Do not tune the margin to minimise the number of review items. Brief §37 is
explicit: *"I'd rather Nova correctly match 95 activities and say 5 require review than
match all 100 while 3 are secretly wrong."* Optimise for precision.

---

### TL-3.4 — Isolate ambiguous matches from confirmed results

**Brief:** §13, §29, §42 · **Blocked by:** TL-3.3

**Why.** Brief §13's rationale is contamination: one uncertain match must not pollute
every downstream calculation. So ambiguous activities must be excluded from confirmed
counts, not merely flagged inside them.

**Files.**
- `rag-agent/backend/src/experimental/nusf_compare_engine.py` — section assembly, `executive_summary`
- `rag-agent/backend/src/version_1_0/adapters.py` — `adapt_health_dashboard`

**Do.**
1. Route `requires_verification` activities into a dedicated bucket, excluded from
   behind/ahead/changed/stage counts.
2. Executive summary reports both: confirmed counts, plus "N require verification".
3. Wording per brief §42 — protective, not broken:
   *"Nova found insufficient evidence to reliably match this activity between the two
   schedules. The activity has therefore been excluded from confirmed comparison results."*
4. Never let an excluded activity vanish. It must be reachable and countable.

**Acceptance criteria.**
- [ ] Ambiguous activities excluded from all confirmed KPI counts
- [ ] Total is reconcilable: confirmed + requires-verification + unmatched = all activities
- [ ] A test asserts that reconciliation on every fixture
- [ ] No activity is silently dropped

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_ambiguity_isolation.py -q`

**Do not.** Do not report the requires-verification count inside the delayed count.
Mixing them recreates exactly the contamination this task removes.

---

### TL-3.5 — Precision-first metrics in the harness

**Brief:** §37, §38 · **Blocked by:** TL-3.3

**Why.** Brief §37 asks for false positives to be measured *separately*, because for
Nova an incorrect confident match is worse than no match.

**Files.**
- `rag-agent/backend/tests/trust/harness.py`
- `rag-agent/backend/tests/trust/test_regression.py`

**Do.**
1. Compute against fixture ground truth: **match precision**, **false match rate**,
   **unmatched rate**, **requires-verification rate**.
2. Report precision and recall separately — never a blended F-score, which would let
   precision loss hide behind recall gains.
3. Add `false match rate` to the regression report as its own category (brief §36 names
   false-match regression as a release gate).

**Acceptance criteria.**
- [ ] All four metrics computed per fixture and in aggregate
- [ ] Precision and recall reported separately
- [ ] A deliberately introduced false match is caught and reported
- [ ] Metrics appear in `harness compare` output

**Verify.** `cd rag-agent/backend && python -m tests.trust.harness compare`

**Do not.** Do not report a single blended accuracy number. Brief §23 and §37 both
argue against it.

---

### TL-3.6 — Calibrate matching thresholds

**Brief:** §7, §35 · **Blocked by:** EXT-1 · **Status: BLOCKED**

**Why.** Brief §7: *"Do NOT hard-code arbitrary thresholds without calibration against
real K&L schedules… these numbers are starting hypotheses, not final thresholds."*
Everything shipped in `TL-3.3` is a structural placeholder.

**Files.**
- `rag-agent/backend/src/trust/matching.py`
- `rag-agent/backend/tests/trust/fixtures/` (extend with real pairs)

**Do (once `EXT-1` lands).**
1. Add the real K&L pairs to the corpus with their ground truth.
2. Sweep the ambiguity margin and multi-field thresholds; plot precision vs.
   review-queue volume.
3. Choose the operating point that maximises precision subject to a review-queue volume
   K&L will actually work through. Record the tradeoff and the chosen point in `DECISIONS.md`.
4. Remove the "uncalibrated" markers from the constants.

**Acceptance criteria.**
- [ ] ≥10 real schedule pairs in the corpus with ground truth
- [ ] Calibration sweep recorded with results
- [ ] Chosen thresholds justified in `DECISIONS.md` with the precision/volume tradeoff stated
- [ ] False match rate on real data measured and recorded as the new baseline

**Verify.** `cd rag-agent/backend && python -m tests.trust.harness compare --real`

**Do not.** Do not start this before real data exists. Calibrating against synthetic
fixtures produces numbers that look authoritative and mean nothing — which is the exact
failure mode this whole programme is meant to eliminate.
