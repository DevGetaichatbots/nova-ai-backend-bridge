"""
Tests for the baseline snapshot runner (TL-0.2).

The plan's own Verify command is a CLI + `git diff --exit-code`, which this
repo checkout cannot exercise directly (there is no `.git` here — see
DECISIONS.md ADR-005). These tests encode the same acceptance criteria in a
form `pytest` can run and CI can enforce regardless of git availability:
one snapshot per offline fixture, re-running produces byte-identical output,
and no snapshot leaks a UUID/timestamp/free-text field.
"""
from __future__ import annotations

import json
import re
import unittest

from tests.trust.harness import BASELINES_DIR, load_fixtures, write_baselines

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_ISO_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


class BaselineSnapshotTests(unittest.TestCase):
    def test_writes_one_snapshot_per_offline_fixture(self):
        fixtures = load_fixtures()
        written = write_baselines(fixtures)
        self.assertEqual(
            {p.name for p in written},
            {f"{f.id}.json" for f in fixtures},
        )
        for path in written:
            self.assertTrue(path.is_file())

    def test_rerun_is_byte_identical(self):
        # First run establishes a known state; the second must reproduce it
        # exactly. This is TL-0.2's core acceptance criterion — a baseline
        # that isn't stable across runs would train everyone to ignore diffs.
        write_baselines()
        before = {p.name: p.read_text(encoding="utf-8") for p in BASELINES_DIR.glob("*.json")}

        write_baselines()
        after = {p.name: p.read_text(encoding="utf-8") for p in BASELINES_DIR.glob("*.json")}

        self.assertEqual(before, after)

    def test_snapshots_contain_no_uuid_or_timestamp_or_rendered_html(self):
        write_baselines()
        for path in BASELINES_DIR.glob("*.json"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, _UUID_RE, f"{path.name} leaks a UUID")
            self.assertNotRegex(text, _ISO_TIMESTAMP_RE, f"{path.name} leaks an ISO timestamp")
            self.assertNotIn("<html", text.lower(), f"{path.name} contains rendered HTML")
            self.assertNotIn("<!doctype", text.lower(), f"{path.name} contains rendered HTML")

    def test_snapshot_is_valid_json_with_expected_top_level_shape(self):
        write_baselines()
        for fixture in load_fixtures():
            path = BASELINES_DIR / f"{fixture.id}.json"
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(snapshot["fixture_id"], fixture.id)
            self.assertIn("health", snapshot)
            self.assertIn("predictive", snapshot)

    def test_stale_baseline_is_removed(self):
        BASELINES_DIR.mkdir(parents=True, exist_ok=True)
        stale = BASELINES_DIR / "__nonexistent_fixture__.json"
        stale.write_text("{}", encoding="utf-8")
        try:
            write_baselines()
            self.assertFalse(stale.exists())
        finally:
            stale.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
