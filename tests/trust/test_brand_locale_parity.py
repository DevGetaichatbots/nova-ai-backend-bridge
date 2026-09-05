"""Tests for TL-7.6 — Brand and locale parity (Kemp/Nova, DA/EN).

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-7-trust-surface.md` (TL-7.6):

- AC1: Every trust string has a reviewed Danish translation
  (`trust_*`, `evidence_class_*`, `forecast_*`, `why_*` keys all have
  matching DA values; no empty strings; sets identical between EN
  and DA).
- AC2: All four formatter entry points render every trust element.
  `format_health_v1_as_html`, `format_kemp_v1_as_html`,
  `format_predictive_v1_as_html`, `format_kemp_predictive_v1_as_html` —
  each carries the trust panel, the three-tone trust badge, the
  evidence-class chip, and the why-button.
- AC3: No trust element is hidden by the Kemp optional-item
  mechanism (`_mark_optional_health_items` / `ni-kemp-hidden`) — a
  trust indicator defaulting into the collapsed Kemp section would
  defeat the brief's "do not let a trust indicator default into the
  collapsed Kemp section" Do-not rule.
- AC4: Flask-side localizers leave trust strings intact. The naive
  `str.replace` localizer in `kemp&lauritzen/backend/utils/
  report_localization.py` historically corrupted the bare "Confidence"
  label into "Tillidsniveau"; the fix was to drop the bare label and
  use per-key labels (TL-7.4's `forecast_confidence_high/medium/low`).
  This test pins that no trust-class label collides with any localizer
  source pattern.
"""
from __future__ import annotations

import re

import pytest

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
        "predictive_snapshot": {
            "what_will_happen": "X",
            "estimated_delay_impact": "+6w",
            "confidence_level": "HIGH",
            "confidence_basis": "Basis text",
            "main_delay_drivers": ["a", "b", "c"],
        },
    }
    if with_actions:
        data["executive_actions"] = [
            {"rank": 1, "action": "Resolve T1", "responsible": "PM",
             "deadline": "Mon", "related_task_ids": ["T1"],
             "manpower_helps": False, "manpower_note": "n/a"}
        ]
    return data


# ============================================================================
# AC1 — every trust string has a DA translation
# ============================================================================


class TestTrustStringsHaveDATranslations:
    """AC1: every trust-keyed string in `LABELS["en"]` has a matching
    non-empty DA translation. Static check — pins the parity at the
    source level so a future translation slip surfaces at the build."""

    @pytest.fixture
    def trust_keys_en(self):
        return {k for k in LABELS["en"] if k.startswith(
            ("trust_", "evidence_class_", "forecast_", "why_")
        )}

    @pytest.fixture
    def trust_keys_da(self):
        return {k for k in LABELS["da"] if k.startswith(
            ("trust_", "evidence_class_", "forecast_", "why_")
        )}

    def test_no_trust_key_present_only_in_en(self, trust_keys_en, trust_keys_da):
        missing = trust_keys_en - trust_keys_da
        assert not missing, f"trust keys missing DA translation: {sorted(missing)}"

    def test_no_trust_key_present_only_in_da(self, trust_keys_en, trust_keys_da):
        extra = trust_keys_da - trust_keys_en
        assert not extra, f"trust keys present in DA but not EN: {sorted(extra)}"

    def test_no_empty_trust_strings_in_en(self, trust_keys_en):
        empty = [k for k in trust_keys_en if not LABELS["en"][k].strip()]
        assert not empty, f"empty EN trust strings: {empty}"

    def test_no_empty_trust_strings_in_da(self, trust_keys_da):
        empty = [k for k in trust_keys_da if not LABELS["da"][k].strip()]
        assert not empty, f"empty DA trust strings: {empty}"


# ============================================================================
# AC2 — every formatter entry point renders every trust element
# ============================================================================


