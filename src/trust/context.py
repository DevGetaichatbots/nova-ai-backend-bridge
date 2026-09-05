"""Structured verified context and response-facts builder
(TL-5.3 + TL-5.4, brief §17).

Brief §17 is explicit about the failure mode this module closes:

    Do not send huge raw OCR dumps to the LLM and ask "What is happening?"
    Instead generate structured verified context.

    { "project_status": {"delayed_activities": 73, "critical_delayed": 6},
      "clusters": [{"location": "NK", "trade": "EL", "delayed": 17,
                     "critical": 3, "confidence": "high"}] }

    Then tell the AI: "Explain only the supplied facts. Do not introduce
    facts not contained in the structured context."

Two distinct outputs live here, with two different size disciplines:

- **`build_predictive_context`** (TL-5.3): the JSON sent TO the model as
  input. Must stay small — brief §17's whole point, pinned by TL-5.3's own
  "order of magnitude smaller than raw text" acceptance criterion (see
  ADR-019). Aggregates (`project_status`, `clusters`) plus, as of TL-5.4,
  two small, explicitly-bounded additions the narrative layer needs to
  write about specific activities without inventing ids
  (`biggest_risk_candidate`: one activity; `actionable_activities`:
  CRITICAL_NOW/IMPORTANT_NEXT/root-cause activities only — the minority the
  prompt's own decision-support layer actually reasons about per-activity,
  never the full delayed set). This resolves the open question ADR-019
  deferred to this task.
- **`build_response_facts`** (TL-5.4): the deterministic FACTS half of the
  final API response — `schedule_overview`, the full `delayed_activities`
  list, `downstream_consequences`, and the deterministic subset of
  `insight_data`. No size constraint applies here; this is never sent to
  the model, only merged with its narrative output in
  `predictive_agent.analyze()`. Every id, count, and classification here is
  computed from `PredictiveActivity`/`Activity` data — the model is never
  asked to produce any of it (brief §4, §15).

Trust discipline (brief §6, §14) applies to both:

- Every fact this module emits carries an explicit trust signal — either a
  cluster's `confidence`, `project_status.confidence`, or (for
  `build_response_facts`) each activity's own `trust_state`. Nothing is
  handed to the model, or returned to the user, unlabelled.
- `UNVERIFIED`-trust activities never contribute to `project_status`'s
  confirmed counts or to any `clusters`/`actionable_activities` entry. They
  are counted, not detailed — `project_status.unverified_delayed_count`
  says "N more activities exist but could not be confirmed," which is
  itself a true, verifiable statement, without asserting anything about
  which N or why. `build_response_facts` follows the same rule for its own
  `delayed_activities`/`insight_data` counts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional, Sequence

from ingestion.models.nusf import Activity
from src.trust.predictive_facts import (
    CRITICAL_NOW,
    IMPORTANT_NEXT,
    MONITOR,
    PredictiveActivity,
    classify_project_status,
)
from src.trust.vocabulary import TrustState

_UNKNOWN_LOCATION = "Unknown"
_UNKNOWN_TRADE = "Unknown"

# Trust state -> the "high"/"medium"/"low" wire-format word brief §17's own
# example uses for cluster confidence. This is deliberately a separate,
# local mapping rather than reusing `src/trust/vocabulary.py`'s
# `trust_label`/`trust_tooltip` — those are localized (EN/DA) UI copy for
# human display; this is a stable, English-only, machine-readable token in
# a JSON payload sent to the model, and must not change if DA wording
# changes (EXT-2) or a UI label is reworded.
_CONFIDENCE_WORD: dict[TrustState, str] = {
    TrustState.VERIFIED: "high",
    TrustState.REVIEW: "medium",
    # TrustState.UNVERIFIED deliberately has no entry: an UNVERIFIED-only
    # cluster is never built (see `_group_by_location_trade`) because every
    # member contributing to a cluster is already confirmed
    # (VERIFIED or REVIEW) by the time clustering runs.
}


@dataclass(frozen=True)
class ClusterFact:
    """One `location` x `trade` cluster of confirmed delayed activities
    (brief §17's `clusters[]` shape)."""

    location: str
    trade: str
    delayed: int
    critical: int
    confidence: str  # "high" | "medium" — see `_CONFIDENCE_WORD`


def _confirmed(facts: Sequence[PredictiveActivity]) -> list[PredictiveActivity]:
    """Facts whose trust state passed the Trust Engine (VERIFIED or REVIEW).
    UNVERIFIED facts never reach any structured-context field beyond an
    aggregate count (brief's "never passed as plain facts")."""
    return [f for f in facts if f.trust.state != TrustState.UNVERIFIED]


def _weakest_confidence_word(facts: Sequence[PredictiveActivity]) -> str:
    """Weakest-link confidence word (brief §14) across a set of already-
    confirmed facts: "high" only if every member is VERIFIED, "medium" if
    any member is REVIEW. Never called on an empty set or on facts
    containing UNVERIFIED — both are guarded by callers."""
    if any(f.trust.state == TrustState.REVIEW for f in facts):
        return _CONFIDENCE_WORD[TrustState.REVIEW]
    return _CONFIDENCE_WORD[TrustState.VERIFIED]


def _resolve_id(internal_id: Optional[str], by_id: dict[str, Activity]) -> Optional[str]:
    """Resolve an `internal_id` (never displayed — `ingestion/models/nusf.py`)
    to the activity's `source_id`. `None` when there is no id to resolve, or
    when the referenced activity's own `source_id` is itself unverifiable
    (Phase 2's "never invent an ID" contract, `TL-2.1`-`TL-2.4`) — this
    module does not invent one."""
    if internal_id is None:
        return None
    activity = by_id.get(internal_id)
    return activity.source_id if activity is not None else None


def _location_trade(internal_id: str, by_id: dict[str, Activity]) -> tuple[str, str]:
    """`(location, trade)` for one activity, falling back to the literal
    `"Unknown"` bucket rather than being dropped — brief's "never invent"
    rule (Phase 2) forbids inventing a location/trade, but grouping under
    an explicit `"Unknown"` label is not invention, it is honest absence,
    the same pattern Phase 2's ID-display contract (`TL-2.4`) established
    for unverifiable identifiers."""
    activity = by_id.get(internal_id)
    location = (activity.area if activity and activity.area else _UNKNOWN_LOCATION).strip() or _UNKNOWN_LOCATION
    trade = (activity.discipline if activity and activity.discipline else _UNKNOWN_TRADE).strip() or _UNKNOWN_TRADE
    return location, trade


def _group_by_location_trade(
    confirmed: Sequence[PredictiveActivity], by_id: dict[str, Activity]
) -> list[ClusterFact]:
    """brief §17's `clusters[]`: group confirmed delayed activities by
    (location, trade), each cluster carrying its own weakest-link
    confidence."""
    groups: dict[tuple[str, str], list[PredictiveActivity]] = {}
    for f in confirmed:
        key = _location_trade(f.internal_id, by_id)
        groups.setdefault(key, []).append(f)

    clusters = [
        ClusterFact(
            location=location,
            trade=trade,
            delayed=len(members),
            critical=sum(1 for m in members if m.priority == CRITICAL_NOW),
            confidence=_weakest_confidence_word(members),
        )
        for (location, trade), members in groups.items()
    ]
    # Deterministic order (AC5): sort by location then trade. Python dict
    # insertion order already follows `confirmed`'s order, which is itself
    # deterministic, but this sort makes the guarantee explicit rather than
    # incidental.
    clusters.sort(key=lambda c: (c.location, c.trade))
    return clusters


def _biggest_risk_candidate(
    confirmed: Sequence[PredictiveActivity], by_id: dict[str, Activity]
) -> Optional[dict[str, Any]]:
    """TL-5.4: the single highest-impact root cause — grounding fact for the
    narrative `predictive_biggest_risk` field, which brief's own schema
    requires to name a real task id
    (`PREDICTIVE_SYSTEM_PROMPT`: "Must include task ID... NEVER omit the
    ID"). `None` when there are no confirmed root causes to name.

    Tie-break follows `PREDICTIVE_SYSTEM_PROMPT`'s own stated rule ("Pick
    the single root cause task with the highest combination of:
    days_overdue + number of affected_task_ids"): sort by
    `(days_overdue, affected_count)` descending, `internal_id` last for a
    fully deterministic result when both are tied.
    """
    root_causes = [f for f in confirmed if f.is_root_cause]
    if not root_causes:
        return None
    best = max(root_causes, key=lambda f: (f.days_overdue, len(f.affected_task_ids), f.internal_id))
    location, trade = _location_trade(best.internal_id, by_id)
    return {
        "id": best.source_id,
        "name": best.name,
        "days_overdue": best.days_overdue,
        "affected_count": len(best.affected_task_ids),
        "location": location,
        "trade": trade,
        "trust_state": best.trust.state.value,
    }


# Cap on `actionable_activities`. Named, documented, UNCALIBRATED — same
# posture as `TL-3.3`'s `_AMBIGUITY_MARGIN_DAYS` and `TL-5.2`'s priority
# thresholds (brief §7). Without a cap, a schedule with many independent
# root causes (each with no predecessors, hence individually a root cause —
# a real, not just adversarial, shape: see ADR-020) makes
# `actionable_activities` scale with total activity count, reproducing the
# exact size blow-up ADR-019 already fixed once for the unbounded
# `delayed_activities` field this replaced. Capping is explicit and
# labelled (`actionable_activities_omitted_count`), never a silent drop —
# `TL-5.5`'s "no silent truncation" rule applies here in spirit even though
# `TL-5.5` itself scopes to the raw-text truncation path.
_ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED = 6


def _actionable_activities(
    confirmed: Sequence[PredictiveActivity], by_id: dict[str, Activity]
) -> tuple[list[dict[str, Any]], int]:
    """TL-5.4: the bounded subset of confirmed activities the narrative
    layer needs to reason about individually — every root cause (brief:
    "One entry per root cause task") plus every CRITICAL_NOW/IMPORTANT_NEXT
    activity (brief: forcing/resource assessment cover these two priorities,
    "skip MONITOR tasks"), then capped to the highest-impact
    `_ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED` by `days_overdue`.

    Returns `(activities, omitted_count)` — `omitted_count` must always be
    surfaced by the caller, never dropped silently.
    """
    actionable = [f for f in confirmed if f.is_root_cause or f.priority in (CRITICAL_NOW, IMPORTANT_NEXT)]
    actionable.sort(key=lambda f: (-f.days_overdue, f.internal_id))
    omitted_count = max(0, len(actionable) - _ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED)
    capped = actionable[:_ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED]

    # Fields kept lean deliberately: only what the model needs to write
    # grounded prose. `task_type`/`problem_type`/`trust_state` are not
    # included — they are not needed for narrative writing (the model is
    # never asked to choose or echo them; `predictive_agent.analyze()`
    # backfills them from `build_response_facts`'s authoritative facts
    # during the merge, keyed by `id`), and every activity here is already
    # confirmed (non-`UNVERIFIED`) by construction.
    result = []
    for f in capped:
        location, trade = _location_trade(f.internal_id, by_id)
        result.append({
            "id": f.source_id,
            "name": f.name,
            "days_overdue": f.days_overdue,
            "priority": f.priority,
            "is_root_cause": f.is_root_cause,
            "blocked_by_id": _resolve_id(f.blocked_by_id, by_id),
            "affected_count": len(f.affected_task_ids),
            "location": location,
            "trade": trade,
        })
    return result, omitted_count


def build_predictive_context(
    facts: Sequence[PredictiveActivity],
    activities: Sequence[Activity],
    reference_date: date,
) -> dict[str, Any]:
    """TL-5.3: build the brief §17 structured, verified JSON context from
    the Phase 5 fact set. Pure function, deterministic, no LLM, no raw
    schedule text anywhere in the output.

    `facts` is `compute_predictive_facts(detect_delayed_activities(activities,
    reference_date), activities)` — the caller already ran TL-5.1/TL-5.2.
    `activities` is passed again (not just `facts`) because `location`
    (`Activity.area`) and `trade` (`Activity.discipline`) are not part of
    the `PredictiveActivity` shape.
    """
    by_id = {a.internal_id: a for a in activities}
    confirmed = _confirmed(facts)
    unverified_count = len(facts) - len(confirmed)

    project_status: dict[str, Any] = {
        "delayed_activities": len(confirmed),
        "critical_delayed": sum(1 for f in confirmed if f.priority == CRITICAL_NOW),
        "important_delayed": sum(1 for f in confirmed if f.priority == IMPORTANT_NEXT),
        "monitor_delayed": sum(1 for f in confirmed if f.priority == MONITOR),
        "root_cause_count": sum(1 for f in confirmed if f.is_root_cause),
        "unverified_delayed_count": unverified_count,
        # None (not "high") when there is nothing confirmed to assess —
        # asserting a confidence level over an empty set would itself be a
        # confidently-wrong claim (brief's core rule, applied to the
        # meta-level: don't be confident about having nothing).
        "confidence": _weakest_confidence_word(confirmed) if confirmed else None,
    }

    clusters = _group_by_location_trade(confirmed, by_id)
    actionable_activities, actionable_omitted_count = _actionable_activities(confirmed, by_id)

    return {
        "reference_date": reference_date.isoformat(),
        "project_status": project_status,
        "clusters": [
            {
                "location": c.location,
                "trade": c.trade,
                "delayed": c.delayed,
                "critical": c.critical,
                "confidence": c.confidence,
            }
            for c in clusters
        ],
        "biggest_risk_candidate": _biggest_risk_candidate(confirmed, by_id),
        "actionable_activities": actionable_activities,
        "actionable_activities_omitted_count": actionable_omitted_count,
    }


# ============================================================================
# `build_response_facts` (TL-5.4)
# ============================================================================
# The deterministic FACTS half of the final API response — everything
# `NOVA_INSIGHT_SCHEMA` previously asked the model to invent per-activity
# (`schedule_overview`, the full `delayed_activities` array,
# `downstream_consequences`, and the deterministic subset of `insight_data`)
# computed here instead, from the same `PredictiveActivity`/`Activity` data
# `build_predictive_context` already has. Never sent to the model — this is
# merged with the model's *narrative* output in
# `predictive_agent.PredictiveAgent.analyze_from_facts` (TL-5.4). No size
# constraint applies (contrast `build_predictive_context`): this is a
# response, not a prompt.


def _format_ddmmyyyy(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def _format_duration(duration_hours: int) -> str:
    """8 working hours ≈ 1 working day (brief's own conversion table,
    `PREDICTIVE_SYSTEM_PROMPT`'s NUSF field reference). `0h` renders as
    `"0d"` — a milestone, not a missing value."""
    days = duration_hours / 8
    return f"{days:g}d"


def _format_progress(percent_complete: float) -> str:
    return f"{percent_complete:g}%"


def _delayed_activity_fact(f: PredictiveActivity, by_id: dict[str, Activity]) -> dict[str, Any]:
    """One `delayed_activities[]` entry (brief schema), fully deterministic.

    `human_label` defaults to the real `name` — never a fabricated
    shortening — because the bulk of delayed activities are never shown to
    the model (only `actionable_activities`' bounded subset is); a
    narrative-generated label can only be trusted for the activities the
    model actually saw. `predictive_agent.analyze_from_facts` overwrites
    `human_label` for exactly that subset after the model responds, keyed by
    `id` (never invented — Phase 2's "never invent an ID" contract applies
    to lookups here too)."""
    activity = by_id.get(f.internal_id)
    location, _trade = _location_trade(f.internal_id, by_id)
    return {
        "id": f.source_id,
        "task_name": f.name,
        "human_label": f.name,
        "start_date": _format_ddmmyyyy(activity.planned_start.date()) if activity else "",
        "end_date": _format_ddmmyyyy(activity.planned_finish.date()) if activity else "",
        "duration": _format_duration(activity.duration_hours) if activity else "",
        "progress": _format_progress(activity.percent_complete) if activity else "",
        "days_overdue": f.days_overdue,
        "task_type": f.task_type,
        "priority": f.priority,
        "is_root_cause": f.is_root_cause,
        "blocked_by_id": _resolve_id(f.blocked_by_id, by_id),
        "area": location,
    }


def _root_cause_fact(f: PredictiveActivity, by_id: dict[str, Activity]) -> dict[str, Any]:
    """One `root_cause_analysis[]` entry's deterministic fields — the
    narrative text fields (`why_it_matters`, `downstream_impact`,
    `consequence_if_unresolved`) are filled in by
    `predictive_agent.analyze_from_facts` from the model's narrative
    response, keyed by this `id`."""
    return {
        "id": f.source_id,
        "task_name": f.name,
        "human_label": f.name,
        "days_overdue": f.days_overdue,
        "problem_type": f.problem_type,
        "affected_task_ids": [
            rid for rid in (_resolve_id(a, by_id) for a in f.affected_task_ids) if rid is not None
        ],
    }


def _downstream_consequence_fact(f: PredictiveActivity, by_id: dict[str, Activity]) -> dict[str, Any]:
    return {
        "id": f.source_id,
        "task_name": f.name,
        "human_label": f.name,
        "blocked_by_id": _resolve_id(f.blocked_by_id, by_id),
    }


def _summary_by_area_facts(confirmed: Sequence[PredictiveActivity], by_id: dict[str, Activity]) -> list[dict[str, Any]]:
    """Deterministic per-area counts (brief schema's `summary_by_area[]`
    minus the narrative `summary` sentence, which
    `predictive_agent.analyze_from_facts` merges in by `area`, matched
    case-sensitively against the exact string this function emits)."""
    groups: dict[str, list[PredictiveActivity]] = {}
    for f in confirmed:
        location, _trade = _location_trade(f.internal_id, by_id)
        groups.setdefault(location, []).append(f)
    rows = [
        {
            "area": area,
            "delayed_count": len(members),
            "critical_count": sum(1 for m in members if m.priority == CRITICAL_NOW),
            "important_count": sum(1 for m in members if m.priority == IMPORTANT_NEXT),
            "monitor_count": sum(1 for m in members if m.priority == MONITOR),
        }
        for area, members in groups.items()
    ]
    # Sorted by severity (brief: "sorted by severity"), most delayed first;
    # area name last as a deterministic tie-break.
    rows.sort(key=lambda r: (-r["delayed_count"], r["area"]))
    return rows


def build_response_facts(
    facts: Sequence[PredictiveActivity],
    activities: Sequence[Activity],
    schedule_name: str,
    reference_date: date,
    format_detected: str,
) -> dict[str, Any]:
    """TL-5.4: the deterministic FACTS half of the final API response.

    Every id, count, date, and classification here is computed from
    `PredictiveActivity`/`Activity` data — the model is never asked to
    produce any of it (brief §4, §15). `UNVERIFIED` facts are counted, not
    detailed, matching `build_predictive_context`'s own rule (module
    docstring) — the two functions share `_confirmed`'s filter so the
    prompt sent to the model and the facts merged into the response can
    never disagree about which activities are confirmed.

    Does not compute `forceable_count`/`not_forceable_count` — those depend
    on `forcing_assessment`, which stays with the model (TL-5.4: "genuinely
    judgemental," `phase-5-predictive-facts.md`). The caller computes those
    two counts after merging the model's `forcing_assessment` response.
    """
    by_id = {a.internal_id: a for a in activities}
    confirmed = _confirmed(facts)
    unverified_count = len(facts) - len(confirmed)

    most_overdue_days = max((f.days_overdue for f in confirmed), default=0)
    project_status, risk_level = classify_project_status(len(confirmed), most_overdue_days)

    areas_covered = sorted({_location_trade(f.internal_id, by_id)[0] for f in confirmed})
    root_causes = [f for f in confirmed if f.is_root_cause]
    downstream = [f for f in confirmed if not f.is_root_cause]

    return {
        "schedule_overview": {
            "schedule_name": schedule_name,
            "reference_date": _format_ddmmyyyy(reference_date),
            "total_activities": len(activities),
            "delayed_count": len(confirmed),
            "areas_covered": areas_covered,
            "format_detected": format_detected,
        },
        "delayed_activities": [_delayed_activity_fact(f, by_id) for f in confirmed],
        "root_cause_analysis": [_root_cause_fact(f, by_id) for f in root_causes],
        "downstream_consequences": [_downstream_consequence_fact(f, by_id) for f in downstream],
        "summary_by_area": _summary_by_area_facts(confirmed, by_id),
        "insight_data": {
            "total_activities": len(activities),
            "delayed_count": len(confirmed),
            "critical_count": sum(1 for f in confirmed if f.priority == CRITICAL_NOW),
            "important_count": sum(1 for f in confirmed if f.priority == IMPORTANT_NEXT),
            "monitor_count": sum(1 for f in confirmed if f.priority == MONITOR),
            "root_cause_count": len(root_causes),
            "reference_date": _format_ddmmyyyy(reference_date),
            "most_overdue_days": most_overdue_days,
            "areas_affected": len(areas_covered),
            "format_detected": format_detected,
            "schedule_name": schedule_name,
            "project_status": project_status,
            "risk_level": risk_level,
            "unverified_delayed_count": unverified_count,
        },
    }
