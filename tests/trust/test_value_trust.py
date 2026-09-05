r"""Tests for TL-4.2 — Derive per-value trust state from upstream evidence.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-4-trust-engine.md` (TL-4.2):
- AC1: AI-inferred fields never reach VERIFIED.
- AC2: Exact-read sources (CSV/MPP/MSPDI) are not penalized for having no OCR confidence.
- AC3: Unresolvable OCR spans reduce the state.
- AC4: OCR confidence thresholds use named UNCALIBRATED constants.
"""
from __future__ import annotations

import pytest
from src.trust.engine import TrustEngine
from src.trust.vocabulary import TrustState


class TestValueTrustDerivation:
    def setup_method(self):
        self.engine = TrustEngine()

    def test_ai_inferred_field_never_reaches_verified(self):
        assessment = self.engine.assess_value(
            field_name="planned_start",
            value="2026-01-01",
            is_ai_inferred=True,
        )
        assert assessment.state != TrustState.VERIFIED
        assert assessment.state == TrustState.REVIEW
        assert "AI-inferred" in assessment.reason

    def test_exact_read_source_reaches_verified_without_ocr_conf(self):
        assessment = self.engine.assess_value(
            field_name="source_id",
            value="ACT-101",
            extraction_method="csv",
        )
        assert assessment.state == TrustState.VERIFIED
        assert "Exact-read source" in assessment.reason

    def test_ocr_high_confidence_reaches_verified(self):
        assessment = self.engine.assess_value(
            field_name="planned_start",
            value="2026-01-01",
            provenance={"confidence": 0.98, "method": "tesseract"},
        )
        assert assessment.state == TrustState.VERIFIED

    def test_ocr_amber_confidence_reaches_review(self):
        assessment = self.engine.assess_value(
            field_name="planned_start",
            value="2026-01-01",
            provenance={"confidence": 0.85, "method": "tesseract"},
        )
        assert assessment.state == TrustState.REVIEW

    def test_ocr_low_confidence_reaches_unverified(self):
        assessment = self.engine.assess_value(
            field_name="planned_start",
            value="2026-01-01",
            provenance={"confidence": 0.50, "method": "tesseract"},
        )
        assert assessment.state == TrustState.UNVERIFIED

    def test_unresolvable_ocr_span_yields_unverified(self):
        assessment = self.engine.assess_value(
            field_name="planned_start",
            value="2026-01-01",
            extraction_method="pdf_ocr",
            provenance=None,
        )
        assert assessment.state == TrustState.UNVERIFIED


class TestRealProvenanceObjects:
    """ADR-017: `assess_value`'s Rule 3 previously read `.confidence` off any
    non-dict `provenance` argument, but real `Provenance` objects (post-TL-1.6)
    expose value-level confidence as `.ocr_confidence` — `.confidence` does not
    exist on the model. Every real `Provenance` therefore silently skipped the
    OCR-confidence branch and fell through to "exact-read" `VERIFIED`,
    regardless of how low its actual `ocr_confidence` was. TL-5.1 is the first
    caller to pass real `Provenance` objects into `assess_value`, so this fixes
    the bug before it can produce a confidently-wrong trust state."""

    def setup_method(self):
        self.engine = TrustEngine()

    def test_real_provenance_low_ocr_confidence_is_not_silently_verified(self):
        from ingestion.models.nusf import Provenance

        prov = Provenance(source_field="planned_start", ocr_confidence=0.10, extraction_method="ocr_table")
        assessment = self.engine.assess_value(field_name="planned_start", value="x", provenance=prov)
        assert assessment.state == TrustState.UNVERIFIED
        assert "0.10" in assessment.reason

    def test_real_provenance_high_ocr_confidence_reaches_verified(self):
        from ingestion.models.nusf import Provenance

        prov = Provenance(source_field="planned_start", ocr_confidence=0.99, extraction_method="ocr_table")
        assessment = self.engine.assess_value(field_name="planned_start", value="x", provenance=prov)
        assert assessment.state == TrustState.VERIFIED

    def test_real_provenance_exact_read_reaches_verified_via_canonical_method(self):
        from ingestion.models.nusf import Provenance

        for method in ("csv_cell", "excel_cell", "mpp_field", "mspdi_field"):
            prov = Provenance(source_field="percent_complete", ocr_confidence=None, extraction_method=method)
            assessment = self.engine.assess_value(field_name="percent_complete", value=0.0, provenance=prov)
            assert assessment.state == TrustState.VERIFIED, f"extraction_method={method}"

    def test_real_provenance_ocr_text_layer_with_no_confidence_stays_unverified(self):
        from ingestion.models.nusf import Provenance

        prov = Provenance(source_field="planned_start", ocr_confidence=None, extraction_method="ocr_text_layer")
        assessment = self.engine.assess_value(field_name="planned_start", value="x", provenance=prov)
        assert assessment.state == TrustState.UNVERIFIED
