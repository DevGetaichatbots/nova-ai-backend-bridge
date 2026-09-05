"""Tests for TL-6.3 — Claim verification against the fact store.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-6-agent-contract.md` (TL-6.3):

- AC1: Numeric claims verified by recount, with a contradiction fixture
  proving detection.
- AC2: Every referenced activity ID verified to exist.
- AC3: Superlative claims recomputed, not accepted.
- AC4: Causal claims never reach VERIFIED.
- AC5: `CONTRADICTED` claims are removed from output.

Do-not: never "fix" a contradicted number by rewriting it into the
sentence — pinned by `TestDoNotRewriteContradictedNumbers`.
"""
from __future__ import annotations

import pytest

from src.trust.claims import (
    ClaimForm,
    VerificationOutcome,
    VerifiedClaim,
    extract_claims,
    verify_claim,
    verify_claims,
    verify_narrative,
)
from src.trust.engine import verify_id_reference

BRIEF_16_EXAMPLE = (
    "Electrical works in Building NK are the project's largest concentration "
    "of delay, with 17 activities behind schedule and three critical activities."
)


def _facts(
    delayed_count=17,
    critical_count=3,
    root_cause_count=2,
    areas_affected=2,
    most_overdue_days=47,
    activities=None,
    areas=None,
    reference_date="01-01-2026",
):
    return {
        "insight_data": {
            "delayed_count": delayed_count,
            "critical_count": critical_count,
            "root_cause_count": root_cause_count,
            "areas_affected": areas_affected,
            "most_overdue_days": most_overdue_days,
        },
        "delayed_activities": activities if activities is not None else [
            {"id": "A1", "days_overdue": 47, "start_date": "01-01-2026", "end_date": "10-01-2026"},
            {"id": "A2", "days_overdue": 12, "start_date": "02-01-2026", "end_date": "11-01-2026"},
        ],
        "summary_by_area": areas if areas is not None else [
            {"area": "NK", "delayed_count": 12},
            {"area": "AAA", "delayed_count": 5},
        ],
        "schedule_overview": {"reference_date": reference_date},
    }


# ============================================================================
# AC1 — numeric claims verified by recount, with a contradiction fixture
# ============================================================================


class TestNumericQuantityVerification:
    def test_matching_count_is_verified(self):
        claim = extract_claims("17 activities are delayed.").claims[0]
        result = verify_claim(claim, _facts(delayed_count=17))
        assert result.outcome == VerificationOutcome.VERIFIED

    def test_mismatched_count_is_contradicted(self):
        """The contradiction fixture: the narrative claims a number the
        fact store's recount disagrees with."""
        claim = extract_claims("25 activities are delayed.").claims[0]
        result = verify_claim(claim, _facts(delayed_count=17))
        assert result.outcome == VerificationOutcome.CONTRADICTED
        assert "25" in result.reason and "17" in result.reason

    def test_critical_count_recount(self):
        claim = extract_claims("Three critical activities remain.").claims[0]
        result = verify_claim(claim, _facts(critical_count=3))
        assert result.outcome == VerificationOutcome.VERIFIED

    def test_critical_count_contradiction(self):
        claim = extract_claims("Ten critical activities remain.").claims[0]
        result = verify_claim(claim, _facts(critical_count=3))
        assert result.outcome == VerificationOutcome.CONTRADICTED

    def test_quantity_with_no_field_hint_is_unverifiable(self):
        """A number whose noun phrase gives no reliable hint at which
        fact-store field it means must not be guessed against the wrong
        denominator."""
        claim = extract_claims("17 widgets were counted.").claims[0]
        assert claim.asserted_fields == ()
        result = verify_claim(claim, _facts())
        assert result.outcome == VerificationOutcome.UNVERIFIABLE

    def test_ambiguous_per_activity_hint_is_unverifiable_not_guessed(self):
        """`days_overdue` is per-activity, not a single aggregate — a bare
        numeric claim hinting at it must not be checked against an
        arbitrary aggregate (this is why DATE_DURATION owns real overdue
        numbers instead, tested separately)."""
        claim = extract_claims("47 overdue items were found.").claims[0]
        result = verify_claim(claim, _facts())
        assert result.outcome == VerificationOutcome.UNVERIFIABLE

    def test_missing_field_in_fact_store_is_unverifiable(self):
        claim = extract_claims("17 activities are delayed.").claims[0]
        facts = _facts()
        del facts["insight_data"]["delayed_count"]
        result = verify_claim(claim, facts)
        assert result.outcome == VerificationOutcome.UNVERIFIABLE


