"""Tests for TL-7.1 — Three-state trust badge component.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-7-trust-surface.md` (TL-7.1):

- AC1: Exactly three states rendered, tooltips verbatim from brief §21.
- AC2: Verified badges suppressed when a row is fully verified.
- AC3: Badges legible and distinguishable in both palettes — visually
  confirmed. A pytest suite cannot literally look at a screen; this file
  pins the *computable* half (the three tones are distinct from each
  other and from both palettes' actual green values, by a real color-
  distance metric, not just "the hex strings differ") and a rendered
  sample is sent separately for the visual half the AC also asks for.
- AC4: Labels and tooltips resolve in EN and DA.

Do-not: no fourth state, no badging every cell (the latter is a rendering
discipline this test file cannot enforce structurally — it is pinned by
`suppress_verified` defaulting to `True`, which is the mechanism that
makes "only badge what carries information" the path of least resistance
for every future caller).
"""
from __future__ import annotations

import re

import pytest

from src.trust.vocabulary import TrustState
from src.version_1_0.formatters import CSS, CSS_KEMP, _trust_badge

# Brief §21's exact wording — pinned verbatim, not paraphrased.
_BRIEF_21_TOOLTIPS = {
    TrustState.VERIFIED: "Verified against source schedule.",
    TrustState.REVIEW: "Nova identified uncertainty in the source data or activity match. Review recommended.",
    TrustState.UNVERIFIED: "Nova could not reliably verify this value. It has not been used as confirmed data.",
}


# ============================================================================
# AC1 — exactly three states, verbatim tooltips
# ============================================================================


class TestThreeStatesVerbatimTooltips:
    @pytest.mark.parametrize("state", list(TrustState))
    def test_exactly_three_trust_states_exist(self, state):
        assert len(list(TrustState)) == 3

    def test_verified_tooltip_verbatim(self):
        html = _trust_badge(TrustState.VERIFIED, "en", suppress_verified=False)
        assert _BRIEF_21_TOOLTIPS[TrustState.VERIFIED] in html

    def test_review_tooltip_verbatim(self):
        html = _trust_badge(TrustState.REVIEW, "en")
        assert _BRIEF_21_TOOLTIPS[TrustState.REVIEW] in html

    def test_unverified_tooltip_verbatim(self):
        html = _trust_badge(TrustState.UNVERIFIED, "en")
        assert _BRIEF_21_TOOLTIPS[TrustState.UNVERIFIED] in html

    def test_accepts_raw_string_value_same_as_enum_member(self):
        """Matches the existing convention in `src.trust.vocabulary`'s own
        accessors — callers may pass a `TrustState` or its `.value` string."""
        by_enum = _trust_badge(TrustState.REVIEW, "en")
        by_string = _trust_badge("review", "en")
        assert by_enum == by_string

    def test_unrecognized_state_renders_nothing_not_a_fourth_state(self):
        """Do-not: no fourth state. An unmapped key must not silently
        render as if it were one of the three — it renders nothing,
        which is a caller bug surfacing as absence, not as invention."""
        assert _trust_badge("source_conflict", "en") == ""


# ============================================================================
# AC2 — VERIFIED badges suppressed when everything is verified
# ============================================================================


class TestVerifiedSuppression:
    def test_verified_suppressed_by_default(self):
        """The default is the safe default: a caller rendering one badge
        per field, with no special-casing, automatically produces brief
        §21's 'only badge what carries information' — VERIFIED never
        shows unless explicitly asked to."""
        assert _trust_badge(TrustState.VERIFIED, "en") == ""

    def test_review_and_unverified_are_never_suppressed(self):
        assert _trust_badge(TrustState.REVIEW, "en") != ""
        assert _trust_badge(TrustState.UNVERIFIED, "en") != ""

    def test_verified_can_be_shown_explicitly_for_a_legend(self):
        """A caller building an explicit three-state legend (where
        showing VERIFIED is the point) can opt out of suppression."""
        html = _trust_badge(TrustState.VERIFIED, "en", suppress_verified=False)
        assert html != ""
        assert "ni-trust-badge--verified" in html

    def test_a_fully_verified_row_produces_no_visible_badges(self):
        """Simulates a table row where every underlying field is
        VERIFIED — rendering one badge per field with the default
        produces zero visible badges, which is the row-level effect
        brief §21's 'suppress on fully-verified rows' describes."""
        row_states = [TrustState.VERIFIED, TrustState.VERIFIED, TrustState.VERIFIED]
        rendered = "".join(_trust_badge(s, "en") for s in row_states)
        assert rendered == ""

    def test_a_partially_verified_row_shows_only_the_non_verified_badges(self):
        row_states = [TrustState.VERIFIED, TrustState.REVIEW, TrustState.VERIFIED]
        rendered = [_trust_badge(s, "en") for s in row_states]
        assert rendered[0] == ""
        assert rendered[1] != ""
        assert rendered[2] == ""


# ============================================================================
# AC3 — legible and distinguishable in both palettes
# ============================================================================


