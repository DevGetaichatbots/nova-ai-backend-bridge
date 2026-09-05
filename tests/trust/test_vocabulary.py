"""Tests for the canonical trust vocabulary (TL-0.4).

Encodes every acceptance criterion from
`changes/trust-layer/plan/phase-0-safety-net.md` as a pytest, plus the
discipline tests that future trust-layer phases depend on (prefix audit,
string round-trip, enum/string tolerance in the accessors).
"""
from __future__ import annotations

import pytest

from src.trust import (
    ClaimKind,
    EvidenceClass,
    SOURCE_CONFLICT_FLAG,
    TrustState,
    claim_label,
    claim_tooltip,
    conflict_label,
    conflict_tooltip,
    evidence_label,
    evidence_tooltip,
    trust_label,
    trust_tooltip,
)
from src.version_1_0.localization import (
    LABELS,
    t_claim,
    t_conflict,
    t_evidence,
    t_state,
)


# The set of keys TL-0.4 added to LABELS. Asserted against in the prefix
# discipline test, and used to generate per-key DA presence checks.
TRUST_PREFIX = "trust_"
TRUST_KEYS_EN: list[str] = [
    # state labels + tooltips
    "trust_state_verified", "trust_state_verified_tt",
    "trust_state_review", "trust_state_review_tt",
    "trust_state_unverified", "trust_state_unverified_tt",
    # conflict flag
    "trust_source_conflict", "trust_source_conflict_tt",
    # claim kinds
    "trust_claim_fact", "trust_claim_fact_tt",
    "trust_claim_derived_fact", "trust_claim_derived_fact_tt",
    "trust_claim_inference", "trust_claim_inference_tt",
    "trust_claim_unknown", "trust_claim_unknown_tt",
    # evidence classes
    "trust_evidence_source_data", "trust_evidence_source_data_tt",
    "trust_evidence_nova_calculation", "trust_evidence_nova_calculation_tt",
    "trust_evidence_nova_insight", "trust_evidence_nova_insight_tt",
    "trust_evidence_nova_forecast", "trust_evidence_nova_forecast_tt",
]


# Banned phrasing per brief §46. Case-insensitive substring search against
# every EN/DA label and tooltip.
BANNED_PHRASES = (
    "ai thinks",
    "probably correct",
    "% accurate",
    "98.7% accurate",
    "96% accurate",
)


def _all_trust_strings() -> list[str]:
    """Every EN + DA string introduced by TL-0.4."""
    out: list[str] = []
    for key in TRUST_KEYS_EN:
        out.append(LABELS["en"][key])
        out.append(LABELS["da"][key])
    return out


# ---------------------------------------------------------------------------
# AC1 — Every enum value has an EN and a DA label and tooltip
# ---------------------------------------------------------------------------

class TestEnumCoverage:
    def test_trust_state_label_and_tooltip_en_da(self):
        for state in TrustState:
            assert trust_label(state, "en"), f"missing EN label for {state}"
            assert trust_label(state, "da"), f"missing DA label for {state}"
            assert trust_tooltip(state, "en"), f"missing EN tooltip for {state}"
            assert trust_tooltip(state, "da"), f"missing DA tooltip for {state}"

    def test_claim_kind_label_and_tooltip_en_da(self):
        for kind in ClaimKind:
            assert claim_label(kind, "en"), f"missing EN label for {kind}"
            assert claim_label(kind, "da"), f"missing DA label for {kind}"
            assert claim_tooltip(kind, "en"), f"missing EN tooltip for {kind}"
            assert claim_tooltip(kind, "da"), f"missing DA tooltip for {kind}"

    def test_evidence_class_label_and_tooltip_en_da(self):
        for cls in EvidenceClass:
            assert evidence_label(cls, "en"), f"missing EN label for {cls}"
            assert evidence_label(cls, "da"), f"missing DA label for {cls}"
            assert evidence_tooltip(cls, "en"), f"missing EN tooltip for {cls}"
            assert evidence_tooltip(cls, "da"), f"missing DA tooltip for {cls}"

    def test_conflict_flag_has_label_and_tooltip(self):
        assert conflict_label("en")
        assert conflict_label("da")
        assert conflict_tooltip("en")
        assert conflict_tooltip("da")

    def test_en_and_da_differ_for_every_trust_string(self):
        """No DA key may silently fall back to the EN string."""
        for key in TRUST_KEYS_EN:
            en = LABELS["en"][key]
            da = LABELS["da"][key]
            assert en != da, (
                f"DA label for {key!r} is identical to EN ({en!r}); "
                "either the DA copy is missing or it accidentally matches."
            )


# ---------------------------------------------------------------------------
# AC2 — t("da", <every new key>) resolves without falling back to English
# ---------------------------------------------------------------------------

