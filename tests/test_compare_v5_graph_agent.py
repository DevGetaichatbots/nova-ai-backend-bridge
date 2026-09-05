import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

fake_vector_store = ModuleType("src.vector_store")
fake_vector_store.vector_store_manager = SimpleNamespace(
    fetch_all_from_stores=lambda *_args, **_kwargs: {}
)
sys.modules.setdefault("src.vector_store", fake_vector_store)

fake_config = ModuleType("src.config")
fake_config.settings = SimpleNamespace(
    AZURE_OPENAI_API_KEY="test",
    AZURE_OPENAI_API_VERSION="2025-04-01-preview",
    AZURE_OPENAI_ENDPOINT="https://example.invalid",
    AZURE_OPENAI_CHAT_DEPLOYMENT="test-model",
)
sys.modules.setdefault("src.config", fake_config)

fake_openai = ModuleType("openai")
fake_openai.AzureOpenAI = lambda **_kwargs: SimpleNamespace()
sys.modules.setdefault("openai", fake_openai)

from src.experimental import compare_v5_graph_agent as v5_module


HEADER = (
    "source_id;stable_key;name;planned_start;planned_finish;percent_complete;"
    "activity_type;wbs_code;discipline;location_path;area;floor;phase;"
    "duration_hours;actual_start;actual_finish;is_late;inspected_status;"
    "critical_flag;total_float;predecessors;successors"
)


def _chunks(*rows):
    return [{"content": "\n".join(["FORMAT: NUSF CSV - each row = one activity.", HEADER, *rows])}]


class _FakeCompletions:
    calls = []

    def create(self, **_kwargs):
        self.calls.append(_kwargs)
        payload = {
            "executive_summary": {
                "recommended_action": "LLM: prioritize EL recovery and confirm basement VVS handover.",
            },
            "delay_drivers": [
                {
                    "driver": "EL recovery risk",
                    "description": "The EL work is late and on the critical path.",
                    "affected_count": 1,
                }
            ],
            "action_recommendations": [
                {
                    "activity": "EL - Cable install",
                    "issue": "LLM identified EL as the priority recovery item.",
                    "actions": ["Confirm blockers", "Assign recovery crew"],
                }
            ],
        }
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])


class _FakeClient:
    chat = SimpleNamespace(completions=_FakeCompletions())


