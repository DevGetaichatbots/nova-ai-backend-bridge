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

from src.experimental import compare_v4_agent as v4_module


class _FakeCompletions:
    def create(self, **_kwargs):
        payload = {
            "executive_summary": {
                "project_health": "Green",
                "selected_activities": 0,
                "added_activities": 0,
                "behind_schedule_count": 0,
                "ahead_of_schedule_count": 0,
                "critical_count": 0,
                "point_of_no_return_count": 0,
                "recommended_action": "",
            },
            "changed_activities": {"added": [], "removed": [], "changes": []},
            "not_started_overdue": [],
            "progress_vs_expected": [],
            "stage_mismatch": [],
            "point_of_no_return": [],
            "action_recommendations": [],
            "critical_path_activities": [],
            "delay_drivers": [],
            "summary_notes": {},
        }
        message = SimpleNamespace(content=json.dumps(payload))
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class _FakeClient:
    chat = SimpleNamespace(completions=_FakeCompletions())


class CompareV4AgentTest(unittest.TestCase):
    def test_activity_count_ignores_planned_start_header(self):
        chunks = [
            {
                "content": "\n".join(
                    [
                        "FORMAT: CSV - each row = one activity",
                        "name;planned_start;planned_finish;progress",
                        "EL - Cable install;01-01-2026;05-01-2026;0%",
                        "VVS - Pipe install;02-01-2026;06-01-2026;0%",
                    ]
                )
            }
        ]

        agent = v4_module.CompareV4Agent.__new__(v4_module.CompareV4Agent)
        agent.client = _FakeClient()
        agent._retrieve_context = lambda *_args: ("", 1)

        with patch.object(
            v4_module.vector_store_manager,
            "fetch_all_from_stores",
            side_effect=lambda tables, chunk_type: {tables[0]: chunks},
        ):
            result = agent.analyze(
                scope_filter="All activities",
                reference_date="01-02-2026",
                table_names=["old_table", "new_table"],
                session_id="session_123",
                old_filename="old.csv",
                new_filename="new.csv",
            )

        summary = result["json"]["executive_summary"]
        self.assertEqual(summary["selected_activities"], 2)
        self.assertEqual(summary["trade_counts"]["ALL"], 2)

    def test_nusf_rows_use_name_column_for_trade_and_location_metadata(self):
        chunks = [
            {
                "content": "\n".join(
                    [
                        "FORMAT: CSV - each row = one activity",
                        "source_id;name;planned_start;planned_finish;percent_complete;activity_type;wbs_code;discipline;duration_hours;actual_start;actual_finish",
                        "1001;EL - Hovedledninger/sti;15-08-2026;01-10-2026;23;TASK;Building A > Level 02 > Phase 1;Electrical;80;;",
                        "1002;VVS - Rørføring teknikrum;15-08-2026;01-10-2026;10;TASK;Building B > Basement > Phase 2;Plumbing;80;;",
                    ]
                )
            }
        ]

        agent = v4_module.CompareV4Agent.__new__(v4_module.CompareV4Agent)
        agent.client = _FakeClient()
        agent._retrieve_context = lambda *_args: ("", 1)

        with patch.object(
            v4_module.vector_store_manager,
            "fetch_all_from_stores",
            side_effect=lambda tables, chunk_type: {tables[0]: chunks},
        ):
            result = agent.analyze(
                scope_filter="All activities",
                reference_date="01-02-2026",
                table_names=["old_table", "new_table"],
                session_id="session_123",
                old_filename="old.csv",
                new_filename="new.csv",
            )

        data = result["json"]
        summary = data["executive_summary"]
        self.assertEqual(summary["selected_activities"], 2)
        self.assertEqual(summary["trade_counts"]["ALL"], 2)
        self.assertEqual(summary["trade_counts"]["EL"], 1)
        self.assertEqual(summary["trade_counts"]["VVS"], 1)
        self.assertIn("Building A", data["filter_options"]["areas"])
        self.assertIn("Level 02", data["filter_options"]["floors"])
        self.assertIn("Phase 1", data["filter_options"]["phases"])


if __name__ == "__main__":
    unittest.main()
