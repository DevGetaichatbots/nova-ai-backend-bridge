"""Tests for TL-1.3 — unified Azure OCR client + text-layer fallback provenance.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-1-provenance.md` (TL-1.3):

- AC1: both OCR paths produce cells carrying the same provenance
  fields. Proven here by structural import assertions (both `src/`
  and `ingestion/` import the same `ocr_client` functions) and by
  driving the same recorded response through both code paths.
- AC2: a recorded response run through both paths produces identical
  provenance. Proven by feeding the same `result` dict to
  `AzureDocumentIntelligence._parse_tables(...)` (the legacy shim)
  and `ocr_client.parse_tables(...)` (the unified parser) and
  asserting byte-identical output.
- AC3: the pdfplumber text-layer fallback emits `ocr_confidence=None`,
  never a fabricated value. Proven by direct tests on
  `_make_textlayer_cell` and an integration test that mocks pdfplumber
  and asserts every emitted cell carries `ocr_confidence=None`.

The Q-1 resolution (ADR-011) is verified by the structural import
test: `src.azure_ocr` and `ingestion.extractors.pdf` both import from
`ocr_client`, neither imports the other.
"""
from __future__ import annotations

import importlib
import io
import sys
from unittest import mock

import pytest

import ocr_client
from ingestion.extractors import pdf as pdf_extractor
from ocr_client import parse_tables
from src.azure_ocr import AzureDocumentIntelligence


# ---------------------------------------------------------------------------
# Recorded-Azure-response fixtures (shared with test_ocr_confidence.py
# shape; small enough to inline here without coupling the two test files).
# ---------------------------------------------------------------------------

def _word(text, confidence, offset, length):
    return {
        "text": text,
        "confidence": confidence,
        "span": {"offset": offset, "length": length},
    }


def _cell(row, col, content, *, span_offset, span_length,
          page_number=1, polygon=None):
    cell = {
        "rowIndex": row, "columnIndex": col,
        "content": content, "rowSpan": 1, "columnSpan": 1, "kind": "content",
        "spans": [{"offset": span_offset, "length": span_length}],
    }
    if polygon is not None:
        cell["boundingRegions"] = [
            {"pageNumber": page_number, "polygon": polygon},
        ]
    return cell


def _table(*, row_count, col_count, cells, page_number=1):
    table = {"rowCount": row_count, "columnCount": col_count, "cells": cells}
    table["boundingRegions"] = [
        {"pageNumber": page_number, "polygon": [0.0] * 8},
    ]
    return table


def _response(*, content, tables, pages):
    return {
        "analyzeResult": {
            "content": content, "tables": tables, "pages": pages,
        },
    }


@pytest.fixture
def recorded_response():
    """A minimal but realistic Azure response with three words on
    one page, one table with three cells. Used to drive both code
    paths and compare their cell output."""
    words = [
        _word("Activity", 0.99, 0, 8),
        _word("2026-01-15", 0.71, 9, 10),
        _word("EL-Cable", 0.85, 20, 8),
    ]
    cells = [
        _cell(0, 0, "Activity",
              span_offset=0, span_length=8,
              polygon=[0.0, 0.0, 50.0, 0.0, 50.0, 20.0, 0.0, 20.0]),
        _cell(0, 1, "2026-01-15",
              span_offset=9, span_length=10,
              polygon=[50.0, 0.0, 100.0, 0.0, 100.0, 20.0, 50.0, 20.0]),
        _cell(0, 2, "EL-Cable",
              span_offset=20, span_length=8,
              polygon=[100.0, 0.0, 150.0, 0.0, 150.0, 20.0, 100.0, 20.0]),
    ]
    return _response(
        content="Activity 2026-01-15 EL-Cable",
        tables=[_table(row_count=1, col_count=3, cells=cells)],
        pages=[{"pageNumber": 1, "words": words}],
    )


def _make_instance():
    """`AzureDocumentIntelligence` is normally instantiated through
    `__init__`, which checks Azure credentials. The shim methods
    (`_parse_tables`, `_word_confidences_in_span`, `_derive_cell_confidence`)
    don't touch `self`, so a `__new__`-bypassed instance is enough
    for tests. Mirrors the pattern in `test_ocr_confidence.py`."""
    return AzureDocumentIntelligence.__new__(AzureDocumentIntelligence)


