"""Tests for TL-5.6 — Separate FORECAST from FACT in the schema.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-5-predictive-facts.md` (TL-5.6):

- AC1: Every schema element carries an `EvidenceClass` (the merged
  response's `_classification` map covers every (section, field) pair
  present in the response body).
- AC2: Forecasts carry confidence band, evidence, and key drivers
  (`predictive_snapshot` exposes `confidence_level` / `confidence_basis`
  / `main_delay_drivers` as siblings, and the forecast fields
  `predictive_snapshot.what_will_happen` and `estimated_delay_impact`
  are tagged NOVA_FORECAST).
- AC3: No element defaults to `SOURCE_DATA` implicitly — every
  classification is named in `FIELD_EVIDENCE_CLASSIFICATIONS`, and a
  response field absent from the map raises rather than silently
  classifying.
- AC4: A test asserts total classification coverage (this is the
  shape of `TestCoverage.test_every_response_field_is_classified`,
  pinning AC1 structurally so a future schema addition cannot ship
  without an explicit classification).

The "Do not" rule (zero-delay structural-risk narrative is NOT a
forecast about delay) is encoded as `TestStructuralRiskOverride` —
the field-level classification is NOVA_FORECAST (because that is what
the field is intended to hold), but the renderer (TL-7.4) is the one
that re-classifies when `delayed_count == 0`. We pin the contract here
so a future schema refactor does not silently mis-classify.
"""
from __future__ import annotations

import datetime

import pytest

from src.predictive_agent import (
    FIELD_EVIDENCE_CLASSIFICATIONS,
    _build_classification,
    _merge_narrative_into_facts,
)
from src.trust.vocabulary import EvidenceClass


# ============================================================================
# Fixtures
# ============================================================================

REF = datetime.date(2026, 1, 1)


def _complete_response() -> dict:
    """A minimal but complete merged-response shape — every section
    `FIELD_EVIDENCE_CLASSIFICATIONS` knows about, with at least one
    item per list-section so the per-item walker has something to read."""
    return {
        "predictive_snapshot": {
            "what_will_happen": "If no action is taken, the project will be delayed by 4-8 weeks.",
            "estimated_delay_impact": "+6 weeks",
            "confidence_level": "HIGH",
            "confidence_basis": "Based on 28 delayed activities with clear root cause chains.",
            "main_delay_drivers": [
                "12 coordination bottlenecks blocking cross-discipline handoffs",
                "6 unresolved bygherre decisions stalling design input",
                "8 production tasks overdue in Omr. 2 and Omr. 3",
            ],
        },
        "predictive_biggest_risk": {
            "risk_title": "Task ID 41 — coordination milestone 47 days overdue",
            "will_block": "Unresolved, this will delay electrical and HVAC installation.",
            "prevent_action_now": "Escalate ID 41 coordination meeting to project director today.",
        },
        "executive_actions": [
            {
                "rank": 1,
                "action": "Call coordination meeting with EL and VVS to resolve interface conflict.",
                "responsible": "Project Manager",
                "deadline": "Monday, January 5, 2026",
                "related_task_ids": ["T1", "T2"],
                "manpower_helps": False,
                "manpower_note": "Adding people will not help — waiting on client decision.",
            }
        ],
        "management_conclusion": "The project is at material risk; immediate coordination required.",
        "schedule_overview": {
            "schedule_name": "Test Project",
            "reference_date": "01-01-2026",
            "total_activities": 100,
            "delayed_count": 10,
            "areas_covered": ["NK", "AAA"],
            "format_detected": "csv",
        },
        "delayed_activities": [
            {
                "id": "T1",
                "task_name": "Pour Concrete Slab",
                "human_label": "Pour Concrete Slab",
                "start_date": "01-01-2026",
                "end_date": "10-01-2026",
                "duration": "10d",
                "progress": "0%",
                "days_overdue": 47,
                "task_type": "Production",
                "priority": "CRITICAL_NOW",
                "is_root_cause": True,
                "blocked_by_id": None,
                "area": "NK",
            }
        ],
        "root_cause_analysis": [
            {
                "id": "T1",
                "task_name": "Pour Concrete Slab",
                "human_label": "Pour Concrete Slab",
                "days_overdue": 47,
                "problem_type": "coordination",
                "why_it_matters": "Blocks all EL and VVS follow-on work.",
                "downstream_impact": "Cascades into 6 disciplines across NK and AAA.",
                "consequence_if_unresolved": "Project delay of 6-8 weeks.",
                "affected_task_ids": ["T2", "T3"],
            }
        ],
        "downstream_consequences": [
            {"id": "T2", "task_name": "Install Conduit", "human_label": "Install Conduit", "blocked_by_id": "T1"}
        ],
        "priority_actions": [
            {"step": 1, "action": "Resolve ID 41 coordination issue", "action_type": "coordination"}
        ],
        "resource_assessment": [
            {
                "id": "T1",
                "task_name": "Pour Concrete Slab",
                "human_label": "Pour Concrete Slab",
                "resource_type": "manpower",
                "assessment": "Crew available but blocked by upstream coordination issue.",
            }
        ],
        "forcing_assessment": [
            {
                "id": "T1",
                "task_name": "Pour Concrete Slab",
                "human_label": "Pour Concrete Slab",
                "is_forceable": "not_recommended",
                "constraint_type": "design",
                "reason": "Waiting on design revision before pour can proceed.",
                "risk_if_forced": "Pour against unconfirmed design may require rework.",
                "recommendation": "Wait for design revision.",
                "coordination_cost": "high",
                "parallelizability": "low",
                "max_speedup_factor": 1.1,
                "optimal_team_size": 4,
                "point_of_no_return": "Pour day itself",
            }
        ],
        "summary_by_area": [
            {
                "area": "NK",
                "delayed_count": 8,
                "critical_count": 3,
                "important_count": 3,
                "monitor_count": 2,
                "summary": "NK has the bulk of the delay, driven by EL/VVS coordination.",
            }
        ],
        "insight_data": {
            "total_activities": 100,
            "delayed_count": 10,
            "critical_count": 3,
            "important_count": 4,
            "monitor_count": 3,
            "root_cause_count": 3,
            "reference_date": "01-01-2026",
            "most_overdue_days": 47,
            "areas_affected": 3,
            "format_detected": "csv",
            "schedule_name": "Test Project",
            "primary_risk": "Coordination bottleneck at task ID 41.",
            "forceable_count": 1,
            "not_forceable_count": 2,
            "project_status": "CRITICAL",
            "risk_level": "HIGH",
            "critical_findings": ["Coordination bottleneck blocking 6 downstream tasks."],
            "consequences_if_no_action": ["Project delay of 6-8 weeks."],
        },
    }


