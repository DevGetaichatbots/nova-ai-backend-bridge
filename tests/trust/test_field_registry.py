"""Tests for TL-1.7 — Field criticality registry.

Encodes every acceptance criterion from
`changes/trust-layer/plan/phase-1-provenance.md` (TL-1.7):

- AC1: Registry covers every field in the NUSF `Activity` model that
       appears in the provenance dict.
- AC2: Each field maps to exactly one criticality.
- AC3: Relationship to the recogniser's `CRITICAL_FIELDS` documented
       in both places (structural / source-text test).
- AC4: Thresholds are hooks with placeholder values, explicitly marked
       UNCALIBRATED; no production threshold value is hard-coded.

Defence-in-depth tests beyond the four ACs:
- `criticality()` raises `KeyError` for unregistered fields.
- `CRITICAL_FIELD_NAMES` and `SECONDARY_FIELD_NAMES` are disjoint.
- `THRESHOLDS` is immutable (frozen dataclass).
- Six specific fields are CRITICAL and match brief §8 §6.
- All THRESHOLDS values are in (0, 1), critical thresholds are higher
  than secondary thresholds (structural sanity, not calibration claim).
"""
from __future__ import annotations

import pathlib
import pytest

from src.trust.fields import (
    Criticality,
    CRITICAL_FIELD_NAMES,
    SECONDARY_FIELD_NAMES,
    THRESHOLDS,
    criticality,
)


# ---------------------------------------------------------------------------
# AC1 — Registry covers every provenance key in the Activity model
# ---------------------------------------------------------------------------

class TestRegistryCoverage:
    """AC1: every field that can appear in Activity.provenance is registered."""

    # The provenance keys used by NormalizationEngine.normalize() as of TL-1.5.
    # When new fields are added to the engine, extend this list and add them
    # to the appropriate set in fields.py.
    KNOWN_PROVENANCE_KEYS = {
        # Critical (brief §8 §6)
        "source_id", "name", "planned_start", "planned_finish",
        "duration_hours", "percent_complete",
        # Secondary — location
        "location_path", "area", "floor", "phase",
        # Secondary — classification
        "discipline", "activity_type", "wbs_code",
        # Secondary — progress / status flags
        "actual_start", "actual_finish",
        "is_late", "inspected_status", "critical_flag", "total_float",
        # Secondary — notes
        "remarks",
    }

    def test_all_known_provenance_keys_are_registered(self):
        """Every key the engine can emit in Activity.provenance must be in the
        registry so downstream trust consumers never hit a KeyError."""
        unregistered = self.KNOWN_PROVENANCE_KEYS - (
            CRITICAL_FIELD_NAMES | SECONDARY_FIELD_NAMES
        )
        assert not unregistered, (
            f"Fields missing from registry: {sorted(unregistered)}. "
            "Add them to CRITICAL_FIELD_NAMES or SECONDARY_FIELD_NAMES in "
            "src/trust/fields.py."
        )

    def test_every_registered_field_is_reachable_via_criticality(self):
        """Every name in either set can be looked up without raising."""
        for field in CRITICAL_FIELD_NAMES | SECONDARY_FIELD_NAMES:
            result = criticality(field)
            assert isinstance(result, Criticality)


# ---------------------------------------------------------------------------
# AC2 — Each field maps to exactly one criticality
# ---------------------------------------------------------------------------

class TestExactlyOneCriticality:
    """AC2: no field can be both CRITICAL and SECONDARY."""

    def test_sets_are_disjoint(self):
        overlap = CRITICAL_FIELD_NAMES & SECONDARY_FIELD_NAMES
        assert not overlap, (
            f"Fields appear in both sets: {sorted(overlap)}. "
            "Each field must belong to exactly one criticality."
        )

    def test_criticality_returns_critical_for_critical_set(self):
        for field in CRITICAL_FIELD_NAMES:
            assert criticality(field) is Criticality.CRITICAL, (
                f"{field!r} is in CRITICAL_FIELD_NAMES but criticality() "
                "returns SECONDARY"
            )

    def test_criticality_returns_secondary_for_secondary_set(self):
        for field in SECONDARY_FIELD_NAMES:
            assert criticality(field) is Criticality.SECONDARY, (
                f"{field!r} is in SECONDARY_FIELD_NAMES but criticality() "
                "returns CRITICAL"
            )

    def test_unregistered_field_raises_key_error(self):
        with pytest.raises(KeyError, match="not registered"):
            criticality("__definitely_not_a_field__")


# ---------------------------------------------------------------------------
# AC3 — Cross-reference between heuristics.py and fields.py is documented
# ---------------------------------------------------------------------------