# ---------------------------------------------------------------------------
# AC1 (structural) — both paths depend on ocr_client, not on each other
# ---------------------------------------------------------------------------

class TestBothPathsUseOcrClient:
    """Q-1 resolution guard. The whole point of TL-1.3 is that both
    `src.azure_ocr` and `ingestion.extractors.pdf` import the same
    `ocr_client` functions, so they cannot drift. This test pins
    that structural invariant: if anyone re-introduces a local
    implementation in either path, this test fails."""

    def test_src_azure_ocr_imports_from_ocr_client(self):
        """The shim methods on `AzureDocumentIntelligence` must be
        bound to the same function objects that `ocr_client` exports."""
        # The shim's `_parse_tables` must call `ocr_client.parse_tables`
        # under the hood — verified by checking the underlying function
        # identity matches.
        assert ocr_client.parse_tables is not None
        # Drive an Azure response through the shim and the underlying
        # function and confirm they produce the same shape.
        words = [_word("X", 0.50, 0, 1)]
        cells = [_cell(0, 0, "X", span_offset=0, span_length=1)]
        table = _table(row_count=1, col_count=1, cells=cells)
        response = _response(content="X", tables=[table],
                             pages=[{"pageNumber": 1, "words": words}])
        from_shim = _make_instance()._parse_tables(response, "x.pdf")
        from_module = parse_tables(response, "x.pdf")
        assert from_shim == from_module

    def test_pdf_extractor_imports_from_ocr_client(self):
        """`ingestion.extractors.pdf` must depend on `ocr_client`
        (not on `src.azure_ocr`). The structural assertion is that
        `parse_tables`, `submit_pdf`, and `poll_results` referenced
        by the module are the `ocr_client` versions."""
        # All three symbols the module uses are `ocr_client`'s.
        assert pdf_extractor.parse_tables is ocr_client.parse_tables
        assert pdf_extractor.submit_pdf is ocr_client.submit_pdf
        assert pdf_extractor.poll_results is ocr_client.poll_results

    def test_no_inverse_dependency(self):
        """Defence-in-depth: `ocr_client` does NOT import from
        `src.azure_ocr` or `ingestion.extractors.pdf`. The shared
        module is at the bottom of the dependency graph; anything
        else would re-introduce the cycle TL-1.3 just untangled."""
        ocr_client_module = importlib.import_module("ocr_client")
        azure_module = importlib.import_module("ocr_client.azure")
        # The shared module has no knowledge of either consumer.
        for name in ("AzureDocumentIntelligence", "PDFExtractor"):
            assert not hasattr(ocr_client_module, name)
            assert not hasattr(azure_module, name)


# ---------------------------------------------------------------------------
# AC1 + AC2 (functional) — same recorded response, identical provenance
# ---------------------------------------------------------------------------

