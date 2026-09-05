import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

fake_requests = ModuleType("requests")
fake_requests.exceptions = SimpleNamespace(RequestException=Exception)
sys.modules.setdefault("requests", fake_requests)

fake_openai = ModuleType("openai")
fake_openai.AzureOpenAI = lambda **_kwargs: SimpleNamespace()
sys.modules.setdefault("openai", fake_openai)

fake_openpyxl = ModuleType("openpyxl")
fake_openpyxl.Workbook = object
fake_openpyxl.load_workbook = lambda *_args, **_kwargs: None
sys.modules.setdefault("openpyxl", fake_openpyxl)

from ingestion.normalization.engine import NormalizationEngine, to_nusf_chunks
from ingestion.recognition.heuristics import HeuristicRecognizer


class NusfNormalizationTests(unittest.TestCase):
    def _normalize(self, headers, rows):
        recognition = HeuristicRecognizer().recognize(headers)
        return NormalizationEngine().normalize(
            extracted={"headers": headers, "rows": rows},
            recognition=recognition,
            source_system="CSV",
            filename="sample.csv",
        )

    def test_tactplan_uses_tbs_as_stable_source_id(self):
        schedule = self._normalize(
            ["#", "TBS", "Aktivitetstype", "Navn", "Lokation", "Startdato", "Slutdato", "Varighed", "Fremdrift"],
            [["3348", "1.1.1", "locationTask", "Dæk over", "Project / Indvendige arbejder / L1 / Stueplan", "16/03/2021", "09/03/2022", "257", "0"]],
        )

        activity = schedule.activities[0]
        self.assertEqual(activity.source_id, "1.1.1")
        self.assertEqual(activity.stable_key, "1.1.1")
        self.assertEqual(activity.location_path, "Project / Indvendige arbejder / L1 / Stueplan")

        chunk_text = to_nusf_chunks(schedule)[0]["content"]
        self.assertIn("stable_key", chunk_text.splitlines()[1])
        self.assertIn("location_path", chunk_text.splitlines()[1])
        self.assertIn("1.1.1;1.1.1;Dæk over", chunk_text)

    def test_plandisc_uses_name_location_as_stable_source_id_and_preserves_late_status(self):
        location = "KatrineTorvet / Råhus / Square / P-kælder -2"
        schedule = self._normalize(
            [
                "name", "location_path", "task_group_name",
                "planned_start_date", "planned_end_date", "planned_shift_duration",
                "actual_completion_pct", "actual_start_date", "actual_end_date",
                "is_late", "inspectedType",
            ],
            [[
                "EL - Kabeltræk", location, "Elektriker",
                "2025-08-15 07:00:00", "2025-10-01 15:00:00", "48",
                "23", "", "", "true", "noProgress",
            ]],
        )

        activity = schedule.activities[0]
        self.assertIsNone(activity.source_id)
        self.assertIn("EL - Kabeltræk", activity.stable_key)
        self.assertIn("P-kælder -2", activity.stable_key)
        self.assertEqual(activity.location_path, location)
        self.assertEqual(activity.discipline, "Elektriker")
        self.assertTrue(activity.is_late)
        self.assertEqual(activity.inspected_status, "noProgress")
        self.assertEqual(activity.area, "Råhus")
        self.assertEqual(activity.floor, "Basement -2")
        self.assertEqual(activity.phase, "Square")

        chunk_text = to_nusf_chunks(schedule)[0]["content"]
        header = chunk_text.splitlines()[1]
        self.assertIn("is_late", header)
        self.assertIn("inspected_status", header)
        self.assertIn("Basement -2", chunk_text)


    def test_mspdi_critical_and_total_slack_map_to_nusf_critical_path_fields(self):
        schedule = self._normalize(
            [
                "ID", "Aktivitetsnavn", "Startdato", "Slutdato", "Varighed",
                "FuldfÃ¸rt %", "WBS", "ForgÃ¦nger-ID", "Ressourcer",
                "Critical", "TotalSlack",
            ],
            [
                ["1", "Critical task", "01-06-2026", "02-06-2026", "1d", "10", "1", "", "EL", "1", "0"],
                ["2", "Non-critical task", "03-06-2026", "04-06-2026", "1d", "0", "2", "1", "VVS", "0", "2.0"],
            ],
        )

        first, second = schedule.activities
        self.assertTrue(first.critical_flag)
        self.assertEqual(first.total_float, 0)
        self.assertFalse(second.critical_flag)
        self.assertEqual(second.total_float, 2.0)

        chunk_text = to_nusf_chunks(schedule)[0]["content"]
        self.assertIn("critical_flag", chunk_text.splitlines()[1])
        self.assertIn("total_float", chunk_text.splitlines()[1])
        self.assertIn("true;0.0", chunk_text)


if __name__ == "__main__":
    unittest.main()
