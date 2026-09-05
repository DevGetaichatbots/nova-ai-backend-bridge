"""Tests for TL-6.5 — No-answer behaviour (brief §18, §42).

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-6-agent-contract.md` (TL-6.5):

- AC1: No-answer is a distinct response type, not an error. `NoAnswerInfo`
  is a first-class shape; `validate_agent_response` returns a
  `ValidatedResponse` with `gate_decision=NO_ANSWERED` when set.
- AC2: The brief §18 A142 scenario produces the documented three-part
  response — "What I can confirm: ...", "What cannot be determined: ...",
  "What you can do next: ..." — in both EN and DA.
- AC3: Both apps render it as a normal result. The renderer receives
  the validated text (the three-part response, not an error banner);
  the `is_no_answer` flag in the chat endpoint signals the frontend.
- AC4: A fabricated causal explanation is never returned for an
  unanswerable question. `is_causal_question` detects causal patterns;
  `detect_no_answer` requires both the causal pattern AND
  unverifiable claims before returning a `NoAnswerInfo`; the chat
  path bypasses the LLM call when no-answer is detected.

Brief §42 ("reassuring, not broken") is encoded as a deliberate tone
choice in the templates — short, specific, never alarming, never
scolding. The tests pin both shape and tone.
"""
from __future__ import annotations

import pytest

from src.trust.response_contract import (
    AgentResponse,
    GateDecision,
    NoAnswerInfo,
    build_no_answer_response,
    detect_no_answer,
    is_causal_question,
    validate_agent_response,
)


# ============================================================================
# AC1 — NoAnswerInfo is a distinct response type
# ============================================================================


class TestNoAnswerShape:
    """AC1: `NoAnswerInfo` is a first-class dataclass with three required
    parts (`known`, `cannot_verify`, `next_step`) plus a `language`
    pin. Brief §18 names all three parts explicitly."""

    def test_no_answer_info_has_three_required_parts(self):
        """Brief §18: known (what IS verified), cannot_verify (what was
        asked but unanswerable), next_step (constructive suggestion).
        All three must be present in the dataclass shape."""
        info = NoAnswerInfo(
            known=("A142 is delayed by 18 days",),
            cannot_verify=("the cause of A142's delay",),
            next_step="I can show you the predecessor activities and recent schedule changes.",
        )
        assert "A142 is delayed by 18 days" in info.known
        assert "the cause of A142's delay" in info.cannot_verify
        assert "predecessor activities" in info.next_step

    def test_no_answer_info_is_frozen(self):
        """A `NoAnswerInfo` is a value object — frozen dataclass so a
        caller cannot mutate it after construction (would let a buggy
        renderer rewrite the `cannot_verify` list to "soften" the
        no-answer, defeating the gate)."""
        info = NoAnswerInfo(
            known=("x",), cannot_verify=("y",), next_step="z",
        )
        with pytest.raises((AttributeError, Exception)):
            info.known = ("rewritten",)  # type: ignore[misc]

    def test_validate_renders_three_part_response(self):
        """AC1/AC2: when `no_answer` is set on `AgentResponse`,
        `validate_agent_response` returns a `ValidatedResponse` with
        `gate_decision=NO_ANSWERED` and a `text` containing all three
        brief §18 sections."""
        response = AgentResponse(
            answer="(would-be LLM response — never rendered when no_answer is set)",
            no_answer=NoAnswerInfo(
                known=("A142 is delayed by 18 days",),
                cannot_verify=("the cause of A142's delay",),
                next_step="I can show you the predecessor activities and recent schedule changes.",
            ),
        )
        validated = validate_agent_response(response, language="en")
        assert validated.gate_decision == GateDecision.NO_ANSWERED
        # All three sections present
        assert "What I can confirm" in validated.text
        assert "A142 is delayed by 18 days" in validated.text
        assert "What cannot be determined" in validated.text
        assert "the cause of A142's delay" in validated.text
        assert "What you can do next" in validated.text

    def test_no_answer_short_circuits_the_normal_gate(self):
        """A response with `no_answer` set AND `unverified_claims`
        present does not fall through to QUALIFY/REMOVE/REJECT — the
        no-answer shape takes precedence (the gate cannot convert a
        no-answer into a partial answer, that would be the same kind
        of misrepresentation the brief §34 architecture exists to
        prevent)."""
        response = AgentResponse(
            answer="would-be answer",
            unverified_claims=["some unverifiable claim"],
            no_answer=NoAnswerInfo(
                known=("x",), cannot_verify=("y",), next_step="z",
            ),
        )
        validated = validate_agent_response(response, language="en")
        assert validated.gate_decision == GateDecision.NO_ANSWERED
        # Unverifiable claim text is NOT surfaced as a disclaimer
        # appended to the answer — the no-answer shape replaces the
        # answer entirely.
        assert "some unverifiable claim" not in validated.text

    def test_normal_answer_is_unaffected_by_no_answer_default(self):
        """AC1 (positive): a normal `AgentResponse` (no `no_answer`)
        flows through the existing QUALIFY gate — no_answer is an
        opt-in shape, not a forced one. Brief §18: "this is a feature,
        not a failure" — i.e. opt-in for the cases where the data
        truly cannot answer, not for every response."""
        response = AgentResponse(answer="normal answer")
        validated = validate_agent_response(response, language="en")
        assert validated.gate_decision == GateDecision.ANSWERED
        assert "normal answer" in validated.text
        assert "cannot verify" not in validated.text.lower()