# ============================================================================
# AC2 — every referenced activity ID verified to exist
# ============================================================================


class TestActivityIdVerification:
    def test_existing_id_is_verified(self):
        claim = extract_claims("Task ID A1 is severely overdue.").claims[0]
        result = verify_claim(claim, _facts())
        assert result.outcome == VerificationOutcome.VERIFIED

    def test_nonexistent_id_is_contradicted(self):
        """The id-reference contradiction fixture — reuses TL-2.3's
        'never invent an id' guarantee: an id absent from the known set
        is treated as a false claim, not merely an unchecked one."""
        claim = extract_claims("Task ID A999 is severely overdue.").claims[0]
        result = verify_claim(claim, _facts())
        assert result.outcome == VerificationOutcome.CONTRADICTED
        assert "A999" in result.reason

    def test_no_known_ids_is_unverifiable_not_contradicted(self):
        """An empty fact store cannot positively disprove an id — that is
        'we don't know,' not 'we know it's false.'"""
        claim = extract_claims("Task ID A1 is overdue.").claims[0]
        result = verify_claim(claim, _facts(activities=[]))
        assert result.outcome == VerificationOutcome.UNVERIFIABLE

    def test_verify_id_reference_is_exact_membership_only(self):
        """`engine.verify_id_reference` does no fuzzy matching — an id one
        character off from a real one is not 'close enough.'"""
        assert verify_id_reference("A1", ["A1", "A2"]) is True
        assert verify_id_reference("A1x", ["A1", "A2"]) is False
        assert verify_id_reference("a1", ["A1", "A2"]) is False  # case-sensitive: ids are exact tokens, not free text


# ============================================================================
# AC3 — superlative claims recomputed, not accepted
# ============================================================================


class TestSuperlativeVerification:
    def test_unique_top_entry_is_verified(self):
        claim = extract_claims("This is the largest concentration of delay in NK.").claims[0]
        result = verify_claim(claim, _facts(areas=[{"area": "NK", "delayed_count": 12}, {"area": "AAA", "delayed_count": 5}]))
        assert result.outcome == VerificationOutcome.VERIFIED

    def test_tied_top_entries_contradict_the_superlative(self):
        """The recompute-based contradiction fixture: a tie at the top
        means no single 'largest' exists, regardless of which location
        the narrative names."""
        claim = extract_claims("NK has the largest concentration of delay.").claims[0]
        result = verify_claim(
            claim,
            _facts(areas=[{"area": "NK", "delayed_count": 5}, {"area": "AAA", "delayed_count": 5}]),
        )
        assert result.outcome == VerificationOutcome.CONTRADICTED
        assert "tied" in result.reason.lower()

    def test_no_area_breakdown_is_unverifiable(self):
        claim = extract_claims("This is the largest concentration of delay.").claims[0]
        result = verify_claim(claim, _facts(areas=[]))
        assert result.outcome == VerificationOutcome.UNVERIFIABLE

    def test_single_area_is_unverifiable_not_verified(self):
        """With only one area, there is nothing to rank against — a
        superlative claim cannot be confirmed OR contradicted."""
        claim = extract_claims("This is the largest concentration of delay.").claims[0]
        result = verify_claim(claim, _facts(areas=[{"area": "NK", "delayed_count": 5}]))
        assert result.outcome == VerificationOutcome.UNVERIFIABLE


