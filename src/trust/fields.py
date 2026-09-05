"""
Field criticality registry
===========================
TL-1.7 (brief §8, parallel-safe)

Declares every field in the NUSF `Activity` model as either CRITICAL
or SECONDARY, and exposes per-criticality threshold *hooks*.

**Why this module exists.**  Brief §8 is unambiguous:

  "A 90% confidence score on 'description' is not necessarily equivalent
   to 90% confidence on Activity ID."

Criticality must be data, not scattered conditionals scattered across
multiple callers.  Every Phase 1–9 task that gates on confidence
thresholds imports from here — the values are in one place and the
uncalibrated status is explicit.

**Relationship to ``ingestion/recognition/heuristics.py``.**

  ``heuristics.py`` also defines a ``CRITICAL_FIELDS`` set::

      CRITICAL_FIELDS = {"name", "planned_start", "planned_finish"}

  That set answers a *different* question: "which semantic roles must
  be resolved for the AI-fallback recogniser to skip AI and return a
  confident result?"  It is a column-recognition heuristic with three
  elements (the minimum viable set for a parseable schedule row).

  This module's ``CRITICAL`` criticality answers the trust-layer
  question: "which Activity fields, if misread, can materially change
  analysis and should therefore face stricter trust thresholds?"  The
  answer is broader — six fields including Activity ID, duration, and
  progress — and it will never be used to gate AI-fallback behaviour.

  Do NOT silently merge the two.  The cross-reference comment in
  ``heuristics.py`` (line 170) points here; this docstring points
  there.  If either set ever changes, both files must be reviewed.

**Threshold hooks.**  The ``Thresholds`` dataclass carries the
per-criticality OCR confidence thresholds the Trust Engine will use
(Phase 4, TL-4.3 / TL-4.7).  The *values* are structural placeholders
— brief §7 explicitly forbids hard-coding final numbers before
calibration against real K&L schedules (EXT-1, blocked TL-3.6 and
TL-4.7).  They are labelled UNCALIBRATED so no downstream code may
treat them as tuned thresholds.

Usage::

    from src.trust.fields import criticality, Criticality, THRESHOLDS

    if criticality("source_id") is Criticality.CRITICAL:
        threshold = THRESHOLDS.critical_ocr_min  # UNCALIBRATED
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet


# ---------------------------------------------------------------------------
# Criticality enum
# ---------------------------------------------------------------------------

class Criticality(str, Enum):
    """Trust-layer field criticality level.

    CRITICAL  — errors can materially change analysis (brief §8).
                These fields face stricter OCR confidence thresholds
                and, when unverifiable, surface an explicit trust flag.

    SECONDARY — informational fields; lower quality is acceptable and
                does not gate analysis or match confidence.  Absence
                is tolerable; a wrong value rarely changes a KPI.
    """
    CRITICAL  = "critical"
    SECONDARY = "secondary"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Every field name here matches a key in ``Activity.provenance`` (the
# string keys used by ``NormalizationEngine.normalize()``) or the
# ``Activity`` model attribute name directly.
#
# Covers every field in ``ingestion/models/nusf.py :: Activity``
# that can appear in the provenance dict, plus the internal/structural
# fields that are relevant to trust accounting.
# ---------------------------------------------------------------------------

#: Fields whose misread value can materially change analysis or comparison.
#: Source: brief §8 §6 §9 §10.
#: Compare with ``ingestion/recognition/heuristics.py :: CRITICAL_FIELDS``
#: — that is a narrower 3-element set used only for AI-fallback gating.
CRITICAL_FIELD_NAMES: FrozenSet[str] = frozenset({
    "source_id",         # §9 §10: "Never invent an Activity ID"
    "name",              # §8: identity; mismatch breaks cross-revision matching
    "planned_start",     # §8 §6: drives delay, PONR, and critical-path analysis
    "planned_finish",    # §8 §6: drives delay, PONR, and critical-path analysis
    "duration_hours",    # §6: schedule arithmetic depends on it
    "percent_complete",  # §8 §6: progress deviation KPI
})

#: Fields whose misread value is informational — lower quality acceptable.
#: Source: brief §8 ("descriptions, notes, metadata").
SECONDARY_FIELD_NAMES: FrozenSet[str] = frozenset({
    # Location / spatial hierarchy
    "location_path",     # raw hierarchy string; derived fields below carry the substance
    "area",              # derived from location_path
    "floor",             # derived from location_path
    "phase",             # derived from location_path
    # Classification
    "discipline",        # trade/department tag
    "activity_type",     # TASK / SUMMARY / MILESTONE / LOE
    "wbs_code",          # hierarchical code, optional in many formats
    # Progress & status flags
    "actual_start",      # captured when available; absent is normal
    "actual_finish",     # captured when available; absent is normal
    "is_late",           # source late-flag; redundant with date delta
    "inspected_status",  # source inspection state; display-only
    "critical_flag",     # source critical-path flag; advisory
    "total_float",       # source float/slack; advisory
    # Notes / remarks
    "remarks",           # free-text notes; no analysis dependency
})

# Sanity check: every name appears in exactly one set.
_ALL_REGISTERED: FrozenSet[str] = CRITICAL_FIELD_NAMES | SECONDARY_FIELD_NAMES
assert CRITICAL_FIELD_NAMES.isdisjoint(SECONDARY_FIELD_NAMES), (
    "A field cannot be both CRITICAL and SECONDARY — check fields.py"
)


# ---------------------------------------------------------------------------
# Public accessor
# ---------------------------------------------------------------------------

def criticality(field: str) -> Criticality:
    """Return the ``Criticality`` for *field*.

    *field* is the provenance key / ``Activity`` attribute name as used
    in ``NormalizationEngine.normalize()`` (e.g. ``"source_id"``,
    ``"planned_start"``, ``"area"``).

    Raises
    ------
    KeyError
        If *field* is not registered.  This is intentional — an
        unregistered field is a gap in the registry, not a harmless
        unknown.  Add it to the correct set before calling.
    """
    if field in CRITICAL_FIELD_NAMES:
        return Criticality.CRITICAL
    if field in SECONDARY_FIELD_NAMES:
        return Criticality.SECONDARY
    raise KeyError(
        f"Field {field!r} is not registered in src/trust/fields.py. "
        "Add it to CRITICAL_FIELD_NAMES or SECONDARY_FIELD_NAMES."
    )


# ---------------------------------------------------------------------------
# Threshold hooks
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Thresholds:
    """Per-criticality OCR confidence threshold hooks.

    **UNCALIBRATED — structural placeholders only.**

    Brief §7 forbids hard-coding final numbers before calibration
    against real K&L schedule pairs (EXT-1, target 2026-10-19).
    These values MUST NOT be described to the client as tuned.

    Calibration is owned by TL-4.7 (blocked on EXT-1).  When EXT-1
    data arrives, update this dataclass and remove the UNCALIBRATED
    label from each field.

    Threshold semantics (brief §7):
      GREEN  (≥ high_green) → VERIFIED, normal processing
      AMBER  (≥ amber_min)  → REVIEW, flag internally and where material
      RED    (< amber_min)  → UNVERIFIED, do not treat as reliable fact
    """

    # --- CRITICAL fields ---

    #: Minimum OCR confidence for a CRITICAL field to reach VERIFIED.
    #: UNCALIBRATED — placeholder 0.95.
    critical_ocr_green: float = 0.95

    #: Floor for a CRITICAL field to reach REVIEW (below → UNVERIFIED).
    #: UNCALIBRATED — placeholder 0.80.
    critical_ocr_amber_min: float = 0.80

    # --- SECONDARY fields ---

    #: Minimum OCR confidence for a SECONDARY field to reach VERIFIED.
    #: UNCALIBRATED — placeholder 0.85.
    secondary_ocr_green: float = 0.85

    #: Floor for a SECONDARY field to reach REVIEW (below → UNVERIFIED).
    #: UNCALIBRATED — placeholder 0.65.
    secondary_ocr_amber_min: float = 0.65


#: Singleton — import and use directly.
#: All values are UNCALIBRATED placeholders; do not present to the
#: client as tuned thresholds until TL-4.7 lands.
THRESHOLDS = _Thresholds()
