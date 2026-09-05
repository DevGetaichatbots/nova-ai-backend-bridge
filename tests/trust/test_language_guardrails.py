"""Tests for TL-6.6 — Language guardrails (brief §20, §46).

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-6-agent-contract.md` (TL-6.6):

- AC1: Overclaiming patterns detected in both EN and DA. The detection
  regex list covers causal verbs ("caused by", "due to"), unhedged
  future assertions ("will be delayed"), and absolute certainty
  adverbs ("definitely", "always").
- AC2: Both brief §20 wrong/right pairs handled as documented —
  "will be delayed" → "shows a pattern of delay", "caused by" →
  "associated with" (English); Danish equivalents.
- AC3: An inference phrased with fact-grade certainty is caught.
  The `hedge_overclaiming` rewrite applies to INFERENCE and UNKNOWN
  claims, not FACT or DERIVED_FACT.
- AC4: Verified facts are not over-hedged by the check — FACT and
  DERIVED_FACT claims pass through unchanged (Do-not rule: "do not
  hedge `DERIVED_FACT` statements — precision cuts both ways").

Brief §46: Kemp is Danish-only; both languages must be covered.
Brief §34: enforcement is structural (deterministic Python), the
prompt update is the last layer.
"""
from __future__ import annotations

import pytest

from src.trust.claims import (
    ClaimKind,
    check_overclaiming,
    hedge_overclaiming,
    hedge_narrative_overclaiming,
    verify_narrative,
)


# ============================================================================
# AC1 — Overclaiming patterns detected in both EN and DA
# ============================================================================


class TestOverclaimingDetectionEN:
    """AC1 (English): causal verbs, unhedged future assertions, and
    absolute certainty adverbs are detected on INFERENCE / UNKNOWN
    text. Detection returns a non-empty issue list; hedging returns
    the rewritten text plus a non-empty fix list."""

    @pytest.mark.parametrize("overclaim,hedged_substring", [
        ("caused by", "associated with"),
        ("caused the", "is associated with the"),
        ("due to", "consistent with"),
        ("because of", "consistent with"),
        ("will be delayed", "shows a pattern of delay"),
        ("will fail", "is at risk of failing"),
        ("definitely", "likely"),
        ("certainly", "likely"),
    ])
    def test_en_pattern_detected_and_hedged(self, overclaim, hedged_substring):
        """Each overclaim pattern is rewritten to its hedged equivalent
        on INFERENCE text. Detection is the gate; the rewrite is the
        action — both must work for the same set of patterns."""
        text = f"The project {overclaim} in NK."
        issues = check_overclaiming(text, ClaimKind.INFERENCE, "en")
        assert len(issues) > 0, f"failed to detect {overclaim!r}"

        hedged, fixes = hedge_overclaiming(text, ClaimKind.INFERENCE, "en")
        assert overclaim not in hedged.lower(), (
            f"overclaim {overclaim!r} survived: {hedged!r}"
        )
        assert hedged_substring in hedged.lower(), (
            f"expected hedged form {hedged_substring!r} in {hedged!r}"
        )
        assert len(fixes) > 0


class TestOverclaimingDetectionDA:
    """AC1 (Danish): the same pattern categories are detected and
    rewritten. Brief §46: Kemp is Danish-only, so Danish coverage is
    not optional."""

    @pytest.mark.parametrize("overclaim,hedged_substring", [
        ("forårsaget af", "forbundet med"),
        ("forårsagede", "var forbundet med"),
        ("på grund af", "konsistent med"),
        ("skyldes", "kan tilskrives"),
        ("vil blive forsinket", "viser et mønster af forsinkelse"),
        ("helt sikkert", "sandsynligvis"),
        ("bestemt", "sandsynligvis"),
    ])
    def test_da_pattern_detected_and_hedged(self, overclaim, hedged_substring):
        text = f"Projektet {overclaim} i NK."
        issues = check_overclaiming(text, ClaimKind.INFERENCE, "da")
        assert len(issues) > 0, f"failed to detect {overclaim!r}"

        hedged, fixes = hedge_overclaiming(text, ClaimKind.INFERENCE, "da")
        assert overclaim not in hedged.lower(), (
            f"overclaim {overclaim!r} survived: {hedged!r}"
        )
        assert hedged_substring in hedged.lower(), (
            f"expected hedged form {hedged_substring!r} in {hedged!r}"
        )