class TestCrossReference:
    """AC3: both files carry the cross-reference comment so the two
    CRITICAL_FIELDS sets are never silently merged."""

    BACKEND_ROOT = pathlib.Path(__file__).parent.parent.parent

    def _read(self, rel_path: str) -> str:
        return (self.BACKEND_ROOT / rel_path).read_text(encoding="utf-8",
                                                        errors="replace")

    def test_heuristics_cross_references_trust_fields(self):
        """heuristics.py must mention src/trust/fields.py near its
        CRITICAL_FIELDS definition so a reader sees the relationship."""
        src = self._read("ingestion/recognition/heuristics.py")
        assert "src/trust/fields.py" in src, (
            "ingestion/recognition/heuristics.py must cross-reference "
            "src/trust/fields.py near CRITICAL_FIELDS (TL-1.7 AC3)."
        )

    def test_fields_cross_references_heuristics(self):
        """fields.py must mention heuristics.py to close the loop."""
        src = self._read("src/trust/fields.py")
        assert "heuristics.py" in src, (
            "src/trust/fields.py must cross-reference heuristics.py "
            "(TL-1.7 AC3)."
        )

    def test_heuristics_critical_fields_is_three_elements(self):
        """The recogniser's CRITICAL_FIELDS is the minimum viable set for a
        parseable row — exactly three elements.  If this changes, the
        cross-reference comment and this test need reviewing."""
        from ingestion.recognition.heuristics import (
            CRITICAL_FIELDS as HEURISTIC_CF,
        )
        assert HEURISTIC_CF == {"name", "planned_start", "planned_finish"}, (
            "heuristics.py CRITICAL_FIELDS changed — review the cross-reference "
            "comment in heuristics.py and fields.py."
        )

    def test_trust_critical_fields_is_six_elements(self):
        """The trust registry's CRITICAL set covers all six brief §8 fields."""
        assert CRITICAL_FIELD_NAMES == {
            "source_id", "name", "planned_start", "planned_finish",
            "duration_hours", "percent_complete",
        }

    def test_two_sets_overlap_only_on_name_start_finish(self):
        """The intersection of the two CRITICAL sets is exactly the three
        fields they share — source_id, duration_hours, percent_complete
        are trust-critical but NOT recogniser-critical."""
        from ingestion.recognition.heuristics import (
            CRITICAL_FIELDS as HEURISTIC_CF,
        )
        overlap = CRITICAL_FIELD_NAMES & HEURISTIC_CF
        assert overlap == {"name", "planned_start", "planned_finish"}, (
            f"Unexpected overlap: {overlap}. The two CRITICAL_FIELDS sets "
            "must remain distinct — they answer different questions."
        )


# ---------------------------------------------------------------------------
# AC4 — Thresholds are hooks, not calibrated values
# ---------------------------------------------------------------------------

class TestThresholdHooks:
    """AC4: thresholds are structural placeholders, explicitly marked
    UNCALIBRATED; no value is described as tuned (brief §7)."""

    def test_thresholds_are_floats_in_unit_interval(self):
        for attr in (
            "critical_ocr_green", "critical_ocr_amber_min",
            "secondary_ocr_green", "secondary_ocr_amber_min",
        ):
            val = getattr(THRESHOLDS, attr)
            assert isinstance(val, float), f"{attr} must be float"
            assert 0.0 < val < 1.0, (
                f"{attr}={val} is outside (0, 1) — thresholds must be "
                "fractional confidence values."
            )

    def test_critical_thresholds_exceed_secondary(self):
        """Critical fields carry stricter thresholds than secondary ones.
        This is a structural sanity check, not a calibration claim — the
        values themselves are UNCALIBRATED placeholders (brief §7)."""
        assert THRESHOLDS.critical_ocr_green >= THRESHOLDS.secondary_ocr_green, (
            "critical_ocr_green must be ≥ secondary_ocr_green "
            "(critical fields require higher confidence to reach VERIFIED)."
        )
        assert THRESHOLDS.critical_ocr_amber_min >= THRESHOLDS.secondary_ocr_amber_min, (
            "critical_ocr_amber_min must be ≥ secondary_ocr_amber_min "
            "(critical fields have a higher floor for REVIEW)."
        )

    def test_thresholds_are_immutable(self):
        """THRESHOLDS is a frozen dataclass — callers cannot accidentally
        modify the values at runtime."""
        with pytest.raises((AttributeError, TypeError)):
            THRESHOLDS.critical_ocr_green = 0.5  # type: ignore[misc]

    def test_fields_docstring_says_uncalibrated(self):
        """The module docstring must contain the word UNCALIBRATED so
        anyone reading the source knows these are not tuned values."""
        src = pathlib.Path(__file__).parent.parent.parent / "src/trust/fields.py"
        text = src.read_text()
        assert "UNCALIBRATED" in text, (
            "src/trust/fields.py must say UNCALIBRATED near threshold values "
            "(brief §7 forbids presenting placeholders as tuned)."
        )

    def test_thresholds_singleton_is_importable_from_package(self):
        """THRESHOLDS is re-exported from `src.trust` so callers don't
        need to know about `fields.py` directly."""
        from src.trust import THRESHOLDS as T
        assert T is THRESHOLDS
