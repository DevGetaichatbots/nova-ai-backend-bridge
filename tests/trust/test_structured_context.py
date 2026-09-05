"""Tests for TL-5.3 — Structured verified context builder.

Encodes acceptance criteria from
`changes/trust-layer/plan/phase-5-predictive-facts.md` (TL-5.3):
- AC1: Context is structured data, not concatenated raw rows.
- AC2: Every supplied fact carries a trust state.
- AC3: `UNVERIFIED` values are never presented as plain facts.
- AC4: Context size for the largest fixture drops by at least an order of
  magnitude (vs. the raw-text-blob approach `_build_predictive_context`
  in `src/main.py` uses today).
- AC5: Context is deterministic for a given input.

Scope note (ADR-019, extended by ADR-020/TL-5.4): this module emits brief
§17's illustrated shape — `project_status` (aggregate counts + confidence)
and `clusters` (location x trade) — plus two small, capped additions the
narrative layer needs to ground specific claims without inventing ids:
`biggest_risk_candidate` (one activity) and `actionable_activities`
(root-cause/CRITICAL_NOW/IMPORTANT_NEXT activities only, capped at
`_ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED`). It still does not emit the full
delayed-activity set — see ADR-019 for why an unbounded per-activity array
fails AC4 at realistic schedule sizes.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from ingestion.models.nusf import Activity, ActivityType, Provenance
from src.trust.context import _ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED, build_predictive_context
from src.trust.predictive_facts import compute_predictive_facts, detect_delayed_activities
from src.trust.vocabulary import TrustState

REF = date(2026, 1, 1)


def _activity(
    internal_id: str,
    source_id: str | None = None,
    name: str = "Activity",
    planned_start: datetime = datetime(2020, 1, 1),
    planned_finish: datetime = datetime(2020, 1, 10),
    percent_complete: float = 0.0,
    predecessors: list[str] | None = None,
    successors: list[str] | None = None,
    area: str | None = None,
    discipline: str | None = None,
    provenance: dict | None = None,
) -> Activity:
    return Activity(
        internal_id=internal_id,
        source_id=source_id if source_id is not None else internal_id,
        name=name,
        planned_start=planned_start,
        planned_finish=planned_finish,
        duration_hours=80,
        percent_complete=percent_complete,
        activity_type=ActivityType.TASK,
        predecessors=predecessors or [],
        successors=successors or [],
        area=area,
        discipline=discipline,
        provenance=provenance or {},
    )


def _exact_read_provenance(field: str) -> Provenance:
    return Provenance(source_field=field, extraction_method="csv_cell")


def _low_confidence_provenance(field: str) -> Provenance:
    return Provenance(source_field=field, ocr_confidence=0.10, extraction_method="ocr_table")


def _build(activities: list[Activity]) -> dict:
    delayed = detect_delayed_activities(activities, REF)
    facts = compute_predictive_facts(delayed, activities)
    return build_predictive_context(facts, activities, REF)


class TestStructuredShape:
    def test_output_has_brief_17_top_level_keys(self):
        act = _activity(
            "A", area="NK", discipline="EL",
            provenance={"planned_start": _exact_read_provenance("Startdato"), "percent_complete": _exact_read_provenance("% færdigt")},
        )
        ctx = _build([act])
        assert {"reference_date", "project_status", "clusters"} <= set(ctx.keys())
        assert ctx["reference_date"] == "2026-01-01"

    def test_output_is_json_serializable(self):
        act = _activity("A", area="NK", discipline="EL", provenance={
            "planned_start": _exact_read_provenance("Startdato"), "percent_complete": _exact_read_provenance("% færdigt"),
        })
        ctx = _build([act])
        json.dumps(ctx)  # must not raise

    def test_no_raw_provenance_strings_in_output(self):
        """AC1: structured data, not concatenated raw rows — the raw
        provenance strings (`source_field`, `raw_value`) never appear."""
        act = _activity("A", name="Pour Concrete Slab", area="NK", discipline="EL", provenance={
            "planned_start": Provenance(source_field="Startdato", raw_value="ma 05-01-20", extraction_method="csv_cell"),
            "percent_complete": _exact_read_provenance("% færdigt"),
        })
        ctx = _build([act])
        serialized = json.dumps(ctx)
        assert "Startdato" not in serialized
        assert "ma 05-01-20" not in serialized

    def test_task_name_appears_only_for_grounded_actionable_activities(self):
        """A root-cause/critical activity's name IS included (bounded,
        `actionable_activities`) so the model can reference it — but a
        MONITOR-priority, non-root-cause activity's name never reaches the
        context at all (it is only a number inside `project_status`)."""
        root_cause = _activity("A", name="Pour Concrete Slab", area="NK", discipline="EL", provenance={
            "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        # A MONITOR-priority downstream consequence: blocked by A, short
        # overdue window, no further downstream impact of its own.
        monitor_task = _activity(
            "B", name="Paint Touch-Up Work", area="NK", discipline="EL",
            planned_start=datetime(2025, 12, 30), predecessors=["A"], provenance={
                "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
            },
        )
        ctx = _build([root_cause, monitor_task])
        serialized = json.dumps(ctx)
        assert "Pour Concrete Slab" in serialized
        assert "Paint Touch-Up Work" not in serialized

    def test_project_status_counts(self):
        acts = [
            _activity(f"A{i}", area="NK", discipline="EL", provenance={
                "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
            })
            for i in range(3)
        ]
        ctx = _build(acts)
        assert ctx["project_status"]["delayed_activities"] == 3
        assert ctx["project_status"]["critical_delayed"] == 3  # all 3 root causes, hugely overdue -> CRITICAL_NOW
        assert ctx["project_status"]["root_cause_count"] == 3

    def test_cluster_counts_and_confidence(self):
        acts = [
            _activity(f"A{i}", area="NK", discipline="EL", provenance={
                "planned_start": _exact_read_provenance("Startdato"), "percent_complete": _exact_read_provenance("% færdigt"),
            })
            for i in range(3)
        ]
        ctx = _build(acts)
        assert len(ctx["clusters"]) == 1
        cluster = ctx["clusters"][0]
        assert cluster["location"] == "NK"
        assert cluster["trade"] == "EL"
        assert cluster["delayed"] == 3
        assert cluster["confidence"] == "high"

    def test_missing_location_and_trade_fall_back_to_unknown_not_invented(self):
        act = _activity("A", provenance={
            "planned_start": _exact_read_provenance("Startdato"), "percent_complete": _exact_read_provenance("% færdigt"),
        })
        ctx = _build([act])
        assert ctx["clusters"][0]["location"] == "Unknown"
        assert ctx["clusters"][0]["trade"] == "Unknown"

    def test_two_locations_produce_two_clusters_sorted(self):
        a = _activity("A", area="NK", discipline="EL", provenance={
            "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        b = _activity("B", area="AAA", discipline="VVS", provenance={
            "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        ctx = _build([b, a])  # deliberately out of alphabetical order
        locations = [c["location"] for c in ctx["clusters"]]
        assert locations == ["AAA", "NK"]  # sorted, not input order


class TestTrustDiscipline:
    def test_every_cluster_carries_confidence(self):
        act = _activity("A", area="NK", discipline="EL", provenance={
            "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        ctx = _build([act])
        assert ctx["clusters"][0]["confidence"] in ("high", "medium")

    def test_project_status_carries_confidence(self):
        act = _activity("A", area="NK", discipline="EL", provenance={
            "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        ctx = _build([act])
        assert ctx["project_status"]["confidence"] == "high"

    def test_review_state_produces_medium_confidence(self):
        act = _activity("A", area="NK", discipline="EL", provenance={
            "planned_start": Provenance(source_field="x", ocr_confidence=0.85, extraction_method="ocr_table"),
            "percent_complete": _exact_read_provenance("x"),
        })
        ctx = _build([act])
        assert ctx["clusters"][0]["confidence"] == "medium"
        assert ctx["project_status"]["confidence"] == "medium"

    def test_unverified_activity_excluded_from_clusters(self):
        act = _activity("A", area="NK", discipline="EL", provenance={
            "planned_start": _low_confidence_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        ctx = _build([act])
        assert ctx["clusters"] == []

    def test_unverified_activity_counted_but_not_named(self):
        """AC3: 'either omitted or explicitly labelled unverified; never
        passed as plain facts' — this module omits the activity entirely
        and surfaces only a count."""
        act = _activity("A", name="Secret Task Name", area="NK", discipline="EL", provenance={
            "planned_start": _low_confidence_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        ctx = _build([act])
        assert ctx["project_status"]["unverified_delayed_count"] == 1
        assert ctx["project_status"]["delayed_activities"] == 0
        assert "Secret Task Name" not in json.dumps(ctx)

    def test_unverified_activities_do_not_inflate_confirmed_counts(self):
        verified = _activity("A", area="NK", discipline="EL", provenance={
            "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        unverified = _activity("B", area="NK", discipline="EL", provenance={
            "planned_start": _low_confidence_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        ctx = _build([verified, unverified])
        assert ctx["project_status"]["delayed_activities"] == 1
        assert ctx["project_status"]["unverified_delayed_count"] == 1

    def test_project_status_confidence_is_none_when_nothing_confirmed(self):
        act = _activity("A", provenance={
            "planned_start": _low_confidence_provenance("x"), "percent_complete": _exact_read_provenance("x"),
        })
        ctx = _build([act])
        assert ctx["project_status"]["confidence"] is None
        assert ctx["clusters"] == []


class TestDeterminism:
    def test_repeated_calls_produce_identical_output(self):
        acts = [
            _activity(f"A{i}", area="NK" if i % 2 == 0 else "KLD", discipline="EL", provenance={
                "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
            })
            for i in range(10)
        ]
        ctx1 = _build(acts)
        ctx2 = _build(acts)
        assert ctx1 == ctx2
        assert json.dumps(ctx1, sort_keys=True) == json.dumps(ctx2, sort_keys=True)

    def test_input_order_does_not_affect_cluster_order(self):
        acts = [
            _activity(f"A{i}", area=f"Area-{i % 5}", discipline=f"Trade-{i % 3}", provenance={
                "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
            })
            for i in range(20)
        ]
        forward = _build(acts)
        reversed_ = _build(list(reversed(acts)))
        assert forward["clusters"] == reversed_["clusters"]


class TestContextSizeReduction:
    def test_structured_context_is_an_order_of_magnitude_smaller_than_raw_dump(self):
        """AC4. Builds 200 activities and compares the structured JSON
        context's size against a naive concatenated-row text dump — the
        shape `_build_predictive_context` (`src/main.py`) produces today."""
        acts = []
        raw_rows_text_parts = []
        for i in range(200):
            aid = f"A{i}"
            acts.append(_activity(
                aid, name=f"Some reasonably long construction activity description number {i}",
                area=f"Area-{i % 5}", discipline=f"Trade-{i % 4}",
                provenance={
                    "planned_start": _exact_read_provenance("Startdato"),
                    "percent_complete": _exact_read_provenance("% færdigt"),
                },
            ))
            raw_rows_text_parts.append(
                f"Id: {aid} | Opgavenavn: Some reasonably long construction activity description "
                f"number {i} | Varighed: 10d | Startdato: 01-01-2020 | Slutdato: 10-01-2020 | "
                f"% arbejde færdigt: 0 | omr.: Area-{i % 5} | Ansvarlig: Trade-{i % 4}"
            )
        raw_dump = "\n".join(raw_rows_text_parts)

        ctx = _build(acts)
        structured_size = len(json.dumps(ctx).encode("utf-8"))
        raw_size = len(raw_dump.encode("utf-8"))

        assert structured_size * 10 <= raw_size, (
            f"structured={structured_size} bytes, raw={raw_size} bytes — "
            f"expected at least a 10x reduction"
        )

    def test_size_stays_bounded_as_activity_count_grows(self):
        """Size is driven by the number of distinct (location, trade)
        clusters and the `actionable_activities` cap, not by raw activity
        count: growing from cap-many to 500 same-cluster root-cause
        activities only adds entries up to the cap, never one-per-activity.

        `small`'s count is pinned to the cap itself (not an arbitrary number
        below it) so both sides are actually exercising the capped path —
        a `small` count below the cap would report its uncapped length,
        which is a different (also true, but not this test's) invariant."""
        small = [
            _activity(f"A{i}", area="NK", discipline="EL", provenance={
                "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
            })
            for i in range(_ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED)
        ]
        large = [
            _activity(f"A{i}", area="NK", discipline="EL", provenance={
                "planned_start": _exact_read_provenance("x"), "percent_complete": _exact_read_provenance("x"),
            })
            for i in range(500)
        ]
        small_ctx = _build(small)
        large_ctx = _build(large)
        small_size = len(json.dumps(small_ctx).encode("utf-8"))
        large_size = len(json.dumps(large_ctx).encode("utf-8"))
        # `actionable_activities` itself is capped — same length either way.
        assert len(small_ctx["actionable_activities"]) == _ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED
        assert len(large_ctx["actionable_activities"]) == _ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED
        # `omitted_count` is where the growth actually shows up — labelled,
        # never silently dropped (module docstring; `TL-5.5`'s rule applied
        # in spirit).
        assert small_ctx["actionable_activities_omitted_count"] == 0
        assert large_ctx["actionable_activities_omitted_count"] == 500 - _ACTIONABLE_ACTIVITIES_CAP_UNCALIBRATED
        # Growth is bounded (counts/omitted_count change, not a new entry
        # per activity): a large activity-count increase must not produce
        # anywhere near a proportional size increase.
        assert large_size < small_size * 3
