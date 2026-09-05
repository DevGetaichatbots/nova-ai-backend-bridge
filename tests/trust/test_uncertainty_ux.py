"""Tests for TL-7.8 — Reassuring uncertainty UX (not error states).

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-7-trust-surface.md` (TL-7.8):

- AC1: Uncertainty states render as informative, not as errors.
- AC2: `BLOCK` renders as a protective pause with an explanation.
- AC4: Flask status derivation accounts for gating outcomes, not just
  HTTP 200 (`_truncation_block_response` marks progress as `blocked`,
  never `error`).

(AC3 — both React apps handle gated/partial/no-answer states — and AC5 —
screens reviewed against brief §42's wording — are the manual-review /
frontend half of this task; see `ComparisonAnalysis.jsx`/
`ScheduleAnalysis.jsx` in both `kemp&lauritzen/app` and
`website/workspace/app`.)

Do-not: never show a raw exception or an empty dashboard. Every
uncertainty state must explain itself and offer a next step (brief §42's
literal four-part shape: heading / what happened / what Nova did / a
next step).
"""
from __future__ import annotations

from src.trust.preflight import PreflightReport, TruncationReport
from src.trust.response_contract import build_uncertainty_notice

# Brief §42's own "Bad" example and its close relatives — none of these
# words may appear anywhere a BLOCK notice is rendered.
_ANTI_PATTERN_WORDS = ("error", "failed", "broken", "crash", "exception")


def _all_notice_dicts():
    for kind in ("preflight_block", "context_truncation_block"):
        for language in ("en", "da"):
            yield kind, language, build_uncertainty_notice(kind, language)


class TestUncertaintyNoticeShape:
    """AC2: brief §42's literal four-part shape — heading / what happened
    / what Nova did about it / a next step."""

    def test_notice_has_all_four_brief_42_parts(self):
        for kind, language, notice in _all_notice_dicts():
            assert set(notice.keys()) == {"heading", "what_happened", "what_nova_did", "action_label"}, (
                f"{kind}/{language} missing a brief §42 part: {notice!r}"
            )
            for key, value in notice.items():
                assert value and value.strip(), f"{kind}/{language}.{key} is empty"

    def test_heading_matches_brief_42s_own_wording(self):
        """Brief §42's worked example heading is literally 'Review
        required' — not 'Error', not 'Warning'."""
        for kind, language, notice in _all_notice_dicts():
            if language == "en":
                assert notice["heading"] == "Review required"
            else:
                assert notice["heading"] == "Gennemgang påkrævet"

    def test_action_label_reads_as_a_next_step_not_a_dead_end(self):
        for kind, language, notice in _all_notice_dicts():
            assert "→" in notice["action_label"] or "->" in notice["action_label"]

    def test_unrecognized_kind_falls_back_rather_than_raising(self):
        """A BLOCK response must never fail to return because the notice
        lookup didn't recognize the kind — falling back to a still-
        reassuring default is strictly better than a 500."""
        notice = build_uncertainty_notice("some_future_kind_not_yet_named", "en")
        assert notice["heading"] == "Review required"

    def test_unrecognized_language_falls_back_to_english(self):
        notice = build_uncertainty_notice("preflight_block", "fr")
        assert notice["heading"] == "Review required"


class TestNeverErrorShaped:
    """AC1/Do-not: never a bare 'ERROR' or crash-shaped word anywhere a
    BLOCK notice is rendered — brief §42's whole point."""

    def test_no_anti_pattern_words_in_any_notice(self):
        for kind, language, notice in _all_notice_dicts():
            haystack = " ".join(notice.values()).lower()
            for word in _ANTI_PATTERN_WORDS:
                assert word not in haystack, (
                    f"{kind}/{language} notice contains anti-pattern word {word!r}: {notice!r}"
                )

    def test_what_nova_did_communicates_protection_not_failure(self):
        """Brief §42: 'That communicates: Nova protected you from a
        potentially incorrect result.' — the `what_nova_did` sentence is
        the part that has to carry this, so it must be phrased as a
        deliberate, protective choice ('paused'), not something that
        merely happened to it."""
        for kind, language, notice in _all_notice_dicts():
            if language == "en":
                assert "paused" in notice["what_nova_did"].lower()


