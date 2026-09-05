r"""Tests for TL-3.1 — MatchConfidence level model.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-3-matching.md` (TL-3.1):
- AC1: All five levels defined with brief §12 semantics.
- AC2: MatchResult records which fields provided the evidence.
- AC3: L5 cannot be constructed with a non-null matched counterpart (type/model invariant).
- AC4: Mapping to TrustState is total for all 5 levels.
- AC5: L4 and L5 enforce requires_verification = True.
"""
from __future__ import annotations

import pytest
from src.trust.matching import MatchLevel, MatchResult, to_trust_state
from src.trust.vocabulary import TrustState


class TestMatchLevels:
    def test_all_five_levels_exist(self):
        levels = [l.value for l in MatchLevel]
        assert "L1_EXACT_VERIFIED_ID" in levels
        assert "L2_STRONG_MULTI_FIELD" in levels
        assert "L3_PARTIAL" in levels
        assert "L4_FUZZY" in levels
        assert "L5_NO_RELIABLE_MATCH" in levels

    def test_match_result_records_evidence(self):
        res = MatchResult(
            level=MatchLevel.L2_STRONG_MULTI_FIELD,
            method="name_location_trade_floor",
            evidence=["name", "location", "trade", "floor"],
            matched_id="ACT-100",
        )
        assert res.evidence == ["name", "location", "trade", "floor"]
        assert res.matched_id == "ACT-100"
        assert res.requires_verification is False

    def test_l5_cannot_have_matched_id(self):
        with pytest.raises(ValueError, match="L5_NO_RELIABLE_MATCH cannot have a non-null matched_id"):
            MatchResult(
                level=MatchLevel.L5_NO_RELIABLE_MATCH,
                method="unmatched",
                matched_id="ACT-999",
            )

    def test_l4_l5_enforce_requires_verification(self):
        res_l4 = MatchResult(
            level=MatchLevel.L4_FUZZY,
            method="fuzzy_similarity",
            matched_id="ACT-101",
        )
        assert res_l4.requires_verification is True

        res_l5 = MatchResult(
            level=MatchLevel.L5_NO_RELIABLE_MATCH,
            method="unmatched",
            matched_id=None,
        )
        assert res_l5.requires_verification is True

    def test_total_mapping_to_trust_state(self):
        assert to_trust_state(MatchLevel.L1_EXACT_VERIFIED_ID) == TrustState.VERIFIED
        assert to_trust_state(MatchLevel.L2_STRONG_MULTI_FIELD) == TrustState.REVIEW
        assert to_trust_state(MatchLevel.L3_PARTIAL) == TrustState.REVIEW
        assert to_trust_state(MatchLevel.L4_FUZZY) == TrustState.UNVERIFIED
        assert to_trust_state(MatchLevel.L5_NO_RELIABLE_MATCH) == TrustState.UNVERIFIED
