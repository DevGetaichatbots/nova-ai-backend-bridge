r"""Tests for TL-4.3 — Weakest-link propagation.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-4-trust-engine.md` (TL-4.3):
- AC1: Propagation is weakest-link, not averaging.
- AC2: Brief §14 worked example chains produce documented outcomes.
- AC3: Every propagated assessment names its weakest link.
- AC4: Strong LLM output over weak inputs cannot yield VERIFIED.
"""
from __future__ import annotations

import pytest
from src.trust.engine import TrustAssessment, TrustEngine
from src.trust.vocabulary import TrustState


class TestPropagation:
    def setup_method(self):
        self.engine = TrustEngine()

    def test_brief_section_14_high_confidence_chain(self):
        ocr = self.engine.assess_value("planned_start", "2026-01-01", provenance={"confidence": 0.99})
        parse = TrustAssessment(state=TrustState.VERIFIED, reason="Clean parse", weakest_link="parser")
        match = TrustAssessment(state=TrustState.VERIFIED, reason="Exact L1 match", weakest_link="matcher")
        calc = TrustAssessment(state=TrustState.VERIFIED, reason="Exact delta", weakest_link="calculator")

        propagated = self.engine.propagate([ocr, parse, match, calc])
        assert propagated.state == TrustState.VERIFIED

    def test_brief_section_14_weak_link_chain_produces_unverified(self):
        ocr = self.engine.assess_value("planned_start", "2026-01-01", provenance={"confidence": 0.67})  # UNVERIFIED (< 80)
        parse = TrustAssessment(state=TrustState.REVIEW, reason="Parsing 91%", weakest_link="parser")
        match = TrustAssessment(state=TrustState.UNVERIFIED, reason="Match 58%", weakest_link="matcher")

        propagated = self.engine.propagate([ocr, parse, match])
        assert propagated.state == TrustState.UNVERIFIED
        assert propagated.weakest_link in ("planned_start", "matcher")

    def test_weakest_link_does_not_average(self):
        # 3 VERIFIED inputs + 1 UNVERIFIED input must yield UNVERIFIED, not REVIEW or VERIFIED
        v1 = TrustAssessment(state=TrustState.VERIFIED, reason="V1", weakest_link="link1")
        v2 = TrustAssessment(state=TrustState.VERIFIED, reason="V2", weakest_link="link2")
        v3 = TrustAssessment(state=TrustState.VERIFIED, reason="V3", weakest_link="link3")
        u1 = TrustAssessment(state=TrustState.UNVERIFIED, reason="U1", weakest_link="weak_link")

        propagated = self.engine.propagate([v1, v2, v3, u1])
        assert propagated.state == TrustState.UNVERIFIED
        assert propagated.weakest_link == "weak_link"
