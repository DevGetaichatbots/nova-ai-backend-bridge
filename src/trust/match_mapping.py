"""Verified match mapping store
==============================
TL-8.3 / TL-8.4 / TL-8.5 (brief §26)

Brief §26: *"Do not make him correct the same deterministic ambiguity
every upload if the relevant identity relationship remains valid."*
Once a human confirms "activity X in revision 1 is activity Y in
revision 2", that decision should be reused on every subsequent upload —
until the underlying evidence changes materially, at which point it must
be invalidated and re-surfaced, never silently kept or silently dropped.

Mappings are keyed by `(project_id, match_key)`, never globally — the
same activity name means different things on different projects (TL-8.3's
own Do-not rule). `match_key` is an opaque, caller-supplied stable
identifier for "this real-world activity slot" (e.g. a normalized
name+location composite) — deliberately NOT a raw `internal_id`, since
Phase 2 established those are derived per-parse and are not stable
across separate uploads of the same project.
"""
from __future__ import annotations

import difflib
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Optional, Sequence

# Named, UNCALIBRATED (brief §7 posture — same as every other similarity
# threshold in this plan pending real K&L data, EXT-1). Below this ratio,
# a name is treated as materially different, not a rename/typo-fix.
_NAME_SIMILARITY_THRESHOLD_UNCALIBRATED = 0.6


@dataclass(frozen=True)
class VerifiedMapping:
    """One version of a human-confirmed identity relationship. Never
    edited in place — `MatchMappingStore.confirm`/`.invalidate` always
    create a new `VerifiedMapping` and keep the prior one in history
    (`version` increments; `invalidated`/`invalidated_reason` mark the
    terminal state of that version, they never get retro-applied to an
    earlier version)."""

    mapping_id: str
    project_id: str
    match_key: str
    old_activity_id: Optional[str]  # None means "confirmed: no match"
    evidence: str
    confirmed_by: str
    confirmed_at: datetime
    version: int
    invalidated: bool = False
    invalidated_reason: str = ""
    invalidated_at: Optional[datetime] = None


def detect_material_change(
    *,
    original_name: Optional[str] = None,
    current_name: Optional[str] = None,
    original_location: Optional[str] = None,
    current_location: Optional[str] = None,
    contradicting_verified_id: Optional[str] = None,
    split_into: Sequence[str] = (),
) -> Optional[str]:
    """TL-8.5 AC1: "define what 'materially changed' means, concretely
    and testably." Four checks, brief's own minimum list, in the order
    given there. Returns a human-readable reason when changed, else
    `None` — the reason is what the review queue shows the user for
    "why did this come back" (TL-8.5's own Do-not rule: never re-surface
    silently)."""
    if contradicting_verified_id:
        return (
            f"A verified source ID ({contradicting_verified_id}) now appears that "
            f"contradicts this mapping."
        )
    if len(split_into) > 1:
        return f"The activity was split into {len(split_into)} activities: {', '.join(split_into)}."
    if original_name and current_name:
        ratio = difflib.SequenceMatcher(None, original_name.strip().lower(), current_name.strip().lower()).ratio()
        if ratio < _NAME_SIMILARITY_THRESHOLD_UNCALIBRATED:
            return f"The activity name changed from {original_name!r} to {current_name!r}."
    if original_location and current_location and original_location.strip().lower() != current_location.strip().lower():
        return f"The activity's location changed from {original_location!r} to {current_location!r}."
    return None


class MatchMappingStore:
    """Reference, in-memory implementation of the mapping-store contract.
    Each Flask backend persists this same shape in its own database —
    versioned rows, never deleted, never edited in place."""

    def __init__(self) -> None:
        # (project_id, match_key) -> ordered list of all versions, oldest first
        self._history: dict[tuple[str, str], list[VerifiedMapping]] = {}

    def confirm(
        self,
        project_id: str,
        match_key: str,
        old_activity_id: Optional[str],
        evidence: str,
        confirmed_by: str,
    ) -> VerifiedMapping:
        """TL-8.3: store a new confirmed mapping. If a mapping already
        exists for this key, this is a new *version* — the prior one
        stays in history untouched (TL-8.3 AC2: "each mapping records
        evidence, author, and timestamp"; nothing here overwrites a
        previous version's own record of those three things)."""
        key = (project_id, match_key)
        prior = self._history.get(key, [])
        mapping = VerifiedMapping(
            mapping_id=str(uuid.uuid4()),
            project_id=project_id,
            match_key=match_key,
            old_activity_id=old_activity_id,
            evidence=evidence,
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(timezone.utc),
            version=len(prior) + 1,
        )
        self._history.setdefault(key, []).append(mapping)
        return mapping

    def active_mapping(self, project_id: str, match_key: str) -> Optional[VerifiedMapping]:
        """TL-8.3 AC1 / TL-8.4: the mapping a matcher should consult
        *before* falling back to ambiguity detection — `None` if there is
        none, or if the latest version was invalidated (TL-8.5: an
        invalidated mapping must not keep silently winning)."""
        history = self._history.get((project_id, match_key), [])
        if not history:
            return None
        latest = history[-1]
        return None if latest.invalidated else latest

    def history_of(self, project_id: str, match_key: str) -> tuple[VerifiedMapping, ...]:
        """TL-8.5 AC3: invalidation history retained — every version,
        including invalidated ones, stays queryable forever."""
        return tuple(self._history.get((project_id, match_key), ()))

    def invalidate(self, project_id: str, match_key: str, reason: str) -> Optional[VerifiedMapping]:
        """TL-8.5: mark the active mapping invalidated in place — as a
        new terminal record (`replace`, a new object), not a mutation of
        the existing one, so `history_of` still shows exactly what the
        mapping looked like before invalidation. Returns `None` if there
        was no active mapping to invalidate."""
        key = (project_id, match_key)
        history = self._history.get(key, [])
        if not history or history[-1].invalidated:
            return None
        invalidated = replace(
            history[-1],
            invalidated=True,
            invalidated_reason=reason,
            invalidated_at=datetime.now(timezone.utc),
        )
        history[-1] = invalidated
        return invalidated

    def reconcile(
        self,
        project_id: str,
        match_key: str,
        *,
        original_name: Optional[str] = None,
        current_name: Optional[str] = None,
        original_location: Optional[str] = None,
        current_location: Optional[str] = None,
        contradicting_verified_id: Optional[str] = None,
        split_into: Sequence[str] = (),
    ) -> tuple[Optional[VerifiedMapping], Optional[str]]:
        """TL-8.5: the single entry point a matcher calls before trusting
        a mapping. Returns `(mapping, None)` when the mapping is still
        valid and usable, or `(None, reason)` when it was just
        invalidated — the caller (TL-8.4's matching integration) must
        treat the latter as "no mapping, fall back to ambiguity
        detection, and return this item to the review queue with
        `reason`" (TL-8.5's own Do-not rule)."""
        mapping = self.active_mapping(project_id, match_key)
        if mapping is None:
            return None, None
        reason = detect_material_change(
            original_name=original_name,
            current_name=current_name,
            original_location=original_location,
            current_location=current_location,
            contradicting_verified_id=contradicting_verified_id,
            split_into=split_into,
        )
        if reason is None:
            return mapping, None
        self.invalidate(project_id, match_key, reason)
        return None, reason


__all__ = [
    "VerifiedMapping",
    "MatchMappingStore",
    "detect_material_change",
]
