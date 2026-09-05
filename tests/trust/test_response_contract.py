"""Tests for TL-6.1 — Agent response contract structure.

Encodes the acceptance criteria from
`changes/trust-layer/plan/phase-6-agent-contract.md` (TL-6.1):

- AC1: `AgentResponse` carries all six brief §33 fields.
- AC2: The render path accepts only validated response objects.
- AC3: A response with unresolved `unverified_claims` cannot be rendered
  as-is (it is removed / qualified / rejected — never passed through).
- AC4: Both agents (`predictive_agent.py`, `agent.py`) produce responses
  through this contract.

Do-not: no bypass flag for "trusted" callers. `TestNoBypassExists` pins
this structurally — there is no parameter, anywhere in the module, that
skips the gate.
"""
from __future__ import annotations

import dataclasses

import pytest

from src.trust.response_contract import (
    AgentResponse,
    GateDecision,
    GatePolicy,
    ValidatedResponse,
    render_validated_response,
    validate_agent_response,
)
from src.trust.vocabulary import TrustState


# ============================================================================
# AC1 — AgentResponse carries all six brief §33 fields
# ============================================================================


class TestAgentResponseShape:
    def test_all_six_brief_33_fields_present(self):
        """TL-6.1 pins the six brief §33 fields; TL-6.5 adds a seventh
        (`no_answer`) — a first-class response shape, not an error. The
        six original fields must still be present and unchanged."""
        field_names = {f.name for f in dataclasses.fields(AgentResponse)}
        assert {"answer", "supporting_facts", "source_references",
                "confidence_state", "inferences", "unverified_claims"} <= field_names
        assert "no_answer" in field_names  # TL-6.5 addition

    def test_minimal_construction_defaults_are_safe(self):
        """An agent that supplies only `answer` gets empty lists and the
        most conservative confidence state — never an implicit "trust me"
        default."""
        response = AgentResponse(answer="x")
        assert response.supporting_facts == []
        assert response.source_references == []
        assert response.inferences == []
        assert response.unverified_claims == []
        assert response.confidence_state == TrustState.UNVERIFIED

    def test_confidence_state_is_a_trust_state(self):
        """Reuses `TrustState` (TL-0.4) rather than inventing a parallel
        vocabulary — ADR-002's "extend, don't replace" precedent."""
        response = AgentResponse(answer="x", confidence_state=TrustState.VERIFIED)
        assert response.confidence_state is TrustState.VERIFIED


# ============================================================================
# AC2 + AC3 — the render path accepts only validated objects; unresolved
# unverified_claims cannot be rendered as-is
# ============================================================================


class TestRenderPathAcceptsOnlyValidatedResponses:
    def test_render_rejects_raw_string(self):
        with pytest.raises(TypeError):
            render_validated_response("just a plain string")  # type: ignore[arg-type]

    def test_render_rejects_raw_agent_response(self):
        """An `AgentResponse` that never went through the gate must not
        render — even if it happens to have empty `unverified_claims`."""
        raw = AgentResponse(answer="Nothing unverified here.")
        with pytest.raises(TypeError):
            render_validated_response(raw)  # type: ignore[arg-type]

    def test_render_accepts_a_properly_validated_response(self):
        validated = validate_agent_response(AgentResponse(answer="All clear."))
        assert render_validated_response(validated) == "All clear."


class TestValidatedResponseCannotBeConstructedDirectly:
    """AC2/AC3, structurally: the ONLY legitimate constructor is
    `validate_agent_response`. This is what makes the gate impossible to
    bypass, not merely inconvenient to bypass."""

    def test_direct_construction_raises(self):
        with pytest.raises(RuntimeError):
            ValidatedResponse(
                text="sneaking past the gate",
                gate_decision=GateDecision.ANSWERED,
                confidence_state=TrustState.VERIFIED,
                supporting_facts=[],
                source_references=[],
                inferences=[],
                resolved_unverified_claim_count=0,
            )

    def test_validate_agent_response_is_the_only_working_path(self):
        result = validate_agent_response(AgentResponse(answer="ok"))
        assert isinstance(result, ValidatedResponse)


