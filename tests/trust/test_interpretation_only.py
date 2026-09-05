"""Tests for TL-5.4 — Demote `predictive_agent` to interpretation-only.

Encodes acceptance criteria from
`changes/trust-layer/plan/phase-5-predictive-facts.md` (TL-5.4):
- AC1: Schema separates supplied facts from generated narrative.
- AC2: Prompt contains no fact-extraction instructions.
- AC3: Model output contains no activity ID absent from the supplied context.
- AC4: Determinism settings unchanged (`temperature=0, top_p=0.1, seed=42`).
- AC5: Predictive counts on every fixture match Phase 5's deterministic
  values exactly.

No live Azure OpenAI call is made anywhere in this module (matching every
other test in `tests/trust/`) — `TestDeterminismAndWiring` patches
`src.predictive_agent.AzureOpenAI` itself, before `PredictiveAgent()` is
constructed, so no real credentials are touched. Everything else in this
file drives `_merge_narrative_into_facts` directly: it is a pure function
(no LLM, no I/O), which is exactly what makes AC3's enforcement testable
without a live model in the loop (brief §34 — the prompt instruction is
necessary but not sufficient; this is the sufficient part).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ingestion.models.nusf import Activity, ActivityType, Provenance
from src.predictive_agent import (
    NOVA_NARRATIVE_SCHEMA,
    PREDICTIVE_NARRATIVE_SYSTEM_PROMPT,
    _FALLBACK_NARRATIVE_TEXT,
    _NO_ROOT_CAUSE_RISK,
    _merge_narrative_into_facts,
)
from src.trust.context import build_predictive_context, build_response_facts
from src.trust.predictive_facts import compute_predictive_facts, detect_delayed_activities

REF = date(2026, 1, 1)


def _activity(
    internal_id: str,
    name: str = "Activity",
    planned_start: datetime = datetime(2020, 1, 1),
    planned_finish: datetime = datetime(2020, 1, 10),
    area: str | None = "NK",
    discipline: str | None = "EL",
    predecessors: list[str] | None = None,
    successors: list[str] | None = None,
) -> Activity:
    prov = Provenance(source_field="x", extraction_method="csv_cell")
    return Activity(
        internal_id=internal_id,
        source_id=internal_id,
        name=name,
        planned_start=planned_start,
        planned_finish=planned_finish,
        duration_hours=80,
        percent_complete=0.0,
        activity_type=ActivityType.TASK,
        predecessors=predecessors or [],
        successors=successors or [],
        area=area,
        discipline=discipline,
        provenance={"planned_start": prov, "percent_complete": prov},
    )


def _facts_for(activities: list[Activity]):
    delayed = detect_delayed_activities(activities, REF)
    return compute_predictive_facts(delayed, activities)


class TestSchemaSeparation:
    """AC1: the narrative schema cannot express a fact."""

    def test_narrative_schema_top_level_has_no_fact_fields(self):
        required = set(NOVA_NARRATIVE_SCHEMA["schema"]["required"])
        # None of the old FACTS-half keys survive into the narrative schema.
        for fact_key in ("schedule_overview", "delayed_activities", "downstream_consequences", "insight_data"):
            assert fact_key not in required

    def test_narrative_schema_required_set_is_exactly_narrative_fields(self):
        assert set(NOVA_NARRATIVE_SCHEMA["schema"]["required"]) == {
            "predictive_snapshot",
            "predictive_biggest_risk",
            "executive_actions",
            "management_conclusion",
            "root_cause_narratives",
            "priority_actions",
            "resource_assessment",
            "forcing_assessment",
            "summary_by_area_narratives",
            "insight_narrative",
        }

    def test_root_cause_narratives_carries_no_fact_fields(self):
        """The narrative half of root-cause analysis is text only — id,
        task_name, days_overdue, affected_task_ids (all facts) are not
        askable of the model here; they come from `build_response_facts`."""
        props = set(NOVA_NARRATIVE_SCHEMA["schema"]["properties"]["root_cause_narratives"]["items"]["properties"].keys())
        assert props == {"id", "why_it_matters", "downstream_impact", "consequence_if_unresolved"}

    def test_forcing_assessment_drops_task_name_and_human_label(self):
        """Facts (`task_name`, `human_label`) are backfilled from
        `build_response_facts` in the merge, not asked of the model."""
        props = NOVA_NARRATIVE_SCHEMA["schema"]["properties"]["forcing_assessment"]["items"]["properties"]
        assert "task_name" not in props
        assert "human_label" not in props
        # The judgement fields (genuinely the model's job, brief's own
        # "genuinely judgemental" carve-out) are still all present.
        for judgement_field in ("is_forceable", "constraint_type", "reason", "risk_if_forced", "recommendation"):
            assert judgement_field in props

    def test_every_object_schema_is_strict(self):
        """Every object in the narrative schema is `additionalProperties:
        False` with every property required — Azure's structured-output
        strict-mode contract, same discipline as `NOVA_INSIGHT_SCHEMA`."""

        def _walk(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    assert node.get("additionalProperties") is False, node
                    assert set(node.get("required", [])) == set(node.get("properties", {}).keys())
                for value in node.values():
                    _walk(value)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(NOVA_NARRATIVE_SCHEMA["schema"])


class TestPromptHasNoFactExtractionInstructions:
    """AC2."""

    def test_no_detection_rule_language(self):
        forbidden_phrases = [
            "AUTO-DETECT DOCUMENT TYPE",
            "PASS 1: Scan EVERY",
            "PASS 2: Filter candidates",
            "DETECTION RULE — STANDARD FORMATS",
            "ADAPTIVE COLUMN MAPPING",
            "CRITICAL ID RULE",
            "FORMAT 1: MS PROJECT EXPORT",
        ]
        for phrase in forbidden_phrases:
            assert phrase not in PREDICTIVE_NARRATIVE_SYSTEM_PROMPT, f"found fact-extraction instruction: {phrase!r}"

    def test_contains_the_no_invention_rule(self):
        assert "NEVER invent an id" in PREDICTIVE_NARRATIVE_SYSTEM_PROMPT

    def test_contains_explain_only_supplied_facts_directive(self):
        """Brief §17's exact directive must be present in substance: the
        model does not detect, count, or decide facts — only explain them."""
        assert "you do not detect delays" in PREDICTIVE_NARRATIVE_SYSTEM_PROMPT.lower()


class TestMergeEnforcesNoInventedIds:
    """AC3 — the load-bearing test class. `_merge_narrative_into_facts` is
    the enforcement; the prompt instruction alone (brief §34) is not
    trusted to hold on its own."""

    def _response_facts(self):
        activities = [
            _activity("A1", name="Root cause task"),
            _activity("A2", name="Downstream task", predecessors=["A1"]),
        ]
        facts = _facts_for(activities)
        return build_response_facts(facts, activities, "Test Schedule", REF, "NUSF"), activities, facts

    def _structured_context(self, facts, activities):
        return build_predictive_context(facts, activities, REF)

    def test_invented_ids_are_dropped_from_every_field(self):
        response_facts, activities, facts = self._response_facts()
        structured_context = self._structured_context(facts, activities)

        narrative = {
            "root_cause_narratives": [
                {"id": "A1", "why_it_matters": "Blocks everything", "downstream_impact": "EL trade", "consequence_if_unresolved": "Cascades"},
                {"id": "GHOST-1", "why_it_matters": "invented", "downstream_impact": "invented", "consequence_if_unresolved": "invented"},
            ],
            "resource_assessment": [
                {"id": "A1", "resource_type": "coordination_bottleneck", "assessment": "Needs a meeting"},
                {"id": "GHOST-2", "resource_type": "production_manpower", "assessment": "invented"},
            ],
            "forcing_assessment": [
                {"id": "A1", "is_forceable": "not_recommended", "constraint_type": "coordination_dependency", "reason": "r", "risk_if_forced": "rf", "recommendation": "rec", "coordination_cost": "high", "parallelizability": "low", "max_speedup_factor": "1.0x", "optimal_team_size": "N/A", "point_of_no_return": "N/A"},
                {"id": "GHOST-3", "is_forceable": "possible", "constraint_type": "execution_capacity", "reason": "invented", "risk_if_forced": "invented", "recommendation": "invented", "coordination_cost": "low", "parallelizability": "high", "max_speedup_factor": "2.0x", "optimal_team_size": "2-3", "point_of_no_return": "invented"},
            ],
            "executive_actions": [
                {"rank": 1, "action": "Escalate", "responsible": "PM", "deadline": "Thursday", "related_task_ids": ["A1", "GHOST-4"], "manpower_helps": False, "manpower_note": "n/a"},
            ],
            "summary_by_area_narratives": [{"area": "NK", "summary": "Area NK is behind."}],
            "predictive_snapshot": {"what_will_happen": "x", "estimated_delay_impact": "+2 weeks", "confidence_level": "HIGH", "confidence_basis": "y", "main_delay_drivers": ["a", "b", "c"]},
            "predictive_biggest_risk": {"risk_title": "A1 is late", "will_block": "EL work", "prevent_action_now": "Escalate A1"},
            "management_conclusion": "Conclusion.",
            "priority_actions": [{"step": 1, "action": "Do X", "action_type": "coordination"}],
            "insight_narrative": {"primary_risk": "A1", "critical_findings": ["a", "b", "c"], "consequences_if_no_action": ["a", "b", "c"]},
        }

        result = _merge_narrative_into_facts(response_facts, structured_context, narrative)
        serialized = json.dumps(result)

        for ghost_id in ("GHOST-1", "GHOST-2", "GHOST-3", "GHOST-4"):
            assert ghost_id not in serialized, f"invented id {ghost_id!r} leaked into merged response"

        assert [r["id"] for r in result["root_cause_analysis"]] == ["A1"]
        assert result["root_cause_analysis"][0]["why_it_matters"] == "Blocks everything"
        assert [r["id"] for r in result["resource_assessment"]] == ["A1"]
        assert [r["id"] for r in result["forcing_assessment"]] == ["A1"]
        assert result["executive_actions"][0]["related_task_ids"] == ["A1"]

    def test_facts_backfilled_onto_narrative_entries(self):
        """`task_name`/`human_label` in `resource_assessment`/
        `forcing_assessment` come from facts, never from the model — the
        narrative schema does not even offer the model a place to put them
        (see `TestSchemaSeparation`)."""
        response_facts, activities, facts = self._response_facts()
        structured_context = self._structured_context(facts, activities)
        narrative = {
            "resource_assessment": [{"id": "A1", "resource_type": "coordination_bottleneck", "assessment": "x"}],
            "forcing_assessment": [{"id": "A1", "is_forceable": "not_recommended", "constraint_type": "coordination_dependency", "reason": "r", "risk_if_forced": "rf", "recommendation": "rec", "coordination_cost": "high", "parallelizability": "low", "max_speedup_factor": "1.0x", "optimal_team_size": "N/A", "point_of_no_return": "N/A"}],
        }
        result = _merge_narrative_into_facts(response_facts, structured_context, narrative)
        assert result["resource_assessment"][0]["task_name"] == "Root cause task"
        assert result["forcing_assessment"][0]["task_name"] == "Root cause task"

    def test_facts_pass_through_untouched_by_narrative(self):
        """AC5: delayed_activities / schedule_overview / downstream_consequences
        are never influenced by the model's response at all."""
        response_facts, activities, facts = self._response_facts()
        structured_context = self._structured_context(facts, activities)
        result = _merge_narrative_into_facts(response_facts, structured_context, {})
        assert result["delayed_activities"] == response_facts["delayed_activities"]
        assert result["schedule_overview"] == response_facts["schedule_overview"]
        assert result["downstream_consequences"] == response_facts["downstream_consequences"]

    def test_missing_narrative_entry_falls_back_not_fabricated(self):
        """If the model's response omits a root cause the facts say exists,
        the gap is filled with a fixed, honest placeholder — never a
        fabricated-sounding sentence invented ad hoc."""
        response_facts, activities, facts = self._response_facts()
        structured_context = self._structured_context(facts, activities)
        result = _merge_narrative_into_facts(response_facts, structured_context, {"root_cause_narratives": []})
        assert result["root_cause_analysis"][0]["why_it_matters"] == _FALLBACK_NARRATIVE_TEXT
        assert result["root_cause_analysis"][0]["downstream_impact"] == _FALLBACK_NARRATIVE_TEXT

    def test_no_confirmed_root_cause_overrides_narrative_defensively(self):
        """When `biggest_risk_candidate` is `None`, the merge overrides
        `predictive_biggest_risk` with a fixed fallback regardless of what
        the model wrote — there is nothing supplied to ground free text
        against, so free text is not trusted even if it looks plausible."""
        activities = [_activity("A1", name="Isolated non-root-cause-only fixture")]
        # Force zero confirmed root causes by using an activity with a
        # predecessor that is itself delayed, so A1 is a downstream
        # consequence, not a root cause — then biggest_risk_candidate is
        # None because there are no root causes in the confirmed set.
        blocked = _activity("A2", name="Blocked task", predecessors=["A1"])
        facts = _facts_for([activities[0], blocked])
        response_facts = build_response_facts(facts, [activities[0], blocked], "Test", REF, "NUSF")
        structured_context = build_predictive_context(facts, [activities[0], blocked], REF)
        assert structured_context["biggest_risk_candidate"] is not None  # A1 IS the root cause here — sanity check the fixture

        # Now force the no-root-cause case directly at the merge boundary,
        # independent of how build_predictive_context happens to classify
        # this particular fixture — the merge's own defensive override is
        # what this test actually pins.
        structured_context_no_risk = {**structured_context, "biggest_risk_candidate": None}
        narrative = {"predictive_biggest_risk": {"risk_title": "Invented risk naming a real-looking id", "will_block": "x", "prevent_action_now": "y"}}
        result = _merge_narrative_into_facts(response_facts, structured_context_no_risk, narrative)
        assert result["predictive_biggest_risk"] == _NO_ROOT_CAUSE_RISK


