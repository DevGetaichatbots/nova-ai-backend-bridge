r"""Tests for TL-3.2 — Match classification with level and method.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-3-matching.md` (TL-3.2):
- AC1: Every match carries a level and a method.
- AC2: Fixtures with durable verified IDs yield L1 for all matches.
- AC3: Fixtures with positional-only IDs yield no L1 matches.
- AC4: Q-3 resolved in DECISIONS.md (L2/L3 map to TrustState.REVIEW).
"""
from __future__ import annotations

import pytest
from src.experimental.nusf_compare_engine import _resolve_activity_matches
from src.trust.matching import MatchLevel, to_trust_state
from src.trust.vocabulary import TrustState


class TestMatchClassification:
    def test_durable_ids_yield_l1_matches(self):
        old_rows = [
            {"_identity": "ACT-1", "source_id": "EXT-100", "match_method": "verified_source_id", "name": "Task A", "planned_start": "2026-01-01", "planned_finish": "2026-01-10"},
            {"_identity": "ACT-2", "source_id": "EXT-200", "match_method": "verified_source_id", "name": "Task B", "planned_start": "2026-01-05", "planned_finish": "2026-01-15"},
        ]
        new_rows = [
            {"_identity": "ACT-1-v2", "source_id": "EXT-100", "match_method": "verified_source_id", "name": "Task A Renamed", "planned_start": "2026-01-02", "planned_finish": "2026-01-11"},
            {"_identity": "ACT-2-v2", "source_id": "EXT-200", "match_method": "verified_source_id", "name": "Task B", "planned_start": "2026-01-06", "planned_finish": "2026-01-16"},
        ]
        matches, results = _resolve_activity_matches(old_rows, new_rows)
        assert len(matches) == 2
        assert results["ACT-1-v2"].level == MatchLevel.L1_EXACT_VERIFIED_ID
        assert results["ACT-1-v2"].method == "verified_source_id"
        assert results["ACT-1-v2"].matched_id == "ACT-1"
        assert results["ACT-2-v2"].level == MatchLevel.L1_EXACT_VERIFIED_ID
        assert to_trust_state(results["ACT-1-v2"].level) == TrustState.VERIFIED

    def test_positional_only_ids_yield_no_l1_matches(self):
        old_rows = [
            {"_identity": "Row_0", "source_id": "0", "match_method": "positional", "name": "Concrete Pour", "location_path": "Zone A", "planned_start": "2026-01-01", "planned_finish": "2026-01-10"},
        ]
        new_rows = [
            {"_identity": "Row_0", "source_id": "0", "match_method": "positional", "name": "Concrete Pour", "location_path": "Zone A", "planned_start": "2026-01-01", "planned_finish": "2026-01-10"},
        ]
        matches, results = _resolve_activity_matches(old_rows, new_rows)
        assert len(matches) == 1
        # Positional IDs are not verified durable IDs, so match level cannot be L1!
        assert results["Row_0"].level != MatchLevel.L1_EXACT_VERIFIED_ID
        assert results["Row_0"].level in (MatchLevel.L2_STRONG_MULTI_FIELD, MatchLevel.L3_PARTIAL)
        assert to_trust_state(results["Row_0"].level) == TrustState.REVIEW

    def test_multi_field_matches_map_to_review_trust_state(self):
        assert to_trust_state(MatchLevel.L2_STRONG_MULTI_FIELD) == TrustState.REVIEW
        assert to_trust_state(MatchLevel.L3_PARTIAL) == TrustState.REVIEW
