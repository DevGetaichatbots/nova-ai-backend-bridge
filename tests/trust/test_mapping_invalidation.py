"""Tests for TL-8.5 — Mapping invalidation.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-8-review-queue.md` (TL-8.5):

- AC1: Material-change criteria defined, documented, and tested.
- AC2: Invalidated mappings return to the queue with an explanation.
- AC3: Invalidation history retained.
- AC4: Fixture: resolve a match, materially change the activity, confirm invalidation.

Do-not: do not delete invalidated mappings. Do not re-surface an item
without explaining what changed.
"""
from __future__ import annotations

from src.trust.match_mapping import MatchMappingStore, detect_material_change


class TestMaterialChangeCriteria:
    """AC1: brief's minimum list, each independently testable."""

    def test_no_change_is_not_material(self):
        assert detect_material_change(
            original_name="Ventilation Level 2", current_name="Ventilation Level 2",
            original_location="Building A", current_location="Building A",
        ) is None

    def test_minor_rewording_is_not_material(self):
        """A small wording tweak (typo fix, punctuation) is not the same
        as the activity becoming a different thing."""
        assert detect_material_change(
            original_name="Ventilation Level 2", current_name="Ventilation, Level 2",
        ) is None

    def test_name_changed_beyond_similarity_threshold_is_material(self):
        reason = detect_material_change(
            original_name="Ventilation Level 2", current_name="Electrical Rough-in Level 5",
        )
        assert reason is not None
        assert "name changed" in reason.lower()

    def test_location_change_is_material(self):
        reason = detect_material_change(
            original_location="Building A", current_location="Building B",
        )
        assert reason is not None
        assert "location changed" in reason.lower()

    def test_contradicting_verified_id_is_material(self):
        reason = detect_material_change(contradicting_verified_id="ACT-999")
        assert reason is not None
        assert "ACT-999" in reason

    def test_split_into_multiple_activities_is_material(self):
        reason = detect_material_change(split_into=["ACT-1a", "ACT-1b"])
        assert reason is not None
        assert "split" in reason.lower()

    def test_split_into_a_single_activity_is_not_material(self):
        """A 1-element `split_into` means nothing actually split."""
        assert detect_material_change(split_into=["ACT-1"]) is None


class TestInvalidatedMappingsReturnWithExplanation:
    def test_reconcile_invalidates_on_material_change_and_returns_reason(self):
        store = MatchMappingStore()
        store.confirm("proj-1", "k", "OLD-1", "manual pick", "pm@example.com")
        mapping, reason = store.reconcile(
            "proj-1", "k",
            original_name="Ventilation Level 2", current_name="Structural Steel Level 9",
        )
        assert mapping is None
        assert reason is not None and "name changed" in reason.lower()

    def test_reconcile_returns_the_mapping_unchanged_when_still_valid(self):
        store = MatchMappingStore()
        store.confirm("proj-1", "k", "OLD-1", "manual pick", "pm@example.com")
        mapping, reason = store.reconcile(
            "proj-1", "k",
            original_name="Ventilation Level 2", current_name="Ventilation Level 2",
        )
        assert mapping is not None
        assert mapping.old_activity_id == "OLD-1"
        assert reason is None

    def test_invalidated_mapping_no_longer_active(self):
        store = MatchMappingStore()
        store.confirm("proj-1", "k", "OLD-1", "manual pick", "pm@example.com")
        store.invalidate("proj-1", "k", "activity was split")
        assert store.active_mapping("proj-1", "k") is None


class TestInvalidationHistoryRetained:
    def test_invalidated_version_stays_in_history(self):
        store = MatchMappingStore()
        store.confirm("proj-1", "k", "OLD-1", "manual pick", "pm@example.com")
        store.invalidate("proj-1", "k", "location changed")
        history = store.history_of("proj-1", "k")
        assert len(history) == 1
        assert history[0].invalidated is True
        assert history[0].invalidated_reason == "location changed"
        assert history[0].old_activity_id == "OLD-1"  # never deleted, never blanked

    def test_invalidating_twice_is_a_no_op_not_an_error(self):
        store = MatchMappingStore()
        store.confirm("proj-1", "k", "OLD-1", "manual pick", "pm@example.com")
        store.invalidate("proj-1", "k", "reason 1")
        result = store.invalidate("proj-1", "k", "reason 2")
        assert result is None
        assert store.history_of("proj-1", "k")[0].invalidated_reason == "reason 1"

    def test_a_new_confirmation_after_invalidation_is_a_fresh_version(self):
        """AC4's fixture, end to end: resolve a match, materially change
        the activity (invalidating it), then a human resolves it again —
        the full history (original, invalidation, re-confirmation) is
        all retained."""
        store = MatchMappingStore()
        store.confirm("proj-1", "k", "OLD-1", "first pick", "pm@example.com")
        store.invalidate("proj-1", "k", "the activity was renamed")
        store.confirm("proj-1", "k", "OLD-2", "re-confirmed after rename", "pm2@example.com")

        history = store.history_of("proj-1", "k")
        assert len(history) == 2
        assert history[0].invalidated is True
        assert history[1].invalidated is False
        assert store.active_mapping("proj-1", "k").old_activity_id == "OLD-2"
