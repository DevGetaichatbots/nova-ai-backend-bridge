"""Tests for TL-5.2 — Deterministic overdue, priority, and root-cause computation.

Encodes acceptance criteria from
`changes/trust-layer/plan/phase-5-predictive-facts.md` (TL-5.2):
- AC1: `days_overdue`, priority, and root-cause flags all computed in Python.
- AC2: Root cause derived from the dependency graph, with a fixture proving
  the chain (and the prompt's own sanity rule: 3-10 root causes for 20-40
  delays becomes a verifiable property).
- AC3: Post-hoc pruning/ratio-correction in `predictive_agent.analyze()` —
  see ADR-018: deliberately NOT removed yet; deferred to TL-5.4 when the
  live `/predictive` route actually switches to this module. The old code
  is marked superseded in place instead. Not re-tested here (untouched).
- AC4: Counts are stable across repeated runs on the same input (no model
  variance) — trivially true for a pure function, pinned by a determinism
  test anyway per the plan's own discipline.
"""
from __future__ import annotations

from datetime import date, datetime

from ingestion.models.nusf import Activity, ActivityType
from src.trust.predictive_facts import (
    BYGHERRE,
    COORDINATION,
    CRITICAL_NOW,
    DESIGN,
    IMPORTANT_NEXT,
    MILESTONE_TASK_TYPE,
    MONITOR,
    PROCUREMENT,
    PRODUCTION,
    compute_predictive_facts,
    detect_delayed_activities,
)

REF = date(2026, 1, 1)


def _activity(
    internal_id: str,
    planned_start: datetime = datetime(2025, 1, 1),
    planned_finish: datetime = datetime(2025, 1, 10),
    percent_complete: float = 0.0,
    predecessors: list[str] | None = None,
    successors: list[str] | None = None,
    activity_type: ActivityType = ActivityType.TASK,
    name: str | None = None,
) -> Activity:
    return Activity(
        internal_id=internal_id,
        source_id=internal_id,
        name=name if name is not None else f"Activity {internal_id}",
        planned_start=planned_start,
        planned_finish=planned_finish,
        duration_hours=80,
        percent_complete=percent_complete,
        activity_type=activity_type,
        predecessors=predecessors or [],
        successors=successors or [],
        provenance={},
    )