# ============================================================================
# AC2 — Brief §20 wrong/right pairs
# ============================================================================


class TestBriefSection20Pairs:
    """AC2: brief §20's two worked pairs are handled correctly:

    WRONG  "The project will be delayed"
    RIGHT  "The current schedule pattern indicates increased delay risk"

    WRONG  "Electrical work caused the delay"
    RIGHT  "The largest concentration of current delay is within electrical activities"

    The deterministic check does not produce the full RIGHT phrasing
    (that requires the prompt layer to teach the model the structural
    rewrite — see `PREDICTIVE_NARRATIVE_SYSTEM_PROMPT`'s HEDGING
    section); it does remove the overclaiming phrase, which is the
    minimum the gate enforces. The test pins the overclaim-removal
    half and trusts the prompt layer for the structural rewrite.
    """

    def test_will_be_delayed_is_hedged_en(self):
        """WRONG: "The project will be delayed" → no longer asserts."""
        text = "The project will be delayed."
        hedged, fixes = hedge_overclaiming(text, ClaimKind.INFERENCE, "en")
        assert "will be delayed" not in hedged.lower()
        assert len(fixes) > 0

    def test_caused_by_is_hedged_en(self):
        """WRONG: "Electrical work caused the delay" → no longer asserts."""
        text = "Electrical work caused the delay."
        hedged, fixes = hedge_overclaiming(text, ClaimKind.INFERENCE, "en")
        assert "caused" not in hedged.lower() or "associated" in hedged.lower()
        assert len(fixes) > 0

    def test_will_be_delayed_is_hedged_da(self):
        text = "Projektet vil blive forsinket."
        hedged, fixes = hedge_overclaiming(text, ClaimKind.INFERENCE, "da")
        assert "vil blive forsinket" not in hedged.lower()
        assert len(fixes) > 0

    def test_caused_by_is_hedged_da(self):
        text = "Forsinkelsen var forårsaget af dårlig koordinering."
        hedged, fixes = hedge_overclaiming(text, ClaimKind.INFERENCE, "da")
        assert "forårsaget" not in hedged.lower() or "forbundet" in hedged.lower()
        assert len(fixes) > 0


# ============================================================================
# AC3 — Inference phrased with fact-grade certainty is caught
# ============================================================================


class TestInferenceFactGradePhrasing:
    """AC3: an INFERENCE-shaped claim that uses fact-grade phrasing is
    caught by the hedger — the overclaiming word is removed, the
    surrounding prose is preserved. Multiple overclaims in one text
    are all caught."""

    def test_inference_with_multiple_overclaims(self):
        """Two overclaims in one sentence: both get rewritten, both
        appear in the fix audit trail."""
        text = "This will definitely fail because of bad coordination."
        hedged, fixes = hedge_overclaiming(text, ClaimKind.INFERENCE, "en")
        assert "will definitely" not in hedged.lower()
        assert "because of" not in hedged.lower()
        assert len(fixes) >= 2, (
            f"expected at least 2 fixes (will definitely + because of), got {fixes!r}"
        )

    def test_unknown_forecast_prose_is_also_hedged(self):
        """An UNVERIFIABLE forecast (kind=UNKNOWN per TL-6.4) still
        has INFERENCE-shaped prose ("will be delayed") and must be
        hedged. This pins the fact that hedge applies to both
        INFERENCE and UNKNOWN — UNKNOWN covers the case where the
        fact store has nothing to verify the prose against, but the
        prose is still a forward-looking assertion.
        """
        text = "The project will be delayed by 4-8 weeks."
        # UNKNOWN — same hedging behavior as INFERENCE
        hedged, fixes = hedge_overclaiming(text, ClaimKind.UNKNOWN, "en")
        assert "will be delayed" not in hedged.lower()
        assert len(fixes) > 0

    def test_hedging_preserves_surrounding_prose(self):
        """The hedge is conservative — phrase substitutions only,
        not full rewrites. The surrounding prose is preserved."""
        text = "Electrical work caused the delay in production."
        hedged, fixes = hedge_overclaiming(text, ClaimKind.INFERENCE, "en")
        # "in production" should still be there
        assert "in production" in hedged, (
            f"surrounding prose lost: {hedged!r}"
        )


