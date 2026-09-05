"""Pre-flight source quality check & gating
==========================================
TL-4.6 (brief §28, §29)

Performs a pre-flight quality check on normalized schedule data before invoking
expensive analysis or LLM steps, producing a report and a gating outcome:
PASS, PARTIAL, or BLOCK.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ingestion.models.nusf import NormalizedSchedule

logger = logging.getLogger(__name__)


@dataclass
class PreflightReport:
    """Pre-flight quality check report shape (brief §28)."""

    activities_detected: int
    confidently_parsed: int
    requiring_review: int
    unresolved: int
    decision: str  # "PASS" | "PARTIAL" | "BLOCK"
    excluded_activities: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activities_detected": self.activities_detected,
            "confidently_parsed": self.confidently_parsed,
            "requiring_review": self.requiring_review,
            "unresolved": self.unresolved,
            "decision": self.decision,
            "excluded_activities": self.excluded_activities,
            "reason": self.reason,
        }

    def to_refusal_response(self, language: str = "en") -> Dict[str, Any]:
        """Structured refusal outcome for BLOCK decision (brief §29).

        TL-7.8 (brief §42): `success: False` alongside the existing
        `status: "blocked"` — the frontends' upload handlers already
        branch on `data.success`, so a BLOCK response must be
        distinguishable from a success response on the same field a
        caller is already checking, not only on a second field a caller
        might not check. `notice` carries the brief §42 four-part
        reassuring shape (never rendered as a bare error banner).
        """
        from src.trust.response_contract import build_uncertainty_notice

        return {
            "status": "blocked",
            "success": False,
            "gating_decision": "BLOCK",
            "message": "Nova has paused analysis to avoid producing unreliable results",
            "notice": build_uncertainty_notice("preflight_block", language),
            "report": self.to_dict(),
        }


def run_preflight_check(schedule: NormalizedSchedule) -> PreflightReport:
    """Evaluate pre-flight source quality check (TL-4.6)."""
    total = len(schedule.activities)
    if total == 0:
        return PreflightReport(
            activities_detected=0,
            confidently_parsed=0,
            requiring_review=0,
            unresolved=0,
            decision="BLOCK",
            reason="Schedule contains 0 activities",
        )

    issues = schedule.validation_issues or []
    issue_activity_ids = {iss.activity_id for iss in issues if iss.activity_id}

    unresolved_ids = []
    review_ids = []

    for act in schedule.activities:
        # If activity has logic warning or validation issues
        if act.has_logic_warning or act.internal_id in issue_activity_ids:
            review_ids.append(act.internal_id)
        # Unresolvable ID
        if act.internal_id.startswith("__unknown_"):
            unresolved_ids.append(act.internal_id)

    unresolved_count = len(set(unresolved_ids))
    review_count = len(set(review_ids))
    confident_count = max(0, total - review_count - unresolved_count)

    unresolved_ratio = unresolved_count / max(1, total)

    # BLOCK gating rule: > 40% unresolvable or validation failed with critical errors
    if unresolved_ratio > 0.4 or not schedule.validation_passed:
        decision = "BLOCK"
        reason = f"Unresolved ratio {unresolved_ratio:.1%} > 40% or critical validation failed"
    elif review_count > 0 or unresolved_count > 0:
        decision = "PARTIAL"
        reason = f"{review_count} activities require review, {unresolved_count} unresolved"
    else:
        decision = "PASS"
        reason = "Pre-flight checks passed completely"

    return PreflightReport(
        activities_detected=total,
        confidently_parsed=confident_count,
        requiring_review=review_count,
        unresolved=unresolved_count,
        decision=decision,
        excluded_activities=list(set(unresolved_ids)),
        reason=reason,
    )


# ============================================================================
# TL-5.5 — Context-truncation gating (brief §17, §28)
# ============================================================================
# `src/main.py`'s `_build_predictive_context` caps the raw-text context sent
# to the model at a byte budget and, before this task, dropped whatever did
# not fit with only a `logger.warning` — a confident report over a silently
# partial schedule, exactly the failure mode this whole programme exists to
# prevent. `gate_context_completeness` turns "some chunks did not fit" into
# the same PASS/PARTIAL/BLOCK vocabulary `run_preflight_check` already
# established, so the truncation event is a gating decision the caller must
# act on, not a log line the caller can ignore.


@dataclass
class TruncationReport:
    """Context-completeness gating report (brief §17, §28) — the TL-5.5
    counterpart to `PreflightReport`. `decision` follows the same
    PASS/PARTIAL/BLOCK vocabulary as TL-4.6's pre-flight check."""

    total_chunks: int
    included_chunks: int
    total_bytes: int
    included_bytes: int
    decision: str  # "PASS" | "PARTIAL" | "BLOCK"
    reason: str

    @property
    def omitted_chunks(self) -> int:
        return self.total_chunks - self.included_chunks

    @property
    def omitted_bytes(self) -> int:
        return self.total_bytes - self.included_bytes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_chunks": self.total_chunks,
            "included_chunks": self.included_chunks,
            "omitted_chunks": self.omitted_chunks,
            "total_bytes": self.total_bytes,
            "included_bytes": self.included_bytes,
            "omitted_bytes": self.omitted_bytes,
            "decision": self.decision,
            "reason": self.reason,
        }

    def to_refusal_response(self, language: str = "en") -> Dict[str, Any]:
        """Structured refusal outcome for BLOCK decision — same shape as
        `PreflightReport.to_refusal_response()` so callers do not need two
        different refusal contracts.

        TL-7.8 (brief §42): `success: False` + `notice` — see
        `PreflightReport.to_refusal_response`'s docstring for why.
        """
        from src.trust.response_contract import build_uncertainty_notice

        return {
            "status": "blocked",
            "success": False,
            "gating_decision": "BLOCK",
            "message": "Nova has paused analysis to avoid producing a result over data it could not fully include",
            "notice": build_uncertainty_notice("context_truncation_block", language),
            "report": self.to_dict(),
        }


