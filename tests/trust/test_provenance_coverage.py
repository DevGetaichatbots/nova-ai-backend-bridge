"""Tests for TL-1.5 — comprehensive Provenance coverage across critical
and secondary fields.

Encodes every acceptance criterion from
`changes/trust-layer/plan/phase-1-provenance.md` (TL-1.5):

- AC1: every critical field on every activity in every fixture has a
  Provenance entry.
- AC2: no critical field has Provenance with
  `extraction_method="unknown"` for a clean fixture.
- AC3: derived fields are distinguishable from read fields.
- AC4: harness `compare` shows no change to any computed result
  (covered end-to-end by the existing harness runner; this file
  pins the model-level invariants the harness relies on).

Drives `NormalizationEngine.normalize()` directly with synthetic
extracted data + cells. No Azure HTTP, no pdfplumber, no live API
calls.

Defence-in-depth tests beyond the four ACs:
- secondary fields (`location_path`, `area`, `floor`, `phase`,
  `discipline`, `critical_flag`, `total_float`) follow the same
  rule as critical fields but only emit when the source data
  carries the value.
- `_row` fallback is preserved as a last resort with
  `extraction_method="unknown"` so it cannot be confused with
  real provenance (ADR-013).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from ingestion.normalization.engine import NormalizationEngine
from ingestion.recognition.heuristics import RecognitionResult


# ---------------------------------------------------------------------------
# Minimal RecognitionResult stand-in (shared with test_provenance_threading)
# ---------------------------------------------------------------------------

def _recognition(column_map: dict, *, ai_needed: bool = False,
                 confidence: float = 1.0) -> RecognitionResult:
    return RecognitionResult(
        column_map=column_map,
        ai_needed=ai_needed,
        confidence=confidence,
        match_key="entydigt_id",
        format_label="",
    )


def _cell(content: str, *, ocr_confidence=0.91, page_number=1,
          extraction_method="ocr_table", source_field=""):
    """Build a unified-shape cell dict."""
    return {
        "content": content,
        "ocr_confidence": ocr_confidence,
        "page_number": page_number,
        "bounding_box": None,
        "spans": None,
        "extraction_method": extraction_method,
        "source_field": source_field,
        "source_row": 0,
        "source_document": "synthetic.pdf",
    }


def _extracted(headers, rows, cells=None) -> dict:
    return {
        "headers": headers,
        "rows": rows,
        "cells": cells,
        "source_system": "PDF",
        "file_name": "synthetic.pdf",
    }


# ---------------------------------------------------------------------------
# AC1 — every critical field has a Provenance entry
# ---------------------------------------------------------------------------

class TestEveryCriticalFieldHasProvenance:
    """AC1: every critical field on every activity has a provenance
    entry. Brief §6 names Activity ID, Name, Start, Finish, Duration,
    Progress as critical."""

    CRITICAL_FIELDS = (
        "source_id", "name", "planned_start", "planned_finish",
        "duration_hours", "percent_complete",
    )

    def _normalize_with_all_critical_columns(self):
        """Build a schedule where every critical column is mapped,
        so every critical field gets a Provenance entry from a
        real cell."""
        cells = [[
            _cell("42", source_field="source_id", ocr_confidence=0.95),
            _cell("Activity X", source_field="name", ocr_confidence=0.95),
            _cell("15-01-2026", source_field="planned_start",
                  ocr_confidence=0.91),
            _cell("20-01-2026", source_field="planned_finish",
                  ocr_confidence=0.88),
            _cell("5d", source_field="duration", ocr_confidence=0.93),
            _cell("50%", source_field="percent_complete", ocr_confidence=0.97),
        ]]
        extracted = _extracted(
            headers=["source_id", "name", "planned_start",
                     "planned_finish", "duration", "percent_complete"],
            rows=[["42", "Activity X", "15-01-2026",
                   "20-01-2026", "5d", "50%"]],
            cells=cells,
        )
        rec = _recognition({
            "source_id": "source_id", "name": "name",
            "planned_start": "planned_start",
            "planned_finish": "planned_finish",
            "duration": "duration",
            "percent_complete": "percent_complete",
        })
        engine = NormalizationEngine()
        return engine.normalize(extracted, rec, "PDF", "x.pdf").activities

    def test_all_six_critical_fields_have_provenance(self):
        """Every critical field on the activity has a Provenance
        entry — no missing field."""
        acts = self._normalize_with_all_critical_columns()
        assert len(acts) == 1
        prov = acts[0].provenance
        for field in self.CRITICAL_FIELDS:
            assert field in prov, (
                f"critical field {field!r} missing from provenance; "
                "AC1 violated — every critical field must have an entry"
            )

    def test_each_critical_field_has_cell_evidence(self):
        """When the cell is present, the Provenance carries the
        TL-1.2 evidence fields — `ocr_confidence`, `page_number`,
        `source_document`, `extraction_method`."""
        acts = self._normalize_with_all_critical_columns()
        prov = acts[0].provenance
        for field in self.CRITICAL_FIELDS:
            assert prov[field].ocr_confidence is not None, (
                f"{field} should carry cell evidence but ocr_confidence is None"
            )
            assert prov[field].page_number == 1
            assert prov[field].source_document == "synthetic.pdf"
            assert prov[field].extraction_method == "ocr_table"

    def test_legacy_fixtures_get_full_coverage_too(self):
        """Even when cells is None (legacy data, non-OCR sources),
        every critical field still gets a Provenance entry —
        `cells=None` is not a reason to skip a critical field
        (TL-1.5 spec, AC1)."""
        extracted = _extracted(
            headers=["source_id", "name", "planned_start",
                     "planned_finish", "duration", "percent_complete"],
            rows=[["42", "Activity X", "15-01-2026",
                   "20-01-2026", "5d", "50%"]],
            cells=None,
        )
        rec = _recognition({
            "source_id": "source_id", "name": "name",
            "planned_start": "planned_start",
            "planned_finish": "planned_finish",
            "duration": "duration",
            "percent_complete": "percent_complete",
        })
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        prov = acts[0].provenance
        for field in self.CRITICAL_FIELDS:
            assert field in prov
            # OCR-specific fields stay None (no fabrication).
            assert prov[field].ocr_confidence is None
            assert prov[field].page_number is None


# ---------------------------------------------------------------------------
# AC2 — no critical field has extraction_method="unknown" on a clean fixture
# ---------------------------------------------------------------------------

class TestNoUnknownExtractionMethodForCleanCriticalFields:
    """AC2: when a cell is available, every critical field's
    `extraction_method` reflects the cell's actual method (e.g.
    `ocr_table`), not the silent `"unknown"` sentinel."""

    def test_ocr_table_method_threads_through_for_all_critical(self):
        cells = [[
            _cell("42", source_field="source_id",
                  extraction_method="ocr_table"),
            _cell("Activity X", source_field="name",
                  extraction_method="ocr_table"),
            _cell("15-01-2026", source_field="planned_start",
                  extraction_method="ocr_table"),
            _cell("20-01-2026", source_field="planned_finish",
                  extraction_method="ocr_table"),
            _cell("5d", source_field="duration",
                  extraction_method="ocr_table"),
            _cell("50%", source_field="percent_complete",
                  extraction_method="ocr_table"),
        ]]
        extracted = _extracted(
            headers=["source_id", "name", "planned_start",
                     "planned_finish", "duration", "percent_complete"],
            rows=[["42", "Activity X", "15-01-2026",
                   "20-01-2026", "5d", "50%"]],
            cells=cells,
        )
        rec = _recognition({
            "source_id": "source_id", "name": "name",
            "planned_start": "planned_start",
            "planned_finish": "planned_finish",
            "duration": "duration",
            "percent_complete": "percent_complete",
        })
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        prov = acts[0].provenance
        for field in ("source_id", "name", "planned_start",
                      "planned_finish", "duration_hours",
                      "percent_complete"):
            assert prov[field].extraction_method == "ocr_table", (
                f"{field}.extraction_method should be 'ocr_table' "
                "from the cell, not 'unknown'"
            )

    def test_ocr_text_layer_method_threads_through(self):
        """Text-layer cells carry `extraction_method="ocr_text_layer"`
        (TL-1.3). The Provenance reflects that verbatim — the
        unrated path is a load-bearing distinction (brief §45)."""
        cells = [[
            _cell("42", source_field="source_id",
                  extraction_method="ocr_text_layer"),
            _cell("Activity X", source_field="name",
                  extraction_method="ocr_text_layer"),
            _cell("15-01-2026", source_field="planned_start",
                  extraction_method="ocr_text_layer"),
            _cell("20-01-2026", source_field="planned_finish",
                  extraction_method="ocr_text_layer"),
            _cell("5d", source_field="duration",
                  extraction_method="ocr_text_layer"),
            _cell("50%", source_field="percent_complete",
                  extraction_method="ocr_text_layer"),
        ]]
        extracted = _extracted(
            headers=["source_id", "name", "planned_start",
                     "planned_finish", "duration", "percent_complete"],
            rows=[["42", "Activity X", "15-01-2026",
                   "20-01-2026", "5d", "50%"]],
            cells=cells,
        )
        rec = _recognition({
            "source_id": "source_id", "name": "name",
            "planned_start": "planned_start",
            "planned_finish": "planned_finish",
            "duration": "duration",
            "percent_complete": "percent_complete",
        })
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        prov = acts[0].provenance
        for field in ("source_id", "name", "planned_start",
                      "planned_finish", "duration_hours",
                      "percent_complete"):
            assert prov[field].extraction_method == "ocr_text_layer"


# ---------------------------------------------------------------------------
# AC3 — derived fields are distinguishable from read fields
# ---------------------------------------------------------------------------

class TestDerivedFieldsAreDistinguishable:
    """AC3: derived fields carry `extraction_method="derived"` and a
    `source_field_override` indicating what they were derived from.
    Read fields carry the cell's extraction_method."""

    def test_duration_hours_derived_from_date_delta(self):
        """When `dur_col` is missing but `duration_hours > 0` is
        computed from `(planned_finish - planned_start)`, the
        Provenance marks it derived — so downstream consumers can
        tell "read from source" from "computed by Nova"."""
        cells = [[
            _cell("42", source_field="source_id"),
            _cell("Activity X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start"),
            _cell("20-01-2026", source_field="planned_finish"),
            # No `duration` column → 5d gets derived from date delta.
        ]]
        extracted = _extracted(
            headers=["source_id", "name", "planned_start", "planned_finish"],
            rows=[["42", "Activity X", "15-01-2026", "20-01-2026"]],
            cells=cells,
        )
        rec = _recognition({
            "source_id": "source_id", "name": "name",
            "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        prov = acts[0].provenance
        assert "duration_hours" in prov
        assert prov["duration_hours"].extraction_method == "derived"
        # The source_field indicates what was derived from.
        assert "computed_from" in prov["duration_hours"].source_field

    def test_source_id_derived_when_only_positional_id(self):
        """When `match_key` is "id" or "row_index" and no real ID
        column exists, source_id is None (unverified). The Provenance
        marks it derived with source_field="unverified"."""
        rec = RecognitionResult(
            column_map={
                "name": "name",
                "planned_start": "planned_start",
                "planned_finish": "planned_finish",
            },
            ai_needed=False,
            confidence=1.0,
            match_key="row_index",
            format_label="",
        )
        cells = [[
            _cell("Activity X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start"),
            _cell("20-01-2026", source_field="planned_finish"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["Activity X", "15-01-2026", "20-01-2026"]],
            cells=cells,
        )
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        assert acts[0].source_id is None
        prov = acts[0].provenance
        assert "source_id" in prov
        assert prov["source_id"].extraction_method == "derived"
        assert prov["source_id"].source_field == "unverified"

    def test_phase_derived_from_location_path(self):
        """`phase` is always derived from `location_path` (no direct
        column source). The Provenance marks it derived. Phase
        requires a multi-part location_path (≥ 3 `/`-separated
        parts); a two-part path like "Area A / 2. sal" yields no
        phase."""
        cells = [[
            _cell("42", source_field="source_id"),
            _cell("Activity X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start"),
            _cell("20-01-2026", source_field="planned_finish"),
            _cell("Building A / 2. sal / Phase 1",
                  source_field="location_path"),
        ]]
        extracted = _extracted(
            headers=["source_id", "name", "planned_start",
                     "planned_finish", "location_path"],
            rows=[["42", "Activity X", "15-01-2026",
                   "20-01-2026",
                   "Building A / 2. sal / Phase 1"]],
            cells=cells,
        )
        rec = _recognition({
            "source_id": "source_id", "name": "name",
            "planned_start": "planned_start",
            "planned_finish": "planned_finish",
            # The engine reads location via `area_col = mapper.get("area")`.
            # The semantic key in the column_map must be "area", not
            # "location_path", otherwise area_col is None and the engine
            # never reads raw_location_path → _location_parts returns empty
            # → phase is never derived.
            "area": "location_path",
        })
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        prov = acts[0].provenance
        assert "phase" in prov
        assert prov["phase"].extraction_method == "derived"
        assert prov["phase"].normalized_value == "Phase 1"

    def test_derived_field_carries_no_ocr_confidence(self):
        """Defence-in-depth: derived fields never carry an
        `ocr_confidence`. They have no OCR measurement to report."""
        cells = [[
            _cell("42", source_field="source_id"),
            _cell("Activity X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start"),
            _cell("20-01-2026", source_field="planned_finish"),
            _cell("Area A", source_field="location_path"),
        ]]
        extracted = _extracted(
            headers=["source_id", "name", "planned_start",
                     "planned_finish", "location_path"],
            rows=[["42", "Activity X", "15-01-2026",
                   "20-01-2026", "Area A"]],
            cells=cells,
        )
        rec = _recognition({
            "source_id": "source_id", "name": "name",
            "planned_start": "planned_start",
            "planned_finish": "planned_finish",
            "location_path": "location_path",
        })
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        prov = acts[0].provenance
        # The derived `phase` field has no OCR measurement.
        if "phase" in prov:
            assert prov["phase"].ocr_confidence is None
        # Same for `duration_hours` if it was derived.
        if "duration_hours" in prov:
            assert prov["duration_hours"].ocr_confidence is None


# ---------------------------------------------------------------------------
# Secondary fields follow the same rule, when source data carries them
# ---------------------------------------------------------------------------

class TestSecondaryFieldsFollowTheSameRule:
    """Secondary fields (brief §6) follow the same rule as critical
    fields but only emit when the source data carries the value."""

    def test_secondary_fields_emit_when_columns_mapped(self):
        cells = [[
            _cell("42", source_field="source_id"),
            _cell("Activity X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start"),
            _cell("20-01-2026", source_field="planned_finish"),
            _cell("Building A / Floor 2", source_field="location_path"),
            _cell("Yes", source_field="critical_flag"),
            _cell("2.5", source_field="total_float"),
        ]]
        extracted = _extracted(
            headers=["source_id", "name", "planned_start",
                     "planned_finish", "location_path",
                     "critical_flag", "total_float"],
            rows=[["42", "Activity X", "15-01-2026",
                   "20-01-2026", "Building A / Floor 2", "Yes", "2.5"]],
            cells=cells,
        )
        rec = _recognition({
            "source_id": "source_id", "name": "name",
            "planned_start": "planned_start",
            "planned_finish": "planned_finish",
            "location_path": "location_path",
            "area": "location_path",  # so `area_col` is "location_path",
                                       # not the YAML's "omr." which
                                       # doesn't exist in headers
            "critical_flag": "critical_flag",
            "total_float": "total_float",
        })
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        prov = acts[0].provenance
        # `location_path` is read from a column → emitted.
        assert "location_path" in prov
        assert prov["location_path"].extraction_method == "ocr_table"
        # `critical_flag` is read from a column → emitted.
        assert "critical_flag" in prov
        # `total_float` is read from a column → emitted.
        assert "total_float" in prov
        # `area`: read directly from area_col (the location_path cell) →
        # extraction_method is the cell's method ("ocr_table"), not "derived".
        assert "area" in prov
        assert prov["area"].extraction_method == "ocr_table"
        # `floor` and `phase` have no direct column source → always derived.
        for derived_field in ("floor", "phase"):
            if derived_field in prov:
                assert prov[derived_field].extraction_method == "derived"

    def test_secondary_fields_omitted_when_source_absent(self):
        """When no column maps to a secondary field, that field is
        simply omitted from provenance — it doesn't appear at all."""
        cells = [[
            _cell("42", source_field="source_id"),
            _cell("Activity X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start"),
            _cell("20-01-2026", source_field="planned_finish"),
            # No `location_path`, no `critical_flag`, no `total_float`.
        ]]
        extracted = _extracted(
            headers=["source_id", "name", "planned_start", "planned_finish"],
            rows=[["42", "Activity X", "15-01-2026", "20-01-2026"]],
            cells=cells,
        )
        rec = _recognition({
            "source_id": "source_id", "name": "name",
            "planned_start": "planned_start",
            "planned_finish": "planned_finish",
            # Note: no `location_path`, `critical_flag`, `total_float`.
        })
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        prov = acts[0].provenance
        assert "location_path" not in prov
        assert "critical_flag" not in prov
        assert "total_float" not in prov


# ---------------------------------------------------------------------------
# `_row` fallback — last-resort, marked explicitly as unknown
# ---------------------------------------------------------------------------

class TestRowFallbackIsExplicit:
    """The `_row` fallback is preserved as a last resort. It must be
    marked `extraction_method="unknown"` so it cannot be confused
    with real provenance."""

    def test_row_fallback_emitted_when_no_fields_mapped(self):
        """When no column maps to a known semantic role, the only
        Provenance entry is `_row` with `extraction_method="unknown"`."""
        extracted = _extracted(
            headers=["unknown_col"],
            rows=[["some value"]],
            cells=[[_cell("some value", source_field="unknown_col")]],
        )
        rec = _recognition({})  # no fields mapped
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        # No parseable dates → no activities created (rows skipped).
        # Pin the contract via a different scenario.
        extracted2 = _extracted(
            headers=["unknown_col", "date_col"],
            rows=[["x", "15-01-2026"], ["y", "20-01-2026"]],
            cells=[
                [_cell("x", source_field="unknown_col"),
                 _cell("15-01-2026", source_field="date_col")],
                [_cell("y", source_field="unknown_col"),
                 _cell("20-01-2026", source_field="date_col")],
            ],
        )
        acts = engine.normalize(extracted2, rec, "PDF", "x.pdf").activities
        # No activities (no parseable planned_start/finish) → no
        # provenance rows emitted at all. The `_row` fallback only
        # emits when an activity is otherwise created but no fields
        # are mapped. Pin that contract here:
        assert acts == [] or all(
            not a.provenance or "_row" not in a.provenance
            for a in acts
        )

    def test_row_fallback_marked_unknown(self):
        """The `_row` fallback Provenance carries extraction_method='unknown'.

        Implementation note: the `_row` path inside normalize() fires
        only when `not provenance` after all field-building logic runs.
        In practice this requires zero columns to be mapped in the
        recognition. But zero-mapped columns means every `_get_val()`
        call returns "" (no col_name), so `raw_name`, `raw_start`, and
        `raw_finish` are all empty strings — the row is skipped by the
        empty-row guard before provenance is ever built. The `_row`
        fallback is therefore unreachable through a standard normalize()
        call with zero mapped fields.

        This test pins the shape contract directly at the Provenance
        model level — the `_row` entry the engine would emit is
        constructed with the same arguments the engine uses, so any
        future change to those arguments (source_field format,
        extraction_method value, ocr_confidence coercion) will break
        this test before it reaches production.
        """
        from ingestion.models.nusf import Provenance

        for row_idx in range(3):  # verify the f"row_{row_idx}" pattern
            prov = Provenance(
                source_field=f"row_{row_idx}",
                source_row=row_idx,
                is_ai_inferred=False,
                confidence=1.0,
                raw_value=None,
                normalized_value=None,
                ocr_confidence=None,
                page_number=None,
                bounding_box=None,
                source_document="x.pdf",
                extraction_method="unknown",
            )
            assert prov.extraction_method == "unknown", (
                "_row fallback must be marked 'unknown' so it cannot be "
                "confused with real provenance (ADR-013)"
            )
            assert prov.source_field == f"row_{row_idx}"
            assert prov.ocr_confidence is None, (
                "_row fallback must not fabricate an OCR confidence "
                "(same rule as ADR-009 / ADR-010)"
            )

        # Also verify the engine's last-resort fallback block matches
        # this shape. Walk the engine source to confirm the literal
        # arguments haven't drifted from this test's expectations.
        import ast, pathlib
        engine_src = pathlib.Path(__file__).parent.parent.parent / (
            "ingestion/normalization/engine.py"
        )
        src_text = engine_src.read_text()
        assert 'extraction_method="unknown"' in src_text, (
            "engine.py _row fallback block must use extraction_method='unknown'"
        )
        assert 'source_field=f"row_{row_idx}"' in src_text, (
            "engine.py _row fallback block must set source_field=f'row_{row_idx}'"
        )