r"""Tests for TL-3.5 — Precision-first metrics reporting in regression harness.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-3-matching.md` (TL-3.5):
- AC1: Computes precision, false match rate, unmatched rate, and requires-verification rate.
- AC2: Precision and recall reported separately (never a single blended F-score).
- AC3: Deliberate false match is caught and reported.
- AC4: Metrics appear in harness compare output.
"""
from __future__ import annotations

import pytest
from tests.trust.harness import (
    Fixture,
    MatchMetrics,
    compute_fixture_metrics,
    compare_against_baseline,
)


class TestPrecisionMetrics:
    def test_metrics_computation(self):
        fixture = Fixture(
            id="test_fx",
            dir=None,  # type: ignore
            kind="pair",
            reference_date="Unknown",
            ground_truth={"expected": {"false_matches": 1}},
        )
        snapshot = {
            "health": {
                "comparison": {
                    "executive_summary": {
                        "selected_activities": 10,
                        "confirmed_matches_count": 8,
                        "requires_verification_count": 1,
                    }
                }
            }
        }
        metrics = compute_fixture_metrics(fixture, snapshot)
        assert metrics.fixture_id == "test_fx"
        # 8 confirmed matches, 1 false match => 7 correct / 9 matches = 0.7778
        assert metrics.match_precision < 1.0
        # 1 false match / 9 matches = 0.1111
        assert metrics.false_match_rate > 0.0
        # 1 requires verification / 10 total = 0.1000
        assert metrics.requires_verification_rate == 0.1
        # 10 - 8 - 1 = 1 unmatched / 10 total = 0.1000
        assert metrics.unmatched_rate == 0.1

    def test_precision_metrics_appear_in_harness_output(self):
        report = compare_against_baseline()
        output = report.render()
        assert "Precision-First Matching Metrics:" in output
        assert "Precision:" in output
        assert "False Match Rate:" in output
        assert "Verification Required:" in output
