"""Nova Trust Layer — canonical user-facing trust vocabulary.

This module is the single source of truth for trust-related enums and their
labels/tooltips. The string content itself lives in
`src/version_1_0/localization.py` so it is co-located with all other Nova
copy and routed through the existing `t()` lookup; this module only owns
the *types* and the accessors.

Danish wording is the initial translation. Final wording requires K&L
sign-off (external dependency EXT-2 in `PROGRESS.md`).
"""
from __future__ import annotations

from enum import Enum

from src.version_1_0.localization import (
    t_claim,
    t_conflict,
    t_evidence,
    t_state,
)


class TrustState(str, Enum):
    """The three user-facing trust states (brief §21, §46).

    Exactly three values. `SOURCE_CONFLICT` is modelled as a separate flag
    (`SOURCE_CONFLICT_FLAG`), not as a fourth state — brief §21 is explicit
    about this and the test in `tests/trust/test_vocabulary.py` enforces it.
    """

    VERIFIED = "verified"
    REVIEW = "review"
    UNVERIFIED = "unverified"


#: Flag indicating the source schedule contains conflicting values for the
#: item in question (brief §46: "Source Conflict"). This is *not* a fourth
#: `TrustState`; it is an orthogonal bit that can be set on top of any state.
SOURCE_CONFLICT_FLAG: bool = True


class ClaimKind(str, Enum):
    """How a statement in Nova's response is grounded (brief §19).

    Used by the agent response contract (Phase 6) to classify every claim
    before it is rendered. `UNKNOWN` is a first-class value, not an
    absence — see brief §19 "Never present inference as fact."
    """

    FACT = "fact"
    DERIVED_FACT = "derived_fact"
    INFERENCE = "inference"
    UNKNOWN = "unknown"


class EvidenceClass(str, Enum):
    """What kind of evidence backs a value (brief §45).

    Distinct visual classes (brief §45, TL-7.3) — the same number on the
    dashboard means different things across these classes.
    """

    SOURCE_DATA = "source_data"
    NOVA_CALCULATION = "nova_calculation"
    NOVA_INSIGHT = "nova_insight"
    NOVA_FORECAST = "nova_forecast"


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------
# These accept both enum members and raw `.value` strings so callers do not
# have to care which they have. Internally they delegate to the namespaced
# `t_state` / `t_claim` / `t_evidence` helpers in localization.py, which
# themselves route through `t()`.

def trust_label(state, lang: str) -> str:
    """User-facing label for a `TrustState` (brief §46 wording)."""
    key = state.value if isinstance(state, TrustState) else str(state)
    return t_state(key, lang, tooltip=False)


def trust_tooltip(state, lang: str) -> str:
    """Tooltip for a `TrustState`. Brief §21 wording — verbatim."""
    key = state.value if isinstance(state, TrustState) else str(state)
    return t_state(key, lang, tooltip=True)


def claim_label(kind, lang: str) -> str:
    """User-facing label for a `ClaimKind` (brief §19 wording)."""
    key = kind.value if isinstance(kind, ClaimKind) else str(kind)
    return t_claim(key, lang, tooltip=False)


def claim_tooltip(kind, lang: str) -> str:
    """Tooltip for a `ClaimKind` (brief §19 wording)."""
    key = kind.value if isinstance(kind, ClaimKind) else str(kind)
    return t_claim(key, lang, tooltip=True)


def evidence_label(cls, lang: str) -> str:
    """User-facing label for an `EvidenceClass` (brief §45/§46 wording)."""
    key = cls.value if isinstance(cls, EvidenceClass) else str(cls)
    return t_evidence(key, lang, tooltip=False)


def evidence_tooltip(cls, lang: str) -> str:
    """Tooltip for an `EvidenceClass` (brief §45 wording)."""
    key = cls.value if isinstance(cls, EvidenceClass) else str(cls)
    return t_evidence(key, lang, tooltip=True)


def conflict_label(lang: str) -> str:
    """User-facing label for the source-conflict flag (brief §46 wording)."""
    return t_conflict(lang, tooltip=False)


def conflict_tooltip(lang: str) -> str:
    """Tooltip for the source-conflict flag."""
    return t_conflict(lang, tooltip=True)


__all__ = [
    "TrustState",
    "ClaimKind",
    "EvidenceClass",
    "SOURCE_CONFLICT_FLAG",
    "trust_label",
    "trust_tooltip",
    "claim_label",
    "claim_tooltip",
    "evidence_label",
    "evidence_tooltip",
    "conflict_label",
    "conflict_tooltip",
]
