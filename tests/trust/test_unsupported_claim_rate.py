"""Tests for TL-6.7 — Unsupported factual claim rate (brief §39).

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-6-agent-contract.md` (TL-6.7):

- AC1: Rate computed across the full fixture corpus. A standing
  suite of test questions runs against `verify_narrative`; the
  resulting CONTRADICTED count feeds the metric.
- AC2: Test-question set defined and committed. The suite lives in
  `tests/trust/harness.py::_NARRATIVE_VERIFICATION_SUITE` and is
  exercised on every `python -m tests.trust.harness compare` run.
- AC3: Non-zero rate lists the specific unsupported claims. The
  `unsupported_offending` list captures `(question_id, claim_text)`
  pairs; `harness compare` renders them under the metric line.
- AC4: Metric appears in the regression report as its own line.
  `ComparisonReport.render()` always emits it, before the per-fixture
  diff block.

Brief §39 / Do-not rule: "Do not average this away across many
claims. One unsupported factual claim is a defect, not a rounding
error." — the metric counts claims, not fixture failures; one
CONTRADICTED in a 1000-claim run is still a defect. `meets_target`
is the brief §39 invariant, separate from the suite's calibration
(adversarial fixtures deliberately produce CONTRADICTED claims so
the metric is exercised — that is the calibration signal, not a
regression).
"""
from __future__ import annotations

import pytest

from src.trust.claims import (
    Claim,
    ClaimForm,
    NarrativeVerificationResult,
    UnsupportedClaimMetric,
    VerifiedClaim,
    VerificationOutcome,
    collect_unsupported_claims,
    compute_unsupported_claim_metric,
    verify_narrative,
)
from src.trust.vocabulary import ClaimKind


# ============================================================================
# Helpers
# ============================================================================


def _verified(text: str, kind: ClaimKind = ClaimKind.FACT) -> VerifiedClaim:
    """One VERIFIED claim (kind defaults to FACT)."""
    return VerifiedClaim(
        claim=Claim(text=text, span=(0, len(text)), form=ClaimForm.NUMERIC_QUANTITY),
        outcome=VerificationOutcome.VERIFIED,
        reason="test fixture",
        kind=kind,
    )


def _contradicted(text: str, kind: ClaimKind = ClaimKind.FACT) -> VerifiedClaim:
    return VerifiedClaim(
        claim=Claim(text=text, span=(0, len(text)), form=ClaimForm.NUMERIC_QUANTITY),
        outcome=VerificationOutcome.CONTRADICTED,
        reason="test fixture",
        kind=kind,
    )


def _unverifiable(text: str, kind: ClaimKind = ClaimKind.UNKNOWN) -> VerifiedClaim:
    return VerifiedClaim(
        claim=Claim(text=text, span=(0, len(text)), form=ClaimForm.NUMERIC_QUANTITY),
        outcome=VerificationOutcome.UNVERIFIABLE,
        reason="test fixture",
        kind=kind,
    )


def _result(
    verified: list = None,
    contradicted: list = None,
    unverifiable: list = None,
) -> NarrativeVerificationResult:
    """Build a `NarrativeVerificationResult` from explicit claim lists.
    Keyword-only args so callers cannot accidentally absorb claims into
    the wrong bucket via positional ambiguity."""
    verified = verified or []
    contradicted = contradicted or []
    unverifiable = unverifiable or []
    return NarrativeVerificationResult(
        cleaned_text="",
        unverified_claim_texts=[vc.claim.text for vc in unverifiable],
        verified=verified,
        contradicted=contradicted,
        unverifiable=unverifiable,
        decomposable=True,
    )


# ============================================================================
# AC1 — Rate computation
# ============================================================================


