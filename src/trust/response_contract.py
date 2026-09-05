"""Agent response contract & rendering gate (TL-6.1, brief §33, §34).

Brief §33 specifies the internal structure every agent answer must carry
before it is allowed near a user:

    answer, supporting_facts[], source_references[], confidence_state,
    inferences[], unverified_claims[]

Brief §34 is the reason this is a module, not a convention: *"Prompt rules
are the last layer, not the safety architecture."* A docstring telling
callers "please gate on unverified_claims" is not enforcement. This module
makes the gate structural instead:

- `AgentResponse` is the only shape an agent may hand upstream. It is a
  plain, ungated data container — anyone can build one.
- `ValidatedResponse` is the only shape any renderer may accept. It can
  ONLY be constructed by `validate_agent_response()` — direct construction
  raises `RuntimeError` (see `_GATE_TOKEN`). There is no code path that
  turns an `AgentResponse` (or a bare string) into rendered text without
  passing through the brief §33 gate.
- `render_validated_response()` is the only function permitted to produce
  final text, and it runtime-type-checks its argument — a caller cannot
  hand it a raw string or an unvalidated `AgentResponse` and have it work.

This closes exactly the loophole TL-6.1's own "Do not" rule names: no
bypass flag exists for "trusted" callers, because there is no parameter
that skips the gate at all — only a choice of which brief §33 behaviour
(`remove` / `qualify` / `reject` / `no_answer`) applies when
`unverified_claims` is non-empty.

`TL-6.2` (claim extraction) and `TL-6.3` (verification against the fact
store) do not exist yet. Until they land, no agent has a real mechanism to
populate `unverified_claims` claim-by-claim from generated narrative text —
that is precisely their job. This module's job is narrower and already
useful on its own: make the six-field contract and the render gate
structurally real *now*, so every agent response already flows through it
(brief §33's own AC: "the render path accepts only validated response
objects"), and `TL-6.2`/`TL-6.3` only need to start *populating*
`unverified_claims`/`inferences` with real content — not invent the pipe
they travel through.

`TL-6.5` extends the contract with a first-class *no-answer* response
type (brief §18, §42): when the user asks a question the data cannot
answer (most often a causal/"why" question — see brief §20), Nova
acknowledges what is known, names what cannot be determined, and offers
a constructive next step. This is a *valid response shape*, not an error
banner — both apps render it as a normal result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from src.trust.vocabulary import TrustState

# Only `validate_agent_response` holds this object. A `ValidatedResponse`
# constructed without it raises — see `ValidatedResponse.__post_init__`.
_GATE_TOKEN = object()


class GatePolicy(str, Enum):
    """Which brief §33 behaviour applies when `AgentResponse.unverified_claims`
    is non-empty. Deliberately exhaustive and deliberately missing a fourth
    "skip the gate" option — see the module's Do-not rule."""

    REMOVE = "remove"
    QUALIFY = "qualify"
    REJECT = "reject"


class GateDecision(str, Enum):
    """What `validate_agent_response` actually did, recorded on the
    resulting `ValidatedResponse` so a caller (or a test) can tell an
    untouched answer apart from one the gate intervened on."""

    ANSWERED = "answered"  # no unverified claims, or REMOVE resolved all of them
    QUALIFIED = "qualified"  # unverified claims remain; a disclaimer was appended
    REJECTED = "rejected"  # REJECT policy fired; the original answer was withheld
    NO_ANSWERED = "no_answered"  # TL-6.5: structured no-answer response rendered (brief §18)


