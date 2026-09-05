"""Tests for TL-6.2 — Claim extraction from generated narrative.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-6-agent-contract.md` (TL-6.2):

- AC1: All five claim kinds (forms) extracted, each with a test.
- AC2: The brief §16 example decomposes into its three claims.
- AC3: Claims record spans, enabling targeted removal or qualification.
- AC4: Text that cannot be decomposed is marked unverified (`decomposable=False`)
  rather than passed through as "no claims found."

Do-not: a model is never the arbiter of whether a claim is supported —
pinned indirectly by this whole module being regex/parsing only (no LLM
import anywhere in `src/trust/claims.py`, asserted directly below).
"""
from __future__ import annotations

import ast

import pytest

from src.trust.claims import (
    Claim,
    ClaimExtractionResult,
    ClaimForm,
    extract_claims,
)

BRIEF_16_EXAMPLE = (
    "Electrical works in Building NK are the project's largest concentration "
    "of delay, with 17 activities behind schedule and three critical activities."
)


# ============================================================================
# AC2 — the brief §16 example decomposes into its three claims
# ============================================================================


class TestBrief16Example:
    def test_decomposes_into_exactly_three_claims(self):
        result = extract_claims(BRIEF_16_EXAMPLE)
        assert result.decomposable is True
        assert len(result.claims) == 3

    def test_one_superlative_claim(self):
        result = extract_claims(BRIEF_16_EXAMPLE)
        superlatives = [c for c in result.claims if c.form == ClaimForm.SUPERLATIVE]
        assert len(superlatives) == 1
        assert "largest concentration" in superlatives[0].text

    def test_two_numeric_quantity_claims_17_and_3(self):
        result = extract_claims(BRIEF_16_EXAMPLE)
        numerics = [c for c in result.claims if c.form == ClaimForm.NUMERIC_QUANTITY]
        assert len(numerics) == 2
        numbers = sorted(c.extracted_values["number"] for c in numerics)
        assert numbers == [3, 17]

    def test_claims_are_disjoint_spans(self):
        """No two claims overlap — each character belongs to at most one
        claim's span."""
        result = extract_claims(BRIEF_16_EXAMPLE)
        spans = sorted(c.span for c in result.claims)
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            assert e1 <= s2, f"overlapping spans: ({s1},{e1}) and ({s2},{e2})"


# ============================================================================
# AC1 — all five claim forms extracted, each with its own test
# ============================================================================


class TestNumericQuantityClaims:
    def test_digit_quantity(self):
        result = extract_claims("There are 12 delayed activities in area NK.")
        numerics = [c for c in result.claims if c.form == ClaimForm.NUMERIC_QUANTITY]
        assert any(c.extracted_values["number"] == 12 for c in numerics)

    def test_word_quantity(self):
        result = extract_claims("Three critical activities remain unresolved.")
        numerics = [c for c in result.claims if c.form == ClaimForm.NUMERIC_QUANTITY]
        assert any(c.extracted_values["number"] == 3 for c in numerics)

    def test_danish_word_quantity(self):
        result = extract_claims("Der er 12 forsinkede aktiviteter i område NK.")
        numerics = [c for c in result.claims if c.form == ClaimForm.NUMERIC_QUANTITY]
        assert any(c.extracted_values["number"] == 12 for c in numerics)

    def test_field_hint_guessed_for_delayed_count(self):
        result = extract_claims("17 activities are delayed.")
        numerics = [c for c in result.claims if c.form == ClaimForm.NUMERIC_QUANTITY]
        assert numerics
        assert "delayed_count" in numerics[0].asserted_fields

    def test_field_hint_guessed_for_critical_count(self):
        result = extract_claims("Three critical activities remain.")
        numerics = [c for c in result.claims if c.form == ClaimForm.NUMERIC_QUANTITY]
        assert numerics
        assert "critical_count" in numerics[0].asserted_fields

    def test_long_unbroken_noun_phrase_still_extracts_a_claim(self):
        """Regression (ADR-031): a noun phrase needing more than 5 words
        to reach a connector word or punctuation used to make the whole
        match fail silently — the claim vanished with no signal at all,
        rather than being extracted with a merely-imprecise cutoff. A
        number followed by a long, unbroken run of plain words must
        still produce a claim."""
        text = "There are 999999 delayed activities recorded across every single discipline and area."
        result = extract_claims(text)
        numerics = [c for c in result.claims if c.form == ClaimForm.NUMERIC_QUANTITY]
        assert numerics, "claim vanished — the long-noun-phrase fallback regressed"
        assert numerics[0].extracted_values["number"] == 999999

    def test_brief_16_example_unaffected_by_the_long_phrase_fallback(self):
        """The fallback alternative must never win over the precise,
        lazy-bounded match when a real stopping boundary exists — pins
        that the fix in the previous test did not change this
        already-correct, already-tested behaviour."""
        text = "17 activities behind schedule and three critical activities."
        result = extract_claims(text)
        numerics = [c for c in result.claims if c.form == ClaimForm.NUMERIC_QUANTITY]
        assert [c.extracted_values["number"] for c in numerics] == [17, 3]
        assert numerics[0].extracted_values["noun_phrase"] == "activities"


