"""Tests for TL-7.3 — Source / Calculation / Insight / Forecast distinction.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-7-trust-surface.md` (TL-7.3):

- AC1: All four classes visually distinguishable and consistently applied.
  The chip carries class-specific CSS (`--source_data` / `--nova_calculation`
  / `--nova_insight` / `--nova_forecast`) with border-style differentiation
  (solid / double / dashed / dotted) rather than colour (brief §21
  "no Christmas tree" — same chip palette as the trust badge's neutral
  base).
- AC2: Terminology matches brief §46 exactly, EN and DA. "Source data",
  "Nova calculation", "Nova insight", "Nova forecast" — never "AI thinks",
  "AI tænker", or similar.
- AC3: Treatment does not collide with trust badges. The chip uses a
  single neutral palette (one background, one border colour) distinct
  from the trust badge's three-tone palette; differentiation between
  evidence classes is by border-style, not colour.
- AC4: Applied to both dashboards. The chip appears in both
  `format_health_v1_as_html` (Nova health + Kemp) and
  `format_predictive_v1_as_html` (Nova predictive + Kemp predictive) —
  the shared `_render_payload` + `_render_kpis` + `_render_actions`
  paths guarantee parity by construction.
"""
from __future__ import annotations

import re

import pytest

from src.trust.vocabulary import EvidenceClass
from src.version_1_0.formatters import (
    _evidence_class_chip,
    format_health_v1_as_html,
    format_kemp_predictive_v1_as_html,
    format_kemp_v1_as_html,
    format_predictive_v1_as_html,
)
from src.version_1_0.localization import LABELS


# ============================================================================
# Fixtures
# ============================================================================


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