@dataclass(frozen=True)
class NoAnswerInfo:
    """TL-6.5: structured no-answer (brief §18, §42).

    A first-class response shape, not an error. Carries three parts:

    - `known`: verified facts about the situation (e.g. "A142 is delayed
      by 18 days"). Always non-empty for a meaningful no-answer —
      without it, "I cannot verify" becomes an unhelpful dead-end.
    - `cannot_verify`: the specific claim(s) the user asked about that
      cannot be established from the uploaded data (e.g. "the cause of
      A142's delay"). Required to be non-empty — this is what makes
      the response a *no-answer* rather than a regular partial answer.
    - `next_step`: a constructive suggestion for what the user can do
      next (brief §18's worked example: "I can show you the predecessor
      activities and recent schedule changes").
    - `language`: the language the response text is rendered in. Pinned
      here rather than on the renderer so the validator can produce the
      right text directly (`validate_agent_response` is the only path
      to a rendered `ValidatedResponse`, per TL-6.1's gate).

    Brief §42 says a no-answer must read as reassuring, not broken. The
    template below (`build_no_answer_response`) is deliberately short,
    specific about what could not be confirmed, and never alarming.
    """

    known: tuple[str, ...]
    cannot_verify: tuple[str, ...]
    next_step: str
    language: str = "en"


@dataclass(frozen=True)
class AgentResponse:
    """Brief §33's six-field contract, extended with `no_answer` (TL-6.5).
    Any agent may construct one freely — it carries no guarantee on its
    own; only `validate_agent_response` turns it into something a renderer
    may touch.

    - `answer`: the narrative text the agent produced.
    - `supporting_facts`: verified statements backing `answer` (Phase 5
      deterministic facts, not narrative prose).
    - `source_references`: evidence pointers grounding those facts —
      typically activity ids (never invented ones — Phase 2's contract).
    - `confidence_state`: the overall trust state for this answer, reusing
      `TrustState` (`TL-0.4`) rather than inventing a parallel vocabulary.
    - `inferences`: statements that go beyond directly verified fact —
      judgement, forecast, or interpretation (formal `ClaimKind` tagging is
      `TL-6.4`; until then this is a plain-text list).
    - `unverified_claims`: statements the agent could not verify. Non-empty
      is what triggers the gate in `validate_agent_response`.
    - `no_answer`: when set, `validate_agent_response` renders the brief
      §18 three-part response instead of the normal answer. Mutually
      exclusive with a substantive answer by construction: setting
      `no_answer` short-circuits the gate (no QUALIFY/REMOVE/REJECT
      applies because the response is the structured no-answer).
    """

    answer: str
    supporting_facts: list[str] = field(default_factory=list)
    source_references: list[str] = field(default_factory=list)
    confidence_state: TrustState = TrustState.UNVERIFIED
    inferences: list[str] = field(default_factory=list)
    unverified_claims: list[str] = field(default_factory=list)
    no_answer: Optional[NoAnswerInfo] = None


# Brief §16's own worked qualifier ("Critical status could not be verified
# for all activities.") is the model for both languages here — short,
# specific about what could not be confirmed, never alarming (brief §42:
# uncertainty should read as reassuring, not broken — TL-7.8 owns the full
# UX treatment; this is the text-level default until then).
_UNVERIFIED_QUALIFIER = {
    "en": "Note: {n} statement(s) in this answer could not be independently verified from the uploaded schedule data.",
    "da": "Bemærk: {n} udsagn i dette svar kunne ikke verificeres uafhængigt ud fra de uploadede tidsplandata.",
}

_REJECTED_ANSWER = {
    "en": "Nova could not verify enough of this answer against the uploaded schedule data to present it with confidence.",
    "da": "Nova kunne ikke verificere tilstrækkeligt af dette svar ud fra de uploadede tidsplandata til at præsentere det med sikkerhed.",
}


# ============================================================================
# TL-6.5 — No-answer detection and rendering (brief §18, §42)
# ============================================================================

