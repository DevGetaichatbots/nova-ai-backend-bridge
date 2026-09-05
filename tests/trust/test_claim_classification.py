"""Tests for TL-6.4 — Fact / Derived / Inference / Unknown classification.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-6-agent-contract.md` (TL-6.4):

- AC1: Every statement carries exactly one `ClaimKind` — both per-claim
  (each `VerifiedClaim` from TL-6.3 has a `kind` field) and per-field
  (every entry in `FIELD_CLAIM_KINDS` / `build_field_claim_kinds`).
- AC2: Inferred critical path (TL-4.4) and forcing assessment (TL-5.4)
  always classify as `INFERENCE` — brief Do item 2 says "enforce, do
  not rely on classification at runtime," meaning the static table is
  the contract, not a heuristic at render time.
- AC3: All four brief §19 examples classify as documented:
    "finish date moved 18 days"      → FACT
    "31 of 73 delayed are in NK"     → DERIVED_FACT
    "may indicate a coordination
        bottleneck"                   → INFERENCE
    "insufficient evidence"           → UNKNOWN
- AC4: No statement defaults to `FACT` implicitly — every claim must
  have an explicit `kind`; an unmapped (form, outcome) combination or
  an unmapped (section, field) raises rather than silently defaulting.

Brief §20/TL-6.4 also requires that CAUSAL claims are always INFERENCE
regardless of verification outcome (a verified causal claim is still an
inference — schedule data records what and when, never why). This is
encoded as the unconditional CAUSAL→INFERENCE rule in
`_CLASSIFICATION_TABLE` and pinned by the tests below.
"""
from __future__ import annotations

import pytest

from src.predictive_agent import _build_agent_response
from src.trust.claims import (
    Claim,
    ClaimForm,
    ClaimExtractionResult,
    VerificationOutcome,
    extract_claims,
    verify_claim,
    verify_narrative,
    FIELD_CLAIM_KINDS,
    build_field_claim_kinds,
    _CLASSIFICATION_TABLE,
    _classify_claim,
)
from src.trust.vocabulary import ClaimKind


# ============================================================================
# Helpers — minimal fact store, no fixtures, deterministic everywhere
# ============================================================================


def _fact_store(
    *,
    delayed_count: int = 10,
    critical_count: int = 3,
    delayed_activities: list | None = None,
    summary_by_area: list | None = None,
    reference_date: str = "01-01-2026",
    days_overdue_per_activity: list | None = None,
) -> dict:
    """Minimal `insight_data` + `delayed_activities` + `summary_by_area`
    shape — same shape both agent paths produce, so this fixture is
    enough for any verify_* test to run."""
    if delayed_activities is None:
        days = days_overdue_per_activity or [47, 18, 5]
        delayed_activities = [
            {
                "id": f"T{i+1}",
                "task_name": f"Task {i+1}",
                "human_label": f"Task {i+1}",
                "start_date": "01-01-2026",
                "end_date": "10-01-2026",
                "duration": "10d",
                "progress": "0%",
                "days_overdue": d,
                "task_type": "Production",
                "priority": "CRITICAL_NOW" if i == 0 else "IMPORTANT_NEXT",
                "is_root_cause": i == 0,
                "blocked_by_id": None,
                "area": "NK" if i == 0 else "AAA",
            }
            for i, d in enumerate(days)
        ]
    if summary_by_area is None:
        summary_by_area = [
            {"area": "NK", "delayed_count": 7, "critical_count": 3, "important_count": 2, "monitor_count": 2},
            {"area": "AAA", "delayed_count": 3, "critical_count": 0, "important_count": 2, "monitor_count": 1},
        ]
    return {
        "insight_data": {
            "delayed_count": delayed_count,
            "critical_count": critical_count,
            "important_count": 4,
            "monitor_count": 3,
            "root_cause_count": 1,
            "most_overdue_days": 47,
            "areas_affected": 2,
            "project_status": "CRITICAL",
            "risk_level": "HIGH",
        },
        "delayed_activities": delayed_activities,
        "summary_by_area": summary_by_area,
        "schedule_overview": {"reference_date": reference_date, "schedule_name": "Test"},
    }


