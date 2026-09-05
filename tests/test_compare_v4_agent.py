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

# REMOVED: compare_v4_agent module deleted in route cleanup (no longer imported by any endpoint)
v4_module = None  # placeholder kept so this file remains import-safe


class _FakeCompletions:
    calls = []

    def create(self, **_kwargs):
        self.calls.append(_kwargs)
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


# REMOVED: CompareV4Agent tests were tied to compare_v4_agent which was removed in route cleanup
class CompareV4AgentTest(unittest.TestCase):
    def test_module_removed(self):
        self.skipTest("compare_v4_agent module was removed in route cleanup")

if __name__ == "__main__":
    unittest.main()