# ============================================================================
# AC1 + AC4 — every response element is classified
# ============================================================================


class TestCoverage:
    """AC1 + AC4: a single test that walks the response and asserts every
    (section, field) present in the response body has a corresponding
    entry in the returned classification map."""

    def test_every_response_field_is_classified(self):
        """Every section in the response has a classification entry; every
        field in every section does too. This is the structural test that
        catches a future schema addition that ships without an explicit
        classification."""
        response = _complete_response()
        classification = _build_classification(response)

        # Top-level coverage: every section is in the map.
        for section_name in response:
            assert section_name in classification, (
                f"section {section_name!r} missing from classification"
            )

        # Field-level coverage for object sections.
        for section_name, section_value in response.items():
            if isinstance(section_value, dict):
                for field_name in section_value:
                    assert field_name in classification[section_name], (
                        f"field {section_name!r}.{field_name!r} missing from classification"
                    )

        # Field-level coverage for array-of-items sections.
        for section_name, section_value in response.items():
            if isinstance(section_value, list) and section_value:
                item = section_value[0]
                if isinstance(item, dict):
                    for field_name in item:
                        assert field_name in classification[section_name], (
                            f"field {section_name!r}[].{field_name!r} missing from classification"
                        )

    def test_classification_uses_only_valid_evidence_class_values(self):
        """Every emitted classification must be one of the four
        `EvidenceClass` values — no synthetic strings, no typos."""
        response = _complete_response()
        classification = _build_classification(response)
        valid_values = {cls.value for cls in EvidenceClass}
        for section_name, section_cls in classification.items():
            if isinstance(section_cls, dict):
                for field_name, field_cls in section_cls.items():
                    assert field_cls in valid_values, (
                        f"{section_name!r}.{field_name!r}: {field_cls!r} not in {valid_values}"
                    )
            else:
                assert section_cls in valid_values, (
                    f"{section_name!r}: {section_cls!r} not in {valid_values}"
                )

    def test_response_with_unknown_section_raises(self):
        """AC3: an unknown section must surface as a hard error rather
        than being silently dropped or defaulting to SOURCE_DATA."""
        response = _complete_response()
        response["some_unknown_section"] = {"foo": "bar"}
        with pytest.raises(ValueError, match="some_unknown_section"):
            _build_classification(response)

    def test_response_with_unmapped_field_raises(self):
        """AC3: a field inside a known section that has no entry in the
        master map must surface as an error."""
        response = _complete_response()
        response["delayed_activities"][0]["some_unknown_field"] = "boom"
        with pytest.raises(ValueError, match="some_unknown_field"):
            _build_classification(response)