class TestRootCauseFromDependencyGraph:
    """AC2: a linear chain A -> B -> C -> D, all delayed, all 0% progress.
    Only A (no delayed predecessor) is a root cause; B, C, D are each
    blocked by the previous link."""

    def _chain_schedule(self) -> list[Activity]:
        a = _activity("A", planned_start=datetime(2020, 1, 1), successors=["B"])
        b = _activity("B", planned_start=datetime(2020, 1, 1), predecessors=["A"], successors=["C"])
        c = _activity("C", planned_start=datetime(2020, 1, 1), predecessors=["B"], successors=["D"])
        d = _activity("D", planned_start=datetime(2020, 1, 1), predecessors=["C"])
        return [a, b, c, d]

    def test_only_head_of_chain_is_root_cause(self):
        activities = self._chain_schedule()
        delayed = detect_delayed_activities(activities, REF)
        facts = compute_predictive_facts(delayed, activities)
        by_id = {f.internal_id: f for f in facts}

        assert by_id["A"].is_root_cause is True
        assert by_id["A"].blocked_by_id is None
        for downstream_id in ("B", "C", "D"):
            assert by_id[downstream_id].is_root_cause is False

    def test_blocked_by_id_points_to_immediate_delayed_predecessor(self):
        activities = self._chain_schedule()
        delayed = detect_delayed_activities(activities, REF)
        facts = compute_predictive_facts(delayed, activities)
        by_id = {f.internal_id: f for f in facts}

        assert by_id["B"].blocked_by_id == "A"
        assert by_id["C"].blocked_by_id == "B"
        assert by_id["D"].blocked_by_id == "C"

    def test_root_cause_affected_task_ids_include_entire_downstream_chain(self):
        activities = self._chain_schedule()
        delayed = detect_delayed_activities(activities, REF)
        facts = compute_predictive_facts(delayed, activities)
        by_id = {f.internal_id: f for f in facts}

        assert set(by_id["A"].affected_task_ids) == {"B", "C", "D"}
        assert by_id["D"].affected_task_ids == ()  # nothing downstream of the tail

    def test_root_cause_count_stays_low_relative_to_delay_count(self):
        """`PREDICTIVE_SYSTEM_PROMPT` STEP 2's sanity rule: "expect 3-10 root
        causes for 20-40 delays" — verifiable rather than hoped-for. Builds
        4 independent chains of 6 delayed activities each (24 delays total,
        4 root causes), well inside a <40% root-cause ratio."""
        activities: list[Activity] = []
        for chain in range(4):
            prev_id = None
            for i in range(6):
                aid = f"C{chain}-{i}"
                preds = [prev_id] if prev_id else []
                if prev_id:
                    # wire successor on the previous node
                    idx = next(j for j, a in enumerate(activities) if a.internal_id == prev_id)
                    activities[idx] = activities[idx].model_copy(update={"successors": [aid]})
                activities.append(_activity(aid, planned_start=datetime(2020, 1, 1), predecessors=preds))
                prev_id = aid

        delayed = detect_delayed_activities(activities, REF)
        assert len(delayed) == 24
        facts = compute_predictive_facts(delayed, activities)
        root_causes = [f for f in facts if f.is_root_cause]
        assert len(root_causes) == 4
        assert len(root_causes) < len(facts) * 0.4

    def test_activity_with_no_predecessors_is_root_cause(self):
        act = _activity("A", planned_start=datetime(2020, 1, 1))
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].is_root_cause is True
        assert facts[0].blocked_by_id is None
        assert facts[0].affected_task_ids == ()

    def test_predecessor_not_itself_delayed_does_not_block(self):
        """B depends on A, but A is not delayed (recent start) — B is still
        a root cause among the delayed set."""
        a = _activity("A", planned_start=date(2026, 6, 1), successors=["B"])  # not delayed
        b = _activity("B", planned_start=datetime(2020, 1, 1), predecessors=["A"])
        delayed = detect_delayed_activities([a, b], REF)
        facts = compute_predictive_facts(delayed, [a, b])
        assert len(facts) == 1
        assert facts[0].internal_id == "B"
        assert facts[0].is_root_cause is True
        assert facts[0].blocked_by_id is None

    def test_multiple_delayed_predecessors_picks_first_declared(self):
        a = _activity("A", planned_start=datetime(2020, 1, 1), successors=["C"])
        b = _activity("B", planned_start=datetime(2020, 1, 1), successors=["C"])
        c = _activity("C", planned_start=datetime(2020, 1, 1), predecessors=["A", "B"])
        delayed = detect_delayed_activities([a, b, c], REF)
        facts = compute_predictive_facts(delayed, [a, b, c])
        by_id = {f.internal_id: f for f in facts}
        assert by_id["C"].blocked_by_id == "A"

    def test_diamond_dependency_no_infinite_loop(self):
        """A -> B, A -> C, B -> D, C -> D (diamond). Successors visited via
        both paths must not double-loop or crash; D is reachable once."""
        a = _activity("A", planned_start=datetime(2020, 1, 1), successors=["B", "C"])
        b = _activity("B", planned_start=datetime(2020, 1, 1), predecessors=["A"], successors=["D"])
        c = _activity("C", planned_start=datetime(2020, 1, 1), predecessors=["A"], successors=["D"])
        d = _activity("D", planned_start=datetime(2020, 1, 1), predecessors=["B", "C"])
        delayed = detect_delayed_activities([a, b, c, d], REF)
        facts = compute_predictive_facts(delayed, [a, b, c, d])
        by_id = {f.internal_id: f for f in facts}
        assert set(by_id["A"].affected_task_ids) == {"B", "C", "D"}


class TestPriorityClassification:
    def test_root_cause_with_high_overdue_is_critical_now(self):
        act = _activity("A", planned_start=datetime(2020, 1, 1))  # thousands of days overdue
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].priority == CRITICAL_NOW

    def test_root_cause_blocking_many_downstream_is_critical_now(self):
        """Even with a short overdue window, blocking >= 3 downstream
        delayed activities is CRITICAL_NOW."""
        recent = REF.replace(day=1)  # 0 days overdue-ish, still < REF
        head = _activity("A", planned_start=datetime(2025, 12, 31), successors=["B", "C", "D"])
        tail = [
            _activity(x, planned_start=datetime(2020, 1, 1), predecessors=["A"])
            for x in ("B", "C", "D")
        ]
        activities = [head] + tail
        delayed = detect_delayed_activities(activities, REF)
        facts = compute_predictive_facts(delayed, activities)
        by_id = {f.internal_id: f for f in facts}
        assert by_id["A"].priority == CRITICAL_NOW

    def test_downstream_consequence_with_no_further_impact_is_monitor_or_important(self):
        a = _activity("A", planned_start=datetime(2020, 1, 1), successors=["B"])
        b = _activity("B", planned_start=datetime(2025, 12, 30), predecessors=["A"])  # 2 days overdue
        delayed = detect_delayed_activities([a, b], REF)
        facts = compute_predictive_facts(delayed, [a, b])
        by_id = {f.internal_id: f for f in facts}
        # B: not root cause, 2 days overdue (< IMPORTANT threshold), no downstream
        assert by_id["B"].priority == MONITOR

    def test_isolated_short_delay_is_monitor(self):
        act = _activity("A", planned_start=datetime(2025, 12, 30))  # 2 days overdue, no graph
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].priority == MONITOR

    def test_isolated_moderate_delay_is_important_next(self):
        act = _activity("A", planned_start=datetime(2025, 12, 20))  # ~12 days overdue
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].priority == IMPORTANT_NEXT


