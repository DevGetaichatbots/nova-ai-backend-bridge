"""Tests for Brief §43 Trust Center and Verification Report (TL-9.5).

Verifies:
1. Complete Brief §43 field set rendered (data verification, activity matching,
   items requiring review, unresolved items, last validation date, analysis engine version).
2. Defined denominators on all percentage figures (Brief §23).
3. "View verification report" exportable in markdown and json formats.
4. Tenant isolation (Brief §43 Do-not rule: no cross-tenant leaking in Nova).
5. Brand & locale parity (Danish for Kemp, English/Danish for Nova).
6. Integration with FastAPI endpoints (/trust-center/summary and /trust-center/report).
"""
import json
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.trust.metrics import (
    ALL_TEN_BRIEF_38_METRICS,
    TrustMetric,
    TrustMetricsSnapshot,
    TrustMetricsStore,
    build_trust_metric,
    metrics_store,
)
from src.trust.trust_center import (
    TrustCenterOverview,
    build_trust_center_overview,
    format_rate_with_denominator,
    generate_verification_report,
)
from src.trust.versioning import DEFAULT_ANALYSIS_ENGINE_VERSION, AnalysisVersions


@pytest.fixture
def client():
    return TestClient(app)


def _make_dummy_snapshot(
    company_id="comp-1",
    verified_fields=95,
    total_fields=100,
    matched_activities=48,
    total_activities=50,
    false_matches=0,
):
    return TrustMetricsSnapshot(
        company_id=company_id,
        critical_field_verification_rate=build_trust_metric(
            "critical_field_verification_rate",
            "Critical Field Verification",
            numerator=verified_fields,
            denominator=total_fields,
            target=0.95,
        ),
        activity_match_precision=build_trust_metric(
            "activity_match_precision",
            "Activity Match Precision",
            numerator=matched_activities,
            denominator=total_activities,
            target=0.95,
        ),
        unmatched_activity_rate=build_trust_metric(
            "unmatched_activity_rate",
            "Unmatched Activity Rate",
            numerator=total_activities - matched_activities,
            denominator=total_activities,
            target=0.05,
        ),
        manual_review_rate=build_trust_metric(
            "manual_review_rate",
            "Manual Review Rate",
            numerator=5,
            denominator=total_activities,
        ),
        ocr_review_rate=build_trust_metric(
            "ocr_review_rate",
            "OCR Review Rate",
            numerator=2,
            denominator=total_fields,
        ),
        false_match_rate=build_trust_metric(
            "false_match_rate",
            "False Match Rate",
            numerator=false_matches,
            denominator=matched_activities,
            target=0.0,
            prominent=True,
        ),
        conflict_detection_rate=build_trust_metric(
            "conflict_detection_rate",
            "Conflict Detection Rate",
            numerator=1,
            denominator=total_activities,
        ),
        agent_unsupported_claim_rate=build_trust_metric(
            "agent_unsupported_claim_rate",
            "Agent Unsupported Claim Rate",
            numerator=0,
            denominator=10,
            target=0.0,
            prominent=True,
        ),
        human_correction_rate=build_trust_metric(
            "human_correction_rate",
            "Human Correction Rate",
            numerator=0,
            denominator=total_activities,
        ),
        regression_failure_rate=build_trust_metric(
            "regression_failure_rate",
            "Regression Failure Rate",
            numerator=0,
            denominator=10,
            target=0.0,
        ),
    )


class TestTrustCenterFields:
    """Brief §43 field set tests."""

    def test_complete_brief_43_field_set(self):
        snap = _make_dummy_snapshot()
        overview = build_trust_center_overview(
            company_id="comp-1",
            snapshots=[snap],
            review_items=[
                {"item_id": "rev-1", "category": "uncertain_match"},
                {"item_id": "rev-2", "category": "low_confidence_id"},
            ],
            resolutions=[{"item_id": "rev-1"}],
        )

        # 1. Data verification
        assert overview.data_verification.verified_count == 95
        assert overview.data_verification.total_count == 100
        assert overview.data_verification.verification_rate == 0.95
        assert "95/100 (95.00%)" in overview.data_verification.display_string

        # 2. Activity matching
        assert overview.activity_matching.matched_count == 48
        assert overview.activity_matching.total_count == 50
        assert overview.activity_matching.match_precision == 0.96
        assert "48/50 (96.00%)" in overview.activity_matching.display_string
        assert overview.activity_matching.false_match_rate == 0.0

        # 3. Items requiring review
        assert overview.items_requiring_review == 2
        assert overview.review_summary.breakdown.uncertain_match == 1
        assert overview.review_summary.breakdown.low_confidence_id == 1

        # 4. Unresolved items
        assert overview.unresolved_items == 1
        assert overview.review_summary.resolved_items == 1

        # 5. Last validation date
        assert overview.last_validation_date is not None

        # 6. Analysis engine version
        assert overview.analysis_engine_version == DEFAULT_ANALYSIS_ENGINE_VERSION
        assert "analysis_engine" in overview.versions

    def test_defined_denominators_brief_23(self):
        """Every percentage must have a stated denominator (Brief §23)."""
        rate, display = format_rate_with_denominator(15, 20)
        assert rate == 0.75
        assert display == "15/20 (75.00%)"

        # Edge case: zero denominator
        zero_rate, zero_display = format_rate_with_denominator(0, 0)
        assert zero_rate == 0.0
        assert zero_display == "0/0 (0.00%)"

        snap = _make_dummy_snapshot(verified_fields=120, total_fields=128)
        overview = build_trust_center_overview(company_id="comp-1", snapshots=[snap])
        assert overview.data_verification.display_string == "120/128 (93.75%)"
        assert overview.activity_matching.display_string == "48/50 (96.00%)"