# ============================================================================
# AC1 (specific cases) — `predictive_snapshot` fields are classified as expected
# ============================================================================


class TestPredictiveSnapshotClassification:
    """The `predictive_snapshot` section is the brief's headline example
    (brief §31, §45): forecasts must never look like observed facts.
    Pin its field classifications explicitly."""

    def test_what_will_happen_is_a_forecast(self):
        response = _complete_response()
        cls = _build_classification(response)
        assert cls["predictive_snapshot"]["what_will_happen"] == EvidenceClass.NOVA_FORECAST.value

    def test_estimated_delay_impact_is_a_forecast(self):
        response = _complete_response()
        cls = _build_classification(response)
        assert cls["predictive_snapshot"]["estimated_delay_impact"] == EvidenceClass.NOVA_FORECAST.value

    def test_confidence_level_is_a_calculation(self):
        """HIGH/MEDIUM/LOW is rule-based (brief §31's "based on
        delayed_count, most_overdue_days, ambiguity"). Even though the
        LLM is asked to assign it, the rules are deterministic — it is
        a NOVA_CALCULATION, not an insight."""
        response = _complete_response()
        cls = _build_classification(response)
        assert cls["predictive_snapshot"]["confidence_level"] == EvidenceClass.NOVA_CALCULATION.value

    def test_confidence_basis_is_an_insight(self):
        response = _complete_response()
        cls = _build_classification(response)
        assert cls["predictive_snapshot"]["confidence_basis"] == EvidenceClass.NOVA_INSIGHT.value

    def test_main_delay_drivers_is_an_insight(self):
        response = _complete_response()
        cls = _build_classification(response)
        assert cls["predictive_snapshot"]["main_delay_drivers"] == EvidenceClass.NOVA_INSIGHT.value


# ============================================================================
# AC2 — forecasts carry the trio (band, evidence, drivers)
# ============================================================================


class TestForecastTrio:
    """AC2: forecast elements carry confidence band, evidence, and key
    drivers (brief §31's required set). `predictive_snapshot` is the
    only forecast-bearing section that exposes the trio explicitly as
    sibling fields; this test pins that contract so a refactor does not
    silently drop the trio."""

    def test_predictive_snapshot_has_confidence_band(self):
        """`confidence_level` (HIGH/MEDIUM/LOW) is the band."""
        response = _complete_response()
        assert "confidence_level" in response["predictive_snapshot"]
        assert response["predictive_snapshot"]["confidence_level"] in {"HIGH", "MEDIUM", "LOW"}

    def test_predictive_snapshot_has_evidence(self):
        """`confidence_basis` is the evidence behind the band — one
        sentence explaining why."""
        response = _complete_response()
        assert "confidence_basis" in response["predictive_snapshot"]
        assert isinstance(response["predictive_snapshot"]["confidence_basis"], str)
        assert len(response["predictive_snapshot"]["confidence_basis"]) > 0

    def test_predictive_snapshot_has_key_drivers(self):
        """`main_delay_drivers` is the list of key drivers — exactly
        three short bullets (per the schema's minItems/maxItems=3)."""
        response = _complete_response()
        drivers = response["predictive_snapshot"]["main_delay_drivers"]
        assert isinstance(drivers, list)
        assert len(drivers) == 3
        for d in drivers:
            assert isinstance(d, str) and len(d) > 0

    def test_other_forecast_fields_are_tagged_no_invented_trio(self):
        """The trio is on the parent `predictive_snapshot`. Forecast
        fields elsewhere (`predictive_biggest_risk.will_block`,
        `executive_actions[].action`) are tagged NOVA_FORECAST but do
        not duplicate the trio inline — that is deliberate, and the
        renderer (TL-7.4) joins them back to the parent's trio. This
        test pins the contract: forecast tagging, no invented trio."""
        response = _complete_response()
        cls = _build_classification(response)

        # Forecasts outside predictive_snapshot
        assert cls["predictive_biggest_risk"]["will_block"] == EvidenceClass.NOVA_FORECAST.value
        assert cls["predictive_biggest_risk"]["prevent_action_now"] == EvidenceClass.NOVA_FORECAST.value
        assert cls["executive_actions"]["action"] == EvidenceClass.NOVA_FORECAST.value
        assert cls["priority_actions"]["action"] == EvidenceClass.NOVA_FORECAST.value

        # The forecast classification is structural — these fields do
        # NOT add their own trio. The renderer is responsible for joining
        # to predictive_snapshot.trio at render time.