class TestMetricComputation:
    """AC1: `compute_unsupported_claim_metric` aggregates a batch of
    `NarrativeVerificationResult` into a single rate. Brief §39's
    metric is `unsupported_count / total_claims` (zero is the target)."""

    def test_zero_metric_on_empty_batch(self):
        metric = compute_unsupported_claim_metric([])
        assert metric.verified_count == 0
        assert metric.contradicted_count == 0
        assert metric.unverifiable_count == 0
        assert metric.total_claims == 0
        assert metric.unsupported_count == 0
        assert metric.unsupported_rate == 0.0
        assert metric.meets_target() is True

    def test_zero_unsupported_when_all_verified(self):
        metric = compute_unsupported_claim_metric([
            _result(verified=[_verified("a"), _verified("b"), _verified("c")]),
        ])
        assert metric.verified_count == 3
        assert metric.contradicted_count == 0
        assert metric.unsupported_count == 0
        assert metric.unsupported_rate == 0.0
        assert metric.meets_target() is True

    def test_unsupported_count_is_contradicted_count(self):
        """Brief §39: 'unsupported factual claims' = claims the system
        caught as false. CONTRADICTED is the headline failure mode
        (TL-6.3 Do-not rule: 'removing the claim' is the only safe
        response)."""
        metric = compute_unsupported_claim_metric([
            _result(
                verified=[_verified("good")],
                contradicted=[_contradicted("fabricated-1"), _contradicted("fabricated-2")],
            ),
        ])
        assert metric.unsupported_count == 2
        assert metric.meets_target() is False

    def test_rate_is_contradicted_over_total(self):
        metric = compute_unsupported_claim_metric([
            _result(
                verified=[_verified("a"), _verified("b"), _verified("c")],
                contradicted=[_contradicted("d")],
            ),
        ])
        assert metric.total_claims == 4
        assert metric.unsupported_count == 1
        assert metric.unsupported_rate == pytest.approx(0.25)

    def test_unverifiable_counted_separately_from_unsupported(self):
        """UNVERIFIABLE is a different class of failure (the data had
        nothing to check against) — not the same as CONTRADICTED.
        Brief §39's headline metric is CONTRADICTED; UNVERIFIABLE is
        reported separately so a caller can distinguish."""
        metric = compute_unsupported_claim_metric([
            _result(
                verified=[_verified("good-1"), _verified("good-2")],
                contradicted=[_contradicted("fabricated")],
                unverifiable=[_unverifiable("uncertain")],
            ),
        ])
        assert metric.verified_count == 2
        assert metric.unverifiable_count == 1
        assert metric.contradicted_count == 1
        assert metric.unsupported_count == 1  # only CONTRADICTED
        assert metric.unsupported_rate == pytest.approx(0.25)

    def test_metric_aggregates_across_multiple_results(self):
        """The metric is computed across a batch — one bad result
        doesn't average away (Do-not rule)."""
        metric = compute_unsupported_claim_metric([
            _result(verified=[_verified("good-a"), _verified("good-b")]),
            _result(contradicted=[_contradicted("fabricated")]),
            _result(verified=[_verified("good-c")]),
        ])
        assert metric.total_claims == 4
        assert metric.unsupported_count == 1
        # One defect, not 1/4 averaged — the metric reports the count
        assert metric.meets_target() is False


# ============================================================================
# AC3 — Offending claims enumeration
# ============================================================================


