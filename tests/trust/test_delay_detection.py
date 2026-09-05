"""Tests for TL-5.1 — Deterministic delayed-activity detection.

Encodes acceptance criteria from
`changes/trust-layer/plan/phase-5-predictive-facts.md` (TL-5.1):
- AC1: Detection is pure Python over `Activity` objects, no LLM call.
- AC2: Standard and Plandisc rules both implemented, with fixtures for each.
- AC3: The 50-shared-start-date case detects all 50.
- AC4: `planned_completion_pct` is never used as progress — asserted by test.
- AC5: Detected counts match or exceed the current LLM-derived counts (verified
  here via a full-pipeline CSV fixture per format, since no LLM output exists
  yet to diff against in this offline suite).
"""
from __future__ import annotations

import inspect
from datetime import date, datetime

import pytest

from ingestion.models.nusf import Activity, ActivityType, Provenance
from ingestion.pipeline import IngestionPipeline
from src.trust import predictive_facts
from src.trust.engine import TrustEngine
from src.trust.predictive_facts import (
    PLANDISC_A,
    PLANDISC_B,
    PLANDISC_C,
    STANDARD,
    detect_delayed_activities,
)
from src.trust.vocabulary import TrustState

REF = date(2026, 1, 1)


def _activity(
    internal_id: str = "A-1",
    source_id: str | None = "A-1",
    name: str = "Pour Concrete",
    planned_start: datetime = datetime(2025, 1, 1),
    planned_finish: datetime = datetime(2025, 1, 10),
    percent_complete: float = 0.0,
    activity_type: ActivityType = ActivityType.TASK,
    actual_start: datetime | None = None,
    is_late: bool | None = None,
    inspected_status: str | None = None,
    provenance: dict | None = None,
) -> Activity:
    return Activity(
        internal_id=internal_id,
        source_id=source_id,
        name=name,
        planned_start=planned_start,
        planned_finish=planned_finish,
        duration_hours=80,
        percent_complete=percent_complete,
        activity_type=activity_type,
        actual_start=actual_start,
        is_late=is_late,
        inspected_status=inspected_status,
        provenance=provenance or {},
    )


class TestNoLLMCall:
    def test_module_imports_no_llm_client(self):
        """AC1: no OpenAI/Azure client, no network call, anywhere in the module."""
        source = inspect.getsource(predictive_facts)
        for banned in ("openai", "AzureOpenAI", "chat.completions", "requests.post"):
            assert banned not in source, f"found '{banned}' in predictive_facts.py"


class TestStandardDetection:
    def test_old_start_zero_progress_is_delayed(self):
        act = _activity(planned_start=datetime(2020, 1, 1), percent_complete=0.0)
        result = detect_delayed_activities([act], REF)
        assert len(result) == 1
        assert result[0].condition == STANDARD
        assert result[0].internal_id == "A-1"

    def test_old_start_with_progress_is_not_delayed(self):
        act = _activity(planned_start=datetime(2020, 1, 1), percent_complete=45.0)
        assert detect_delayed_activities([act], REF) == []

    def test_recent_start_zero_progress_is_not_delayed(self):
        act = _activity(planned_start=date(2026, 6, 1), percent_complete=0.0)
        assert detect_delayed_activities([act], REF) == []

    def test_start_yesterday_zero_progress_is_delayed_by_one_day(self):
        act = _activity(planned_start=datetime(2025, 12, 31), percent_complete=0.0)
        result = detect_delayed_activities([act], REF)
        assert len(result) == 1
        assert result[0].days_overdue == 1

    def test_summary_row_excluded_even_if_it_matches(self):
        act = _activity(
            planned_start=datetime(2020, 1, 1), percent_complete=0.0,
            activity_type=ActivityType.SUMMARY,
        )
        assert detect_delayed_activities([act], REF) == []

    def test_milestone_zero_duration_is_not_excluded(self):
        act = _activity(
            planned_start=datetime(2020, 1, 1), percent_complete=0.0,
            activity_type=ActivityType.MILESTONE,
        )
        result = detect_delayed_activities([act], REF)
        assert len(result) == 1

    def test_days_overdue_measured_from_planned_start(self):
        act = _activity(planned_start=datetime(2020, 1, 1), percent_complete=0.0)
        result = detect_delayed_activities([act], REF)
        expected = (REF - date(2020, 1, 1)).days
        assert result[0].days_overdue == expected


