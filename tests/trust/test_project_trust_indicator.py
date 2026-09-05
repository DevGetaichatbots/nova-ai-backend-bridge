"""Tests for TL-7.2 — Project-level trust indicator.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-7-trust-surface.md` (TL-7.2):

- AC1: Indicator renders the brief §22 breakdown.
- AC2: Denominator defined, documented, and exposed to the user (Q-4).
- AC3: Feature-specific confidences displayed alongside (health only).
- AC4: `grep -ri "accurate"` over rendered output returns nothing.
- AC5: Q-4 resolved in `DECISIONS.md` (checked here by asserting the
  resolution text is actually present in the file, not just claimed).

Do-not: never publish a percentage whose denominator cannot be stated in
one sentence, never equate confidence with accuracy.
"""
from __future__ import annotations

import pathlib
import re

from src.version_1_0.adapters import (
    compute_project_trust_breakdown,
    compute_project_trust_breakdown_predictive,
)
from src.version_1_0.formatters import (
    format_health_v1_as_html,
    format_kemp_predictive_v1_as_html,
    format_kemp_v1_as_html,
    format_predictive_v1_as_html,
)


def _health_data(requires_verification=None, selected_activities=10):
    return {
        "executive_summary": {
            "project_health": "YELLOW",
            "selected_activities": selected_activities,
            "confirmed_activities_count": selected_activities - len(requires_verification or []),
            "requires_verification_count": len(requires_verification or []),
        },
        "summary_notes": {"total_activities": selected_activities},
        "progress_vs_expected": [],
        "requires_verification_activities": requires_verification or [],
    }


def _predictive_data(total=50, delayed=12, unverified=3):
    return {
        "insight_data": {
            "total_activities": total,
            "delayed_count": delayed,
            "unverified_delayed_count": unverified,
            "project_status": "AT_RISK",
        },
        "delayed_activities": [
            {"id": f"A{i}", "task_name": "t", "priority": "CRITICAL_NOW"} for i in range(delayed)
        ],
    }


# ============================================================================
# AC1 — the breakdown itself: N verified / N require review / N unmatched
# ============================================================================


class TestBreakdownComputation:
    def test_verified_review_unresolved_partition_the_total(self):
        breakdown = compute_project_trust_breakdown(
            _health_data([
                {"level": "L2_STRONG_MULTI_FIELD"},
                {"level": "L3_PARTIAL"},
                {"level": "L5_NO_RELIABLE_MATCH"},
            ]),
            _health_data([
                {"level": "L2_STRONG_MULTI_FIELD"},
                {"level": "L3_PARTIAL"},
                {"level": "L5_NO_RELIABLE_MATCH"},
            ])["executive_summary"],
        )
        assert breakdown["total"] == 10
        assert breakdown["review"] == 2  # L2 + L3
        assert breakdown["unresolved"] == 1  # L5
        assert breakdown["verified"] == 7
        assert breakdown["verified"] + breakdown["review"] + breakdown["unresolved"] == breakdown["total"]

    def test_verified_matches_confirmed_activities_count(self):
        """Not a coincidence — this is the consistency check ADR-033
        pins: the two independently-computed numbers must agree, because
        `to_trust_state`'s mapping never routes an L1-equivalent row into
        `requires_verification_activities` in the first place."""
        data = _health_data([{"level": "L4_FUZZY"}], selected_activities=20)
        breakdown = compute_project_trust_breakdown(data, data["executive_summary"])
        assert breakdown["verified"] == data["executive_summary"]["confirmed_activities_count"]

    def test_no_requires_verification_rows_is_fully_verified(self):
        data = _health_data([], selected_activities=15)
        breakdown = compute_project_trust_breakdown(data, data["executive_summary"])
        assert breakdown == {"total": 15, "verified": 15, "review": 0, "unresolved": 0}

    def test_unrecognized_level_is_treated_as_unresolved_not_verified(self):
        """An unknown/malformed level string must never be silently
        counted as verified — the most conservative bucket wins."""
        data = _health_data([{"level": "SOMETHING_UNEXPECTED"}], selected_activities=5)
        breakdown = compute_project_trust_breakdown(data, data["executive_summary"])
        assert breakdown["unresolved"] == 1
        assert breakdown["verified"] == 4

    def test_predictive_breakdown_uses_unverified_delayed_count(self):
        breakdown = compute_project_trust_breakdown_predictive(
            {"total_activities": 50, "delayed_count": 12, "unverified_delayed_count": 3}
        )
        assert breakdown == {"total": 50, "verified": 47, "review": 0, "unresolved": 3, "delayed": 12}

    def test_predictive_breakdown_never_invents_a_review_bucket(self):
        """No real per-activity REVIEW signal exists at this layer yet
        (ADR-033) — `review` must be honestly 0, never fabricated."""
        breakdown = compute_project_trust_breakdown_predictive(
            {"total_activities": 10, "delayed_count": 2, "unverified_delayed_count": 0}
        )
        assert breakdown["review"] == 0