# ============================================================================
# AC2 — Brief §18 A142 scenario produces the documented three-part response
# ============================================================================


class TestBriefSection18A142:
    """AC2: brief §18's A142 worked scenario — "A142 is delayed by 18
    days" (known), "the cause cannot be determined" (cannot_verify),
    "show predecessor activities and recent changes" (next_step) —
    produces the documented three-part response in EN and DA."""

    def test_a142_scenario_en(self):
        """Brief §18's worked pattern, English."""
        text = build_no_answer_response(
            known=["A142 is delayed by 18 days"],
            cannot_verify=["the cause of A142's delay"],
            language="en",
        )
        # Header (brief §18's exact framing)
        assert "I cannot verify that from the uploaded schedules" in text
        # Three sections, in order
        assert text.find("What I can confirm") < text.find("What cannot be determined")
        assert text.find("What cannot be determined") < text.find("What you can do next")
        # Concrete content
        assert "A142 is delayed by 18 days" in text
        assert "the cause of A142's delay" in text
        assert "predecessor activities" in text
        assert "recent schedule changes" in text

    def test_a142_scenario_da(self):
        """Brief §18's pattern, Danish — both dashboards ship Danish
        (brief §46; Kemp is Danish-only). Same three-part structure."""
        text = build_no_answer_response(
            known=["A142 er forsinket med 18 dage"],
            cannot_verify=["årsagen til A142's forsinkelse"],
            language="da",
        )
        assert "Jeg kan ikke verificere" in text
        assert "Hvad jeg kan bekræfte" in text
        assert "Hvad der ikke kan bestemmes" in text
        assert "Hvad du kan gøre næste gang" in text
        assert "A142 er forsinket med 18 dage" in text

    def test_response_is_reassuring_not_broken(self):
        """Brief §42: the no-answer should feel reassuring, not broken.
        Pin the tone: short header, specific bullets, never alarming
        words ("error", "failed", "broken"), never scolding ("you
        should have")."""
        text = build_no_answer_response(
            known=["Fact A"], cannot_verify=["Question B"], language="en",
        )
        # Brief §42 anti-patterns — these words must NOT appear
        for word in ("error", "failed", "broken", "invalid", "you should have"):
            assert word not in text.lower(), (
                f"reassuring tone violated: {word!r} in {text!r}"
            )

    def test_response_lists_each_fact_and_unverifiable(self):
        """Pin that every `known` and every `cannot_verify` item is
        surfaced in the rendered text — silent drops would be the
        same misrepresentation the gate prevents."""
        text = build_no_answer_response(
            known=["Fact 1", "Fact 2", "Fact 3"],
            cannot_verify=["Unanswerable 1", "Unanswerable 2"],
            language="en",
        )
        for f in ("Fact 1", "Fact 2", "Fact 3"):
            assert f in text
        for u in ("Unanswerable 1", "Unanswerable 2"):
            assert u in text


# ============================================================================
# AC3 — Detection logic + chat-path wiring (rendering flag)
# ============================================================================