# Trigger words that mark a question as asking for causality or root
# cause — almost always unanswerable from schedule data alone (brief
# §20's own framing: a schedule records *what* and *when*, never *why*).
# The list is deliberately conservative: a false negative means the
# question gets the normal gate treatment (still gated, still verified
# claim-by-claim); a false positive means a regular question gets the
# no-answer shape and the user is told "I can't verify this" when the
# system actually has the data. The latter is the worse failure mode,
# so the list errs on the side of fewer triggers.
_NO_ANSWER_TRIGGERS = (
    # English — explicit causal/unanswerable patterns
    r"\bwhy\b",
    r"\bwhat caused\b",
    r"\bwhat is causing\b",
    r"\bwhat'?s causing\b",
    r"\bcaused by\b",
    r"\bdue to\b",
    r"\bbecause of\b",
    r"\bwhat led to\b",
    r"\bwhat'?s blocking\b",
    r"\bwhat is blocking\b",
    r"\bwhat is preventing\b",
    r"\bwhat'?s preventing\b",
    r"\breason for\b",
    r"\broot cause\b",
    r"\bunderlying cause\b",
    r"\bwhy is\b",
    r"\bwhy are\b",
    # Danish — same shapes
    r"\bhvorfor\b",
    r"\bårsag til\b",
    r"\bforårsaget af\b",
    r"\bgrund til\b",
    r"\bhvad forårsager\b",
    r"\bhvad skyldes\b",
    r"\bhvad blokerer\b",
    r"\bhvad forhindrer\b",
)
_NO_ANSWER_PATTERN = re.compile(
    r"|".join(_NO_ANSWER_TRIGGERS),
    re.IGNORECASE | re.UNICODE,
)


def is_causal_question(question: str) -> bool:
    """TL-6.5: True if the question asks for causality or root cause —
    typically unanswerable from schedule data alone (brief §20).

    Conservative by design — see the trigger list's note. A regular
    question that contains one of these patterns as a *non*-causal
    mention (e.g. "is this caused by your system, or is it the data?")
    is fine to no-answer; the worst failure mode is telling a user
    "I can't verify this" when the system actually has the answer, and
    that is the direction we err against.
    """
    return bool(question and _NO_ANSWER_PATTERN.search(question))


_NO_ANSWER_TEMPLATES = {
    "en": {
        "header": "I cannot verify that from the uploaded schedules.",
        "known_prefix": "What I can confirm:",
        "unknown_prefix": "What cannot be determined:",
        "next_step_prefix": "What you can do next:",
    },
    "da": {
        "header": "Jeg kan ikke verificere det ud fra de uploadede tidsplaner.",
        "known_prefix": "Hvad jeg kan bekræfte:",
        "unknown_prefix": "Hvad der ikke kan bestemmes:",
        "next_step_prefix": "Hvad du kan gøre næste gang:",
    },
}

_NO_ANSWER_NEXT_STEP = {
    # Default next-step suggestion per brief §18's worked pattern. Brief
    # §42: reassuring, not broken — short, constructive, never scolding.
    "en": "I can show you the predecessor activities, dependency graph, and recent schedule changes to help you investigate.",
    "da": "Jeg kan vise dig forgængeraktiviteter, afhængighedsgrafen og de seneste tidsplanændringer, så du kan undersøge det nærmere.",
}


def build_no_answer_response(
    known: Sequence[str],
    cannot_verify: Sequence[str],
    language: str = "en",
) -> str:
    """TL-6.5: render the brief §18 three-part reassuring no-answer.

    Layout (per language template):
        <header>
        What I can confirm:
          - <known[0]>
          - <known[1]>
        What cannot be determined:
          - <cannot_verify[0]>
        What you can do next:
          - <next-step suggestion>

    Brief §42: this text should feel reassuring, not broken. The header
    is short and direct, the bullets are specific (never "various issues"),
    and the next step is constructive (never "I cannot help").
    """
    templates = _NO_ANSWER_TEMPLATES.get(language, _NO_ANSWER_TEMPLATES["en"])
    next_step_text = _NO_ANSWER_NEXT_STEP.get(language, _NO_ANSWER_NEXT_STEP["en"])

    parts = [templates["header"]]
    if known:
        parts.append("")
        parts.append(templates["known_prefix"])
        for k in known:
            parts.append(f"  - {k}")
    if cannot_verify:
        parts.append("")
        parts.append(templates["unknown_prefix"])
        for u in cannot_verify:
            parts.append(f"  - {u}")
    parts.append("")
    parts.append(templates["next_step_prefix"])
    parts.append(f"  - {next_step_text}")
    return "\n".join(parts)