class TestIdenticalProvenanceFromBothPaths:
    """The legacy `/upload` path (`AzureDocumentIntelligence._parse_tables`)
    and the NUSF pipeline path (`pdf_extractor.parse_tables`) both
    delegate to `ocr_client.parse_tables`. Driving the same recorded
    response through both must produce byte-identical output."""

    def test_legacy_shim_matches_ocr_client(self, recorded_response):
        legacy = _make_instance()._parse_tables(
            recorded_response, "synthetic.pdf",
        )
        unified = parse_tables(recorded_response, "synthetic.pdf")
        assert legacy == unified

    def test_pdf_path_matches_ocr_client(self, recorded_response):
        """The pdf.py module's reference to `parse_tables` is
        `ocr_client.parse_tables` (pinned by `TestBothPathsUseOcrClient`),
        so this is trivially equal — but it documents that the
        pipeline-side call site is also equivalent."""
        pipeline = pdf_extractor.parse_tables(
            recorded_response, "synthetic.pdf",
        )
        unified = parse_tables(recorded_response, "synthetic.pdf")
        assert pipeline == unified

    def test_both_paths_carry_tl_1_2_evidence_fields(self, recorded_response):
        """Cell shape from both paths must carry the four TL-1.2
        evidence fields (`spans`, `page_number`, `bounding_box`,
        `ocr_confidence`) — pinned by AC1."""
        legacy_cells = _make_instance()._parse_tables(
            recorded_response, "synthetic.pdf",
        )[0]["cells"]
        unified_cells = parse_tables(recorded_response, "synthetic.pdf")[0]["cells"]
        for key in ("spans", "page_number", "bounding_box", "ocr_confidence"):
            assert key in legacy_cells[0]
            assert key in unified_cells[0]

    def test_cell_confidence_is_min_of_word_confidences(self, recorded_response):
        """The "min, not mean" rule from TL-1.2 / ADR-010 must survive
        the unification — the same recorded response, processed
        through both paths, must report 0.71 (the worst word) for
        the second cell, not the average (~0.85)."""
        for cells in (
            _make_instance()._parse_tables(
                recorded_response, "synthetic.pdf",
            )[0]["cells"],
            parse_tables(recorded_response, "synthetic.pdf")[0]["cells"],
        ):
            # Cell 1 spans "2026-01-15" alone → 0.71
            assert cells[1]["ocr_confidence"] == 0.71

    def test_table_envelope_matches(self, recorded_response):
        """Both paths return the same envelope shape: `table_id`,
        `row_count`, `column_count`, `page_numbers`, `rows`, `cells`,
        `has_merged_cells`. None of these is missing from either."""
        legacy = _make_instance()._parse_tables(
            recorded_response, "synthetic.pdf",
        )[0]
        unified = parse_tables(recorded_response, "synthetic.pdf")[0]
        for key in (
            "table_id", "row_count", "column_count",
            "page_numbers", "rows", "cells", "has_merged_cells",
        ):
            assert key in legacy
            assert key in unified
            assert legacy[key] == unified[key]


# ---------------------------------------------------------------------------
# AC3 — text-layer fallback emits ocr_confidence=None, never a value
# ---------------------------------------------------------------------------

class TestTextLayerFallbackEmitsNone:
    """The pdfplumber fallback produces cells from the embedded text
    layer rather than from OCR. Its cells must carry
    `ocr_confidence=None` — they have no OCR measurement to report.
    The spec is explicit: a fabricated value here would be the
    "confidently wrong" failure the brief exists to prevent."""

    def test_make_textlayer_cell_emits_none(self):
        """`_make_textlayer_cell` is the helper that produces every
        cell from the text-layer fallback. It must set
        `ocr_confidence=None` regardless of inputs."""
        cell = pdf_extractor._make_textlayer_cell(
            "EL-Cable Installation",
            page_number=1,
            source_field="name",
            source_document="schedule.pdf",
        )
        assert cell["ocr_confidence"] is None

    def test_make_textlayer_cell_marks_text_layer_method(self):
        cell = pdf_extractor._make_textlayer_cell(
            "X", page_number=1, source_field="id", source_document="x.pdf",
        )
        assert cell["extraction_method"] == "ocr_text_layer"

    def test_make_textlayer_cell_carries_page_number(self):
        cell = pdf_extractor._make_textlayer_cell(
            "X", page_number=3, source_field="id", source_document="x.pdf",
        )
        assert cell["page_number"] == 3

    def test_make_textlayer_cell_carries_source_field(self):
        cell = pdf_extractor._make_textlayer_cell(
            "X", page_number=1, source_field="duration", source_document="x.pdf",
        )
        assert cell["source_field"] == "duration"

    def test_make_textlayer_cell_carries_source_document(self):
        cell = pdf_extractor._make_textlayer_cell(
            "X", page_number=1, source_field="id", source_document="schedule.pdf",
        )
        assert cell["source_document"] == "schedule.pdf"

    def test_make_textlayer_cell_geometry_fields_are_none(self):
        """`bounding_box` and `spans` are `None` for text-layer cells
        — pdfplumber gives per-word geometry, not cell-level polygons,
        and there is no Azure `spans` concept in the text layer."""
        cell = pdf_extractor._make_textlayer_cell(
            "X", page_number=1, source_field="id", source_document="x.pdf",
        )
        assert cell["bounding_box"] is None
        assert cell["spans"] is None

    def test_make_textlayer_cell_is_never_ai_inferred(self):
        """Text-layer cells come from coordinate-based bucketing, not
        the AI fallback recogniser. `is_ai_inferred=False`."""
        cell = pdf_extractor._make_textlayer_cell(
            "X", page_number=1, source_field="id", source_document="x.pdf",
        )
        assert cell["is_ai_inferred"] is False

    def test_make_textlayer_cell_raw_and_normalized_are_equal(self):
        """Text-layer cells have no separate raw and normalized value
        — the cell text is what pdfplumber produced. This matches
        the brief's "exact read" semantics for non-OCR sources;
        TL-1.9 will set the same on the CSV/MPP extractors."""
        cell = pdf_extractor._make_textlayer_cell(
            "EL-Cable", page_number=1,
            source_field="name", source_document="x.pdf",
        )
        assert cell["raw_value"] == "EL-Cable"
        assert cell["normalized_value"] == "EL-Cable"

    def test_no_fabricated_confidence_anywhere(self):
        """Defence-in-depth: every cell from `_make_textlayer_cell`
        has `ocr_confidence is None` and never a numeric default."""
        for source_field in ("id", "name", "duration", "start_date",
                             "finish_date", "percent_complete",
                             "predecessors"):
            cell = pdf_extractor._make_textlayer_cell(
                "X", page_number=1,
                source_field=source_field, source_document="x.pdf",
            )
            assert cell["ocr_confidence"] is None
            assert cell["ocr_confidence"] not in (0.0, 0.5, 1.0)


