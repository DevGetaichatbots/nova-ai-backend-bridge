"""Tests for Brief §41 versioning: seven independent version dimensions (TL-9.3).

Brief §41:
    "Results will change over time, and without versions nobody can
    explain why."

Acceptance criteria:
- [x] All seven version dimensions recorded
- [x] Versions stamped on results and audit entries
- [x] A model or prompt change is visible in the audit trail
- [x] Two analyses of the same input under different versions are distinguishable
"""
import pytest
from unittest.mock import MagicMock, patch

from src.trust.audit import (
    AnalysisAuditTrail,
    AuditChainEntry,
    AuditStage,
    audit_store,
)
from src.trust.versioning import (
    ALL_VERSION_DIMENSIONS,
    DEFAULT_ANALYSIS_ENGINE_VERSION,
    DEFAULT_MANUAL_CORRECTIONS,
    DEFAULT_MATCHING_ALGORITHM_VERSION,
    DEFAULT_MODEL_VERSION,
    DEFAULT_PARSER_VERSION,
    DEFAULT_PROMPT_VERSION,
    DEFAULT_SCHEDULE_REVISION,
    AnalysisVersions,
)
from src.experimental.nusf_compare_engine import (
    ANALYSIS_ENGINE_VERSION,
    MATCHING_ALGORITHM_VERSION,
    compare_nusf_chunks,
)
from ingestion.pipeline import PARSER_VERSION
from src.predictive_agent import (
    PREDICTIVE_ENGINE_VERSION,
    PREDICTIVE_PROMPT_VERSION,
    PredictiveAgent,
)


def test_all_seven_version_dimensions_recorded():
    """AC1: All seven version dimensions from Brief §41 are recorded and non-empty."""
    expected_dimensions = {
        "parser",
        "matching_algorithm",
        "analysis_engine",
        "prompt",
        "model",
        "schedule_revision",
        "manual_corrections",
    }
    assert set(ALL_VERSION_DIMENSIONS) == expected_dimensions
    assert len(ALL_VERSION_DIMENSIONS) == 7

    versions = AnalysisVersions()
    ver_dict = versions.to_dict()
    assert set(ver_dict.keys()) == expected_dimensions
    for dim, val in ver_dict.items():
        assert val is not None and len(str(val)) > 0, f"Dimension {dim} is empty"


def test_aliases_normalized_correctly():
    """Accepts both direct names (e.g. parser) and suffixed names (e.g. parser_version)."""
    versions = AnalysisVersions(
        parser_version="custom-parser-v3",
        matching_algorithm_version="custom-matcher-v2",
        analysis_engine_version="custom-engine-v1",
        prompt_version="custom-prompt-v9",
        model_version="custom-gpt-5",
        manual_corrections_version="custom-corrections-v4",
    )
    assert versions.parser == "custom-parser-v3"
    assert versions.matching_algorithm == "custom-matcher-v2"
    assert versions.analysis_engine == "custom-engine-v1"
    assert versions.prompt == "custom-prompt-v9"
    assert versions.model == "custom-gpt-5"
    assert versions.manual_corrections == "custom-corrections-v4"


def test_versions_stamped_on_compare_engine_results():
    """AC2: Versions are stamped onto comparison analysis results."""
    old_chunks = [
        {
            "header": "Entydigt Id,Opgavenavn,Startdato,Slutdato,% Færdigt",
            "rows": ["101,Groundwork,2026-01-01,2026-02-01,100%"],
        }
    ]
    new_chunks = [
        {
            "header": "Entydigt Id,Opgavenavn,Startdato,Slutdato,% Færdigt",
            "rows": ["101,Groundwork,2026-01-01,2026-02-01,100%"],
        }
    ]
    result = compare_nusf_chunks(old_chunks, new_chunks, reference_date="2026-02-01")
    assert "versions" in result
    v = result["versions"]
    assert v["matching_algorithm"] == MATCHING_ALGORITHM_VERSION
    assert v["analysis_engine"] == ANALYSIS_ENGINE_VERSION
    assert v["parser"] == PARSER_VERSION
    for dim in ALL_VERSION_DIMENSIONS:
        assert dim in v


def test_versions_stamped_on_predictive_agent_results():
    """AC2: Versions are stamped onto PredictiveAgent analysis results."""
    agent = PredictiveAgent()
    mock_choice = MagicMock()
    mock_choice.message.content = (
        '{"executive_actions": [], "management_conclusion": "ok", '
        '"schedule_overview": {}, "delayed_activities": [], '
        '"root_cause_analysis": [], "downstream_consequences": [], '
        '"priority_actions": [], "resource_assessment": {}, '
        '"forcing_assessment": [], "summary_by_area": {}, "insight_data": {}}'
    )
    mock_choice.message.refusal = None
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o-2024-08-06"
    mock_response.usage = None

    with patch.object(agent.client.chat.completions, "create", return_value=mock_response):
        res = agent.analyze(context="Activity,Start,Finish\nA,2026-01-01,2026-01-05", user_query="status")
        assert res["status"] == "success"
        assert "versions" in res
        v = res["versions"]
        assert v["prompt"] == PREDICTIVE_PROMPT_VERSION
        assert v["analysis_engine"] == PREDICTIVE_ENGINE_VERSION
        assert v["model"] == "gpt-4o-2024-08-06"
        for dim in ALL_VERSION_DIMENSIONS:
            assert dim in v


