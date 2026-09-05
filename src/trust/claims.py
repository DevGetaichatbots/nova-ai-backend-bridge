"""Claim extraction and verification (TL-6.2 + TL-6.3, brief §16).

Brief §16's own worked example is the spec:

    "Electrical works in Building NK are the project's largest
    concentration of delay, with 17 activities behind schedule and three
    critical activities."

Nova must verify each claim independently — *largest concentration?* *17
delayed?* *3 critical?* — and only display after validation. `TL-6.3`
(verification) cannot do that unless the claims are isolated first; that
is this module's entire job. It does not verify anything — it only finds
candidate claims and records enough about each one (its exact span, its
form, and the values it asserts) for `TL-6.3` to check deterministically.

Extraction is regex/parsing over the narrative text — no model call
anywhere in this module, and none should be added. A model could in
principle *propose* claim candidates, but brief §34 and this task's own
Do-not rule are explicit: a model's output is itself unverified and must
never be trusted to *clear* a claim, only to suggest one for the
deterministic verifier to check. Keeping this module LLM-free entirely
avoids the question.

Naming trap to avoid: `ClaimForm` (this module) is NOT
`src.trust.vocabulary.ClaimKind` (`TL-0.4`: FACT / DERIVED_FACT /
INFERENCE / UNKNOWN). They are different axes on the same claim:

- `ClaimForm` — the claim's *syntactic/semantic shape* (numeric quantity,
  superlative, activity-id reference, date/duration, causal). Assigned at
  extraction time, before anything is verified. This is what tells
  `TL-6.3` *how* to check a claim (recount, recompute a ranking, look up
  an id, ...).
- `ClaimKind` — the claim's *epistemic status* (fact, derived fact,
  inference, unknown). Assigned by `TL-6.4`, after verification, from the
  outcome. A `CAUSAL`-form claim always ends up `INFERENCE` or gets
  removed (brief §18's A142 example); a verified `NUMERIC_QUANTITY` claim
  ends up `FACT` or `DERIVED_FACT`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Sequence

from src.trust.engine import verify_id_reference
from src.trust.vocabulary import ClaimKind

logger = logging.getLogger(__name__)


class ClaimForm(str, Enum):
    """Which of the five brief §16 claim shapes this claim takes. See the
    module docstring for why this is not `vocabulary.ClaimKind`."""

    NUMERIC_QUANTITY = "numeric_quantity"
    SUPERLATIVE = "superlative"
    ACTIVITY_ID_REFERENCE = "activity_id_reference"
    DATE_DURATION = "date_duration"
    CAUSAL = "causal"


@dataclass(frozen=True)
class Claim:
    """One atomic, isolated factual claim (brief §16).

    - `text`: the exact substring of the narrative this claim covers
      (`narrative[span[0]:span[1]]`).
    - `span`: `(start, end)` character offsets into the *original*
      narrative string — not a copy, not normalized. This is what lets
      `TL-6.1`'s `GatePolicy.REMOVE` (currently a best-effort substring
      match, per its own docstring) upgrade to precise, position-based
      removal, and what "Claims record spans, enabling targeted removal
      or qualification" (this task's AC3) actually means.
    - `form`: the claim's shape (`ClaimForm`) — how `TL-6.3` should verify
      it.
    - `extracted_values`: form-specific structured data pulled out of the
      text (e.g. `{"number": 17, "noun_phrase": "activities"}` for a
      numeric claim, `{"activity_id": "A142"}` for an id reference). Never
      guessed beyond what the text literally contains.
    - `asserted_fields`: best-effort, deterministic keyword hints at which
      fact-store concept this claim is about (e.g. `("delayed_count",)`,
      `("critical_count",)`, `("activity_id",)`). These are hints for
      `TL-6.3` to route verification, not a resolved path into a specific
      schema — `TL-6.3` still does the actual recount/lookup. Can be
      empty when the mapping is ambiguous; an empty tuple is not an error,
      it means "this module could not guess which fact-store concept
      applies," which `TL-6.3` should treat as needing its own more
      careful (but still deterministic) resolution, not as "unverifiable."
    """

    text: str
    span: tuple[int, int]
    form: ClaimForm
    extracted_values: dict[str, Any] = field(default_factory=dict)
    asserted_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimExtractionResult:
    """The result of attempting to decompose one narrative string.

    `decomposable=False` (AC4) means the input could not be safely
    processed at all — not a string, or an exception during pattern
    matching — and must be treated by the caller as *unverified*, never as
    "no claims were found, so the text must be safe." A `decomposable=True`
    result with an empty `claims` tuple is different and legitimate: the
    text was processed and genuinely contains none of the five detectable
    claim shapes (e.g. an empty string, or a sentence with no numbers,
    superlatives, ids, dates, or causal language at all).
    """

    claims: tuple[Claim, ...]
    decomposable: bool
    reason: str = ""


# ============================================================================
# Word-number vocabulary (EN + DA) — both dashboards ship Danish (brief
# §46; Kemp is Danish-only), and Nova's own generated narrative already
# writes small numbers as words ("three critical activities" — brief §16's
# own example).
# ============================================================================

_WORD_TO_NUMBER: dict[str, int] = {
    # English
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    # Danish
    "nul": 0, "en": 1, "et": 1, "to": 2, "tre": 3, "fire": 4, "fem": 5,
    "seks": 6, "syv": 7, "otte": 8, "ni": 9, "ti": 10,
    "elleve": 11, "tolv": 12, "tretten": 13, "fjorten": 14, "femten": 15,
    "seksten": 16, "sytten": 17, "atten": 18, "nitten": 19, "tyve": 20,
}
# Longest-first so e.g. "seventeen" is not shadowed by a shorter alternative
# earlier in the regex alternation.
_WORD_NUMBER_ALTERNATION = "|".join(
    re.escape(w) for w in sorted(_WORD_TO_NUMBER, key=len, reverse=True)
)


def _word_or_digit_to_number(token: str) -> int:
    token_lower = token.lower()
    if token_lower in _WORD_TO_NUMBER:
        return _WORD_TO_NUMBER[token_lower]
    return int(token)


# ============================================================================
# Extraction order and overlap resolution
# ============================================================================
# A single number in the text (e.g. "18") can plausibly be claimed by more
# than one detector — "18 days" is a DATE_DURATION, not a bare
# NUMERIC_QUANTITY. Detectors run independently and produce candidate
# matches; `extract_claims` then keeps candidates greedily in this
# priority order, skipping any candidate whose span overlaps one already
# kept. Most-specific-shape-wins: an id or a date/duration is a more
# precise claim than treating the same digits as a generic quantity.

_PRIORITY_ORDER: tuple[ClaimForm, ...] = (
    ClaimForm.ACTIVITY_ID_REFERENCE,
    ClaimForm.DATE_DURATION,
    ClaimForm.CAUSAL,
    ClaimForm.SUPERLATIVE,
    ClaimForm.NUMERIC_QUANTITY,
)


def _spans_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


# ============================================================================
# Numeric quantity claims — brief §16: "17 activities behind schedule",
# "three critical activities"
# ============================================================================
# `noun_phrase` is captured lazily (as few words as possible) so it stops
# at the first connector word or punctuation rather than swallowing the
# rest of the sentence — "17 activities behind schedule and three..."
# yields noun_phrase="activities", not "activities behind schedule and".

_CONNECTOR_WORDS = (
    "and", "or", "but", "behind", "is", "are", "in", "at", "on", "with",
    "due", "caused", "for", "of", "to", "from",
    "og", "eller", "men", "bagud", "er", "i", "på", "med", "grundet", "for",
)

_WORD = r"[A-Za-zÆØÅæøå][A-Za-zÆØÅæøå\-]*"
_STOP_LOOKAHEAD = r"(?=[,.;:!?]|\s+(?:" + "|".join(_CONNECTOR_WORDS) + r")\b|$)"

# Two alternatives for `noun_phrase`, tried in order:
#   (a) the precise, lazy form — stop at the first real boundary (a
#       connector word, punctuation, or end of string) within 5 words.
#       This is what every well-formed sentence hits, and it is tried
#       first so it always wins when it can match at all (identical
#       behaviour to the pre-fix pattern for every case that used to
#       succeed).
#   (b) a bounded fallback — if no such boundary exists within 5 words
#       (a long, unbroken run of plain words with no connector and no
#       punctuation before hitting the cap), grab the first 4 words
#       anyway rather than let the whole match fail. Regex alternation
#       tries (a) first at every position; (b) only fires when (a) is
#       exhausted for every word count 0-4, so this never changes a
#       previously-correct (a)-match, only prevents the previous
#       "silent zero claims" failure when (a) cannot find a boundary at
#       all (see ADR-031: a claim used to vanish entirely rather than
#       being extracted with a merely-imprecise cutoff).
_NUMERIC_QUANTITY_PATTERN = re.compile(
    r"\b(?P<number>\d+|" + _WORD_NUMBER_ALTERNATION + r")\b"
    r"\s+(?P<noun_phrase>"
    r"(?:" + _WORD + r"(?:\s+" + _WORD + r"){0,4}?" + _STOP_LOOKAHEAD + r")"
    r"|"
    r"(?:" + _WORD + r"(?:\s+" + _WORD + r"){0,3})"
    r")",
    re.IGNORECASE,
)

# Keyword -> best-effort fact-store hint (`asserted_fields`). Order matters:
# more specific phrases are checked before generic ones.
_QUANTITY_FIELD_HINTS: tuple[tuple[str, str], ...] = (
    ("root cause", "root_cause_count"),
    ("grundårsag", "root_cause_count"),
    ("critical", "critical_count"),
    ("kritisk", "critical_count"),
    ("important", "important_count"),
    ("vigtig", "important_count"),
    ("overdue", "days_overdue"),
    ("forsinket", "days_overdue"),
    ("delayed", "delayed_count"),
    ("forsink", "delayed_count"),
    ("activit", "delayed_count"),
    ("aktivit", "delayed_count"),
    ("area", "areas_affected"),
    ("område", "areas_affected"),
)


def _guess_quantity_field(noun_phrase: str) -> tuple[str, ...]:
    lowered = noun_phrase.lower()
    for keyword, hint in _QUANTITY_FIELD_HINTS:
        if keyword in lowered:
            return (hint,)
    return ()


def _extract_numeric_quantity_claims(text: str) -> list[Claim]:
    claims = []
    for m in _NUMERIC_QUANTITY_PATTERN.finditer(text):
        number_token = m.group("number")
        noun_phrase = m.group("noun_phrase")
        try:
            number = _word_or_digit_to_number(number_token)
        except ValueError:
            continue
        claims.append(
            Claim(
                text=m.group(0),
                span=m.span(),
                form=ClaimForm.NUMERIC_QUANTITY,
                extracted_values={"number": number, "noun_phrase": noun_phrase},
                asserted_fields=_guess_quantity_field(noun_phrase),
            )
        )
    return claims


# ============================================================================
# Superlative / ranking claims — brief §16: "largest concentration of delay"
# ============================================================================

_SUPERLATIVE_KEYWORDS = (
    # English
    "largest", "biggest", "greatest", "highest", "most", "smallest",
    "least", "fewest", "worst", "best", "top",
    # Danish
    "største", "mest", "højeste", "flest", "færrest", "værste", "bedste",
    "mindste", "topscorer",
)

# The trailing "of/in <phrase>" clause is matched lazily (as few extra
# words as possible) with the actual stopping point decided by the
# trailing lookahead — the same "stop before a connector/linking word or
# punctuation" strategy `_NUMERIC_QUANTITY_PATTERN` uses, so "largest
# concentration of current delay is within..." stops at "delay" rather
# than swallowing "is within" too.
_SUPERLATIVE_PATTERN = re.compile(
    r"\b(?:the\s+)?(?:[A-Za-zÆØÅæøå]+'s\s+)?"
    r"(?P<superlative>(?:" + "|".join(_SUPERLATIVE_KEYWORDS) + r")"
    r"\s+[A-Za-zÆØÅæøå][A-Za-zÆØÅæøå\-]*"
    r"(?:\s+(?:of|in|på|i|af)\s+[A-Za-zÆØÅæøå][A-Za-zÆØÅæøå\-]*"
    r"(?:\s+[A-Za-zÆØÅæøå][A-Za-zÆØÅæøå\-]*){0,2}?)?)"
    r"(?=[,.;:!?]|\s+(?:" + "|".join(_CONNECTOR_WORDS) + r")\b|$)",
    re.IGNORECASE,
)


def _extract_superlative_claims(text: str) -> list[Claim]:
    claims = []
    for m in _SUPERLATIVE_PATTERN.finditer(text):
        claims.append(
            Claim(
                text=m.group(0),
                span=m.span(),
                form=ClaimForm.SUPERLATIVE,
                extracted_values={"superlative_phrase": m.group("superlative")},
                asserted_fields=("ranking",),
            )
        )
    return claims


# ============================================================================
# Activity ID references — brief §18/§16: "A142", "Task ID 41"
# ============================================================================
# Two shapes: a keyword-anchored reference ("Task ID 41", "ID: A142",
# "aktivitet A142") and a bare alphanumeric token that looks like an id
# (letters immediately followed by digits, e.g. "A142", "EL-4"). The bare
# form is intentionally conservative (requires at least one letter AND one
# digit) so it does not fire on plain numbers, which `NUMERIC_QUANTITY`
# already owns.

_ID_KEYWORD_PATTERN = re.compile(
    r"\b(?:Task\s+ID|task\s+id|ID|Id|aktivitet(?:en)?(?:\s+med\s+id)?)"
    r"\s*[:#]?\s*(?P<id>[A-Za-zÆØÅæøå]{0,6}[-_]?\d+[A-Za-z0-9]*)\b"
)
_BARE_ID_PATTERN = re.compile(r"\b(?P<id>[A-Za-zÆØÅæøå]{1,6}[-_]?\d{1,6}[A-Za-z0-9]*)\b")


def _extract_activity_id_claims(text: str) -> list[Claim]:
    claims: list[Claim] = []
    claimed_spans: list[tuple[int, int]] = []

    for m in _ID_KEYWORD_PATTERN.finditer(text):
        claims.append(
            Claim(
                text=m.group(0),
                span=m.span(),
                form=ClaimForm.ACTIVITY_ID_REFERENCE,
                extracted_values={"activity_id": m.group("id")},
                asserted_fields=("activity_id",),
            )
        )
        claimed_spans.append(m.span())

    for m in _BARE_ID_PATTERN.finditer(text):
        span = m.span()
        if any(_spans_overlap(span, taken) for taken in claimed_spans):
            continue
        claims.append(
            Claim(
                text=m.group(0),
                span=span,
                form=ClaimForm.ACTIVITY_ID_REFERENCE,
                extracted_values={"activity_id": m.group("id")},
                asserted_fields=("activity_id",),
            )
        )
    return claims


# ============================================================================
# Date / duration claims — brief §16/§33: "18 days", "+6 weeks", "01-03-2026"
# ============================================================================

_DURATION_PATTERN = re.compile(
    r"\b(?P<number>\d+(?:[.,]\d+)?)"
    r"(?:\s*[-–]\s*(?P<number2>\d+(?:[.,]\d+)?))?"
    r"\s*(?P<unit>days?|weeks?|months?|dage|uger|måneder)\b",
    re.IGNORECASE,
)
_ISO_DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_DMY_DATE_PATTERN = re.compile(r"\b\d{1,2}[-./]\d{1,2}[-./]\d{2,4}\b")


def _extract_date_duration_claims(text: str) -> list[Claim]:
    claims = []
    for m in _DURATION_PATTERN.finditer(text):
        values: dict[str, Any] = {"number": float(m.group("number").replace(",", ".")), "unit": m.group("unit").lower()}
        if m.group("number2"):
            values["number_upper"] = float(m.group("number2").replace(",", "."))
        claims.append(
            Claim(text=m.group(0), span=m.span(), form=ClaimForm.DATE_DURATION,
                  extracted_values=values, asserted_fields=("duration",))
        )
    for pattern, kind in ((_ISO_DATE_PATTERN, "iso"), (_DMY_DATE_PATTERN, "dmy")):
        for m in pattern.finditer(text):
            claims.append(
                Claim(text=m.group(0), span=m.span(), form=ClaimForm.DATE_DURATION,
                      extracted_values={"date": m.group(0), "date_format": kind},
                      asserted_fields=("date",))
            )
    return claims


# ============================================================================
# Causal claims — brief §20: always suspect, never verifiable from
# schedule data alone (brief §18's A142 example)
# ============================================================================

_CAUSAL_TRIGGERS = (
    # Order matters only for readability here — `re.finditer` finds every
    # non-overlapping match regardless of alternation order. Includes both
    # the prepositional forms ("caused by", "due to") and the bare verb
    # form ("caused the delay") — brief §20's own wrong-example is exactly
    # the bare verb form ("Electrical work caused the delay"), so a
    # trigger list covering only "caused by" would miss the brief's own
    # headline case.
    r"caused by", r"caused", r"causing", r"due to", r"because of",
    r"as a result of", r"resulting from", r"leads? to", r"led to",
    r"results? in", r"resulted in", r"is responsible for",
    r"skyldes", r"på grund af", r"forårsaget af", r"forårsager",
    r"forårsagede", r"som følge af", r"fører til", r"resulterer i",
    r"resulterede i",
)
_CAUSAL_PATTERN = re.compile(r"\b(?:" + "|".join(_CAUSAL_TRIGGERS) + r")\b", re.IGNORECASE)

def _extract_causal_claims(text: str) -> list[Claim]:
    claims = []
    for m in _CAUSAL_PATTERN.finditer(text):
        # Expand to the enclosing sentence: find the nearest sentence start
        # at/before the trigger and the nearest sentence-ending punctuation
        # at/after it. Falls back to the trigger's own span if no sentence
        # punctuation is found (e.g. a narrative fragment with no period).
        preceding = text[: m.start()]
        sentence_start = 0
        last_boundary = None
        for boundary in re.finditer(r"[.!?]\s+", preceding):
            last_boundary = boundary
        if last_boundary is not None:
            sentence_start = last_boundary.end()

        end_match = re.search(r"[.!?]", text[m.end():])
        sentence_end = m.end() + end_match.end() if end_match else len(text)

        span = (sentence_start, sentence_end)
        claims.append(
            Claim(
                text=text[span[0]:span[1]].strip(),
                span=span,
                form=ClaimForm.CAUSAL,
                extracted_values={"trigger": m.group(0)},
                # Brief §20/TL-6.3: causal claims can never be verified from
                # schedule data alone — no fact-store field applies.
                asserted_fields=(),
            )
        )
    return claims


# ============================================================================
# Top-level extraction
# ============================================================================

_EXTRACTORS: dict[ClaimForm, Any] = {
    ClaimForm.ACTIVITY_ID_REFERENCE: _extract_activity_id_claims,
    ClaimForm.DATE_DURATION: _extract_date_duration_claims,
    ClaimForm.CAUSAL: _extract_causal_claims,
    ClaimForm.SUPERLATIVE: _extract_superlative_claims,
    ClaimForm.NUMERIC_QUANTITY: _extract_numeric_quantity_claims,
}


def _extract_all_claims(text: str) -> list[Claim]:
    """Run every detector, then keep candidates greedily in
    `_PRIORITY_ORDER`, skipping any whose span overlaps one already kept.
    Ties within a form are resolved left-to-right (earlier span first).

    `CAUSAL` claims are collected unconditionally, exempt from the overlap
    check in both directions. A causal claim's span is deliberately the
    *whole enclosing sentence* (it is a claim about a relationship, not
    about one token) — it will routinely overlap an id/number/date claim
    that lives inside the same sentence. Those are not competing
    interpretations of the same text (contrast e.g. "18 days" as
    NUMERIC_QUANTITY vs. DATE_DURATION, which genuinely are); a sentence
    can and often does carry both a causal claim and a numeric claim at
    once (brief's own concern: "A142 is delayed by 18 days, caused by a
    coordination issue" is two claims, not one). Suppressing one for the
    other would silently drop exactly the causal claim brief §20 says is
    "always suspect" and must never pass through unflagged.
    """
    causal_claims = sorted(_EXTRACTORS[ClaimForm.CAUSAL](text), key=lambda c: c.span[0])
    accepted: list[Claim] = list(causal_claims)

    for form in _PRIORITY_ORDER:
        if form is ClaimForm.CAUSAL:
            continue
        candidates = sorted(_EXTRACTORS[form](text), key=lambda c: c.span[0])
        non_causal_accepted = [c for c in accepted if c.form is not ClaimForm.CAUSAL]
        for candidate in candidates:
            if any(_spans_overlap(candidate.span, taken.span) for taken in non_causal_accepted):
                continue
            accepted.append(candidate)
            non_causal_accepted.append(candidate)

    accepted.sort(key=lambda c: c.span[0])
    return accepted


def extract_claims(text: Any) -> ClaimExtractionResult:
    """TL-6.2: decompose `text` into atomic `Claim`s.

    Returns `decomposable=False` (AC4) if `text` is not a string, or if
    extraction raises for any reason — the caller must treat that as
    "unverified," never as "no claims were found." A non-empty string that
    genuinely contains none of the five detectable claim shapes still
    returns `decomposable=True` with an empty `claims` tuple — that is a
    legitimate outcome, not a failure.
    """
    if not isinstance(text, str):
        return ClaimExtractionResult(claims=(), decomposable=False, reason=f"expected str, got {type(text).__name__}")
    if not text.strip():
        return ClaimExtractionResult(claims=(), decomposable=True)

    try:
        claims = tuple(_extract_all_claims(text))
    except Exception as exc:  # defensive: a pattern-matching failure must never look like "no claims"
        logger.error(f"  [claims] extraction failed: {exc}")
        return ClaimExtractionResult(claims=(), decomposable=False, reason=f"extraction error: {exc}")

    return ClaimExtractionResult(claims=claims, decomposable=True)


# ============================================================================
# TL-6.3 — Claim verification against the fact store (brief §16, §34)
# ============================================================================
# This is the enforcement point brief §34 is actually about: extraction
# (above) only isolates candidates; nothing is checked until here. Every
# rule in this section is deterministic — recount, exact membership,
# recompute a ranking — never a model call, for the same reason
# extraction has none (see the module docstring's Do-not rule).
#
# The "fact store" a claim is checked against is the same flat response
# shape `predictive_agent._merge_narrative_into_facts` (NUSF path) and
# `predictive_agent.analyze()` (raw path, after its correction block)
# both already converge on: a dict with `insight_data` (deterministic
# counts), `delayed_activities` (deterministic per-activity facts), and
# `summary_by_area` (deterministic per-area counts — used here as the
# ranking data for superlative claims, since it is present in *both*
# paths' final shape, unlike the NUSF-only intermediate `clusters`).
# Verification does not care which path produced the dict — only that
# these three keys mean what Phase 5 guarantees they mean.


class VerificationOutcome(str, Enum):
    """Brief §16's three outcomes. There is no fourth "close enough"
    value — a claim is either grounded, contradicted, or the fact store
    has nothing to check it against."""

    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    UNVERIFIABLE = "unverifiable"


# ============================================================================
# TL-6.4 — `ClaimKind` classification (brief §19)
# ============================================================================
# Brief §19: *"Never present inference as fact."* A claim's epistemic
# status — FACT / DERIVED_FACT / INFERENCE / UNKNOWN — is derived
# deterministically from (ClaimForm, VerificationOutcome):
#
#   - FACT — directly from source. A `VERIFIED` `ACTIVITY_ID_REFERENCE`
#     (the id exists in the fact store) and a `VERIFIED` `DATE_DURATION`
#     (the date or day count matches a known fact-store value) are facts
#     lifted from the source. They are *not* re-derivations of aggregates,
#     so they get `FACT` rather than `DERIVED_FACT`.
#   - DERIVED_FACT — deterministically calculated. A `VERIFIED`
#     `NUMERIC_QUANTITY` (recount from `insight_data`) or a `VERIFIED`
#     `SUPERLATIVE` (recomputed ranking from `summary_by_area`) is a
#     Python-side calculation grounded in the source, not a value taken
#     verbatim from it — `DERIVED_FACT` rather than `FACT`.
#   - INFERENCE — evidence suggests, does not prove. `CAUSAL` is always
#     `INFERENCE`, regardless of outcome, per brief §18's A142 example
#     ("A142 is delayed by 18 days caused by a coordination issue"):
#     causality cannot be established from schedule data alone, and
#     brief §20 is emphatic that a verified causal claim is still an
#     inference.
#   - UNKNOWN — insufficient evidence. Any `UNVERIFIABLE` claim that is
#     not causal — the fact store had nothing to check the claim
#     against, so its truth value is genuinely unknown. CONTRADICTED
#     claims are mapped to `UNKNOWN` for the rare caller that inspects
#     the rejected list (e.g. `TL-6.7`'s rate metric): they never
#     reach a renderer in normal flow (`verify_narrative` removes
#     them), but the classification is recorded for completeness.
#
# The Do-not rule "do not classify a DERIVED_FACT as INFERENCE out of
# caution" is the reason the `VERIFIED × {NUMERIC_QUANTITY,
# SUPERLATIVE}` cases land on `DERIVED_FACT` and not `INFERENCE` — the
# rules in `_CLASSIFICATION_TABLE` are *exact*, not a hedge.

_CLASSIFICATION_TABLE: dict[tuple[ClaimForm, VerificationOutcome], ClaimKind] = {
    # VERIFIED cases — what kind each form becomes once grounded
    (ClaimForm.ACTIVITY_ID_REFERENCE, VerificationOutcome.VERIFIED): ClaimKind.FACT,
    (ClaimForm.DATE_DURATION, VerificationOutcome.VERIFIED): ClaimKind.FACT,
    (ClaimForm.NUMERIC_QUANTITY, VerificationOutcome.VERIFIED): ClaimKind.DERIVED_FACT,
    (ClaimForm.SUPERLATIVE, VerificationOutcome.VERIFIED): ClaimKind.DERIVED_FACT,
    # CAUSAL is special: never verified, always INFERENCE (brief §20).
    # The VERIFIED row is included for symmetry / explicitness — even if
    # a future verifier returned VERIFIED for a causal claim (it must
    # not, per `_verify_causal`), the classifier would still mark it
    # INFERENCE so the brief §20 rule holds structurally rather than by
    # convention.
    (ClaimForm.CAUSAL, VerificationOutcome.VERIFIED): ClaimKind.INFERENCE,
    # UNVERIFIABLE — non-causal claims with no fact-store handle
    (ClaimForm.ACTIVITY_ID_REFERENCE, VerificationOutcome.UNVERIFIABLE): ClaimKind.UNKNOWN,
    (ClaimForm.DATE_DURATION, VerificationOutcome.UNVERIFIABLE): ClaimKind.UNKNOWN,
    (ClaimForm.NUMERIC_QUANTITY, VerificationOutcome.UNVERIFIABLE): ClaimKind.UNKNOWN,
    (ClaimForm.SUPERLATIVE, VerificationOutcome.UNVERIFIABLE): ClaimKind.UNKNOWN,
    (ClaimForm.CAUSAL, VerificationOutcome.UNVERIFIABLE): ClaimKind.INFERENCE,
    # CONTRADICTED — these claims never reach a renderer, but record the
    # classification for callers that want to inspect the rejected list.
    (ClaimForm.ACTIVITY_ID_REFERENCE, VerificationOutcome.CONTRADICTED): ClaimKind.UNKNOWN,
    (ClaimForm.DATE_DURATION, VerificationOutcome.CONTRADICTED): ClaimKind.UNKNOWN,
    (ClaimForm.NUMERIC_QUANTITY, VerificationOutcome.CONTRADICTED): ClaimKind.UNKNOWN,
    (ClaimForm.SUPERLATIVE, VerificationOutcome.CONTRADICTED): ClaimKind.UNKNOWN,
    (ClaimForm.CAUSAL, VerificationOutcome.CONTRADICTED): ClaimKind.INFERENCE,
}


def _classify_claim(claim: Claim, outcome: VerificationOutcome) -> ClaimKind:
    """TL-6.4: assign a `ClaimKind` to a verified claim.

    Pure lookup over `_CLASSIFICATION_TABLE`. Raises `KeyError` if a
    (form, outcome) pair is unmapped — that would be a bug (every
    reachable combination must be in the table; the table is
    deliberately exhaustive), not a silent default to `FACT` or any
    other value. AC4 ("no statement defaults to FACT implicitly") is
    enforced structurally: there is no fallback, and a missing entry
    surfaces as a build-time failure rather than a quiet
    misclassification at render time.
    """
    return _CLASSIFICATION_TABLE[(claim.form, outcome)]


@dataclass(frozen=True)
class VerifiedClaim:
    """One claim after verification. `claim.span`/`claim.text` are
    unchanged from extraction — this is what lets a caller remove exactly
    a `CONTRADICTED` claim's own text from the narrative (this task's
    Do-not rule: never rewrite the number in place, remove the claim).

    `kind` is the `TL-6.4` epistemic-status assignment (brief §19): the
    claim's classification *given* its verified outcome, not just the
    outcome alone. A `VERIFIED` numeric-quantity claim is `DERIVED_FACT`
    (the count was deterministically recounted from `insight_data`); a
    `VERIFIED` activity-id claim is `FACT` (the id exists in the source
    per `TL-2.3`); a `CAUSAL` claim — verified or not — is always
    `INFERENCE`, per brief §18's A142 example: causality cannot be
    established from schedule data alone, regardless of what the fact
    store says. `UNVERIFIABLE` claims with no other handle are `UNKNOWN`."""

    claim: Claim
    outcome: VerificationOutcome
    reason: str
    kind: ClaimKind = field(default=ClaimKind.UNKNOWN)


# Numeric-claim field hints (`Claim.asserted_fields`, from `TL-6.2`) that
# map to an unambiguous single aggregate in `insight_data`. Hints not
# listed here (e.g. `"days_overdue"`, which is per-activity and therefore
# ambiguous in aggregate narrative — brief's own worked activity-level
# example, "A142 is delayed by 18 days," is a DATE_DURATION claim, not a
# NUMERIC_QUANTITY one, and is checked separately below) are deliberately
# left UNVERIFIABLE rather than guessed against the wrong denominator.
_VERIFIABLE_NUMERIC_HINTS = (
    "delayed_count", "critical_count", "important_count",
    "root_cause_count", "areas_affected",
)


def _verify_numeric_quantity(claim: Claim, facts: dict) -> VerifiedClaim:
    insight_data = facts.get("insight_data", {}) or {}
    hints = [h for h in claim.asserted_fields if h in _VERIFIABLE_NUMERIC_HINTS]
    if not hints:
        return VerifiedClaim(
            claim, VerificationOutcome.UNVERIFIABLE,
            "no unambiguous fact-store field for this quantity",
            kind=_classify_claim(claim, VerificationOutcome.UNVERIFIABLE),
        )
    field_name = hints[0]
    if field_name not in insight_data:
        return VerifiedClaim(
            claim, VerificationOutcome.UNVERIFIABLE,
            f"'{field_name}' not present in fact store",
            kind=_classify_claim(claim, VerificationOutcome.UNVERIFIABLE),
        )

    actual = insight_data[field_name]
    claimed = claim.extracted_values.get("number")
    if actual == claimed:
        return VerifiedClaim(
            claim, VerificationOutcome.VERIFIED,
            f"recount matches: {field_name}={actual}",
            kind=_classify_claim(claim, VerificationOutcome.VERIFIED),
        )
    return VerifiedClaim(
        claim, VerificationOutcome.CONTRADICTED,
        f"recount mismatch: narrative claims {claimed}, fact store has {field_name}={actual}",
        # CONTRADICTED claims are removed by `verify_narrative` and never
        # reach a renderer, but we still attach a `kind` for the rare
        # caller that inspects the rejected list (`TL-6.7`'s metric).
        kind=_classify_claim(claim, VerificationOutcome.CONTRADICTED),
    )


def _verify_activity_id_reference(claim: Claim, facts: dict) -> VerifiedClaim:
    candidate_id = claim.extracted_values.get("activity_id")
    delayed_activities = facts.get("delayed_activities")
    if not delayed_activities:
        return VerifiedClaim(
            claim, VerificationOutcome.UNVERIFIABLE,
            "fact store has no known activity ids to check against",
            kind=_classify_claim(claim, VerificationOutcome.UNVERIFIABLE),
        )

    known_ids = {a["id"] for a in delayed_activities if a.get("id") is not None}
    if verify_id_reference(candidate_id, known_ids):
        return VerifiedClaim(
            claim, VerificationOutcome.VERIFIED,
            f"id {candidate_id!r} exists in the fact store",
            kind=_classify_claim(claim, VerificationOutcome.VERIFIED),
        )
    return VerifiedClaim(
        claim, VerificationOutcome.CONTRADICTED,
        f"id {candidate_id!r} does not exist in the fact store — never invent an id (TL-2.3)",
        kind=_classify_claim(claim, VerificationOutcome.CONTRADICTED),
    )


def _verify_date_duration(claim: Claim, facts: dict) -> VerifiedClaim:
    """Dates/durations map to more places than a single aggregate — check
    the ones we can (`most_overdue_days`, any `delayed_activities[].days_overdue`,
    `schedule_overview.reference_date`) and fall back to UNVERIFIABLE
    otherwise. Never CONTRADICTED here unless the claim is unambiguously
    a specific overdue-days figure that matches no known activity at all
    — a duration mentioned for other reasons (a forecast window, a
    generic estimate) is not "wrong," just outside what this fact store
    can check."""
    insight_data = facts.get("insight_data", {}) or {}
    delayed_activities = facts.get("delayed_activities", []) or []

    if "date" in claim.extracted_values:
        schedule_overview = facts.get("schedule_overview", {}) or {}
        known_dates = {schedule_overview.get("reference_date")}
        known_dates.update(a.get("start_date") for a in delayed_activities)
        known_dates.update(a.get("end_date") for a in delayed_activities)
        known_dates.discard(None)
        if claim.extracted_values["date"] in known_dates:
            return VerifiedClaim(
                claim, VerificationOutcome.VERIFIED,
                "date matches a known fact-store date",
                kind=_classify_claim(claim, VerificationOutcome.VERIFIED),
            )
        return VerifiedClaim(
            claim, VerificationOutcome.UNVERIFIABLE,
            "date does not match any known fact-store date",
            kind=_classify_claim(claim, VerificationOutcome.UNVERIFIABLE),
        )

    number = claim.extracted_values.get("number")
    unit = claim.extracted_values.get("unit", "")
    if unit.lower().startswith(("day", "dage")) and number is not None:
        known_day_counts = {a.get("days_overdue") for a in delayed_activities}
        known_day_counts.add(insight_data.get("most_overdue_days"))
        known_day_counts.discard(None)
        if number in known_day_counts:
            return VerifiedClaim(
                claim, VerificationOutcome.VERIFIED,
                "day count matches a known fact-store value",
                kind=_classify_claim(claim, VerificationOutcome.VERIFIED),
            )
        return VerifiedClaim(
            claim, VerificationOutcome.UNVERIFIABLE,
            "day count does not match any known per-activity or aggregate figure",
            kind=_classify_claim(claim, VerificationOutcome.UNVERIFIABLE),
        )

    return VerifiedClaim(
        claim, VerificationOutcome.UNVERIFIABLE,
        "duration unit not checkable against this fact store",
        kind=_classify_claim(claim, VerificationOutcome.UNVERIFIABLE),
    )


def _verify_superlative(claim: Claim, facts: dict) -> VerifiedClaim:
    """Recompute the ranking (this task's Do section item 1) rather than
    accepting the claim's wording. `summary_by_area` (present in both the
    raw and NUSF paths' final response shape) is the ranking data:
    sorted by `delayed_count` descending, a superlative claim ("largest
    concentration...") is only structurally true if there is a single,
    unambiguous top entry. A tie at the top means no such single
    "largest" exists — the claim is CONTRADICTED regardless of which
    location it names, because the premise ("there is one largest") is
    itself false.

    This does not confirm the claim named the *correct* location —
    `Claim` (from `TL-6.2`) does not currently capture which subject the
    superlative attaches to, only the superlative phrase itself. Fully
    attributing a superlative to a named entity is real future work, not
    silently assumed done here.
    """
    summary_by_area = facts.get("summary_by_area")
    if not summary_by_area:
        return VerifiedClaim(
            claim, VerificationOutcome.UNVERIFIABLE,
            "fact store has no per-area breakdown to rank",
            kind=_classify_claim(claim, VerificationOutcome.UNVERIFIABLE),
        )

    ranked = sorted((row.get("delayed_count", 0) for row in summary_by_area), reverse=True)
    if len(ranked) < 2:
        return VerifiedClaim(
            claim, VerificationOutcome.UNVERIFIABLE,
            "fewer than two areas — no ranking to contradict",
            kind=_classify_claim(claim, VerificationOutcome.UNVERIFIABLE),
        )
    if ranked[0] > ranked[1]:
        return VerifiedClaim(
            claim, VerificationOutcome.VERIFIED,
            f"recomputed ranking confirms a unique top entry ({ranked[0]})",
            kind=_classify_claim(claim, VerificationOutcome.VERIFIED),
        )
    return VerifiedClaim(
        claim, VerificationOutcome.CONTRADICTED,
        f"recomputed ranking is tied at the top ({ranked[0]}) — no single 'largest' exists",
        kind=_classify_claim(claim, VerificationOutcome.CONTRADICTED),
    )


def _verify_causal(claim: Claim) -> VerifiedClaim:
    """Brief §20 / this task's AC: causal claims can never be verified
    from schedule data alone — a schedule records *what* happened and
    *when*, never *why*. This is a categorical rule, not a per-claim
    judgement call; every causal claim is UNVERIFIABLE unconditionally,
    regardless of what fact store is supplied (brief §18's A142 example:
    even with full schedule data, causation is never established)."""
    return VerifiedClaim(
        claim, VerificationOutcome.UNVERIFIABLE,
        "causal claims cannot be verified from schedule data alone (brief §20)",
        kind=_classify_claim(claim, VerificationOutcome.UNVERIFIABLE),
    )


_VERIFIERS = {
    ClaimForm.NUMERIC_QUANTITY: _verify_numeric_quantity,
    ClaimForm.ACTIVITY_ID_REFERENCE: _verify_activity_id_reference,
    ClaimForm.DATE_DURATION: _verify_date_duration,
    ClaimForm.SUPERLATIVE: _verify_superlative,
}


def verify_claim(claim: Claim, facts: dict) -> VerifiedClaim:
    """TL-6.3: verify one claim against `facts` (the deterministic Phase 5
    fact store — see this section's module-level note for its expected
    shape). Dispatches purely on `claim.form`; `CAUSAL` never reaches a
    fact-store lookup at all (see `_verify_causal`)."""
    if claim.form is ClaimForm.CAUSAL:
        return _verify_causal(claim)
    return _VERIFIERS[claim.form](claim, facts)


def verify_claims(claims: Sequence[Claim], facts: dict) -> list[VerifiedClaim]:
    return [verify_claim(c, facts) for c in claims]


@dataclass(frozen=True)
class NarrativeVerificationResult:
    """End-to-end result of extracting and verifying every claim in one
    narrative string.

    - `cleaned_text`: `text` with every `CONTRADICTED` claim's span
      removed outright (this task's Do-not rule: never rewrite a
      contradicted number into the sentence — the old
      `predictive_agent.py` regex-renumbering pattern this supersedes did
      exactly that, and brief calls it "actively harmful" once
      deterministic facts exist to check against instead). Whitespace left
      behind by a removed span is collapsed, not left as a visible gap.
      `TL-6.6` adds: surviving `INFERENCE` claims have their overclaiming
      phrasing (brief §20 — causal verbs, absolute certainty, unhedged
      future assertions) rewritten to hedged form *in this field*.
    - `unverified_claim_texts`: the `UNVERIFIABLE` claims' text, in the
      shape `TL-6.1`'s `AgentResponse.unverified_claims` already expects —
      this is the field TL-6.1 wired through empty, pending this task.
    - `verified`, `contradicted`, `unverifiable`: the full `VerifiedClaim`
      breakdown, for callers that want more than the two summary fields
      above (e.g. `TL-6.4`'s classification, `TL-6.7`'s rate metric).
    - `overclaiming_fixes` (TL-6.6): the audit trail of every phrase
      substitution applied to surviving INFERENCE claims. Empty when no
      hedging was needed; one entry per rewrite applied. Used by
      `TL-6.7`'s instrumentation and by the `harness compare` regression
      report.
    - `decomposable`: propagated from `extract_claims` (AC4) — `False`
      means `text` could not be safely analyzed at all; a caller must
      treat the *entire* text as unverified in that case, not just find
      zero claims in it.
    """

    cleaned_text: str
    unverified_claim_texts: list[str]
    verified: list[VerifiedClaim]
    contradicted: list[VerifiedClaim]
    unverifiable: list[VerifiedClaim]
    decomposable: bool
    overclaiming_fixes: list[str] = field(default_factory=list)


def _remove_spans_exact(text: str, spans: Sequence[tuple[int, int]]) -> str:
    """Remove every span in `spans` from `text`, highest offset first so
    earlier offsets stay valid. Pure deletion only — no whitespace/
    punctuation cleanup (see `_tidy_whitespace` for that) — so the
    resulting length change is *exactly* the sum of the removed spans'
    lengths, which is what `_map_offset_after_removals` assumes when it
    remaps a surviving claim's span onto this text. Mixing cosmetic
    cleanup into this step (as an earlier version of this function did)
    silently invalidates that assumption: `.strip()` and whitespace
    collapsing can shift positions by amounts no span-length arithmetic
    can predict, which is exactly how a real bug slipped through
    (ADR-031) — a surviving claim's remapped span landed a few characters
    off, splicing a hedge into the wrong place. Keeping this function
    length-exact is what makes the remap correct.
    """
    result = text
    for start, end in sorted(spans, key=lambda s: s[0], reverse=True):
        result = result[:start] + result[end:]
    return result


def _tidy_whitespace(text: str) -> str:
    """Collapse the whitespace/punctuation debris a span removal leaves
    behind (a dangling ", ", a doubled space, a space before a period) —
    purely cosmetic, and safe to run exactly once, at the very end of
    `verify_narrative`, after every span-sensitive operation (removal,
    remapping, hedging) is already done. Running this *before* those
    steps (as `_remove_spans` used to) breaks the offset arithmetic they
    depend on — see `_remove_spans_exact`'s docstring."""
    result = re.sub(r"\s*,\s*(?=[.,;:!?]|$)", "", text)
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"\s+([.,;:!?])", r"\1", result)
    return result.strip()


def _map_offset_after_removals(pos: int, removed_spans: Sequence[tuple[int, int]]) -> int:
    """Map `pos` (an offset into the pre-removal text) to its
    corresponding offset in the text produced by `_remove_spans(text,
    removed_spans)`.

    A removed span entirely before `pos` shifts it left by that span's
    full length. A removed span that *contains* `pos` (starts before it,
    ends at or after it) collapses `pos` down to that removal's own start
    — the content between the removal's start and `pos` no longer exists
    in the cleaned text, so there is nowhere else for `pos` to map to.
    The latter case matters because a `CAUSAL` claim's span covers its
    whole enclosing sentence (`TL-6.2`) and is exempt from the extractor's
    overlap suppression against other forms, so a separately-`CONTRADICTED`
    claim can legitimately sit *inside* a surviving causal claim's own
    span (e.g. "A142 is delayed by 18 days, caused by a coordination
    issue." — a fabricated "A142" removed from within the causal claim's
    sentence).
    """
    shift = 0
    for r_start, r_end in removed_spans:
        if r_end <= pos:
            shift += r_end - r_start
        elif r_start < pos:
            shift += pos - r_start
    return pos - shift


def _remap_span_after_removals(
    span: tuple[int, int], removed_spans: Sequence[tuple[int, int]]
) -> tuple[int, int]:
    if not removed_spans:
        return span
    return (
        _map_offset_after_removals(span[0], removed_spans),
        _map_offset_after_removals(span[1], removed_spans),
    )


def verify_narrative(text: Any, facts: dict, language: str = "en") -> NarrativeVerificationResult:
    """TL-6.3 + TL-6.6: the top-level entry point — extract every claim in
    `text` (`TL-6.2`), verify each against `facts`, remove every
    `CONTRADICTED` claim from the text, hedge every `INFERENCE`-classified
    claim's overclaiming phrasing (`TL-6.6`, brief §20), and collect
    every `UNVERIFIABLE` claim's text for `TL-6.1`'s gate to qualify.

    If `text` is not decomposable at all (AC4 — see `extract_claims`), the
    whole text is treated as a single unverifiable unit rather than
    silently passed through: `cleaned_text` is unchanged, but
    `unverified_claim_texts` contains `text` itself and `decomposable` is
    `False`, so a caller (`TL-6.1`'s gate) still ends up qualifying or
    rejecting it rather than rendering it as clean.

    `overclaiming_fixes` (new in TL-6.6) records every phrase
    substitution applied to surviving INFERENCE claims — for logging
    and for `TL-6.7`'s instrumentation. The text in `cleaned_text` is
    already hedged; the list is the audit trail.
    """
    extraction = extract_claims(text)
    if not extraction.decomposable:
        return NarrativeVerificationResult(
            cleaned_text=text if isinstance(text, str) else "",
            unverified_claim_texts=[text] if isinstance(text, str) and text.strip() else [],
            verified=[], contradicted=[], unverifiable=[],
            decomposable=False,
            overclaiming_fixes=[],
        )

    verified_claims = verify_claims(extraction.claims, facts)
    verified = [vc for vc in verified_claims if vc.outcome == VerificationOutcome.VERIFIED]
    contradicted = [vc for vc in verified_claims if vc.outcome == VerificationOutcome.CONTRADICTED]
    unverifiable = [vc for vc in verified_claims if vc.outcome == VerificationOutcome.UNVERIFIABLE]

    # TL-6.3 (Do-not rule): CONTRADICTED claims are removed, never
    # rewritten. Exact deletion only here (no cosmetic cleanup yet — see
    # `_remove_spans_exact`'s docstring) so the length change is exactly
    # predictable and the remap below is correct.
    removed_spans = [vc.claim.span for vc in contradicted]
    cleaned_text = _remove_spans_exact(text, removed_spans) if contradicted else text

    # TL-6.6: hedge surviving INFERENCE claims' overclaiming phrasing
    # (brief §20: predictions must not look like facts). The hedger
    # operates on `cleaned_text`, which is shorter than `text` by however
    # much the removals above deleted — every surviving claim's `span`
    # was computed against the *original* `text` (TL-6.2), so it must be
    # remapped onto `cleaned_text`'s offsets before use here, or the
    # hedger silently locates the wrong stretch of text (or none at all)
    # whenever a CONTRADICTED claim was removed earlier in the same
    # narrative — found empirically: a real, demonstrable case where a
    # genuine INFERENCE-classified causal claim went unhedged because its
    # stale span pointed past the end of the (now shorter) text. See
    # ADR-031. Verified facts (`FACT` / `DERIVED_FACT`) are deliberately
    # NOT hedged — Do-not rule.
    surviving = verified + unverifiable
    if removed_spans:
        surviving = [
            replace(vc, claim=replace(vc.claim, span=_remap_span_after_removals(vc.claim.span, removed_spans)))
            for vc in surviving
        ]
    cleaned_text, overclaiming_fixes = hedge_narrative_overclaiming(
        cleaned_text, surviving, language,
    )

    # Cosmetic whitespace/punctuation cleanup runs last, exactly once —
    # nothing downstream of this point needs span alignment, so it is
    # safe to strip and collapse now (see `_tidy_whitespace`'s docstring
    # for why this must not happen any earlier).
    cleaned_text = _tidy_whitespace(cleaned_text)

    return NarrativeVerificationResult(
        cleaned_text=cleaned_text,
        unverified_claim_texts=[vc.claim.text for vc in unverifiable],
        verified=verified,
        contradicted=contradicted,
        unverifiable=unverifiable,
        decomposable=True,
        overclaiming_fixes=overclaiming_fixes,
    )


# ============================================================================
# TL-6.4 — Field-level `ClaimKind` map (brief §19, §20)
# ============================================================================
# `_classify_claim` (above) tags extracted narrative claims. But many
# model-attributed fields — `forcing_assessment[]`, `predictive_biggest_risk`,
# the per-area `summary` sentences — never go through extraction: they
# are top-level model output, not narrative prose to be checked. Brief
# §19 ("Never present inference as fact") and §20 (causal/forecast
# framing must be hedged) both apply to them as much as to extracted
# claims, so they need the same epistemic-status tag.
#
# This map mirrors `FIELD_EVIDENCE_CLASSIFICATIONS` (`TL-5.6`,
# `predictive_agent.py`) in shape — every section and field is named
# explicitly, no implicit default — but uses the `ClaimKind` taxonomy
# (brief §19) rather than the `EvidenceClass` taxonomy (brief §45). The
# two are deliberately *parallel*, not duplicated: `EvidenceClass` is
# "what kind of evidence backs this value" (for the renderer's visual
# distinction), `ClaimKind` is "what epistemic status does this
# statement have" (for the renderer's truth-distinction). The mapping
# is exact for the easy cases:
#
#     SOURCE_DATA       → FACT          (verbatim from source)
#     NOVA_CALCULATION  → DERIVED_FACT  (deterministic Python)
#     NOVA_INSIGHT      → INFERENCE     (model interpretation)
#     NOVA_FORECAST     → INFERENCE     (model forecast — still inference)
#
# but is encoded directly in the table below rather than derived, so
# `TL-5.6` and `TL-6.4` can diverge if a future section's epistemic
# status needs to be different from its evidence class (e.g. a derived
# forecast that is still a `DERIVED_FACT` rather than `INFERENCE`).
#
# Brief Do item 2 — "LLM-inferred critical path (TL-4.4) and forcing
# assessment (TL-5.4) are INFERENCE by construction — enforce, do not
# rely on classification at runtime" — is enforced by the table below:
# every field in `forcing_assessment[]` is `INFERENCE` regardless of
# what the model's output looks like at runtime.

FIELD_CLAIM_KINDS: dict = {
    # Top-level scalars
    "management_conclusion": ClaimKind.INFERENCE,
    # predictive_snapshot — forecast and insight, never fact
    "predictive_snapshot": {
        "what_will_happen": ClaimKind.INFERENCE,        # forward-looking (forecast-shaped, even when zero-delay structural)
        "estimated_delay_impact": ClaimKind.INFERENCE,  # forecast window
        "confidence_level": ClaimKind.DERIVED_FACT,     # HIGH/MEDIUM/LOW is rule-based (TL-5.6)
        "confidence_basis": ClaimKind.INFERENCE,        # model's explanation of confidence
        "main_delay_drivers": ClaimKind.INFERENCE,      # model categorisation
    },
    # predictive_biggest_risk — risk framing is always interpretive
    "predictive_biggest_risk": {
        "risk_title": ClaimKind.INFERENCE,
        "will_block": ClaimKind.INFERENCE,              # forward-looking claim
        "prevent_action_now": ClaimKind.INFERENCE,      # forward-looking imperative
    },
    # executive_actions — TOP 3 imperative moves; the imperative itself is
    # forward-looking even when the surrounding facts are deterministic.
    "executive_actions": {
        "rank": ClaimKind.INFERENCE,
        "action": ClaimKind.INFERENCE,                  # forward-looking imperative
        "responsible": ClaimKind.INFERENCE,
        "deadline": ClaimKind.DERIVED_FACT,             # today + arithmetic, deterministic
        "related_task_ids": ClaimKind.FACT,             # ids lifted from source
        "manpower_helps": ClaimKind.INFERENCE,
        "manpower_note": ClaimKind.INFERENCE,
    },
    # schedule_overview — lifted from the source / deterministic
    "schedule_overview": {
        "schedule_name": ClaimKind.FACT,
        "reference_date": ClaimKind.FACT,
        "total_activities": ClaimKind.DERIVED_FACT,
        "delayed_count": ClaimKind.DERIVED_FACT,
        "areas_covered": ClaimKind.FACT,
        "format_detected": ClaimKind.DERIVED_FACT,
    },
    # delayed_activities — per-item, deterministic counts/types, source for ids/dates
    "delayed_activities": {
        "id": ClaimKind.FACT,
        "task_name": ClaimKind.FACT,
        "human_label": ClaimKind.INFERENCE,             # model-generated label
        "start_date": ClaimKind.FACT,
        "end_date": ClaimKind.FACT,
        "duration": ClaimKind.FACT,
        "progress": ClaimKind.FACT,
        "days_overdue": ClaimKind.DERIVED_FACT,
        "task_type": ClaimKind.DERIVED_FACT,
        "priority": ClaimKind.DERIVED_FACT,
        "is_root_cause": ClaimKind.DERIVED_FACT,
        "blocked_by_id": ClaimKind.FACT,
        "area": ClaimKind.FACT,
    },
    # root_cause_analysis — source for ids, calculation for days/problem_type,
    # inference for the model's narrative ("why_it_matters" etc.)
    "root_cause_analysis": {
        "id": ClaimKind.FACT,
        "task_name": ClaimKind.FACT,
        "human_label": ClaimKind.INFERENCE,
        "days_overdue": ClaimKind.DERIVED_FACT,
        "problem_type": ClaimKind.DERIVED_FACT,
        "why_it_matters": ClaimKind.INFERENCE,
        "downstream_impact": ClaimKind.INFERENCE,
        "consequence_if_unresolved": ClaimKind.INFERENCE,
        "affected_task_ids": ClaimKind.FACT,
    },
    # downstream_consequences — sourced from the dependency graph
    "downstream_consequences": {
        "id": ClaimKind.FACT,
        "task_name": ClaimKind.FACT,
        "human_label": ClaimKind.INFERENCE,
        "blocked_by_id": ClaimKind.FACT,
    },
    # priority_actions — model's prioritised list of actions to take
    "priority_actions": {
        "step": ClaimKind.DERIVED_FACT,
        "action": ClaimKind.INFERENCE,
        "action_type": ClaimKind.DERIVED_FACT,
    },
    # resource_assessment — model's interpretive judgement on resource bottlenecks
    "resource_assessment": {
        "id": ClaimKind.FACT,
        "task_name": ClaimKind.FACT,
        "human_label": ClaimKind.INFERENCE,
        "resource_type": ClaimKind.INFERENCE,
        "assessment": ClaimKind.INFERENCE,
    },
    # forcing_assessment — Brief Do item 2: every field is INFERENCE by
    # construction. Enforced here, not at runtime.
    "forcing_assessment": {
        "id": ClaimKind.FACT,
        "task_name": ClaimKind.FACT,
        "human_label": ClaimKind.INFERENCE,
        "is_forceable": ClaimKind.INFERENCE,
        "constraint_type": ClaimKind.INFERENCE,
        "reason": ClaimKind.INFERENCE,
        "risk_if_forced": ClaimKind.INFERENCE,
        "recommendation": ClaimKind.INFERENCE,
        "coordination_cost": ClaimKind.INFERENCE,
        "parallelizability": ClaimKind.INFERENCE,
        "max_speedup_factor": ClaimKind.INFERENCE,
        "optimal_team_size": ClaimKind.INFERENCE,
        "point_of_no_return": ClaimKind.INFERENCE,
    },
    # summary_by_area — counts are derived; the per-area `summary` is model prose
    "summary_by_area": {
        "area": ClaimKind.FACT,
        "delayed_count": ClaimKind.DERIVED_FACT,
        "critical_count": ClaimKind.DERIVED_FACT,
        "important_count": ClaimKind.DERIVED_FACT,
        "monitor_count": ClaimKind.DERIVED_FACT,
        "summary": ClaimKind.INFERENCE,
    },
    # insight_data — almost entirely DERIVED_FACT (counts); narrative fields are inference
    "insight_data": {
        "total_activities": ClaimKind.DERIVED_FACT,
        "delayed_count": ClaimKind.DERIVED_FACT,
        "critical_count": ClaimKind.DERIVED_FACT,
        "important_count": ClaimKind.DERIVED_FACT,
        "monitor_count": ClaimKind.DERIVED_FACT,
        "root_cause_count": ClaimKind.DERIVED_FACT,
        "reference_date": ClaimKind.FACT,
        "most_overdue_days": ClaimKind.DERIVED_FACT,
        "areas_affected": ClaimKind.DERIVED_FACT,
        "format_detected": ClaimKind.DERIVED_FACT,
        "schedule_name": ClaimKind.FACT,
        "primary_risk": ClaimKind.INFERENCE,
        "forceable_count": ClaimKind.DERIVED_FACT,
        "not_forceable_count": ClaimKind.DERIVED_FACT,
        "project_status": ClaimKind.DERIVED_FACT,
        "risk_level": ClaimKind.DERIVED_FACT,
        "unverified_delayed_count": ClaimKind.DERIVED_FACT,
        "critical_findings": ClaimKind.INFERENCE,
        "consequences_if_no_action": ClaimKind.INFERENCE,
    },
}


def build_field_claim_kinds(parsed_json: dict) -> dict:
    """TL-6.4: emit a per-(section, field) `ClaimKind` map for the merged
    response, parallel to TL-5.6's `EvidenceClass` `_classification`.

    This is the *field-level* epistemic status for everything in the
    response that does NOT go through extraction (the `forcing_assessment`
    table, the per-area `summary` sentences, etc.). Per-claim `kind`
    for extracted narrative lives on each `VerifiedClaim` (TL-6.3) and
    is computed by `_classify_claim` (above); this function covers
    everything else.

    Like `FIELD_EVIDENCE_CLASSIFICATIONS` (`TL-5.6`), the map is
    exhaustive — every entry is named, no implicit default. A field
    present in `parsed_json` but missing from `FIELD_CLAIM_KINDS` raises
    `ValueError`. That is what enforces brief Do item 2's "do not rely
    on classification at runtime": the table is the contract, not a
    heuristic at the renderer.
    """
    classification: dict = {}
    for section_name, section_value in parsed_json.items():
        if section_name.startswith("_"):
            continue
        classification_for_section = FIELD_CLAIM_KINDS.get(section_name)
        if classification_for_section is None:
            raise ValueError(
                f"TL-6.4: section {section_name!r} is present in the response "
                f"but has no classification in FIELD_CLAIM_KINDS. Add an explicit "
                f"entry — do not let it default."
            )
        if isinstance(classification_for_section, ClaimKind):
            classification[section_name] = classification_for_section.value
            continue
        if isinstance(section_value, list):
            if not section_value:
                classification[section_name] = {
                    field: cls.value for field, cls in classification_for_section.items()
                }
                continue
            first_item = section_value[0]
            if not isinstance(first_item, dict):
                raise ValueError(
                    f"TL-6.4: section {section_name!r} items must be dicts, "
                    f"got {type(first_item).__name__}"
                )
            classification[section_name] = {}
            for field_name in first_item.keys():
                if field_name not in classification_for_section:
                    raise ValueError(
                        f"TL-6.4: field {section_name!r}.{field_name!r} is present "
                        f"in the response but has no ClaimKind. Add an explicit entry."
                    )
                classification[section_name][field_name] = (
                    classification_for_section[field_name].value
                )
        elif isinstance(section_value, dict):
            classification[section_name] = {}
            for field_name in section_value.keys():
                if field_name not in classification_for_section:
                    raise ValueError(
                        f"TL-6.4: field {section_name!r}.{field_name!r} is present "
                        f"in the response but has no ClaimKind. Add an explicit entry."
                    )
                classification[section_name][field_name] = (
                    classification_for_section[field_name].value
                )
        else:
            classification[section_name] = classification_for_section.value
    return classification


# ============================================================================
# TL-6.6 — Language guardrails (brief §20, §46)
# ============================================================================
# Brief §20: *"Never make a prediction visually indistinguishable from an
# observed fact."* The phrasing matters to construction professionals.
# A `INFERENCE` or `NOVA_FORECAST` statement must NOT use fact-grade phrasing
# — unhedged future assertions ("will be delayed"), unestablished causal
# verbs ("caused by", "due to"), or absolute certainty adverbs ("definitely",
# "always", "never") applied to a claim the data does not prove.
#
# This module implements the *enforcement* layer — the prompt update
# (`PREDICTIVE_NARRATIVE_SYSTEM_PROMPT`) is the last layer per brief §34,
# and a prompt alone is never enough. The deterministic check below is the
# gate: when the model produces overclaiming prose for an INFERENCE-class
# statement, the overclaiming words are rewritten to hedged form
# (`check_overclaiming` reports the issue; `hedge_overclaiming` applies
# the rewrite) before the response reaches the renderer.
#
# Brief §20 worked pairs this task pins:
#   WRONG: "The project will be delayed"            → RIGHT: "The current schedule pattern indicates increased delay risk"
#   WRONG: "Electrical work caused the delay"        → RIGHT: "The largest concentration of current delay is within electrical activities"
#
# Verified facts are NOT over-hedged (Do-not rule: "do not hedge
# `DERIVED_FACT` statements — precision cuts both ways"). Only
# `INFERENCE`-classified text triggers the rewrites; `FACT` and
# `DERIVED_FACT` pass through unchanged.

# Overclaiming phrase → hedged replacement, per language. Keys are
# regex patterns; values are the hedged substitutions (preserving the
# surrounding text via group back-references where possible). Patterns
# are deliberately conservative — a false positive rewrites a phrase the
# data can support; a false negative lets fact-grade phrasing through on
# an inference. Brief §34's "architecture, not prompts" rule means we
# err in the direction of *more* rewriting on INFERENCE text, not less.
_OVERCLAIMING_PATTERNS: dict[str, dict[str, str]] = {
    "en": {
        # Causal verbs — brief §20's headline concern
        r"\bcaused by\b": "associated with",
        r"\bcaused the\b": "is associated with the",
        r"\bcaused\b": "is associated with",
        r"\bcauses the\b": "is associated with",
        r"\bcauses\b": "is associated with",
        r"\bcausing the\b": "associated with the",
        r"\bcausing\b": "associated with",
        r"\bdue to\b": "consistent with",
        r"\bbecause of\b": "consistent with",
        r"\bas a result of\b": "in the same period as",
        r"\bresulting from\b": "following",
        r"\bleads? to\b": "is followed by",
        r"\bled to\b": "was followed by",
        r"\bresults? in\b": "coincides with",
        r"\bresulted in\b": "coincided with",
        r"\bis responsible for\b": "is associated with",
        # Unhedged future assertions on INFERENCE text
        r"\bwill be delayed\b": "shows a pattern of delay",
        r"\bwill fail\b": "is at risk of failing",
        r"\bwill definitely\b": "is likely to",
        r"\bwill certainly\b": "is likely to",
        # Absolute certainty adverbs — brief §20's other concern
        r"\bdefinitely\b": "likely",
        r"\bcertainly\b": "likely",
        r"\bundoubtedly\b": "probably",
        r"\bunquestionably\b": "probably",
    },
    "da": {
        # Causal verbs — Danish (Kemp is Danish-only per brief §46)
        r"\bforårsaget af\b": "forbundet med",
        r"\bforårsager\b": "er forbundet med",
        r"\bforårsagede\b": "var forbundet med",
        r"\bpå grund af\b": "konsistent med",
        r"\bskyldes\b": "kan tilskrives",
        r"\bsom følge af\b": "i samme periode som",
        r"\bfører til\b": "efterfølges af",
        r"\bresulterer i\b": "sammenfaldende med",
        # Unhedged future assertions
        r"\bvil blive forsinket\b": "viser et mønster af forsinkelse",
        r"\bvil fejle\b": "er i risiko for at fejle",
        r"\bvil helt sikkert\b": "vil sandsynligvis",
        r"\bvil bestemt\b": "vil sandsynligvis",
        # Absolute certainty adverbs
        r"\bhelt sikkert\b": "sandsynligvis",
        r"\bbestemt\b": "sandsynligvis",
        r"\babsolut\b": "sandsynligvis",
        r"\butvivlsomt\b": "sandsynligvis",
    },
}


def check_overclaiming(
    text: str,
    kind: ClaimKind,
    language: str = "en",
) -> list[str]:
    """TL-6.6: detect overclaiming phrases in `text` given its epistemic
    `kind`.

    Returns a list of issue descriptions (one per detected phrase). An
    empty list means no overclaiming — the text is either properly hedged
    for its kind, or the kind is `FACT` / `DERIVED_FACT` (which are
    exempt from the check per the Do-not rule).

    `INFERENCE` and `UNKNOWN` claims are both checked — an
    UNVERIFIABLE forecast whose form is `DATE_DURATION` (e.g. "the
    project will be delayed by 4-8 weeks") classifies as `UNKNOWN` per
    TL-6.4's table, but the *prose* is INFERENCE-shaped and the
    hedging must apply. `FACT` and `DERIVED_FACT` return `[]`
    unconditionally — verified facts must be allowed to speak directly
    (brief §20's "Electrical work caused the delay" is wrong on an
    INFERENCE; on a verified FACT, the same phrasing is fine because
    causality is established).
    """
    if not text or kind in (ClaimKind.FACT, ClaimKind.DERIVED_FACT):
        return []
    patterns = _OVERCLAIMING_PATTERNS.get(language, _OVERCLAIMING_PATTERNS["en"])
    issues: list[str] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE):
            issues.append(f"overclaiming ({kind.value}, {language}): pattern {pattern!r}")
    return issues


