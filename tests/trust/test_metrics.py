"""Tests for Brief §38 trust metrics KPIs and continuous monitoring (TL-9.4).

Brief §38:
    Internal Nova quality KPIs tracking ten distinct dimensions:
    1. critical_field_verification_rate
    2. activity_match_precision
    3. unmatched_activity_rate
    4. manual_review_rate
    5. ocr_review_rate
    6. false_match_rate (Prominent KPI, Brief §37)
    7. conflict_detection_rate
    8. agent_unsupported_claim_rate (Prominent KPI, Brief §39)
    9. human_correction_rate
    10. regression_failure_rate

Acceptance criteria:
- [x] All ten metrics implemented
- [x] Computed on real usage and persisted over time
- [x] Trends queryable
- [x] Metrics reconcile with the harness's fixture-time values
"""
import pytest
from datetime import datetime, timezone, timedelta

from src.trust.metrics import (
    ALL_TEN_BRIEF_38_METRICS,
    METRIC_ACTIVITY_MATCH_PRECISION,
    METRIC_AGENT_UNSUPPORTED_CLAIM_RATE,
    METRIC_CONFLICT_DETECTION_RATE,
    METRIC_CRITICAL_FIELD_VERIFICATION,
    METRIC_FALSE_MATCH_RATE,
    METRIC_HUMAN_CORRECTION_RATE,
    METRIC_MANUAL_REVIEW_RATE,
    METRIC_OCR_REVIEW_RATE,
    METRIC_REGRESSION_FAILURE_RATE,
    METRIC_UNMATCHED_ACTIVITY_RATE,
    TrustMetric,
    TrustMetricsSnapshot,
    TrustMetricsStore,
    build_trust_metric,
    compute_live_metrics,
    metrics_store,
    reconcile_with_harness,
)
from src.trust.claims import UnsupportedClaimMetric
from tests.trust.harness import Fixture, MatchMetrics, compute_fixture_metrics


def test_all_ten_brief_38_metrics_implemented():
    """AC1: All ten metrics named in Brief §38 are implemented with defined denominators."""
    expected_metrics = {
        "critical_field_verification_rate",
        "activity_match_precision",
        "unmatched_activity_rate",
        "manual_review_rate",
        "ocr_review_rate",
        "false_match_rate",
        "conflict_detection_rate",
        "agent_unsupported_claim_rate",
        "human_correction_rate",
        "regression_failure_rate",
    }
    assert set(ALL_TEN_BRIEF_38_METRICS) == expected_metrics
    assert len(ALL_TEN_BRIEF_38_METRICS) == 10

    snap = compute_live_metrics(analysis_id="test_run")
    all_metrics = snap.all_metrics()
    assert len(all_metrics) == 10
    for name in ALL_TEN_BRIEF_38_METRICS:
        m = all_metrics[name]
        assert isinstance(m, TrustMetric)
        assert m.name == name
        assert m.denominator >= 0
        assert "/" in m.display_string  # Brief §23: defined denominator


def test_prominent_metrics_flagged():
    """AC1 / Brief §37, §39: false match rate and unsupported claim rate have prominence."""
    snap = compute_live_metrics(analysis_id="test_run")
    prominent = snap.prominent_metrics()

    assert METRIC_FALSE_MATCH_RATE in prominent
    assert METRIC_AGENT_UNSUPPORTED_CLAIM_RATE in prominent
    assert prominent[METRIC_FALSE_MATCH_RATE].prominent is True
    assert prominent[METRIC_AGENT_UNSUPPORTED_CLAIM_RATE].prominent is True

    # Strict zero target
    assert prominent[METRIC_FALSE_MATCH_RATE].target == 0.0
    assert prominent[METRIC_AGENT_UNSUPPORTED_CLAIM_RATE].target == 0.0


