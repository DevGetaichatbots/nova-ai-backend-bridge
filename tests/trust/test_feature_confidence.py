r"""Tests for TL-4.4 — Feature-specific confidence calculation.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-4-trust-engine.md` (TL-4.4):
- AC1: Five feature confidences computed independently.
- AC2: LLM-inferred critical path never reports VERIFIED.
- AC3: Schedule with no float data reports critical path as REVIEW or UNAVAILABLE.
- AC4: Feature confidences appear in dashboard payload.
"""
from __future__ import annotations

import pytest
from src.trust.engine import TrustAssessment, TrustEngine
from src.trust.vocabulary import TrustState
from src.version_1_0.adapters import adapt_health_dashboard, compute_feature_confidences


class TestFeatureConfidence:
    def setup_method(self):
        self.engine = TrustEngine()

    def test_five_feature_confidences_computed(self):
        conf = compute_feature_confidences({"requires_verification_count": 0, "has_explicit_float": False})
        assert "schedule_parsing" in conf
        assert "activity_matching" in conf
        assert "progress_comparison" in conf
        assert "critical_path" in conf
        assert "forecast" in conf

    def test_inferred_critical_path_never_reports_verified(self):
        conf = compute_feature_confidences({"requires_verification_count": 0, "has_explicit_float": False})
        assert conf["critical_path"] != TrustState.VERIFIED.value
        assert conf["critical_path"] in (TrustState.REVIEW.value, "unavailable")

    def test_feature_confidences_included_in_health_payload(self):
        data = {
            "executive_summary": {"selected_activities": 5, "requires_verification_count": 0},
            "summary_notes": {},
            "changed_activities": {},
            "progress_vs_expected": [],
        }
        res = adapt_health_dashboard(data)
        assert "feature_confidence" in res
        assert res["feature_confidence"]["schedule_parsing"] == TrustState.VERIFIED.value
