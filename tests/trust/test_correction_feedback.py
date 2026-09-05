"""Tests for TL-8.4 — Corrections feed back into matching.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-8-review-queue.md` (TL-8.4):

- AC1: Mapped pairs skip the review queue on subsequent uploads.
- AC2: Match method records human verification.
- AC3: "Why?" shows that a human confirmed this match, and when.
- AC4: Contradiction between mapping and strong source evidence raises a conflict.

Do-not: do not let a stored mapping silently override contradicting
source evidence.
"""
from __future__ import annotations

from src.experimental.nusf_compare_engine import _resolve_activity_matches
from src.trust.match_mapping import MatchMappingStore
from src.trust.matching import MatchLevel


def _row(identity, name, location, start, finish, source_id=None, match_method=None):
    row = {
        "_identity": identity, "name": name, "location_path": location,
        "planned_start": start, "planned_finish": finish,
    }
    if source_id:
        row["source_id"] = source_id
    if match_method:
        row["match_method"] = match_method
    return row


class TestMappedPairsSkipTheReviewQueue:
    def test_ambiguous_pair_is_resolved_by_a_verified_mapping(self):
        """The exact TL-3.3 ambiguous-duplicate-name fixture — but this
        time a human already confirmed which candidate is correct."""
        old_rows = [
            _row("Dæksel_A", "Dæksel", "Bygning 1", "2026-02-01", "2026-02-10"),
            _row("Dæksel_B", "Dæksel", "Bygning 1", "2026-02-02", "2026-02-11"),
        ]
        new_rows = [_row("Dæksel_A_v2", "Dæksel", "Bygning 1", "2026-02-01", "2026-02-10")]

        store = MatchMappingStore()
        store.confirm("proj-1", "dæksel|bygning 1", "Dæksel_B", "site walkthrough", "pm@example.com")

        matches, results = _resolve_activity_matches(
            old_rows, new_rows,
            mapping_lookup=lambda key: store.active_mapping("proj-1", key),
        )
        assert matches["Dæksel_A_v2"]["_identity"] == "Dæksel_B"
        assert results["Dæksel_A_v2"].requires_verification is False
        assert results["Dæksel_A_v2"].level == MatchLevel.L1_EXACT_VERIFIED_ID

    def test_without_a_mapping_the_same_pair_still_requires_review(self):
        """Sanity check: it's the mapping that changes the outcome, not a
        change to the underlying ambiguity logic itself."""
        old_rows = [
            _row("Dæksel_A", "Dæksel", "Bygning 1", "2026-02-01", "2026-02-10"),
            _row("Dæksel_B", "Dæksel", "Bygning 1", "2026-02-02", "2026-02-11"),
        ]
        new_rows = [_row("Dæksel_A_v2", "Dæksel", "Bygning 1", "2026-02-01", "2026-02-10")]
        matches, results = _resolve_activity_matches(old_rows, new_rows)
        assert "Dæksel_A_v2" not in matches
        assert results["Dæksel_A_v2"].requires_verification is True

    def test_confirmed_no_match_is_honoured_and_not_re_ambiguated(self):
        """A confirmed "no match" is never re-run through ambiguity
        detection (it does NOT get a fresh `ambiguous_candidates` /
        ad-hoc `unmatched` verdict every upload) — its `method` field
        shows a human already looked at it, which is what `"Why?"` (AC3)
        and the review queue's own resolved-state (TL-8.1) key off of.
        `requires_verification` stays `True` (the `MatchResult` model's
        own TL-3.1 invariant for any L4/L5 level, unconditionally) — an
        already-resolved item is filtered out at the review-queue layer
        (`ReviewQueueStore.list_items(..., include_resolved=False)`),
        not by lying about the match's own confidence level."""
        old_rows = [
            _row("Dæksel_A", "Dæksel", "Bygning 1", "2026-02-01", "2026-02-10"),
            _row("Dæksel_B", "Dæksel", "Bygning 1", "2026-02-02", "2026-02-11"),
        ]
        new_rows = [_row("Dæksel_A_v2", "Dæksel", "Bygning 1", "2026-02-01", "2026-02-10")]

        store = MatchMappingStore()
        store.confirm("proj-1", "dæksel|bygning 1", None, "confirmed genuinely new activity", "pm@example.com")

        matches, results = _resolve_activity_matches(
            old_rows, new_rows,
            mapping_lookup=lambda key: store.active_mapping("proj-1", key),
        )
        assert "Dæksel_A_v2" not in matches
        assert results["Dæksel_A_v2"].method == "human_verified_no_match"
        # Never re-flagged as freshly ambiguous or unmatched — that's the
        # actual "skip re-litigating the same ambiguity" guarantee.
        assert results["Dæksel_A_v2"].method not in ("ambiguous_candidates", "unmatched")