def test_versions_stamped_on_audit_entries_and_trail():
    """AC2: Versions stamped into audit chain entries and verifiable via hash."""
    trail = AnalysisAuditTrail(analysis_id="test-version-stamp")
    custom_ver = AnalysisVersions(
        parser="custom-parser-v1",
        model="gpt-4o-deployment-v1",
    )
    trail.set_versions(custom_ver)

    entry = trail.add_entry(AuditStage.PARSER_VERSION, {"parser": "test"})
    assert entry.versions is not None
    assert entry.versions["parser"] == "custom-parser-v1"
    assert entry.versions["model"] == "gpt-4o-deployment-v1"
    assert trail.verify_integrity() is True


def test_model_or_prompt_change_visible_in_audit_trail():
    """AC3: A model or prompt change is visible in the audit trail and alters cryptographic hash."""
    trail1 = AnalysisAuditTrail(analysis_id="analysis-run-1")
    trail1.set_versions(AnalysisVersions(model="azure-gpt-4o-2024-05-13", prompt="prompt:v1.0"))
    e1 = trail1.add_entry(
        AuditStage.AGENT_ANSWER,
        {"model_version": "azure-gpt-4o-2024-05-13", "prompt_version": "prompt:v1.0"},
    )

    trail2 = AnalysisAuditTrail(analysis_id="analysis-run-2")
    trail2.set_versions(AnalysisVersions(model="azure-gpt-4o-2024-08-06", prompt="prompt:v2.0"))
    e2 = trail2.add_entry(
        AuditStage.AGENT_ANSWER,
        {"model_version": "azure-gpt-4o-2024-08-06", "prompt_version": "prompt:v2.0"},
    )

    # Both trails have valid cryptographic integrity
    assert trail1.verify_integrity() is True
    assert trail2.verify_integrity() is True

    # But their recorded versions and cryptographic entry hashes differ!
    assert trail1.get_versions()["model"] != trail2.get_versions()["model"]
    assert trail1.get_versions()["prompt"] != trail2.get_versions()["prompt"]
    assert e1.hash != e2.hash


def test_two_analyses_same_input_different_versions_are_distinguishable():
    """AC4: Two analyses of the same input under different versions are distinguishable."""
    v_may = AnalysisVersions(model="gpt-4o-2024-05-13", parser="nusf-pipeline-v2.0")
    v_aug = AnalysisVersions(model="gpt-4o-2024-08-06", parser="nusf-pipeline-v2.1")

    assert v_may.is_distinguishable_from(v_aug) is True

    diffs = v_may.diff(v_aug)
    assert "model" in diffs
    assert diffs["model"] == ("gpt-4o-2024-05-13", "gpt-4o-2024-08-06")
    assert "parser" in diffs
    assert diffs["parser"] == ("nusf-pipeline-v2.0", "nusf-pipeline-v2.1")

    # When all 7 dimensions match, they are not distinguishable
    v_copy = AnalysisVersions(model="gpt-4o-2024-05-13", parser="nusf-pipeline-v2.0")
    assert v_may.is_distinguishable_from(v_copy) is False
    assert v_may.diff(v_copy) == {}


def test_no_single_global_version_number():
    """Do-not rule: Do NOT use a single global version number.

    The seven dimensions must change independently.
    """
    base = AnalysisVersions()
    # Varying only prompt leaves other 6 unchanged
    changed_prompt = AnalysisVersions(prompt="prompt:experimental-v9")
    diffs = base.diff(changed_prompt)
    assert len(diffs) == 1
    assert "prompt" in diffs
    assert diffs["prompt"][0] != diffs["prompt"][1]

    # Varying only matching_algorithm leaves other 6 unchanged
    changed_matcher = AnalysisVersions(matching_algorithm="matcher:levenshtein-only")
    diffs_matcher = base.diff(changed_matcher)
    assert len(diffs_matcher) == 1
    assert "matching_algorithm" in diffs_matcher


def test_reconstruct_answer_includes_versions():
    """reconstruct_answer includes the complete seven-dimensional version manifest."""
    trail = AnalysisAuditTrail(analysis_id="reconstruct-test")
    trail.set_versions(AnalysisVersions(
        parser="test-parser",
        matching_algorithm="test-matcher",
        analysis_engine="test-engine",
        prompt="test-prompt",
        model="test-model",
        schedule_revision="rev:test-42",
        manual_corrections="corrections-v2",
    ))
    recon = trail.reconstruct_answer()
    assert "versions" in recon
    v = recon["versions"]
    for dim in ALL_VERSION_DIMENSIONS:
        assert dim in v
    assert v["parser"] == "test-parser"
    assert v["model"] == "test-model"
    assert v["prompt"] == "test-prompt"
    assert v["schedule_revision"] == "rev:test-42"
    assert v["manual_corrections"] == "corrections-v2"
