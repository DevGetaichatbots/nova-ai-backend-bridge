"""Tests for TL-1.4 — cell-confidence threading into field-level Provenance.

Encodes every acceptance criterion from
`changes/trust-layer/plan/phase-1-provenance.md` (TL-1.4):

- AC1: for a PDF fixture, `activity.provenance["planned_start"].ocr_confidence`
  is a real number.
- AC2: `raw_value` differs from `normalized_value` wherever normalization
  changed it (e.g. date reformatting).
- AC3: `page_number` and `bounding_box` are populated for OCR-derived
  fields.
- AC4: harness `compare` shows no change to any computed result
  (covered end-to-end by the existing harness; this file pins the
  model-level invariant that the harness relies on).

The tests drive `NormalizationEngine.normalize()` directly with synthetic
extracted data + cells. No Azure HTTP, no pdfplumber, no live API calls.

Defence-in-depth tests beyond the four ACs:
- text-layer cells (TL-1.3) produce Provenance with `ocr_confidence=None`
  and `extraction_method="ocr_text_layer"` — the unrated path.
- when `cells` is absent (legacy data, non-OCR sources pre-TL-1.9),
  Provenance still constructs via the four-field legacy shape.
- a missing-cell position (cell is `None`) falls back to the legacy
  shape on that field only — other fields keep their cell evidence.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from ingestion.models.nusf import Provenance
from ingestion.normalization.engine import NormalizationEngine
from ingestion.recognition.heuristics import RecognitionResult


# ---------------------------------------------------------------------------
# Minimal RecognitionResult stand-in
# ---------------------------------------------------------------------------

def _recognition(column_map: dict[str, str], *, ai_needed: bool = False,
                 confidence: float = 1.0) -> RecognitionResult:
    """Build a RecognitionResult with a custom column map. The
    heuristics module's RecognitionResult accepts arbitrary keyword
    arguments; we only need `column_map` populated for `normalize()`
    to find columns."""
    return RecognitionResult(
        column_map=column_map,
        ai_needed=ai_needed,
        confidence=confidence,
        match_key="entydigt_id",
        format_label="",
    )


def _cell(content: str, *, ocr_confidence: float | None = 0.91,
          page_number: int | None = 1, bounding_box=None,
          extraction_method="ocr_table", source_field=""):
    """Build a unified-shape cell dict, the kind threaded through
    `_tables_to_headers_and_rows`."""
    return {
        "content": content,
        "ocr_confidence": ocr_confidence,
        "page_number": page_number,
        "bounding_box": bounding_box,
        "spans": None,
        "extraction_method": extraction_method,
        "source_field": source_field,
        "source_row": 0,
        "source_document": "synthetic.pdf",
    }


def _extracted(headers, rows, cells=None, *, source_system="PDF",
               filename="synthetic.pdf") -> dict:
    return {
        "headers": headers,
        "rows": rows,
        "cells": cells,
        "source_system": source_system,
        "file_name": filename,
    }


# ---------------------------------------------------------------------------
# AC1 — activity.provenance["planned_start"].ocr_confidence is real
# ---------------------------------------------------------------------------

class TestOcrConfidenceIsThreaded:
    def test_planned_start_ocr_confidence_threads_through(self):
        cells = [[
            _cell("Activity 42", source_field="name"),
            _cell("2026-01-15", source_field="planned_start",
                  ocr_confidence=0.91, page_number=1),
            _cell("2026-01-20", source_field="planned_finish",
                  ocr_confidence=0.85, page_number=1),
            _cell("42", source_field="id"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish", "id"],
            rows=[["Activity 42", "2026-01-15", "2026-01-20", "42"]],
            cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "synthetic.pdf")
        assert len(schedule.activities) == 1
        prov = schedule.activities[0].provenance["planned_start"]
        assert prov.ocr_confidence == 0.91
        assert isinstance(prov.ocr_confidence, float)

    def test_planned_finish_ocr_confidence_threads_through(self):
        cells = [[
            _cell("X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start",
                  ocr_confidence=0.91),
            _cell("20-01-2026", source_field="planned_finish",
                  ocr_confidence=0.62),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["X", "15-01-2026", "20-01-2026"]],
            cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["planned_finish"]
        assert prov.ocr_confidence == 0.62

    def test_name_field_also_carries_ocr_confidence(self):
        """AC1 mentions `planned_start` but the threading applies to every
        field that has a column mapping. `name` is the obvious second case."""
        cells = [[
            _cell("EL-Cable Installation", source_field="name",
                  ocr_confidence=0.74),
            _cell("15-01-2026", source_field="planned_start"),
            _cell("20-01-2026", source_field="planned_finish"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["EL-Cable Installation", "15-01-2026", "20-01-2026"]],
            cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["name"]
        assert prov.ocr_confidence == 0.74


# ---------------------------------------------------------------------------
# AC2 — raw_value differs from normalized_value when normalization changed it
# ---------------------------------------------------------------------------

class TestRawValueVsNormalizedValue:
    def test_date_format_normalization(self):
        """Cell raw value is "15-01-2026" (DD-MM-YYYY European);
        parse_date produces `datetime(2026, 1, 15, tzinfo=UTC)`. The
        Provenance must record both: `raw_value` is the cell text,
        `normalized_value` is the parsed ISO string. The brief §7
        explicitly forbids confusing the two."""
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
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["planned_start"]
        assert prov.raw_value == "15-01-2026"
        # Compare against the timezone-aware datetime the parser
        # actually returns — `parse_date` sets tzinfo=UTC, so
        # isoformat() includes the `+00:00` suffix.
        from datetime import timezone
        assert prov.normalized_value == datetime(2026, 1, 15, tzinfo=timezone.utc).isoformat()
        assert prov.raw_value != prov.normalized_value

    def test_finish_date_normalization(self):
        cells = [[
            _cell("X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start"),
            _cell("20-01-2026", source_field="planned_finish"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["X", "15-01-2026", "20-01-2026"]],
            cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["planned_finish"]
        assert prov.raw_value == "20-01-2026"
        from datetime import timezone
        assert prov.normalized_value == datetime(2026, 1, 20, tzinfo=timezone.utc).isoformat()

    def test_name_field_raw_and_normalized_are_equal(self):
        """For fields where no parsing happens, raw and normalized
        should be the same string. The contract is "differs when
        normalization changed it" — for `name`, nothing changed."""
        cells = [[
            _cell("Cable Tray Installation", source_field="name"),
            _cell("15-01-2026", source_field="planned_start"),
            _cell("20-01-2026", source_field="planned_finish"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["Cable Tray Installation", "15-01-2026", "20-01-2026"]],
            cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["name"]
        assert prov.raw_value == "Cable Tray Installation"
        assert prov.normalized_value == "Cable Tray Installation"


# ---------------------------------------------------------------------------
# AC3 — page_number and bounding_box are populated
# ---------------------------------------------------------------------------

class TestPageAndBoundingBox:
    def test_page_number_threads(self):
        cells = [[
            _cell("X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start",
                  page_number=3),
            _cell("20-01-2026", source_field="planned_finish"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["X", "15-01-2026", "20-01-2026"]], cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["planned_start"]
        assert prov.page_number == 3

    def test_bounding_box_threads(self):
        polygon = [10.0, 20.0, 110.0, 20.0, 110.0, 40.0, 10.0, 40.0]
        cells = [[
            _cell("X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start",
                  page_number=1, bounding_box=polygon),
            _cell("20-01-2026", source_field="planned_finish"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["X", "15-01-2026", "20-01-2026"]], cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["planned_start"]
        assert prov.bounding_box == polygon

    def test_page_and_box_combined(self):
        """Both fields populated simultaneously."""
        polygon = [0.0, 0.0, 100.0, 0.0, 100.0, 20.0, 0.0, 20.0]
        cells = [[
            _cell("X", source_field="name"),
            _cell("15-01-2026", source_field="planned_start",
                  page_number=2, bounding_box=polygon,
                  ocr_confidence=0.88),
            _cell("20-01-2026", source_field="planned_finish"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["X", "15-01-2026", "20-01-2026"]], cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["planned_start"]
        assert prov.page_number == 2
        assert prov.bounding_box == polygon
        assert prov.ocr_confidence == 0.88

    def test_missing_page_or_box_falls_back_to_none(self):
        """When the cell carries no `page_number` or `bounding_box`,
        Provenance carries `None` — never a fabricated default."""
        cells = [[
            _cell("X", source_field="name"),
            # No page_number, no bounding_box — degraded cell.
            _cell("15-01-2026", source_field="planned_start",
                  page_number=None, bounding_box=None,
                  ocr_confidence=0.91),
            _cell("20-01-2026", source_field="planned_finish"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["X", "15-01-2026", "20-01-2026"]], cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["planned_start"]
        assert prov.page_number is None
        assert prov.bounding_box is None
        assert prov.ocr_confidence == 0.91


# ---------------------------------------------------------------------------
# Graceful degradation — cells=None (legacy data, non-OCR pre-TL-1.9)
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_no_cells_falls_back_to_legacy_shape(self):
        """When `cells` is absent from `extracted`, Provenance still
        constructs. The legacy four-field shape is used (plus
        raw/normalized). No throw, no fabricated OCR confidence."""
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["Activity X", "15-01-2026", "20-01-2026"]],
            cells=None,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["planned_start"]
        # Legacy four-field shape carries the pre-TL-1.1 fields;
        # OCR-specific fields are absent (not coerced to defaults).
        assert prov.source_field == "planned_start"
        assert prov.ocr_confidence is None
        assert prov.page_number is None
        assert prov.bounding_box is None
        # raw_value / normalized_value still carry the
        # pre- vs post-normalization distinction (AC2 even on
        # the legacy path). Compare against the timezone-aware
        # datetime the parser actually returns.
        from datetime import timezone
        assert prov.raw_value == "15-01-2026"
        assert prov.normalized_value == datetime(2026, 1, 15, tzinfo=timezone.utc).isoformat()

    def test_missing_cell_position_falls_back_per_field(self):
        """When `cells` is provided but a particular position is
        `None`, only that field falls back to the legacy shape —
        other fields still carry their cell evidence."""
        cells = [[
            _cell("Activity X", source_field="name",
                  ocr_confidence=0.95),
            None,  # planned_start has no cell — legacy fallback
            _cell("20-01-2026", source_field="planned_finish",
                  ocr_confidence=0.85),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["Activity X", "15-01-2026", "20-01-2026"]],
            cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        acts = schedule.activities
        assert len(acts) == 1
        name_prov = acts[0].provenance["name"]
        assert name_prov.ocr_confidence == 0.95
        start_prov = acts[0].provenance["planned_start"]
        assert start_prov.ocr_confidence is None  # fell back
        finish_prov = acts[0].provenance["planned_finish"]
        assert finish_prov.ocr_confidence == 0.85  # cell evidence

    def test_no_fields_mapped_uses_row_fallback(self):
        """If no fields have column mappings, the legacy `_row`
        Provenance is the only entry — preserves pre-TL-1.4 behaviour
        for unrecognized schedules."""
        extracted = _extracted(
            headers=["unknown_col"],
            rows=[["some value"]],
            cells=[[_cell("some value", source_field="unknown_col")]],
        )
        rec = _recognition({})  # no fields mapped
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        acts = schedule.activities
        # No fields mapped → row skipped (no dates).
        # The single-row schedule has no activities and `_row` is
        # therefore not emitted either. Pin the no-throw invariant.
        assert acts == []


# ---------------------------------------------------------------------------
# Text-layer cells (TL-1.3) — unrated, ocr_confidence=None
# ---------------------------------------------------------------------------

class TestTextLayerCellsThreading:
    def test_text_layer_cell_threads_with_none_confidence(self):
        """Text-layer cells from `_make_textlayer_cell` carry
        `extraction_method="ocr_text_layer"` and `ocr_confidence=None`.
        Provenance must carry those values verbatim — the unrated
        path is a load-bearing distinction (brief §45, ADR-011)."""
        cells = [[
            _cell("X", source_field="name",
                  extraction_method="ocr_table", ocr_confidence=0.95),
            _cell("15-01-2026", source_field="planned_start",
                  extraction_method="ocr_text_layer",
                  ocr_confidence=None, page_number=2),
            _cell("20-01-2026", source_field="planned_finish",
                  extraction_method="ocr_table"),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["X", "15-01-2026", "20-01-2026"]], cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance["planned_start"]
        assert prov.ocr_confidence is None  # None, not 0.0 or 1.0
        assert prov.extraction_method == "ocr_text_layer"
        assert prov.page_number == 2

    def test_ocr_table_vs_text_layer_distinction_preserved(self):
        """Two fields from the same row, different extraction paths.
        Each carries its own provenance hint."""
        cells = [[
            _cell("X", source_field="name",
                  extraction_method="ocr_table", ocr_confidence=0.95),
            _cell("15-01-2026", source_field="planned_start",
                  extraction_method="ocr_text_layer",
                  ocr_confidence=None),
            _cell("20-01-2026", source_field="planned_finish",
                  extraction_method="ocr_table", ocr_confidence=0.85),
        ]]
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["X", "15-01-2026", "20-01-2026"]], cells=cells,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        acts = schedule.activities
        assert acts[0].provenance["name"].extraction_method == "ocr_table"
        assert acts[0].provenance["name"].ocr_confidence == 0.95
        assert acts[0].provenance["planned_start"].extraction_method == "ocr_text_layer"
        assert acts[0].provenance["planned_start"].ocr_confidence is None
        assert acts[0].provenance["planned_finish"].extraction_method == "ocr_table"
        assert acts[0].provenance["planned_finish"].ocr_confidence == 0.85


# ---------------------------------------------------------------------------
# Direct unit tests for `_build_field_provenance`
# ---------------------------------------------------------------------------

class TestBuildFieldProvenanceHelper:
    def test_helper_carries_cell_evidence(self):
        rec = _recognition({"name": "name"})
        cell = _cell("X", ocr_confidence=0.7, page_number=2,
                    bounding_box=[0, 0, 1, 0, 1, 1, 0, 1],
                    source_field="name")
        from ingestion.normalization.engine import _build_field_provenance
        prov = _build_field_provenance(
            "name", 0, raw_value="X", normalized_value="X",
            recognition=rec, cells=[[cell]], headers=["name"],
            filename="x.pdf",
        )
        assert isinstance(prov, Provenance)
        assert prov.ocr_confidence == 0.7
        assert prov.page_number == 2
        assert prov.bounding_box == [0, 0, 1, 0, 1, 1, 0, 1]
        assert prov.source_document == "synthetic.pdf"
        assert prov.extraction_method == "ocr_table"
        assert prov.raw_value == "X"
        assert prov.normalized_value == "X"
        assert prov.source_field == "name"
        assert prov.source_row == 0

    def test_helper_falls_back_when_cell_is_none(self):
        rec = _recognition({"name": "name"})
        from ingestion.normalization.engine import _build_field_provenance
        # cells=None → legacy fallback (four-field + raw/normalized).
        # TL-1.5: when no cell exists, the fallback records the
        # filename as `source_document` (we still know which file
        # the row came from, even when no cell evidence is
        # available) but `ocr_confidence` / `page_number` /
        # `bounding_box` stay `None` — never fabricated.
        prov = _build_field_provenance(
            "name", 0, raw_value="X", normalized_value="X",
            recognition=rec, cells=None, headers=["name"],
            filename="x.pdf",
        )
        assert prov.ocr_confidence is None
        assert prov.page_number is None
        assert prov.bounding_box is None
        assert prov.source_document == "x.pdf"
        assert prov.extraction_method == "unknown"
        assert prov.raw_value == "X"
        assert prov.normalized_value == "X"

    def test_helper_never_fabricates_confidence_for_missing_cell(self):
        """Defence-in-depth: even with cells provided, if the cell at
        `(row_idx, col_idx)` is `None`, the helper must NOT
        fabricate a confidence. It must fall back to None and the
        'unknown' extraction_method sentinel."""
        rec = _recognition({"name": "name"})
        from ingestion.normalization.engine import _build_field_provenance
        prov = _build_field_provenance(
            "name", 0, raw_value="X", normalized_value="X",
            recognition=rec, cells=[[None]], headers=["name"],
            filename="x.pdf",
        )
        assert prov.ocr_confidence is None
        assert prov.extraction_method == "unknown"


# ---------------------------------------------------------------------------
# AC4 (end-to-end) — harness compare covers the existing fixtures.
# This file pins the model-level invariant the harness relies on.
# ---------------------------------------------------------------------------

class TestExistingFixturesStillWork:
    """The 8 synthetic fixtures in `tests/trust/fixtures/` already go
    through the harness runner and are pinned by `harness compare`. That
    is the canonical end-to-end AC4 check. This class adds a
    model-level check that does NOT touch the fixtures: when `cells`
    is absent (which is what the legacy fixtures look like), the
    Provenance shape is unchanged from pre-TL-1.4 (apart from the new
    `raw_value` / `normalized_value` fields, which the harness doesn't
    snapshot)."""

    def test_no_cells_no_raw_value_set_to_none_consistently(self):
        """TL-1.5: even when cells aren't available, Provenance is
        populated for every critical field that has a value. The
        legacy fallback still sets `raw_value` and `normalized_value`
        (so AC2 always holds), and the OCR-specific fields stay
        `None` — confirming no fabricated evidence is smuggled in
        when cells aren't available. Derived fields carry
        `extraction_method="derived"`; non-derived fields carry
        `"unknown"`."""
        extracted = _extracted(
            headers=["name", "planned_start", "planned_finish"],
            rows=[["Activity X", "15-01-2026", "20-01-2026"]],
            cells=None,
        )
        rec = _recognition({
            "name": "name", "planned_start": "planned_start",
            "planned_finish": "planned_finish",
        })
        engine = NormalizationEngine()
        schedule = engine.normalize(extracted, rec, "PDF", "x.pdf")
        prov = schedule.activities[0].provenance
        for field_prov in prov.values():
            assert field_prov.ocr_confidence is None
            assert field_prov.page_number is None
            assert field_prov.bounding_box is None
            # TL-1.5: derived fields carry `extraction_method="derived"`,
            # read-but-unreadable fields carry `"unknown"`. Both are
            # honest — neither fabricates a measurement.
            assert field_prov.extraction_method in ("unknown", "derived")