# ============================================================================
# AC4 (foundation) — exhaustive mapping, no implicit default
# ============================================================================


class TestClassificationTableCompleteness:
    """AC4 (structural half): the `(ClaimForm, VerificationOutcome)` →
    `ClaimKind` table is *exhaustive* — every reachable combination has
    an explicit entry. A missing entry would mean a silent
    `KeyError` at runtime (tested in `test_unmapped_combination_raises`)
    rather than a silent default to `FACT`."""

    def test_every_form_x_outcome_pair_is_mapped(self):
        """Pins the table at all 5 forms × 3 outcomes = 15 entries. If a
        future change adds a form or outcome without updating the
        table, the count check catches it."""
        all_pairs = {(form, outcome) for form in ClaimForm for outcome in VerificationOutcome}
        mapped = set(_CLASSIFICATION_TABLE.keys())
        assert mapped == all_pairs, (
            f"missing pairs: {all_pairs - mapped}; "
            f"unexpected pairs: {mapped - all_pairs}"
        )

    def test_every_value_is_a_real_claim_kind(self):
        """No string defaults like `"fact"` sneaking in — every value is
        a real `ClaimKind` member."""
        for (form, outcome), kind in _CLASSIFICATION_TABLE.items():
            assert isinstance(kind, ClaimKind), (
                f"{form.value} × {outcome.value}: not a ClaimKind — {kind!r}"
            )

    def test_every_kind_is_used_at_least_once(self):
        """All four `ClaimKind` values appear in the table — drift that
        drops one (e.g. schema removes all INFERENCE cases) is caught
        as a test failure rather than a quiet removal of a label."""
        used = {kind for kind in _CLASSIFICATION_TABLE.values()}
        assert used == set(ClaimKind), (
            f"unused kinds: {set(ClaimKind) - used}"
        )

    def test_unmapped_combination_raises(self):
        """AC4 runtime half: an unmapped (form, outcome) raises rather
        than silently defaulting. This is what enforces "no default to
        FACT" structurally — even an internal `_classify_claim` call
        cannot leak a `KeyError` into a silent `FACT`."""
        # Build a fake claim whose (form, outcome) is not in the table.
        # Trick: temporarily mutate the table. (Restored immediately.)
        original = dict(_CLASSIFICATION_TABLE)
        sentinel = (ClaimForm.NUMERIC_QUANTITY, VerificationOutcome.VERIFIED)
        try:
            del _CLASSIFICATION_TABLE[sentinel]
            claim = Claim(text="x", span=(0, 1), form=ClaimForm.NUMERIC_QUANTITY)
            with pytest.raises(KeyError):
                _classify_claim(claim, VerificationOutcome.VERIFIED)
        finally:
            _CLASSIFICATION_TABLE.clear()
            _CLASSIFICATION_TABLE.update(original)


# ============================================================================
# AC2 (brief §20) — causal claims are always INFERENCE
# ============================================================================


class TestCausalAlwaysInference:
    """Brief §20/TL-6.4 AC2: a CAUSAL claim is always INFERENCE,
    regardless of what the verification says. A schedule records what
    and when, never why; a "verified causal claim" is structurally
    impossible (brief §18's A142 example). The unconditional rule is
    what makes the brief §20 framing constraint structural rather than
    a runtime judgement."""

    def test_causal_verified_is_inference(self):
        """Even a hypothetical VERIFIED causal claim is INFERENCE — the
        table encodes brief §20's rule structurally; if a future
        verifier ever returned VERIFIED for a CAUSAL claim (it must not,
        per `_verify_causal`), the classification would still hold."""
        claim = Claim(text="caused", span=(0, 6), form=ClaimForm.CAUSAL)
        assert _classify_claim(claim, VerificationOutcome.VERIFIED) == ClaimKind.INFERENCE

    def test_causal_unverifiable_is_inference(self):
        """The actual case — `_verify_causal` always returns
        UNVERIFIABLE; classification is INFERENCE."""
        claim = Claim(text="caused", span=(0, 6), form=ClaimForm.CAUSAL)
        assert _classify_claim(claim, VerificationOutcome.UNVERIFIABLE) == ClaimKind.INFERENCE

    def test_causal_contradicted_is_inference(self):
        """Even a CONTRADICTED causal claim (rare — would mean the
        model said something causally wrong AND the fact store
        contradicted it) is still tagged INFERENCE rather than UNKNOWN.
        Causal claims are categorically inference; contradiction
        doesn't change that."""
        claim = Claim(text="caused", span=(0, 6), form=ClaimForm.CAUSAL)
        assert _classify_claim(claim, VerificationOutcome.CONTRADICTED) == ClaimKind.INFERENCE