# ============================================================================
# AC4 — causal claims never reach VERIFIED
# ============================================================================


class TestCausalNeverVerified:
    def test_causal_claim_is_unverifiable_regardless_of_facts(self):
        claim = extract_claims("Electrical work caused the delay in Building NK.").claims[0]
        assert claim.form == ClaimForm.CAUSAL
        result = verify_claim(claim, _facts())
        assert result.outcome == VerificationOutcome.UNVERIFIABLE

    def test_causal_claim_is_unverifiable_even_with_rich_facts(self):
        """Brief §18's A142 point: causation is never established by
        schedule data, no matter how complete that data is."""
        rich_facts = _facts(activities=[{"id": f"A{i}", "days_overdue": i} for i in range(50)])
        claim = extract_claims("The coordination bottleneck caused this delay.").claims[0]
        result = verify_claim(claim, rich_facts)
        assert result.outcome == VerificationOutcome.UNVERIFIABLE

    def test_no_causal_claim_form_ever_maps_to_verified(self):
        """Exhaustive check across every causal trigger phrase this
        module recognises."""
        sentences = [
            "The delay was caused by a coordination issue.",
            "Electrical work caused the delay.",
            "The schedule slipped due to a design change.",
            "Forsinkelsen skyldes en koordineringskonflikt.",
        ]
        for text in sentences:
            for claim in extract_claims(text).claims:
                if claim.form == ClaimForm.CAUSAL:
                    result = verify_claim(claim, _facts())
                    assert result.outcome != VerificationOutcome.VERIFIED, text


# ============================================================================
# AC5 — CONTRADICTED claims are removed from output, never merely flagged
# ============================================================================


class TestContradictedClaimsAreRemoved:
    def test_contradicted_numeric_claim_is_removed_from_cleaned_text(self):
        result = verify_narrative("There are 25 delayed activities in the schedule.", _facts(delayed_count=17))
        assert "25" not in result.cleaned_text
        assert len(result.contradicted) == 1

    def test_contradicted_id_claim_is_removed_from_cleaned_text(self):
        result = verify_narrative("Task ID A999 is severely overdue.", _facts())
        assert "A999" not in result.cleaned_text

    def test_verified_claims_survive_in_cleaned_text(self):
        result = verify_narrative(BRIEF_16_EXAMPLE, _facts())
        assert result.contradicted == []
        assert "17 activities" in result.cleaned_text
        assert "three critical activities" in result.cleaned_text

    def test_mixed_verified_and_contradicted_only_removes_the_contradicted_one(self):
        text = "17 activities are delayed, and 999 are critical."
        result = verify_narrative(text, _facts(delayed_count=17, critical_count=3))
        assert "17 activities" in result.cleaned_text
        assert "999" not in result.cleaned_text


# ============================================================================
# Do-not — never rewrite a contradicted number into the sentence
# ============================================================================


class TestDoNotRewriteContradictedNumbers:
    def test_contradicted_number_is_deleted_not_replaced(self):
        """The old `predictive_agent.py` correction block used to
        regex-renumber narrative prose in place. This task's Do-not rule
        forbids that pattern here: the wrong number must be gone, and the
        correct number must NOT silently appear in its place (which would
        make the sentence assert something the model never actually
        wrote and never had grounds to write)."""
        result = verify_narrative("There are 25 delayed activities.", _facts(delayed_count=17))
        assert "25" not in result.cleaned_text
        assert "17" not in result.cleaned_text  # not rewritten in — genuinely removed

    def test_cleaned_text_has_no_leftover_double_punctuation(self):
        """Span removal must not leave a visibly broken sentence (a
        dangling ', .' or doubled space) — the Do-not rule is about
        not rewriting facts, not about tolerating garbled prose."""
        result = verify_narrative("17 activities are delayed, and 999 are critical.", _facts(delayed_count=17, critical_count=3))
        assert ",." not in result.cleaned_text
        assert "  " not in result.cleaned_text


