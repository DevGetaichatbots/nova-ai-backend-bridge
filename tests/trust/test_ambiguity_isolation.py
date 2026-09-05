r"""Tests for TL-3.4 — Isolate ambiguous matches from confirmed results.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-3-matching.md` (TL-3.4):
- AC1: Ambiguous activities excluded from confirmed comparison counts.
- AC2: Total is reconcilable across confirmed + requires_verification + unmatched.
- AC3: No activity silently vanishes.
"""
from __future__ import annotations

import pytest
from src.experimental.nusf_compare_engine import compare_nusf_chunks


class TestAmbiguityIsolation:
    def test_ambiguous_matches_routed_to_requires_verification_bucket(self):
        # Two activities in old schedule with same name and location, dates 1 day apart
        old_chunks = [
            {
                "content": (
                    "Id;Name;Location;Planned_Start;Planned_Finish;Percent_Complete\n"
                    "1;Task Alpha;Zone A;01-01-2026;10-01-2026;0\n"
                    "2;Task Alpha;Zone A;02-01-2026;11-01-2026;0\n"
                )
            }
        ]
        new_chunks = [
            {
                "content": (
                    "Id;Name;Location;Planned_Start;Planned_Finish;Percent_Complete\n"
                    "1;Task Alpha;Zone A;01-01-2026;10-01-2026;50\n"
                )
            }
        ]

        result = compare_nusf_chunks(old_chunks, new_chunks, reference_date="05-01-2026")
        exec_summary = result["executive_summary"]
        req_verif = result["requires_verification_activities"]

        assert exec_summary["requires_verification_count"] == len(req_verif)
        assert len(req_verif) > 0
        assert req_verif[0]["activity"] == "Task Alpha"
        assert "excluded from confirmed comparison results" in req_verif[0]["reason"]

    def test_reconciliation_total_matches_all_activities(self):
        old_chunks = [
            {
                "content": (
                    "Id;Name;Location;Planned_Start;Planned_Finish;Percent_Complete\n"
                    "1;Clean Task 1;Zone A;01-01-2026;10-01-2026;100\n"
                    "2;Ambiguous Task;Zone B;01-01-2026;10-01-2026;0\n"
                    "3;Ambiguous Task;Zone B;02-01-2026;11-01-2026;0\n"
                )
            }
        ]
        new_chunks = [
            {
                "content": (
                    "Id;Name;Location;Planned_Start;Planned_Finish;Percent_Complete\n"
                    "1;Clean Task 1;Zone A;01-01-2026;10-01-2026;100\n"
                    "2;Ambiguous Task;Zone B;01-01-2026;10-01-2026;10\n"
                )
            }
        ]

        result = compare_nusf_chunks(old_chunks, new_chunks, reference_date="05-01-2026")
        exec_summary = result["executive_summary"]
        total_new = exec_summary["selected_activities"]
        req_verif_count = exec_summary["requires_verification_count"]
        confirmed_count = exec_summary["confirmed_activities_count"]

        # Reconcilable invariant: confirmed + requires_verification == total
        assert confirmed_count + req_verif_count == total_new
