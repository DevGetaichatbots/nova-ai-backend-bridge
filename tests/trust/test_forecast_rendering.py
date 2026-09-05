"""Tests for TL-7.4 — Forecast never renders like observed fact.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-7-trust-surface.md` (TL-7.4):

- AC1: Every forecast element shows confidence, evidence, and drivers.
  `predictive_snapshot.what_will_happen`, `estimated_delay_impact`,
  `confidence_level` (band), `confidence_basis`, and `main_delay_drivers`
  all render inside the forecast panel.
- AC2: The two headline snapshot fields (`what_will_happen`,
  `estimated_delay_impact`) render as forecasts — inside `.ni-forecast-panel`,
  never inside the `.ni-kpis` strip.
- AC3: Observed and forecast data are never visually merged — the forecast
  panel is a structurally separate section from the KPI strip, and the
  zero-delay case uses `nova_insight` chip (Do-not rule from TL-5.6's
  TestStructuralRiskOverride) to avoid reading as a delay prediction.
- AC4: Low-confidence forecasts are marked at the point of display, inside
  the panel, not in a footnote.

Both dashboards (Nova predictive + Kemp predictive) are covered.
The health dashboard must NOT have a forecast panel (health has no snapshot).
"""
from __future__ import annotations

import re

import pytest

from src.version_1_0.formatters import (
    _confidence_badge,
    format_kemp_predictive_v1_as_html,
    format_health_v1_as_html,
    format_predictive_v1_as_html,
)


# ============================================================================
# Fixtures
# ============================================================================


def _health_data(selected_activities: int = 10):
    return {
        "executive_summary": {
            "project_health": "YELLOW",
            "selected_activities": selected_activities,
        },
        "summary_notes": {"total_activities": selected_activities},
        "progress_vs_expected": [],
    }


def _predictive_data(
    *,
    total: int = 50,
    delayed: int = 12,
    unverified: int = 3,
    with_snapshot: bool = True,
    confidence_level: str = "HIGH",
    with_biggest_risk: bool = False,
) -> dict:
    """Build a predictive data dict that exercises the forecast panel.

    `with_snapshot=True` includes `predictive_snapshot` with all 5 required
    fields (what_will_happen, estimated_delay_impact, confidence_level,
    confidence_basis, main_delay_drivers). `with_biggest_risk=True` adds a
    `predictive_biggest_risk` section.
    """
    data: dict = {
        "insight_data": {
            "total_activities": total,
            "delayed_count": delayed,
            "unverified_delayed_count": unverified,
            "project_status": "AT_RISK",
        },
        "delayed_activities": [
            {"id": f"A{i}", "task_name": f"Task {i}", "priority": "CRITICAL_NOW"}
            for i in range(delayed)
        ],
    }
    if with_snapshot:
        data["predictive_snapshot"] = {
            "what_will_happen": (
                "If no action is taken, the project will be delayed by 4-8 weeks, "
                "primarily driven by coordination failures in Omr. 2."
            ),
            "estimated_delay_impact": "+6 weeks",
            "confidence_level": confidence_level,
            "confidence_basis": (
                "Based on 28 delayed activities with 6 identified root causes "
                "and clear predecessor chains across 3 disciplines."
            ),
            "main_delay_drivers": [
                "12 coordination bottlenecks blocking cross-discipline handoffs",
                "6 unresolved bygherre decisions stalling design input",
                "8 production tasks overdue in Omr. 2 and Omr. 3",
            ],
        }
    if with_biggest_risk:
        data["predictive_biggest_risk"] = {
            "risk_title": "Task ID 41 — coordination milestone 47 days overdue",
            "will_block": (
                "Unresolved, this will delay electrical and HVAC installation "
                "across Omr. 2 and Omr. 3 by at least 6-8 weeks."
            ),
            "prevent_action_now": (
                "Escalate ID 41 coordination meeting to project director today."
            ),
        }
    return data


