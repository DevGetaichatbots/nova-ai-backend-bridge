r"""Tests for TL-3.3 — Replace greedy nearest-date forcing with ambiguity detection.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-3-matching.md` (TL-3.3):
- AC1: Ambiguous candidates in duplicate-name group trigger L4_FUZZY + requires_verification=True instead of forced match.
- AC2: Unique-name fixture is unaffected (matches cleanly).
- AC3: Ambiguous rows record their candidate list in MatchResult.candidates.
"""
from __future__ import annotations

import pytest
from src.experimental.nusf_compare_engine import _resolve_activity_matches, _AMBIGUITY_MARGIN_DAYS
from src.trust.matching import MatchLevel


class TestNoForcedMatching:
    def test_ambiguity_margin_constant_exists(self):
        assert _AMBIGUITY_MARGIN_DAYS > 0

    def test_unique_name_matches_cleanly(self):
        old_rows = [
            {"_identity": "ACT-1", "name": "Unique Foundation Work", "location_path": "Zone A", "planned_start": "2026-01-01", "planned_finish": "2026-01-10"}
        ]
        new_rows = [
            {"_identity": "ACT-1-v2", "name": "Unique Foundation Work", "location_path": "Zone A", "planned_start": "2026-01-02", "planned_finish": "2026-01-11"}
        ]
        matches, results = _resolve_activity_matches(old_rows, new_rows)
        assert len(matches) == 1
        assert "ACT-1-v2" in matches
        assert results["ACT-1-v2"].requires_verification is False

    def test_ambiguous_duplicate_name_group_refuses_pairing(self):
        # Two activities with same name and location, close dates (1 day apart distance)
        old_rows = [
            {"_identity": "Dæksel_A", "name": "Dæksel", "location_path": "Bygning 1", "planned_start": "2026-02-01", "planned_finish": "2026-02-10"},
            {"_identity": "Dæksel_B", "name": "Dæksel", "location_path": "Bygning 1", "planned_start": "2026-02-02", "planned_finish": "2026-02-11"},
        ]
        new_rows = [
            {"_identity": "Dæksel_A_v2", "name": "Dæksel", "location_path": "Bygning 1", "planned_start": "2026-02-01", "planned_finish": "2026-02-10"},
        ]
        matches, results = _resolve_activity_matches(old_rows, new_rows)
        # Because candidate date distance between Dæksel_A (0 days) and Dæksel_B (2 days) is < _AMBIGUITY_MARGIN_DAYS (3 days),
        # Nova refuses to greedily pick Dæksel_A and forces review!
        assert "Dæksel_A_v2" not in matches
        res = results["Dæksel_A_v2"]
        assert res.level == MatchLevel.L4_FUZZY
        assert res.requires_verification is True
        assert len(res.candidates) == 2
        cand_ids = [c["matched_id"] for c in res.candidates]
        assert "Dæksel_A" in cand_ids
        assert "Dæksel_B" in cand_ids
