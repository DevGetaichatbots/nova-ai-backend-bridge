"""Tests for TL-7.7 — PDF export carries the same trust model.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-7-trust-surface.md` (TL-7.7):

- AC1: Trust badges visible and correctly coloured in exported PDFs.
- AC2: Hover-only information has a visible print fallback.
- AC3: Partial-verification footer appears when applicable.
- AC4: Trust indicator on page one.
- AC5: Verified for both brands.

The live PDF path (`src/pdf_export.py`) renders the exact same
self-contained HTML the browser shows, via headless Chromium — these
tests verify the pieces that make trust survive that trip (the CSS
injected at render time, the footer, page-one positioning) without
actually launching a browser; `Verify` in the plan also calls for a
manual inspection of one exported PDF per brand, which is outside a
pytest suite's reach.

Do-not: do not rely on hover tooltips in a PDF.
"""
from __future__ import annotations

import re

from src.pdf_export import _COLOR_CSS, _PDF_TRUST_FALLBACK_CSS, _render
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
# AC3 — partial-verification footer (brief §44's literal wording)
# ============================================================================


class TestMethodologyFooter:
    def test_footer_appears_when_health_has_activities_requiring_review(self):
        html = format_health_v1_as_html(
            _health_data([{"level": "L2_STRONG_MULTI_FIELD"}]), language="en",
        )
        assert 'class="ni-methodology-footer"' in html
        assert "Based on partially verified activity matching." in html

    def test_footer_appears_when_health_has_unresolved_activities(self):
        html = format_health_v1_as_html(
            _health_data([{"level": "L5_NO_RELIABLE_MATCH"}]), language="en",
        )
        assert 'class="ni-methodology-footer"' in html

    def test_footer_absent_when_fully_verified(self):
        """No footer at all on a clean comparison — a footer on every
        report regardless of outcome would be exactly the noise brief
        §21's 'no Christmas tree' rule and TL-7.2's 'no 0 require review
        noise' precedent both argue against."""
        html = format_health_v1_as_html(_health_data([]), language="en")
        assert 'class="ni-methodology-footer"' not in html

    def test_footer_appears_when_predictive_has_unverified_delayed(self):
        html = format_predictive_v1_as_html(_predictive_data(unverified=3), language="en")
        assert 'class="ni-methodology-footer"' in html

    def test_footer_absent_when_predictive_fully_verified(self):
        html = format_predictive_v1_as_html(_predictive_data(unverified=0), language="en")
        assert 'class="ni-methodology-footer"' not in html

    def test_footer_renders_in_danish_for_kemp(self):
        html = format_kemp_v1_as_html(
            _health_data([{"level": "L3_PARTIAL"}]), language="da",
        )
        assert "Baseret på delvist verificeret aktivitetsmatch." in html

    def test_footer_never_says_accurate(self):
        """Same brief §23 rule as TL-7.2's trust panel — a methodology
        caveat is not the place to slip in the forbidden word either."""
        html = format_health_v1_as_html(
            _health_data([{"level": "L2_STRONG_MULTI_FIELD"}]), language="en",
        )
        assert "accura" not in html.lower()

    def test_footer_reuses_the_trust_panels_own_breakdown_not_a_second_signal(self):
        """The footer's condition is read directly off `project_trust`
        (the same dict `_render_project_trust` already built) — not a
        second, independently-computed partial/complete judgement that
        could disagree with the panel a few hundred pixels above it."""
        from src.version_1_0.formatters import _render_methodology_footer

        assert _render_methodology_footer({"project_trust": {"review": 0, "unresolved": 0}}, "en") == ""
        assert _render_methodology_footer({"project_trust": {"review": 1, "unresolved": 0}}, "en") != ""
        assert _render_methodology_footer({"project_trust": {}}, "en") == ""


# ============================================================================
# AC4 — trust indicator on page one
# ============================================================================