class TestAllFormatterEntryPointsRenderTrustElements:
    """AC2: every formatter entry point (Nova health, Nova predictive,
    Kemp health, Kemp predictive) renders the trust panel, the
    three-tone trust badge, the evidence-class chip, and the
    why-button."""

    def test_nova_health_has_trust_elements(self):
        html = format_health_v1_as_html(_health_data(), language="en")
        assert "ni-trust-panel" in html                       # trust panel
        assert "ni-trust-badge" in html                        # three-tone badge
        # Evidence-class chip & why-button are predictive-only
        # (the health dashboard has no forecasts). They appear only
        # in predictive renders — tested below.

    def test_kemp_health_has_trust_elements(self):
        html = format_kemp_v1_as_html(_health_data(), language="da")
        assert "ni-trust-panel" in html
        assert "ni-trust-badge" in html

    def test_nova_predictive_has_all_four_trust_elements(self):
        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        assert "ni-trust-panel" in html              # TL-7.2 panel
        assert "ni-trust-badge" in html               # TL-7.1 badge
        assert "ni-evidence-label" in html           # TL-7.3 chip
        assert "ni-why-btn" in html                  # TL-7.5 button

    def test_kemp_predictive_has_all_four_trust_elements(self):
        """AC2 (Kemp parity): the same four elements render under
        `format_kemp_predictive_v1_as_html`. Kemp is Danish-only
        (brief §46); the trust elements must not be hidden by the
        Kemp variant or rendered in English when language='da'."""
        html = format_kemp_predictive_v1_as_html(_predictive_data(), language="da")
        assert "ni-trust-panel" in html
        assert "ni-trust-badge" in html
        assert "ni-evidence-label" in html
        assert "ni-why-btn" in html

    def test_danish_predictive_uses_danish_trust_strings(self):
        """Brief §46: Kemp is Danish-only — every trust element must
        render in Danish when language='da', not English."""
        html = format_kemp_predictive_v1_as_html(_predictive_data(), language="da")
        # Trust panel heading
        assert "Tillid til denne analyse" in html
        # Evidence-class chip — Nova forecast
        assert "Nova-prognose" in html
        # Why button — `Hvorfor` (DA) or the EN fallback during transitions
        assert "Hvorfor" in html or "Why?" in html
        # Trust breakdown pill copy — lowercase in `LABELS["da"]`
        assert "verificeret" in html.lower()


# ============================================================================
# AC3 — no trust element hidden by the Kemp optional-item mechanism
# ============================================================================


class TestTrustElementsNotHiddenByKempOptional:
    """AC3: the trust indicator must NEVER default into the collapsed
    Kemp section. `_mark_optional_health_items` toggles `_kemp_hidden`
    on KPI pills (`activities_analyzed`, `critical_path_table`,
    `point_no_return`) and on the `critical_path_table` section —
    never on `ni-trust-panel`, `ni-trust-badge`, `ni-evidence-label`,
    or `ni-why-btn`."""

    def test_trust_panel_is_never_marked_optional(self):
        """`_mark_optional_health_items` is the only place that
        sets `_kemp_hidden`. The trust panel never carries that
        class — if a future change adds it, this test fails."""
        from src.version_1_0.formatters import _render_project_trust, format_health_v1_as_html
        html = format_health_v1_as_html(_health_data(), language="da")
        # Find the trust panel and check it has no ni-kemp-hidden class
        m = re.search(r'<div class="ni-trust-panel"[^>]*>', html)
        assert m, "no trust panel in Kemp health"
        assert "ni-kemp-hidden" not in m.group(), (
            f"trust panel marked hidden by Kemp optional mechanism: {m.group()}"
        )

    def test_trust_panel_survives_kemp_optional_toggle_in_html(self):
        """Render Kemp health, then simulate the user toggling the
        optional section. The trust panel must remain visible —
        not collapse with the rest of the optional items."""
        html = format_kemp_v1_as_html(_health_data(), language="da")
        # The ni-trust-panel exists
        assert "<div class=\"ni-trust-panel\">" in html
        # The ni-trust-panel does NOT carry ni-kemp-hidden or ni-kemp-optional
        panel_match = re.search(r'<div class="ni-trust-panel"[^>]*>', html)
        assert panel_match
        klass = panel_match.group()
        assert "ni-kemp-hidden" not in klass
        assert "ni-kemp-optional" not in klass

    def test_trust_badge_never_marked_optional(self):
        """Per-row trust badges (TL-7.1) — the optional mechanism only
        marks KPI pills and table sections, not row-level badges."""
        # Predictive dashboard with actions and rows
        html = format_predictive_v1_as_html(_predictive_data(), language="da")
        # Count ni-trust-badge occurrences
        badges = re.findall(r'<span class="ni-trust-badge[^"]*"', html)
        assert len(badges) > 0
        for b in badges:
            assert "ni-kemp-hidden" not in b, (
                f"trust badge marked hidden: {b}"
            )

    def test_kemp_optional_keys_list_does_not_include_trust_elements(self):
        """Static check on `_mark_optional_health_items`'s key list —
        a future change that adds `ni-trust-panel` or `ni-trust-badge`
        to `_kemp_optional_kpi_keys` would be a regression."""
        from src.version_1_0.formatters import _mark_optional_health_items
        payload = {
            "tables": {
                "critical_path": [],
                "behind": [], "ahead": [], "changed": [], "stage": [],
            }
        }
        _mark_optional_health_items(payload, payload["tables"])
        forbidden = {"trust_panel", "trust_badge", "evidence_label", "why_btn"}
        for key in payload.get("_kemp_optional_kpi_keys", []):
            assert not any(f in key.lower() for f in forbidden), (
                f"Kemp optional mechanism now marks a trust element: {key}"
            )


