"""Tests for TL-8.3 — Verified match mapping store.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-8-review-queue.md` (TL-8.3):

- AC1: Confirmed mappings persist and are reused on the next upload.
- AC2: Each mapping records evidence, author, and timestamp.
- AC3: Human-verified matches are distinguishable from source-verified ones.
- AC4: Mappings do not leak across projects or tenants.

Do-not: do not make human-confirmed mappings globally applicable.
"""
from __future__ import annotations

from datetime import datetime

from src.trust.match_mapping import MatchMappingStore, VerifiedMapping


class TestConfirmedMappingsPersist:
    def test_confirmed_mapping_is_reused(self):
        store = MatchMappingStore()
        store.confirm("proj-1", "ventilation::level-2", "OLD-1", "manual pick", "pm@example.com")
        mapping = store.active_mapping("proj-1", "ventilation::level-2")
        assert mapping is not None
        assert mapping.old_activity_id == "OLD-1"

    def test_no_mapping_returns_none(self):
        store = MatchMappingStore()
        assert store.active_mapping("proj-1", "unknown::key") is None

    def test_confirming_again_creates_a_new_version_not_an_edit(self):
        store = MatchMappingStore()
        first = store.confirm("proj-1", "k", "OLD-1", "e1", "a@x.com")
        second = store.confirm("proj-1", "k", "OLD-2", "e2", "b@x.com")
        assert second.version == first.version + 1
        assert store.active_mapping("proj-1", "k").old_activity_id == "OLD-2"
        # The first version is retained, not deleted or edited.
        history = store.history_of("proj-1", "k")
        assert len(history) == 2
        assert history[0] == first

    def test_confirmed_no_match_is_a_valid_mapping(self):
        """A human confirming 'these are genuinely different activities'
        (old_activity_id=None) is a real, reusable decision too."""
        store = MatchMappingStore()
        store.confirm("proj-1", "k", None, "confirmed distinct activities", "pm@example.com")
        mapping = store.active_mapping("proj-1", "k")
        assert mapping is not None
        assert mapping.old_activity_id is None


class TestMappingRecordsEvidenceAuthorTimestamp:
    def test_mapping_carries_all_three(self):
        store = MatchMappingStore()
        mapping = store.confirm("proj-1", "k", "OLD-1", "site visit confirmed", "pm@example.com")
        assert mapping.evidence == "site visit confirmed"
        assert mapping.confirmed_by == "pm@example.com"
        assert isinstance(mapping.confirmed_at, datetime)


class TestHumanVerifiedDistinguishableFromSourceVerified:
    def test_mapping_id_and_confirmed_by_mark_it_as_human_verified(self):
        """The mapping object itself, distinct from a `MatchResult`, is
        the structural signal: a `MatchResult` with `method='verified_
        source_id'` (TL-3.1) exists whether or not any human was ever
        involved; a `VerifiedMapping` only exists because a human
        confirmed it (TL-8.4 wires `method='human_verified'` onto the
        `MatchResult` it produces — see `test_correction_feedback.py`)."""
        store = MatchMappingStore()
        mapping = store.confirm("proj-1", "k", "OLD-1", "manual", "pm@example.com")
        assert mapping.confirmed_by == "pm@example.com"
        assert mapping.mapping_id  # a real, non-empty identity of its own


class TestMappingsAreProjectScoped:
    def test_same_match_key_different_projects_do_not_collide(self):
        store = MatchMappingStore()
        store.confirm("proj-1", "ventilation::level-2", "OLD-1", "e", "a@x.com")
        store.confirm("proj-2", "ventilation::level-2", "OLD-99", "e", "b@x.com")
        assert store.active_mapping("proj-1", "ventilation::level-2").old_activity_id == "OLD-1"
        assert store.active_mapping("proj-2", "ventilation::level-2").old_activity_id == "OLD-99"

    def test_history_is_also_project_scoped(self):
        store = MatchMappingStore()
        store.confirm("proj-1", "k", "OLD-1", "e", "a@x.com")
        assert store.history_of("proj-2", "k") == ()