class TestMatchMethodRecordsHumanVerification:
    def test_method_is_human_verified(self):
        old_rows = [_row("OLD-1", "Ventilation Level 2", "Building A", "2026-01-01", "2026-01-10")]
        new_rows = [_row("NEW-1", "Ventilation Level 2", "Building A", "2026-01-01", "2026-01-10")]
        store = MatchMappingStore()
        store.confirm("proj-1", "ventilation level 2|building a", "OLD-1", "manual pick", "pm@example.com")
        _, results = _resolve_activity_matches(
            old_rows, new_rows, mapping_lookup=lambda key: store.active_mapping("proj-1", key),
        )
        assert results["NEW-1"].method == "human_verified"
        # AC3: the mapping itself (queryable separately, "Why?"-visible)
        # records who and when.
        mapping = store.active_mapping("proj-1", "ventilation level 2|building a")
        assert mapping.confirmed_by == "pm@example.com"
        assert mapping.confirmed_at is not None


class TestContradictionRaisesConflictNotSilentOverride:
    def test_mapping_contradicting_a_fresh_verified_id_match_raises_conflict(self):
        """Do-not: a human mapping from weeks ago must not silently win
        over a brand-new, strong verified-ID match to a DIFFERENT
        activity — that's exactly the "evidence changed materially"
        case TL-8.5 exists for; this function raises the conflict rather
        than picking a side."""
        old_rows = [
            _row("OLD-1", "Ventilation Level 2", "Building A", "2026-01-01", "2026-01-10"),
            _row("OLD-2", "Ventilation Level 2", "Building A", "2026-01-05", "2026-01-14", source_id="ACT-99", match_method="verified_source_id"),
        ]
        new_rows = [
            _row("NEW-1", "Ventilation Level 2", "Building A", "2026-01-05", "2026-01-14", source_id="ACT-99", match_method="verified_source_id"),
        ]
        store = MatchMappingStore()
        # Human confirmed OLD-1 weeks ago; but NEW-1 now carries a fresh,
        # verified source id that actually points to OLD-2.
        store.confirm("proj-1", "ventilation level 2|building a", "OLD-1", "old manual pick", "pm@example.com")

        matches, results = _resolve_activity_matches(
            old_rows, new_rows, mapping_lookup=lambda key: store.active_mapping("proj-1", key),
        )
        assert "NEW-1" not in matches
        result = results["NEW-1"]
        assert result.method == "mapping_conflict"
        assert result.requires_verification is True
        matched_ids = {c["matched_id"] for c in result.candidates}
        assert matched_ids == {"OLD-1", "OLD-2"}

    def test_mapping_agreeing_with_fresh_verified_id_is_not_a_conflict(self):
        old_rows = [
            _row("OLD-1", "Ventilation Level 2", "Building A", "2026-01-01", "2026-01-10", source_id="ACT-99", match_method="verified_source_id"),
        ]
        new_rows = [
            _row("NEW-1", "Ventilation Level 2", "Building A", "2026-01-01", "2026-01-10", source_id="ACT-99", match_method="verified_source_id"),
        ]
        store = MatchMappingStore()
        store.confirm("proj-1", "ventilation level 2|building a", "OLD-1", "manual pick", "pm@example.com")
        matches, results = _resolve_activity_matches(
            old_rows, new_rows, mapping_lookup=lambda key: store.active_mapping("proj-1", key),
        )
        assert matches["NEW-1"]["_identity"] == "OLD-1"
        assert results["NEW-1"].method == "human_verified"


class TestMappingLookupIsOptional:
    def test_no_mapping_lookup_behaves_exactly_as_before(self):
        """The function's behaviour with no `mapping_lookup` argument at
        all must be byte-for-byte identical to before TL-8.4 — this
        parameter must never be load-bearing for existing callers."""
        old_rows = [_row("OLD-1", "Foundations", "Zone A", "2026-01-01", "2026-01-10")]
        new_rows = [_row("NEW-1", "Foundations", "Zone A", "2026-01-02", "2026-01-11")]
        matches, results = _resolve_activity_matches(old_rows, new_rows)
        assert matches["NEW-1"]["_identity"] == "OLD-1"

    def test_mapping_lookup_returning_none_for_everything_is_a_no_op(self):
        old_rows = [_row("OLD-1", "Foundations", "Zone A", "2026-01-01", "2026-01-10")]
        new_rows = [_row("NEW-1", "Foundations", "Zone A", "2026-01-02", "2026-01-11")]
        matches, results = _resolve_activity_matches(old_rows, new_rows, mapping_lookup=lambda key: None)
        assert matches["NEW-1"]["_identity"] == "OLD-1"
