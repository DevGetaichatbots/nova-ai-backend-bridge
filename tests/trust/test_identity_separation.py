r"""Tests for TL-2.2 — Split matching identity from source Activity ID.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-2-identity.md` (TL-2.2):
- AC1: `match_key` and `source_id` are separate fields with separate semantics.
- AC2: No composite `match_key` value ever appears in a display field (`source_id` or rendered `id`).
- AC3: `match_method` is recorded for every activity.
"""
from __future__ import annotations

import pytest

from ingestion.normalization.engine import NormalizationEngine
from ingestion.recognition.heuristics import RecognitionResult
from src.experimental.nusf_compare_engine import _dashboard_meta


def _recognition(column_map: dict, match_key: str = "entydigt_id") -> RecognitionResult:
    return RecognitionResult(
        column_map=column_map,
        ai_needed=False,
        confidence=1.0,
        match_key=match_key,
        format_label="",
    )


class TestIdentitySeparation:
    def test_durable_source_id_sets_matching_identity(self):
        extracted = {
            "headers": ["ID", "Name", "Start", "Finish"],
            "rows": [["TASK-101", "Foundation", "01-01-2026", "10-01-2026"]],
        }
        rec = _recognition({
            "source_id": "ID",
            "name": "Name",
            "planned_start": "Start",
            "planned_finish": "Finish",
        }, match_key="entydigt_id")

        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "CSV", "test.csv")
        act = schedule.activities[0]

        assert act.source_id == "TASK-101"
        assert act.match_key == "TASK-101"
        assert act.match_method == "verified_source_id"

    def test_composite_matching_does_not_leak_to_source_id_or_display_id(self):
        extracted = {
            "headers": ["Name", "Location", "Start", "Finish"],
            "rows": [["Concrete Pour", "Basement -1", "01-01-2026", "10-01-2026"]],
        }
        rec = _recognition({
            "name": "Name",
            "location_path": "Location",
            "planned_start": "Start",
            "planned_finish": "Finish",
        }, match_key="name_location")

        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "CSV", "test.csv")
        act = schedule.activities[0]

        # source_id MUST be None (unverified), match_key holds composite
        assert act.source_id is None
        assert act.match_key is not None
        assert "Concrete Pour" in act.match_key
        assert act.match_method == "name_location_composite"

        # Dashboard meta MUST NOT put composite in visual id
        row_dict = {"name": act.name, "source_id": act.source_id or "", "_identity_label": act.match_key}
        meta = _dashboard_meta(row_dict)
        assert meta["id"] == ""
        assert "Concrete Pour" not in meta["id"]