def hedge_overclaiming(
    text: str,
    kind: ClaimKind,
    language: str = "en",
) -> tuple[str, list[str]]:
    """TL-6.6: rewrite overclaiming phrases in `text` to hedged form,
    given its epistemic `kind`.

    Returns `(hedged_text, list_of_fixes)` — the rewritten text and the
    list of patterns that were replaced. An empty list means no rewrite
    was needed. The text is returned unchanged for `FACT` /
    `DERIVED_FACT` (verified facts must speak directly per the
    Do-not rule).

    As with `check_overclaiming`, both `INFERENCE` and `UNKNOWN` claims
    are hedged — `UNKNOWN`-classified forecasts have INFERENCE-shaped
    prose and the rewrite applies. `FACT` / `DERIVED_FACT` are
    untouched.

    Rewrites are conservative — phrase substitutions only, never full
    sentence rewrites. The brief §20 worked pairs are NOT produced by
    a single regex swap (e.g. "will be delayed" → "the pattern indicates
    delay risk" is a structural change). What this function does is the
    *minimum* correction: remove the fact-grade assertion that violates
    brief §20's headline rule ("predictions must not look like facts"),
    keep the rest of the sentence intact, and let the renderer / TL-7.3
    handle the full UX-level framing.
    """
    if not text or kind in (ClaimKind.FACT, ClaimKind.DERIVED_FACT):
        return text, []
    patterns = _OVERCLAIMING_PATTERNS.get(language, _OVERCLAIMING_PATTERNS["en"])
    hedged = text
    fixes: list[str] = []
    for pattern, replacement in patterns.items():
        if re.search(pattern, hedged, flags=re.IGNORECASE | re.UNICODE):
            hedged = re.sub(
                pattern, replacement, hedged,
                flags=re.IGNORECASE | re.UNICODE,
            )
            fixes.append(f"{pattern!r} → {replacement!r}")
    return hedged, fixes