class TestPredictiveCountsMatchPhase5Exactly:
    """AC5, end to end through the real deterministic pipeline (not a
    hand-built fixture) — `detect_delayed_activities` ->
    `compute_predictive_facts` -> `build_response_facts`, merged with an
    empty narrative, must report exactly the same counts Phase 5's own
    functions compute."""

    def test_counts_match_across_repeated_runs(self):
        activities = [_activity(f"A{i}", name=f"Task {i}") for i in range(5)]
        facts = _facts_for(activities)
        response_facts = build_response_facts(facts, activities, "Schedule", REF, "NUSF")
        structured_context = build_predictive_context(facts, activities, REF)

        result1 = _merge_narrative_into_facts(response_facts, structured_context, {})
        result2 = _merge_narrative_into_facts(response_facts, structured_context, {})
        assert result1 == result2  # deterministic merge, no model variance possible

        assert result1["insight_data"]["delayed_count"] == len(facts)
        assert result1["insight_data"]["critical_count"] == sum(1 for f in facts if f.priority == "CRITICAL_NOW")
        assert result1["insight_data"]["root_cause_count"] == sum(1 for f in facts if f.is_root_cause)
        assert len(result1["delayed_activities"]) == len(facts)


class TestDeterminismAndWiring:
    """AC4, plus a full (mocked) round trip through `analyze_from_facts` to
    prove the schema/prompt/merge are actually wired together correctly.
    `AzureOpenAI` is patched before `PredictiveAgent()` is constructed —
    no real credentials are read, no network call is made."""

    def _agent_with_fake_client(self, narrative_payload: dict):
        with patch("src.predictive_agent.AzureOpenAI") as fake_azure_cls:
            fake_client = MagicMock()
            fake_azure_cls.return_value = fake_client
            from src.predictive_agent import PredictiveAgent

            agent = PredictiveAgent()

        fake_message = SimpleNamespace(content=json.dumps(narrative_payload), refusal=None)
        fake_choice = SimpleNamespace(message=fake_message, finish_reason="stop")
        fake_response = SimpleNamespace(choices=[fake_choice], usage=None, model="fake-deployment")
        agent.client.chat.completions.create.return_value = fake_response
        return agent

    def test_temperature_top_p_seed_unchanged_and_narrative_schema_used(self):
        agent = self._agent_with_fake_client({})

        activities = [_activity("A1", name="Root cause task")]
        facts = _facts_for(activities)
        response_facts = build_response_facts(facts, activities, "Schedule", REF, "NUSF")
        structured_context = build_predictive_context(facts, activities, REF)

        result = agent.analyze_from_facts(
            structured_context=structured_context,
            response_facts=response_facts,
            user_query="Explain the supplied facts.",
            language="en",
            schedule_filename="Schedule",
            reference_date=REF.isoformat(),
        )

        assert result["status"] == "success"
        kwargs = agent.client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0
        assert kwargs["top_p"] == 0.1
        assert kwargs["seed"] == 42
        assert kwargs["response_format"]["json_schema"] is NOVA_NARRATIVE_SCHEMA

        # The model was sent the small structured context, never a raw text
        # dump — the user message must contain the JSON-serialized context.
        user_message = kwargs["messages"][1]["content"]
        assert json.dumps(structured_context, ensure_ascii=False, indent=2) in user_message

        # AC5, through the live (mocked-transport) call path this time.
        assert result["predictive_json"]["delayed_activities"] == response_facts["delayed_activities"]

    def test_malformed_json_response_is_reported_as_error_not_crash(self):
        agent = self._agent_with_fake_client({})
        agent.client.chat.completions.create.return_value.choices[0].message.content = "not json"

        activities = [_activity("A1")]
        facts = _facts_for(activities)
        response_facts = build_response_facts(facts, activities, "Schedule", REF, "NUSF")
        structured_context = build_predictive_context(facts, activities, REF)

        result = agent.analyze_from_facts(
            structured_context=structured_context,
            response_facts=response_facts,
            user_query="q",
        )
        assert result["status"] == "error"
        assert result["predictive_json"] is None
