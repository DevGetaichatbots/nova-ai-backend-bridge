r"""Tests for TL-4.6 — Pre-flight source quality check and gating decisions.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-4-trust-engine.md` (TL-4.6):
- AC1: All three outcomes (PASS, PARTIAL, BLOCK) reachable.
- AC2: BLOCK returns a structured refusal payload (never HTTP 500).
- AC3: PARTIAL response enumerates what was excluded and why.
"""
from __future__ import annotations

import datetime
import pytest
from ingestion.models.nusf import Activity, NormalizedSchedule, ScheduleMetadata
from src.trust.preflight import PreflightReport, run_preflight_check


class TestPreflightGating:
    def _make_metadata(self, count: int = 1) -> ScheduleMetadata:
        return ScheduleMetadata(
            project_name="Test Project",
            source_filename="test.pdf",
            source_system="PDF_OCR",
            data_date=datetime.datetime(2026, 1, 1),
            total_activities=count,
            total_relationships=0,
            earliest_date=datetime.datetime(2026, 1, 1),
            latest_date=datetime.datetime(2026, 1, 30),
            duration_days=30,
            parse_quality_score=0.95,
        )

    def test_pass_decision_on_clean_schedule(self):
        act = Activity(
            internal_id="ACT-1",
            source_id="ACT-1",
            name="Clean Activity",
            planned_start=datetime.datetime(2026, 1, 1),
            planned_finish=datetime.datetime(2026, 1, 10),
            duration_hours=80.0,
            percent_complete=0.0,
            provenance={},
        )
        schedule = NormalizedSchedule(
            metadata=self._make_metadata(1),
            activities=[act],
            relationships=[],
            validation_passed=True,
        )
        report = run_preflight_check(schedule)
        assert report.decision == "PASS"
        assert report.confidently_parsed == 1

    def test_partial_decision_on_some_unresolved_activities(self):
        activities = [
            Activity(
                internal_id=f"ACT-{i}",
                source_id=f"ACT-{i}",
                name=f"Clean Activity {i}",
                planned_start=datetime.datetime(2026, 1, 1),
                planned_finish=datetime.datetime(2026, 1, 10),
                duration_hours=80.0,
                percent_complete=0.0,
                provenance={},
            )
            for i in range(1, 5)
        ]
        activities.append(
            Activity(
                internal_id="__unknown_row5",
                source_id="",
                name="Unresolved Activity",
                planned_start=datetime.datetime(2026, 1, 1),
                planned_finish=datetime.datetime(2026, 1, 10),
                duration_hours=80.0,
                percent_complete=0.0,
                provenance={},
            )
        )
        schedule = NormalizedSchedule(
            metadata=self._make_metadata(5),
            activities=activities,
            relationships=[],
            validation_passed=True,
        )
        report = run_preflight_check(schedule)
        assert report.decision == "PARTIAL"
        assert len(report.excluded_activities) == 1

    def test_block_decision_and_structured_refusal(self):
        schedule = NormalizedSchedule(
            metadata=self._make_metadata(0),
            activities=[],
            relationships=[],
            validation_passed=False,
        )
        report = run_preflight_check(schedule)
        assert report.decision == "BLOCK"

        refusal = report.to_refusal_response()
        assert refusal["status"] == "blocked"
        assert refusal["gating_decision"] == "BLOCK"
        assert "Nova has paused analysis" in refusal["message"]
        assert "report" in refusal