class TestSuperlativeClaims:
    def test_largest_concentration(self):
        result = extract_claims("This is the largest concentration of delay in the project.")
        superlatives = [c for c in result.claims if c.form == ClaimForm.SUPERLATIVE]
        assert len(superlatives) == 1
        assert "largest concentration of delay" in superlatives[0].text

    def test_danish_superlative(self):
        result = extract_claims("Dette er den største koncentration af forsinkelser.")
        superlatives = [c for c in result.claims if c.form == ClaimForm.SUPERLATIVE]
        assert superlatives

    def test_superlative_stops_before_linking_verb(self):
        """Regression: the trailing 'of X' clause must not swallow the
        linking verb and everything after it."""
        result = extract_claims("The largest concentration of current delay is within electrical activities.")
        superlatives = [c for c in result.claims if c.form == ClaimForm.SUPERLATIVE]
        assert len(superlatives) == 1
        assert superlatives[0].text.strip().endswith("delay")
        assert "is within" not in superlatives[0].text


class TestActivityIdReferenceClaims:
    def test_bare_alphanumeric_id(self):
        result = extract_claims("A142 is delayed by 18 days.")
        ids = [c for c in result.claims if c.form == ClaimForm.ACTIVITY_ID_REFERENCE]
        assert any(c.extracted_values["activity_id"] == "A142" for c in ids)

    def test_task_id_keyword_form(self):
        result = extract_claims("Task ID 41 is blocking downstream work.")
        ids = [c for c in result.claims if c.form == ClaimForm.ACTIVITY_ID_REFERENCE]
        assert any(c.extracted_values["activity_id"] == "41" for c in ids)

    def test_bare_number_alone_is_not_an_id(self):
        """A plain number with no letters must not be misread as an id —
        that is `NUMERIC_QUANTITY`'s territory."""
        result = extract_claims("17 activities are delayed.")
        ids = [c for c in result.claims if c.form == ClaimForm.ACTIVITY_ID_REFERENCE]
        assert ids == []

    def test_keyword_and_bare_forms_do_not_double_count(self):
        result = extract_claims("Task ID A142 is delayed.")
        ids = [c for c in result.claims if c.form == ClaimForm.ACTIVITY_ID_REFERENCE]
        assert len(ids) == 1


class TestDateDurationClaims:
    def test_days_duration(self):
        result = extract_claims("The finish date moved 18 days.")
        durations = [c for c in result.claims if c.form == ClaimForm.DATE_DURATION]
        assert any(c.extracted_values.get("number") == 18.0 and c.extracted_values.get("unit") == "days" for c in durations)

    def test_week_range_duration(self):
        result = extract_claims("Expected delay: 4-8 weeks.")
        durations = [c for c in result.claims if c.form == ClaimForm.DATE_DURATION]
        assert durations
        assert durations[0].extracted_values.get("number_upper") == 8.0

    def test_iso_date(self):
        result = extract_claims("Reference date: 2026-01-05.")
        dates = [c for c in result.claims if c.form == ClaimForm.DATE_DURATION]
        assert any(c.extracted_values.get("date") == "2026-01-05" for c in dates)

    def test_dmy_date(self):
        result = extract_claims("The finish date moved to 01-03-2026.")
        dates = [c for c in result.claims if c.form == ClaimForm.DATE_DURATION]
        assert any(c.extracted_values.get("date") == "01-03-2026" for c in dates)

    def test_danish_duration_unit(self):
        result = extract_claims("Forventet forsinkelse: 6 uger.")
        durations = [c for c in result.claims if c.form == ClaimForm.DATE_DURATION]
        assert any(c.extracted_values.get("unit") == "uger" for c in durations)

    def test_duration_not_double_counted_as_numeric_quantity(self):
        """'18 days' must be one DATE_DURATION claim, not also a
        NUMERIC_QUANTITY claim on the same digits."""
        result = extract_claims("A142 is delayed by 18 days.")
        numerics = [c for c in result.claims if c.form == ClaimForm.NUMERIC_QUANTITY]
        assert not any("18" in c.text for c in numerics)