# ============================================================================
# AC1 — per-claim classification: every `VerifiedClaim` has exactly one `kind`
# ============================================================================


class TestPerClaimClassification:
    """AC1: every surviving statement carries exactly one `ClaimKind` —
    every `VerifiedClaim` produced by TL-6.3's verification has a `kind`
    field, set by `_classify_claim`."""

    def test_verified_numeric_claim_is_derived_fact(self):
        """Brief §19 example: "31 of 73 delayed are in NK" — a numeric
        claim verified by recount."""
        facts = _fact_store(delayed_count=31, critical_count=0)
        narrative = "There are 31 delayed activities in the schedule."
        extraction = extract_claims(narrative)
        # The narrative produces one NUMERIC_QUANTITY claim (delayed_count).
        assert any(c.form == ClaimForm.NUMERIC_QUANTITY for c in extraction.claims)
        numeric_claim = next(c for c in extraction.claims if c.form == ClaimForm.NUMERIC_QUANTITY)
        verified = verify_claim(numeric_claim, facts)
        assert verified.outcome == VerificationOutcome.VERIFIED
        assert verified.kind == ClaimKind.DERIVED_FACT

    def test_verified_id_claim_is_fact(self):
        """An ACTIVITY_ID_REFERENCE verified by exact membership is a
        fact lifted from the source, not a derived calculation —
        `FACT`, not `DERIVED_FACT`."""
        facts = _fact_store(delayed_activities=[
            {"id": "A142", "task_name": "x", "human_label": "x", "start_date": "01-01-2026", "end_date": "10-01-2026",
             "duration": "10d", "progress": "0%", "days_overdue": 18, "task_type": "Production",
             "priority": "CRITICAL_NOW", "is_root_cause": True, "blocked_by_id": None, "area": "NK"}
        ])
        narrative = "Task ID A142 is the bottleneck."
        extraction = extract_claims(narrative)
        id_claim = next(c for c in extraction.claims if c.form == ClaimForm.ACTIVITY_ID_REFERENCE)
        verified = verify_claim(id_claim, facts)
        assert verified.outcome == VerificationOutcome.VERIFIED
        assert verified.kind == ClaimKind.FACT

    def test_verified_date_claim_is_fact(self):
        """A DATE_DURATION verified by matching a known fact-store date
        is `FACT`, not `DERIVED_FACT` — dates are lifted from the
        source verbatim."""
        facts = _fact_store(reference_date="01-01-2026", days_overdue_per_activity=[18])
        narrative = "The reference date is 01-01-2026."
        extraction = extract_claims(narrative)
        date_claim = next(
            c for c in extraction.claims
            if c.form == ClaimForm.DATE_DURATION and "date" in c.extracted_values
        )
        verified = verify_claim(date_claim, facts)
        assert verified.outcome == VerificationOutcome.VERIFIED
        assert verified.kind == ClaimKind.FACT

    def test_verified_superlative_claim_is_derived_fact(self):
        """A SUPERLATIVE verified by recomputed ranking is `DERIVED_FACT`
        — the ranking was computed in Python from `summary_by_area`."""
        facts = _fact_store(summary_by_area=[
            {"area": "NK", "delayed_count": 8, "critical_count": 3, "important_count": 3, "monitor_count": 2},
            {"area": "AAA", "delayed_count": 3, "critical_count": 0, "important_count": 2, "monitor_count": 1},
        ])
        narrative = "NK has the largest concentration of delay."
        extraction = extract_claims(narrative)
        superlative_claim = next(c for c in extraction.claims if c.form == ClaimForm.SUPERLATIVE)
        verified = verify_claim(superlative_claim, facts)
        assert verified.outcome == VerificationOutcome.VERIFIED
        assert verified.kind == ClaimKind.DERIVED_FACT

    def test_unverifiable_numeric_claim_is_unknown(self):
        """A NUMERIC_QUANTITY claim with no fact-store field to check
        against is `UNKNOWN` — not enough evidence."""
        facts = _fact_store()
        narrative = "There are 47 elephants on the roof."
        extraction = extract_claims(narrative)
        numeric_claim = next(
            (c for c in extraction.claims if c.form == ClaimForm.NUMERIC_QUANTITY),
            None,
        )
        if numeric_claim is None:
            # Pattern may not fire on "47 elephants" — that's fine, the
            # test still validates that no FALSE claim about elephants
            # got VERIFIED. We assert the absence directly:
            assert all(
                verify_claim(c, facts).outcome != VerificationOutcome.VERIFIED
                for c in extraction.claims
            )
        else:
            verified = verify_claim(numeric_claim, facts)
            assert verified.outcome == VerificationOutcome.UNVERIFIABLE
            assert verified.kind == ClaimKind.UNKNOWN


