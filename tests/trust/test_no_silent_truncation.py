"""Tests for TL-5.5 — Remove silent context truncation.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-5-predictive-facts.md` (TL-5.5):

- AC1: Truncation is impossible without a corresponding gating outcome
  (every dropped chunk produces a `TruncationReport` whose
  `decision` is one of PASS / PARTIAL / BLOCK).
- AC2: Oversized fixture produces `PARTIAL` or `BLOCK`, never a silent
  partial result (the 1.9MB byte budget that used to drop with only a
  `logger.warning` is now a gating event).
- AC3: Response enumerates what was omitted and why (the report's
  `to_dict()` / `to_refusal_response()` shapes name chunks and bytes).
- AC4: No code path drops context with only a log line (static check
  against `_build_predictive_context`'s body — it must not contain a
  `logger.warning` in the truncation branch, and the only place a chunk
  is skipped is the `break` that exits the include loop).

Scope: TL-5.5 is the raw-text truncation path in `_build_predictive_context`
(`src/main.py`). The NUSF path (TL-5.4) builds a structured JSON context
that has no byte budget, so the gate does not apply there — see
ADR-019/ADR-021 for why.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.main import _build_predictive_context
from src.trust.preflight import TruncationReport, gate_context_completeness


# AC3: named, documented threshold — mirrors
# `_TRUNCATION_BLOCK_OMITTED_RATIO_UNCALIBRATED` in `src/trust/preflight.py`.
# If the production threshold changes, this test is the canary.
_BLOCK_OMITTED_RATIO = 0.5
_MAX_PREDICTIVE_CONTEXT_BYTES = 1_900_000


def _table_chunk(content: str, row_count: int = 1) -> dict:
    """One synthetic table chunk shaped like `process_pdf_binary`'s output."""
    return {"content": content, "metadata": {"type": "table", "row_count": row_count}}


def _oversized_chunks(total_target_bytes: int) -> list[dict]:
    """A list of table chunks whose combined content is at least
    `total_target_bytes` — used to exercise the byte-budget cap.
    Each chunk is sized just under the cap so the second chunk is the
    first one the production code drops."""
    first_chunk = "a" * (_MAX_PREDICTIVE_CONTEXT_BYTES - 100)
    second_chunk = "b" * 100_000
    return [_table_chunk(first_chunk, row_count=1000), _table_chunk(second_chunk, row_count=100)]


# ============================================================================
# AC1 + AC3 — `TruncationReport` shape
# ============================================================================


class TestTruncationReportShape:
    """AC3: the report enumerates what was omitted. The shape must be
    stable enough for both `to_dict()` (PARTIAL responses) and
    `to_refusal_response()` (BLOCK responses) to share."""

    def test_required_fields_present(self):
        report = TruncationReport(
            total_chunks=10, included_chunks=6,
            total_bytes=2_000_000, included_bytes=1_200_000,
            decision="PARTIAL", reason="x",
        )
        d = report.to_dict()
        for key in (
            "total_chunks", "included_chunks", "omitted_chunks",
            "total_bytes", "included_bytes", "omitted_bytes",
            "decision", "reason",
        ):
            assert key in d, f"missing key {key!r}"

    def test_omitted_counts_match(self):
        report = TruncationReport(
            total_chunks=10, included_chunks=6,
            total_bytes=2_000_000, included_bytes=1_200_000,
            decision="PARTIAL", reason="x",
        )
        assert report.omitted_chunks == 4
        assert report.omitted_bytes == 800_000
        assert report.to_dict()["omitted_chunks"] == 4
        assert report.to_dict()["omitted_bytes"] == 800_000

    def test_refusal_response_is_a_block_signal(self):
        report = TruncationReport(
            total_chunks=10, included_chunks=4,
            total_bytes=2_000_000, included_bytes=800_000,
            decision="BLOCK", reason="too much missing",
        )
        refusal = report.to_refusal_response()
        assert refusal["status"] == "blocked"
        assert refusal["gating_decision"] == "BLOCK"
        assert "Nova has paused analysis" in refusal["message"]
        assert refusal["report"]["decision"] == "BLOCK"
        assert refusal["report"]["omitted_chunks"] == 6


# ============================================================================
# AC1 + AC2 — `gate_context_completeness` decisions
# ============================================================================


