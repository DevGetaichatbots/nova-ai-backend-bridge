"""Tests for TL-8.1 — Review queue data model + backend.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-8-review-queue.md` (TL-8.1):

- AC1: All four brief §25 categories representable.
- AC2: Items carry candidate options where a choice is required.
- AC4: Resolutions never mutate extracted source values.
- AC5: Read-only users cannot resolve items.

(AC3 — endpoints exist in both Flask backends with correct auth and
tenant scoping — lives in `kemp&lauritzen/backend/routes/schedule.py` and
`website/workspace/app/Nova-Insights-Backend/routes/schedule.py`, outside
this repo's pytest suite.)

Do-not: do not let a resolution overwrite the extracted value. The
original reading and the human decision are separate facts.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import pathlib

import pytest

from ingestion.models.nusf import Activity, ActivityType, Provenance
from src.trust.review_queue import (
    NO_MATCH_OPTION_ID,
    CandidateOption,
    ReadOnlyUserError,
    ResolutionState,
    ReviewCategory,
    ReviewItem,
    ReviewQueueStore,
    build_review_queue,
    derive_conflicting_value_items,
    derive_low_confidence_id_items,
    derive_uncertain_match_items,
    derive_unreadable_date_items,
)


def _activity(internal_id="uuid-1", source_id="ACT-1", *, source_id_conf=0.98, date_conf=0.98):
    return Activity(
        internal_id=internal_id,
        source_id=source_id,
        name="Foundations",
        planned_start="2026-01-01T00:00:00",
        planned_finish="2026-01-10T00:00:00",
        duration_hours=80,
        percent_complete=0.0,
        activity_type=ActivityType.TASK,
        provenance={
            "source_id": Provenance(
                source_field="ID", source_row=1, ocr_confidence=source_id_conf,
                column_mapping_confidence=1.0, extraction_method="ocr_table",
            ),
            "planned_start": Provenance(
                source_field="Start", source_row=1, ocr_confidence=date_conf,
                column_mapping_confidence=1.0, extraction_method="ocr_table",
            ),
        },
    )


# ============================================================================
# AC1 — all four categories representable
# ============================================================================


class TestAllFourCategoriesRepresentable:
    def test_uncertain_match_category(self):
        rows = [
            {
                "id": "A1", "activity": "Ventilation Level 2", "level": "L4_FUZZY",
                "method": "ambiguous_candidates",
                "candidates": [{"matched_id": "OLD-1", "date_distance": 1}, {"matched_id": "OLD-2", "date_distance": 2}],
                "reason": "Nova found insufficient evidence to reliably match this activity between the two schedules.",
            }
        ]
        items = derive_uncertain_match_items(rows, "proj-1")
        assert len(items) == 1
        assert items[0].category == ReviewCategory.UNCERTAIN_MATCH
        assert items[0].affected_activity_ids == ("A1",)

    def test_low_confidence_id_category(self):
        act = _activity(source_id_conf=0.5)  # below critical_ocr_amber_min (0.80) -> UNVERIFIED
        items = derive_low_confidence_id_items([act], "proj-1")
        assert len(items) == 1
        assert items[0].category == ReviewCategory.LOW_CONFIDENCE_ID
        assert items[0].affected_activity_ids == ("ACT-1",)

    def test_unreadable_date_category(self):
        act = _activity(date_conf=0.4)  # below critical_ocr_amber_min -> UNVERIFIED
        items = derive_unreadable_date_items([act], "proj-1")
        assert len(items) == 1
        assert items[0].category == ReviewCategory.UNREADABLE_DATE

    def test_conflicting_value_category(self):
        issue = {
            "category": "SOURCE_CONFLICT",
            "activity_id": "uuid-9",
            "message": "Rule Source Conflict (invalid_progress): Activity 'uuid-9' has progress 140% > 100%",
        }
        items = derive_conflicting_value_items([issue], "proj-1")
        assert len(items) == 1
        assert items[0].category == ReviewCategory.CONFLICTING_VALUE
        assert items[0].affected_activity_ids == ("uuid-9",)

    def test_non_conflict_validation_issues_are_excluded(self):
        """Only `SOURCE_CONFLICT` issues become review items — a
        structural/logical issue (e.g. Rule 102's circular dependency) is
        not something a human resolves by picking a candidate value."""
        issue = {"category": "LOGICAL", "activity_id": "uuid-9", "message": "circular dependency"}
        assert derive_conflicting_value_items([issue], "proj-1") == []

    def test_high_confidence_fields_produce_no_items(self):
        """A well-extracted activity contributes nothing to the queue —
        the queue is for what Nova is actually unsure about, not a
        listing of every activity."""
        act = _activity(source_id_conf=0.99, date_conf=0.99)
        assert derive_low_confidence_id_items([act], "proj-1") == []
        assert derive_unreadable_date_items([act], "proj-1") == []

    def test_build_review_queue_assembles_all_categories(self):
        rows = [{"id": "A1", "activity": "X", "level": "L5_NO_RELIABLE_MATCH", "method": "none", "candidates": []}]
        act = _activity(source_id_conf=0.5, date_conf=0.5)
        issue = {"category": "SOURCE_CONFLICT", "activity_id": "uuid-1", "message": "conflict"}
        items = build_review_queue(
            "proj-1",
            requires_verification_activities=rows,
            activities=[act],
            validation_issues=[issue],
        )
        categories = {i.category for i in items}
        assert categories == {
            ReviewCategory.UNCERTAIN_MATCH,
            ReviewCategory.LOW_CONFIDENCE_ID,
            ReviewCategory.UNREADABLE_DATE,
            ReviewCategory.CONFLICTING_VALUE,
        }

    def test_missing_inputs_default_to_empty_not_an_error(self):
        """A caller with only match data (e.g. the raw/non-NUSF path)
        still gets a valid, if partial, queue."""
        items = build_review_queue("proj-1")
        assert items == []


# ============================================================================
# AC2 — candidate options where a choice is required
# ============================================================================


class TestCandidateOptions:
    def test_uncertain_match_carries_real_candidates_plus_no_match(self):
        rows = [
            {
                "id": "A1", "activity": "Ventilation Level 2", "level": "L4_FUZZY", "method": "ambiguous_candidates",
                "candidates": [{"matched_id": "OLD-1", "date_distance": 1}, {"matched_id": "OLD-2", "date_distance": 3}],
            }
        ]
        item = derive_uncertain_match_items(rows, "proj-1")[0]
        option_ids = {o.option_id for o in item.candidate_options}
        activity_ids = {o.activity_id for o in item.candidate_options if o.activity_id}
        assert NO_MATCH_OPTION_ID in option_ids
        assert activity_ids == {"OLD-1", "OLD-2"}

    def test_no_match_is_always_present_even_with_zero_candidates(self):
        """Brief §25: 'No match is always an explicit, first-class
        choice' — true even when Nova found no candidates at all
        (L5_NO_RELIABLE_MATCH)."""
        rows = [{"id": "A1", "activity": "X", "level": "L5_NO_RELIABLE_MATCH", "method": "none", "candidates": []}]
        item = derive_uncertain_match_items(rows, "proj-1")[0]
        assert len(item.candidate_options) == 1
        assert item.candidate_options[0].option_id == NO_MATCH_OPTION_ID

    def test_low_confidence_id_items_have_no_fabricated_candidates(self):
        """A low-confidence ID is a single-value confirmation, not a
        multi-candidate choice — no fake options invented to fill the
        field."""
        act = _activity(source_id_conf=0.5)
        item = derive_low_confidence_id_items([act], "proj-1")[0]
        assert item.candidate_options == ()


# ============================================================================
# AC4 — resolutions never mutate extracted source values
# ============================================================================


class TestResolutionsNeverMutateSourceData:
    def test_resolve_and_reopen_never_reference_ingestion_models(self):
        """Structural guarantee: neither method imports or receives an
        `Activity`/`Provenance` — there is nothing for them to mutate
        even if they tried."""
        for fn in (ReviewQueueStore.resolve, ReviewQueueStore.reopen):
            src = inspect.getsource(fn)
            body = src[src.index('"""', src.index('"""') + 3) + 3:]  # strip the docstring
            assert "Activity" not in body
            assert "Provenance" not in body
            assert ".provenance" not in body

    def test_review_item_is_unchanged_after_resolution(self):
        store = ReviewQueueStore()
        item = ReviewItem(
            item_id="i1", project_id="p1", category=ReviewCategory.UNCERTAIN_MATCH,
            affected_activity_ids=("A1",), evidence="uncertain",
            candidate_options=(CandidateOption(option_id="candidate_0", label="Match to OLD-1", activity_id="OLD-1"),),
        )
        store.add_items([item])
        store.resolve("i1", "candidate_0", actor="pm@example.com")
        # The original item object — same fields, same identity of data —
        # is untouched; only history grew.
        assert store.get_item("i1") == item

    def test_resolution_is_a_separate_record_from_the_item(self):
        store = ReviewQueueStore()
        item = ReviewItem(
            item_id="i1", project_id="p1", category=ReviewCategory.CONFLICTING_VALUE,
            affected_activity_ids=("A1",), evidence="conflict",
        )
        store.add_items([item])
        record = store.resolve("i1", NO_MATCH_OPTION_ID, actor="pm@example.com", note="confirmed with site team")
        assert record.item_id == "i1"
        assert record.action == "resolved"
        assert record.note == "confirmed with site team"
        assert record in store.history_of("i1")


# ============================================================================
# AC5 — read-only users cannot resolve items
# ============================================================================


class TestReadOnlyUsersCannotResolve:
    def _store_with_item(self):
        store = ReviewQueueStore()
        store.add_items([
            ReviewItem(
                item_id="i1", project_id="p1", category=ReviewCategory.UNCERTAIN_MATCH,
                affected_activity_ids=("A1",), evidence="uncertain",
                candidate_options=(CandidateOption(option_id="candidate_0", label="X", activity_id="OLD-1"),),
            )
        ])
        return store

    def test_read_only_actor_cannot_resolve(self):
        store = self._store_with_item()
        with pytest.raises(ReadOnlyUserError):
            store.resolve("i1", NO_MATCH_OPTION_ID, actor="viewer@example.com", actor_role="read_only_user")
        assert store.state_of("i1") == ResolutionState.PENDING

    def test_read_only_actor_cannot_reopen(self):
        store = self._store_with_item()
        store.resolve("i1", NO_MATCH_OPTION_ID, actor="pm@example.com")
        with pytest.raises(ReadOnlyUserError):
            store.reopen("i1", actor="viewer@example.com", actor_role="read_only_user")
        assert store.state_of("i1") == ResolutionState.RESOLVED

    def test_read_only_error_is_a_permission_error(self):
        """Lets a Flask route catch it the same way it already catches
        other auth failures, and return 403 (matching the codebase's
        existing `read_only_user` convention) rather than a 500."""
        assert issubclass(ReadOnlyUserError, PermissionError)


# ============================================================================
# Resolve / reopen mechanics — validity, history, state transitions
# ============================================================================


class TestResolveAndReopenMechanics:
    def _store_with_item(self):
        store = ReviewQueueStore()
        store.add_items([
            ReviewItem(
                item_id="i1", project_id="p1", category=ReviewCategory.UNCERTAIN_MATCH,
                affected_activity_ids=("A1",), evidence="uncertain",
                candidate_options=(CandidateOption(option_id="candidate_0", label="X", activity_id="OLD-1"),),
            )
        ])
        return store

    def test_resolving_with_an_invented_option_id_is_rejected(self):
        store = self._store_with_item()
        with pytest.raises(ValueError):
            store.resolve("i1", "made_up_option", actor="pm@example.com")

    def test_resolving_unknown_item_raises(self):
        store = ReviewQueueStore()
        with pytest.raises(KeyError):
            store.resolve("does-not-exist", NO_MATCH_OPTION_ID, actor="pm@example.com")

    def test_reopen_before_resolve_raises(self):
        store = self._store_with_item()
        with pytest.raises(ValueError):
            store.reopen("i1", actor="pm@example.com")

    def test_new_item_starts_pending(self):
        store = self._store_with_item()
        assert store.state_of("i1") == ResolutionState.PENDING

    def test_resolve_then_reopen_then_resolve_keeps_full_history(self):
        store = self._store_with_item()
        store.resolve("i1", "candidate_0", actor="pm@example.com")
        store.reopen("i1", actor="pm2@example.com", note="new info arrived")
        store.resolve("i1", NO_MATCH_OPTION_ID, actor="pm2@example.com")
        history = store.history_of("i1")
        assert [r.action for r in history] == ["resolved", "reopened", "resolved"]
        assert store.state_of("i1") == ResolutionState.RESOLVED

    def test_list_items_scoped_to_project(self):
        store = ReviewQueueStore()
        store.add_items([
            ReviewItem(item_id="i1", project_id="p1", category=ReviewCategory.CONFLICTING_VALUE, affected_activity_ids=(), evidence="x"),
            ReviewItem(item_id="i2", project_id="p2", category=ReviewCategory.CONFLICTING_VALUE, affected_activity_ids=(), evidence="y"),
        ])
        assert [i.item_id for i in store.list_items("p1")] == ["i1"]
        assert [i.item_id for i in store.list_items("p2")] == ["i2"]

    def test_list_items_can_exclude_resolved(self):
        store = self._store_with_item()
        store.resolve("i1", NO_MATCH_OPTION_ID, actor="pm@example.com")
        assert store.list_items("p1", include_resolved=True) != []
        assert store.list_items("p1", include_resolved=False) == []


# ============================================================================
# Wire format — the shape that actually crosses the wire to a Flask backend
# ============================================================================


class TestWireFormat:
    def test_review_items_are_json_serializable_via_dataclasses_asdict(self):
        """`src/main.py`'s `/version-1.0/health` and `/version-1.0/kemp/
        health` endpoints attach `review_queue` to their JSON response as
        `[dataclasses.asdict(item) for item in build_review_queue(...)]`
        — this pins that the resulting structure actually survives a real
        `json.dumps` round trip (the `ReviewCategory` enum is `str`-based
        specifically so this works with no custom encoder)."""
        rows = [
            {
                "id": "A1", "activity": "Ventilation Level 2", "level": "L4_FUZZY",
                "method": "ambiguous_candidates",
                "candidates": [{"matched_id": "OLD-1", "date_distance": 1}],
            }
        ]
        items = build_review_queue("analysis-123", requires_verification_activities=rows)
        as_dicts = [dataclasses.asdict(item) for item in items]
        dumped = json.dumps(as_dicts)
        reloaded = json.loads(dumped)
        assert reloaded[0]["category"] == "uncertain_match"
        assert reloaded[0]["candidate_options"][0]["activity_id"] == "OLD-1"
        assert reloaded[0]["candidate_options"][-1]["option_id"] == NO_MATCH_OPTION_ID


class TestWiredIntoTheHealthEndpoints:
    """Source-level pin (no live DB/session in this suite to actually
    invoke the FastAPI endpoints) that both `/version-1.0/health` and
    `/version-1.0/kemp/health` attach `review_queue` to their response,
    ahead of `TL-8.1`'s own `Files:` list naming `src/main.py`."""

    @pytest.fixture
    def main_source(self):
        main_path = pathlib.Path(__file__).resolve().parents[2] / "src" / "main.py"
        return main_path.read_text(encoding="utf-8")

    def test_both_health_endpoints_attach_review_queue(self, main_source):
        assert main_source.count('"review_queue": review_queue') == 2

    def test_review_queue_built_from_requires_verification_activities(self, main_source):
        assert "build_review_queue(" in main_source
        assert 'json_data.get("requires_verification_activities", [])' in main_source