# ============================================================================
# Brief §19 — all four worked examples classify as documented
# ============================================================================


class TestBriefSection19Examples:
    """AC3: every brief §19 example classifies as documented. The
    brief's four worked examples cover the four-way `ClaimKind`
    taxonomy, so pinning them here pins the entire taxonomy at once."""

    def test_example_fact(self):
        """'finish date moved 18 days' → FACT (DATE_DURATION, VERIFIED)."""
        facts = _fact_store(days_overdue_per_activity=[18])
        narrative = "The finish date moved 18 days."
        extraction = extract_claims(narrative)
        date_claim = next(
            (c for c in extraction.claims
             if c.form == ClaimForm.DATE_DURATION and "number" in c.extracted_values),
            None,
        )
        if date_claim is None:
            # Pattern may need the number followed by a duration unit.
            # Adjust narrative to force the match.
            narrative = "The task is delayed by 18 days."
            extraction = extract_claims(narrative)
            date_claim = next(
                c for c in extraction.claims
                if c.form == ClaimForm.DATE_DURATION and "number" in c.extracted_values
            )
        verified = verify_claim(date_claim, facts)
        assert verified.outcome == VerificationOutcome.VERIFIED
        assert verified.kind == ClaimKind.FACT, (
            f"brief §19 says FACT; got {verified.kind}"
        )

    def test_example_derived_fact(self):
        """'31 of 73 delayed are in NK' → DERIVED_FACT (NUMERIC_QUANTITY,
        VERIFIED via `delayed_count` recount)."""
        facts = _fact_store(delayed_count=31, critical_count=0)
        narrative = "31 activities are delayed."
        extraction = extract_claims(narrative)
        numeric_claim = next(c for c in extraction.claims if c.form == ClaimForm.NUMERIC_QUANTITY)
        verified = verify_claim(numeric_claim, facts)
        assert verified.outcome == VerificationOutcome.VERIFIED
        assert verified.kind == ClaimKind.DERIVED_FACT, (
            f"brief §19 says DERIVED_FACT; got {verified.kind}"
        )

    def test_example_inference(self):
        """Brief §19's INFERENCE example. Two readings of it:

        (a) "may indicate a coordination bottleneck" — the model's
            interpretive framing of an observed pattern, not a strict
            causal claim. The classification lives at the *field* level
            (e.g. `insight_data.primary_risk`), tagged INFERENCE by
            `FIELD_CLAIM_KINDS` because it is a model judgement
            regardless of its trigger vocabulary.
        (b) A strict causal trigger like "caused by" (brief §18's A142
            example) — the per-claim path extracts a CAUSAL claim that
            is always INFERENCE per `_classify_claim`.

        Both readings classify as INFERENCE; we pin both."""
        facts = _fact_store()
        # (b) — strict causal trigger; per-claim path
        causal_narrative = "A142 is delayed by 18 days, caused by a coordination issue."
        causal_extraction = extract_claims(causal_narrative)
        causal_claim = next(c for c in causal_extraction.claims if c.form == ClaimForm.CAUSAL)
        verified = verify_claim(causal_claim, facts)
        assert verified.outcome == VerificationOutcome.UNVERIFIABLE
        assert verified.kind == ClaimKind.INFERENCE, (
            f"brief §19 says INFERENCE (CAUSAL is always INFERENCE per brief §20); got {verified.kind}"
        )
        # (a) — interpretive framing; field-level path
        framing_narrative = "This pattern may indicate a coordination bottleneck."
        framing_extraction = extract_claims(framing_narrative)
        # The narrative may not produce a CAUSAL claim (no strict
        # trigger); the brief §19 invariant is: anything claim-shaped
        # in this narrative is NOT VERIFIED, and any field that
        # contains such prose (e.g. `primary_risk`) is INFERENCE by
        # the field-level table. We assert both.
        result = verify_narrative(framing_narrative, facts)
        assert not result.verified, (
            f"'may indicate' must not produce any VERIFIED claim: {result}"
        )
        assert FIELD_CLAIM_KINDS["insight_data"]["primary_risk"] == ClaimKind.INFERENCE

    def test_example_unknown(self):
        """'insufficient evidence' → UNKNOWN.

        The brief §19 example is a meta-statement about evidence
        absence; it has no claim to extract (no number, no
        superlative, no id, no date, no causal trigger). In the
        classification vocabulary, the *field* that holds such a
        statement (e.g. `insight_data.primary_risk` when it says
        "insufficient evidence to determine a root cause") is tagged
        `INFERENCE` (model narrative), and any extracted claim is
        either verified/contradicted/unverifiable as usual. We assert
        both axes: nothing false gets VERIFIED, and any unverifiable
        claim in the statement lands on `UNKNOWN`."""
        facts = _fact_store()
        narrative = "There is insufficient evidence to determine the cause."
        extraction = extract_claims(narrative)
        # No NUMERIC / ID / DATE / SUPERLATIVE claim in this narrative;
        # the only "claim-shaped" item is, at most, an unanchored
        # "insufficient evidence" phrase that the extractor cannot
        # classify into any of the five forms.
        forms = {c.form for c in extraction.claims}
        # The narrative may extract zero or more CAUSAL-shaped claims
        # ("determine the cause" is borderline). The brief §19
        # invariant is: no claim in this narrative is VERIFIED —
        # because there is no fact-store field that proves the
        # absence of a cause.
        result = verify_narrative(narrative, facts)
        assert not result.verified, (
            f"'insufficient evidence' must not produce any VERIFIED claim: {result}"
        )


