r"""Tests for TL-4.1 — TrustEngine module and Verifier protocol integration.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-4-trust-engine.md` (TL-4.1):
- AC1: TrustEngine computes trust assessments naming the weakest link.
- AC2: TrustEngine satisfies Verifier protocol and integrates with diffs.py.
"""
from __future__ import annotations

import pytest
from src.trust.engine import TrustAssessment, TrustEngine
from src.trust.vocabulary import TrustState
from src.version_1_0.diffs import Verifier, ActivityDiff, FieldDiff


class TestTrustEngine:
    def test_trust_engine_verifier_protocol_compliance(self):
        engine = TrustEngine()
        # Ensure engine is recognized as a Verifier protocol instance
        assert isinstance(engine, Verifier)

    def test_verifier_methods_return_expected_boolean(self):
        engine = TrustEngine()
        ass1 = TrustAssessment(
            state=TrustState.VERIFIED,
            reason="Confirmed",
            weakest_link="planned_start",
        )
        ass2 = TrustAssessment(
            state=TrustState.REVIEW,
            reason="OCR unconfident",
            weakest_link="planned_finish",
        )

        engine.register_activity_assessment("ACT-1", "planned_start", ass1)
        engine.register_activity_assessment("ACT-1", "planned_finish", ass2)

        assert engine.verify_field("ACT-1", "planned_start") is True
        assert engine.verify_field("ACT-1", "planned_finish") is False
        # Activity overall is REVIEW because planned_finish is REVIEW
        assert engine.verify_activity("ACT-1") is False

    def test_all_verified_activity_returns_true(self):
        engine = TrustEngine()
        ass1 = TrustAssessment(state=TrustState.VERIFIED, reason="Ok", weakest_link="start")
        ass2 = TrustAssessment(state=TrustState.VERIFIED, reason="Ok", weakest_link="finish")

        engine.register_activity_assessment("ACT-2", "start", ass1)
        engine.register_activity_assessment("ACT-2", "finish", ass2)

        assert engine.verify_activity("ACT-2") is True
