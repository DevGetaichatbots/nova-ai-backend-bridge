"""Nova Trust Layer — canonical user-facing trust vocabulary.

This package is the single source of truth for trust-related enums and their
labels/tooltips. The string content itself lives in
`src.version_1_0.localization` so it is co-located with all other Nova
copy and routed through the existing `t()` lookup; this package only owns
the *types* and the accessors.

Danish wording is the initial translation. Final wording requires K&L
sign-off (external dependency EXT-2 in `changes/trust-layer/plan/PROGRESS.md`).
"""

from .vocabulary import (
    ClaimKind,
    EvidenceClass,
    SOURCE_CONFLICT_FLAG,
    TrustState,
    claim_label,
    claim_tooltip,
    conflict_label,
    conflict_tooltip,
    evidence_label,
    evidence_tooltip,
    trust_label,
    trust_tooltip,
)
from .fields import (
    Criticality,
    CRITICAL_FIELD_NAMES,
    SECONDARY_FIELD_NAMES,
    THRESHOLDS,
    criticality,
)
from .matching import (
    MatchLevel,
    MatchResult,
    to_trust_state,
)
from .engine import (
    TrustAssessment,
    TrustEngine,
    verify_id_reference,
)
from .preflight import (
    PreflightReport,
    TruncationReport,
    gate_context_completeness,
    run_preflight_check,
)
from .predictive_facts import (
    CRITICAL_NOW,
    IMPORTANT_NEXT,
    MONITOR,
    PLANDISC_A,
    PLANDISC_B,
    PLANDISC_C,
    STANDARD,
    DelayedActivity,
    PredictiveActivity,
    compute_predictive_facts,
    detect_delayed_activities,
)
from .context import (
    ClusterFact,
    build_predictive_context,
)
from .response_contract import (
    AgentResponse,
    GateDecision,
    GatePolicy,
    NoAnswerInfo,
    ValidatedResponse,
    build_no_answer_response,
    detect_no_answer,
    is_causal_question,
    merge_inferences,
    render_validated_response,
    validate_agent_response,
)
from .claims import (
    Claim,
    ClaimExtractionResult,
    ClaimForm,
    NarrativeVerificationResult,
    VerificationOutcome,
    VerifiedClaim,
    extract_claims,
    verify_claim,
    verify_claims,
    verify_narrative,
)

__all__ = [
    # vocabulary (TL-0.4)
    "TrustState",
    "ClaimKind",
    "EvidenceClass",
    "SOURCE_CONFLICT_FLAG",
    "trust_label",
    "trust_tooltip",
    "claim_label",
    "claim_tooltip",
    "evidence_label",
    "evidence_tooltip",
    "conflict_label",
    "conflict_tooltip",
    # fields (TL-1.7)
    "Criticality",
    "CRITICAL_FIELD_NAMES",
    "SECONDARY_FIELD_NAMES",
    "THRESHOLDS",
    "criticality",
    # matching (TL-3.1)
    "MatchLevel",
    "MatchResult",
    "to_trust_state",
    # engine (TL-4.1)
    "TrustAssessment",
    "TrustEngine",
    # engine (TL-6.3)
    "verify_id_reference",
    # preflight (TL-4.6)
    "PreflightReport",
    "run_preflight_check",
    # context-truncation gating (TL-5.5)
    "TruncationReport",
    "gate_context_completeness",
    # predictive_facts (TL-5.1)
    "DelayedActivity",
    "detect_delayed_activities",
    "STANDARD",
    "PLANDISC_A",
    "PLANDISC_B",
    "PLANDISC_C",
    # predictive_facts (TL-5.2)
    "PredictiveActivity",
    "compute_predictive_facts",
    "CRITICAL_NOW",
    "IMPORTANT_NEXT",
    "MONITOR",
    # context (TL-5.3)
    "ClusterFact",
    "build_predictive_context",
    # response_contract (TL-6.1, TL-6.5)
    "AgentResponse",
    "NoAnswerInfo",
    "ValidatedResponse",
    "GatePolicy",
    "GateDecision",
    "validate_agent_response",
    "render_validated_response",
    "build_no_answer_response",
    "detect_no_answer",
    "is_causal_question",
    # claims (TL-6.2)
    "Claim",
    "ClaimForm",
    "ClaimExtractionResult",
    "extract_claims",
    # claims (TL-6.3)
    "VerificationOutcome",
    "VerifiedClaim",
    "NarrativeVerificationResult",
    "verify_claim",
    "verify_claims",
    "verify_narrative",
    # claims (TL-6.6 — language guardrails)
    "check_overclaiming",
    "hedge_overclaiming",
    "hedge_narrative_overclaiming",
    # audit (TL-9.2)
    "AuditStage",
    "AuditChainEntry",
    "AnalysisAuditTrail",
    "AuditStore",
    "audit_store",
    # versioning (TL-9.3)
    "AnalysisVersions",
    "ALL_VERSION_DIMENSIONS",
    "DEFAULT_PARSER_VERSION",
    "DEFAULT_MATCHING_ALGORITHM_VERSION",
    "DEFAULT_ANALYSIS_ENGINE_VERSION",
    "DEFAULT_PROMPT_VERSION",
    "DEFAULT_MODEL_VERSION",
    "DEFAULT_SCHEDULE_REVISION",
    "DEFAULT_MANUAL_CORRECTIONS",
    # metrics (TL-9.4)
    "ALL_TEN_BRIEF_38_METRICS",
    "TrustMetric",
    "TrustMetricsSnapshot",
    "TrustMetricsStore",
    "metrics_store",
    "build_trust_metric",
    "compute_live_metrics",
    "reconcile_with_harness",
    # trust center (TL-9.5)
    "TrustCenterOverview",
    "TrustCenterDataVerification",
    "TrustCenterActivityMatching",
    "TrustCenterReviewSummary",
    "VerificationCategoryBreakdown",
    "build_trust_center_overview",
    "generate_verification_report",
]

from .audit import (
    AuditStage,
    AuditChainEntry,
    AnalysisAuditTrail,
    AuditStore,
    audit_store,
)
from .versioning import (
    AnalysisVersions,
    ALL_VERSION_DIMENSIONS,
    DEFAULT_PARSER_VERSION,
    DEFAULT_MATCHING_ALGORITHM_VERSION,
    DEFAULT_ANALYSIS_ENGINE_VERSION,
    DEFAULT_PROMPT_VERSION,
    DEFAULT_MODEL_VERSION,
    DEFAULT_SCHEDULE_REVISION,
    DEFAULT_MANUAL_CORRECTIONS,
)
from .metrics import (
    ALL_TEN_BRIEF_38_METRICS,
    TrustMetric,
    TrustMetricsSnapshot,
    TrustMetricsStore,
    metrics_store,
    build_trust_metric,
    compute_live_metrics,
    reconcile_with_harness,
)
from .trust_center import (
    TrustCenterOverview,
    TrustCenterDataVerification,
    TrustCenterActivityMatching,
    TrustCenterReviewSummary,
    VerificationCategoryBreakdown,
    build_trust_center_overview,
    generate_verification_report,
)