def hedge_narrative_overclaiming(
    text: str,
    claims: Sequence,
    language: str = "en",
) -> tuple[str, list[str]]:
    """TL-6.6: walk each surviving INFERENCE claim, expand its span to
    the enclosing sentence (overclaiming prose often sits in surrounding
    text, not in the extracted claim itself — e.g. *"will be delayed"*
    is prose around a `DATE_DURATION` claim of *"4-8 weeks"*), apply
    `hedge_overclaiming` to that sentence-level text, and substitute it
    back into the narrative. Returns `(hedged_text, fixes)` — the
    rewritten narrative and a flat list of every fix applied (for
    logging / `harness compare` instrumentation).

    `FACT` / `DERIVED_FACT` claims are skipped (verified facts speak
    directly, Do-not rule). `CAUSAL` claims are `INFERENCE` per TL-6.4
    (brief §20: causal prose is always inference); their extractor
    already captures the whole enclosing sentence as the claim text, so
    expansion is a no-op for them.

    The text-rebuild mirrors `verify_narrative`'s `_remove_spans_exact` —
    process spans highest-offset-first so earlier offsets stay valid.

    Claims are grouped by their (expanded) enclosing-sentence bounds
    before splicing, not spliced once per claim: a sentence can carry
    more than one hedge-worthy claim at once (e.g. a `CAUSAL` claim and a
    separately-`UNVERIFIABLE` `DATE_DURATION` claim in the same sentence
    — "A142 is delayed by 18 days, caused by a coordination issue."
    yields both). Splicing the same sentence range independently for each
    claim corrupts the text: the second splice runs against offsets that
    the first splice already invalidated. Found empirically (ADR-031) —
    duplicated trailing text ("...issue.issue.") from exactly this case.
    """
    if not text or not claims:
        return text, []

    # Group hedge-worthy claims by their exact enclosing-sentence bounds
    # (two claims in the same real sentence always resolve to the same
    # bounds, since `_enclosing_sentence_bounds` is a pure function of
    # `text` and sentence-boundary punctuation) so each sentence is
    # hedged and spliced exactly once, even when several claims land in
    # it.
    bounds_to_kinds: dict[tuple[int, int], list[ClaimKind]] = {}
    for verified_claim in claims:
        if verified_claim.kind in (ClaimKind.FACT, ClaimKind.DERIVED_FACT):
            continue
        bounds = _enclosing_sentence_bounds(text, verified_claim.claim.span)
        bounds_to_kinds.setdefault(bounds, []).append(verified_claim.kind)

    replacements: list[tuple[tuple[int, int], str, list[str]]] = []
    for (sentence_start, sentence_end), kinds in bounds_to_kinds.items():
        sentence_text = text[sentence_start:sentence_end]
        hedged_sentence = sentence_text
        fixes: list[str] = []
        # One hedge pass per distinct kind present in the sentence. Each
        # pass is idempotent on phrases the previous pass already
        # rewrote (a causal-verb pattern no longer matches its own
        # hedged replacement), so applying more than one kind's patterns
        # to the same sentence is safe.
        for kind in set(kinds):
            hedged_sentence, kind_fixes = hedge_overclaiming(hedged_sentence, kind, language)
            fixes.extend(kind_fixes)
        if fixes and hedged_sentence != sentence_text:
            replacements.append(((sentence_start, sentence_end), hedged_sentence, fixes))

    if not replacements:
        return text, []

    # Highest-offset first so earlier spans stay valid as we splice.
    replacements.sort(key=lambda r: r[0][0], reverse=True)
    result = text
    all_fixes: list[str] = []
    for span, hedged_text, fixes in replacements:
        all_fixes.extend(fixes)
        result = result[:span[0]] + hedged_text + result[span[1]:]
    return result, all_fixes


