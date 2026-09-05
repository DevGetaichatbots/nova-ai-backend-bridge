import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.experimental.nusf_compare_engine import compare_nusf_chunks


def _chunk(rows):
    header = (
        "source_id;stable_key;name;planned_start;planned_finish;percent_complete;"
        "activity_type;wbs_code;discipline;location_path;area;floor;phase;"
        "duration_hours;actual_start;actual_finish;is_late;inspected_status;"
        "critical_flag;total_float;predecessors;successors"
    )
    return [{"content": "\n".join(["FORMAT: NUSF CSV - each row = one activity.", header, *rows])}]


class NusfCompareEngineTests(unittest.TestCase):
    def _assert_change_in(self, changes, expected):
        for change in changes:
            if all(change.get(k) == v for k, v in expected.items()):
                return
        self.fail(f"{expected} not found (as subset) in {changes}")

    def test_detects_added_removed_finish_changes_and_progress_status(self):
        old_chunks = _chunk(
            [
                "1;1;EL - Cable install;01-06-2026;10-06-2026;30;TASK;1;Electrical;Project / Building A / 1.;;1. Floor;Phase 1;80;;;false;;false;5;;",
                "2;2;VVS - Pipe install;01-06-2026;12-06-2026;40;TASK;2;Plumbing;Project / Building A / Basement;;Basement;Phase 1;80;;;false;;false;8;;",
                "3;3;VENT - Removed fan;01-06-2026;08-06-2026;20;TASK;3;Ventilation;Project / Building B / Roof;;Roof;Phase 2;80;;;false;;false;3;;",
            ]
        )
        new_chunks = _chunk(
            [
                "1;1;EL - Cable install;01-06-2026;20-06-2026;25;TASK;1;Electrical;Project / Building A / 1.;;1. Floor;Phase 1;80;;;true;noProgress;true;0;;",
                "2;2;VVS - Pipe install;01-06-2026;10-06-2026;100;TASK;2;Plumbing;Project / Building A / Basement;;Basement;Phase 1;80;;;false;;false;8;;",
                "4;4;ARK - New wall;11-06-2026;14-06-2026;0;TASK;4;Architecture;Project / Building C / 2.;;2. Floor;Phase 3;80;;;false;;false;4;;",
            ]
        )

        data = compare_nusf_chunks(old_chunks, new_chunks, reference_date="06-06-2026")

        self.assertEqual(data["executive_summary"]["selected_activities"], 3)
        self.assertEqual(data["executive_summary"]["added_activities"], 1)
        self.assertEqual(data["executive_summary"]["trade_counts"]["EL"], 1)
        self.assertEqual(data["executive_summary"]["trade_counts"]["VVS"], 1)
        self.assertEqual(data["changed_activities"]["added"], ["ARK - New wall"])
        self.assertEqual(data["changed_activities"]["removed"], ["VENT - Removed fan"])
        self._assert_change_in(
            data["changed_activities"]["changes"],
            {"activity": "EL - Cable install", "change_type": "Finish Date", "old": "10-06-2026", "new": "20-06-2026"},
        )
        self._assert_change_in(
            data["changed_activities"]["changes"],
            {"activity": "VVS - Pipe install", "change_type": "Finish Date", "old": "12-06-2026", "new": "10-06-2026"},
        )
        behind = [i for i in data["progress_vs_expected"] if i["status"] == "behind"]
        ahead = [i for i in data["progress_vs_expected"] if i["status"] == "ahead"]
        self.assertEqual([i["activity"] for i in behind], ["EL - Cable install"])
        self.assertEqual([i["activity"] for i in ahead], ["VVS - Pipe install"])
        self.assertEqual(data["critical_path_activities"][0]["activity"], "EL - Cable install")
        self.assertIn("Building A", data["filter_options"]["areas"])
        self.assertIn("1. Floor", data["filter_options"]["floors"])
        self.assertIn("Phase 1", data["filter_options"]["phases"])

    def test_plandisc_late_flag_marks_activity_behind_even_when_dates_are_equal(self):
        old_chunks = _chunk(
            [
                "old;EL - Rough-in | Project / Core / Basement -2;EL - Rough-in;01-06-2026;20-06-2026;50;TASK;;Electrical;Project / Core / Basement -2;Core;Basement -2;Square;80;;;false;;false;5;;",
            ]
        )
        new_chunks = _chunk(
            [
                "new;EL - Rough-in | Project / Core / Basement -2;EL - Rough-in;01-06-2026;20-06-2026;50;TASK;;Electrical;Project / Core / Basement -2;Core;Basement -2;Square;80;;;true;noProgress;false;5;;",
            ]
        )

        data = compare_nusf_chunks(old_chunks, new_chunks, reference_date="10-06-2026")

        row = data["progress_vs_expected"][0]
        self.assertEqual(row["activity"], "EL - Rough-in")
        self.assertEqual(row["status"], "behind")
        self.assertEqual(row["late_flag"], True)
        self.assertEqual(data["executive_summary"]["behind_schedule_count"], 1)
        self.assertIn("Core", data["filter_options"]["areas"])
        self.assertIn("Basement -2", data["filter_options"]["floors"])
        self.assertIn("Square", data["filter_options"]["phases"])

    def test_unstable_positional_ids_fall_back_to_name_location_date_matching(self):
        # Simulates a source tool (e.g. Holm8) that regenerates row IDs as
        # "<name>_<ordinal>" on every export, so raw IDs are not a stable
        # cross-version join key even though the underlying activities are
        # unchanged. Old and new use disjoint raw IDs for the same two
        # "Daek" activities at the same location; matching must fall back to
        # name+location, pairing by date order rather than by raw ID.
        old_chunks = _chunk(
            [
                "Daek_0;Daek_0;Daek;01-06-2026;05-06-2026;50;TASK;;Concrete;Project / Building A / 2. Floor;Building A;2. Floor;;40;;;false;;false;5;;",
                "Daek_1;Daek_1;Daek;10-06-2026;15-06-2026;20;TASK;;Concrete;Project / Building A / 2. Floor;Building A;2. Floor;;40;;;false;;false;5;;",
            ]
        )
        new_chunks = _chunk(
            [
                "Daek_0;Daek_0;Daek;01-06-2026;06-06-2026;100;TASK;;Concrete;Project / Building A / 2. Floor;Building A;2. Floor;;40;;;false;;false;5;;",
                "Daek_1;Daek_1;Daek;10-06-2026;16-06-2026;40;TASK;;Concrete;Project / Building A / 2. Floor;Building A;2. Floor;;40;;;false;;false;5;;",
                "Daek_2;Daek_2;Daek;20-06-2026;25-06-2026;0;TASK;;Concrete;Project / Building A / 2. Floor;Building A;2. Floor;;40;;;false;;false;5;;",
            ]
        )

        data = compare_nusf_chunks(old_chunks, new_chunks, reference_date="01-06-2026")

        # The two earlier activities are matched by date order within the
        # name+location group (not by their unrelated raw IDs), and the
        # third, genuinely new activity is reported as added rather than
        # spuriously matched against a leftover old row.
        self.assertEqual(data["changed_activities"]["added"], ["Daek"])
        self.assertEqual(data["changed_activities"]["removed"], [])
        self._assert_change_in(
            data["changed_activities"]["changes"],
            {"activity": "Daek", "change_type": "Finish Date", "old": "05-06-2026", "new": "06-06-2026"},
        )
        self._assert_change_in(
            data["changed_activities"]["changes"],
            {"activity": "Daek", "change_type": "Finish Date", "old": "15-06-2026", "new": "16-06-2026"},
        )

    def test_group_size_change_does_not_cascade_wrong_pairings(self):
        # A same-named, same-location group whose size differs between old and
        # new (e.g. a rolling 6-week look-ahead plan that picks up a new task)
        # must not let one inserted/removed member shift every later pairing
        # in date-sorted order. Four "Isolering" activities exist in both
        # versions (one unchanged, one unchanged, two both shifted by the same
        # +2 days); the new version also gains a brand-new fifth instance that
        # sorts in between the first two by date. A naive sort+zip pairing
        # cascades: it pairs the unrelated inserted row against an existing
        # old row and pushes every following pairing off by one, producing a
        # false "changed" diff against an activity that never moved. Greedy
        # nearest-date matching must instead report the fifth row as added and
        # keep the other four correctly paired.
        old_chunks = _chunk(
            [
                "234;234;Isolering;03-05-2026;30-05-2026;90;TASK;;;Project / A;A;;;80;;;false;;false;5;;",
                "251;251;Isolering;06-05-2026;20-05-2026;0;TASK;;;Project / B;B;;;80;;;false;;false;5;;",
                "266;266;Isolering;01-06-2026;15-06-2026;0;TASK;;;Project / C;C;;;80;;;false;;false;5;;",
                "284;284;Isolering;01-06-2026;15-06-2026;0;TASK;;;Project / D;D;;;80;;;false;;false;5;;",
            ]
        )
        new_chunks = _chunk(
            [
                "234;234;Isolering;03-05-2026;30-05-2026;90;TASK;;;Project / A;A;;;80;;;false;;false;5;;",
                "999;999;Isolering;04-05-2026;19-05-2026;0;TASK;;;Project / E;E;;;80;;;false;;false;5;;",
                "252;252;Isolering;06-05-2026;20-05-2026;0;TASK;;;Project / B;B;;;80;;;false;;false;5;;",
                "269;269;Isolering;03-06-2026;17-06-2026;0;TASK;;;Project / C;C;;;80;;;false;;false;5;;",
                "288;288;Isolering;03-06-2026;17-06-2026;0;TASK;;;Project / D;D;;;80;;;false;;false;5;;",
            ]
        )

        data = compare_nusf_chunks(old_chunks, new_chunks, reference_date="01-05-2026")

        self.assertEqual(data["changed_activities"]["added"], ["Isolering"])
        self.assertEqual(data["changed_activities"]["removed"], [])
        # The unchanged 06-05->20-05 activity (location B) must not appear as
        # a "changed" entry — the bug pulled it in as a false Start/Finish
        # Date change when the inserted row shifted the sort-zip alignment.
        for change in data["changed_activities"]["changes"]:
            self.assertFalse(
                change["change_type"] in ("Start Date", "Finish Date") and change["old"] == "20-05-2026",
                f"unchanged activity falsely reported as changed: {change}",
            )
        self._assert_change_in(
            data["changed_activities"]["changes"],
            {"activity": "Isolering", "change_type": "Finish Date", "old": "15-06-2026", "new": "17-06-2026"},
        )


if __name__ == "__main__":
    unittest.main()