class TestDeterminism:
    def test_repeated_runs_produce_identical_output(self):
        a = _activity("A", planned_start=datetime(2020, 1, 1), successors=["B"])
        b = _activity("B", planned_start=datetime(2020, 1, 1), predecessors=["A"])
        activities = [a, b]

        run1 = compute_predictive_facts(detect_delayed_activities(activities, REF), activities)
        run2 = compute_predictive_facts(detect_delayed_activities(activities, REF), activities)

        assert run1 == run2

    def test_days_overdue_priority_and_root_cause_all_present_no_llm(self):
        """AC1: every field computed in Python, no external call — trivially
        true since the module makes none, but assert the shape is complete."""
        act = _activity("A", planned_start=datetime(2020, 1, 1))
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        f = facts[0]
        assert isinstance(f.days_overdue, int)
        assert f.priority in (CRITICAL_NOW, IMPORTANT_NEXT, MONITOR)
        assert isinstance(f.is_root_cause, bool)


class TestTaskTypeClassification:
    """TL-5.4: `task_type`/`problem_type` computed in Python
    (`_classify_task_type`), UNCALIBRATED keyword heuristic — not asked of
    the model. See `PredictiveActivity.task_type`/`problem_type`."""

    def test_milestone_activity_type_wins_regardless_of_name(self):
        act = _activity(
            "A", planned_start=datetime(2020, 1, 1),
            activity_type=ActivityType.MILESTONE, name="Bestilling af stål",  # would otherwise match Procurement
        )
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].task_type == MILESTONE_TASK_TYPE
        assert facts[0].problem_type == "Coordination blockage"

    def test_coordination_keyword(self):
        act = _activity("A", planned_start=datetime(2020, 1, 1), name="Koordineringsmøde EL/VVS")
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].task_type == COORDINATION
        assert facts[0].problem_type == "Coordination blockage"

    def test_design_keyword(self):
        act = _activity("A", planned_start=datetime(2020, 1, 1), name="Projektering af facade")
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].task_type == DESIGN
        assert facts[0].problem_type == "Design input missing"

    def test_bygherre_keyword(self):
        act = _activity("A", planned_start=datetime(2020, 1, 1), name="Bygherre godkendelse af farve")
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].task_type == BYGHERRE
        assert facts[0].problem_type == "Bygherre decision pending"

    def test_procurement_keyword(self):
        act = _activity("A", planned_start=datetime(2020, 1, 1), name="Levering af vinduer")
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].task_type == PROCUREMENT
        assert facts[0].problem_type == "Procurement delay"

    def test_no_keyword_match_falls_back_to_production(self):
        act = _activity("A", planned_start=datetime(2020, 1, 1), name="Støbning af beton")
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        assert facts[0].task_type == PRODUCTION
        assert facts[0].problem_type == "Production delay"

    def test_every_task_type_maps_to_a_valid_problem_type(self):
        """The schema's `problem_type` enum has exactly 5 values; every
        `task_type` (including `MILESTONE_TASK_TYPE`, which has no direct
        counterpart) must resolve to one of them."""
        valid_problem_types = {
            "Coordination blockage", "Design input missing", "Bygherre decision pending",
            "Production delay", "Procurement delay",
        }
        for task_type in (COORDINATION, DESIGN, BYGHERRE, PRODUCTION, PROCUREMENT, MILESTONE_TASK_TYPE):
            act = _activity("A", planned_start=datetime(2020, 1, 1), activity_type=(
                ActivityType.MILESTONE if task_type == MILESTONE_TASK_TYPE else ActivityType.TASK
            ), name={
                COORDINATION: "koordinering", DESIGN: "design", BYGHERRE: "bygherre",
                PROCUREMENT: "levering", PRODUCTION: "arbejde", MILESTONE_TASK_TYPE: "arbejde",
            }[task_type])
            delayed = detect_delayed_activities([act], REF)
            facts = compute_predictive_facts(delayed, [act])
            assert facts[0].problem_type in valid_problem_types
