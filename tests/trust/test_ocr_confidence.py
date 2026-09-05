"""Tests for TL-1.2 — per-cell OCR confidence + geometry capture.

Encodes every acceptance criterion from
`changes/trust-layer/plan/phase-1-provenance.md` (TL-1.2) as a pytest:

- AC1: each returned cell carries `ocr_confidence`, `page_number`,
  `bounding_box` (and `spans`).
- AC2: cell confidence is the **minimum** of its constituent word
  confidences, not the mean.
- AC3: unresolvable spans yield `None`, and a test asserts this
  specifically. Specifically: spans resolve to no words, no spans at
  all, or every overlapping word omitted its confidence.
- AC4: existing consumers of `_parse_tables` are unaffected. The
  existing key shape on every cell and on the table envelope must be
  preserved exactly. (The harness `compare` runner is the canonical
  end-to-end check for this; this test pins the model-level invariant.)

Tests drive `AzureDocumentIntelligence._parse_tables` directly against
synthetic recorded Azure responses (no live API calls, per the plan's
"recorded Azure response fixture" requirement).
"""
from __future__ import annotations

import pytest

from src.azure_ocr import AzureDocumentIntelligence


# ---------------------------------------------------------------------------
# Recorded-Azure-response fixtures
#
# These are minimal but realistic shapes. The spans, boundingRegions, and
# word confidences are chosen so each test's assertion has a clear
# expected answer.
# ---------------------------------------------------------------------------

def _word(text, confidence, offset, length):
    return {
        "text": text,
        "confidence": confidence,
        "span": {"offset": offset, "length": length},
    }


def _cell(
    row, col, content,
    *,
    span_offset, span_length,
    page_number=1, polygon=None,
    row_span=1, col_span=1, kind="content",
):
    cell = {
        "rowIndex": row,
        "columnIndex": col,
        "content": content,
        "rowSpan": row_span,
        "columnSpan": col_span,
        "kind": kind,
        "spans": [{"offset": span_offset, "length": span_length}],
    }
    if polygon is not None:
        cell["boundingRegions"] = [
            {"pageNumber": page_number, "polygon": polygon},
        ]
    return cell


def _table(
    *,
    row_count, col_count,
    cells, page_number=1,
    table_polygon=None,
):
    table = {
        "rowCount": row_count,
        "columnCount": col_count,
        "cells": cells,
    }
    if table_polygon is not None:
        table["boundingRegions"] = [
            {"pageNumber": page_number, "polygon": table_polygon},
        ]
    return table


def _response(*, content, tables, pages):
    return {"analyzeResult": {"content": content, "tables": tables, "pages": pages}}


def _make_instance():
    """Construct an instance without going through the Azure credential
    check. `_parse_tables` and the confidence helpers are static / do
    not touch `self`."""
    # Bypass `__init__` — these tests exercise parsing logic only.
    inst = AzureDocumentIntelligence.__new__(AzureDocumentIntelligence)
    return inst


# ---------------------------------------------------------------------------
# AC1 — each cell carries the four new keys (and `spans`)
# ---------------------------------------------------------------------------

class TestCellCarriesEvidenceKeys:
    @pytest.fixture
    def parsed(self):
        words = [
            _word("Activity", 0.99, 0, 8),
            _word("2026-01-15", 0.95, 9, 10),
            _word("EL-Cable", 0.91, 20, 8),
        ]
        cells = [
            _cell(0, 0, "Activity",
                  span_offset=0, span_length=8,
                  page_number=1, polygon=[0.0, 0.0, 50.0, 0.0, 50.0, 20.0, 0.0, 20.0]),
            _cell(0, 1, "2026-01-15",
                  span_offset=9, span_length=10,
                  page_number=1, polygon=[50.0, 0.0, 100.0, 0.0, 100.0, 20.0, 50.0, 20.0]),
            _cell(0, 2, "EL-Cable",
                  span_offset=20, span_length=8,
                  page_number=1, polygon=[100.0, 0.0, 150.0, 0.0, 150.0, 20.0, 100.0, 20.0]),
        ]
        table = _table(
            row_count=1, col_count=3, cells=cells,
            page_number=1, table_polygon=[0.0, 0.0, 150.0, 0.0, 150.0, 20.0, 0.0, 20.0],
        )
        response = _response(
            content="Activity 2026-01-15 EL-Cable",
            tables=[table],
            pages=[{"pageNumber": 1, "words": words}],
        )
        return _make_instance()._parse_tables(response, "synthetic.pdf")

    def test_each_cell_has_the_new_keys(self, parsed):
        cell = parsed[0]["cells"][0]
        for key in ("spans", "page_number", "bounding_box", "ocr_confidence"):
            assert key in cell, f"cell missing required TL-1.2 key {key!r}"

    def test_spans_carries_verbatim_offsets(self, parsed):
        cells = parsed[0]["cells"]
        assert cells[0]["spans"] == [{"offset": 0, "length": 8}]
        assert cells[1]["spans"] == [{"offset": 9, "length": 10}]
        assert cells[2]["spans"] == [{"offset": 20, "length": 8}]

    def test_page_number_is_int(self, parsed):
        for cell in parsed[0]["cells"]:
            assert cell["page_number"] == 1
            assert isinstance(cell["page_number"], int)

    def test_bounding_box_is_polygon_list(self, parsed):
        cells = parsed[0]["cells"]
        assert cells[0]["bounding_box"] == [0.0, 0.0, 50.0, 0.0, 50.0, 20.0, 0.0, 20.0]
        assert cells[1]["bounding_box"] == [50.0, 0.0, 100.0, 0.0, 100.0, 20.0, 50.0, 20.0]
        # Polygon is a list; shape is not enforced here (TL-9.1 owns
        # geometry validation, per ADR-009).