class TestRefusalResponsesCarryTheNotice:
    """AC2/AC4: both existing BLOCK gating decisions (`TL-4.6` pre-flight,
    `TL-5.5` context-truncation) attach the brief §42 notice and an
    explicit `success: False` — the frontends' upload handlers already
    branch on `data.success`, so a BLOCK must be distinguishable on a
    field a caller is already checking."""

    def test_preflight_refusal_response_carries_notice_and_success_false(self):
        report = PreflightReport(
            activities_detected=10, confidently_parsed=2, requiring_review=0,
            unresolved=8, decision="BLOCK", reason="too many unresolved ids",
        )
        response = report.to_refusal_response()
        assert response["success"] is False
        assert response["status"] == "blocked"
        assert response["notice"]["heading"] == "Review required"

    def test_preflight_refusal_response_localizes_the_notice(self):
        report = PreflightReport(
            activities_detected=10, confidently_parsed=2, requiring_review=0,
            unresolved=8, decision="BLOCK", reason="too many unresolved ids",
        )
        response = report.to_refusal_response("da")
        assert response["notice"]["heading"] == "Gennemgang påkrævet"

    def test_truncation_refusal_response_carries_notice_and_success_false(self):
        report = TruncationReport(
            total_chunks=10, included_chunks=2, total_bytes=1_000_000,
            included_bytes=200_000, decision="BLOCK", reason="too much omitted",
        )
        response = report.to_refusal_response()
        assert response["success"] is False
        assert response["status"] == "blocked"
        assert "heading" in response["notice"]

    def test_truncation_refusal_response_localizes_the_notice(self):
        report = TruncationReport(
            total_chunks=10, included_chunks=2, total_bytes=1_000_000,
            included_bytes=200_000, decision="BLOCK", reason="too much omitted",
        )
        response = report.to_refusal_response("da")
        assert response["notice"]["heading"] == "Gennemgang påkrævet"

    def test_the_two_refusal_shapes_use_different_notice_wording(self):
        """The pre-flight and context-truncation BLOCKs are different
        situations — the notice should say something specific to each,
        not the exact same boilerplate copy-pasted twice."""
        preflight = build_uncertainty_notice("preflight_block", "en")
        truncation = build_uncertainty_notice("context_truncation_block", "en")
        assert preflight["what_happened"] != truncation["what_happened"]


class TestFlaskStatusDerivationAccountsForGating:
    """AC4 (Do item 3/4): a BLOCK must not be represented the same way as
    an actual crash in the polling-progress dict — that is the concrete
    'Flask marks a run completed/errored on HTTP 200 alone' hazard the
    task names, for the one BLOCK gating decision that is already wired
    into a live route (`TL-5.5`'s context-truncation gate)."""

    def test_blocked_progress_stage_exists_and_is_distinct_from_error(self):
        from src.main import PROGRESS_STAGES
        assert "blocked" in PROGRESS_STAGES
        assert PROGRESS_STAGES["blocked"]["en"] != PROGRESS_STAGES["error"]["en"]

    def test_blocked_stage_copy_has_no_anti_pattern_words(self):
        from src.main import PROGRESS_STAGES
        for language in ("en", "da"):
            text = PROGRESS_STAGES["blocked"][language].lower()
            for word in _ANTI_PATTERN_WORDS:
                assert word not in text, f"PROGRESS_STAGES['blocked'][{language!r}] contains {word!r}"

    def test_truncation_block_response_marks_progress_as_blocked_not_error(self):
        from src.main import _predictive_progress, _truncation_block_response

        report = TruncationReport(
            total_chunks=10, included_chunks=2, total_bytes=1_000_000,
            included_bytes=200_000, decision="BLOCK", reason="too much omitted",
        )
        analysis_id = "test-uncertainty-ux-analysis-id"
        try:
            _truncation_block_response(report, analysis_id, "en", "test.csv")
            progress = _predictive_progress.get(analysis_id)
            assert progress is not None, "no progress entry recorded for the BLOCK"
            assert progress["stage"] == "blocked"
            assert progress["stage"] != "error"
        finally:
            _predictive_progress.pop(analysis_id, None)

    def test_truncation_block_response_still_returns_the_refusal_shape(self):
        """The progress-stage fix must not have come at the cost of the
        response body itself — `TL-5.5`'s existing contract stays intact."""
        from src.main import _truncation_block_response

        report = TruncationReport(
            total_chunks=10, included_chunks=2, total_bytes=1_000_000,
            included_bytes=200_000, decision="BLOCK", reason="too much omitted",
        )
        response = _truncation_block_response(report, "test-id-2", "en", "test.csv")
        assert response["status"] == "blocked"
        assert response["success"] is False
        assert response["notice"]["heading"] == "Review required"
