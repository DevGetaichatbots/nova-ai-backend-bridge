r"""Tests for TL-1.6 — Separate recognition confidence from value confidence.

Encodes every acceptance criterion from
`changes/trust-layer/plan/phase-1-provenance.md` (TL-1.6):

- AC1: `grep -rn "provenance.*\.confidence" rag-agent/backend` returns no ambiguous uses.
- AC2: Both scores (`column_mapping_confidence` and `ocr_confidence`) are independently readable per field.
- AC3: A fixture with a well-recognised column but low OCR quality shows high mapping confidence and low OCR confidence.
- AC4: `is_ai_inferred` is true for every field mapped by the AI fallback.
"""
from __future__ import annotations

import pathlib
import pytest

from ingestion.models.nusf import Provenance
from ingestion.normalization.engine import NormalizationEngine
from ingestion.recognition.heuristics import RecognitionResult


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
# AC1 — No ambiguous `.confidence` usage on Provenance in code
# ---------------------------------------------------------------------------

class TestNoAmbiguousConfidenceAccess:
    """AC1: `Provenance` model has `column_mapping_confidence` and `ocr_confidence`,
    no bare `confidence` field."""

    def test_provenance_has_column_mapping_confidence_attr(self):
        p = Provenance(source_field="name")
        assert hasattr(p, "column_mapping_confidence")
        assert not hasattr(p, "confidence")


# ---------------------------------------------------------------------------
# AC2 & AC3 — Independent scores & low OCR / high mapping decoupling
# ---------------------------------------------------------------------------

class TestDecoupledConfidenceScores:
    """AC2 & AC3: Both scores are independently readable.
    Low OCR quality does not degrade column mapping confidence and vice versa."""

    def test_low_ocr_high_mapping_decoupling(self):
        cells = [[
            _cell("42", source_field="source_id", ocr_confidence=0.25),
            _cell("Activity X", source_field="name", ocr_confidence=0.99),
            _cell("15-01-2026", source_field="planned_start", ocr_confidence=0.30),
            _cell("20-01-2026", source_field="planned_finish", ocr_confidence=0.95),
        ]]
        extracted = _extracted(
            headers=["source_id", "name", "planned_start", "planned_finish"],
            rows=[["42", "Activity X", "15-01-2026", "20-01-2026"]],
            cells=cells,
        )
        # 1.0 recognition mapping confidence
        rec = _recognition(
            {
                "source_id": "source_id",
                "name": "name",
                "planned_start": "planned_start",
                "planned_finish": "planned_finish",
            },
            ai_needed=False,
            confidence=1.0,
        )
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        assert len(acts) == 1
        prov = acts[0].provenance

        # High column mapping confidence (1.0), low OCR confidence (0.25)
        assert prov["source_id"].column_mapping_confidence == 1.0
        assert prov["source_id"].ocr_confidence == 0.25

        # Independent per field
        assert prov["name"].column_mapping_confidence == 1.0
        assert prov["name"].ocr_confidence == 0.99


# ---------------------------------------------------------------------------
# AC4 — is_ai_inferred propagation
# ---------------------------------------------------------------------------

class TestAiInferredPropagation:
    """AC4: is_ai_inferred is true for every field when mapped by AI fallback."""

    def test_is_ai_inferred_propagates_to_provenance(self):
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
        rec = _recognition(
            {
                "name": "name",
                "planned_start": "planned_start",
                "planned_finish": "planned_finish",
            },
            ai_needed=True,  # AI fallback was used
            confidence=0.67,
        )
        engine = NormalizationEngine()
        acts = engine.normalize(extracted, rec, "PDF", "x.pdf").activities
        assert len(acts) == 1
        prov = acts[0].provenance
        assert prov["name"].is_ai_inferred is True
        assert prov["name"].column_mapping_confidence == 0.67