class TestUnverifiedClaimsGate:
    """AC3: a response with unresolved `unverified_claims` never reaches a
    renderer with those claims intact and unacknowledged."""

    def test_no_unverified_claims_passes_through_unchanged(self):
        response = AgentResponse(answer="17 activities are delayed.")
        validated = validate_agent_response(response)
        assert validated.gate_decision == GateDecision.ANSWERED
        assert validated.text == "17 activities are delayed."

    def test_qualify_policy_appends_disclaimer_and_keeps_answer(self):
        response = AgentResponse(
            answer="Electrical works in Building NK have the largest concentration of delay.",
            unverified_claims=["largest concentration of delay"],
        )
        validated = validate_agent_response(response, policy=GatePolicy.QUALIFY)
        assert validated.gate_decision == GateDecision.QUALIFIED
        assert "Electrical works in Building NK" in validated.text
        assert "could not be independently verified" in validated.text

    def test_reject_policy_withholds_the_original_answer(self):
        response = AgentResponse(
            answer="This entire answer rests on an unverifiable claim.",
            unverified_claims=["unverifiable claim"],
        )
        validated = validate_agent_response(response, policy=GatePolicy.REJECT)
        assert validated.gate_decision == GateDecision.REJECTED
        assert "unverifiable claim" not in validated.text
        assert "This entire answer" not in validated.text
        assert validated.confidence_state == TrustState.UNVERIFIED

    def test_remove_policy_strips_located_claim_text(self):
        response = AgentResponse(
            answer="17 activities are delayed. This is the largest concentration project-wide.",
            unverified_claims=["This is the largest concentration project-wide."],
        )
        validated = validate_agent_response(response, policy=GatePolicy.REMOVE)
        assert "largest concentration" not in validated.text
        assert "17 activities are delayed." in validated.text
        assert validated.gate_decision == GateDecision.ANSWERED
        assert validated.resolved_unverified_claim_count == 1

    def test_remove_policy_falls_back_to_qualify_for_unlocatable_claims(self):
        """A claim the gate cannot find verbatim in `answer` (e.g. it was
        already paraphrased, or spans were never precise) must not be
        silently dropped from the count — brief §33's gate is "remove OR
        qualify", never "remove and hope"."""
        response = AgentResponse(
            answer="17 activities are delayed.",
            unverified_claims=["a claim whose exact text does not appear above"],
        )
        validated = validate_agent_response(response, policy=GatePolicy.REMOVE)
        assert validated.gate_decision == GateDecision.QUALIFIED
        assert validated.resolved_unverified_claim_count == 0
        assert "could not be independently verified" in validated.text

    def test_qualify_disclaimer_is_localized_to_danish(self):
        response = AgentResponse(answer="17 aktiviteter er forsinket.", unverified_claims=["x"])
        validated = validate_agent_response(response, policy=GatePolicy.QUALIFY, language="da")
        assert "kunne ikke verificeres" in validated.text

    def test_rejected_answer_is_localized_to_danish(self):
        response = AgentResponse(answer="x", unverified_claims=["x"])
        validated = validate_agent_response(response, policy=GatePolicy.REJECT, language="da")
        assert "kunne ikke verificere" in validated.text

    def test_supporting_facts_and_source_references_survive_qualify(self):
        """The gate only acts on `unverified_claims` — verified supporting
        material is not collateral damage."""
        response = AgentResponse(
            answer="x",
            supporting_facts=["17 delayed activities confirmed"],
            source_references=["A1", "A2"],
            unverified_claims=["y"],
        )
        validated = validate_agent_response(response, policy=GatePolicy.QUALIFY)
        assert validated.supporting_facts == ["17 delayed activities confirmed"]
        assert validated.source_references == ["A1", "A2"]

    def test_reject_clears_supporting_material_too(self):
        """REJECT withholds the whole answer — nothing it rested on should
        be presented as though it were a clean result."""
        response = AgentResponse(
            answer="x",
            supporting_facts=["fact"],
            source_references=["A1"],
            inferences=["inference"],
            unverified_claims=["y"],
        )
        validated = validate_agent_response(response, policy=GatePolicy.REJECT)
        assert validated.supporting_facts == []
        assert validated.source_references == []
        assert validated.inferences == []


# ============================================================================
# Do-not — no bypass flag for "trusted" callers
# ============================================================================