class TestTenantIsolation:
    """Brief §43 Do-not rule: never surface cross-tenant figures in Nova."""

    def test_tenant_filtering_excludes_other_companies(self):
        snap_a = _make_dummy_snapshot(company_id="company-A", verified_fields=100, total_fields=100)
        snap_b = _make_dummy_snapshot(company_id="company-B", verified_fields=10, total_fields=100)

        overview_a = build_trust_center_overview(
            company_id="company-A", snapshots=[snap_a, snap_b]
        )
        assert overview_a.data_verification.verified_count == 100
        assert overview_a.data_verification.total_count == 100
        assert overview_a.company_id == "company-A"

        overview_b = build_trust_center_overview(
            company_id="company-B", snapshots=[snap_a, snap_b]
        )
        assert overview_b.data_verification.verified_count == 10
        assert overview_b.data_verification.total_count == 100
        assert overview_b.company_id == "company-B"

    def test_single_tenant_includes_all_snapshots(self):
        snap_a = _make_dummy_snapshot(company_id="company-A", verified_fields=50, total_fields=100)
        snap_b = _make_dummy_snapshot(company_id="company-B", verified_fields=40, total_fields=100)

        # Single tenant (Kemp) specifies company_id=None
        overview_single = build_trust_center_overview(company_id=None, snapshots=[snap_a, snap_b])
        assert overview_single.data_verification.verified_count == 90
        assert overview_single.data_verification.total_count == 200


class TestVerificationReport:
    """Exportable verification report generation (Brief §43)."""

    def test_generate_markdown_report_da(self):
        snap = _make_dummy_snapshot(company_id="kemp-1")
        overview = build_trust_center_overview(
            company_id="kemp-1", locale="da", snapshots=[snap]
        )
        report = generate_verification_report(overview, format="markdown")

        assert isinstance(report, str)
        assert "# Valideringsrapport — Nova Trust Center" in report
        assert "## 1. Hovedkonklusioner" in report
        assert "## 2. Brief §43 Nøgletal" in report
        assert "## 3. Manuel Gennemgang & Udeståender" in report
        assert "## 4. Versionsstyring & Audit" in report
        assert overview.analysis_engine_version in report
        assert "Brief §23" in report
        assert "SHA-256" in report

    def test_generate_markdown_report_en(self):
        snap = _make_dummy_snapshot(company_id="nova-tenant-1")
        overview = build_trust_center_overview(
            company_id="nova-tenant-1", locale="en", snapshots=[snap]
        )
        report = generate_verification_report(overview, format="markdown")

        assert isinstance(report, str)
        assert "# Verification Report — Nova Trust Center" in report
        assert "## 1. Executive Summary" in report
        assert "## 2. Core Quality KPIs (Brief §43)" in report
        assert "Data Verification" in report
        assert "Activity Matching" in report
        assert "False Match Rate" in report

    def test_generate_json_report(self):
        snap = _make_dummy_snapshot(company_id="nova-tenant-1")
        overview = build_trust_center_overview(
            company_id="nova-tenant-1", locale="en", snapshots=[snap]
        )
        report = generate_verification_report(overview, format="json")

        assert isinstance(report, dict)
        assert "data_verification" in report
        assert "activity_matching" in report
        assert "analysis_engine_version" in report
        assert report["company_id"] == "nova-tenant-1"


class TestFastAPIEndpoints:
    """Verify FastAPI integration for Trust Center."""

    def test_trust_center_summary_endpoint(self, client):
        resp = client.get("/trust-center/summary?locale=da")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        tc = data["trust_center"]
        assert "data_verification" in tc
        assert "activity_matching" in tc
        assert "items_requiring_review" in tc
        assert "unresolved_items" in tc
        assert "analysis_engine_version" in tc

    def test_trust_center_report_markdown_endpoint(self, client):
        resp = client.get("/trust-center/report?locale=en&format=markdown")
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        content = resp.text
        assert "# Verification Report" in content
        assert "Brief §43" in content

    def test_trust_center_report_json_endpoint(self, client):
        resp = client.get("/trust-center/report?locale=da&format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "report" in data
        assert "data_verification" in data["report"]
