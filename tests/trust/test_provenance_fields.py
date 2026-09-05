"""Tests for the extended Provenance model (TL-1.1).

Encodes every acceptance criterion from
`changes/trust-layer/plan/phase-1-provenance.md` (TL-1.1) as a pytest:

- AC1: All new fields optional with safe defaults; existing construction
  sites still valid.
- AC2: `pytest tests/test_nusf_normalization.py -q` stays green with no
  source changes there. (Run that suite separately; this file focuses on
  the model-level ACs and does not duplicate the integration check.)
- AC3: A test asserts `Provenance()` with only the old fields still
  constructs. (Today the old fields are `source_field`, `source_row`,
  `is_ai_inferred`, `confidence`. A `Provenance(source_field="X")` must
  succeed and the new fields must all default cleanly.)
- AC4: `harness compare` shows no diff. (Run as a separate command;
  this file asserts the model-level invariant that the harness's
  snapshot relies on: every previously-storable Provenance still stores
  byte-identically under Pydantic's default JSON encoding.)

Discipline tests (beyond the four ACs) pin the load-bearing `None`
sentinel on `ocr_confidence` and the additive-only contract: removing or
renaming any field in this module must trip a regression test, so a
future task cannot silently break the additive-schema rule (D3).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ingestion.models.nusf import Provenance


# ---------------------------------------------------------------------------
# AC1 + AC3 — old construction sites still valid; new fields optional
# ---------------------------------------------------------------------------

class TestProvenanceConstructsWithOldFieldsOnly:
    """A pre-TL-1.1 `Provenance(source_field="X")` must still construct,
    and the new fields must all default cleanly. This is the additive-only
    invariant (D3) — Phase 2, 7, 9 will rely on legacy sessions loading
    with provenance rows that pre-date these fields."""

    def test_minimal_old_construction_succeeds(self):
        """Pre-TL-1.1 minimal form: only `source_field` (the original
        required field). All other original fields default; all new
        fields default."""
        p = Provenance(source_field="Activity Name")
        assert p.source_field == "Activity Name"
        # Original optional fields
        assert p.source_row is None
        assert p.is_ai_inferred is False
        assert p.column_mapping_confidence == 1.0
        # New TL-1.1 fields, all defaulted
        assert p.raw_value is None
        assert p.normalized_value is None
        assert p.ocr_confidence is None
        assert p.page_number is None
        assert p.bounding_box is None
        assert p.source_document is None
        assert p.extraction_method == "unknown"

    def test_full_old_construction_still_works(self):
        """The full pre-TL-1.1 form (all four original fields supplied)
        still constructs and all new fields still default."""
        p = Provenance(
            source_field="Activity Name",
            source_row=12,
            is_ai_inferred=True,
            column_mapping_confidence=0.67,
        )
        assert p.source_field == "Activity Name"
        assert p.source_row == 12
        assert p.is_ai_inferred is True
        assert p.column_mapping_confidence == 0.67
        # New fields still default
        assert p.raw_value is None
        assert p.normalized_value is None
        assert p.ocr_confidence is None
        assert p.page_number is None
        assert p.bounding_box is None
        assert p.source_document is None
        assert p.extraction_method == "unknown"


# ---------------------------------------------------------------------------
# New fields are individually constructable and respect their types
# ---------------------------------------------------------------------------

class TestNewFieldsAreAdditive:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"raw_value": "2026-01-15"},
            {"normalized_value": "2026-01-15T00:00:00"},
            {"ocr_confidence": 0.95},
            {"ocr_confidence": 0.0},
            {"page_number": 3},
            {"bounding_box": [0.0, 0.0, 100.0, 0.0, 100.0, 20.0, 0.0, 20.0]},
            {"source_document": "schedule.pdf"},
            {"extraction_method": "ocr_table"},
            {"extraction_method": "csv_cell"},
            {"extraction_method": "derived"},
        ],
    )
    def test_each_new_field_round_trips(self, kwargs):
        p = Provenance(source_field="x", **kwargs)
        for k, v in kwargs.items():
            assert getattr(p, k) == v


# ---------------------------------------------------------------------------
# Discipline: the `None` sentinel on ocr_confidence is load-bearing.
# ---------------------------------------------------------------------------

class TestOcrConfidenceNoneSemantics:
    """Brief §6 + the TL-1.2 Do-not rule: `ocr_confidence=None` means
    'not applicable', never 'unknown, assume good'. The model must
    accept None without coercion, and must reject a value outside
    [0.0, 1.0] if one is provided."""

    def test_none_is_accepted_and_preserved(self):
        """Default is None; explicitly passing None is preserved."""
        assert Provenance(source_field="x").ocr_confidence is None
        assert Provenance(source_field="x", ocr_confidence=None).ocr_confidence is None

    def test_out_of_range_rejected(self):
        """A value outside [0.0, 1.0] is invalid even if not None."""
        with pytest.raises(ValidationError):
            Provenance(source_field="x", ocr_confidence=1.5)
        with pytest.raises(ValidationError):
            Provenance(source_field="x", ocr_confidence=-0.01)

    def test_boundary_values_accepted(self):
        """0.0 and 1.0 are the inclusive bounds; both must construct."""
        assert Provenance(source_field="x", ocr_confidence=0.0).ocr_confidence == 0.0
        assert Provenance(source_field="x", ocr_confidence=1.0).ocr_confidence == 1.0

    def test_legacy_construction_does_not_invent_a_confidence(self):
        """Defence-in-depth: a `Provenance(source_field="x")` must NOT
        default `ocr_confidence` to 1.0 or 0.0. The only acceptable
        default for a non-OCR source is None. This is the same
        'confidently wrong' failure the brief exists to prevent."""
        p = Provenance(source_field="x")
        assert p.ocr_confidence is None
        # And: it must not silently coerce to 0 or 1 either.
        assert p.ocr_confidence not in (0.0, 1.0)


# ---------------------------------------------------------------------------
# Discipline: bounding_box and page_number accept the documented shapes.
# ---------------------------------------------------------------------------

class TestGeometryAndPageFields:
    def test_page_number_must_be_positive(self):
        """Page 0 is not a page; reject it."""
        with pytest.raises(ValidationError):
            Provenance(source_field="x", page_number=0)
        with pytest.raises(ValidationError):
            Provenance(source_field="x", page_number=-1)

    def test_bounding_box_default_is_none(self):
        assert Provenance(source_field="x").bounding_box is None

    def test_bounding_box_accepts_flat_polygon(self):
        """Azure's `boundingRegions[].polygon` is a flat list of floats
        (8 numbers for a quadrilateral). The model accepts any list; the
        shape is not enforced here because TL-1.2 / TL-9.1 own geometry
        validation."""
        polygon = [10.0, 20.0, 110.0, 20.0, 110.0, 40.0, 10.0, 40.0]
        p = Provenance(source_field="x", bounding_box=polygon)
        assert p.bounding_box == polygon


# ---------------------------------------------------------------------------
# Discipline: extraction_method enum stability.
# ---------------------------------------------------------------------------

class TestExtractionMethod:
    def test_default_is_unknown(self):
        """`unknown` is the canonical 'not yet classified' value per
        TL-1.5. Pre-TL-1.5 code that never set this field will read
        `unknown` after this change — flagging those rows for the
        TL-1.5 cleanup pass without breaking them."""
        assert Provenance(source_field="x").extraction_method == "unknown"

    def test_canonical_values_round_trip(self):
        """All canonical values from the spec must round-trip. Adding
        new methods here pins the public vocabulary; future tasks can
        extend it but should not silently change the existing set."""
        canonical = [
            "ocr_table",
            "ocr_text_layer",
            "csv_cell",
            "excel_cell",
            "mpp_field",
            "mspdi_field",
            "ai_inferred",
            "derived",
            "unknown",
        ]
        for method in canonical:
            p = Provenance(source_field="x", extraction_method=method)
            assert p.extraction_method == method

    def test_arbitrary_string_accepted(self):
        """The field is a `str`, not a strict enum — extension is
        intentionally cheap. TL-1.5 is the right place to tighten the
        vocabulary; here we just confirm extensibility does not break
        downstream consumers."""
        p = Provenance(source_field="x", extraction_method="future_method_v2")
        assert p.extraction_method == "future_method_v2"


# ---------------------------------------------------------------------------
# Discipline: the model is JSON-serialisable; legacy payloads still load.
# ---------------------------------------------------------------------------

class TestRoundTripCompatibility:
    """The D3 invariant (additive schema, regenerate on demand) depends
    on every Provenance that was ever persisted still loading under the
    new schema. Round-trip through JSON: dump → load → re-dump, and
    the bytes must match."""

    def test_minimal_round_trip(self):
        p = Provenance(source_field="x")
        d1 = p.model_dump_json()
        p2 = Provenance.model_validate_json(d1)
        d2 = p2.model_dump_json()
        assert d1 == d2

    def test_fully_populated_round_trip(self):
        p = Provenance(
            source_field="Activity Name",
            source_row=12,
            is_ai_inferred=True,
            column_mapping_confidence=0.67,
            raw_value="2026-01-15",
            normalized_value="2026-01-15T00:00:00",
            ocr_confidence=0.91,
            page_number=3,
            bounding_box=[0.0, 0.0, 100.0, 0.0, 100.0, 20.0, 0.0, 20.0],
            source_document="schedule.pdf",
            extraction_method="ocr_table",
        )
        d1 = p.model_dump_json()
        p2 = Provenance.model_validate_json(d1)
        d2 = p2.model_dump_json()
        assert d1 == d2
        assert p2.ocr_confidence == 0.91
        assert p2.bounding_box == [0.0, 0.0, 100.0, 0.0, 100.0, 20.0, 0.0, 20.0]

    def test_legacy_payload_without_new_fields_loads(self):
        """Simulate a row persisted before TL-1.1 lands. The legacy
        schema has only the four original fields. The new model must
        load it cleanly with all new fields defaulting."""
        legacy_json = (
            '{"source_field":"Activity Name",'
            '"source_row":12,'
            '"is_ai_inferred":false,'
            '"column_mapping_confidence":1.0}'
        )
        p = Provenance.model_validate_json(legacy_json)
        assert p.source_field == "Activity Name"
        assert p.source_row == 12
        assert p.is_ai_inferred is False
        assert p.column_mapping_confidence == 1.0
        assert p.raw_value is None
        assert p.normalized_value is None
        assert p.ocr_confidence is None
        assert p.page_number is None
        assert p.bounding_box is None
        assert p.source_document is None
        assert p.extraction_method == "unknown"