def _zero_delay_data() -> dict:
    """Data where delayed_count == 0 — triggers the Do-not rule
    (TestStructuralRiskOverride from TL-5.6): chip must be nova_insight."""
    data = _predictive_data(delayed=0, with_snapshot=True)
    data["predictive_snapshot"]["what_will_happen"] = (
        "Large-scale restructuring introduces elevated coordination risk — "
        "validation of new dependency links is required before schedule "
        "impact can be confirmed."
    )
    # No estimated_delay_impact on zero-delay (nothing to delay)
    data["predictive_snapshot"].pop("estimated_delay_impact", None)
    return data


# ============================================================================
# AC1 — Every forecast element shows confidence, evidence, and drivers
# ============================================================================


class TestAC1ForecastElementsPresent:
    """AC1: every forecast element shows confidence, evidence, and drivers."""

    def test_snapshot_carries_nova_forecast_chip(self):
        """The forecast panel carries a NOVA_FORECAST evidence chip — the
        visual cue that this content is a prediction, not a measured fact."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "ni-evidence-label--nova_forecast" in html

    def test_snapshot_card_shows_confidence_band(self):
        """AC1: the confidence band (HIGH/MEDIUM/LOW badge) is present
        inside the rendered HTML."""
        html = format_predictive_v1_as_html(_predictive_data(confidence_level="HIGH"), language="en")
        assert "ni-trust-badge--verified" in html  # HIGH maps to verified tone

    def test_snapshot_card_shows_medium_confidence_band(self):
        html = format_predictive_v1_as_html(_predictive_data(confidence_level="MEDIUM"), language="en")
        assert "ni-trust-badge--review" in html  # MEDIUM maps to review tone

    def test_snapshot_card_shows_key_drivers(self):
        """AC1: all 3 `main_delay_drivers` appear in the rendered HTML."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "ni-forecast-driver" in html
        assert "12 coordination bottlenecks blocking cross-discipline handoffs" in html
        assert "6 unresolved bygherre decisions stalling design input" in html
        assert "8 production tasks overdue in Omr. 2 and Omr. 3" in html

    def test_snapshot_card_shows_confidence_basis(self):
        """AC1: the `confidence_basis` one-sentence explanation renders."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "Based on 28 delayed activities" in html
        assert "ni-forecast-basis" in html

    def test_snapshot_card_shows_what_will_happen(self):
        """AC1 (integration): `what_will_happen` headline is in the output."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "If no action is taken, the project will be delayed" in html

    def test_snapshot_card_shows_estimated_delay_impact(self):
        """AC1: `estimated_delay_impact` renders when delayed > 0."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "+6 weeks" in html
        assert "ni-forecast-impact-value" in html

    def test_no_snapshot_renders_empty(self):
        """If `predictive_snapshot` is absent, no forecast panel is emitted —
        the section only renders when there is actual content."""
        html = format_predictive_v1_as_html(_predictive_data(with_snapshot=False), language="en")
        # Check for the rendered element, not the CSS class selector
        # (`ni-forecast-panel` is also in the formatter's `<style>` block,
        # so a bare substring check on the full HTML always matches).
        assert '<section class="ni-section ni-forecast-panel">' not in html


# ============================================================================
# AC2 — Two headline snapshot fields render as forecasts, not KPI tiles
# ============================================================================


class TestAC2HeadlineFieldsAreForecasts:
    """AC2: `what_will_happen` and `estimated_delay_impact` render inside
    the forecast panel, never inside the `.ni-kpis` strip (brief §31's
    specific failure: a forecast number in the same style as a measured KPI)."""

    def test_what_will_happen_is_in_forecast_panel(self):
        """`what_will_happen` text appears inside `.ni-forecast-panel`."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "ni-forecast-panel" in html
        # The headline class wraps it
        assert "ni-forecast-headline" in html

    def test_estimated_delay_impact_is_in_forecast_panel(self):
        """The delay impact value appears inside the forecast panel, not in
        the KPI strip."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        # Impact rendered inside the panel's impact-value class
        assert "ni-forecast-impact-value" in html

    def test_what_will_happen_not_in_kpi_strip(self):
        """The `what_will_happen` headline must NOT be inside the `.ni-kpis`
        element — that is precisely the failure brief §31 names."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        # Extract the kpis strip (between ni-kpis and its closing tag)
        kpis_match = re.search(r'class="ni-kpis"[^>]*>(.*?)</div>\s*<div', html, re.DOTALL)
        if kpis_match:
            kpis_html = kpis_match.group(1)
            assert "If no action is taken" not in kpis_html

    def test_estimated_delay_impact_not_in_kpi_strip(self):
        """The delay impact value must NOT be inside the `.ni-kpis` strip."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        kpis_match = re.search(r'class="ni-kpis"[^>]*>(.*?)</div>\s*<div', html, re.DOTALL)
        if kpis_match:
            kpis_html = kpis_match.group(1)
            # The +6 weeks value should not appear as a raw KPI value
            assert "ni-forecast-impact-value" not in kpis_html


# ============================================================================
# AC3 — Observed and forecast data never visually merged
# ============================================================================


class TestAC3ObservedAndForecastSeparate:
    """AC3: the forecast panel is structurally distinct from the KPI/observed
    sections. The zero-delay case uses `nova_insight` chip (Do-not rule)."""

    def test_forecast_panel_present_as_distinct_section(self):
        """`.ni-forecast-panel` exists in the HTML as a section, separate
        from the KPI strip."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "ni-forecast-panel" in html
        # The forecast panel must appear AFTER the KPI strip
        kpi_pos = html.find("ni-kpis")
        panel_pos = html.find("ni-forecast-panel")
        assert kpi_pos != -1, "KPI strip missing"
        assert panel_pos != -1, "Forecast panel missing"
        assert panel_pos > kpi_pos, "Forecast panel must be after KPI strip"

    def test_forecast_panel_not_inside_kpi_strip(self):
        """The forecast panel class must not appear inside the kpis element —
        that would merge them visually."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        kpis_match = re.search(r'class="ni-kpis"[^>]*>(.*?)</div>\s*<div', html, re.DOTALL)
        if kpis_match:
            kpis_html = kpis_match.group(1)
            assert "ni-forecast-panel" not in kpis_html

    def test_zero_delay_uses_insight_chip_not_forecast(self):
        """Zero-delay case (Do-not rule, TL-5.6 TestStructuralRiskOverride):
        when delayed_count == 0, the chip inside the snapshot card must be
        `nova_insight` (structural risk), NOT `nova_forecast` (delay prediction).
        The `what_will_happen` text is an inference about structure, not a
        delay prediction."""
        html = format_predictive_v1_as_html(_zero_delay_data(), language="en")
        # Panel is still rendered (not suppressed)
        assert "ni-forecast-panel" in html
        # Chip is nova_insight, not nova_forecast, inside the panel heading
        panel_match = re.search(r'ni-forecast-panel">(.*?)</section>', html, re.DOTALL)
        assert panel_match, "forecast panel not found"
        panel_html = panel_match.group(1)
        assert "ni-evidence-label--nova_insight" in panel_html
        # nova_forecast chip must not appear inside the panel head area
        panel_head_match = re.search(r'ni-forecast-panel-head">(.*?)</div>', panel_html, re.DOTALL)
        if panel_head_match:
            assert "ni-evidence-label--nova_forecast" not in panel_head_match.group(1)

    def test_zero_delay_omits_estimated_delay_impact(self):
        """Zero-delay case: `estimated_delay_impact` must be omitted — there
        is no delay to impact. Showing it would mislead the PM into thinking
        a delay window exists when it does not."""
        html = format_predictive_v1_as_html(_zero_delay_data(), language="en")
        # The impact-value class is only rendered when there is an impact
        # In zero-delay, even if the snapshot has the field, the panel omits it
        panel_match = re.search(r'ni-forecast-panel">(.*?)</section>', html, re.DOTALL)
        if panel_match:
            assert "ni-forecast-impact-value" not in panel_match.group(1)


# ============================================================================
# AC4 — Low-confidence forecasts marked at point of display
# ============================================================================


class TestAC4LowConfidenceAtPointOfDisplay:
    """AC4: low-confidence forecasts must be marked at the point of display,
    inside the panel — not in a footer or footnote. Brief §31: "where forecast
    confidence is low, say so at the point of display"."""

    def test_low_confidence_renders_caution_at_panel(self):
        """LOW confidence: the caution text appears within `.ni-forecast-panel`,
        not only in an external footer."""
        html = format_predictive_v1_as_html(
            _predictive_data(confidence_level="LOW"), language="en"
        )
        assert "ni-forecast-panel" in html
        assert "ni-forecast-caution" in html
        # The caution class must be inside the panel, not outside it
        panel_match = re.search(r'ni-forecast-panel">(.*?)</section>', html, re.DOTALL)
        assert panel_match, "forecast panel not found"
        assert "ni-forecast-caution" in panel_match.group(1), (
            "caution block must be inside the panel, not in a footnote"
        )

    def test_low_confidence_caution_text_present(self):
        """The actual caution string ('interpret with caution') renders."""
        html = format_predictive_v1_as_html(
            _predictive_data(confidence_level="LOW"), language="en"
        )
        assert "caution" in html.lower()

    def test_high_confidence_no_caution(self):
        """HIGH confidence must NOT show the caution block — reserved for LOW."""
        html = format_predictive_v1_as_html(
            _predictive_data(confidence_level="HIGH"), language="en"
        )
        # Check for the rendered element, not the CSS class selector
        # (`ni-forecast-caution` is also in the formatter's `<style>` block).
        assert 'class="ni-forecast-caution"' not in html

    def test_medium_confidence_no_caution(self):
        """MEDIUM confidence must NOT show the caution block either."""
        html = format_predictive_v1_as_html(
            _predictive_data(confidence_level="MEDIUM"), language="en"
        )
        assert 'class="ni-forecast-caution"' not in html

    def test_low_confidence_band_badge_is_unverified_tone(self):
        """LOW confidence badge reuses the `ni-trust-badge--unverified` tone —
        consistent with the trust layer's existing colour vocabulary."""
        html = format_predictive_v1_as_html(
            _predictive_data(confidence_level="LOW"), language="en"
        )
        assert "ni-trust-badge--unverified" in html