class TestOffendingClaimsEnumeration:
    """AC3: a non-zero rate lists the specific unsupported claims,
    tagged with the originating question so the report is actionable."""

    def test_collects_concatenated_offenders(self):
        results = [
            _result(verified=[_verified("ok")], contradicted=[_contradicted("bad-1")]),
            _result(verified=[_verified("ok")], contradicted=[_contradicted("bad-2")]),
        ]
        offenders = collect_unsupported_claims(results, ["Q1", "Q2"])
        assert offenders == [("Q1", "bad-1"), ("Q2", "bad-2")]

    def test_empty_when_no_offenders(self):
        results = [_result(verified=[_verified("ok")])]
        offenders = collect_unsupported_claims(results, ["Q1"])
        assert offenders == []

    def test_length_mismatch_raises(self):
        results = [_result(verified=[_verified("ok")])]
        with pytest.raises(ValueError, match="lengths must match"):
            collect_unsupported_claims(results, ["Q1", "Q2"])

    def test_keeps_contradicted_only_not_unverifiable(self):
        """Only CONTRADICTED claims are the unsupported factual claims
        (brief §39's headline). UNVERIFIABLE claims are reported
        separately as a different class of failure."""
        results = [_result(
            verified=[_verified("ok")],
            contradicted=[_contradicted("CONTRADICTED-text")],
            unverifiable=[_unverifiable("UNVERIFIABLE-text")],
        )]
        offenders = collect_unsupported_claims(results, ["Q1"])
        assert offenders == [("Q1", "CONTRADICTED-text")]


# ============================================================================
# AC4 — Metric appears in the harness compare report as its own line
# ============================================================================


class TestHarnessCompareIntegration:
    """AC4: the metric appears in `python -m tests.trust.harness compare`
    output as its own line, with offending claims listed when the rate
    is non-zero."""

    def test_compare_render_includes_metric_line(self):
        from tests.trust.harness import (
            compare_against_baseline,
            UnsupportedClaimMetric,
        )
        # Build a minimal baseline directory with one empty fixture
        # so compare runs without "new_baseline" noise
        import json
        import tempfile
        from pathlib import Path
        from tests.trust.harness import _NARRATIVE_VERIFICATION_SUITE
        # Use a temp baselines dir so the test is hermetic
        with tempfile.TemporaryDirectory() as tmp:
            baselines_dir = Path(tmp)
            (baselines_dir / "fake.json").write_text("{}")
            report = compare_against_baseline(baselines_dir=baselines_dir, fixtures=[])
        rendered = report.render()
        # AC4: metric line is present
        assert "Unsupported factual claims" in rendered
        assert "TL-6.7" in rendered
        assert "brief §39" in rendered

    def test_compare_render_includes_offending_claims_when_nonzero(self):
        """AC3: non-zero rate lists offending claims with question IDs.
        The adversarial fixtures in the suite are designed to produce
        CONTRADICTED claims — the metric exercises both the gate
        (which catches them) and the report (which lists them).
        """
        from tests.trust.harness import compare_against_baseline
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            baselines_dir = Path(tmp)
            (baselines_dir / "fake.json").write_text("{}")
            report = compare_against_baseline(baselines_dir=baselines_dir, fixtures=[])
        rendered = report.render()
        # The suite has two adversarial fixtures (TL67-Q5, TL67-Q6)
        # that produce CONTRADICTED claims — they MUST be listed
        assert "Offending claims:" in rendered
        assert "TL67-Q5-fabricated-number-contradicted" in rendered
        assert "TL67-Q6-fabricated-id-contradicted" in rendered


# ============================================================================
# AC2 — Test-question set is defined and committed
# ============================================================================