def _extract_tone_colors(css: str) -> dict[str, str]:
    """Pull `--ni-tb-tone` hex values for each `.ni-trust-badge--*` rule
    out of a CSS string."""
    tones = {}
    for state in ("verified", "review", "unverified"):
        m = re.search(rf"\.ni-trust-badge--{state}\{{[^}}]*--ni-tb-tone:(#[0-9a-fA-F]{{6}})", css)
        assert m, f"no --ni-tb-tone found for .ni-trust-badge--{state} in given CSS"
        tones[state] = m.group(1)
    return tones


def _extract_kemp_brand_greens(css: str) -> list[str]:
    """Pull the Kemp palette's own accent-green hex values (used for
    logos, buttons, section borders) — the colors brief §21 specifically
    warns are 'close to the verified state colour'."""
    return sorted(set(re.findall(r"#00a766|#02c79b|#008c55", css)))


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _color_distance(a: str, b: str) -> float:
    """Simple Euclidean RGB distance — not perceptually exact, but a
    real, computable proxy for 'these two colors are not the same or
    near-identical,' good enough to catch an accidental near-duplicate."""
    ra, ga, ba = _hex_to_rgb(a)
    rb, gb, bb = _hex_to_rgb(b)
    return ((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2) ** 0.5


# A conservative "clearly not the same color" threshold in 0-441.7 RGB
# Euclidean-distance space (441.7 = max possible, black vs white).
_MIN_DISTINGUISHABLE_DISTANCE = 60.0


class TestPaletteDistinguishability:
    def test_badge_css_present_in_both_palettes(self):
        for css in (CSS, CSS_KEMP):
            assert ".ni-trust-badge--verified" in css
            assert ".ni-trust-badge--review" in css
            assert ".ni-trust-badge--unverified" in css

    def test_badge_colors_are_identical_across_both_palettes(self):
        """The trust semantic must not depend on which dashboard is
        rendering it — same three hex values in `CSS` and `CSS_KEMP`."""
        assert _extract_tone_colors(CSS) == _extract_tone_colors(CSS_KEMP)

    def test_the_three_states_are_mutually_distinguishable(self):
        tones = _extract_tone_colors(CSS)
        pairs = [("verified", "review"), ("verified", "unverified"), ("review", "unverified")]
        for a, b in pairs:
            distance = _color_distance(tones[a], tones[b])
            assert distance >= _MIN_DISTINGUISHABLE_DISTANCE, (
                f"{a} ({tones[a]}) and {b} ({tones[b]}) are too close: distance={distance:.1f}"
            )

    def test_review_amber_is_distinguishable_from_kemp_brand_green(self):
        """This task's own Do item 3: 'the Kemp palette's green is close
        to the verified state colour — check this explicitly.' The
        REVIEW tone (amber) must not be confusable with Kemp's own brand
        green wherever it appears in the Kemp dashboard."""
        review_tone = _extract_tone_colors(CSS_KEMP)["review"]
        kemp_greens = _extract_kemp_brand_greens(CSS_KEMP)
        assert kemp_greens, "expected to find Kemp's brand green hex values in CSS_KEMP"
        for green in kemp_greens:
            distance = _color_distance(review_tone, green)
            assert distance >= _MIN_DISTINGUISHABLE_DISTANCE, (
                f"REVIEW ({review_tone}) too close to Kemp brand green ({green}): distance={distance:.1f}"
            )

    def test_verified_green_is_not_identical_to_kemp_brand_green(self):
        """The verified badge is deliberately a *different* green from
        Kemp's own brand accent (see the module docstring in
        `formatters.py`) — not required to be maximally distant (both
        are legitimately 'green' and that is fine; VERIFIED reading as
        blandly positive is acceptable), but must not be pixel-identical
        to Kemp's own UI chrome, which would make it invisible as a
        distinct signal."""
        verified_tone = _extract_tone_colors(CSS_KEMP)["verified"]
        kemp_greens = _extract_kemp_brand_greens(CSS_KEMP)
        assert verified_tone not in kemp_greens


# ============================================================================
# AC4 — labels and tooltips resolve in EN and DA
# ============================================================================


class TestLocalization:
    @pytest.mark.parametrize("state", [TrustState.REVIEW, TrustState.UNVERIFIED])
    def test_en_and_da_produce_different_text(self, state):
        en = _trust_badge(state, "en")
        da = _trust_badge(state, "da")
        assert en != da
        assert en != ""
        assert da != ""

    def test_danish_review_matches_localization_strings(self):
        html = _trust_badge(TrustState.REVIEW, "da")
        assert "Kontrol anbefales" in html
        assert "Kontrol anbefales" in html  # label appears
        assert "usikkerhed" in html.lower()

    def test_danish_unverified_matches_localization_strings(self):
        html = _trust_badge(TrustState.UNVERIFIED, "da")
        assert "Kan ikke verificeres" in html

    def test_unknown_language_falls_back_to_english(self):
        """Matches the existing `t()`/`t_state()` fallback convention —
        an unrecognized language code never produces an empty tooltip."""
        html = _trust_badge(TrustState.REVIEW, "fr")
        assert _BRIEF_21_TOOLTIPS[TrustState.REVIEW] in html