def detect_no_answer(
    question: str,
    facts: Sequence[str] = (),
    unverifiable_claims: Sequence[str] = (),
    language: str = "en",
) -> Optional[NoAnswerInfo]:
    """TL-6.5: decide whether a question should be answered with the
    structured no-answer shape (brief §18).

    Logic — both conditions must hold:
    1. The question is causal/unanswerable (matches a trigger in
       `is_causal_question`).
    2. There is something specific that could not be verified
       (`unverifiable_claims` non-empty). Without this, the question
       is causal but the data has nothing to say — that is a *partial
       answer*, not a no-answer (a partial answer can still be
       useful: "here are the facts that ARE known, even if the cause
       is not in the data").

    Returns `None` for normal/partial answers; a `NoAnswerInfo` only
    when both conditions hold. The function does not invent `known`
    or `cannot_verify` content — those come from the caller (the
    verified claim set from TL-6.3, or the retrieval context from the
    RAGAgent's chat path).

    Brief AC4 ("a fabricated causal explanation is never returned for
    an unanswerable question") is enforced by the fact that this
    function is called *before* the LLM produces a causal story: the
    no-answer is what is rendered, so the LLM's causal narrative is
    never returned in this case.
    """
    if not is_causal_question(question):
        return None
    if not unverifiable_claims:
        return None

    return NoAnswerInfo(
        known=tuple(facts),
        cannot_verify=tuple(unverifiable_claims),
        next_step=_NO_ANSWER_NEXT_STEP.get(language, _NO_ANSWER_NEXT_STEP["en"]),
        language=language,
    )


@dataclass(frozen=True)
class ValidatedResponse:
    """The only response shape any renderer may accept (brief §33's own
    AC). Constructing one directly raises `RuntimeError` — the sole
    legitimate constructor is `validate_agent_response()`. This is what
    makes "renderer accepts only validated response objects" a structural
    guarantee rather than a convention a future caller can quietly skip.
    """

    text: str
    gate_decision: GateDecision
    confidence_state: TrustState
    supporting_facts: list[str]
    source_references: list[str]
    inferences: list[str]
    resolved_unverified_claim_count: int
    _gate_token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._gate_token is not _GATE_TOKEN:
            raise RuntimeError(
                "ValidatedResponse must be constructed via validate_agent_response() — "
                "direct construction bypasses the brief §33 gate."
            )


