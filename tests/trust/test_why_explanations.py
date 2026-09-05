"""Tests for TL-7.5 — "Why?" explanations.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-7-trust-surface.md` (TL-7.5):

- AC1: "Why?" available on risk flags, priority actions, and the trust
  indicator.
- AC2: Explanations assembled from recorded evidence, no LLM call.
- AC3: Content matches brief §32's structure (specific counts, evidence).
- AC4: Works inside the sandboxed iframe both apps render into (client-side
  disclosure, no network call).

Do-not: never generate the explanation with a model. A generated rationale
for a deterministic decision is itself an unverified claim.
"""
from __future__ import annotations

import re

from src.version_1_0.adapters import _activity_row
from src.version_1_0.formatters import (
    JS,
    _why_action_explanation,
    _why_button,
    _why_delayed_row_explanation,
    format_health_v1_as_html,
    format_kemp_predictive_v1_as_html,
    format_predictive_v1_as_html,
)


def _predictive_data(*, with_action=True):
    data = {
        "insight_data": {
            "total_activities": 50,
            "delayed_count": 3,
            "unverified_delayed_count": 0,
            "project_status": "AT_RISK",
        },
        "delayed_activities": [
            {
                "id": "A1", "task_name": "Root task", "priority": "CRITICAL_NOW",
                "days_overdue": 20, "is_root_cause": True, "blocked_by_id": None,
                "area": "Omr. 1",
            },
            {
                "id": "A2", "task_name": "Downstream task", "priority": "IMPORTANT_NEXT",
                "days_overdue": 5, "is_root_cause": False, "blocked_by_id": "A1",
                "area": "Omr. 1",
            },
            {
                "id": "A3", "task_name": "No-evidence task", "priority": "MONITOR",
                "days_overdue": 0, "is_root_cause": False, "blocked_by_id": None,
                "area": "Omr. 2",
            },
        ],
    }
    if with_action:
        data["executive_actions"] = [
            {
                "action": "Escalate A1 coordination meeting",
                "responsible": "PM",
                "deadline": "this week",
                "related_task_ids": ["A1", "A2"],
            }
        ]
    return data


def _health_data():
    return {
        "executive_summary": {
            "project_health": "YELLOW",
            "selected_activities": 10,
            "confirmed_activities_count": 9,
            "requires_verification_count": 1,
        },
        "summary_notes": {"total_activities": 10},
        "progress_vs_expected": [],
        "requires_verification_activities": [{"level": "L3_PARTIAL"}],
    }


# ============================================================================
# Unit tests — the explanation builders themselves
# ============================================================================


class TestWhyButtonHelper:
    def test_empty_explanation_renders_nothing(self):
        """No affordance for a flag with nothing recorded behind it —
        never invent a rationale to fill the button."""
        assert _why_button("", "en") == ""

    def test_non_empty_explanation_renders_button_and_hidden_panel(self):
        html = _why_button("Some recorded fact.", "en")
        assert '<button type="button" class="ni-why-btn"' in html
        assert 'onclick="niV1WhyToggle(this)"' in html
        assert '<div class="ni-why-panel" hidden>Some recorded fact.</div>' in html

    def test_explanation_text_is_html_escaped(self):
        html = _why_button("<script>alert(1)</script>", "en")
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestDelayedRowExplanation:
    """AC2/AC3: assembled purely from `is_root_cause` / `blocked_by_id` /
    `days_overdue` — the same deterministic facts `compute_predictive_facts`
    (TL-5.2) already computed, never a generated rationale."""

    def test_root_cause_row_cites_root_cause_and_days_overdue(self):
        row = {"is_root_cause": True, "blocked_by_id": None, "days_overdue": 20}
        text = _why_delayed_row_explanation(row, "en")
        assert "root cause" in text
        assert "20 days overdue" in text

    def test_downstream_row_cites_blocking_id_and_days_overdue(self):
        row = {"is_root_cause": False, "blocked_by_id": "A1", "days_overdue": 5}
        text = _why_delayed_row_explanation(row, "en")
        assert "A1" in text
        assert "downstream consequence" in text
        assert "5 days overdue" in text

    def test_no_recorded_evidence_yields_empty_explanation(self):
        """A row with zero days overdue, not a root cause, and no
        recorded blocking predecessor has nothing to explain — the
        button must not render (see `TestWhyButtonHelper`)."""
        row = {"is_root_cause": False, "blocked_by_id": None, "days_overdue": 0}
        assert _why_delayed_row_explanation(row, "en") == ""

    def test_never_mentions_the_uncalibrated_priority_thresholds(self):
        """The explanation must not dress up
        `_CRITICAL_DAYS_OVERDUE_UNCALIBRATED` (14) or
        `_CRITICAL_AFFECTED_COUNT_UNCALIBRATED` (3) as validated business
        rules — those constants are explicitly uncalibrated pending
        `EXT-1` (brief's own `TL-3.6`/`TL-4.7` posture)."""
        row = {"is_root_cause": True, "blocked_by_id": None, "days_overdue": 20}
        text = _why_delayed_row_explanation(row, "en").lower()
        assert "threshold" not in text

    def test_danish_translation(self):
        row = {"is_root_cause": True, "blocked_by_id": None, "days_overdue": 20}
        text = _why_delayed_row_explanation(row, "da")
        assert "grundårsag" in text
        assert "20 dage forsinket" in text