# ---------------------------------------------------------------------------
# AC2 — cell confidence is the MINIMUM of word confidences
# ---------------------------------------------------------------------------

class TestConfidenceIsMin:
    def test_min_among_mixed_confidences(self):
        """A cell spanning three words with confidences 0.99 / 0.71 /
        0.85 must report 0.71 — the worst one. Averaging would hide
        the single misread digit."""
        words = [
            _word("Activity", 0.99, 0, 8),
            _word("2026-01-15", 0.71, 9, 10),  # the misread date
            _word("EL-Cable", 0.85, 20, 8),
        ]
        cells = [
            _cell(0, 0, "Activity 2026-01-15 EL-Cable",
                  span_offset=0, span_length=28,
                  page_number=1, polygon=[0.0, 0.0, 200.0, 0.0, 200.0, 20.0, 0.0, 20.0]),
        ]
        table = _table(row_count=1, col_count=1, cells=cells,
                       page_number=1, table_polygon=[0.0, 0.0, 200.0, 0.0, 200.0, 20.0, 0.0, 20.0])
        response = _response(
            content="Activity 2026-01-15 EL-Cable",
            tables=[table],
            pages=[{"pageNumber": 1, "words": words}],
        )
        parsed = _make_instance()._parse_tables(response, "synthetic.pdf")
        assert parsed[0]["cells"][0]["ocr_confidence"] == 0.71

    def test_min_across_multiple_spans(self):
        """A cell can carry multiple spans (e.g. if its content is
        non-contiguous). The min must be taken across ALL spans, not
        per-span."""
        words = [
            _word("A", 0.99, 0, 1),
            _word("B", 0.60, 5, 1),
            _word("C", 0.88, 10, 1),
        ]
        cells = [
            _cell(0, 0, "A B C",
                  span_offset=0, span_length=11,
                  page_number=1, polygon=[0.0, 0.0, 50.0, 0.0, 50.0, 20.0, 0.0, 20.0]),
        ]
        # Override the cell to have multiple spans.
        cells[0]["spans"] = [
            {"offset": 0, "length": 1},
            {"offset": 5, "length": 1},
            {"offset": 10, "length": 1},
        ]
        table = _table(row_count=1, col_count=1, cells=cells,
                       page_number=1, table_polygon=[0.0, 0.0, 50.0, 0.0, 50.0, 20.0, 0.0, 20.0])
        response = _response(
            content="A B C",
            tables=[table],
            pages=[{"pageNumber": 1, "words": words}],
        )
        parsed = _make_instance()._parse_tables(response, "synthetic.pdf")
        assert parsed[0]["cells"][0]["ocr_confidence"] == 0.60

    def test_single_word_cell_returns_that_words_confidence(self):
        words = [_word("X", 0.77, 0, 1)]
        cells = [_cell(0, 0, "X", span_offset=0, span_length=1)]
        table = _table(row_count=1, col_count=1, cells=cells,
                       page_number=1, table_polygon=[0.0, 0.0, 10.0, 0.0, 10.0, 20.0, 0.0, 20.0])
        response = _response(content="X", tables=[table],
                             pages=[{"pageNumber": 1, "words": words}])
        parsed = _make_instance()._parse_tables(response, "x.pdf")
        assert parsed[0]["cells"][0]["ocr_confidence"] == 0.77


# ---------------------------------------------------------------------------
# AC3 — unresolvable spans yield None (never 1.0)
# ---------------------------------------------------------------------------

