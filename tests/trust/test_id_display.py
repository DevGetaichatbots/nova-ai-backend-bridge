r"""Tests for TL-2.4 — Display contract for unverifiable IDs.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-2-identity.md` (TL-2.4):
- AC1: Missing source_id renders as canonical marker ("Unable to verify" EN / "Kan ikke verificeres" DA).
- AC2: Tooltip matches brief §21 verbatim.
- AC3: Works across both dashboards (Health & Predictive) and both brand variants (Nova & Kemp).
"""
from __future__ import annotations

import pytest
from src.version_1_0.formatters import (
    format_health_v1_as_html,
    format_kemp_v1_as_html,
    format_predictive_v1_as_html,
    format_kemp_predictive_v1_as_html,
)


@pytest.fixture
def sample_health_data_unverified():
    return {
        "executive_summary": {"project_health": "YELLOW", "selected_activities": 1},
        "summary_notes": {"total_activities": 1, "overall_progress_new_pct": 50},
        "progress_vs_expected": [
            {
                "id": "",
                "source_id": "",
                "activity": "Unverified Task",
                "status": "BEHIND",
                "actual_pct": 20,
                "expected_pct": 50,
                "deviation": -30,
            }
        ],
    }


@pytest.fixture
def sample_predictive_data_unverified():
    return {
        "insight_data": {"project_status": "AT_RISK", "total_activities": 1},
        "delayed_activities": [
            {
                "id": "",
                "source_id": "",
                "task_name": "Unverified Delay Task",
                "days_overdue": 10,
                "priority": "CRITICAL_NOW",
            }
        ],
    }


class TestIdDisplayContract:
    def test_health_english_unverified_marker(self, sample_health_data_unverified):
        html = format_health_v1_as_html(sample_health_data_unverified, language="en")
        assert "Unable to verify" in html or "Unable to Verify" in html
        assert "Nova could not reliably verify this value" in html

    def test_health_danish_unverified_marker(self, sample_health_data_unverified):
        html = format_health_v1_as_html(sample_health_data_unverified, language="da")
        assert "Kan ikke verificeres" in html
        assert "Nova kunne ikke pålideligt verificere denne værdi" in html

    def test_kemp_variant_unverified_marker(self, sample_health_data_unverified):
        html = format_kemp_v1_as_html(sample_health_data_unverified, language="da")
        assert "Kan ikke verificeres" in html

    def test_predictive_unverified_marker(self, sample_predictive_data_unverified):
        html_en = format_predictive_v1_as_html(sample_predictive_data_unverified, language="en")
        assert "Unable to verify" in html_en or "Unable to Verify" in html_en

        html_da = format_kemp_predictive_v1_as_html(sample_predictive_data_unverified, language="da")
        assert "Kan ikke verificeres" in html_da
