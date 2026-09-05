"""Review queue data model
=========================
TL-8.1 (brief §25)

Gives humans a way to resolve what Nova refused to guess. Brief §25's own
worked example: *"31 items require review"*, categorised as low-confidence
IDs, uncertain activity matches, unreadable dates, conflicting values —
brief §26's own worked example: *"Nova found two possible matches for
Activity 'Ventilation Level 2' — Option A / Option B / No match."*

Architectural rule (brief §34, restated for this module): every category
here is *derived* from evidence a prior phase already computed —
`requires_verification_activities` (TL-3.4), `Provenance`/`TrustEngine`
(TL-1.x/TL-4.x), and `ValidationIssue`s tagged `SOURCE_CONFLICT` (TL-4.5).
Nothing in this module runs a new detector; it only reshapes existing,
already-tested signals into one queue.

Do-not (brief §25/§26, restated): a resolution is an *additive* record —
it is never allowed to overwrite the extracted source value. The original
reading and the human decision are two separate, permanently-retained
facts (Phase 9's audit trail depends on both surviving). Enforced
structurally here: `ReviewQueueStore.resolve`/`.reopen` never receive an
`Activity`, a `Provenance`, or any handle to source data — there is
nothing for them to mutate even if they tried.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Sequence

from src.trust.engine import TrustEngine
from src.trust.vocabulary import TrustState

_ENGINE = TrustEngine()


class ReviewCategory(str, Enum):
    """Brief §25's own four categories — exhaustive by design; a new
    category is a plan decision (a new ADR), not a silent runtime add."""

    LOW_CONFIDENCE_ID = "low_confidence_id"
    UNCERTAIN_MATCH = "uncertain_match"
    UNREADABLE_DATE = "unreadable_date"
    CONFLICTING_VALUE = "conflicting_value"


class ResolutionState(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    REOPENED = "reopened"


# Every review item's "no match" choice (brief §25: "No match is always an
# explicit, first-class choice" — TL-8.2's own AC). A fixed sentinel, not a
# per-item string, so callers never have to guess the spelling.
NO_MATCH_OPTION_ID = "no_match"


@dataclass(frozen=True)
class CandidateOption:
    """One choice a human can make on a `ReviewItem`. `activity_id` is the
    real (never-invented — Phase 2's contract) source id of the candidate
    counterpart, when the category is a match choice; `None` for
    categories where the choice is not "which activity" but "confirm or
    correct this value"."""

    option_id: str
    label: str
    activity_id: Optional[str] = None
    evidence: str = ""


@dataclass(frozen=True)
class ReviewItem:
    """One entry in the review queue. Immutable — a `ReviewItem` is Nova's
    record of what it found; resolving it never edits this object, it only
    appends a `Resolution` (see `ReviewQueueStore`)."""

    item_id: str
    project_id: str
    category: ReviewCategory
    affected_activity_ids: tuple[str, ...]
    evidence: str
    candidate_options: tuple[CandidateOption, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Resolution:
    """One append-only event against a `ReviewItem`. `action` is
    `"resolved"` or `"reopened"` — never `"edited"` or `"deleted"`; the
    history is a log, not a mutable record (brief §25/§26's Do-not rule,
    and the audit trail `TL-9.2` will read)."""

    resolution_id: str
    item_id: str
    action: str  # "resolved" | "reopened"
    chosen_option_id: Optional[str]
    actor: str
    at: datetime
    note: str = ""


class ReadOnlyUserError(PermissionError):
    """Raised when a read-only actor attempts to resolve or reopen an
    item (TL-8.1 AC5). A `PermissionError` subclass so a Flask route can
    catch it narrowly without string-matching an error message."""


class ReviewQueueStore:
    """Reference, in-memory implementation of the review-queue contract.

    Each Flask backend (`kemp&lauritzen/backend`, `website/workspace/app/
    Nova-Insights-Backend`) persists this same shape in its own database —
    this class is what both must behave like: `list`/`resolve`/`reopen`,
    additive history, no source mutation, read-only actors blocked. It is
    also directly usable as-is for the RAG service's own tests and for any
    caller that does not need cross-process persistence.
    """

    def __init__(self) -> None:
        self._items: dict[str, ReviewItem] = {}
        self._history: dict[str, list[Resolution]] = {}

    # -- population -----------------------------------------------------

    def add_items(self, items: Sequence[ReviewItem]) -> None:
        for item in items:
            self._items[item.item_id] = item
            self._history.setdefault(item.item_id, [])

    # -- reads ------------------------------------------------------------

    def get_item(self, item_id: str) -> Optional[ReviewItem]:
        return self._items.get(item_id)

    def state_of(self, item_id: str) -> ResolutionState:
        history = self._history.get(item_id, [])
        if not history:
            return ResolutionState.PENDING
        return (
            ResolutionState.RESOLVED
            if history[-1].action == "resolved"
            else ResolutionState.REOPENED
        )

    def history_of(self, item_id: str) -> tuple[Resolution, ...]:
        """Full append-only history — never truncated, never edited. This
        is the audit trail `TL-9.2` reads; a resolve-then-reopen-then-
        resolve sequence keeps all three records, not just the latest."""
        return tuple(self._history.get(item_id, ()))

    def list_items(
        self, project_id: str, *, include_resolved: bool = True
    ) -> list[ReviewItem]:
        """Brief §25's "list items for a session" endpoint. `project_id`
        is an opaque scoping key — the caller decides what it means
        (Nova's multi-tenant backend can prefix it with `company_id`;
        Kemp, which has no tenant column, can pass the bare session id;
        `ReviewQueueStore` itself does not need to know the difference)."""
        items = [it for it in self._items.values() if it.project_id == project_id]
        if include_resolved:
            return items
        return [it for it in items if self.state_of(it.item_id) != ResolutionState.RESOLVED]

    # -- writes (additive only) -------------------------------------------

    def resolve(
        self,
        item_id: str,
        chosen_option_id: str,
        actor: str,
        *,
        actor_role: Optional[str] = None,
        note: str = "",
    ) -> Resolution:
        """Brief §25's "resolve an item" endpoint. `chosen_option_id` must
        be `NO_MATCH_OPTION_ID` or one of the item's own
        `candidate_options` — a typo'd or invented option id is rejected,
        never silently accepted as "resolved" with nothing meaningful
        behind it.

        Never touches the item's own fields, never touches any `Activity`
        or `Provenance` object — there is no source value in scope here to
        overwrite (TL-8.1's Do-not rule, structurally: this function does
        not import, receive, or reference anything from
        `ingestion.models`)."""
        if actor_role == "read_only_user":
            raise ReadOnlyUserError("Read-only users cannot resolve review items")
        item = self._items.get(item_id)
        if item is None:
            raise KeyError(f"No such review item: {item_id!r}")
        valid_option_ids = {NO_MATCH_OPTION_ID} | {o.option_id for o in item.candidate_options}
        if chosen_option_id not in valid_option_ids:
            raise ValueError(
                f"{chosen_option_id!r} is not a valid option for item {item_id!r} "
                f"(valid: {sorted(valid_option_ids)})"
            )
        record = Resolution(
            resolution_id=str(uuid.uuid4()),
            item_id=item_id,
            action="resolved",
            chosen_option_id=chosen_option_id,
            actor=actor,
            at=datetime.now(timezone.utc),
            note=note,
        )
        self._history.setdefault(item_id, []).append(record)
        return record

    def reopen(
        self,
        item_id: str,
        actor: str,
        *,
        actor_role: Optional[str] = None,
        note: str = "",
    ) -> Resolution:
        """Brief §25's "reopen a resolution" endpoint. Appends a
        `"reopened"` event — the prior `"resolved"` record stays in
        history untouched (never deleted, never overwritten); `state_of`
        simply reads the latest entry."""
        if actor_role == "read_only_user":
            raise ReadOnlyUserError("Read-only users cannot reopen review items")
        if item_id not in self._items:
            raise KeyError(f"No such review item: {item_id!r}")
        if self.state_of(item_id) != ResolutionState.RESOLVED:
            raise ValueError(f"Item {item_id!r} is not currently resolved — nothing to reopen")
        record = Resolution(
            resolution_id=str(uuid.uuid4()),
            item_id=item_id,
            action="reopened",
            chosen_option_id=None,
            actor=actor,
            at=datetime.now(timezone.utc),
            note=note,
        )
        self._history.setdefault(item_id, []).append(record)
        return record


# ============================================================================
# Derivation — turning already-computed upstream signals into ReviewItems
# ============================================================================
# Each function below reads one existing signal and produces `ReviewItem`s.
# None of them re-derive a trust judgement from scratch; they only ask
# "does this already-computed assessment cross the line into 'needs a
# human'?" — the assessment itself is TL-1.x/TL-3.x/TL-4.x's, not new.


def derive_uncertain_match_items(
    requires_verification_activities: Sequence[dict[str, Any]], project_id: str
) -> list[ReviewItem]:
    """Brief §25's "uncertain activity matches" category, from
    `nusf_compare_engine.py`'s `requires_verification_activities` (TL-3.4).
    Brief §26's worked example ("Option A / Option B / No match") maps
    directly onto each row's `candidates` list (`MatchResult.candidates`,
    TL-3.2/TL-3.3) plus the always-present `NO_MATCH_OPTION_ID` choice.
    """
    items: list[ReviewItem] = []
    for row in requires_verification_activities:
        own_id = row.get("id") or ""
        candidates_raw = row.get("candidates") or []
        options = tuple(
            CandidateOption(
                option_id=f"candidate_{i}",
                label=f"Match to {c.get('matched_id')}",
                activity_id=c.get("matched_id"),
                evidence=(
                    f"{c['date_distance']} day(s) apart" if c.get("date_distance") is not None else ""
                ),
            )
            for i, c in enumerate(candidates_raw)
            if c.get("matched_id")
        ) + (
            CandidateOption(option_id=NO_MATCH_OPTION_ID, label="No match"),
        )
        items.append(
            ReviewItem(
                item_id=f"match::{project_id}::{own_id or uuid.uuid4()}",
                project_id=project_id,
                category=ReviewCategory.UNCERTAIN_MATCH,
                affected_activity_ids=(own_id,) if own_id else (),
                evidence=row.get("reason") or (
                    "Nova found insufficient evidence to reliably match this "
                    "activity between the two schedules."
                ),
                candidate_options=options,
                detail={
                    "activity_name": row.get("activity", ""),
                    "level": row.get("level"),
                    "method": row.get("method"),
                    "match_key": row.get("match_key", ""),
                },
            )
        )
    return items


def derive_conflicting_value_items(
    validation_issues: Sequence[Any], project_id: str
) -> list[ReviewItem]:
    """Brief §25's "conflicting values" category, from `TL-4.5`'s
    `ValidationIssue`s (`ingestion/validation/engine.py::_rule_conflicts`,
    category `SOURCE_CONFLICT`). Every other validation category
    (`STRUCTURAL`/`LOGICAL`/`QUALITY`) is a different concern — Rule 102's
    circular-dependency check, for instance, is not something a human
    resolves by picking a candidate value, so it is deliberately excluded
    here."""
    items: list[ReviewItem] = []
    for issue in validation_issues:
        category = getattr(issue, "category", None) or (
            issue.get("category") if isinstance(issue, dict) else None
        )
        if category != "SOURCE_CONFLICT":
            continue
        activity_id = getattr(issue, "activity_id", None) if not isinstance(issue, dict) else issue.get("activity_id")
        message = getattr(issue, "message", None) if not isinstance(issue, dict) else issue.get("message")
        items.append(
            ReviewItem(
                item_id=f"conflict::{project_id}::{activity_id or uuid.uuid4()}::{uuid.uuid4().hex[:8]}",
                project_id=project_id,
                category=ReviewCategory.CONFLICTING_VALUE,
                affected_activity_ids=(activity_id,) if activity_id else (),
                evidence=message or "Source data contains conflicting values for this activity.",
                candidate_options=(),
            )
        )
    return items


def _low_confidence_field_items(
    activities: Sequence[Any],
    project_id: str,
    *,
    field_names: Sequence[str],
    category: ReviewCategory,
    evidence_template: str,
) -> list[ReviewItem]:
    """Shared machinery for `derive_low_confidence_id_items` and
    `derive_unreadable_date_items` — both ask the same question
    (`TrustEngine.assess_value` on a named field, is it UNVERIFIED?) over
    a different field set. `activities` is any iterable of objects/dicts
    exposing `.internal_id`/`.source_id`/`.provenance` (the `Activity`
    model shape from `ingestion/models/nusf.py`) — kept duck-typed so this
    module never needs to import that model directly."""
    items: list[ReviewItem] = []
    for act in activities:
        provenance = getattr(act, "provenance", None)
        if provenance is None and isinstance(act, dict):
            provenance = act.get("provenance")
        provenance = provenance or {}
        internal_id = getattr(act, "internal_id", None) or (act.get("internal_id") if isinstance(act, dict) else None)
        source_id = getattr(act, "source_id", None) or (act.get("source_id") if isinstance(act, dict) else None)
        display_id = source_id or internal_id or ""

        for field_name in field_names:
            prov = provenance.get(field_name) if isinstance(provenance, dict) else None
            if prov is None:
                continue
            value = getattr(act, field_name, None) if not isinstance(act, dict) else act.get(field_name)
            assessment = _ENGINE.assess_value(field_name, value, provenance=prov)
            if assessment.state != TrustState.UNVERIFIED:
                continue
            items.append(
                ReviewItem(
                    item_id=f"{category.value}::{project_id}::{internal_id}::{field_name}",
                    project_id=project_id,
                    category=category,
                    affected_activity_ids=(display_id,) if display_id else (),
                    evidence=evidence_template.format(field=field_name, reason=assessment.reason),
                    candidate_options=(),
                    detail={"field": field_name, "extracted_value": value},
                )
            )
    return items


def derive_low_confidence_id_items(activities: Sequence[Any], project_id: str) -> list[ReviewItem]:
    """Brief §25's "low-confidence IDs" category — an activity's
    `source_id` was extracted with low enough OCR confidence that
    `TrustEngine.assess_value` (TL-4.2) already marked it UNVERIFIED."""
    return _low_confidence_field_items(
        activities,
        project_id,
        field_names=("source_id",),
        category=ReviewCategory.LOW_CONFIDENCE_ID,
        evidence_template="Activity ID could not be reliably read from the source schedule ({reason}).",
    )


def derive_unreadable_date_items(activities: Sequence[Any], project_id: str) -> list[ReviewItem]:
    """Brief §25's "unreadable dates" category — any of the four date
    fields Phase 1 tracks provenance for was extracted with low enough
    OCR confidence that `TrustEngine.assess_value` already marked it
    UNVERIFIED."""
    return _low_confidence_field_items(
        activities,
        project_id,
        field_names=("planned_start", "planned_finish", "actual_start", "actual_finish"),
        category=ReviewCategory.UNREADABLE_DATE,
        evidence_template="The {field} date could not be reliably read from the source schedule ({reason}).",
    )


def build_review_queue(
    project_id: str,
    *,
    requires_verification_activities: Sequence[dict[str, Any]] = (),
    activities: Sequence[Any] = (),
    validation_issues: Sequence[Any] = (),
) -> list[ReviewItem]:
    """Assemble every category into one queue for a project — the single
    entry point a caller (the RAG service's comparison endpoint, or a
    Flask backend populating its own table) needs. Any argument left at
    its default simply contributes no items for that category; a caller
    that only has match data (e.g. the raw/non-NUSF path) still gets a
    valid, if partial, queue rather than an error.
    """
    items: list[ReviewItem] = []
    items.extend(derive_uncertain_match_items(requires_verification_activities, project_id))
    items.extend(derive_low_confidence_id_items(activities, project_id))
    items.extend(derive_unreadable_date_items(activities, project_id))
    items.extend(derive_conflicting_value_items(validation_issues, project_id))
    return items


__all__ = [
    "ReviewCategory",
    "ResolutionState",
    "NO_MATCH_OPTION_ID",
    "CandidateOption",
    "ReviewItem",
    "Resolution",
    "ReadOnlyUserError",
    "ReviewQueueStore",
    "derive_uncertain_match_items",
    "derive_conflicting_value_items",
    "derive_low_confidence_id_items",
    "derive_unreadable_date_items",
    "build_review_queue",
]