class TestUnresolvableYieldsNone:
    def test_no_spans_on_cell_yields_none(self):
        """A cell with no `spans` key has no resolvable confidence.
        Must be None — never the default 1.0."""
        words = [_word("X", 0.50, 0, 1)]
        cells = [{
            "rowIndex": 0, "columnIndex": 0,
            "content": "X", "rowSpan": 1, "columnSpan": 1, "kind": "content",
            # deliberately no `spans`
            "boundingRegions": [{"pageNumber": 1, "polygon": [0.0]*8}],
        }]
        table = _table(row_count=1, col_count=1, cells=cells,
                       page_number=1, table_polygon=[0.0]*8)
        response = _response(content="X", tables=[table],
                             pages=[{"pageNumber": 1, "words": words}])
        parsed = _make_instance()._parse_tables(response, "x.pdf")
        assert parsed[0]["cells"][0]["ocr_confidence"] is None, (
            "a cell with no spans must yield None; "
            "defaulting to 1.0 is the failure mode TL-1.2 explicitly bans."
        )

    def test_spans_resolve_to_no_words_yields_none(self):
        """A cell whose spans do not overlap any word has nothing to
        measure. Must be None."""
        # Word is at offset 100, but the cell's span is at offset 0.
        words = [_word("Y", 0.95, 100, 1)]
        cells = [_cell(0, 0, "Y", span_offset=0, span_length=1)]
        table = _table(row_count=1, col_count=1, cells=cells,
                       page_number=1, table_polygon=[0.0]*8)
        response = _response(content="Y", tables=[table],
                             pages=[{"pageNumber": 1, "words": words}])
        parsed = _make_instance()._parse_tables(response, "y.pdf")
        assert parsed[0]["cells"][0]["ocr_confidence"] is None

    def test_overlapping_words_without_confidence_yield_none(self):
        """A cell whose overlapping words all omit `confidence` has no
        value to take a min of. Must be None — never 0.0, never 1.0."""
        words = [
            {"text": "Z", "span": {"offset": 0, "length": 1}},  # no confidence
            {"text": "W", "span": {"offset": 2, "length": 1}},  # no confidence
        ]
        cells = [_cell(0, 0, "Z W", span_offset=0, span_length=3)]
        table = _table(row_count=1, col_count=1, cells=cells,
                       page_number=1, table_polygon=[0.0]*8)
        response = _response(content="Z W", tables=[table],
                             pages=[{"pageNumber": 1, "words": words}])
        parsed = _make_instance()._parse_tables(response, "z.pdf")
        assert parsed[0]["cells"][0]["ocr_confidence"] is None

    def test_no_words_anywhere_yields_none(self):
        """An Azure response with no `words[]` at all (e.g. text-only
        page that was not OCR-scanned) leaves every cell unresolvable.
        Must be None."""
        cells = [_cell(0, 0, "X", span_offset=0, span_length=1)]
        table = _table(row_count=1, col_count=1, cells=cells,
                       page_number=1, table_polygon=[0.0]*8)
        response = _response(
            content="X", tables=[table],
            pages=[{"pageNumber": 1}],  # no `words` key at all
        )
        parsed = _make_instance()._parse_tables(response, "x.pdf")
        assert parsed[0]["cells"][0]["ocr_confidence"] is None

    def test_none_is_never_coerced_to_one(self):
        """Defence-in-depth: in every unresolvable case above, the
        cell's ocr_confidence must NOT be 1.0 (or 0.0). Pin both."""
        words = []  # no words
        cells = [_cell(0, 0, "X", span_offset=0, span_length=1)]
        table = _table(row_count=1, col_count=1, cells=cells,
                       page_number=1, table_polygon=[0.0]*8)
        response = _response(content="X", tables=[table],
                             pages=[{"pageNumber": 1, "words": words}])
        parsed = _make_instance()._parse_tables(response, "x.pdf")
        confidence = parsed[0]["cells"][0]["ocr_confidence"]
        assert confidence is None
        assert confidence not in (0.0, 1.0)


# ---------------------------------------------------------------------------
# AC4 — existing key shape preserved
# ---------------------------------------------------------------------------