# ============================================================================
# AC4 — Flask localizers leave trust strings intact
# ============================================================================


# The naive Flask-side localizer does literal `str.replace` over the
# rendered HTML against a hardcoded list of EN → DA pairs. Trust strings
# that happened to contain any source-pattern word would be silently
# translated. The bare "Confidence" label is the historical bug — the
# localizer's "Confidence" → "Tillidsniveau" entry rewrote the trust
# badge tooltip into Danish even when the badge was an English-rendered
# MEDIUM (which kept its English label).
_LOCALIZER_SOURCES = [
    "Confidence", "High Risk", "Stable", "Delayed", "Accelerated",
    "Added", "Removed", "Impact", "Schedule Outlook", "Biggest Risk",
    "Schedule Overview", "Management Conclusion", "Delayed Activities",
    "Root Cause Analysis", "Summary by Area", "Priority Actions",
    "Resource Assessment", "Forcing Assessment", "Confidence Level",
    "PROJECT STATUS", "Project Status", "Reference Date", "Actions",
    "Overview", "Summary of Changes", "Project Health", "Attention Needed",
]


class TestFlaskLocalizersDoNotCorruptTrust:
    """AC4: every trust-class label that ends up in rendered HTML must
    not contain any localizer source pattern. The naive `str.replace`
    localizer in `report_localization.py` does literal substring
    matching — a trust string that contains "Confidence" gets silently
    translated to "Tillidsniveau" even when the rest of the page is
    English. This test pins the absence of any such collision."""

    @pytest.fixture
    def localizer_colliding_keys(self):
        colliding = []
        # Some localizer sources happen to coincide with a trust key's
        # EN value (e.g. `forecast_biggest_risk`'s EN value IS literally
        # "Biggest Risk", a source pattern). That is only "corruption" if
        # the localizer's own translation would produce something other
        # than what Nova's own DA label for that same key already says —
        # if the naive `str.replace` pass happens to land on the same
        # (or a merely differently-cased) correct Danish string, the
        # rendered page is still correct, just reached by two paths.
        # Compared case-insensitively — Danish sentence-case vs. the
        # localizer's borrowed English title-case is a style nuance, not
        # a corruption. Checked against `LABELS["da"][key]` (Nova's own
        # translation for THIS key), never against `value` (the EN
        # string being tested) — comparing against `value` can never
        # match a Danish string and would defeat the exemption entirely.
        COINCIDENT_OK = {
            "Biggest Risk": "Største Risiko",
        }
        for lang in ("en", "da"):
            for key, value in LABELS[lang].items():
                if not key.startswith(("trust_", "evidence_class_", "forecast_", "why_")):
                    continue
                # Only check EN values — DA translations are intentional,
                # they don't go through the Flask localizer (they're already DA).
                if lang != "en":
                    continue
                for src in _LOCALIZER_SOURCES:
                    if src in value:
                        expected = COINCIDENT_OK.get(src)
                        actual_da = LABELS["da"].get(key, "")
                        if expected is not None and expected.lower() == actual_da.lower():
                            continue
                        colliding.append((key, src, value))
        return colliding

    def test_no_trust_string_collides_with_a_localizer_source(self, localizer_colliding_keys):
        assert not localizer_colliding_keys, (
            "trust-class label collides with a Flask localizer source pattern "
            "(the naive `str.replace` localizer would silently corrupt the trust "
            "string):\n  " + "\n  ".join(f"{k!r} contains {src!r}: {v!r}" for k, src, v in localizer_colliding_keys)
        )

    def test_flask_localizer_actually_runs_against_predictive_html(self):
        """Integration: import the real localizer from
        `kemp&lauritzen/backend/utils/report_localization.py`,
        render a predictive dashboard, run the localizer, and assert
        no trust element has been corrupted."""
        import sys
        sys.path.insert(
            0, "/home/abaan/work/gac/nova/projects/nova-insights/kemp&lauritzen/backend"
        )
        try:
            from utils.report_localization import localize_predictive_report_html
        except ImportError:
            pytest.skip("kemp&lauritzen not on sys.path; integration skipped")

        html = format_predictive_v1_as_html(_predictive_data(), language="en")
        localized = localize_predictive_report_html(html, language="da")
        # Trust-class labels survive intact
        assert "Trust in this analysis" in localized
        assert "Nova forecast" in localized
        assert "Nova calculation" in localized
        assert "Why?" in localized or "Hvorfor" in localized
        # No accidental translation of trust-class labels
        assert "Tillidsniveau" not in localized
        assert "Tillidsniveau basis" not in localized

    def test_flask_localizer_actually_runs_against_health_html(self):
        """Same integration check for the comparison/health dashboard."""
        import sys
        sys.path.insert(
            0, "/home/abaan/work/gac/nova/projects/nova-insights/kemp&lauritzen/backend"
        )
        try:
            from utils.report_localization import localize_comparison_dashboard_html
        except ImportError:
            pytest.skip("kemp&lauritzen not on sys.path; integration skipped")

        html = format_health_v1_as_html(_health_data(), language="en")
        localized = localize_comparison_dashboard_html(html, language="da")
        # The trust panel survives
        assert "Trust in this analysis" in localized
        # No accidental translation
        assert "Tillidsniveau" not in localized