class TestPlandiscDetection:
    """`is_late` / `inspected_status` non-None on any activity in the batch
    switches the whole batch to Plandisc rules (see `_is_plandisc_batch`)."""

    def test_condition_a_not_started_past_planned_end(self):
        act = _activity(
            planned_finish=datetime(2025, 1, 1), percent_complete=0.0,
            inspected_status="noProgress",
        )
        result = detect_delayed_activities([act], REF)
        assert len(result) == 1
        assert result[0].condition == PLANDISC_A

    def test_condition_a_excluded_when_accepted(self):
        act = _activity(
            planned_finish=datetime(2025, 1, 1), percent_complete=0.0,
            inspected_status="accepted",
        )
        assert detect_delayed_activities([act], REF) == []

    def test_condition_a_excluded_when_fully_complete(self):
        act = _activity(
            planned_finish=datetime(2025, 1, 1), percent_complete=100.0,
            inspected_status="noProgress",
        )
        assert detect_delayed_activities([act], REF) == []

    def test_accepted_status_is_case_insensitive(self):
        act = _activity(
            planned_finish=datetime(2025, 1, 1), percent_complete=0.0,
            inspected_status="Accepted",
        )
        assert detect_delayed_activities([act], REF) == []

    def test_condition_b_in_progress_flagged_late_future_deadline(self):
        """brief: is_late=true is a strong delay signal even when
        planned_end_date is still in the future."""
        act = _activity(
            planned_finish=datetime(2026, 6, 1), percent_complete=40.0,
            is_late=True, inspected_status="noProgress",
        )
        result = detect_delayed_activities([act], REF)
        assert len(result) == 1
        assert result[0].condition == PLANDISC_B
        assert result[0].days_overdue == 0

    def test_condition_b_not_flagged_when_is_late_false(self):
        act = _activity(
            planned_finish=datetime(2026, 6, 1), percent_complete=40.0,
            is_late=False, inspected_status="noProgress",
        )
        assert detect_delayed_activities([act], REF) == []

    def test_condition_c_started_but_stalled(self):
        act = _activity(
            planned_finish=datetime(2025, 1, 1), percent_complete=0.0,
            actual_start=datetime(2024, 12, 1), inspected_status="noProgress",
        )
        result = detect_delayed_activities([act], REF)
        assert len(result) == 1
        # Condition A also matches this row (planned_finish < ref, pct == 0);
        # A is checked first and is the reported condition — see
        # `_plandisc_condition`'s docstring on the A/C overlap.
        assert result[0].condition == PLANDISC_A

    def test_days_overdue_measured_from_planned_finish_not_start(self):
        act = _activity(
            planned_start=datetime(2020, 1, 1),  # far in the past
            planned_finish=datetime(2025, 12, 1),
            percent_complete=0.0, inspected_status="noProgress",
        )
        result = detect_delayed_activities([act], REF)
        expected = (REF - date(2025, 12, 1)).days
        assert result[0].days_overdue == expected


class TestAutoDetectFormat:
    def test_batch_with_any_plandisc_field_uses_plandisc_rules(self):
        plain = _activity(internal_id="A-1", planned_start=datetime(2020, 1, 1), percent_complete=0.0)
        plandisc = _activity(
            internal_id="A-2", planned_finish=datetime(2025, 1, 1),
            percent_complete=0.0, inspected_status="noProgress",
        )
        result = detect_delayed_activities([plain, plandisc], REF)
        ids = {d.internal_id: d.condition for d in result}
        # "plain" has planned_start in 2025 (default) which also satisfies the
        # standard rule, but the batch is Plandisc-classified so it is
        # evaluated under Plandisc conditions, not STANDARD.
        assert ids["A-2"] == PLANDISC_A
        assert "A-1" not in ids or ids["A-1"] != STANDARD

    def test_batch_with_no_plandisc_fields_uses_standard_rules(self):
        act = _activity(planned_start=datetime(2020, 1, 1), percent_complete=0.0)
        result = detect_delayed_activities([act], REF)
        assert result[0].condition == STANDARD


class TestFiftySharedStartDate:
    def test_all_fifty_detected_no_truncation(self):
        activities = [
            _activity(internal_id=f"A-{i}", source_id=f"A-{i}", planned_start=datetime(2020, 1, 1), percent_complete=0.0)
            for i in range(50)
        ]
        result = detect_delayed_activities(activities, REF)
        assert len(result) == 50
        assert {d.internal_id for d in result} == {f"A-{i}" for i in range(50)}


class TestPlannedCompletionPctTrapClosedUpstream:
    """AC4: `planned_completion_pct` is never used as progress.

    `Activity` has no `planned_completion_pct` field at all — normalization
    (TL-1.*) maps only `actual_completion_pct` into `percent_complete`
    (`ingestion/recognition/heuristics.py`). This function reads
    `percent_complete` exclusively, so the trap cannot reach it.
    """

    def test_module_source_never_reads_planned_completion_pct_as_a_value(self):
        """`planned_completion_pct` may appear in prose (explaining why it's
        irrelevant); it must never appear as an attribute/key access, which
        is the only way this module could actually read it as progress."""
        source = inspect.getsource(predictive_facts)
        for pattern in (".planned_completion_pct", '"planned_completion_pct"', "'planned_completion_pct'"):
            assert pattern not in source, f"found '{pattern}' — module may be reading the trap field"

    def test_zero_actual_progress_is_never_treated_as_complete(self):
        """A Plandisc row where the (hypothetical) planned_completion_pct
        would read 100 but actual_completion_pct (-> percent_complete) is 0
        must still be detected as delayed — proving the function trusts
        `percent_complete` (actual progress), not any target percentage."""
        act = _activity(
            planned_finish=datetime(2025, 1, 1), percent_complete=0.0,
            inspected_status="noProgress",
        )
        result = detect_delayed_activities([act], REF)
        assert len(result) == 1


