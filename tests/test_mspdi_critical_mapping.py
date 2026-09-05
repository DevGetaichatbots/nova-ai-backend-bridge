import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

fake_requests = ModuleType("requests")
fake_requests.exceptions = SimpleNamespace(RequestException=Exception)
sys.modules.setdefault("requests", fake_requests)

fake_openpyxl = ModuleType("openpyxl")
fake_openpyxl.Workbook = object
fake_openpyxl.load_workbook = lambda *_args, **_kwargs: None
sys.modules.setdefault("openpyxl", fake_openpyxl)

from ingestion.extractors.mspdi import MspdiExtractor
from ingestion.normalization.engine import NormalizationEngine
from ingestion.recognition.heuristics import HeuristicRecognizer


MSPDI_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Tasks>
    <Task>
      <UID>1</UID>
      <ID>1</ID>
      <Name>Critical XML task</Name>
      <Start>2026-06-01T08:00:00</Start>
      <Finish>2026-06-02T16:00:00</Finish>
      <Duration>PT8H0M0S</Duration>
      <PercentComplete>10</PercentComplete>
      <WBS>1</WBS>
      <Critical>1</Critical>
      <TotalSlack>0</TotalSlack>
    </Task>
    <Task>
      <UID>2</UID>
      <ID>2</ID>
      <Name>Non-critical XML task</Name>
      <Start>2026-06-03T08:00:00</Start>
      <Finish>2026-06-04T16:00:00</Finish>
      <Duration>PT8H0M0S</Duration>
      <PercentComplete>0</PercentComplete>
      <WBS>2</WBS>
      <Critical>0</Critical>
      <TotalSlack>9600</TotalSlack>
      <PredecessorLink>
        <PredecessorUID>1</PredecessorUID>
      </PredecessorLink>
    </Task>
  </Tasks>
</Project>
"""


class MspdiCriticalMappingTests(unittest.TestCase):
    def test_mspdi_extractor_emits_critical_and_total_slack_columns(self):
        extracted = MspdiExtractor().extract_from_bytes(MSPDI_XML, "sample.xml")

        self.assertIn("Critical", extracted["headers"])
        self.assertIn("TotalSlack", extracted["headers"])
        critical_idx = extracted["headers"].index("Critical")
        slack_idx = extracted["headers"].index("TotalSlack")
        self.assertEqual(extracted["rows"][0][critical_idx], "1")
        self.assertEqual(extracted["rows"][0][slack_idx], "0.0")
        self.assertEqual(extracted["rows"][1][critical_idx], "0")
        self.assertEqual(extracted["rows"][1][slack_idx], "2.0")

    def test_mspdi_critical_fields_survive_normalization(self):
        extracted = MspdiExtractor().extract_from_bytes(MSPDI_XML, "sample.xml")
        recognition = HeuristicRecognizer().recognize(extracted["headers"])
        schedule = NormalizationEngine().normalize(
            extracted=extracted,
            recognition=recognition,
            source_system="MSPDI",
            filename="sample.xml",
        )

        first, second = schedule.activities
        self.assertTrue(first.critical_flag)
        self.assertEqual(first.total_float, 0)
        self.assertFalse(second.critical_flag)
        self.assertEqual(second.total_float, 2.0)
        self.assertEqual(len(schedule.relationships), 1)


if __name__ == "__main__":
    unittest.main()
