r"""Tests for TL-2.3 — Architectural guard: no synthesized ID can surface.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-2-identity.md` (TL-2.3):
- AC1: Every displayed activity ID across rendered output is either byte-identical to a value present in the source document, or empty/unverified.
- AC2: Adversarial fixture with no ID column produces NO synthesized/positional numeric IDs anywhere in output.
- AC3: Static check asserts no row-index or composite-ID invention patterns exist near source_id assignment.
"""
from __future__ import annotations

import pathlib
import pytest
from ingestion.normalization.engine import NormalizationEngine
from ingestion.recognition.heuristics import RecognitionResult
from src.experimental.nusf_compare_engine import parse_nusf_chunks, compare_nusf_chunks, _dashboard_meta


class TestNoInventedIdsGuard:
    def test_static_check_no_invention_patterns_in_engine(self):
        engine_path = pathlib.Path(__file__).resolve().parents[2] / "ingestion" / "normalization" / "engine.py"
        content = engine_path.read_text(encoding="utf-8")

        # Assert no row_idx + 1 assignment to source_id
        assert "raw_source_id = str(row_idx + 1)" not in content, "Found positional ID invention fallback!"
        # Assert no composite name|location assignment to source_id
        assert 'raw_source_id = f"{_stable_text(raw_name)}' not in content, "Found composite ID invention fallback!"

    def test_adversarial_fixture_no_id_column(self):
        """Schedule with no ID column must produce activities with source_id is None."""
        extracted = {
            "headers": ["Aktivitet", "Start", "Slut"],
            "rows": [
                ["Task A", "01-01-2026", "10-01-2026"],
                ["Task B", "11-01-2026", "20-01-2026"],
            ],
        }
        rec = RecognitionResult(
            column_map={"name": "Aktivitet", "planned_start": "Start", "planned_finish": "Slut"},
            ai_needed=False,
            confidence=1.0,
            match_key="row_index",
            format_label="",
        )
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "CSV", "no_ids.csv")

        for act in schedule.activities:
            assert act.source_id is None, f"Expected source_id to be None, got {act.source_id!r}"

        for act in schedule.activities:
            meta = _dashboard_meta({"name": act.name, "source_id": act.source_id or ""})
            assert meta["id"] == "", f"Expected empty display id for unverifiable ID, got {meta['id']!r}"

    def test_verbatim_id_preservation(self):
        """Durable IDs from source document are preserved verbatim."""
        extracted = {
            "headers": ["ID", "Aktivitet", "Start", "Slut"],
            "rows": [["ACT-999", "Task A", "01-01-2026", "10-01-2026"]],
        }
        rec = RecognitionResult(
            column_map={"source_id": "ID", "name": "Aktivitet", "planned_start": "Start", "planned_finish": "Slut"},
            ai_needed=False,
            confidence=1.0,
            match_key="entydigt_id",
            format_label="",
        )
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "CSV", "with_ids.csv")
        act = schedule.activities[0]

        assert act.source_id == "ACT-999"
        meta = _dashboard_meta({"name": act.name, "source_id": act.source_id})
        assert meta["id"] == "ACT-999"
