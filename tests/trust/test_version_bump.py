r"""Tests for TL-2.6 — Version bump (NUSF format v2).

Encodes acceptance criteria from `changes/trust-layer/plan/phase-2-identity.md` (TL-2.6):
- AC1: ScheduleMetadata.nusf_version defaults to "2.0".
- AC2: Ingested schedule instances output nusf_version "2.0".
"""
from __future__ import annotations
from datetime import datetime
from ingestion.models.nusf import ScheduleMetadata
from ingestion.normalization.engine import NormalizationEngine


class TestVersionBump:
    def test_schedule_metadata_default_version(self):
        meta = ScheduleMetadata(
            project_name="Test Project",
            source_system="CSV",
            source_filename="test.csv",
            data_date=datetime.now(),
            total_activities=1,
            total_relationships=0,
            earliest_date=datetime.now(),
            latest_date=datetime.now(),
            duration_days=10,
            parse_quality_score=1.0,
        )
        assert meta.nusf_version == "2.0"

    def test_normalization_engine_outputs_v2(self):
        from ingestion.recognition.heuristics import RecognitionResult
        extracted = {
            "headers": ["ID", "Aktivitet", "Start", "Slut"],
            "rows": [["A101", "Foundation Pour", "01-05-2026", "10-05-2026"]],
        }
        rec = RecognitionResult(
            column_map={"source_id": "ID", "name": "Aktivitet", "planned_start": "Start", "planned_finish": "Slut"},
            ai_needed=False,
            confidence=1.0,
            match_key="entydigt_id",
            format_label="",
        )
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "CSV", "test.csv")
        assert schedule.metadata.nusf_version == "2.0"