class TestDanishPresence:
    def test_every_trust_key_present_in_da(self):
        for key in TRUST_KEYS_EN:
            assert key in LABELS["da"], (
                f"key {key!r} missing from DA LABELS — would silently fall "
                "back to English through `t()`."
            )
            assert LABELS["da"][key], f"DA value for {key!r} is empty"

    def test_every_trust_key_present_in_en(self):
        for key in TRUST_KEYS_EN:
            assert key in LABELS["en"], f"key {key!r} missing from EN LABELS"
            assert LABELS["en"][key], f"EN value for {key!r} is empty"


# ---------------------------------------------------------------------------
# AC3 — No banned phrasing in any label or tooltip, in either language
# ---------------------------------------------------------------------------

class TestNoBannedPhrasing:
    @pytest.mark.parametrize("text", _all_trust_strings())
    def test_no_banned_phrase(self, text: str):
        lower = text.lower()
        for phrase in BANNED_PHRASES:
            assert phrase not in lower, (
                f"banned phrasing {phrase!r} found in trust string {text!r}"
            )


# ---------------------------------------------------------------------------
# AC4 — Three-state model: exactly three user-facing states
# ---------------------------------------------------------------------------

class TestThreeStateModel:
    def test_trust_state_has_exactly_three_values(self):
        assert len(TrustState) == 3

    def test_trust_state_value_set(self):
        assert {s.value for s in TrustState} == {
            "verified",
            "review",
            "unverified",
        }

    def test_source_conflict_is_a_flag_not_a_state(self):
        assert SOURCE_CONFLICT_FLAG is True
        assert "source_conflict" not in {s.value for s in TrustState}
        assert SOURCE_CONFLICT_FLAG is not TrustState

    def test_source_conflict_has_no_state_lookup(self):
        """Defence-in-depth: even a wrong caller passing the flag string
        to `t_state` must get the English fallback (not a fake fourth
        state), which keeps the three-state invariant visible."""
        # `t_state` looks up `trust_state_source_conflict`, which does not
        # exist in LABELS — `t()` falls back to EN then to the raw key.
        # We just assert no exception is raised; the exact fallback
        # behaviour is governed by `t()` and tested elsewhere.
        result = t_state("source_conflict", "en")
        assert isinstance(result, str)
        assert result  # non-empty


# ---------------------------------------------------------------------------
# Discipline tests — codify the cross-language and namespace contract that
# future phases depend on.
# ---------------------------------------------------------------------------

class TestNamespaceDiscipline:
    def test_all_trust_keys_start_with_prefix(self):
        """Single-regex audit-ability: every TL-0.4 key starts with `trust_`.
        Prevents later phases from adding trust strings outside the prefix."""
        for key in TRUST_KEYS_EN:
            assert key.startswith(TRUST_PREFIX), (
                f"trust key {key!r} does not start with {TRUST_PREFIX!r}"
            )

    def test_trust_prefix_is_unique_to_trust_keys(self):
        """No pre-existing label should accidentally collide with the
        `trust_` prefix — that would mean we silently co-opted another
        feature's strings. (We don't check all of LABELS, just that the
        new keys don't share names with anything else by accident.)"""
        en_keys = list(LABELS["en"].keys())
        for key in TRUST_KEYS_EN:
            assert key in en_keys
            # And confirm we didn't add a duplicate by accident.
            assert en_keys.count(key) == 1


class TestEnumContract:
    def test_enum_values_are_lowercase_strings(self):
        """Phase 2 chunks round-trip these via JSON; str-value enums make
        that work without an adapter."""
        for state in TrustState:
            assert isinstance(state.value, str)
            assert state.value == state.value.lower()
        for kind in ClaimKind:
            assert isinstance(kind.value, str)
            assert kind.value == kind.value.lower()
        for cls in EvidenceClass:
            assert isinstance(cls.value, str)
            assert cls.value == cls.value.lower()

    def test_trust_state_str_values(self):
        assert TrustState.VERIFIED.value == "verified"
        assert TrustState.REVIEW.value == "review"
        assert TrustState.UNVERIFIED.value == "unverified"

    def test_claim_kind_str_values(self):
        assert ClaimKind.FACT.value == "fact"
        assert ClaimKind.DERIVED_FACT.value == "derived_fact"
        assert ClaimKind.INFERENCE.value == "inference"
        assert ClaimKind.UNKNOWN.value == "unknown"

    def test_evidence_class_str_values(self):
        assert EvidenceClass.SOURCE_DATA.value == "source_data"
        assert EvidenceClass.NOVA_CALCULATION.value == "nova_calculation"
        assert EvidenceClass.NOVA_INSIGHT.value == "nova_insight"
        assert EvidenceClass.NOVA_FORECAST.value == "nova_forecast"