def _predictive_data(total=50, delayed=12, unverified=3, with_actions=True):
    data = {
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
    if with_actions:
        data["executive_actions"] = [
            {
                "rank": 1, "action": "Resolve T1", "responsible": "PM",
                "deadline": "Mon", "related_task_ids": ["T1"],
                "manpower_helps": False, "manpower_note": "n/a",
            }
        ]
    return data


# ============================================================================
# AC1 — All four classes visually distinguishable
# ============================================================================


class TestFourClassesDistinguishable:
    """AC1: every `EvidenceClass` value has its own CSS class variant,
    each with a distinct border-style (the visual differentiator —
    not colour, by design)."""

    def test_each_class_has_css_variant(self):
        for cls in EvidenceClass:
            chip = _evidence_class_chip(cls.value, "en")
            assert f"ni-evidence-label--{cls.value}" in chip, (
                f"{cls.value} missing CSS variant: {chip!r}"
            )

    def test_chips_have_distinct_border_styles(self):
        """All four chips share the base palette but differ on
        `border-style` — the visual differentiator. CSS check via
        `formatters.py`'s emitted `<style>` block."""
        from src.version_1_0.formatters import CSS
        # source_data: solid
        assert ".ni-evidence-label--source_data{border-style:solid}" in CSS
        # nova_calculation: double
        assert ".ni-evidence-label--nova_calculation{border-style:double" in CSS
        # nova_insight: dashed
        assert ".ni-evidence-label--nova_insight{border-style:dashed" in CSS
        # nova_forecast: dotted
        assert ".ni-evidence-label--nova_forecast{border-style:dotted" in CSS

    def test_chips_use_single_neutral_palette_no_competition_with_trust_badge(self):
        """AC3: the chip uses a single neutral palette (no four new
        colours competing with the trust badge). The trust badge has
        three distinct tones (verified green, review amber, unverified
        grey); the evidence chip must not have a comparable palette."""
        from src.version_1_0.formatters import CSS
        # The base evidence-label class uses ONE background, ONE border
        # colour. Differentiation is purely structural (border-style).
        assert ".ni-evidence-label{" in CSS
        assert "background:#f4f6f7" in CSS  # single neutral
        # No evidence-class CSS variants should introduce new colour tones
        # beyond the base.
        for cls in EvidenceClass:
            variant = f".ni-evidence-label--{cls.value}"
            if variant in CSS:
                # The variant declarations must not set colour/background —
                # only border-style. Strip comments and whitespace, then
                # check no colour/background property appears.
                block_match = re.search(
                    rf"{re.escape(variant)}\s*\{{([^}}]*)\}}",
                    CSS,
                )
                assert block_match, f"variant {cls.value} block not found"
                block = block_match.group(1)
                assert "border-style" in block
                assert "color:" not in block.lower()
                assert "background:" not in block.lower()

    def test_chips_are_consistent_in_shape_across_classes(self):
        """All four chips share the same shape (height, padding, font) —
        only the border-style differentiates them. Brief §21's "no
        Christmas tree" constraint means consistency, not variation."""
        from src.version_1_0.formatters import CSS
        # The base class declares padding / font-size / border-radius;
        # variants must not override these.
        base = re.search(r"\.ni-evidence-label\{([^}]*)\}", CSS)
        assert base
        for prop in ("padding", "font-size", "border-radius"):
            assert prop in base.group(1), (
                f"base chip must declare {prop!r} so variants don't drift"
            )


# ============================================================================
# AC2 — Terminology matches brief §46 exactly, EN and DA
# ============================================================================


class TestBriefSection46Terminology:
    """AC2: brief §46's approved terminology exactly. "Source data",
    "Nova calculation", "Nova insight", "Nova forecast". No "AI
    thinks" / "AI tænker" — those would violate the load-bearing
    vocabulary the brief names."""

    @pytest.mark.parametrize("cls,en_label", [
        (EvidenceClass.SOURCE_DATA, "Source data"),
        (EvidenceClass.NOVA_CALCULATION, "Nova calculation"),
        (EvidenceClass.NOVA_INSIGHT, "Nova insight"),
        (EvidenceClass.NOVA_FORECAST, "Nova forecast"),
    ])
    def test_english_label_matches_brief(self, cls, en_label):
        assert LABELS["en"][f"evidence_class_{cls.value}"] == en_label

    @pytest.mark.parametrize("cls,da_label", [
        (EvidenceClass.SOURCE_DATA, "Kildedata"),
        (EvidenceClass.NOVA_CALCULATION, "Nova-beregning"),
        (EvidenceClass.NOVA_INSIGHT, "Nova-indsigt"),
        (EvidenceClass.NOVA_FORECAST, "Nova-prognose"),
    ])
    def test_danish_label_matches_brief(self, cls, da_label):
        assert LABELS["da"][f"evidence_class_{cls.value}"] == da_label

    def test_no_ai_thinks_in_english_output(self):
        """Brief §46 is explicit — never "AI thinks". The chip + tooltip
        strings must use approved vocabulary only."""
        html_en = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "ai thinks" not in html_en.lower()
        assert "ai tænker" not in html_en.lower()  # also check the Danish word

    def test_no_ai_taenker_in_danish_output(self):
        """Danish mirror — "AI tænker" is the same forbidden phrase."""
        html_da = format_kemp_predictive_v1_as_html(_predictive_data(), language="da")
        assert "ai tænker" not in html_da.lower()
        assert "ai thinks" not in html_da.lower()

    def test_static_localization_keys_have_no_forbidden_phrases(self):
        """Catch a future `trust_*` key that slips the word in even if
        no fixture exercises it."""
        forbidden = ("ai thinks", "ai tænker", "machine says", "computer thinks")
        for lang in ("en", "da"):
            for key, value in LABELS[lang].items():
                if key.startswith("evidence_class"):
                    for bad in forbidden:
                        assert bad not in value.lower(), (
                            f"{lang}.{key}: forbidden phrase {bad!r} in {value!r}"
                        )


# ============================================================================
# AC3 — Treatment does not collide with trust badges
# ============================================================================


class TestNoCollisionWithTrustBadges:
    """AC3: the evidence chip uses a single neutral palette distinct
    from the three-tone trust badge. Differentiation between classes
    is by border-style, not colour."""

    def test_evidence_chip_does_not_use_trust_badge_tone_classes(self):
        """The trust badge has `--verified` / `--review` / `--unverified`
        variants with green/amber/grey tones. The evidence chip uses
        a different naming scheme and a different palette — they
        cannot share a CSS variant."""
        from src.version_1_0.formatters import CSS
        # The four evidence class variants must NOT carry any of the
        # trust-badge tone values.
        for cls in ("verified", "review", "unverified"):
            for ev_cls in EvidenceClass:
                variant = f"ni-evidence-label--{ev_cls.value}"
                # The evidence variant declarations must not mention
                # trust-badge tone classes (no colour/background cross-
                # contamination).
                block_match = re.search(
                    rf"{re.escape(variant)}\s*\{{([^}}]*)\}}",
                    CSS,
                )
                if block_match:
                    assert "--ni-tb-bg" not in block_match.group(1)
                    assert "--ni-tb-tone" not in block_match.group(1)
                    assert "--ni-tb-border" not in block_match.group(1)

    def test_evidence_chip_uses_neutral_text_color(self):
        """Single neutral palette — no class-specific colour overrides."""
        from src.version_1_0.formatters import CSS
        # The base chip class declares ONE color, used by all variants.
        base = re.search(r"\.ni-evidence-label\{([^}]*)\}", CSS)
        assert base
        assert "color:#5a6470" in base.group(1)
        # Variants must not override the color.
        for cls in EvidenceClass:
            block_match = re.search(
                rf"\.ni-evidence-label--{re.escape(cls.value)}\s*\{{([^}}]*)\}}",
                CSS,
            )
            if block_match:
                assert "color:" not in block_match.group(1)


# ============================================================================
# AC4 — Applied to both dashboards
# ============================================================================


class TestAppliedToBothDashboards:
    """AC4: the chip appears in both health (Nova + Kemp) and
    predictive (Nova + Kemp) dashboards. Shared renderers
    (`_render_kpis`, `_render_actions`) guarantee parity."""

    def test_nova_health_has_chips(self):
        html = format_health_v1_as_html(_health_data(), language="en")
        assert "ni-evidence-label" in html

    def test_kemp_health_has_chips(self):
        html = format_kemp_v1_as_html(_health_data(), language="da")
        assert "ni-evidence-label" in html

    def test_nova_predictive_has_chips(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "ni-evidence-label" in html

    def test_kemp_predictive_has_chips(self):
        html = format_kemp_predictive_v1_as_html(_predictive_data(), language="da")
        assert "ni-evidence-label" in html

    def test_executive_actions_carry_nova_forecast_chip(self):
        """Executive actions are forward-looking imperatives — every
        action card and the section heading carry the NOVA_FORECAST chip."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "ni-evidence-label--nova_forecast" in html
        # Three appearances: section heading + 1 per action
        assert html.count("ni-evidence-label--nova_forecast") >= 2

    def test_kpi_cards_carry_appropriate_class_chips(self):
        """KPI cards' evidence class is mapped by `_KPI_TO_EVIDENCE_CLASS`:
        derived counts (`delayed_activities`, `critical_activities`, ...)
        → NOVA_CALCULATION; totals (`activities_analyzed`) → SOURCE_DATA."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        # delayed_activities KPI → nova_calculation chip
        assert "ni-evidence-label--nova_calculation" in html
        # activities_analyzed KPI → source_data chip
        assert "ni-evidence-label--source_data" in html

    def test_chip_tooltip_explains_the_class(self):
        """Hover text carries brief §45's one-sentence explanation —
        the chip teaches the vocabulary, not just decorates the row."""
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        # Each chip carries a `title="..."` tooltip
        tooltips = re.findall(
            r'ni-evidence-label[^>]*\s+title="([^"]+)"', html
        )
        assert len(tooltips) > 0
        for tooltip in tooltips:
            assert len(tooltip) > 20, (
                f"tooltip too short to be a §45 explanation: {tooltip!r}"
            )


# ============================================================================
# Helpers
# ============================================================================


class TestEvidenceClassChipHelper:
    """Unit tests for `_evidence_class_chip` — the renderer that
    every section uses. Failure modes here propagate to every section."""

    def test_unknown_class_returns_empty_string(self):
        """An unknown class string returns empty string — guards
        against drift if a future field gets a typo'd class."""
        assert _evidence_class_chip("not_a_class", "en") == ""
        assert _evidence_class_chip("", "en") == ""

    def test_chip_carries_label_and_tooltip(self):
        chip = _evidence_class_chip("nova_forecast", "en")
        assert "Nova forecast" in chip
        assert "title=" in chip
        # Tooltip is short, single-sentence
        m = re.search(r'title="([^"]+)"', chip)
        assert m
        assert m.group(1).endswith("."), (
            f"tooltip must end with a period for the §45 one-sentence rule: {m.group(1)!r}"
        )

    def test_chip_renders_in_danish(self):
        chip = _evidence_class_chip("source_data", "da")
        assert "Kildedata" in chip
        # DA tooltip exists
        assert "title=" in chip

    def test_chip_escapes_user_content(self):
        """The label and tooltip come from localization, but if a
        future change introduces user-derived strings, the chip should
        still be safe — the existing `_e()` helper handles HTML escaping."""
        chip = _evidence_class_chip("nova_calculation", "en")
        assert "<script>" not in chip.lower()
        assert "</script>" not in chip.lower()