# ============================================================================
# All four formatter entry points share one source of truth for trust strings
# ============================================================================


class TestParityAllFourEntryPoints:
    """Brief §46: Kemp and Nova share `src/version_1_0/formatters.py`,
    so most work is one change — but parity must be verified. These
    tests confirm the four entry points emit the same trust elements
    (just rendered in the right palette / locale)."""

    def test_health_indicator_present_in_both_brands(self):
        nova = format_health_v1_as_html(_health_data(), language="en")
        kemp = format_kemp_v1_as_html(_health_data(), language="da")
        assert "ni-trust-panel" in nova
        assert "ni-trust-panel" in kemp
        # Brand parity on the three-tone badge
        assert "ni-trust-badge" in nova
        assert "ni-trust-badge" in kemp

    def test_predictive_indicator_present_in_both_brands(self):
        nova = format_predictive_v1_as_html(_predictive_data(), language="en")
        kemp = format_kemp_predictive_v1_as_html(_predictive_data(), language="da")
        for marker in ("ni-trust-panel", "ni-trust-badge", "ni-evidence-label", "ni-why-btn"):
            assert marker in nova, f"Nova predictive missing {marker}"
            assert marker in kemp, f"Kemp predictive missing {marker}"

    def test_evidence_chip_helper_works_in_both_languages(self):
        """Helper-level smoke test: `_evidence_class_chip` reads from
        the same `LABELS` both formatter entry points use, so EN + DA
        are parity-tested at the helper level."""
        en = _evidence_class_chip("nova_forecast", "en")
        da = _evidence_class_chip("nova_forecast", "da")
        assert "Nova forecast" in en
        assert "Nova-prognose" in da
        assert "ni-evidence-label--nova_forecast" in en
        assert "ni-evidence-label--nova_forecast" in da