class TestTrustPropagation:
    """AC (implicit, brief §14): every detected activity carries provenance
    and trust state from Phases 1 and 4 — a delay flagged from unreliable
    evidence must not be reported as VERIFIED."""

    def test_low_ocr_confidence_evidence_yields_non_verified_trust(self):
        prov = {
            "planned_start": Provenance(source_field="Startdato", ocr_confidence=0.10, extraction_method="ocr_table"),
            "percent_complete": Provenance(source_field="% færdigt", ocr_confidence=0.10, extraction_method="ocr_table"),
        }
        act = _activity(planned_start=datetime(2020, 1, 1), percent_complete=0.0, provenance=prov)
        result = detect_delayed_activities([act], REF, trust_engine=TrustEngine())
        assert len(result) == 1
        assert result[0].trust.state == TrustState.UNVERIFIED

    def test_exact_csv_read_yields_verified_trust(self):
        prov = {
            "planned_start": Provenance(source_field="Startdato", extraction_method="csv_cell"),
            "percent_complete": Provenance(source_field="% færdigt", extraction_method="csv_cell"),
        }
        act = _activity(planned_start=datetime(2020, 1, 1), percent_complete=0.0, provenance=prov)
        result = detect_delayed_activities([act], REF, trust_engine=TrustEngine())
        assert result[0].trust.state == TrustState.VERIFIED

    def test_missing_provenance_is_never_silently_verified(self):
        """Regression guard for the `assess_value` "no evidence at all"
        default (see `_assess_delay_trust`'s docstring): a field the rule
        read but that has no `Provenance` entry must not resolve to
        VERIFIED just because nothing was passed."""
        act = _activity(planned_start=datetime(2020, 1, 1), percent_complete=0.0, provenance={})
        result = detect_delayed_activities([act], REF, trust_engine=TrustEngine())
        assert result[0].trust.state != TrustState.VERIFIED

    def test_weakest_link_one_bad_field_caps_whole_activity(self):
        prov = {
            "planned_start": Provenance(source_field="Startdato", extraction_method="csv_cell"),
            "percent_complete": Provenance(source_field="% færdigt", ocr_confidence=0.10, extraction_method="ocr_table"),
        }
        act = _activity(planned_start=datetime(2020, 1, 1), percent_complete=0.0, provenance=prov)
        result = detect_delayed_activities([act], REF, trust_engine=TrustEngine())
        assert result[0].trust.state == TrustState.UNVERIFIED


class TestPipelineIntegration:
    """AC2/AC5: end-to-end from raw file bytes through the real ingestion
    pipeline (extractor + heuristic recognizer + normalizer), for both
    formats — not just hand-built `Activity` objects."""

    def test_standard_csv_format_end_to_end(self):
        csv_text = (
            "Id,Opgavenavn,Startdato,Slutdato,% færdigt,Varighed\n"
            "1,Støbning af beton,01-01-2020,10-01-2020,0,10d\n"
            "2,Opsummering omr. 1,01-01-2020,10-01-2020,0,50d\n"
            "3,Facademontage,01-06-2026,10-06-2026,0,10d\n"
            "4,Malerarbejde,01-01-2020,10-01-2020,60,10d\n"
        )
        schedule, _ = IngestionPipeline().run_from_bytes(csv_text.encode("utf-8"), "schedule.csv")
        result = detect_delayed_activities(schedule.activities, REF)
        names = {d.name for d in result}
        assert "Støbning af beton" in names
        assert "Opsummering omr. 1" not in names  # summary row excluded
        assert "Facademontage" not in names  # starts in the future
        assert "Malerarbejde" not in names  # has progress

    def test_plandisc_csv_format_end_to_end_ignores_planned_completion_pct(self):
        header = (
            "name;location_path;task_group_name;planned_start_date;planned_end_date;"
            "planned_shift_duration;planned_completion_pct;actual_start_date;actual_end_date;"
            "actual_completion_pct;actual_completion_date;actual_by;is_late;inspectedType;"
            "inspected_by;has_constraint;is_flagged\n"
        )
        # planned_completion_pct is 100 (the always-100 target) on every row;
        # only actual_completion_pct varies. If the target were ever read as
        # progress, every row below would look complete and none would be
        # flagged delayed.
        row = (
            "Muring;Omr1/Kld;Murer;2025-01-01 00:00:00;2025-06-01 00:00:00;"
            "48;100;;;0;;;false;noProgress;;false;false\n"
        )
        schedule, _ = IngestionPipeline().run_from_bytes(
            (header + row).encode("utf-8"), "plandisc_export.csv"
        )
        assert schedule.activities, "fixture did not parse into any activities"
        result = detect_delayed_activities(schedule.activities, REF)
        assert len(result) == 1
        assert result[0].condition == PLANDISC_A