class TestStandingSuite:
    """AC2: brief §39's method is "a standing set of test questions
    run against known fixtures" — the suite is committed to
    `tests/trust/harness.py::_NARRATIVE_VERIFICATION_SUITE` and runs
    on every compare."""

    def test_suite_has_clean_baseline_questions(self):
        from tests.trust.harness import _NARRATIVE_VERIFICATION_SUITE
        # At least 4 clean baselines (clean = no fabrication, verifies)
        clean_baselines = [
            q for q in _NARRATIVE_VERIFICATION_SUITE
            if "clean" in q["id"]
        ]
        assert len(clean_baselines) >= 4, (
            f"expected >=4 clean baseline questions, got {len(clean_baselines)}"
        )

    def test_suite_has_adversarial_contradiction_questions(self):
        """AC1 (adversarial coverage): the suite must include at least
        one fabricated-number and one fabricated-id question, each
        designed to trigger CONTRADICTED. Brief §39's headline
        failure mode."""
        from tests.trust.harness import _NARRATIVE_VERIFICATION_SUITE
        ids = [q["id"] for q in _NARRATIVE_VERIFICATION_SUITE]
        assert any("fabricated-number" in i for i in ids)
        assert any("fabricated-id" in i for i in ids)

    def test_suite_has_causal_question_for_unverifiable_coverage(self):
        """Brief §18's A142 — a causal claim always lands UNVERIFIABLE,
        not VERIFIED (brief §20). The suite covers this."""
        from tests.trust.harness import _NARRATIVE_VERIFICATION_SUITE
        ids = [q["id"] for q in _NARRATIVE_VERIFICATION_SUITE]
        assert any("causal" in i for i in ids)

    def test_every_question_has_required_fields(self):
        from tests.trust.harness import _NARRATIVE_VERIFICATION_SUITE
        for q in _NARRATIVE_VERIFICATION_SUITE:
            for required in ("id", "narrative", "facts", "language"):
                assert required in q, f"{q.get('id', '?')!r} missing {required!r}"
            assert isinstance(q["facts"], dict)


# ============================================================================
# Brief §39 Do-not rule: do not average away
# ============================================================================


class TestDoNotAverageAway:
    """Brief §39 / Do-not rule: one unsupported factual claim is a
    defect, not a rounding error. The metric must surface it even
    when surrounded by many verified claims."""

    def test_one_contradicted_among_many_verified_is_still_nonzero(self):
        # 99 verified, 1 contradicted — the metric is NOT 1/100
        # "rounded to 0"; it is 1 CONTRADICTED claim.
        results = [_result(
            verified=[_verified(f"good-{i}") for i in range(99)],
            contradicted=[_contradicted("fabricated-1")],
        )]
        metric = compute_unsupported_claim_metric(results)
        assert metric.unsupported_count == 1
        assert metric.unsupported_rate == pytest.approx(0.01)
        # Brief §39 invariant: meets_target() returns False because
        # any CONTRADICTED, however few, is a defect
        assert metric.meets_target() is False

    def test_collect_unsupported_claims_surfaces_single_offender(self):
        results = [_result(
            verified=[_verified(f"good-{i}") for i in range(50)]
                    + [_verified(f"more-good-{i}") for i in range(50)],
            contradicted=[_contradicted("the-one-fabricated-number")],
        )]
        offenders = collect_unsupported_claims(results, ["Q1"])
        assert offenders == [("Q1", "the-one-fabricated-number")]


# ============================================================================
# AC4 (render shape) — metric line is on its own
# ============================================================================


class TestRenderShape:
    """AC4: the metric line is rendered as its own block, not buried
    in another section. Pins the format so a future change that
    merges it into another section fails the test."""

    def test_render_contains_metric_line_standalone(self):
        from tests.trust.harness import render_unsupported_claim_metric
        metric = UnsupportedClaimMetric(
            verified_count=10, contradicted_count=0,
            unverifiable_count=2, total_claims=12,
        )
        lines = render_unsupported_claim_metric(metric, [])
        text = "\n".join(lines)
        # The metric line is its own paragraph
        assert "Unsupported factual claims (TL-6.7 / brief §39)" in text
        assert "0/12 (0.00%) — target met: True" in text

    def test_render_lists_offenders_when_nonzero(self):
        from tests.trust.harness import render_unsupported_claim_metric
        metric = UnsupportedClaimMetric(
            verified_count=8, contradicted_count=2,
            unverifiable_count=0, total_claims=10,
        )
        offenders = [("Q1", "fabricated-1"), ("Q2", "fabricated-2")]
        lines = render_unsupported_claim_metric(metric, offenders)
        text = "\n".join(lines)
        assert "2/10 (20.00%) — target met: False" in text
        assert "Offending claims:" in text
        assert "[Q1] 'fabricated-1'" in text
        assert "[Q2] 'fabricated-2'" in text