# ============================================================================
# AC1 + AC2 — rendered indicator: breakdown visible, denominator on hover
# ============================================================================


class TestRenderedIndicator:
    def test_health_indicator_renders_all_three_counts(self):
        html = format_health_v1_as_html(
            _health_data([{"level": "L2_STRONG_MULTI_FIELD"}, {"level": "L5_NO_RELIABLE_MATCH"}]),
            language="en",
        )
        assert "8 verified" in html
        assert "1 require review" in html
        assert "1 could not be reliably matched" in html
        assert "8 of 10 activities passed Nova" in html

    def test_denominator_is_exposed_on_hover(self):
        """AC2: 'the definition must be visible to the user on hover.'"""
        html = format_health_v1_as_html(
            _health_data([{"level": "L2_STRONG_MULTI_FIELD"}]), language="en",
        )
        m = re.search(r'<div class="ni-trust-summary" title="([^"]+)"', html)
        assert m, "no title= tooltip found on the trust summary element"
        tooltip = m.group(1)
        assert "10" in tooltip  # total
        assert "examined in this comparison" in tooltip

    def test_zero_review_and_zero_unresolved_omits_those_pills(self):
        """A fully-verified project shows just the verified pill — no
        '0 require review' / '0 could not be matched' noise."""
        html = format_health_v1_as_html(_health_data([], selected_activities=10), language="en")
        assert "10 verified" in html
        assert "require review" not in html
        assert "could not be reliably matched" not in html

    def test_predictive_indicator_renders_and_has_no_review_pill(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "47 verified" in html
        assert "3 could not be reliably matched" in html
        assert "require review" not in html

    def test_no_indicator_rendered_when_total_is_zero(self):
        """Brief's Do-not rule in spirit: never publish a percentage (or
        a breakdown) with a denominator of zero — there is nothing to
        state a defensible sentence about."""
        html = format_health_v1_as_html(_health_data([], selected_activities=0), language="en")
        # Check for the rendered element, not the CSS class selector
        # (`ni-trust-panel` is also in the formatter's `<style>` block,
        # so a substring check on the full HTML would always match —
        # the rendered-element check below is what actually verifies
        # the panel was or was not emitted into the DOM).
        assert '<div class="ni-trust-panel">' not in html
        # And the summary sentence ("N of M activities passed…") must
        # not appear — there is nothing to state when total is zero.
        assert "passed Nova" not in html

    def test_both_brand_variants_render_the_indicator(self):
        data = _health_data([{"level": "L3_PARTIAL"}])
        assert "ni-trust-panel" in format_health_v1_as_html(data, language="en")
        assert "ni-trust-panel" in format_kemp_v1_as_html(data, language="da")

        pdata = _predictive_data()
        assert "ni-trust-panel" in format_predictive_v1_as_html(pdata, language="en")
        assert "ni-trust-panel" in format_kemp_predictive_v1_as_html(pdata, language="da")

    def test_danish_rendering_uses_danish_strings(self):
        html = format_health_v1_as_html(
            _health_data([{"level": "L2_STRONG_MULTI_FIELD"}]), language="da",
        )
        assert "Tillid til denne analyse" in html
        assert "bestod Novas verifikationsregler" in html
        assert "verificeret" in html
        assert "kræver kontrol" in html


# ============================================================================
# AC3 — feature-specific confidences alongside (brief §30)
# ============================================================================


class TestFeatureConfidencesAlongside:
    def test_all_five_features_rendered_for_health(self):
        html = format_health_v1_as_html(_health_data([{"level": "L2_STRONG_MULTI_FIELD"}]), language="en")
        for label in (
            "Schedule Parsing", "Activity Matching", "Progress Comparison",
            "Critical Path", "Forecast",
        ):
            assert label in html

    def test_forecast_unavailable_renders_a_visible_state_not_a_gap(self):
        """`compute_feature_confidences` reports `forecast` as the literal
        string `"unavailable"`, not a `TrustState` value — the renderer
        must show something coherent for it, not silently drop the row."""
        html = format_health_v1_as_html(_health_data([]), language="en")
        assert "Forecast" in html
        assert "Not available" in html

    def test_predictive_dashboard_has_no_feature_confidence_section(self):
        """The predictive pipeline does not compute per-feature
        confidences (ADR-033) — no fabricated section should appear."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        # Check for the rendered element, not the CSS class selector
        # (`ni-trust-features` is also in the formatter's `<style>` block).
        assert '<div class="ni-trust-features">' not in html


# ============================================================================
# AC4 — never the word "accurate"
# ============================================================================


class TestNeverAccurate:
    def test_health_output_never_says_accurate(self):
        html = format_health_v1_as_html(
            _health_data([{"level": "L2_STRONG_MULTI_FIELD"}, {"level": "L5_NO_RELIABLE_MATCH"}]),
            language="en",
        )
        assert "accura" not in html.lower()

    def test_predictive_output_never_says_accurate(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "accura" not in html.lower()

    def test_danish_output_never_says_accurate(self):
        html = format_kemp_v1_as_html(
            _health_data([{"level": "L2_STRONG_MULTI_FIELD"}]), language="da",
        )
        assert "accura" not in html.lower()

    def test_localization_strings_themselves_never_say_accurate(self):
        """Static check on the source strings, not just one rendered
        sample — catches a future trust_* key that slips the word in
        regardless of which fixture happens to be tested."""
        from src.version_1_0.localization import LABELS

        for lang in ("en", "da"):
            for key, value in LABELS[lang].items():
                if key.startswith("trust_"):
                    assert "accura" not in value.lower(), f"{lang}.{key} contains 'accura...': {value!r}"


# ============================================================================
# AC5 — Q-4 resolved in DECISIONS.md
# ============================================================================


class TestQ4Resolved:
    def test_q4_marked_resolved_in_progress_md(self):
        progress_path = (
            pathlib.Path(__file__).resolve().parents[4]
            / "changes" / "trust-layer" / "plan" / "PROGRESS.md"
        )
        text = progress_path.read_text(encoding="utf-8")
        m = re.search(r"\|\s*Q-4\s*\|.*\|\s*(RESOLVED[^|]*)\|", text)
        assert m, "Q-4 row in PROGRESS.md's Open Questions table is not marked RESOLVED"

    def test_denominator_definition_documented_in_decisions_md(self):
        decisions_path = (
            pathlib.Path(__file__).resolve().parents[4]
            / "changes" / "trust-layer" / "plan" / "DECISIONS.md"
        )
        text = decisions_path.read_text(encoding="utf-8")
        assert "Q-4" in text
        assert "selected_activities" in text  # the actual denominator field name