# ============================================================================
# AC4 — Verified facts are NOT over-hedged
# ============================================================================


class TestVerifiedFactsNotHedged:
    """AC4 (the Do-not rule): FACT and DERIVED_FACT claims pass through
    unchanged. Brief §20's "precision cuts both ways" — hedging
    verified numbers erodes trust in the labels themselves.
    """

    def test_fact_claim_is_unchanged_en(self):
        """A FACT claim with overclaiming-shaped prose is left
        untouched. Brief §20: the same phrasing is fine on a verified
        FACT (causality is established)."""
        text = "Task ID 41 is delayed by 47 days, caused by design."
        hedged, fixes = hedge_overclaiming(text, ClaimKind.FACT, "en")
        assert hedged == text
        assert fixes == []

    def test_derived_fact_claim_is_unchanged(self):
        """DERIVED_FACT (the brief §19 example "31 of 73 delayed are in
        NK") must NOT be hedged — the number is deterministically
        recalculated, hedging erodes trust in the recalculation."""
        text = "31 of 73 delayed activities are in NK."
        hedged, fixes = hedge_overclaiming(text, ClaimKind.DERIVED_FACT, "en")
        assert hedged == text
        assert fixes == []

    def test_fact_with_causal_prose_is_not_hedged(self):
        """Even when a FACT claim's prose contains causal verbs (which
        would normally be a hedge trigger on INFERENCE), the FACT is
        left alone — the data has verified it."""
        text = "The 47-day delay was caused by the upstream block."
        # Same text as INFERENCE — should hedge
        hedged_inference, _ = hedge_overclaiming(text, ClaimKind.INFERENCE, "en")
        # But as FACT — should pass through
        hedged_fact, fixes = hedge_overclaiming(text, ClaimKind.FACT, "en")
        assert hedged_inference != text  # INFERENCE version is hedged
        assert hedged_fact == text  # FACT version is unchanged
        assert fixes == []


# ============================================================================
# AC3 (integration) — verify_narrative applies hedging to cleaned_text
# ============================================================================


class TestVerifyNarrativeIntegration:
    """AC3 (integration): `verify_narrative` (TL-6.3) applies the
    TL-6.6 hedge as part of its top-level flow. The final
    `cleaned_text` carries the rewrites; `overclaiming_fixes`
    carries the audit trail."""

    def _facts(self):
        return {
            "insight_data": {
                "delayed_count": 5, "critical_count": 2, "monitor_count": 1,
                "most_overdue_days": 47,
            },
            "delayed_activities": [{
                "id": "T1", "days_overdue": 47,
                "start_date": "01-01-2020", "end_date": "10-01-2020",
            }],
            "summary_by_area": [{"area": "NK", "delayed_count": 5, "critical_count": 2}],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        }

    def test_verify_narrative_hedges_inference_prose(self):
        """A narrative with causal + future overclaims is hedged in
        `cleaned_text`; `overclaiming_fixes` records the substitutions."""
        narrative = (
            "The project will be delayed by 4-8 weeks. "
            "Electrical work caused the delay. "
            "31 of 73 delayed activities are in NK."
        )
        result = verify_narrative(narrative, self._facts(), language="en")
        assert "will be delayed" not in result.cleaned_text.lower()
        assert "caused" not in result.cleaned_text.lower() or (
            "associated" in result.cleaned_text.lower()
        )
        assert len(result.overclaiming_fixes) >= 2

    def test_verify_narrative_does_not_hedge_facts(self):
        """A narrative containing only verified-fact overclaims (which
        is unusual but possible) is left alone — the FACT exemption
        runs at the narrative level, not just per-claim."""
        narrative = "Task T1 is delayed by 47 days."  # verified by fact store
        result = verify_narrative(narrative, self._facts(), language="en")
        # The "is delayed by 47 days" is a FACT (verified) — no hedging
        # 47 is in the fact store, so it verifies.
        assert result.overclaiming_fixes == []

    def test_verify_narrative_handles_danish(self):
        """Danish narrative with Danish overclaims is hedged using
        Danish patterns. Brief §46: Kemp is Danish-only."""
        narrative = (
            "Projektet vil blive forsinket med 4-8 uger. "
            "Forsinkelsen var forårsaget af dårlig koordinering."
        )
        result = verify_narrative(narrative, self._facts(), language="da")
        assert "vil blive forsinket" not in result.cleaned_text.lower()
        assert "forårsaget" not in result.cleaned_text.lower() or (
            "forbundet" in result.cleaned_text.lower()
        )