class TestHelpersAcceptBothForms:
    """Callers will inevitably pass both enum members and raw .value
    strings (especially across the JSON boundary). The accessors must not
    care which they get."""

    @pytest.mark.parametrize("state", list(TrustState))
    def test_trust_label_accepts_enum_or_string(self, state: TrustState):
        assert trust_label(state, "en") == trust_label(state.value, "en")
        assert trust_label(state, "da") == trust_label(state.value, "da")

    @pytest.mark.parametrize("state", list(TrustState))
    def test_trust_tooltip_accepts_enum_or_string(self, state: TrustState):
        assert trust_tooltip(state, "en") == trust_tooltip(state.value, "en")
        assert trust_tooltip(state, "da") == trust_tooltip(state.value, "da")

    @pytest.mark.parametrize("kind", list(ClaimKind))
    def test_claim_label_accepts_enum_or_string(self, kind: ClaimKind):
        assert claim_label(kind, "en") == claim_label(kind.value, "en")
        assert claim_label(kind, "da") == claim_label(kind.value, "da")

    @pytest.mark.parametrize("cls", list(EvidenceClass))
    def test_evidence_label_accepts_enum_or_string(self, cls: EvidenceClass):
        assert evidence_label(cls, "en") == evidence_label(cls.value, "en")
        assert evidence_label(cls, "da") == evidence_label(cls.value, "da")


# ---------------------------------------------------------------------------
# Verbatim wording tests — tooltips come from brief §21 word-for-word;
# labels come from brief §46. These are the regression guards against
# accidental copy drift.
# ---------------------------------------------------------------------------

class TestBriefWording:
    @pytest.mark.parametrize(
        "state,expected",
        [
            (TrustState.VERIFIED, "Verified against source schedule."),
            (TrustState.REVIEW,
             "Nova identified uncertainty in the source data or activity match. Review recommended."),
            (TrustState.UNVERIFIED,
             "Nova could not reliably verify this value. It has not been used as confirmed data."),
        ],
    )
    def test_trust_tooltip_matches_brief_section_21(self, state, expected):
        assert trust_tooltip(state, "en") == expected

    @pytest.mark.parametrize(
        "state,expected_da",
        [
            (TrustState.VERIFIED, "Verificeret mod kildetidsplanen."),
            (TrustState.REVIEW,
             "Nova har identificeret usikkerhed i kildedata eller aktivitetsmatch. Kontrol anbefales."),
            (TrustState.UNVERIFIED,
             "Nova kunne ikke pålideligt verificere denne værdi. Den er ikke brugt som bekræftet data."),
        ],
    )
    def test_trust_tooltip_da_initial_translation(self, state, expected_da):
        """DA tooltips are the initial translation pending EXT-2 sign-off.
        When EXT-2 lands, update both LABELS['da'] and this test."""
        assert trust_tooltip(state, "da") == expected_da

    @pytest.mark.parametrize(
        "state,expected",
        [
            (TrustState.VERIFIED, "Verified"),
            (TrustState.REVIEW, "Review Recommended"),
            (TrustState.UNVERIFIED, "Unable to Verify"),
        ],
    )
    def test_trust_label_matches_brief_section_46(self, state, expected):
        assert trust_label(state, "en") == expected

    def test_conflict_label_matches_brief_section_46(self):
        assert conflict_label("en") == "Source Conflict"

    @pytest.mark.parametrize(
        "cls,expected",
        [
            (EvidenceClass.SOURCE_DATA, "What the schedule says."),
            (EvidenceClass.NOVA_CALCULATION, "What Nova deterministically calculated."),
            (EvidenceClass.NOVA_INSIGHT, "What Nova inferred/interpreted."),
            (EvidenceClass.NOVA_FORECAST, "What Nova predicts."),
        ],
    )
    def test_evidence_tooltip_matches_brief_section_45(self, cls, expected):
        assert evidence_tooltip(cls, "en") == expected

    @pytest.mark.parametrize(
        "cls,expected",
        [
            (EvidenceClass.SOURCE_DATA, "Source Data"),
            (EvidenceClass.NOVA_CALCULATION, "Nova Calculation"),
            (EvidenceClass.NOVA_INSIGHT, "Nova Insight"),
            (EvidenceClass.NOVA_FORECAST, "Nova Forecast"),
        ],
    )
    def test_evidence_label_matches_brief_section_45_46(self, cls, expected):
        assert evidence_label(cls, "en") == expected


class TestNoPercentagesInLabels:
    """Brief §23 bans percentages without a defined denominator. TL-7.2 is
    the separate task for the percentage-with-denominator question. Until
    that lands, no user-facing trust label or tooltip may carry one."""

    @pytest.mark.parametrize("text", _all_trust_strings())
    def test_no_percent_sign(self, text: str):
        assert "%" not in text, (
            f"unexpected percentage in trust string {text!r}; brief §23 "
            "forbids confidence-as-percentage without a defined denominator."
        )