# ============================================================================
# TL-6.7 — Unsupported factual claim rate (brief §39)
# ============================================================================
# Brief §39: *"How often does Nova state a factual claim that cannot be
# traced to verified source data? Target: 0 unsupported factual claims.
# That is more strategically valuable than making the agent sound
# intelligent."*
#
# `CONTRADICTED` claims (TL-6.3) are the headline failure mode — the system
# knew the claim was false (or had no handle to verify it) and removed it
# from the narrative. Each one is a defect, not a rounding error
# (Do-not rule: "Do not average this away across many claims"). The metric
# below counts them across a standing suite of test narratives and
# reports the rate + every offending claim text in `harness compare`.

@dataclass(frozen=True)
class UnsupportedClaimMetric:
    """Brief §39: aggregate unsupported-factual-claim rate across one
    or more `verify_narrative` runs.

    `unsupported_count` is the number of CONTRADICTED claims — those are
    the headline failure mode (the system caught them and removed them;
    a renderer that showed them would be a worst-case misrepresentation
    per brief §16). `unverifiable_count` is reported separately so a
    caller can distinguish "the data proved it wrong" (CONTRADICTED)
    from "the data had no way to check it" (UNVERIFIABLE) — the latter
    is also bad (brief §16: "unparseable narrative... is treated as
    unverified, not as safe") but is a different class of failure.

    `meets_target` is the brief §39 invariant — `True` iff
    `unsupported_count == 0`. `harness compare` reports this metric as
    its own line per the AC.
    """

    verified_count: int
    contradicted_count: int
    unverifiable_count: int
    total_claims: int

    @property
    def unsupported_count(self) -> int:
        """Brief §39's count: claims removed because the system caught
        them as false / unverifiable-as-fact. CONTRADICTED is the
        headline case (TL-6.3 Do-not rule: "removing the claim" is the
        only safe response to a contradicted fact)."""
        return self.contradicted_count

    @property
    def unsupported_rate(self) -> float:
        """Fraction of all factual claims that were contradicted. Zero
        is the target. A non-zero rate is a defect (Do-not rule)."""
        if self.total_claims <= 0:
            return 0.0
        return self.contradicted_count / self.total_claims

    def meets_target(self) -> bool:
        return self.unsupported_count == 0