class TestExistingShapePreserved:
    """The harness `compare` runner is the canonical end-to-end check
    for "existing consumers are unaffected"; this class pins the
    model-level invariant that the runner relies on."""

    @pytest.fixture
    def parsed_with_evidence(self):
        words = [_word("X", 0.80, 0, 1)]
        cells = [_cell(0, 0, "X", span_offset=0, span_length=1)]
        table = _table(row_count=1, col_count=1, cells=cells,
                       page_number=1, table_polygon=[0.0]*8)
        response = _response(content="X", tables=[table],
                             pages=[{"pageNumber": 1, "words": words}])
        return _make_instance()._parse_tables(response, "x.pdf")

    def test_cell_keeps_all_pre_tl_1_2_keys(self, parsed_with_evidence):
        cell = parsed_with_evidence[0]["cells"][0]
        for key in ("content", "row", "col", "row_span", "col_span", "kind"):
            assert key in cell, f"existing key {key!r} dropped by TL-1.2"

    def test_table_envelope_keeps_all_keys(self, parsed_with_evidence):
        table = parsed_with_evidence[0]
        for key in (
            "table_id", "row_count", "column_count",
            "page_numbers", "rows", "cells", "has_merged_cells",
        ):
            assert key in table, f"existing table-level key {key!r} dropped"

    def test_grid_merge_logic_still_runs(self):
        """A merged cell (rowSpan/columnSpan > 1) must still produce the
        `^...` placeholder in the internal grid, and that placeholder
        must still be stripped from `simple_rows` by the existing
        filter (`not cell["content"].startswith("^")`). TL-1.2 must not
        have broken that path. The merge spec itself (`row_span`,
        `col_span`) must still round-trip on the cell record."""
        words = [_word("MERGED", 0.50, 0, 6)]
        cells = [_cell(
            0, 0, "MERGED",
            span_offset=0, span_length=6,
            row_span=2, col_span=2,
        )]
        table = _table(row_count=3, col_count=3, cells=cells,
                       page_number=1, table_polygon=[0.0]*8)
        response = _response(content="MERGED", tables=[table],
                             pages=[{"pageNumber": 1, "words": words}])
        parsed = _make_instance()._parse_tables(response, "merged.pdf")
        rows = parsed[0]["rows"]
        cells_out = parsed[0]["cells"]

        # The merge source keeps its content; merge targets show as
        # empty in `simple_rows` because the existing `^` filter
        # strips the placeholder. If TL-1.2 had broken that filter,
        # these would all be "^MERGED..." strings.
        assert rows[0][0] == "MERGED"
        assert rows[0][1] == ""
        assert rows[1][0] == ""
        assert rows[1][1] == ""

        # The merge spec itself must still round-trip.
        assert cells_out[0]["row_span"] == 2
        assert cells_out[0]["col_span"] == 2

        # And the table envelope still reports merged-cells presence.
        assert parsed[0]["has_merged_cells"] is True


# ---------------------------------------------------------------------------
# Discipline — `_derive_cell_confidence` directly
# ---------------------------------------------------------------------------

class TestDeriveCellConfidenceHelper:
    """Direct unit tests for the static helper. Documents edge cases
    that the integration tests above cover end-to-end."""

    def test_no_spans_returns_none(self):
        assert AzureDocumentIntelligence._derive_cell_confidence(
            cell_spans=[], pages_words=[],
        ) is None

    def test_no_words_returns_none(self):
        assert AzureDocumentIntelligence._derive_cell_confidence(
            cell_spans=[{"offset": 0, "length": 5}],
            pages_words=[],
        ) is None

    def test_disjoint_spans_returns_none(self):
        # Word at offset 100; cell span at 0..5.
        words = [_word("X", 0.99, 100, 1)]
        assert AzureDocumentIntelligence._derive_cell_confidence(
            cell_spans=[{"offset": 0, "length": 5}],
            pages_words=words,
        ) is None

    def test_zero_length_span_yields_none(self):
        """A span of length 0 is degenerate; no word can overlap it."""
        words = [_word("X", 0.99, 0, 5)]
        assert AzureDocumentIntelligence._derive_cell_confidence(
            cell_spans=[{"offset": 0, "length": 0}],
            pages_words=words,
        ) is None

    def test_word_at_boundary_not_counted(self):
        """Word ending exactly where the span begins is not an overlap
        (half-open interval convention)."""
        words = [_word("X", 0.99, 5, 3)]  # 5..8
        # Span is 0..5 — the word's word_start=5 is on the boundary
        # and should NOT be counted.
        result = AzureDocumentIntelligence._derive_cell_confidence(
            cell_spans=[{"offset": 0, "length": 5}],
            pages_words=words,
        )
        assert result is None

    def test_word_with_no_span_skipped(self):
        """Words missing a `span` field are skipped (cannot be matched)."""
        words = [
            {"text": "A", "confidence": 0.99},  # no span
            _word("B", 0.50, 0, 1),  # matches
        ]
        assert AzureDocumentIntelligence._derive_cell_confidence(
            cell_spans=[{"offset": 0, "length": 1}],
            pages_words=words,
        ) == 0.50

    def test_min_is_taken_not_mean(self):
        """Pin the brief's Do-not rule: it must be MIN, not MEAN."""
        words = [
            _word("A", 0.99, 0, 1),
            _word("B", 0.10, 1, 1),
            _word("C", 0.50, 2, 1),
        ]
        # Span covers 0..3, overlapping all three.
        result = AzureDocumentIntelligence._derive_cell_confidence(
            cell_spans=[{"offset": 0, "length": 3}],
            pages_words=words,
        )
        assert result == 0.10  # not the mean (0.53), not the max
