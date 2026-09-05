"""Centralized Trust Engine
========================
TL-4.1 / TL-4.2 / TL-4.3 / TL-4.4 (brief §3, §5, §7, §8, §14, §30)

Centralized service that evaluates upstream evidence (OCR confidence, parser status,
AI inference, field criticality, validation issues) to derive a `TrustAssessment`
and propagate uncertainty downstream using a weakest-link rule.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

from src.trust.fields import Criticality, THRESHOLDS, criticality
from src.trust.matching import MatchLevel, to_trust_state
from src.trust.vocabulary import TrustState

logger = logging.getLogger(__name__)


# Priority rank for ordering TrustState values in weakest-link evaluation
_TRUST_STATE_RANK: dict[TrustState, int] = {
    TrustState.UNVERIFIED: 0,
    TrustState.REVIEW: 1,
    TrustState.VERIFIED: 2,
}


@dataclass(frozen=True)
class TrustAssessment:
    """The outcome of a trust assessment for a single value, activity, or feature."""

    state: TrustState
    reason: str
    weakest_link: str
    evidence_chain: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_verified(self) -> bool:
        return self.state == TrustState.VERIFIED


class TrustEngine:
    """Centralized Trust Engine (brief §3).

    Evaluates upstream evidence, enforces weakest-link propagation, and computes
    feature-specific confidences.
    """

    def __init__(self, activity_trust_map: Optional[dict[str, dict[str, TrustAssessment]]] = None) -> None:
        # activity_id -> {field_name -> TrustAssessment}
        self._activity_trust_map: dict[str, dict[str, TrustAssessment]] = activity_trust_map or {}

    def register_activity_assessment(
        self, activity_id: str, field_name: str, assessment: TrustAssessment
    ) -> None:
        if activity_id not in self._activity_trust_map:
            self._activity_trust_map[activity_id] = {}
        self._activity_trust_map[activity_id][field_name] = assessment

    def assess_value(
        self,
        field_name: str,
        value: Any,
        provenance: Optional[Any] = None,
        validation_issues: Optional[Sequence[Any]] = None,
        is_ai_inferred: bool = False,
        extraction_method: str = "",
    ) -> TrustAssessment:
        """Derive per-value trust state from upstream evidence (TL-4.2)."""
        evidence_chain: list[dict[str, Any]] = []
        field_crit = criticality(field_name) if field_name in ("source_id", "name", "planned_start", "planned_finish", "duration_hours", "percent_complete", "location_path", "area", "floor", "phase", "discipline", "activity_type", "wbs_code", "actual_start", "actual_finish", "is_late", "inspected_status", "critical_flag", "total_float", "remarks") else Criticality.SECONDARY

        # Rule 1: AI-inferred fields are never VERIFIED (brief §6)
        if is_ai_inferred:
            evidence_chain.append({"type": "ai_inference", "is_inferred": True})
            return TrustAssessment(
                state=TrustState.REVIEW,
                reason=f"Field '{field_name}' was AI-inferred, capping state at REVIEW",
                weakest_link=field_name,
                evidence_chain=evidence_chain,
            )

        # Rule 2: Validation issues check
        issues = validation_issues or []
        relevant_issues = [
            iss for iss in issues
            if getattr(iss, "field_name", None) == field_name
            or field_name in str(getattr(iss, "message", ""))
            or ("date" in str(getattr(iss, "message", "")).lower() and ("start" in field_name or "finish" in field_name))
            or ("progress" in str(getattr(iss, "message", "")).lower() and "percent" in field_name)
        ]
        if relevant_issues:
            issue_msgs = [str(getattr(i, "message", i)) for i in relevant_issues]
            evidence_chain.append({"type": "validation_issues", "issues": issue_msgs})
            return TrustAssessment(
                state=TrustState.REVIEW,
                reason=f"Field '{field_name}' has validation issues: {'; '.join(issue_msgs)}",
                weakest_link=field_name,
                evidence_chain=evidence_chain,
            )

        # Rule 3: OCR confidence check
        ocr_conf: Optional[float] = None
        method = extraction_method.lower() if extraction_method else ""

        if provenance:
            if isinstance(provenance, dict):
                ocr_conf = provenance.get("confidence") or provenance.get("ocr_confidence")
                method = method or str(provenance.get("method") or provenance.get("extraction_method") or "").lower()
            else:
                # Real `Provenance` objects (post-TL-1.6) expose value-level
                # confidence as `ocr_confidence`, not `confidence` —
                # `column_mapping_confidence` is a different signal (column
                # recognition, not value correctness; see ADR-002's trap and
                # ADR-017). Read `ocr_confidence` first; fall back to
                # `confidence` only for legacy/mock objects that still use
                # that attribute name (e.g. simple namespaces in older
                # tests). `getattr(..., default)` never raises, so no
                # `hasattr` guard is needed for arbitrary objects here.
                ocr_conf = getattr(provenance, "ocr_confidence", None)
                if ocr_conf is None:
                    ocr_conf = getattr(provenance, "confidence", None)
                method = method or str(getattr(provenance, "extraction_method", "")).lower()

        if ocr_conf is not None:
            evidence_chain.append({"type": "ocr_confidence", "confidence": ocr_conf, "method": method})
            green = THRESHOLDS.critical_ocr_green if field_crit == Criticality.CRITICAL else THRESHOLDS.secondary_ocr_green
            amber_min = THRESHOLDS.critical_ocr_amber_min if field_crit == Criticality.CRITICAL else THRESHOLDS.secondary_ocr_amber_min

            if ocr_conf >= green:
                state = TrustState.VERIFIED
                reason = f"OCR confidence {ocr_conf:.2f} >= green threshold {green:.2f}"
            elif ocr_conf >= amber_min:
                state = TrustState.REVIEW
                reason = f"OCR confidence {ocr_conf:.2f} in amber range [{amber_min:.2f}, {green:.2f})"
            else:
                state = TrustState.UNVERIFIED
                reason = f"OCR confidence {ocr_conf:.2f} below minimum threshold {amber_min:.2f}"

            return TrustAssessment(
                state=state,
                reason=reason,
                weakest_link=field_name,
                evidence_chain=evidence_chain,
            )

        # Exact-read sources (CSV, MPP, MSPDI, Excel) have no OCR confidence but are
        # exact. Includes both the bare aliases pre-dating TL-1.9 and the canonical
        # per-format `extraction_method` values TL-1.9 actually emits
        # (`csv_cell`/`excel_cell`/`mpp_field`/`mspdi_field` — see
        # `ingestion/extractors/{csv,excel,mpp,mspdi}.py` and the vocabulary
        # documented on `Provenance.extraction_method` in
        # `ingestion/models/nusf.py`). OCR methods (`ocr_table`, `ocr_text_layer`)
        # are deliberately excluded — an `ocr_text_layer` cell with no OCR
        # confidence is "unrated" (brief §45), never silently exact.
        if method in (
            "csv", "mpp", "mspdi", "native", "direct_parse",
            "csv_cell", "excel_cell", "mpp_field", "mspdi_field",
        ) or not method:
            evidence_chain.append({"type": "exact_read", "method": method or "exact"})
            return TrustAssessment(
                state=TrustState.VERIFIED,
                reason=f"Exact-read source value for '{field_name}'",
                weakest_link=field_name,
                evidence_chain=evidence_chain,
            )

        # Unresolvable span / missing evidence
        evidence_chain.append({"type": "missing_evidence", "method": method})
        return TrustAssessment(
            state=TrustState.UNVERIFIED,
            reason=f"No OCR confidence or exact-read provenance for '{field_name}'",
            weakest_link=field_name,
            evidence_chain=evidence_chain,
        )

    def propagate(self, assessments: Sequence[TrustAssessment]) -> TrustAssessment:
        """Weakest-link propagation across materially relevant dependencies (TL-4.3 / brief §14).

        Given multiple assessments, the resulting state is capped by the minimum state
        among all inputs.
        """
        if not assessments:
            return TrustAssessment(
                state=TrustState.UNVERIFIED,
                reason="No dependency assessments provided",
                weakest_link="none",
                evidence_chain=[],
            )

        sorted_assessments = sorted(
            assessments, key=lambda a: (_TRUST_STATE_RANK.get(a.state, 0), a.weakest_link)
        )
        weakest = sorted_assessments[0]

        combined_chain = []
        for a in assessments:
            combined_chain.extend(a.evidence_chain)

        return TrustAssessment(
            state=weakest.state,
            reason=f"Propagated weakest link '{weakest.weakest_link}': {weakest.reason}",
            weakest_link=weakest.weakest_link,
            evidence_chain=combined_chain,
        )

    def assess_feature(
        self, feature_name: str, assessments: Sequence[TrustAssessment], is_inferred: bool = False
    ) -> TrustAssessment:
        """Compute feature-specific confidence (TL-4.4 / brief §30)."""
        if not assessments:
            return TrustAssessment(
                state=TrustState.UNVERIFIED,
                reason=f"Feature '{feature_name}' has no available input data (UNAVAILABLE)",
                weakest_link=feature_name,
                evidence_chain=[],
            )

        base_assessment = self.propagate(assessments)

        # Inferred critical path or forecast features are capped below VERIFIED
        if is_inferred or feature_name in ("Critical Path", "Forecast"):
            if is_inferred and base_assessment.state == TrustState.VERIFIED:
                return TrustAssessment(
                    state=TrustState.REVIEW,
                    reason=f"Feature '{feature_name}' is inferred, capping state at REVIEW",
                    weakest_link=base_assessment.weakest_link,
                    evidence_chain=base_assessment.evidence_chain,
                )

        return base_assessment

    # --- Verifier Protocol Compliance (diffs.py integration) ---

    def verify_field(self, activity_id: str, field: str) -> bool:
        """Return True iff field assessment is VERIFIED."""
        activity_map = self._activity_trust_map.get(activity_id, {})
        assessment = activity_map.get(field)
        if assessment is None:
            return False
        return assessment.state == TrustState.VERIFIED

    def verify_activity(self, activity_id: str) -> bool:
        """Return True iff all field assessments for activity are VERIFIED."""
        activity_map = self._activity_trust_map.get(activity_id, {})
        if not activity_map:
            return False
        propagated = self.propagate(list(activity_map.values()))
        return propagated.state == TrustState.VERIFIED


def verify_id_reference(candidate_id: Any, known_ids: Sequence[Any]) -> bool:
    """TL-6.3 (brief §16): does `candidate_id` — an activity id a generated
    narrative claims to reference — actually exist?

    This reuses `TL-2.3`'s architectural guarantee rather than re-deriving
    it: every id in `known_ids` (when `known_ids` is drawn from
    `response_facts`/`delayed_activities`, as `src/trust/claims.py`'s
    verification does) is, by construction, a real `source_id` that
    survived Phase 2's invention-fallback deletion — never a synthesized
    row index or composite key. Verifying an id reference is therefore
    exact membership, nothing more: no fuzzy matching, no partial-string
    matching, no "close enough." A narrative that names an id one
    character off from a real one is not "almost verified" — brief §16's
    whole point is that a claim either traces to real evidence or it does
    not.

    A standalone function, not a `TrustEngine` method: existence-checking
    against an explicit candidate set needs no per-activity trust state,
    no evidence chain, and no engine instance — `TrustEngine`'s existing
    surface (`assess_value`, `propagate`, `verify_activity`) is about
    *how well a value was extracted*, not *does this reference exist at
    all*. Keeping this as a plain function avoids overloading the class
    with an unrelated concern.
    """
    return candidate_id in set(known_ids)