# ============================================================================
# AC4 (from TL-6.2, exercised again here) — undecomposable text stays
# unverified through the whole verification pipeline, not just extraction
# ============================================================================


class TestUndecomposableTextThroughVerification:
    def test_non_string_text_is_not_decomposable_and_fully_unverified(self):
        result = verify_narrative(None, _facts())
        assert result.decomposable is False
        assert result.unverified_claim_texts == []

    def test_undecomposable_extraction_marks_whole_text_unverified(self, monkeypatch):
        import src.trust.claims as claims_module

        def _boom(_text):
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(claims_module, "_extract_all_claims", _boom)
        result = verify_narrative("17 activities are delayed.", _facts())
        assert result.decomposable is False
        assert result.unverified_claim_texts == ["17 activities are delayed."]
        # The text is not silently rendered as verified/clean.
        assert result.verified == []
        assert result.contradicted == []


# ============================================================================
# verify_claims — batch convenience
# ============================================================================


class TestVerifyClaimsBatch:
    def test_batch_verification_preserves_order(self):
        extraction = extract_claims(BRIEF_16_EXAMPLE)
        results = verify_claims(extraction.claims, _facts())
        assert len(results) == len(extraction.claims)
        assert all(isinstance(r, VerifiedClaim) for r in results)
        assert [r.claim.span for r in results] == [c.span for c in extraction.claims]


# ============================================================================
# Integration — `predictive_agent._build_agent_response` actually uses this
# verification, not just the standalone `claims.py` functions
# ============================================================================


class TestPredictiveAgentWiring:
    """`TL-6.3` wired `verify_narrative` into `predictive_agent._build_agent_response`
    ahead of its own declared `Files:` list (same posture as `TL-6.1`'s
    agent wiring, ADR-024) — this proves the wiring itself, not just the
    library functions it calls."""

    def _run(self, management_conclusion: str, insight_data_overrides: dict | None = None):
        from src.predictive_agent import _build_agent_response

        parsed_json = {
            "management_conclusion": management_conclusion,
            "predictive_snapshot": {},
            "predictive_biggest_risk": {},
            "insight_data": {
                "delayed_count": 17,
                "critical_count": 3,
                "root_cause_count": 2,
                "areas_affected": 2,
                "most_overdue_days": 47,
                **(insight_data_overrides or {}),
            },
            "delayed_activities": [
                {"id": "A1", "days_overdue": 47, "start_date": "01-01-2026", "end_date": "10-01-2026"},
            ],
            "summary_by_area": [
                {"area": "NK", "delayed_count": 12},
                {"area": "AAA", "delayed_count": 5},
            ],
            "schedule_overview": {"reference_date": "01-01-2026"},
        }
        return _build_agent_response(parsed_json)

    def test_matching_narrative_is_verified(self):
        from src.trust.vocabulary import TrustState

        response = self._run("17 activities are delayed across the project.")
        assert response.confidence_state == TrustState.VERIFIED
        assert response.unverified_claims == []
        assert "17 activities" in response.answer

    def test_contradicted_number_is_stripped_from_answer(self):
        from src.trust.vocabulary import TrustState

        response = self._run("There are 99 activities delayed across the project.")
        assert "99" not in response.answer
        assert response.confidence_state == TrustState.REVIEW

    def test_causal_claim_lands_in_unverified_claims(self):
        response = self._run("The delay was caused by a coordination failure in NK.")
        assert any("caused by" in c.lower() for c in response.unverified_claims)

    def test_plain_narrative_with_no_claims_stays_review(self):
        """No factual claims to check means nothing to point to as
        verified — this must not default to VERIFIED."""
        from src.trust.vocabulary import TrustState

        response = self._run("The team is reviewing the situation.")
        assert response.confidence_state == TrustState.REVIEW
