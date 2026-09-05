"""
Tests for the trust-layer harness itself (TL-0.1).

These are not regression tests against a baseline (that's TL-0.2/TL-0.3) —
they prove the harness loads the fixture corpus correctly and that
run_health()/run_predictive() reproduce each fixture's ground truth today.
That combination is what "exercises every branch we are about to change"
(phase-0-safety-net.md) actually means in a runnable form.
"""
from __future__ import annotations

import unittest

from tests.trust.harness import FIXTURES_DIR, load_fixtures, run_health, run_predictive


class LoadFixturesTests(unittest.TestCase):
    def test_at_least_8_fixtures_registered(self):
        fixtures = load_fixtures()
        self.assertGreaterEqual(len(fixtures), 8, f"only found: {[f.id for f in fixtures]}")

    def test_every_fixture_has_ground_truth_attached(self):
        for fixture in load_fixtures():
            self.assertTrue(fixture.ground_truth, f"{fixture.id} has empty ground_truth")
            self.assertIn("expected", fixture.ground_truth, f"{fixture.id} missing 'expected'")
            self.assertIn("brief_ref", fixture.ground_truth, f"{fixture.id} missing 'brief_ref'")

    def test_no_fixture_requires_network_by_default(self):
        # load_fixtures() defaults to include_azure=False; assert the corpus
        # doesn't rely on that skip to stay offline — every fixture found
        # here should genuinely not need Azure/an LLM.
        for fixture in load_fixtures():
            self.assertFalse(
                fixture.requires_azure,
                f"{fixture.id} requires Azure but was not filtered out",
            )

    def test_fixture_files_are_registered_in_readme(self):
        readme = (FIXTURES_DIR / "README.md").read_text(encoding="utf-8")
        for fixture in load_fixtures():
            self.assertIn(
                fixture.id, readme,
                f"{fixture.id} has no row in fixtures/README.md",
            )


class RunHealthGroundTruthTests(unittest.TestCase):
    """Runs every 'pair' fixture through run_health() and checks whichever
    facts its ground_truth['expected'] declares. Not every fixture asserts
    every possible field — only the ones the fixture exists to pin down
    (see fixtures/README.md 'Adding a fixture')."""

    def test_pair_fixtures_match_ground_truth(self):
        for fixture in load_fixtures():
            if fixture.kind != "pair":
                continue
            with self.subTest(fixture=fixture.id):
                self._check_pair(fixture)

    def _check_pair(self, fixture):
        expected = fixture.ground_truth["expected"]
        result = run_health(fixture)

        self.assertIsNone(result["old_pipeline_error"], fixture.id)
        self.assertIsNone(result["new_pipeline_error"], fixture.id)

        if "old_activity_count" in expected:
            self.assertEqual(
                result["old_schedule"]["activity_count"], expected["old_activity_count"], fixture.id
            )
        if "new_activity_count" in expected:
            self.assertEqual(
                result["new_schedule"]["activity_count"], expected["new_activity_count"], fixture.id
            )
        if "old_logic_warning_count" in expected:
            self.assertEqual(
                result["old_schedule"]["logic_warning_count"],
                expected["old_logic_warning_count"], fixture.id,
            )
        if "old_issue_rules" in expected:
            self.assertEqual(
                result["old_schedule"]["issue_rules"], expected["old_issue_rules"], fixture.id
            )
        if "old_validation_passed" in expected:
            self.assertEqual(
                result["old_schedule"]["validation_passed"],
                expected["old_validation_passed"], fixture.id,
            )

        comparison = result["comparison"]
        needs_comparison = any(
            k in expected
            for k in (
                "added", "removed", "changed_count", "behind_schedule_count",
                "ahead_of_schedule_count", "critical_count",
                "point_of_no_return_count", "project_health",
                "comparison_selected_activities", "comparison_progress_actual_pcts",
            )
        )
        if not needs_comparison:
            return
        self.assertIsNotNone(comparison, f"{fixture.id}: expected a comparison but got None")

        if "added" in expected:
            self.assertCountEqual(
                comparison["changed_activities"]["added"], expected["added"], fixture.id
            )
        if "removed" in expected:
            self.assertCountEqual(
                comparison["changed_activities"]["removed"], expected["removed"], fixture.id
            )
        if "changed_count" in expected:
            self.assertEqual(
                len(comparison["changed_activities"]["changes"]), expected["changed_count"], fixture.id
            )
        if "behind_schedule_count" in expected:
            self.assertEqual(
                comparison["executive_summary"]["behind_schedule_count"],
                expected["behind_schedule_count"], fixture.id,
            )
        if "ahead_of_schedule_count" in expected:
            self.assertEqual(
                comparison["executive_summary"]["ahead_of_schedule_count"],
                expected["ahead_of_schedule_count"], fixture.id,
            )
        if "critical_count" in expected:
            self.assertEqual(
                comparison["executive_summary"]["critical_count"],
                expected["critical_count"], fixture.id,
            )
        if "point_of_no_return_count" in expected:
            self.assertEqual(
                comparison["executive_summary"]["point_of_no_return_count"],
                expected["point_of_no_return_count"], fixture.id,
            )
        if "project_health" in expected:
            self.assertEqual(
                comparison["executive_summary"]["project_health"],
                expected["project_health"], fixture.id,
            )
        if "comparison_selected_activities" in expected:
            self.assertEqual(
                comparison["executive_summary"]["selected_activities"],
                expected["comparison_selected_activities"], fixture.id,
            )
        if "comparison_progress_actual_pcts" in expected:
            actual_pcts = {
                item["activity"]: item["actual_pct"]
                for item in comparison["progress_vs_expected"]
            }
            self.assertEqual(
                actual_pcts, expected["comparison_progress_actual_pcts"], fixture.id
            )