def compute_unsupported_claim_metric(
    results: Sequence[NarrativeVerificationResult],
) -> UnsupportedClaimMetric:
    """TL-6.7: aggregate unsupported-factual-claim rate across a batch
    of `verify_narrative` runs. Sums the verified/contradicted/
    unverifiable counts from every result; the brief §39 metric is
    `unsupported_count / total_claims` (a fraction, not a count of
    fixture failures — one CONTRADICTED in a 1000-claim run is still
    a defect)."""
    verified = sum(len(r.verified) for r in results)
    contradicted = sum(len(r.contradicted) for r in results)
    unverifiable = sum(len(r.unverifiable) for r in results)
    total = verified + contradicted + unverifiable
    return UnsupportedClaimMetric(
        verified_count=verified,
        contradicted_count=contradicted,
        unverifiable_count=unverifiable,
        total_claims=total,
    )


def collect_unsupported_claims(
    results: Sequence[NarrativeVerificationResult],
    question_ids: Sequence[str],
) -> list[tuple[str, str]]:
    """TL-6.7 / AC3: enumerate the specific unsupported claims so a
    non-zero rate can be inspected. Returns a list of
    `(question_id, claim_text)` pairs — one per CONTRADICTED claim,
    tagged with the originating question so the report is actionable.

    `question_ids[i]` names the question that produced `results[i]`;
    they must be the same length.
    """
    if len(question_ids) != len(results):
        raise ValueError(
            f"question_ids ({len(question_ids)}) and results ({len(results)}) "
            f"lengths must match"
        )
    out: list[tuple[str, str]] = []
    for qid, result in zip(question_ids, results):
        for vc in result.contradicted:
            out.append((qid, vc.claim.text))
    return out


def _enclosing_sentence_bounds(
    text: str, span: tuple[int, int]
) -> tuple[int, int]:
    """TL-6.6 helper: return the `(start, end)` offsets of the sentence(s)
    that contain `span`. A sentence boundary is `[.!?]` followed by
    whitespace. If no boundaries exist before/after `span`, returns
    the start/end of `text` (the whole text is one sentence fragment).
    """
    start, end = span
    # Find the most recent sentence boundary at or before `start`
    preceding = text[:start]
    sentence_start = 0
    last_boundary = None
    for boundary in re.finditer(r"[.!?]\s+", preceding):
        last_boundary = boundary
    if last_boundary is not None:
        sentence_start = last_boundary.end()

    # Find the first sentence boundary at or after `end`
    end_match = re.search(r"[.!?]\s+", text[end:])
    sentence_end = end + end_match.end() if end_match else len(text)

    return (sentence_start, sentence_end)