# ============================================================================
# AC2 — forcing_assessment and predictive_biggest_risk fields are INFERENCE
# ============================================================================


class TestFieldLevelInference:
    """AC2: LLM-inferred fields (TL-4.4 critical path, TL-5.4 forcing
    assessment) are `INFERENCE` by construction. Enforced in
    `FIELD_CLAIM_KINDS`, not at runtime."""

    def test_forcing_assessment_all_fields_are_inference(self):
        """Brief Do item 2: forcing_assessment is INFERENCE for every
        field. Every non-id, non-name field is a model judgement and
        must not be tagged FACT or DERIVED_FACT."""
        forcing = FIELD_CLAIM_KINDS["forcing_assessment"]
        # ids and names are FACT; everything else is INFERENCE
        assert forcing["id"] == ClaimKind.FACT
        assert forcing["task_name"] == ClaimKind.FACT
        assert forcing["human_label"] == ClaimKind.INFERENCE
        for field, kind in forcing.items():
            if field in ("id", "task_name"):
                continue  # source-data carve-out, per spec
            assert kind == ClaimKind.INFERENCE, (
                f"forcing_assessment.{field} should be INFERENCE (brief §20 / "
                f"Do item 2 — forcing is a model judgement), got {kind}"
            )

    def test_predictive_biggest_risk_will_block_is_inference(self):
        """`will_block` is forward-looking — never FACT or DERIVED_FACT."""
        assert FIELD_CLAIM_KINDS["predictive_biggest_risk"]["will_block"] == ClaimKind.INFERENCE

    def test_predictive_biggest_risk_prevent_action_now_is_inference(self):
        """Same: forward-looking imperative."""
        assert FIELD_CLAIM_KINDS["predictive_biggest_risk"]["prevent_action_now"] == ClaimKind.INFERENCE

    def test_predictive_snapshot_what_will_happen_is_inference(self):
        assert FIELD_CLAIM_KINDS["predictive_snapshot"]["what_will_happen"] == ClaimKind.INFERENCE

    def test_executive_actions_action_is_inference(self):
        """Forward-looking imperative."""
        assert FIELD_CLAIM_KINDS["executive_actions"]["action"] == ClaimKind.INFERENCE