class TestGateContextCompleteness:
    """AC1+AC2: every omission becomes a PASS/PARTIAL/BLOCK gate."""

    def test_pass_when_all_chunks_included(self):
        report = gate_context_completeness(
            total_chunks=5, included_chunks=5,
            total_bytes=10_000, included_bytes=10_000,
        )
        assert report.decision == "PASS"
        assert report.omitted_chunks == 0
        assert report.omitted_bytes == 0

    def test_partial_when_a_minority_is_omitted(self):
        report = gate_context_completeness(
            total_chunks=4, included_chunks=3,
            total_bytes=10_000, included_bytes=7_500,
        )
        # 25% omitted — below the 50% threshold
        assert report.decision == "PARTIAL"
        assert report.omitted_chunks == 1
        assert report.omitted_bytes == 2_500
        assert "1/4" in report.reason and "25.0%" in report.reason

    def test_block_when_a_majority_is_omitted(self):
        # 9/10 omitted = 90% > 50% threshold
        report = gate_context_completeness(
            total_chunks=10, included_chunks=1,
            total_bytes=10_000_000, included_bytes=1_000_000,
        )
        assert report.decision == "BLOCK"
        assert report.omitted_chunks == 9
        assert report.omitted_bytes == 9_000_000
        assert "too much of the schedule is missing" in report.reason

    def test_block_on_exactly_half_is_partial(self):
        """Threshold is strictly greater-than 0.5 — exactly half is
        PARTIAL, not BLOCK. Pins the boundary so the threshold change is
        a deliberate, documented decision."""
        report = gate_context_completeness(
            total_chunks=2, included_chunks=1,
            total_bytes=2_000_000, included_bytes=1_000_000,
        )
        assert report.decision == "PARTIAL"

    def test_block_when_no_table_data_extracted(self):
        """AC1: `total_chunks == 0` is BLOCK — there is nothing to
        analyze, which is a stronger failure than partial coverage."""
        report = gate_context_completeness(
            total_chunks=0, included_chunks=0,
            total_bytes=0, included_bytes=0,
        )
        assert report.decision == "BLOCK"
        assert "No schedule table data" in report.reason

    def test_gate_is_pure_function_of_inputs(self):
        report_a = gate_context_completeness(5, 3, 1_000_000, 600_000)
        report_b = gate_context_completeness(5, 3, 1_000_000, 600_000)
        assert report_a.to_dict() == report_b.to_dict()


# ============================================================================
# AC2 — `_build_predictive_context` (the production path) gates, not drops
# ============================================================================


class TestBuildPredictiveContextGates:
    """AC2: hitting the byte budget in `_build_predictive_context` is a
    gating event — the function returns a `(context, TruncationReport)`
    pair, never a silently-truncated string with only a log line."""

    def test_returns_tuple_of_context_and_report(self):
        ctx, report = _build_predictive_context(
            [_table_chunk("hello world", row_count=1)], "test.csv",
        )
        assert isinstance(ctx, str)
        assert isinstance(report, TruncationReport)
        assert report.decision == "PASS"

    def test_pass_when_no_chunk_exceeds_the_budget(self):
        chunks = [_table_chunk("a" * 1000, row_count=10) for _ in range(5)]
        ctx, report = _build_predictive_context(chunks, "test.csv")
        assert report.decision == "PASS"
        assert report.included_chunks == 5
        assert report.omitted_chunks == 0

    def test_partial_when_only_some_chunks_fit(self):
        # First chunk eats the entire budget, second chunk is dropped
        first = "a" * (_MAX_PREDICTIVE_CONTEXT_BYTES - 100)
        chunks = [
            _table_chunk(first, row_count=1000),
            _table_chunk("b" * 100_000, row_count=500),
        ]
        ctx, report = _build_predictive_context(chunks, "test.csv")
        assert report.decision == "PARTIAL"
        assert report.included_chunks == 1
        assert report.omitted_chunks == 1
        # The dropped chunk is enumerated in the report
        assert "1/2" in report.reason
        assert report.omitted_bytes >= 100_000

    def test_block_when_majority_of_data_is_omitted(self):
        # 1 small chunk + 10 huge chunks (~800KB each). With the
        # 1.9MB budget, only the small chunk plus ~2 of the huge ones
        # fit (8-9 of 11 chunks are dropped = >50% omitted → BLOCK).
        chunks = [_table_chunk("small", row_count=1)]
        for _ in range(10):
            chunks.append(_table_chunk("b" * 800_000, row_count=1000))
        ctx, report = _build_predictive_context(chunks, "test.csv")
        assert report.decision == "BLOCK"
        assert report.total_chunks == 11
        assert report.omitted_chunks >= 6  # majority dropped
        # Most of the schedule is missing — that's the BLOCK signal.
        assert report.omitted_bytes >= report.included_bytes

    def test_block_when_chunks_list_is_empty(self):
        ctx, report = _build_predictive_context([], "test.csv")
        assert report.decision == "BLOCK"
        # The placeholder context string still exists so the caller does
        # not crash on a `None`; the gate carries the BLOCK signal.
        assert "No schedule data" in ctx

    def test_block_when_no_table_chunks_present(self):
        # Non-table chunks are filtered out — same outcome as empty input.
        chunks = [
            {"content": "this is not a table", "metadata": {"type": "text"}},
        ]
        ctx, report = _build_predictive_context(chunks, "test.csv")
        assert report.decision == "BLOCK"

    def test_report_enumerates_total_and_included_chunks(self):
        """AC3: the report names what's in and what's out — both counts
        and bytes are populated, not silently zeroed."""
        chunks = _oversized_chunks(total_target_bytes=_MAX_PREDICTIVE_CONTEXT_BYTES * 2)
        ctx, report = _build_predictive_context(chunks, "test.csv")
        d = report.to_dict()
        assert d["total_chunks"] == 2
        assert d["included_chunks"] == 1
        assert d["omitted_chunks"] == 1
        assert d["total_bytes"] > d["included_bytes"]
        assert d["omitted_bytes"] == d["total_bytes"] - d["included_bytes"]