class TestCausalQuestionDetection:
    """AC3 / AC4: `is_causal_question` detects the brief §20 question
    patterns (English + Danish). Conservative by design — a regular
    question must not be mis-detected as causal."""

    @pytest.mark.parametrize("question,expected", [
        # English causal patterns
        ("Why is A142 delayed?", True),
        ("What caused the delay in NK?", True),
        ("Why are coordination tasks behind?", True),
        ("What is causing the bottleneck?", True),
        ("What's blocking the EL work?", True),
        ("What is preventing completion?", True),
        ("Reason for the slippage?", True),
        ("Root cause of the production delay?", True),
        ("Hvad forårsager forsinkelsen?", True),
        ("Hvorfor er aktiviteten bagud?", True),
        # Non-causal questions — must NOT be detected
        ("What is the delayed count?", False),
        ("List the activities in NK.", False),
        ("Compare OLD and NEW schedules.", False),
        ("Show me the schedule overview.", False),
        ("Hello, how does Nova work?", False),
    ])
    def test_causal_detection(self, question, expected):
        assert is_causal_question(question) is expected


class TestDetectNoAnswer:
    """AC4: `detect_no_answer` returns a `NoAnswerInfo` only when BOTH
    conditions hold: causal question AND unverifiable claims. A
    causal question with verified facts is a partial answer, not a
    no-answer."""

    def test_returns_none_for_non_causal_question(self):
        result = detect_no_answer(
            question="What is the delayed count?",
            facts=[],
            unverifiable_claims=["some claim"],
        )
        assert result is None

    def test_returns_none_for_causal_question_with_no_unverifiable_claims(self):
        """A causal question with verified facts IS a useful partial
        answer, not a no-answer — we have something to share."""
        result = detect_no_answer(
            question="Why is A142 delayed?",
            facts=["A142 has 0% progress"],
            unverifiable_claims=[],
        )
        assert result is None

    def test_returns_no_answer_for_causal_question_with_unverifiable_claims(self):
        """AC4: causal question + unverifiable claims = no-answer."""
        result = detect_no_answer(
            question="Why is A142 delayed?",
            facts=["A142 is delayed by 18 days"],
            unverifiable_claims=["the cause of A142's delay"],
            language="en",
        )
        assert result is not None
        assert result.known == ("A142 is delayed by 18 days",)
        assert result.cannot_verify == ("the cause of A142's delay",)
        assert "predecessor activities" in result.next_step

    def test_no_answer_never_invents_causal_explanation(self):
        """AC4 (the headline guarantee): for an unanswerable question,
        the rendered response is the no-answer shape, NOT an LLM
        causal narrative. The detector returns `None` until both
        conditions hold — and when it fires, the gate renders the
        brief §18 reassuring text, never an explanation.
        """
        # Without unverifiable claims, no no-answer (even causal)
        result = detect_no_answer(
            question="What caused the delay?",
            facts=["some verified fact"],
            unverifiable_claims=[],
        )
        assert result is None

        # With unverifiable claims, no-answer is structured — never
        # contains a fabricated cause
        result = detect_no_answer(
            question="What caused the delay?",
            facts=["some verified fact"],
            unverifiable_claims=["the cause"],
        )
        text = build_no_answer_response(
            known=result.known,
            cannot_verify=result.cannot_verify,
            language=result.language,
        )
        # The text MUST NOT contain any causal explanation — only the
        # brief §18 three-part reassuring structure.
        assert "I cannot verify that" in text
        assert "What cannot be determined" in text
        # No fabricated causal verbs in the rendered text
        for verb in ("caused by", "due to the", "because of"):
            assert verb not in text.lower()


class TestValidateRendersDanish:
    """AC3: Danish rendering works end-to-end through the gate."""

    def test_no_answer_danish_through_gate(self):
        response = AgentResponse(
            answer="would-be answer (never rendered)",
            no_answer=NoAnswerInfo(
                known=("A142 er forsinket med 18 dage",),
                cannot_verify=("årsagen til forsinkelsen",),
                next_step="Jeg kan vise dig forgængeraktiviteter og seneste ændringer.",
                language="da",
            ),
        )
        validated = validate_agent_response(response, language="da")
        assert validated.gate_decision == GateDecision.NO_ANSWERED
        assert "Jeg kan ikke verificere" in validated.text
        assert "A142 er forsinket med 18 dage" in validated.text