# ============================================================================
# Detection-only (no rewrite) — for the brief's "rejected back or
# rewritten to hedged form" alternative
# ============================================================================


class TestCheckOverclaimingAPI:
    """The check-vs-hedge split — `check_overclaiming` is the detector,
    `hedge_overclaiming` is the rewriter. A caller may want to log
    overclaiming issues without rewriting (e.g. for the harness's
    audit trail) — both APIs are independently testable."""

    def test_check_returns_empty_for_facts(self):
        """`check_overclaiming` returns `[]` for FACT/DERIVED_FACT
        — verified facts have no overclaiming concerns."""
        assert check_overclaiming("caused by", ClaimKind.FACT, "en") == []
        assert check_overclaiming("caused by", ClaimKind.DERIVED_FACT, "en") == []

    def test_check_returns_issues_for_inference(self):
        issues = check_overclaiming("caused by X", ClaimKind.INFERENCE, "en")
        assert len(issues) > 0
        # Each issue names the pattern
        assert any("caused" in i for i in issues)

    def test_check_returns_empty_for_hedged_text(self):
        """Properly hedged INFERENCE text has no overclaiming issues."""
        text = "Electrical work is associated with the delay."
        issues = check_overclaiming(text, ClaimKind.INFERENCE, "en")
        assert issues == []

    def test_hedge_returns_empty_fixes_for_clean_text(self):
        text = "31 activities are delayed in NK."  # no overclaiming
        hedged, fixes = hedge_overclaiming(text, ClaimKind.UNKNOWN, "en")
        assert hedged == text
        assert fixes == []


# ============================================================================
# Sentence-expansion edge case
# ============================================================================


class TestSentenceExpansionEdgeCase:
    """AC3 (edge case): overclaiming often sits in prose *around* the
    extracted claim, not in the claim text itself. Example: a
    DATE_DURATION claim extracts "4-8 weeks" but "will be delayed"
    sits in the same sentence. The hedge expands the claim span to
    its enclosing sentence so the overclaiming is caught.
    """

    def test_overclaiming_around_narrow_date_duration_claim_is_hedged(self):
        """The DATE_DURATION claim "4-8 weeks" is narrow; "will be
        delayed" is the surrounding prose. `hedge_narrative_overclaiming`
        expands the span to the enclosing sentence and hedges the
        whole sentence."""
        narrative = "The project will be delayed by 4-8 weeks."
        # Build a synthetic VerifiedClaim (UNVERIFIABLE, UNKNOWN kind)
        from src.trust.claims import Claim, VerificationOutcome, VerifiedClaim
        from src.trust.claims import ClaimForm
        claim = Claim(
            text="4-8 weeks",
            span=(20, 29),  # "4-8 weeks" position
            form=ClaimForm.DATE_DURATION,
            extracted_values={"number": 4.0, "number_upper": 8.0, "unit": "weeks"},
            asserted_fields=("duration",),
        )
        verified = VerifiedClaim(
            claim=claim,
            outcome=VerificationOutcome.UNVERIFIABLE,
            reason="no fact store handle",
            kind=ClaimKind.UNKNOWN,
        )
        hedged, fixes = hedge_narrative_overclaiming(
            narrative, [verified], language="en",
        )
        assert "will be delayed" not in hedged.lower()
        assert len(fixes) > 0