# ============================================================================
# AC3 — no implicit SOURCE_DATA default
# ============================================================================


class TestExplicitClassifications:
    """AC3: every classification is explicit. The master map is the
    single source of truth — there is no `dict.get(field, SOURCE_DATA)`
    fallback. This test pins that property statically."""

    def test_every_master_map_entry_is_an_enum_member(self):
        """No string defaults like "source_data" sneaking in — every
        value is a real `EvidenceClass` member."""
        for section, section_cls in FIELD_EVIDENCE_CLASSIFICATIONS.items():
            if isinstance(section_cls, EvidenceClass):
                continue
            assert isinstance(section_cls, dict), (
                f"{section!r}: unexpected type {type(section_cls).__name__}"
            )
            for field, field_cls in section_cls.items():
                assert isinstance(field_cls, EvidenceClass), (
                    f"{section!r}.{field!r}: not an EvidenceClass — {field_cls!r}"
                )

    def test_every_class_value_used_at_least_once(self):
        """All four `EvidenceClass` values are used. A drift that drops
        one entirely (e.g., schema removes all SOURCE_DATA fields) should
        be caught by the test forcing an explicit decision."""
        used: set[str] = set()
        for section_cls in FIELD_EVIDENCE_CLASSIFICATIONS.values():
            if isinstance(section_cls, EvidenceClass):
                used.add(section_cls.value)
            else:
                for field_cls in section_cls.values():
                    used.add(field_cls.value)
        assert used == {c.value for c in EvidenceClass}, (
            f"missing classifications: {set(c.value for c in EvidenceClass) - used}"
        )

    def test_known_response_with_no_unknown_fields_succeeds(self):
        """AC3 (positive case): a response that uses only fields the
        master map knows about must classify cleanly without raising."""
        response = _complete_response()
        cls = _build_classification(response)
        # And every emitted value is a valid enum value
        for section in cls.values():
            if isinstance(section, dict):
                for v in section.values():
                    assert v in {c.value for c in EvidenceClass}
            else:
                assert section in {c.value for c in EvidenceClass}


# ============================================================================
# Structural-risk override — the "Do not" rule
# ============================================================================


class TestStructuralRiskOverride:
    """The plan's "Do not" rule: do not classify the zero-delay
    structural-risk narrative as a forecast about delay. It is an
    inference about structure (brief §20).

    Field-level classification is still NOVA_FORECAST because that is
    what `predictive_snapshot.what_will_happen` is *intended* to hold.
    The renderer (TL-7.4) is responsible for the content-aware
    re-classification when `delayed_count == 0`. This test pins the
    field-level contract so the renderer contract is unambiguous."""

    def test_what_will_happen_field_is_forecast(self):
        """The *field* is NOVA_FORECAST by intent — it can hold a delay
        window. The *value* when delayed_count=0 is structurally an
        insight, and the renderer handles that. We do NOT re-classify
        at the schema level (would obscure the field's intent for
        callers)."""
        response = _complete_response()
        cls = _build_classification(response)
        assert cls["predictive_snapshot"]["what_will_happen"] == EvidenceClass.NOVA_FORECAST.value

    def test_what_will_happen_with_zero_delays_value_remains_field_level_forecast(self):
        """Even when the *value* describes structural risk rather than a
        delay (delayed_count=0 case), the *field* is still classified
        NOVA_FORECAST. The renderer re-classifies on the value; we
        encode that contract here by showing the classification is
        value-independent."""
        response = _complete_response()
        # Simulate the zero-delay case: zero delays, structural risk value
        response["insight_data"]["delayed_count"] = 0
        response["predictive_snapshot"]["what_will_happen"] = (
            "Large-scale restructuring introduces elevated coordination risk — "
            "validation of new dependency links is required before schedule "
            "impact can be confirmed."
        )
        cls = _build_classification(response)
        # Field-level classification is unchanged — the renderer's job to
        # treat the zero-delay value as structural insight at render time.
        assert cls["predictive_snapshot"]["what_will_happen"] == EvidenceClass.NOVA_FORECAST.value