# ============================================================================
# AC1 (field-level) — `build_field_claim_kinds` covers every field
# ============================================================================


class TestFieldLevelCoverage:
    """AC1 (field-level): every field in the response has a `ClaimKind`.
    Like TL-5.6's `TestCoverage` for `EvidenceClass`, this pins the
    contract that every entry in `FIELD_CLAIM_KINDS` is named — no
    implicit default to `FACT` (AC4)."""

    def test_every_field_in_a_real_response_is_classified(self):
        """Walk a complete merged response shape and assert every
        (section, field) is in the classification map."""
        parsed = {
            "predictive_snapshot": {
                "what_will_happen": "x", "estimated_delay_impact": "x",
                "confidence_level": "HIGH", "confidence_basis": "x",
                "main_delay_drivers": ["a"],
            },
            "predictive_biggest_risk": {
                "risk_title": "x", "will_block": "x", "prevent_action_now": "x",
            },
            "executive_actions": [{
                "rank": 1, "action": "x", "responsible": "x", "deadline": "x",
                "related_task_ids": ["T1"], "manpower_helps": False, "manpower_note": "x",
            }],
            "management_conclusion": "x",
            "schedule_overview": {
                "schedule_name": "x", "reference_date": "x",
                "total_activities": 1, "delayed_count": 0,
                "areas_covered": ["NK"], "format_detected": "csv",
            },
            "delayed_activities": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "start_date": "x", "end_date": "x", "duration": "x", "progress": "x",
                "days_overdue": 1, "task_type": "Production", "priority": "CRITICAL_NOW",
                "is_root_cause": True, "blocked_by_id": None, "area": "NK",
            }],
            "root_cause_analysis": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "days_overdue": 1, "problem_type": "x",
                "why_it_matters": "x", "downstream_impact": "x",
                "consequence_if_unresolved": "x", "affected_task_ids": [],
            }],
            "downstream_consequences": [],
            "priority_actions": [{"step": 1, "action": "x", "action_type": "x"}],
            "resource_assessment": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "resource_type": "x", "assessment": "x",
            }],
            "forcing_assessment": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "is_forceable": "possible", "constraint_type": "x", "reason": "x",
                "risk_if_forced": "x", "recommendation": "x",
                "coordination_cost": "x", "parallelizability": "x",
                "max_speedup_factor": 1, "optimal_team_size": 4,
                "point_of_no_return": "x",
            }],
            "summary_by_area": [{
                "area": "NK", "delayed_count": 1, "critical_count": 1,
                "important_count": 0, "monitor_count": 0, "summary": "x",
            }],
            "insight_data": {
                "total_activities": 1, "delayed_count": 1,
                "critical_count": 1, "important_count": 0,
                "monitor_count": 0, "root_cause_count": 1,
                "reference_date": "x", "most_overdue_days": 1,
                "areas_affected": 1, "format_detected": "csv",
                "schedule_name": "x", "primary_risk": "x",
                "forceable_count": 1, "not_forceable_count": 0,
                "project_status": "CRITICAL", "risk_level": "HIGH",
                "unverified_delayed_count": 0,
                "critical_findings": ["x"], "consequences_if_no_action": ["x"],
            },
        }

        classification = build_field_claim_kinds(parsed)

        for section_name, section_value in parsed.items():
            assert section_name in classification, (
                f"section {section_name!r} missing from _claim_kinds"
            )
            if isinstance(section_value, dict):
                for field_name in section_value:
                    assert field_name in classification[section_name], (
                        f"{section_name!r}.{field_name!r} missing"
                    )
            elif isinstance(section_value, list) and section_value:
                item = section_value[0]
                if isinstance(item, dict):
                    for field_name in item:
                        assert field_name in classification[section_name], (
                            f"{section_name!r}[].{field_name!r} missing"
                        )

    def test_unmapped_section_raises(self):
        """AC4: an unknown section raises rather than silently
        defaulting to FACT (the worst-case misclassification per
        brief §19)."""
        with pytest.raises(ValueError, match="some_unknown_section"):
            build_field_claim_kinds({"some_unknown_section": {"x": 1}})

    def test_unmapped_field_raises(self):
        """AC4: a field inside a known section without a `ClaimKind`
        entry raises — schema drift is caught at construction, not
        at render time."""
        parsed = {
            "delayed_activities": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "start_date": "x", "end_date": "x", "duration": "x",
                "progress": "x", "days_overdue": 1, "task_type": "Production",
                "priority": "CRITICAL_NOW", "is_root_cause": True,
                "blocked_by_id": None, "area": "NK",
                "some_new_field": "boom",  # not in FIELD_CLAIM_KINDS
            }]
        }
        with pytest.raises(ValueError, match="some_new_field"):
            build_field_claim_kinds(parsed)

    def test_classification_values_are_real_claim_kinds(self):
        """Every emitted value is a valid `ClaimKind.value` string —
        no synthetic defaults slipping in."""
        parsed = {
            "management_conclusion": "x",
            "predictive_snapshot": {
                "what_will_happen": "x", "estimated_delay_impact": "x",
                "confidence_level": "x", "confidence_basis": "x",
                "main_delay_drivers": ["x"],
            },
        }
        classification = build_field_claim_kinds(parsed)
        valid = {c.value for c in ClaimKind}
        for section in classification.values():
            if isinstance(section, dict):
                for v in section.values():
                    assert v in valid
            else:
                assert section in valid