class RunHealthSingleFixtureTests(unittest.TestCase):
    """'single' fixtures (currently just the empty/headers-only case) exercise
    ingestion in isolation — there is no second side to compare against."""

    def test_single_fixtures_match_ground_truth(self):
        for fixture in load_fixtures():
            if fixture.kind != "single":
                continue
            with self.subTest(fixture=fixture.id):
                self._check_single(fixture)

    def _check_single(self, fixture):
        expected = fixture.ground_truth["expected"]
        result = run_health(fixture)

        if expected.get("old_pipeline_raises"):
            self.assertIsNotNone(result["old_pipeline_error"], fixture.id)
            needle = expected.get("old_pipeline_error_contains")
            if needle:
                self.assertIn(needle, result["old_pipeline_error"], fixture.id)
        self.assertIsNone(result["comparison"], fixture.id)


class RunPredictiveTests(unittest.TestCase):
    """run_predictive() is a Phase-0 placeholder (see harness.py docstring) —
    it must never disagree with run_health(), and it must never touch the
    network. It has no ground_truth of its own; these are structural checks."""

    def test_predictive_facts_derive_from_health_not_a_separate_computation(self):
        for fixture in load_fixtures():
            if fixture.kind != "pair":
                continue
            with self.subTest(fixture=fixture.id):
                health = run_health(fixture)
                predictive = run_predictive(fixture)
                if health["comparison"] is None:
                    self.assertIsNone(predictive["predictive_facts"])
                    continue
                summary = health["comparison"]["executive_summary"]
                facts = predictive["predictive_facts"]
                self.assertEqual(facts["delayed_count"], summary["behind_schedule_count"])
                self.assertEqual(facts["critical_count"], summary["critical_count"])

    def test_single_fixture_predictive_facts_are_none(self):
        for fixture in load_fixtures():
            if fixture.kind != "single":
                continue
            self.assertIsNone(run_predictive(fixture)["predictive_facts"], fixture.id)


if __name__ == "__main__":
    unittest.main()