# ============================================================================
# Integration — agent responses wire no_answer through
# ============================================================================


class TestPredictiveAgentNoAnswerIntegration:
    """Integration: `_build_agent_response` (`src/predictive_agent.py`)
    detects no-answer when the user query is causal AND the conclusion
    has unverifiable claims. Same posture as TL-6.1/TL-6.3/TL-6.4
    wiring (ADR-024/026/027): the wiring point is `_build_agent_response`,
    one place for both NUSF and raw paths."""

    def test_predictive_no_answer_for_causal_user_query(self):
        """A user query like 'Why are coordination tasks behind?' —
        causal — plus an unverifiable causal claim in the conclusion
        triggers the no-answer shape."""
        from src.predictive_agent import _build_agent_response

        parsed = {
            "predictive_snapshot": {
                "what_will_happen": "If no action, +6 weeks.",
                "estimated_delay_impact": "+6 weeks",
                "confidence_level": "HIGH",
                "confidence_basis": "Based on 28 delayed activities.",
                "main_delay_drivers": ["coordination bottlenecks", "design decisions", "production overdue"],
            },
            "predictive_biggest_risk": {
                "risk_title": "T1 — 47 days overdue",
                "will_block": "Blocks downstream EL work.",
                "prevent_action_now": "Escalate T1 coordination meeting.",
            },
            "executive_actions": [{
                "rank": 1, "action": "Resolve T1", "responsible": "PM",
                "deadline": "Monday", "related_task_ids": ["T1"],
                "manpower_helps": False, "manpower_note": "n/a",
            }],
            "management_conclusion": (
                "Activity T1 is delayed due to a coordination issue, "
                "caused by unclear ownership."
            ),
            "schedule_overview": {"schedule_name": "X", "reference_date": "01-01-2026",
                                  "total_activities": 100, "delayed_count": 10,
                                  "areas_covered": ["NK"], "format_detected": "csv"},
            "delayed_activities": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "start_date": "01-01-2026", "end_date": "10-01-2026",
                "duration": "10d", "progress": "0%", "days_overdue": 47,
                "task_type": "Production", "priority": "CRITICAL_NOW",
                "is_root_cause": True, "blocked_by_id": None, "area": "NK",
            }],
            "root_cause_analysis": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "days_overdue": 47, "problem_type": "coordination",
                "why_it_matters": "x", "downstream_impact": "x",
                "consequence_if_unresolved": "x", "affected_task_ids": [],
            }],
            "downstream_consequences": [],
            "priority_actions": [],
            "resource_assessment": [],
            "forcing_assessment": [],
            "summary_by_area": [],
            "insight_data": {
                "total_activities": 100, "delayed_count": 10,
                "critical_count": 3, "important_count": 4, "monitor_count": 3,
                "root_cause_count": 1, "reference_date": "01-01-2026",
                "most_overdue_days": 47, "areas_affected": 2,
                "format_detected": "csv", "schedule_name": "X",
                "primary_risk": "x", "forceable_count": 0,
                "not_forceable_count": 0, "project_status": "CRITICAL",
                "risk_level": "HIGH", "unverified_delayed_count": 0,
                "critical_findings": [], "consequences_if_no_action": [],
            },
        }

        response = _build_agent_response(
            parsed,
            user_query="Why are coordination tasks behind?",
            language="en",
        )
        assert response.no_answer is not None
        # Causal claim extracted from "caused by unclear ownership" lands
        # in `cannot_verify`; verified facts (delayed_count etc.) in
        # `known`.
        assert len(response.no_answer.known) > 0
        assert len(response.no_answer.cannot_verify) > 0

        # Through the gate, the rendered text is the brief §18 response,
        # not the LLM's narrative.
        validated = validate_agent_response(response, language="en")
        assert validated.gate_decision == GateDecision.NO_ANSWERED
        assert "I cannot verify that from the uploaded schedules" in validated.text

    def test_predictive_normal_answer_for_non_causal_user_query(self):
        """Standard predictive query ('Execute full two-phase analysis')
        does NOT trigger no-answer — non-causal, gets the normal
        answer + claim-verification gate treatment."""
        from src.predictive_agent import _build_agent_response

        parsed = {
            "predictive_snapshot": {"what_will_happen": "x", "estimated_delay_impact": "x",
                                    "confidence_level": "HIGH", "confidence_basis": "x",
                                    "main_delay_drivers": ["a"]},
            "predictive_biggest_risk": {"risk_title": "x", "will_block": "x", "prevent_action_now": "x"},
            "executive_actions": [],
            "management_conclusion": "Material risk; coordination required.",
            "schedule_overview": {"schedule_name": "X", "reference_date": "01-01-2026",
                                  "total_activities": 100, "delayed_count": 10,
                                  "areas_covered": ["NK"], "format_detected": "csv"},
            "delayed_activities": [{
                "id": "T1", "task_name": "x", "human_label": "x",
                "start_date": "01-01-2026", "end_date": "10-01-2026",
                "duration": "10d", "progress": "0%", "days_overdue": 47,
                "task_type": "Production", "priority": "CRITICAL_NOW",
                "is_root_cause": True, "blocked_by_id": None, "area": "NK",
            }],
            "root_cause_analysis": [],
            "downstream_consequences": [],
            "priority_actions": [],
            "resource_assessment": [],
            "forcing_assessment": [],
            "summary_by_area": [],
            "insight_data": {"delayed_count": 10, "critical_count": 3,
                             "root_cause_count": 1, "most_overdue_days": 47,
                             "project_status": "CRITICAL", "risk_level": "HIGH",
                             "unverified_delayed_count": 0},
        }

        response = _build_agent_response(
            parsed,
            user_query="Execute full two-phase analysis: detect ALL delayed activities",
            language="en",
        )
        assert response.no_answer is None  # standard query → no no-answer

    def test_predictive_default_no_user_query_means_no_no_answer(self):
        """TL-6.5 backwards compat: existing callers that don't pass
        `user_query` get the standard answer (no no-answer). The
        default `user_query=""` is treated as non-causal."""
        from src.predictive_agent import _build_agent_response

        parsed = {
            "management_conclusion": "Material risk.",
            "predictive_snapshot": {"what_will_happen": "x"},
            "predictive_biggest_risk": {"risk_title": "x", "will_block": "x", "prevent_action_now": "x"},
            "executive_actions": [],
            "schedule_overview": {"schedule_name": "x", "reference_date": "x",
                                  "total_activities": 0, "delayed_count": 0,
                                  "areas_covered": [], "format_detected": "csv"},
            "delayed_activities": [],
            "root_cause_analysis": [],
            "downstream_consequences": [],
            "priority_actions": [],
            "resource_assessment": [],
            "forcing_assessment": [],
            "summary_by_area": [],
            "insight_data": {"delayed_count": 0, "critical_count": 0,
                             "root_cause_count": 0, "most_overdue_days": 0,
                             "project_status": "STABLE", "risk_level": "LOW",
                             "unverified_delayed_count": 0},
        }
        response = _build_agent_response(parsed)  # no user_query / language args
        assert response.no_answer is None