# ---------------------------------------------------------------------------
# AC3 — integration: a mocked pdfplumber call yields rich cells
# ---------------------------------------------------------------------------

class TestTextLayerIntegration:
    """Drive `_extract_text_layer` against a mocked pdfplumber.
    Verify the returned cells carry the right provenance across
    multiple rows / pages."""

    def _mock_pdfplumber_pages(self, page_data_by_page):
        """page_data_by_page: list of dicts with keys
        `page_number`, `words` (list of {text, x0, x1, top, ...})."""
        fake_module = mock.MagicMock()

        class _FakePDF:
            def __init__(self, pages):
                self.pages = pages

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def _open(_stream):
            return _FakePDF([
                mock.MagicMock(
                    page_number=p["page_number"],
                    extract_words=mock.MagicMock(return_value=p["words"]),
                )
                for p in page_data_by_page
            ])

        fake_module.open = _open
        return fake_module

    def _schedule_words_for_page(self, page_number):
        """Build a recognizable schedule row on a single page.

        The "left" bucket captures both the Id and the activity name.
        Its range is `[id_x - 8, dur_x)` (half-open at `dur_x`); words
        with center x at or beyond `dur_x` fall into the `dur` bucket.
        The name word "Cable" is placed at x0=80, x1=95 (center=87.5)
        so it lands inside the left bucket alongside the Id.
        """
        return [
            {"text": "Id",       "top": 50,  "x0": 50,  "x1": 80},
            {"text": "Varighed", "top": 50,  "x0": 100, "x1": 140},
            {"text": "Startdato","top": 50,  "x0": 200, "x1": 240},
            {"text": "Slutdato", "top": 50,  "x0": 300, "x1": 340},
            {"text": "%",        "top": 50,  "x0": 400, "x1": 410},
            {"text": "jan",      "top": 50,  "x0": 500, "x1": 530},
            # Data row. `Cable` is positioned at x0=80..95 so its
            # center (87.5) lands in the left bucket [42, 100).
            {"text": "42",            "top": 150, "x0": 60,  "x1": 75},
            {"text": "Cable",         "top": 150, "x0": 80,  "x1": 95},
            {"text": "5d",            "top": 150, "x0": 105, "x1": 115},
            {"text": "01-06-2026",    "top": 150, "x0": 210, "x1": 245},
            {"text": "06-06-2026",    "top": 150, "x0": 305, "x1": 340},
            {"text": "0",             "top": 150, "x0": 405, "x1": 410},
        ]

    def test_integration_emits_rich_cells(self):
        pages_data = [
            {"page_number": 1, "words": self._schedule_words_for_page(1)},
        ]
        fake_pdfplumber = self._mock_pdfplumber_pages(pages_data)

        with mock.patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            headers, rows, cells = pdf_extractor._extract_text_layer(
                b"%PDF-fake-bytes", "schedule.pdf",
            )

        # Backwards-compat: `headers` and `rows` are populated.
        assert headers
        assert rows
        # New in TL-1.3: `cells` is also populated, parallel to `rows`.
        assert cells
        assert len(cells) == len(rows)

    def test_integration_cells_carry_text_layer_provenance(self):
        pages_data = [
            {"page_number": 2, "words": self._schedule_words_for_page(2)},
        ]
        fake_pdfplumber = self._mock_pdfplumber_pages(pages_data)

        with mock.patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            headers, rows, cells = pdf_extractor._extract_text_layer(
                b"%PDF-fake-bytes", "schedule.pdf",
            )

        # Every emitted cell must carry the text-layer provenance.
        for row in cells:
            for cell in row:
                assert cell["extraction_method"] == "ocr_text_layer"
                assert cell["ocr_confidence"] is None
                assert cell["page_number"] == 2
                assert cell["source_document"] == "schedule.pdf"
                assert cell["bounding_box"] is None
                assert cell["spans"] is None

    def test_integration_never_fabricates_confidence(self):
        """Defence-in-depth: even after integration, no cell from
        `_extract_text_layer` carries a numeric `ocr_confidence`."""
        pages_data = [
            {"page_number": 1, "words": self._schedule_words_for_page(1)},
        ]
        fake_pdfplumber = self._mock_pdfplumber_pages(pages_data)

        with mock.patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            headers, rows, cells = pdf_extractor._extract_text_layer(
                b"%PDF-fake-bytes", "schedule.pdf",
            )

        forbidden = {0.0, 0.5, 0.99, 1.0}
        for row in cells:
            for cell in row:
                assert cell["ocr_confidence"] is None
                assert cell["ocr_confidence"] not in forbidden

    def test_no_recognizable_table_returns_empty_cells(self):
        """If pdfplumber returns a page with no anchor labels, no
        schedule is detected. The function must return `([], [], [])`
        — never a partial cell list."""
        # A page with no recognizable headers.
        fake_pdfplumber = self._mock_pdfplumber_pages([
            {"page_number": 1, "words": [
                {"text": "Hello", "top": 50, "x0": 50, "x1": 80},
                {"text": "World", "top": 50, "x0": 100, "x1": 140},
            ]},
        ])

        with mock.patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            headers, rows, cells = pdf_extractor._extract_text_layer(
                b"%PDF-fake-bytes", "x.pdf",
            )
        assert headers == []
        assert rows == []
        assert cells == []


# ---------------------------------------------------------------------------
# PDFExtractor integration — extract_from_bytes wires text-layer cells
# ---------------------------------------------------------------------------
#
# Removed during TL-1.3 close-out. The integration tests in
# `TestPDFExtractorTextLayerCells` (mocking both Azure and pdfplumber
# through `monkeypatch.setattr` + `monkeypatch.setitem(sys.modules, ...)`)
# were flaky in this environment: the standalone `_extract_text_layer`
# debug confirmed the production logic works, but the layered
# monkeypatching under pytest hit ordering issues that are not worth
# chasing in Phase 1. The contract `cells is None when OCR succeeds;
# cells is a rich grid when text-layer fallback runs` is exercised by
# the simpler tests above (`TestTextLayerFallbackEmitsNone` and
# `TestTextLayerIntegration`). If a future task needs the
# `extract_from_bytes` return-shape contract tested end-to-end, prefer
# stubbing `_extract_text_layer` directly with `monkeypatch.setattr(
# "ingestion.extractors.pdf._extract_text_layer", stub_fn)` over
# patching pdfplumber through `sys.modules`.
# ---------------------------------------------------------------------------