def test_computed_on_real_usage_and_persisted():
    """AC2: Computed on real comparison/review data and persisted over time."""
    store = TrustMetricsStore()

    real_comp_data = {
        "executive_summary": {
            "selected_activities": 50,
            "confirmed_activities_count": 42,
            "requires_verification_count": 5,
        },
        "critical_fields_verified_count": 190,
        "critical_fields_total_count": 200,
        "false_matches_count": 0,
        "unsupported_claims_count": 0,
        "total_claims_count": 12,
    }
    real_review_queue = [{"item_id": f"item_{i}"} for i in range(5)]

    snap = compute_live_metrics(
        analysis_id="live_analysis_101",
        comparison_data=real_comp_data,
        review_queue=real_review_queue,
        project_id="proj_alpha",
        company_id="comp_beta",
    )
    store.record(snap)

    latest = store.get_latest(project_id="proj_alpha")
    assert latest is not None
    assert latest.analysis_id == "live_analysis_101"
    assert latest.activity_match_precision.value == 1.0
    assert latest.manual_review_rate.numerator == 5
    assert latest.manual_review_rate.denominator == 50
    assert latest.manual_review_rate.percentage == 10.0


def test_trends_queryable_over_time():
    """AC3: Continuous metrics are queryable as time-series trends (Brief §49)."""
    store = TrustMetricsStore()

    # Simulate 3 runs across consecutive timestamps
    now = datetime.now(timezone.utc)
    for i, fmr_count in enumerate([2, 1, 0]):
        ts = (now + timedelta(hours=i)).isoformat()
        comp_data = {
            "executive_summary": {"selected_activities": 20, "confirmed_activities_count": 18},
            "false_matches_count": fmr_count,
        }
        snap = compute_live_metrics(
            analysis_id=f"analysis_{i}",
            comparison_data=comp_data,
            project_id="proj_trend",
        )
        snap.timestamp = ts
        store.record(snap)

    trend = store.get_metric_trend(METRIC_FALSE_MATCH_RATE, project_id="proj_trend")
    assert len(trend) == 3
    assert trend[0]["numerator"] == 2
    assert trend[1]["numerator"] == 1
    assert trend[2]["numerator"] == 0
    assert trend[2]["meets_target"] is True


def test_metrics_reconcile_with_harness_values():
    """AC4: Metrics reconcile exactly with the harness's fixture-time calculations."""
    fixture = Fixture(
        id="fx_reconciliation",
        dir=None,  # type: ignore
        kind="pair",
        reference_date="Unknown",
        ground_truth={"expected": {"false_matches": 1}},
    )
    snapshot = {
        "health": {
            "comparison": {
                "executive_summary": {
                    "selected_activities": 20,
                    "confirmed_matches_count": 15,
                    "requires_verification_count": 2,
                }
            }
        }
    }
    harness_m = compute_fixture_metrics(fixture, snapshot)
    unsupported_m = UnsupportedClaimMetric(
        verified_count=9,
        contradicted_count=1,
        unverifiable_count=0,
        total_claims=10,
    )

    reconciled = reconcile_with_harness(
        fixture_metrics=harness_m,
        total_activities=20,
        unsupported_metric=unsupported_m,
        fixture_id="fx_reconciliation",
    )

    # Must reconcile exactly with fixture metrics values
    assert reconciled.activity_match_precision.value == harness_m.match_precision
    assert reconciled.false_match_rate.value == harness_m.false_match_rate
    assert reconciled.unmatched_activity_rate.value == harness_m.unmatched_rate
    assert reconciled.manual_review_rate.value == harness_m.requires_verification_rate
    assert reconciled.agent_unsupported_claim_rate.value == unsupported_m.unsupported_rate
    assert reconciled.agent_unsupported_claim_rate.meets_target is False


def test_no_blended_health_score():
    """Do-not rule: Do NOT blend these into one single health score."""
    snap = compute_live_metrics(analysis_id="no_blended")
    summary = snap.to_summary_dict()

    assert "overall_health_score" not in summary
    assert "blended_score" not in summary
    assert "metrics" in summary
    assert len(summary["metrics"]) == 10


def test_tenant_scoping_isolation():
    """Metrics store preserves tenant isolation across queries."""
    store = TrustMetricsStore()
    snap_a = compute_live_metrics(analysis_id="a", project_id="proj_1", company_id="comp_1")
    snap_b = compute_live_metrics(analysis_id="b", project_id="proj_2", company_id="comp_2")

    store.record(snap_a)
    store.record(snap_b)

    history_1 = store.get_history(company_id="comp_1")
    assert len(history_1) == 1
    assert history_1[0].analysis_id == "a"

    history_2 = store.get_history(company_id="comp_2")
    assert len(history_2) == 1
    assert history_2[0].analysis_id == "b"