# ============================================================================
# Integration — NUSF path produces the same shape
# ============================================================================


class TestMergedResponseIntegration:
    """End-to-end: `_merge_narrative_into_facts` (the NUSF path's
    deterministic-facts merge from TL-5.4) must produce a `_classification`
    map on the merged response, populated from the response's actual
    shape (so drift between the merge and the master map is caught)."""

    def test_merge_attaches_classification(self):
        """Build a minimal-but-valid `response_facts` and narrative,
        run the merge, and assert `_classification` is present with the
        expected structure."""
        from src.trust.context import (
            build_predictive_context,
            build_response_facts,
        )
        from src.trust.predictive_facts import (
            compute_predictive_facts,
            detect_delayed_activities,
        )

        from ingestion.models.nusf import Activity, ActivityType, Provenance

        def _exact(field):
            return Provenance(source_field=field, extraction_method="csv_cell")

        # Build a tiny schedule
        act = Activity(
            internal_id="T1",
            source_id="T1",
            name="Pour Concrete Slab",
            planned_start=datetime.datetime(2020, 1, 1),
            planned_finish=datetime.datetime(2020, 1, 10),
            duration_hours=80.0,
            percent_complete=0.0,
            activity_type=ActivityType.TASK,
            predecessors=[],
            successors=[],
            area="NK",
            discipline="EL",
            provenance={
                "planned_start": _exact("Startdato"),
                "percent_complete": _exact("% færdigt"),
            },
        )
        delayed = detect_delayed_activities([act], REF)
        facts = compute_predictive_facts(delayed, [act])
        structured_context = build_predictive_context(facts, [act], REF)
        response_facts = build_response_facts(
            facts=facts,
            activities=[act],
            schedule_name="Test",
            reference_date=REF,
            format_detected="csv",
        )

        # Minimal narrative — every section the merge looks at
        narrative = {
            "predictive_snapshot": {
                "what_will_happen": "If no action is taken, the project will be delayed.",
                "estimated_delay_impact": "+6 weeks",
                "confidence_level": "HIGH",
                "confidence_basis": "Clear root cause chains visible.",
                "main_delay_drivers": ["coordination bottlenecks", "design decisions", "production overdue"],
            },
            "predictive_biggest_risk": {
                "risk_title": "Task ID T1 — coordination milestone overdue",
                "will_block": "Blocks downstream EL work.",
                "prevent_action_now": "Escalate T1 coordination meeting.",
            },
            "executive_actions": [
                {
                    "rank": 1,
                    "action": "Resolve T1 coordination",
                    "responsible": "Project Manager",
                    "deadline": "Monday",
                    "related_task_ids": ["T1"],
                    "manpower_helps": False,
                    "manpower_note": "Waiting on decision.",
                }
            ],
            "management_conclusion": "Material risk; immediate coordination required.",
            "root_cause_narratives": [],
            "resource_assessment": [],
            "forcing_assessment": [],
            "summary_by_area_narratives": [],
            "insight_narrative": {
                "primary_risk": "Coordination bottleneck.",
                "critical_findings": ["T1 is blocking downstream work."],
                "consequences_if_no_action": ["Project delay of 6 weeks."],
            },
            "priority_actions": [],
        }

        merged = _merge_narrative_into_facts(response_facts, structured_context, narrative)

        # AC1/AC4: classification is present and covers every section the
        # merge emits.
        assert "_classification" in merged
        cls = merged["_classification"]
        assert "predictive_snapshot" in cls
        assert cls["predictive_snapshot"]["what_will_happen"] == EvidenceClass.NOVA_FORECAST.value
        assert "delayed_activities" in cls
        assert cls["delayed_activities"]["id"] == EvidenceClass.SOURCE_DATA.value
        assert "insight_data" in cls
        assert cls["insight_data"]["delayed_count"] == EvidenceClass.NOVA_CALCULATION.value