class TestTrustIndicatorOnPageOne:
    """The PDF is captured as one tall page (or paginated top-down from
    the same DOM) — being first in the rendered document is what "page
    one" means for this rendering pipeline. Checked by string position,
    not a real PDF page count."""

    def test_trust_panel_precedes_every_table_and_the_footer(self):
        html = format_health_v1_as_html(
            _health_data([{"level": "L2_STRONG_MULTI_FIELD"}]), language="en",
        )
        panel_pos = html.find('class="ni-trust-panel"')
        footer_pos = html.find('class="ni-methodology-footer"')
        table_pos = html.find('class="ni-table"')
        assert panel_pos != -1
        assert panel_pos < table_pos
        assert panel_pos < footer_pos

    def test_trust_panel_precedes_the_kpi_strip(self):
        """The panel renders before `_render_kpis` in `_render_payload` —
        the very first thing after the header, on both dashboards."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        panel_pos = html.find('class="ni-trust-panel"')
        kpi_pos = html.find('class="ni-kpis"')
        assert panel_pos != -1 and kpi_pos != -1
        assert panel_pos < kpi_pos


# ============================================================================
# AC1/AC2 — the PDF-render-time CSS: colour survival + hover fallback
# ============================================================================


class TestPdfFallbackCss:
    def test_color_css_forces_exact_background_printing(self):
        """AC1: without this, Chromium's PDF export can drop background
        colours entirely — trust badges are colour-coded pills, so a
        badge with no background is a badge with no signal."""
        assert "print-color-adjust:exact" in _COLOR_CSS

    def test_why_panels_forced_visible_for_pdf(self):
        """AC2: `.ni-why-panel[hidden]` (TL-7.5) can never be opened by
        a click in a static PDF — the fallback must force it visible."""
        assert ".ni-why-panel[hidden]" in _PDF_TRUST_FALLBACK_CSS
        assert "display:block" in _PDF_TRUST_FALLBACK_CSS

    def test_tooltip_fallback_scoped_to_trust_classes_only(self):
        """AC2, narrowly: a blanket `[title]::after` rule would also
        print the dashboard's non-trust tooltips (e.g. the changed-rows
        expand/collapse button's `title`) as unwanted parenthetical
        text. The fallback must be scoped to the specific trust-layer
        classes that carry a tooltip."""
        # A *blanket* rule would have a bare `[title]` selector starting
        # fresh at a selector boundary (start of string or right after a
        # comma) with no class name in front of it. Every occurrence in
        # the real fallback CSS is scoped (`.ni-trust-badge[title]`
        # etc.) — this only fails if a future edit adds an unscoped one.
        assert re.search(r"(^|,)\s*\[title\]", _PDF_TRUST_FALLBACK_CSS) is None, (
            "fallback CSS must not use a blanket, unscoped [title] selector"
        )
        for selector in (".ni-trust-badge[title]", ".ni-evidence-label[title]", ".ni-trust-summary[title]"):
            assert selector in _PDF_TRUST_FALLBACK_CSS

    def test_tooltip_fallback_renders_the_title_attribute_text(self):
        assert "attr(title)" in _PDF_TRUST_FALLBACK_CSS

    def test_pdf_render_injects_both_stylesheets(self):
        """Source-level check (no real Chromium launch in this suite):
        `_render` must add both `_COLOR_CSS` and `_PDF_TRUST_FALLBACK_CSS`
        via `add_style_tag`, and the trust fallback after the colour
        fix — order doesn't matter for CSS application here, but both
        must actually be wired in, not just defined and unused."""
        import inspect

        source = inspect.getsource(_render)
        assert "add_style_tag(content=_COLOR_CSS)" in source
        assert "add_style_tag(content=_PDF_TRUST_FALLBACK_CSS)" in source


# ============================================================================
# AC5 — verified for both brands
# ============================================================================


class TestBothBrandsCarryTheSameTrustModel:
    def test_kemp_and_nova_health_both_get_the_footer_when_partial(self):
        data = _health_data([{"level": "L4_FUZZY"}])
        nova = format_health_v1_as_html(data, language="en")
        kemp = format_kemp_v1_as_html(data, language="da")
        assert 'class="ni-methodology-footer"' in nova
        assert 'class="ni-methodology-footer"' in kemp

    def test_kemp_and_nova_predictive_both_get_the_footer_when_partial(self):
        data = _predictive_data(unverified=2)
        nova = format_predictive_v1_as_html(data, language="en")
        kemp = format_kemp_predictive_v1_as_html(data, language="da")
        assert 'class="ni-methodology-footer"' in nova
        assert 'class="ni-methodology-footer"' in kemp

    def test_kemp_and_nova_trust_panel_both_precede_their_tables(self):
        data = _health_data([{"level": "L2_STRONG_MULTI_FIELD"}])
        for html in (
            format_health_v1_as_html(data, language="en"),
            format_kemp_v1_as_html(data, language="da"),
        ):
            panel_pos = html.find('class="ni-trust-panel"')
            table_pos = html.find('class="ni-table"')
            assert panel_pos != -1 and table_pos != -1
            assert panel_pos < table_pos