# BLOCK gating rule: named, documented, UNCALIBRATED (brief §7 — same posture
# as every other threshold in this plan; no EXT-1-equivalent dataset exists
# for "how much of a schedule can be omitted before a report is meaningless"
# either). Omitting the *majority* of the schedule's table data makes any
# analysis over what remains unrepresentative of the whole project — BLOCK
# rather than let a report speak confidently about a project it saw half of.
_TRUNCATION_BLOCK_OMITTED_RATIO_UNCALIBRATED = 0.5


def gate_context_completeness(
    total_chunks: int, included_chunks: int, total_bytes: int, included_bytes: int
) -> TruncationReport:
    """TL-5.5: decide PASS / PARTIAL / BLOCK for how much of the schedule's
    table data made it into the context actually sent to the model.

    `total_chunks == 0` (no table data extracted at all) is BLOCK, not PASS
    — there is nothing to analyze, which is a stronger failure than partial
    coverage, not the absence of one.
    """
    if total_chunks == 0:
        return TruncationReport(
            total_chunks=0, included_chunks=0, total_bytes=total_bytes, included_bytes=0,
            decision="BLOCK", reason="No schedule table data could be extracted",
        )

    omitted_chunks = total_chunks - included_chunks
    omitted_ratio = omitted_chunks / total_chunks

    if omitted_ratio > _TRUNCATION_BLOCK_OMITTED_RATIO_UNCALIBRATED:
        decision = "BLOCK"
        reason = (
            f"{omitted_chunks}/{total_chunks} data chunks ({omitted_ratio:.1%}) exceeded the context "
            f"size limit and were omitted — too much of the schedule is missing for a reliable analysis"
        )
    elif omitted_chunks > 0:
        decision = "PARTIAL"
        reason = (
            f"{omitted_chunks}/{total_chunks} data chunks ({omitted_ratio:.1%}, "
            f"{total_bytes - included_bytes} bytes) exceeded the context size limit and were omitted"
        )
    else:
        decision = "PASS"
        reason = "All extracted schedule data was included in the context"

    return TruncationReport(
        total_chunks=total_chunks,
        included_chunks=included_chunks,
        total_bytes=total_bytes,
        included_bytes=included_bytes,
        decision=decision,
        reason=reason,
    )