class CompareV5GraphAgentTest(unittest.TestCase):
    def setUp(self):
        _FakeCompletions.calls = []

    def test_v5_graph_uses_llm_enrichment_on_top_of_deterministic_nusf_facts(self):
        old_chunks = _chunks(
            "1;1;EL - Cable install;01-06-2026;10-06-2026;30;TASK;1;Electrical;Project / Building A / 1.;;1. Floor;Phase 1;80;;;false;;false;5;;"
        )
        new_chunks = _chunks(
            "1;1;EL - Cable install;01-06-2026;20-06-2026;25;TASK;1;Electrical;Project / Building A / 1.;;1. Floor;Phase 1;80;;;true;noProgress;true;0;;",
            "2;2;VVS - Pipe install;01-06-2026;10-06-2026;100;TASK;2;Plumbing;Project / Building A / Basement;;Basement;Phase 1;80;;;false;;false;8;;",
        )

        agent = v5_module.CompareV5GraphAgent.__new__(v5_module.CompareV5GraphAgent)
        agent.client = _FakeClient()
        agent._retrieve_context = lambda *_args: ("", 1)

        def fetch(tables, chunk_type):
            return {
                table: old_chunks if table == "old_table" else new_chunks
                for table in tables
            }

        with patch.object(v5_module.vector_store_manager, "fetch_all_from_stores", side_effect=fetch):
            result = agent.analyze(
                scope_filter="All activities",
                reference_date="06-06-2026",
                table_names=["old_table", "new_table"],
                session_id="session_123",
                old_filename="old.csv",
                new_filename="new.csv",
            )

        data = result["json"]
        self.assertEqual(data["executive_summary"]["selected_activities"], 2)
        self.assertEqual(data["executive_summary"]["behind_schedule_count"], 1)
        self.assertEqual(data["executive_summary"]["ahead_of_schedule_count"], 1)
        self.assertEqual(data["executive_summary"]["trade_counts"]["EL"], 1)
        self.assertEqual(data["executive_summary"]["trade_counts"]["VVS"], 1)
        self.assertEqual(
            data["executive_summary"]["recommended_action"],
            "LLM: prioritize EL recovery and confirm basement VVS handover.",
        )
        self.assertEqual(data["delay_drivers"][0]["driver"], "EL recovery risk")
        self.assertEqual(data["action_recommendations"][0]["issue"], "LLM identified EL as the priority recovery item.")
        self.assertEqual(len(_FakeCompletions.calls), 1)
        user_prompt = _FakeCompletions.calls[0]["messages"][1]["content"]
        self.assertIn("DETERMINISTIC_FACTS", user_prompt)
        self.assertIn("EL - Cable install", user_prompt)
        system_prompt = _FakeCompletions.calls[0]["messages"][0]["content"]
        self.assertIn("OUTPUT LANGUAGE: English", system_prompt)
        self.assertEqual(data["progress_vs_expected"][0]["activity"], "EL - Cable install")
        self.assertIn("Building A", data["filter_options"]["areas"])
        self.assertIn("Basement", data["filter_options"]["floors"])

    def test_v5_graph_requests_danish_output_when_language_is_danish(self):
        old_chunks = _chunks(
            "1;1;EL - Cable install;01-06-2026;10-06-2026;30;TASK;1;Electrical;Project / Building A / 1.;;1. Floor;Phase 1;80;;;false;;false;5;;"
        )
        new_chunks = _chunks(
            "1;1;EL - Cable install;01-06-2026;20-06-2026;25;TASK;1;Electrical;Project / Building A / 1.;;1. Floor;Phase 1;80;;;true;noProgress;true;0;;"
        )

        agent = v5_module.CompareV5GraphAgent.__new__(v5_module.CompareV5GraphAgent)
        agent.client = _FakeClient()
        agent._retrieve_context = lambda *_args: ("", 1)

        def fetch(tables, chunk_type):
            return {
                table: old_chunks if table == "old_table" else new_chunks
                for table in tables
            }

        with patch.object(v5_module.vector_store_manager, "fetch_all_from_stores", side_effect=fetch):
            agent.analyze(
                scope_filter="All activities",
                reference_date="06-06-2026",
                table_names=["old_table", "new_table"],
                session_id="session_123",
                old_filename="old.csv",
                new_filename="new.csv",
                language="da",
            )

        system_prompt = _FakeCompletions.calls[0]["messages"][0]["content"]
        self.assertIn("OUTPUT LANGUAGE: Danish", system_prompt)

    def test_v5_graph_requires_nusf_when_requested(self):
        old_chunks = [{"content": "ID;Aktivitetsnavn;Startdato\n1;Task A;01-06-2026"}]
        new_chunks = [{"content": "ID;Aktivitetsnavn;Startdato\n1;Task A;01-06-2026"}]

        agent = v5_module.CompareV5GraphAgent.__new__(v5_module.CompareV5GraphAgent)
        agent.client = _FakeClient()
        agent._retrieve_context = lambda *_args: ("", 1)

        def fetch(tables, chunk_type):
            return {
                table: old_chunks if table == "old_table" else new_chunks
                for table in tables
            }

        with patch.object(v5_module.vector_store_manager, "fetch_all_from_stores", side_effect=fetch):
            with self.assertRaises(RuntimeError) as ctx:
                agent.analyze(
                    scope_filter="All activities",
                    reference_date="06-06-2026",
                    table_names=["old_table", "new_table"],
                    session_id="session_123",
                    old_filename="old.mpp",
                    new_filename="new.mpp",
                    require_nusf=True,
                )

        self.assertIn("not stored as valid NUSF", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