# ============================================================================
# AC3 — Both apps receive no-answer as a normal result (not an error)
# ============================================================================


class TestRenderAsNormalResult:
    """AC3: a no-answer response is rendered as a normal result, not an
    error banner. The gate returns a `ValidatedResponse` whose `text`
    is the three-part reassuring response — never raises, never
    returns an error-shaped object."""

    def test_render_does_not_raise_for_no_answer(self):
        response = AgentResponse(
            answer="would-be answer",
            no_answer=NoAnswerInfo(known=("x",), cannot_verify=("y",), next_step="z"),
        )
        validated = validate_agent_response(response, language="en")
        from src.trust.response_contract import render_validated_response
        text = render_validated_response(validated)
        assert "I cannot verify" in text

    def test_no_answer_is_not_an_error(self):
        """Brief §42 + the AC: a no-answer must not look like an
        error. The `gate_decision` is `NO_ANSWERED`, never `REJECTED` —
        rejected is a different shape (no answer at all), and the
        brief explicitly says "this is a feature, not a failure."
        """
        response = AgentResponse(
            answer="x",
            no_answer=NoAnswerInfo(known=("x",), cannot_verify=("y",), next_step="z"),
        )
        validated = validate_agent_response(response, language="en")
        assert validated.gate_decision != GateDecision.REJECTED
        assert "could not verify enough" not in validated.text.lower()
