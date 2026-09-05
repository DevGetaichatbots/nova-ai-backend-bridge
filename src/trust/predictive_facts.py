"""Deterministic delayed-activity detection and decision-support facts
(TL-5.1, TL-5.2 — brief §4, §15).

Brief §4 is unambiguous:

    The AI/LLM should not independently "look at the schedule and decide"
    numerical facts whenever those facts can be determined programmatically.
    [...] The LLM's job becomes: explain the truth, rather than
    discover/invent the truth.

This module ports two layers of `src/predictive_agent.py`'s
`PREDICTIVE_SYSTEM_PROMPT` into pure Python over normalized NUSF `Activity`
objects. There is no LLM call anywhere in this module, and none should ever
be added — a task that needs the model to "decide" a fact here is a Phase 5
regression, not a feature.

- **TL-5.1 — DETECTION LAYER (Module A)**: which activities are delayed
  (`detect_delayed_activities`, roughly `PREDICTIVE_SYSTEM_PROMPT` L494-552).
  Two rule sets exist because the source schedule format changes which
  progress signal is trustworthy (see the prompt's "AUTO-DETECT DOCUMENT
  TYPE" section):
  - STANDARD (MS Project / Detailtidsplan / Hybrid): a task is delayed iff
    it started before the reference date and has recorded zero progress.
  - PLANDISC: progress is measured differently (`actual_completion_pct`,
    never `planned_completion_pct` — see `_plandisc_condition`'s docstring
    for why that trap cannot reach this function), and the source system's
    own `is_late` flag is itself a delay signal independent of the calendar.

- **TL-5.2 — DECISION SUPPORT LAYER, deterministic half**:
  `days_overdue` (already computed in TL-5.1), priority classification, and
  root-cause vs. downstream-consequence, all derived from
  `Activity.predecessors`/`successors` (the dependency graph), never from
  model judgement (`PREDICTIVE_SYSTEM_PROMPT`'s PHASE 2 STEP 2/STEP 4,
  roughly L564-584). The forcing-assessment layer (PHASE 3, Module F) stays
  with the model per `phase-5-predictive-facts.md` TL-5.4 — it is genuinely
  judgemental, not a fact.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from ingestion.models.nusf import Activity, ActivityType
from src.trust.engine import TrustAssessment, TrustEngine
from src.trust.vocabulary import TrustState

# --- Detection condition tags -------------------------------------------------
# Brief Module A does not collapse "confidently overdue by the calendar rule"
# and "flagged behind by the source system's own is_late signal" into one
# undifferentiated bucket — downstream consumers (and the review UI, Phase 7)
# may want to explain *why* an activity was flagged differently per condition.

STANDARD = "standard"
PLANDISC_A = "plandisc_a"  # not started, past planned end
PLANDISC_B = "plandisc_b"  # in progress but flagged behind schedule
PLANDISC_C = "plandisc_c"  # started but stalled

_ACCEPTED_STATUS = "accepted"

# Fields the detection rule itself reads, per rule set. Used to build the
# weakest-link trust assessment for each detected activity (brief §14) —
# a delay flagged from an UNVERIFIED `percent_complete` is not itself
# VERIFIED just because the detector ran successfully.
_STANDARD_EVIDENCE_FIELDS = ("planned_start", "percent_complete")
_PLANDISC_EVIDENCE_FIELDS = (
    "planned_finish", "percent_complete", "is_late", "inspected_status", "actual_start",
)


@dataclass(frozen=True)
class DelayedActivity:
    """One deterministically-detected delayed activity (brief §4 Module A).

    `condition` records which rule fired (`STANDARD`, `PLANDISC_A/B/C`) — see
    the module docstring for why that distinction is preserved rather than
    discarded.
    """

    internal_id: str
    source_id: Optional[str]
    name: str
    condition: str
    days_overdue: int
    trust: TrustAssessment


def _is_plandisc_batch(activities: Sequence[Activity]) -> bool:
    """Auto-detect whether this batch of activities came from a Plandisc
    export (`PREDICTIVE_SYSTEM_PROMPT` FORMAT 5).

    `Activity.is_late` and `Activity.inspected_status` are only ever
    populated when the recognizer matched the Plandisc-exclusive column
    names `is_late` / `inspectedType` — see
    `ingestion/recognition/heuristics.py`'s `COLUMN_HEURISTICS["is_late"]`
    and `["inspected_type"]`; no other supported format has these columns.
    A schedule is one format throughout, so any activity in the batch
    carrying either field non-`None` means the whole batch is Plandisc.

    `Activity.match_method == "name_location_composite"` was considered as
    the signal and rejected: `ingestion/normalization/engine.py` also
    assigns that exact value on an unrelated fallback branch (any
    non-durable match key that isn't `"id"`/`"row_index"` with no derivable
    stable key), so it is not exclusive to Plandisc rows and would
    misclassify some non-Plandisc schedules.
    """
    return any(a.is_late is not None or a.inspected_status is not None for a in activities)


def _is_summary_row(activity: Activity) -> bool:
    """Grouping/summary header rows are excluded from standard-format
    detection (brief: "Omr. 1", "E100.01 Ventilation", "Globals", ...).
    Milestones are deliberately NOT excluded — the brief explicitly keeps
    0d coordination milestones in scope for standard-format detection."""
    return activity.activity_type == ActivityType.SUMMARY


def _standard_is_delayed(activity: Activity, reference_date: date) -> bool:
    """Standard-format rule (MS Project / Detailtidsplan / Hybrid):
    BOTH `planned_start < reference_date` AND `percent_complete == 0`.
    No duration filter, no importance filter, no exemption for very old
    or very recent starts — matches the prompt's own PASS 1-4 verbatim:
    "If an activity started in 2020 and still has 0% — it is delayed."
    """
    if _is_summary_row(activity):
        return False
    return activity.planned_start.date() < reference_date and activity.percent_complete == 0.0


def _plandisc_condition(activity: Activity, reference_date: date) -> Optional[str]:
    """Plandisc-format rule: delayed iff Condition A, B, or C holds, after
    the format's own exclusions (fully complete, or signed off).

    `percent_complete` here IS `actual_completion_pct`. Normalization
    (TL-1.*) maps only `actual_completion_pct` into `Activity.percent_complete`
    — `ingestion/recognition/heuristics.py`'s
    `COLUMN_HEURISTICS["percent_complete"]` lists `actual_completion_pct`
    and never lists `planned_completion_pct`. The prompt's own trap warning
    ("planned_completion_pct is always 100 for a normal task and must never
    be read as progress") therefore cannot reach this function: the value
    it warns about was never routed here in the first place. This function
    does not need to guard against it again, only rely on the upstream
    contract holding.
    """
    inspected = (activity.inspected_status or "").strip().lower()
    if inspected == _ACCEPTED_STATUS or activity.percent_complete >= 100.0:
        return None  # signed off, or fully complete — never delayed

    # Condition A — not started, past planned end.
    if activity.planned_finish.date() < reference_date and activity.percent_complete == 0.0:
        return PLANDISC_A

    # Condition B — in progress but flagged behind schedule. Fires even when
    # `planned_finish` is still in the future: the brief treats "running
    # slower than planned" as itself the delay signal, independent of
    # whether the deadline has already passed.
    if activity.is_late and activity.percent_complete < 100.0:
        return PLANDISC_B

    # Condition C — started but stalled.
    if (
        activity.actual_start is not None
        and activity.percent_complete == 0.0
        and activity.planned_finish.date() < reference_date
    ):
        return PLANDISC_C

    return None


def _days_overdue(activity: Activity, reference_date: date, condition: str) -> int:
    """Standard formats measure overdue from `planned_start`. Plandisc
    measures from `planned_finish`, because `planned_start` may be far in
    the past for a multi-month revised schedule and would overstate the
    overdue window. A Condition-B row may fire while `planned_finish` is
    still in the future — the brief is explicit that such a row is still
    delayed, but `days_overdue` is 0: there is no calendar overdue window
    yet, only a progress-curve signal from the source system."""
    if condition == STANDARD:
        return max((reference_date - activity.planned_start.date()).days, 0)
    finish = activity.planned_finish.date()
    if finish >= reference_date:
        return 0
    return (reference_date - finish).days


def _assess_delay_trust(activity: Activity, condition: str, engine: TrustEngine) -> TrustAssessment:
    """Weakest-link trust (brief §14) across every field the detection rule
    actually read for this activity. A delay flagged from an UNVERIFIED
    `percent_complete` is not itself VERIFIED just because the detector ran.

    When a field the rule read has no recorded `Provenance` entry, this
    treats it as UNVERIFIED evidence directly rather than calling
    `TrustEngine.assess_value` with `provenance=None` and an empty
    `extraction_method` — that combination hits `assess_value`'s
    "no evidence supplied at all" default, which resolves to VERIFIED
    (see `src/trust/engine.py` Rule 3's final `or not method` branch). That
    default is reasonable for "caller didn't pass anything", but here a
    missing entry means "this field was read and is missing real
    provenance", which must never be reported as VERIFIED (brief's
    "unknown = 1.0" failure mode, applied to trust state rather than a
    confidence number).
    """
    fields = _STANDARD_EVIDENCE_FIELDS if condition == STANDARD else _PLANDISC_EVIDENCE_FIELDS
    assessments: list[TrustAssessment] = []
    for field_name in fields:
        prov = activity.provenance.get(field_name)
        if prov is None:
            assessments.append(
                TrustAssessment(
                    state=TrustState.UNVERIFIED,
                    reason=f"No provenance recorded for field '{field_name}'",
                    weakest_link=field_name,
                    evidence_chain=[{"type": "missing_provenance", "field": field_name}],
                )
            )
            continue
        assessments.append(
            engine.assess_value(
                field_name=field_name,
                value=getattr(activity, field_name, None),
                provenance=prov,
                is_ai_inferred=prov.is_ai_inferred,
                extraction_method=prov.extraction_method,
            )
        )
    return engine.propagate(assessments)


def detect_delayed_activities(
    activities: Sequence[Activity],
    reference_date: date,
    trust_engine: Optional[TrustEngine] = None,
) -> list[DelayedActivity]:
    """Deterministic port of Module A (brief §4, §15). Pure Python, no LLM.

    Scans every activity in `activities` — brief PASS 1: "Read EVERY row.
    Do NOT stop after finding a few." There is no sampling, no truncation,
    and no cap on how many activities can be returned: if 50 activities
    share a start date and are all 0% complete, all 50 come back.

    Auto-detects standard vs. Plandisc rules once for the whole batch (see
    `_is_plandisc_batch`); a batch mixing both formats is not a case any
    current extractor produces (one schedule, one format).
    """
    engine = trust_engine or TrustEngine()
    is_plandisc = _is_plandisc_batch(activities)
    results: list[DelayedActivity] = []

    for activity in activities:
        if is_plandisc:
            condition = _plandisc_condition(activity, reference_date)
            if condition is None:
                continue
        else:
            if not _standard_is_delayed(activity, reference_date):
                continue
            condition = STANDARD

        results.append(
            DelayedActivity(
                internal_id=activity.internal_id,
                source_id=activity.source_id,
                name=activity.name,
                condition=condition,
                days_overdue=_days_overdue(activity, reference_date, condition),
                trust=_assess_delay_trust(activity, condition, engine),
            )
        )

    return results


# ============================================================================
# TL-5.2 — Deterministic overdue, priority, and root-cause computation
# ============================================================================
# `days_overdue` is already computed above (TL-5.1). What remains — priority
# bucketing and root-cause-vs-downstream-consequence — is what
# `PREDICTIVE_SYSTEM_PROMPT` PHASE 2 currently asks the model to infer from a
# text dump. Both are mechanical once the dependency graph is available:
# `Activity.predecessors` / `Activity.successors` already carry it.

CRITICAL_NOW = "CRITICAL_NOW"
IMPORTANT_NEXT = "IMPORTANT_NEXT"
MONITOR = "MONITOR"

# Priority thresholds. Named, documented placeholders — brief §7 applies to
# Phase 5 the same way it applies to `TL-3.3`'s `_AMBIGUITY_MARGIN_DAYS`:
# "these numbers are starting hypotheses, not final thresholds." No
# EXT-1-equivalent golden dataset exists yet for predictive priority
# calibration; these are UNCALIBRATED and must not be described as tuned.
# Chosen to mirror the prompt's own prose (PHASE 2 STEP 4): CRITICAL_NOW
# needs *both* root-cause status and either a long overdue window or a wide
# blast radius; IMPORTANT_NEXT is "significant delay, may block some work";
# everything else is MONITOR.
_CRITICAL_DAYS_OVERDUE_UNCALIBRATED = 14
_CRITICAL_AFFECTED_COUNT_UNCALIBRATED = 3
_IMPORTANT_DAYS_OVERDUE_UNCALIBRATED = 3

# --- Task-type classification (TL-5.4) --------------------------------------
# `PREDICTIVE_SYSTEM_PROMPT` PHASE 2 STEP 1 asks the model to classify each
# delayed activity's `task_type`; brief §15 says anything computable in code
# should not be. Keyword matching on the activity name is a modest,
# deterministic stand-in — not a semantic understanding of the task, just a
# reproducible rule. UNCALIBRATED: the keyword lists are a starting
# hypothesis (brief §7's posture applied to classification, not just numeric
# thresholds), not a validated taxonomy. EN + DA because schedules in this
# pipeline are bilingual (see `PREDICTIVE_SYSTEM_PROMPT`'s own Danish
# examples throughout).
COORDINATION = "Coordination"
DESIGN = "Design"
BYGHERRE = "Bygherre"
PRODUCTION = "Production"
PROCUREMENT = "Procurement"
MILESTONE_TASK_TYPE = "Milestone"

_TASK_TYPE_KEYWORDS_UNCALIBRATED: dict[str, tuple[str, ...]] = {
    COORDINATION: ("koordinering", "coordination", "møde", "meeting", "grænseflade", "interface"),
    DESIGN: ("projektering", "design", "tegning", "drawing", "specifikation", "spec", "data sheet"),
    BYGHERRE: ("bygherre", "client", "godkendelse", "approval", "beslutning", "decision"),
    PROCUREMENT: ("bestilling", "levering", "delivery", "procurement", "indkøb", "order"),
}

# `problem_type` (used in root-cause narrative grounding) is a coarser
# restatement of `task_type` against the fixed 5-value enum
# `NOVA_INSIGHT_SCHEMA` already declares. `MILESTONE_TASK_TYPE` has no direct
# counterpart in that enum — milestones are almost always decision/
# coordination gates in this domain (brief's own Rule 5 in
# `PREDICTIVE_SYSTEM_PROMPT` treats them as such), so it maps to
# "Coordination blockage" rather than inventing a sixth enum value the
# existing schema (and every consumer of it) does not expect.
_PROBLEM_TYPE_FOR_TASK_TYPE: dict[str, str] = {
    COORDINATION: "Coordination blockage",
    DESIGN: "Design input missing",
    BYGHERRE: "Bygherre decision pending",
    PRODUCTION: "Production delay",
    PROCUREMENT: "Procurement delay",
    MILESTONE_TASK_TYPE: "Coordination blockage",
}


def _classify_task_type(activity: Activity) -> str:
    """Deterministic, UNCALIBRATED task-type classification (see module-
    level constants above). Milestone status (from `Activity.activity_type`,
    itself already deterministic — `ingestion/normalization/engine.py`
    `_detect_activity_type`) takes priority over keyword matching: a
    zero-duration coordination gate is a milestone regardless of what its
    name happens to contain. Falls back to `PRODUCTION` — physical
    construction/installation work — when no keyword matches, since that is
    the majority case in a typical schedule and is the prompt's own implicit
    default (`PREDICTIVE_SYSTEM_PROMPT` STEP 1 lists it last)."""
    if activity.activity_type == ActivityType.MILESTONE:
        return MILESTONE_TASK_TYPE
    name_lower = activity.name.lower()
    for task_type, keywords in _TASK_TYPE_KEYWORDS_UNCALIBRATED.items():
        if any(kw in name_lower for kw in keywords):
            return task_type
    return PRODUCTION


@dataclass(frozen=True)
class PredictiveActivity(DelayedActivity):
    """A `DelayedActivity` (TL-5.1) plus the TL-5.2/TL-5.4 decision-support
    facts.

    `is_root_cause` / `blocked_by_id` / `affected_task_ids` come from the
    dependency graph, never from model judgement (brief §4, §15).
    `task_type` / `problem_type` come from `_classify_task_type` — a
    deterministic (if UNCALIBRATED) heuristic, not model judgement either.
    """

    is_root_cause: bool
    blocked_by_id: Optional[str]
    affected_task_ids: tuple[str, ...]
    priority: str
    task_type: str
    problem_type: str


def _blocking_predecessor(activity: Activity, delayed_ids: frozenset[str]) -> Optional[str]:
    """The first predecessor (in the activity's own declared order — itself
    deterministic, coming from source data order) that is also delayed.

    `PREDICTIVE_SYSTEM_PROMPT` STEP 2: "If task B depends on task A, and both
    are delayed → A is the root cause, B is the downstream consequence." A
    row can have more than one delayed predecessor; the first one in
    declared order is reported — the prompt does not specify a tie-break
    either, and declared order is the only deterministic one available
    without inventing a secondary ranking.
    """
    return next((p for p in activity.predecessors if p in delayed_ids), None)


def _transitive_delayed_successors(
    start_id: str, by_id: dict[str, Activity], delayed_ids: frozenset[str]
) -> list[str]:
    """Delayed activities transitively reachable via `successors` from
    `start_id` (excluding `start_id` itself) — the "how many downstream
    tasks may slip" question from `PREDICTIVE_SYSTEM_PROMPT` STEP 3.

    Breadth-first with a visited set: `TL-0.5`/Rule 102 rejects cyclic
    schedules at ingestion (`validation_passed = False`), so a cycle here
    would indicate a schedule that should never have reached this function —
    the visited set is defence in depth, not a documented cyclic case.
    """
    start = by_id.get(start_id)
    if start is None:
        return []
    visited: set[str] = set()
    queue: list[str] = list(start.successors)
    delayed_downstream: list[str] = []
    while queue:
        next_id = queue.pop(0)
        if next_id in visited:
            continue
        visited.add(next_id)
        if next_id in delayed_ids:
            delayed_downstream.append(next_id)
        next_activity = by_id.get(next_id)
        if next_activity is not None:
            queue.extend(next_activity.successors)
    return delayed_downstream


def _classify_priority(is_root_cause: bool, days_overdue: int, affected_count: int) -> str:
    """`PREDICTIVE_SYSTEM_PROMPT` PHASE 2 STEP 4:
    - CRITICAL_NOW: root cause, high overdue, blocks multiple downstream.
    - IMPORTANT_NEXT: significant delay, may block some work.
    - MONITOR: lower-priority, isolated, or downstream consequence.
    """
    if is_root_cause and (
        days_overdue >= _CRITICAL_DAYS_OVERDUE_UNCALIBRATED
        or affected_count >= _CRITICAL_AFFECTED_COUNT_UNCALIBRATED
    ):
        return CRITICAL_NOW
    if days_overdue >= _IMPORTANT_DAYS_OVERDUE_UNCALIBRATED or affected_count >= 1:
        return IMPORTANT_NEXT
    return MONITOR


def compute_predictive_facts(
    delayed: Sequence[DelayedActivity],
    activities: Sequence[Activity],
) -> list[PredictiveActivity]:
    """TL-5.2: attach priority, root-cause classification, and downstream
    impact to every activity `detect_delayed_activities` (TL-5.1) already
    flagged. Pure Python, dependency-graph-driven, no LLM.

    `activities` is the full schedule (not just `delayed`) because
    `predecessors`/`successors` reference `internal_id`s that may belong to
    non-delayed activities — a delayed task can be blocked by (or block) a
    task that isn't itself late.
    """
    by_id = {a.internal_id: a for a in activities}
    delayed_ids = frozenset(d.internal_id for d in delayed)

    results: list[PredictiveActivity] = []
    for d in delayed:
        activity = by_id.get(d.internal_id)
        blocked_by_id = _blocking_predecessor(activity, delayed_ids) if activity is not None else None
        is_root_cause = blocked_by_id is None
        affected_task_ids = tuple(_transitive_delayed_successors(d.internal_id, by_id, delayed_ids))
        priority = _classify_priority(is_root_cause, d.days_overdue, len(affected_task_ids))
        task_type = _classify_task_type(activity) if activity is not None else PRODUCTION
        problem_type = _PROBLEM_TYPE_FOR_TASK_TYPE[task_type]

        results.append(
            PredictiveActivity(
                internal_id=d.internal_id,
                source_id=d.source_id,
                name=d.name,
                condition=d.condition,
                days_overdue=d.days_overdue,
                trust=d.trust,
                is_root_cause=is_root_cause,
                blocked_by_id=blocked_by_id,
                affected_task_ids=affected_task_ids,
                priority=priority,
                task_type=task_type,
                problem_type=problem_type,
            )
        )

    return results


# ============================================================================
# TL-5.4 — Deterministic project-level status/risk classification
# ============================================================================
# `NOVA_INSIGHT_SCHEMA.insight_data.project_status`/`risk_level` were
# previously left to the model, then corrected post-hoc by
# `predictive_agent.analyze()`'s "sanity fix" block (brief §4/§15's exact
# anti-pattern — a Python patch bolted onto an LLM guess instead of a
# computation). This ports that same thresholding logic here unchanged, as a
# named, documented, UNCALIBRATED classifier `src/trust/context.py`'s
# `build_response_facts` can call directly — no model step at all, per
# TL-5.4 (the narrative layer never invents these two fields).

PROJECT_STATUS_STABLE = "STABLE"
PROJECT_STATUS_AT_RISK = "AT_RISK"
PROJECT_STATUS_CRITICAL = "CRITICAL"

RISK_LEVEL_LOW = "LOW"
RISK_LEVEL_MEDIUM = "MEDIUM"
RISK_LEVEL_HIGH = "HIGH"

# Thresholds ported verbatim from the correction block this classifier
# replaces (`predictive_agent.py`, pre-TL-5.4): >15 delayed or >60 days
# overdue on the worst activity -> CRITICAL/HIGH; >=5 delayed or >30 days
# -> AT_RISK/MEDIUM; otherwise STABLE/LOW. Not recalibrated here — porting
# and recalibrating in the same change would conflate "made deterministic"
# with "changed the numbers," which is a separate decision this task does
# not make. UNCALIBRATED per brief §7, same posture as every other
# threshold in this module; no EXT-1-equivalent dataset exists for this
# either.
_PROJECT_CRITICAL_DELAYED_COUNT_UNCALIBRATED = 15
_PROJECT_CRITICAL_DAYS_OVERDUE_UNCALIBRATED = 60
_PROJECT_AT_RISK_DELAYED_COUNT_UNCALIBRATED = 5
_PROJECT_AT_RISK_DAYS_OVERDUE_UNCALIBRATED = 30


def classify_project_status(confirmed_delayed_count: int, most_overdue_days: int) -> tuple[str, str]:
    """`(project_status, risk_level)` for the project as a whole, from two
    already-deterministic aggregates (confirmed delayed count, worst
    `days_overdue` among them). Pure function, no LLM, no per-activity
    detail needed."""
    if (
        confirmed_delayed_count > _PROJECT_CRITICAL_DELAYED_COUNT_UNCALIBRATED
        or most_overdue_days > _PROJECT_CRITICAL_DAYS_OVERDUE_UNCALIBRATED
    ):
        return PROJECT_STATUS_CRITICAL, RISK_LEVEL_HIGH
    if (
        confirmed_delayed_count >= _PROJECT_AT_RISK_DELAYED_COUNT_UNCALIBRATED
        or most_overdue_days > _PROJECT_AT_RISK_DAYS_OVERDUE_UNCALIBRATED
    ):
        return PROJECT_STATUS_AT_RISK, RISK_LEVEL_MEDIUM
    return PROJECT_STATUS_STABLE, RISK_LEVEL_LOW