def validate_agent_response(
    response: AgentResponse,
    policy: GatePolicy = GatePolicy.QUALIFY,
    language: str = "en",
) -> ValidatedResponse:
    """TL-6.1 + TL-6.5: the one and only function that may produce a
    `ValidatedResponse`. Enforces brief §33's gate:

        if unverified_claims: remove / qualify / reject
        if no_answer: render the structured brief §18 response

    `policy` selects *which* of the four brief-sanctioned behaviours
    (`remove` / `qualify` / `reject` / `no_answer`) applies — it is not
    a way to skip the gate; even the most permissive result (`ANSWERED`)
    only happens when there is nothing left unverified to act on.

    TL-6.5: `response.no_answer` short-circuits the gate with a
    `NO_ANSWERED` decision. The brief §18 three-part response is
    rendered directly (it is the validated text), bypassing the normal
    REMOVE/QUALIFY/REJECT flow — a structured no-answer is not an
    error, not an empty result, and not a qualified answer; it is a
    first-class response shape.
    """
    # TL-6.5: no-answer takes precedence. A response that *is* a
    # no-answer is not "an answer with unverified claims"; it is its
    # own shape. The gate cannot make a no-answer into a qualified
    # answer or vice versa — that would be the same kind of
    # misrepresentation the brief §34 enforcement architecture exists
    # to prevent.
    if response.no_answer is not None:
        text = build_no_answer_response(
            known=response.no_answer.known,
            cannot_verify=response.no_answer.cannot_verify,
            language=language,
        )
        return ValidatedResponse(
            text=text,
            gate_decision=GateDecision.NO_ANSWERED,
            confidence_state=TrustState.UNVERIFIED,
            supporting_facts=list(response.supporting_facts),
            source_references=list(response.source_references),
            inferences=[],
            resolved_unverified_claim_count=len(response.no_answer.cannot_verify),
            _gate_token=_GATE_TOKEN,
        )

    claims = response.unverified_claims

    if not claims:
        return ValidatedResponse(
            text=response.answer,
            gate_decision=GateDecision.ANSWERED,
            confidence_state=response.confidence_state,
            supporting_facts=list(response.supporting_facts),
            source_references=list(response.source_references),
            inferences=list(response.inferences),
            resolved_unverified_claim_count=0,
            _gate_token=_GATE_TOKEN,
        )

    if policy is GatePolicy.REJECT:
        return ValidatedResponse(
            text=_REJECTED_ANSWER.get(language, _REJECTED_ANSWER["en"]),
            gate_decision=GateDecision.REJECTED,
            confidence_state=TrustState.UNVERIFIED,
            supporting_facts=[],
            source_references=[],
            inferences=[],
            resolved_unverified_claim_count=len(claims),
            _gate_token=_GATE_TOKEN,
        )

    if policy is GatePolicy.REMOVE:
        # Best-effort verbatim removal: `unverified_claims` entries are
        # plain text until `TL-6.2` gives them real spans. A claim that
        # cannot be located verbatim in `answer` is NOT silently dropped
        # from the count — it falls through to a QUALIFY disclaimer for
        # whatever remains, matching brief §33's "remove OR qualify" (never
        # "remove and hope the rest goes unnoticed").
        text = response.answer
        removed = 0
        for claim_text in claims:
            if claim_text and claim_text in text:
                text = text.replace(claim_text, "").strip()
                removed += 1
        remaining = len(claims) - removed
        if remaining > 0:
            qualifier = _UNVERIFIED_QUALIFIER.get(language, _UNVERIFIED_QUALIFIER["en"]).format(n=remaining)
            text = f"{text}\n\n{qualifier}".strip()
            decision = GateDecision.QUALIFIED
        else:
            decision = GateDecision.ANSWERED
        return ValidatedResponse(
            text=text,
            gate_decision=decision,
            confidence_state=response.confidence_state,
            supporting_facts=list(response.supporting_facts),
            source_references=list(response.source_references),
            inferences=list(response.inferences),
            resolved_unverified_claim_count=removed,
            _gate_token=_GATE_TOKEN,
        )

    # GatePolicy.QUALIFY (default) — keep the answer, name what could not
    # be confirmed (brief §16's own worked example).
    qualifier = _UNVERIFIED_QUALIFIER.get(language, _UNVERIFIED_QUALIFIER["en"]).format(n=len(claims))
    return ValidatedResponse(
        text=f"{response.answer}\n\n{qualifier}".strip(),
        gate_decision=GateDecision.QUALIFIED,
        confidence_state=response.confidence_state,
        supporting_facts=list(response.supporting_facts),
        source_references=list(response.source_references),
        inferences=list(response.inferences),
        resolved_unverified_claim_count=0,
        _gate_token=_GATE_TOKEN,
    )


def render_validated_response(response: ValidatedResponse) -> str:
    """TL-6.1 AC2: the only function permitted to produce final rendered
    text from an agent response. Runtime-type-checked (not just annotated)
    so a caller cannot pass a bare string or an ungated `AgentResponse` —
    both fail loudly instead of silently rendering unvalidated content.
    """
    if not isinstance(response, ValidatedResponse):
        raise TypeError(
            f"render_validated_response() requires a ValidatedResponse — got "
            f"{type(response).__name__}. Call validate_agent_response() first."
        )
    return response.text