class TestActionExplanation:
    def test_cites_related_task_count(self):
        action = {"related_task_ids": ["A1", "A2", "A3"]}
        text = _why_action_explanation(action, "en")
        assert "3" in text
        assert "related delayed activities" in text

    def test_no_related_ids_yields_empty_explanation(self):
        assert _why_action_explanation({}, "en") == ""
        assert _why_action_explanation({"related_task_ids": []}, "en") == ""


# ============================================================================
# AC1 — rendered on risk flags, priority actions, and the trust indicator
# ============================================================================


class TestWhyOnRiskFlags:
    def test_delayed_table_rows_carry_why_buttons(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert html.count('<button type="button" class="ni-why-btn"') >= 4

    def test_root_cause_row_explanation_appears_in_rendered_html(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert (
            "This task is a root cause" in html
            and "20 days overdue" in html
        )

    def test_downstream_row_explanation_appears_in_rendered_html(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "downstream consequence of A1" in html

    def test_row_with_no_evidence_gets_no_why_button_for_that_row(self):
        """`A3` (no days overdue, not root cause, no blocking id) must
        not render a `Why?` button next to its own priority cell."""
        row = _activity_row(
            {
                "id": "A3", "task_name": "No-evidence task",
                "priority": "MONITOR", "days_overdue": 0,
                "is_root_cause": False, "blocked_by_id": None,
            },
            task_key="task_name",
        )
        assert _why_delayed_row_explanation(row, "en") == ""

    def test_health_dashboard_has_no_delayed_table_and_no_row_why_buttons(self):
        """The health dashboard has no priority-flagged delayed table —
        nothing to attach a risk-flag `Why?` to."""
        html = format_health_v1_as_html(_health_data(), language="en")
        assert "root cause" not in html
        assert "downstream consequence" not in html


class TestWhyOnPriorityActions:
    def test_action_carries_why_button_with_related_count(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "Based on 2 related delayed activities" in html

    def test_action_without_related_ids_has_no_action_why(self):
        data = _predictive_data(with_action=True)
        data["executive_actions"][0]["related_task_ids"] = []
        html = format_predictive_v1_as_html(data, language="en")
        assert "related delayed activities" not in html

    def test_no_actions_at_all_renders_no_actions_section(self):
        data = _predictive_data(with_action=False)
        html = format_predictive_v1_as_html(data, language="en")
        assert "related delayed activities" not in html


class TestWhyOnTrustIndicator:
    def test_trust_panel_carries_a_why_button(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        panel_match = re.search(r'<div class="ni-trust-panel">(.*?)</div>', html, re.DOTALL)
        assert panel_match, "trust panel title div not found"
        assert "ni-why-btn" in panel_match.group(1)

    def test_trust_panel_why_reveals_the_same_methodology_as_the_hover_tooltip(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        tooltip_match = re.search(r'class="ni-trust-summary" title="([^"]+)"', html)
        panel_match = re.search(r'<div class="ni-why-panel" hidden>([^<]+)</div>', html)
        assert tooltip_match and panel_match
        # Both should mention the same total (denominator), even though
        # HTML-escaping differs slightly (raw ' vs &#x27; etc. do not
        # appear in this fixture, so a direct compare is safe here).
        assert tooltip_match.group(1) == panel_match.group(1)

    def test_health_trust_panel_also_carries_a_why_button(self):
        html = format_health_v1_as_html(_health_data(), language="en")
        panel_match = re.search(r'<div class="ni-trust-panel">(.*?)</div>', html, re.DOTALL)
        assert panel_match, "trust panel title div not found"
        assert "ni-why-btn" in panel_match.group(1)


# ============================================================================
# AC2 — no LLM call; AC4 — client-side only, works in a sandboxed iframe
# ============================================================================


class TestNoModelAndClientSideOnly:
    def test_why_toggle_is_a_pure_client_side_function_in_the_embedded_js(self):
        assert "niV1WhyToggle" in JS

    def test_embedded_js_has_no_network_calls(self):
        assert "fetch(" not in JS
        assert "XMLHttpRequest" not in JS

    def test_explanation_builders_are_deterministic_pure_functions(self):
        """Same input, same output, twice in a row — no hidden
        randomness or model call in the path."""
        row = {"is_root_cause": True, "blocked_by_id": None, "days_overdue": 20}
        assert _why_delayed_row_explanation(row, "en") == _why_delayed_row_explanation(row, "en")

    def test_why_disclosure_uses_inline_onclick_not_addeventlistener_wiring(self):
        """The disclosure must work without any additional JS running
        after the HTML is dropped into a sandboxed iframe via `srcdoc`
        — an inline `onclick` calling an already-embedded `<script>`
        function needs no external wiring step."""
        html = _why_button("fact", "en")
        assert 'onclick="niV1WhyToggle(this)"' in html


# ============================================================================
# Both brands / both languages
# ============================================================================


class TestBrandAndLocaleParity:
    def test_kemp_predictive_has_why_buttons_in_danish(self):
        html = format_kemp_predictive_v1_as_html(_predictive_data(), language="da")
        assert "Hvorfor?" in html
        assert "grundårsag" in html

    def test_english_predictive_has_why_buttons_in_english(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert ">Why?<" in html
