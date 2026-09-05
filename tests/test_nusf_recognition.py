import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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

from ingestion.recognition.heuristics import HeuristicRecognizer


class NusfRecognitionTests(unittest.TestCase):
    def test_tactplan_headers_use_tbs_match_key(self):
        result = HeuristicRecognizer().recognize(
            ["#", "TBS", "Aktivitetstype", "Navn", "Lokation", "Startdato", "Slutdato", "Varighed", "Fremdrift"]
        )

        self.assertEqual(result.match_key, "tbs")
        self.assertEqual(result.column_map["wbs_code"], "TBS")
        self.assertEqual(result.column_map["name"], "Navn")
        self.assertEqual(result.column_map["percent_complete"], "Fremdrift")
        self.assertEqual(result.column_map["activity_type"], "Aktivitetstype")

    def test_plandisc_headers_map_late_and_inspection_fields(self):
        result = HeuristicRecognizer().recognize(
            [
                "name", "location_path", "task_group_name",
                "planned_start_date", "planned_end_date",
                "actual_completion_pct", "is_late", "inspectedType",
            ]
        )

        self.assertEqual(result.match_key, "name_location")
        self.assertEqual(result.column_map["area"], "location_path")
        self.assertEqual(result.column_map["is_late"], "is_late")
        self.assertEqual(result.column_map["inspected_type"], "inspectedType")

    def test_mspdi_headers_map_percent_and_predecessors_without_false_activity_type(self):
        result = HeuristicRecognizer().recognize(
            ["ID", "Aktivitetsnavn", "Startdato", "Slutdato", "Varighed", "Fuldført %", "WBS", "Forgænger-ID", "Ressourcer"]
        )

        self.assertEqual(result.match_key, "id")
        self.assertEqual(result.column_map["source_id"], "ID")
        self.assertEqual(result.column_map["name"], "Aktivitetsnavn")
        self.assertEqual(result.column_map["percent_complete"], "Fuldført %")
        self.assertEqual(result.column_map["predecessors"], "Forgænger-ID")
        self.assertNotIn("activity_type", result.column_map)


    def test_mspdi_headers_map_critical_and_total_slack(self):
        result = HeuristicRecognizer().recognize(
            [
                "ID", "Aktivitetsnavn", "Startdato", "Slutdato", "Varighed",
                "FuldfÃ¸rt %", "WBS", "ForgÃ¦nger-ID", "Ressourcer",
                "Critical", "TotalSlack",
            ]
        )

        self.assertEqual(result.column_map["critical_flag"], "Critical")
        self.assertEqual(result.column_map["total_float"], "TotalSlack")


if __name__ == "__main__":
    unittest.main()