# ============================================================================
# Regression — CONTRADICTED removal + TL-6.6 hedging interaction (ADR-031)
# ============================================================================
# `verify_narrative` removes CONTRADICTED claims from `text` *before*
# hedging surviving claims (TL-6.3's Do-not rule runs first). Every
# surviving claim's `span` was computed against the *original*, longer
# `text` — if a CONTRADICTED claim sat earlier in the narrative, using
# that stale span directly against the shortened text either misses the
# hedge entirely or (when two hedge-worthy claims land in the same
# sentence) corrupts the output by splicing the same range twice. None of
# the tests above exercise a narrative containing both a contradiction
# and a later hedge-worthy claim in the same call — this class does.


class TestContradictionThenHedgeInteraction:
    def _facts(self):
        return {
            "insight_data": {"delayed_count": 17, "critical_count": 3},
            "delayed_activities": [{"id": "A1", "days_overdue": 47}],
            "summary_by_area": [
                {"area": "NK", "delayed_count": 12},
                {"area": "AAA", "delayed_count": 5},
            ],
            "schedule_overview": {"reference_date": "01-01-2026"},
        }

    def test_hedge_still_applies_after_an_earlier_contradiction_is_removed(self):
        """A fabricated number earlier in the narrative must not prevent
        a later causal claim from being hedged — the two are independent
        claims, and removing one must not blind the pipeline to the
        other."""
        text = (
            "There are 99 delayed activities in the schedule. "
            "The delay was caused by design issues."
        )
        result = verify_narrative(text, self._facts())
        assert "99" not in result.cleaned_text
        assert "caused by" not in result.cleaned_text
        assert "associated with" in result.cleaned_text
        assert result.overclaiming_fixes

    def test_hedge_still_applies_when_the_removed_span_is_much_longer_than_the_gap(self):
        """The offset drift equals the removed span's length — this case
        makes that drift larger than the short sentence sitting between
        the contradiction and the claim to hedge, which is what actually
        exposed the bug (a small drift self-corrects by accident; a large
        one does not)."""
        text = (
            "There are 999999 delayed activities recorded across every "
            "single discipline and area of the whole project today. "
            "OK. "
            "The delay was caused by design issues."
        )
        result = verify_narrative(text, self._facts())
        assert "caused by" not in result.cleaned_text
        assert "associated with" in result.cleaned_text

    def test_no_duplicated_text_when_two_hedge_worthy_claims_share_a_sentence(self):
        """A CAUSAL claim's span covers its whole sentence and can
        legitimately contain a separately-CONTRADICTED sub-claim (here,
        a fabricated activity id). Splicing the same sentence once per
        claim (instead of once per sentence) corrupts the text with
        duplicated trailing content — this pins that it does not."""
        text = "A142 is delayed by 18 days, caused by a coordination issue."
        facts = {
            "insight_data": {},
            "delayed_activities": [{"id": "A1"}],  # "A142" is not in the fact store
            "summary_by_area": [],
        }
        result = verify_narrative(text, facts)
        assert "A142" not in result.cleaned_text
        assert "caused by" not in result.cleaned_text
        assert "associated with" in result.cleaned_text
        # The headline symptom of the double-splice bug: the sentence's
        # own trailing word duplicated.
        assert "issue.issue" not in result.cleaned_text
        assert result.cleaned_text.count("issue") == 1

    def test_trailing_sentence_after_the_hedged_claim_is_preserved_intact(self):
        """A sentence *after* the hedged claim must survive untouched —
        an earlier version of this fix could corrupt or drop it if the
        offset drift pushed the sentence-boundary search past it."""
        text = (
            "There are 99 delayed activities in the schedule. "
            "The delay was caused by design issues. "
            "Also five items remain in area NK for review."
        )
        result = verify_narrative(text, self._facts())
        assert "Also five items remain in area NK for review." in result.cleaned_text