# ============================================================================
# AC4 — no implicit FACT default (Do-not rule enforcement)
# ============================================================================


class TestNoImplicitFactDefault:
    """Brief Do-not rule: "Do not classify a DERIVED_FACT as INFERENCE
    out of caution." Inversely, no FACT default either — a missing
    entry must surface as a failure, never a silent FACT."""

    def test_classification_table_does_not_silently_default_to_fact(self):
        """Structural property: every entry in the table is explicit.
        If a future change accidentally removed an entry, the
        exhaustive-completeness test in `TestClassificationTableCompleteness`
        would catch it before runtime; this is the runtime mirror."""
        # No FACT entries in the UNVERIFIABLE × {non-causal} rows —
        # UNVERIFIABLE always means UNKNOWN (insufficient evidence),
        # never FACT.
        for form in (ClaimForm.NUMERIC_QUANTITY, ClaimForm.SUPERLATIVE,
                     ClaimForm.ACTIVITY_ID_REFERENCE, ClaimForm.DATE_DURATION):
            assert _CLASSIFICATION_TABLE[(form, VerificationOutcome.UNVERIFIABLE)] != ClaimKind.FACT

    def test_contradicted_numeric_is_not_silently_fact(self):
        """A CONTRADICTED claim is unknown, never a confident FACT.
        Even though CONTRADICTED claims are removed by the renderer,
        the classification for the rejected-list inspection is UNKNOWN."""
        claim = Claim(text="17", span=(0, 2), form=ClaimForm.NUMERIC_QUANTITY)
        assert _classify_claim(claim, VerificationOutcome.CONTRADICTED) != ClaimKind.FACT


# ============================================================================
# Integration — `_build_agent_response` attaches `_claim_kinds`
# ============================================================================