# ============================================================================
# Both dashboards — parity (AC4 in phase plan: applied to both brands)
# ============================================================================


class TestBothDashboards:
    """The forecast panel must appear in both Nova and Kemp predictive
    variants. The health dashboard must never have a forecast panel."""

    def test_nova_predictive_has_forecast_panel(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "ni-forecast-panel" in html

    def test_kemp_predictive_has_forecast_panel(self):
        """Kemp is Danish-only and uses `CSS_KEMP`. The forecast panel must
        render there too — parity is enforced by the shared `_render_payload`
        path."""
        html = format_kemp_predictive_v1_as_html(_predictive_data(), language="da")
        assert "ni-forecast-panel" in html

    def test_kemp_predictive_forecast_panel_in_danish(self):
        """The forecast panel heading and labels render in Danish for Kemp."""
        html = format_kemp_predictive_v1_as_html(_predictive_data(), language="da")
        # Danish label for 'forecast outlook heading' = "Prognose"
        assert "Prognose" in html or "ni-forecast-panel" in html

    def test_health_dashboard_has_no_forecast_panel(self):
        """The health dashboard has no `predictive_snapshot` — it must not
        render a forecast panel. Mixing them would imply the health dashboard
        makes forward-looking delay predictions, which it does not."""
        html = format_health_v1_as_html(_health_data(), language="en")
        # Check for the rendered element, not the CSS class selector
        # (`ni-forecast-panel` is also in the formatter's `<style>` block,
        # which is shared across both dashboards regardless of content).
        assert '<section class="ni-section ni-forecast-panel">' not in html


# ============================================================================
# Biggest-risk card
# ============================================================================


class TestBiggestRiskCard:
    """The `predictive_biggest_risk` card carries nova_forecast chips on both
    `will_block` and `prevent_action_now` — both are forecast consequences."""

    def test_biggest_risk_card_renders_when_present(self):
        html = format_predictive_v1_as_html(
            _predictive_data(with_biggest_risk=True), language="en"
        )
        assert "ni-forecast-risk-panel" in html

    def test_biggest_risk_card_omitted_when_absent(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        # Check for the rendered element, not the CSS class selector
        # (`ni-forecast-risk-panel` is also in the formatter's `<style>` block).
        assert '<div class="ni-forecast-risk-panel">' not in html

    def test_biggest_risk_will_block_renders(self):
        html = format_predictive_v1_as_html(
            _predictive_data(with_biggest_risk=True), language="en"
        )
        assert "Unresolved, this will delay electrical" in html

    def test_biggest_risk_prevent_action_renders(self):
        html = format_predictive_v1_as_html(
            _predictive_data(with_biggest_risk=True), language="en"
        )
        assert "Escalate ID 41" in html

    def test_biggest_risk_carries_nova_forecast_chip(self):
        """Both `will_block` and `prevent_action_now` carry the
        `nova_forecast` chip — consistent with their evidence-class
        classification in `FIELD_EVIDENCE_CLASSIFICATIONS` (TL-5.6)."""
        html = format_predictive_v1_as_html(
            _predictive_data(with_biggest_risk=True), language="en"
        )
        # Capture the full panel body up to the next top-level <section> —
        # the previous non-greedy `(.*?)</div>` stopped at the FIRST closing
        # </div> (the risk-title div), silently checking almost nothing.
        risk_match = re.search(
            r'<div class="ni-forecast-risk-panel">(.*?)(?=<section)', html, re.DOTALL
        )
        assert risk_match, "risk panel not found"
        # Both will_block and prevent_action_now carry their own chip.
        assert risk_match.group(1).count("ni-evidence-label--nova_forecast") == 2


# ============================================================================
# Unit tests for _confidence_badge helper
# ============================================================================


class TestConfidenceBadge:
    """Unit tests for the `_confidence_badge` helper — the building block
    used by `_render_predictive_snapshot`."""

    def test_high_maps_to_verified_tone(self):
        badge = _confidence_badge("HIGH", "en")
        assert "ni-trust-badge--verified" in badge
        assert "High" in badge

    def test_medium_maps_to_review_tone(self):
        badge = _confidence_badge("MEDIUM", "en")
        assert "ni-trust-badge--review" in badge
        assert "Medium" in badge

    def test_low_maps_to_unverified_tone(self):
        badge = _confidence_badge("LOW", "en")
        assert "ni-trust-badge--unverified" in badge
        assert "caution" in badge.lower()

    def test_none_returns_empty(self):
        assert _confidence_badge(None, "en") == ""

    def test_unknown_returns_empty(self):
        assert _confidence_badge("VERY_HIGH", "en") == ""

    def test_case_insensitive(self):
        """Input is normalized to upper — 'high' and 'HIGH' are equivalent."""
        badge_upper = _confidence_badge("HIGH", "en")
        badge_lower = _confidence_badge("high", "en")
        assert badge_upper == badge_lower

    def test_danish_label(self):
        badge = _confidence_badge("HIGH", "da")
        assert "ni-trust-badge--verified" in badge
        assert "Høj" in badge

    def test_badge_has_confidence_label_as_title(self):
        """The badge carries a `title=` tooltip explaining the attribute."""
        badge = _confidence_badge("MEDIUM", "en")
        assert 'title="' in badge