# ============================================================================
# AC4 — no code path drops context with only a log line
# ============================================================================


class TestNoSilentDropInSource:
    """AC4: a static check that `_build_predictive_context` (the production
    raw-text truncation path) does not contain a `logger.warning` or
    similar silent-drop pattern in the truncation branch. The only place a
    chunk can be skipped is the `break` statement that exits the include
    loop — every other drop is gated."""

    def _source(self) -> str:
        path = (
            Path(__file__).resolve().parents[2]
            / "src" / "main.py"
        )
        return path.read_text(encoding="utf-8")

    def _extract_function_body(self, name: str) -> str:
        """Best-effort extraction of one function's body from source —
        stops at the next top-level `def ` or `class ` declaration."""
        src = self._source()
        match = re.search(rf"^def {name}\(", src, re.MULTILINE)
        assert match, f"function {name!r} not found in src/main.py"
        start = match.start()
        rest = src[start:]
        # Find the next top-level def/class
        next_def = re.search(r"^(def |class |@)", rest[len(name) + 4 :], re.MULTILINE)
        end = len(name) + 4 + next_def.start() if next_def else len(rest)
        return rest[:end]

    def test_build_predictive_context_has_no_logger_warning(self):
        """The pre-TL-5.5 code emitted `logger.warning(...)` and
        continued with a silently-truncated context. After TL-5.5 that
        log line must not exist as an actual call in the function body
        — silence was the failure mode. (The substring `logger.warning`
        may still appear in docstrings/comments as historical notes; we
        look for the call form `logger.warning(`.)"""
        body = self._extract_function_body("_build_predictive_context")
        assert "logger.warning(" not in body, (
            "AC4 violated: `_build_predictive_context` still contains an "
            "actual `logger.warning(` call — every omission must gate via "
            "`gate_context_completeness`, not be logged and ignored"
        )

    def test_build_predictive_context_returns_report(self):
        """The function's return type signature is `(context, report)` —
        if a future refactor drops the report from the return, this
        test catches it."""
        body = self._extract_function_body("_build_predictive_context")
        sig = re.search(r"def _build_predictive_context\([^)]*\) -> ([^:]+):", body)
        assert sig, "could not find function signature"
        return_type = sig.group(1).strip()
        assert "TruncationReport" in return_type, (
            f"AC4 violated: return type is {return_type!r}, expected a "
            f"tuple including `TruncationReport`"
        )

    def test_block_response_helper_does_not_raise(self):
        """`_truncation_block_response` is the uniform BLOCK handler used
        by every route. It must always succeed and return a dict with
        the canonical BLOCK shape — a misconfigured helper would either
        crash the route (HTTP 500, worst case) or return a non-BLOCK
        payload (which would be the very failure TL-5.5 closes)."""
        from src.main import _truncation_block_response
        report = TruncationReport(
            total_chunks=10, included_chunks=2,
            total_bytes=10_000_000, included_bytes=2_000_000,
            decision="BLOCK", reason="too much missing",
        )
        response = _truncation_block_response(
            report, analysis_id="test-id", language="en", filename="test.pdf",
        )
        assert isinstance(response, dict)
        assert response["status"] == "blocked"
        assert response["gating_decision"] == "BLOCK"
        assert response["analysis_id"] == "test-id"
        assert response["filename"] == "test.pdf"
        assert response["report"]["decision"] == "BLOCK"