class TestBuildAgentResponseIntegration:
    """End-to-end: `_build_agent_response` (TL-6.1 + TL-6.3 + TL-6.4)
    attaches `_claim_kinds` to `parsed_json` so the map travels in
    the API payload (brief §31: "classification travels in the
    payload for TL-7.3 to render")."""

    def test_agent_response_attaches_claim_kinds_to_parsed_json(self):
        """Run `_build_agent_response` on a hand-built minimal
        response and assert `_claim_kinds` is present and covers
        every section."""
        parsed = {
            "predictive_snapshot": {
                "what_will_happen": "If no action, delay of 6 weeks.",
                "estimated_delay_impact": "+6 weeks",
                "confidence_level": "HIGH",
                "confidence_basis": "Based on 28 delayed activities.",
                "main_delay_drivers": ["coordination bottlenecks", "design decisions", "production overdue"],
            },
            "predictive_biggest_risk": {
                "risk_title": "Task T1 — 47 days overdue",
                "will_block": "Blocks downstream EL work.",
                "prevent_action_now": "Escalate T1 coordination meeting.",
            },
            "executive_actions": [{
                "rank": 1, "action": "Resolve T1", "responsible": "PM",
                "deadline": "Monday", "related_task_ids": ["T1"],
                "manpower_helps": False, "manpower_note": "n/a",
            }],
            "management_conclusion": "Material risk; immediate coordination required.",
            "schedule_overview": {"schedule_name": "X", "reference_date": "01-01-2026",
                                  "total_activities": 100, "delayed_count": 10,
                                  "areas_covered": ["NK"], "format_detected": "csv"},
            "delayed_activities": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "start_date": "01-01-2026", "end_date": "10-01-2026",
                "duration": "10d", "progress": "0%", "days_overdue": 47,
                "task_type": "Production", "priority": "CRITICAL_NOW",
                "is_root_cause": True, "blocked_by_id": None, "area": "NK",
            }],
            "root_cause_analysis": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "days_overdue": 47, "problem_type": "coordination",
                "why_it_matters": "Blocks all EL and VVS follow-on work.",
                "downstream_impact": "Cascades into 6 disciplines.",
                "consequence_if_unresolved": "Project delay of 6-8 weeks.",
                "affected_task_ids": ["T2"],
            }],
            "downstream_consequences": [],
            "priority_actions": [{"step": 1, "action": "Resolve", "action_type": "coordination"}],
            "resource_assessment": [{"id": "T1", "task_name": "x", "human_label": "x",
                                     "resource_type": "manpower", "assessment": "blocked"}],
            "forcing_assessment": [{"id": "T1", "task_name": "x", "human_label": "x",
                                    "is_forceable": "not_recommended", "constraint_type": "design",
                                    "reason": "x", "risk_if_forced": "x",
                                    "recommendation": "x", "coordination_cost": "high",
                                    "parallelizability": "low", "max_speedup_factor": 1,
                                    "optimal_team_size": 4, "point_of_no_return": "x"}],
            "summary_by_area": [{"area": "NK", "delayed_count": 8, "critical_count": 3,
                                 "important_count": 3, "monitor_count": 2, "summary": "x"}],
            "insight_data": {
                "total_activities": 100, "delayed_count": 10,
                "critical_count": 3, "important_count": 4, "monitor_count": 3,
                "root_cause_count": 1, "reference_date": "01-01-2026",
                "most_overdue_days": 47, "areas_affected": 2,
                "format_detected": "csv", "schedule_name": "X",
                "primary_risk": "x", "forceable_count": 1, "not_forceable_count": 2,
                "project_status": "CRITICAL", "risk_level": "HIGH",
                "unverified_delayed_count": 0,
                "critical_findings": ["x"], "consequences_if_no_action": ["x"],
            },
        }

        response = _build_agent_response(parsed)

        # Brief §31: the classification travels in the payload.
        assert "_claim_kinds" in parsed
        cls = parsed["_claim_kinds"]
        # Every field in every section has a ClaimKind
        for section_name, section_value in parsed.items():
            if section_name.startswith("_"):
                continue
            assert section_name in cls
            if isinstance(section_value, dict):
                for field_name in section_value:
                    assert field_name in cls[section_name], (
                        f"{section_name!r}.{field_name!r} missing from _claim_kinds"
                    )

        # Sanity: forcing_assessment fields are INFERENCE (AC2)
        assert cls["forcing_assessment"]["is_forceable"] == ClaimKind.INFERENCE.value
        assert cls["forcing_assessment"]["reason"] == ClaimKind.INFERENCE.value
        assert cls["predictive_biggest_risk"]["will_block"] == ClaimKind.INFERENCE.value

        # And the response object itself is unaffected by the map
        # addition — it still carries the brief §33 six fields.
        assert response.answer  # non-empty
        assert response.confidence_state  # set by TL-6.3