class TestNoBypassExists:
    def test_validate_agent_response_has_no_skip_parameter(self):
        import inspect

        sig = inspect.signature(validate_agent_response)
        for forbidden in ("skip", "bypass", "trusted", "force"):
            assert not any(forbidden in p.lower() for p in sig.parameters), (
                f"found a parameter matching {forbidden!r} — this looks like a bypass flag"
            )

    def test_gate_policy_has_exactly_three_members(self):
        """The only knobs are the three brief §33 behaviours themselves —
        not a fourth "do nothing" option."""
        assert {p.value for p in GatePolicy} == {"remove", "qualify", "reject"}

    def test_every_policy_still_produces_a_ValidatedResponse_via_the_gate(self):
        response = AgentResponse(answer="x", unverified_claims=["y"])
        for policy in GatePolicy:
            validated = validate_agent_response(response, policy=policy)
            assert isinstance(validated, ValidatedResponse)


# ============================================================================
# AC4 — both agents produce responses through this contract
# ============================================================================


class TestBothAgentsUseTheContract:
    """Integration-level: both agent entry points must attach a
    `ValidatedResponse` to their result, built via this module — not a
    parallel, unvalidated text field."""

    def test_predictive_agent_result_carries_a_validated_response(self):
        from datetime import date
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        import json as _json

        from ingestion.models.nusf import Activity, ActivityType, Provenance
        from src.trust.context import build_predictive_context, build_response_facts
        from src.trust.predictive_facts import compute_predictive_facts, detect_delayed_activities

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.predictive_agent.AzureOpenAI", lambda **_kw: MagicMock())
            from src.predictive_agent import PredictiveAgent

            agent = PredictiveAgent()

        fake_message = SimpleNamespace(content=_json.dumps({}), refusal=None)
        fake_choice = SimpleNamespace(message=fake_message, finish_reason="stop")
        agent.client.chat.completions.create.return_value = SimpleNamespace(
            choices=[fake_choice], usage=None, model="fake",
        )

        prov = Provenance(source_field="x", extraction_method="csv_cell")
        act = Activity(
            internal_id="A1", source_id="A1", name="Root cause task",
            planned_start=__import__("datetime").datetime(2020, 1, 1),
            planned_finish=__import__("datetime").datetime(2020, 1, 10),
            duration_hours=80, percent_complete=0.0, activity_type=ActivityType.TASK,
            predecessors=[], successors=[], area="NK", discipline="EL",
            provenance={"planned_start": prov, "percent_complete": prov},
        )
        ref = date(2026, 1, 1)
        delayed = detect_delayed_activities([act], ref)
        facts = compute_predictive_facts(delayed, [act])
        structured_context = build_predictive_context(facts, [act], ref)
        response_facts = build_response_facts(facts, [act], "Test", ref, "NUSF")

        result = agent.analyze_from_facts(
            structured_context=structured_context,
            response_facts=response_facts,
            user_query="Explain the facts.",
        )
        assert result["status"] == "success"
        assert "agent_response" in result
        assert isinstance(result["agent_response"], ValidatedResponse)

    def test_rag_agent_result_carries_a_validated_response(self):
        from unittest.mock import MagicMock
        from types import SimpleNamespace

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.agent.AzureOpenAI", lambda **_kw: MagicMock())
            mp.setattr("src.agent.get_chat_history", lambda *_a, **_kw: [])
            mp.setattr("src.agent.save_chat_message", lambda *_a, **_kw: None)
            from src.agent import RAGAgent

            agent = RAGAgent()

        fake_message = SimpleNamespace(content="Here is the answer.", refusal=None)
        fake_choice = SimpleNamespace(message=fake_message, finish_reason="stop")
        agent.client.chat.completions.create.return_value = SimpleNamespace(
            choices=[fake_choice], usage=None, model="fake",
        )

        result = agent.query(
            user_query="What is delayed?",
            table_names=["schedule_1"],
            session_id="test-session",
        )
        assert "agent_response" in result
        assert isinstance(result["agent_response"], ValidatedResponse)
        # The raw string is still there for existing callers (D3 — additive,
        # no premature production risk to callers reading `response`).
        assert result["response"] == "Here is the answer."