# ============================================================================
# TL-7.8 — Reassuring uncertainty UX for BLOCK gating (brief §42)
# ============================================================================
# Brief §42's literal worked example:
#
#     Review required
#     Nova found insufficient evidence to reliably match this activity
#     between the two schedules.
#     The activity has therefore been excluded from confirmed comparison
#     results.
#     Review match →
#
# That is a four-part shape — heading / what happened / what Nova did
# about it / a next step — not free text. `build_uncertainty_notice`
# renders that same shape for the two BLOCK gating decisions that already
# exist (`TL-4.6`'s pre-flight check, `TL-5.5`'s context-truncation gate),
# so a BLOCK response is structurally reassuring by construction rather
# than by a renderer remembering to phrase it nicely. `NoAnswerInfo`
# above is this same brief §42 posture applied to the chat/narrative
# surface (TL-6.5) — this is the dashboard-gating counterpart.

_UNCERTAINTY_NOTICES = {
    "preflight_block": {
        "en": {
            "heading": "Review required",
            "what_happened": "Nova found insufficient reliable data in this schedule to generate a confident analysis.",
            "what_nova_did": "The analysis has therefore been paused, rather than publish a result built on incomplete or unreliable data.",
            "action_label": "Review source data →",
        },
        "da": {
            "heading": "Gennemgang påkrævet",
            "what_happened": "Nova fandt ikke tilstrækkelig pålidelig data i denne tidsplan til at generere en sikker analyse.",
            "what_nova_did": "Analysen er derfor sat på pause, i stedet for at offentliggøre et resultat baseret på ufuldstændige eller upålidelige data.",
            "action_label": "Gennemgå kildedata →",
        },
    },
    "context_truncation_block": {
        "en": {
            "heading": "Review required",
            "what_happened": "Too much of this schedule's data exceeded Nova's context limits to be included in the analysis.",
            "what_nova_did": "The analysis has therefore been paused, rather than publish a result based on less than half of the schedule.",
            "action_label": "Try a smaller file or fewer activities →",
        },
        "da": {
            "heading": "Gennemgang påkrævet",
            "what_happened": "For meget af denne tidsplans data oversteg Novas grænser for, hvor meget der kan indgå i analysen.",
            "what_nova_did": "Analysen er derfor sat på pause, i stedet for at offentliggøre et resultat baseret på under halvdelen af tidsplanen.",
            "action_label": "Prøv en mindre fil eller færre aktiviteter →",
        },
    },
}


def build_uncertainty_notice(kind: str, language: str = "en") -> dict[str, str]:
    """TL-7.8: the brief §42 four-part reassuring shape as a plain dict —
    `heading` / `what_happened` / `what_nova_did` / `action_label` — for a
    BLOCK gating outcome. `kind` is `"preflight_block"` (TL-4.6) or
    `"context_truncation_block"` (TL-5.5); an unrecognized `kind` falls
    back to `"preflight_block"`'s wording rather than raising, since a
    missing notice must never be the reason a BLOCK response fails to
    return at all.

    Deliberately a dict of short strings, not pre-rendered HTML/markup —
    the two React apps (`ComparisonAnalysis.jsx`/`ScheduleAnalysis.jsx` in
    both `kemp&lauritzen/app` and `website/workspace/app`) render it
    inside their own reassuring panel component, and the V1 HTML
    dashboard has no BLOCK-shaped page of its own to render into (a BLOCK
    response never reaches `format_*_v1_as_html` — it is returned before
    any dashboard is built).
    """
    table = _UNCERTAINTY_NOTICES.get(kind, _UNCERTAINTY_NOTICES["preflight_block"])
    return dict(table.get(language, table["en"]))


def merge_inferences(*groups: Sequence[str]) -> list[str]:
    """Small convenience used by both agents' wiring: flatten several
    inference-candidate lists into one, dropping empties, preserving order,
    de-duplicating exact repeats. Not brief-mandated — just avoids every
    call site re-writing the same three lines."""
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.add(item)
                result.append(item)
    return result
