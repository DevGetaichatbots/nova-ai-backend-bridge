r"""Tests for TL-4.5 — Source Conflict Detection Rules.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-4-trust-engine.md` (TL-4.5):
- AC1: All conflict types from brief §27 detected.
- AC2: Auto-swapped dates surface a visible SOURCE_CONFLICT issue.
- AC3: Conflicted values cannot report VERIFIED in TrustEngine.
"""
from __future__ import annotations

import datetime
import pytest
from ingestion.models.nusf import Activity, ActivityType, NormalizedSchedule, ScheduleMetadata
from ingestion.validation.engine import ValidationEngine
from ingestion.validation.issues import CAT_SOURCE_CONFLICT
from src.trust.engine import TrustEngine
from src.trust.vocabulary import TrustState


class TestConflictDetection:
    def setup_method(self):
        self.validator = ValidationEngine()
        self.engine = TrustEngine()

    def _make_metadata(self) -> ScheduleMetadata:
        return ScheduleMetadata(
            project_name="Test Project",
            source_filename="test.pdf",
            source_system="PDF_OCR",
            data_date=datetime.datetime(2026, 1, 1),
            total_activities=3,
            total_relationships=0,
            earliest_date=datetime.datetime(2026, 1, 1),
            latest_date=datetime.datetime(2026, 1, 30),
            duration_days=30,
            parse_quality_score=0.95,
        )

    def test_conflict_detection_rules(self):
        metadata = self._make_metadata()
        act1 = Activity(
            internal_id="ACT-1",
            source_id="ACT-1",
            name="Pour Concrete",
            planned_start=datetime.datetime(2026, 1, 1),
            planned_finish=datetime.datetime(2026, 1, 10),
            duration_hours=80.0,
            percent_complete=100.0,
            provenance={},
        )
        act2 = Activity(
            internal_id="ACT-2",
            source_id="ACT-1",  # Same ID, different name
            name="Lay Rebar",
            planned_start=datetime.datetime(2026, 1, 5),
            planned_finish=datetime.datetime(2026, 1, 15),
            duration_hours=80.0,
            percent_complete=50.0,
            provenance={},
        )
        act3 = Activity(
            internal_id="ACT-3",
            source_id="ACT-3",
            name="Formwork",
            planned_start=datetime.datetime(2026, 1, 1),
            planned_finish=datetime.datetime(2026, 1, 10),
            duration_hours=80.0,
            percent_complete=50.0,
            has_logic_warning=True,  # Auto-swapped dates
            provenance={},
        )

        schedule = NormalizedSchedule(metadata=metadata, activities=[act1, act2, act3], relationships=[], validation_passed=True)
        validated = self.validator.validate(schedule)

        conflict_issues = [i for i in validated.validation_issues if i.category == CAT_SOURCE_CONFLICT]
        assert len(conflict_issues) >= 2

        messages = [i.message for i in conflict_issues]
        assert any("same_id_different_names" in msg for msg in messages)
        assert any("date_swap" in msg for msg in messages)

    def test_conflicted_value_cannot_be_verified_in_trust_engine(self):
        metadata = self._make_metadata()
        act = Activity(
            internal_id="ACT-1",
            source_id="ACT-1",
            name="Pour Concrete",
            planned_start=datetime.datetime(2026, 1, 1),
            planned_finish=datetime.datetime(2026, 1, 10),
            duration_hours=80.0,
            percent_complete=50.0,
            has_logic_warning=True,
            provenance={},
        )
        schedule = NormalizedSchedule(metadata=metadata, activities=[act], relationships=[], validation_passed=True)
        validated = self.validator.validate(schedule)

        assessment = self.engine.assess_value(
            field_name="planned_start",
            value="2026-01-01",
            validation_issues=validated.validation_issues,
        )

        assert assessment.state != TrustState.VERIFIED
        assert assessment.state in (TrustState.REVIEW, TrustState.UNVERIFIED)