class TestCausalClaims:
    def test_caused_by(self):
        result = extract_claims("The delay was caused by a coordination issue.")
        causals = [c for c in result.claims if c.form == ClaimForm.CAUSAL]
        assert len(causals) == 1

    def test_bare_caused_verb_form(self):
        """Brief §20's own wrong-example phrasing: 'Electrical work caused
        the delay' — the bare verb form, not 'caused by'."""
        result = extract_claims("Electrical work caused the delay in Building NK.")
        causals = [c for c in result.claims if c.form == ClaimForm.CAUSAL]
        assert len(causals) == 1
        assert causals[0].extracted_values["trigger"].lower() == "caused"

    def test_due_to(self):
        result = extract_claims("The schedule slipped due to a design change.")
        causals = [c for c in result.claims if c.form == ClaimForm.CAUSAL]
        assert causals

    def test_danish_causal_trigger(self):
        result = extract_claims("Forsinkelsen skyldes en koordineringskonflikt.")
        causals = [c for c in result.claims if c.form == ClaimForm.CAUSAL]
        assert causals

    def test_causal_claim_never_has_asserted_fields(self):
        """Brief §20/TL-6.3: causal claims cannot be verified from
        schedule data alone — no fact-store field applies, ever."""
        result = extract_claims("The delay was caused by a coordination issue.")
        causals = [c for c in result.claims if c.form == ClaimForm.CAUSAL]
        assert all(c.asserted_fields == () for c in causals)

    def test_causal_claim_coexists_with_other_claims_in_same_sentence(self):
        """Regression: a causal claim's broad (whole-sentence) span must
        not suppress, or be suppressed by, a numeric/id/date claim that
        lives in the same sentence — brief's own combined case."""
        result = extract_claims("A142 is delayed by 18 days, caused by a coordination issue.")
        forms = {c.form for c in result.claims}
        assert ClaimForm.CAUSAL in forms
        assert ClaimForm.ACTIVITY_ID_REFERENCE in forms
        assert ClaimForm.DATE_DURATION in forms


# ============================================================================
# AC3 — claims record spans that enable targeted removal/qualification
# ============================================================================


class TestClaimSpans:
    def test_span_matches_text_exactly(self):
        text = "There are 12 delayed activities."
        result = extract_claims(text)
        for claim in result.claims:
            assert text[claim.span[0]:claim.span[1]] == claim.text

    def test_span_is_a_valid_offset_pair(self):
        result = extract_claims(BRIEF_16_EXAMPLE)
        for claim in result.claims:
            start, end = claim.span
            assert 0 <= start < end <= len(BRIEF_16_EXAMPLE)


# ============================================================================
# AC4 — unparseable / undecomposable text is marked unverified
# ============================================================================


class TestUndecomposableInput:
    def test_none_is_not_decomposable(self):
        result = extract_claims(None)
        assert result.decomposable is False
        assert result.claims == ()

    def test_non_string_is_not_decomposable(self):
        result = extract_claims(12345)
        assert result.decomposable is False

    def test_empty_string_is_decomposable_with_no_claims(self):
        """Distinct from the undecomposable case: an empty answer
        genuinely has zero claims to verify — that is a legitimate,
        trivially-safe outcome, not a failure to process."""
        result = extract_claims("")
        assert result.decomposable is True
        assert result.claims == ()

    def test_whitespace_only_string_is_decomposable_with_no_claims(self):
        result = extract_claims("   \n\t  ")
        assert result.decomposable is True
        assert result.claims == ()

    def test_plain_prose_with_no_detectable_claims_is_still_decomposable(self):
        """A sentence with none of the five claim shapes is legitimately
        claim-free — this is not the same as 'could not be processed.'"""
        result = extract_claims("The schedule was reviewed by the team.")
        assert result.decomposable is True
        assert result.claims == ()

    def test_extraction_failure_is_marked_undecomposable_not_silently_empty(self, monkeypatch):
        """If pattern matching itself fails for any reason, the result
        must say so — never silently report zero claims, which a caller
        could mistake for 'this text is clean.'"""
        import src.trust.claims as claims_module

        def _boom(_text):
            raise RuntimeError("simulated extraction failure")

        monkeypatch.setattr(claims_module, "_extract_all_claims", _boom)
        result = extract_claims("17 activities are delayed.")
        assert result.decomposable is False
        assert result.claims == ()
        assert "simulated extraction failure" in result.reason


# ============================================================================
# Do-not — a model is never the arbiter; this module is deterministic only
# ============================================================================


class TestNoModelInvolvement:
    def test_module_imports_no_llm_client(self):
        """Static check: `src/trust/claims.py` must never import an LLM
        client (openai, AzureOpenAI, or any `*_agent` module) — extraction
        is regex/parsing only, per this task's own Do-not rule."""
        import pathlib

        source_path = pathlib.Path(__file__).resolve().parents[2] / "src" / "trust" / "claims.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        forbidden_substrings = ("openai", "predictive_agent", "src.agent")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not any(forbidden in name for forbidden in forbidden_substrings), (
                    f"claims.py imports {name!r} — extraction must be deterministic, no model involvement"
                )

    def test_repeated_calls_are_identical(self):
        """Pure function: same input, same output, every time — no model
        variance possible."""
        result1 = extract_claims(BRIEF_16_EXAMPLE)
        result2 = extract_claims(BRIEF_16_EXAMPLE)
        assert result1 == result2
