"""
Tests for the regression comparison runner and blocking release gates (TL-0.3 / TL-9.6).

Per Brief §36 & §39:
- Critical-field extraction regression — NOT ALLOWED (blocks build)
- False-match regression — NOT ALLOWED (blocks build)
- Known calculation regression — NOT ALLOWED (blocks build)
- Unsupported-claim-rate regression — NOT ALLOWED (blocks build)
- Override requires a recorded justification in DECISIONS.md
- Hard failures (fixture crashes) always fail the build and cannot be overridden
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from tests.trust.harness import (
    GATE_CRITICAL_FIELD_EXTRACTION,
    GATE_FALSE_MATCH,
    GATE_KNOWN_CALCULATION,
    GATE_UNSUPPORTED_CLAIMS,
    MatchMetrics,
    _fixture_snapshot,
    compare_against_baseline,
    load_fixtures,
    validate_gate_override,
)


class RegressionRunnerTests(unittest.TestCase):
    def test_unchanged_tree_reports_no_regressions_and_exits_zero(self):
        report = compare_against_baseline()
        self.assertEqual(report.exit_code, 0)
        self.assertFalse(report.has_hard_failure)
        self.assertFalse(report.has_gate_failures)
        self.assertEqual(report.diffs, [])
        self.assertEqual(report.gate_regressions(), {})
        self.assertIn("no regressions", report.render())

    def test_deliberately_broken_field_produces_a_regressed_line(self):
        target = "01_clean_durable_ids"

        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == target:
                snapshot["health"]["comparison"]["executive_summary"]["behind_schedule_count"] = 0
            return snapshot

        report = compare_against_baseline(snapshot_fn=broken_snapshot)

        # Brief §36 / TL-9.6: release gates are BLOCKING (previously informational in Phase 0)
        self.assertEqual(report.exit_code, 1, "a regression must fail the build in Phase 9 (Brief §36, TL-9.6)")
        self.assertTrue(report.has_gate_failures)
        self.assertIn(GATE_KNOWN_CALCULATION, report.gate_regressions())
        self.assertIn("RELEASE GATES BLOCKED", report.render())

        regressed = [g for g in report.graded if g.verdict == "REGRESSED"]
        self.assertTrue(
            any(g.fixture_id == target and g.field == "behind_schedule_count" for g in regressed),
            f"expected a REGRESSED line naming {target}.behind_schedule_count, got: {report.graded}",
        )
        self.assertTrue(
            any(d.fixture_id == target and "behind_schedule_count" in d.path for d in report.diffs),
            "the categorized diff should also name the same fixture/field",
        )

    def test_fixing_a_previously_wrong_baseline_produces_an_improved_line(self):
        # Mirror image of the REGRESSED case: the *baseline* is wrong
        # relative to ground truth, and the current snapshot fixes it.
        target = "01_clean_durable_ids"
        fixture = next(f for f in load_fixtures() if f.id == target)

        broken_baseline = copy.deepcopy(_fixture_snapshot(fixture))
        broken_baseline["health"]["comparison"]["executive_summary"]["behind_schedule_count"] = 0

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / f"{target}.json").write_text(
                json.dumps(broken_baseline, sort_keys=True), encoding="utf-8"
            )
            report = compare_against_baseline([fixture], baselines_dir=tmp_dir)

        improved = [g for g in report.graded if g.verdict == "IMPROVED"]
        self.assertTrue(
            any(g.fixture_id == target and g.field == "behind_schedule_count" for g in improved),
            f"expected an IMPROVED line, got: {report.graded}",
        )
        self.assertFalse(report.has_gate_failures, "improvements must not trigger gate failures")
        self.assertEqual(report.exit_code, 0)

    def test_crashing_fixture_is_a_hard_failure_even_though_informational(self):
        target = "02_mspdi_positional_id"

        def crashing_snapshot(fixture):
            if fixture.id == target:
                raise RuntimeError("simulated parser crash")
            return _fixture_snapshot(fixture)

        report = compare_against_baseline(snapshot_fn=crashing_snapshot)

        self.assertTrue(report.has_hard_failure)
        self.assertEqual(report.exit_code, 1)
        crashed_ids = {f.fixture_id for f in report.fixtures if f.status == "crashed"}
        self.assertIn(target, crashed_ids)

    def test_report_distinguishes_the_named_regression_classes(self):
        # brief §36: critical-field extraction, false match (-> match_set),
        # known calculation (-> count/KPI); plus new_failures (this task's Do §1).
        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == "01_clean_durable_ids":
                # critical-field extraction: the extracted count itself is wrong
                snapshot["health"]["old_schedule"]["activity_count"] = 999
            elif fixture.id == "05_ambiguous_no_forced_match":
                # false match: something now claims to be added that wasn't
                snapshot["health"]["comparison"]["changed_activities"]["added"].append(
                    "Spurious Forced Match"
                )
            elif fixture.id == "06_zero_delayed":
                # known calculation: a KPI count is wrong
                snapshot["health"]["comparison"]["executive_summary"]["behind_schedule_count"] = 5
            elif fixture.id == "08_empty_headers_only":
                # new failure: a fixture that used to (correctly) fail to load
                # now silently reports no error at all
                snapshot["health"]["old_pipeline_error"] = None
            return snapshot

        report = compare_against_baseline(snapshot_fn=broken_snapshot)
        categories = {d.category for d in report.diffs}
        self.assertIn("critical_field_extraction", categories)
        self.assertIn("match_set", categories)
        self.assertIn("count", categories)
        self.assertIn("new_failures", categories)
        self.assertTrue(report.has_gate_failures)
        self.assertEqual(report.exit_code, 1)


class BlockingReleaseGatesTests(unittest.TestCase):
    """Specific tests verifying each of the four release gates blocks on regression (Brief §36, §39)."""

    def test_gate_critical_field_extraction_blocks(self):
        target = "01_clean_durable_ids"

        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == target:
                snapshot["health"]["old_schedule"]["activity_count"] = 999
            return snapshot

        report = compare_against_baseline(snapshot_fn=broken_snapshot)
        self.assertTrue(report.has_gate_failures)
        self.assertEqual(report.exit_code, 1)
        failures = report.gate_regressions()
        self.assertIn(GATE_CRITICAL_FIELD_EXTRACTION, failures)
        self.assertIn("RELEASE GATES BLOCKED", report.render())

    def test_gate_false_match_blocks_on_spurious_match(self):
        target = "05_ambiguous_no_forced_match"

        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == target:
                snapshot["health"]["comparison"]["changed_activities"]["added"].append(
                    "Spurious Forced Match"
                )
            return snapshot

        report = compare_against_baseline(snapshot_fn=broken_snapshot)
        self.assertTrue(report.has_gate_failures)
        self.assertEqual(report.exit_code, 1)
        failures = report.gate_regressions()
        self.assertIn(GATE_FALSE_MATCH, failures)
        self.assertIn("RELEASE GATES BLOCKED", report.render())

    def test_gate_false_match_blocks_on_nonzero_rate(self):
        report = compare_against_baseline()
        bad_metric = MatchMetrics("01_clean_durable_ids", 0.90, 0.05, 0.05, 0.0)
        report.metrics = [bad_metric]
        self.assertTrue(report.has_gate_failures)
        self.assertEqual(report.exit_code, 1)
        self.assertIn(GATE_FALSE_MATCH, report.gate_regressions())

    def test_gate_known_calculation_blocks(self):
        target = "06_zero_delayed"

        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == target:
                snapshot["health"]["comparison"]["executive_summary"]["behind_schedule_count"] = 5
            return snapshot

        report = compare_against_baseline(snapshot_fn=broken_snapshot)
        self.assertTrue(report.has_gate_failures)
        self.assertEqual(report.exit_code, 1)
        failures = report.gate_regressions()
        self.assertIn(GATE_KNOWN_CALCULATION, failures)
        self.assertIn("RELEASE GATES BLOCKED", report.render())

    def test_gate_unsupported_claim_rate_blocks_on_excess_contradictions(self):
        from src.trust.claims import UnsupportedClaimMetric
        report = compare_against_baseline()
        report.unsupported_metric = UnsupportedClaimMetric(
            verified_count=6, contradicted_count=3, unverifiable_count=3, total_claims=12
        )
        report.unsupported_offending = [
            ("TL67-Q5-fabricated-number-contradicted", "47 activities"),
            ("TL67-Q6-fabricated-id-contradicted", "Task ID T999"),
            ("TL67-Q1-delayed-count-clean", "spurious contradicted claim"),
        ]
        self.assertTrue(report.has_gate_failures)
        self.assertEqual(report.exit_code, 1)
        failures = report.gate_regressions()
        self.assertIn(GATE_UNSUPPORTED_CLAIMS, failures)
        self.assertIn("RELEASE GATES BLOCKED", report.render())

    def test_gate_unsupported_claim_rate_blocks_when_contradiction_net_fails(self):
        from src.trust.claims import UnsupportedClaimMetric
        report = compare_against_baseline()
        # If Q5 is no longer caught as contradicted (adversarial fixture slipped through)
        report.unsupported_metric = UnsupportedClaimMetric(
            verified_count=7, contradicted_count=1, unverifiable_count=3, total_claims=11
        )
        report.unsupported_offending = [
            ("TL67-Q6-fabricated-id-contradicted", "Task ID T999")
        ]
        self.assertTrue(report.has_gate_failures)
        self.assertEqual(report.exit_code, 1)
        failures = report.gate_regressions()
        self.assertIn(GATE_UNSUPPORTED_CLAIMS, failures)


class GateOverrideProcedureTests(unittest.TestCase):
    """Tests for the Brief §36 recorded DECISIONS.md override procedure."""

    def test_gate_override_with_recorded_adr_passes(self):
        target = "01_clean_durable_ids"

        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == target:
                snapshot["health"]["comparison"]["executive_summary"]["behind_schedule_count"] = 0
            return snapshot

        report = compare_against_baseline(
            snapshot_fn=broken_snapshot,
            override_adr="ADR-049",
            override_reason="Temporary migration override documented in ADR-049 for verification",
        )
        self.assertTrue(report.has_gate_failures, "regressions still detected")
        self.assertTrue(report.override.is_valid, "override is valid")
        self.assertEqual(report.exit_code, 0, "exit code must be 0 when valid override is recorded")
        rendered = report.render()
        self.assertIn("RELEASE GATE OVERRIDE ACTIVE", rendered)
        self.assertIn("ADR-049", rendered)
        self.assertIn("PROCEEDING (exit code 0)", rendered)

    def test_gate_override_with_unrecorded_adr_fails(self):
        target = "01_clean_durable_ids"

        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == target:
                snapshot["health"]["comparison"]["executive_summary"]["behind_schedule_count"] = 0
            return snapshot

        report = compare_against_baseline(
            snapshot_fn=broken_snapshot,
            override_adr="ADR-999",
            override_reason="Justification for unrecorded ADR that should be rejected by gate check",
        )
        self.assertTrue(report.has_gate_failures)
        self.assertFalse(report.override.is_valid)
        self.assertEqual(report.exit_code, 1, "unrecorded ADR must not allow override")
        rendered = report.render()
        self.assertIn("RELEASE GATES BLOCKED", rendered)
        self.assertIn("ADR-999 not found in", rendered)

    def test_gate_override_with_short_reason_fails(self):
        target = "01_clean_durable_ids"

        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == target:
                snapshot["health"]["comparison"]["executive_summary"]["behind_schedule_count"] = 0
            return snapshot

        report = compare_against_baseline(
            snapshot_fn=broken_snapshot,
            override_adr="ADR-049",
            override_reason="too short",
        )
        self.assertTrue(report.has_gate_failures)
        self.assertFalse(report.override.is_valid)
        self.assertEqual(report.exit_code, 1)
        self.assertIn("Override justification too short", report.render())

    def test_gate_override_via_environment_variables(self):
        target = "01_clean_durable_ids"

        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == target:
                snapshot["health"]["comparison"]["executive_summary"]["behind_schedule_count"] = 0
            return snapshot

        old_adr = os.environ.get("NOVA_TRUST_GATE_OVERRIDE_ADR")
        old_reason = os.environ.get("NOVA_TRUST_GATE_OVERRIDE_REASON")
        try:
            os.environ["NOVA_TRUST_GATE_OVERRIDE_ADR"] = "ADR-049"
            os.environ["NOVA_TRUST_GATE_OVERRIDE_REASON"] = "Environment override authorized under ADR-049"
            report = compare_against_baseline(snapshot_fn=broken_snapshot)
            self.assertTrue(report.has_gate_failures)
            self.assertTrue(report.override.is_valid)
            self.assertEqual(report.exit_code, 0)
        finally:
            if old_adr is not None:
                os.environ["NOVA_TRUST_GATE_OVERRIDE_ADR"] = old_adr
            else:
                os.environ.pop("NOVA_TRUST_GATE_OVERRIDE_ADR", None)
            if old_reason is not None:
                os.environ["NOVA_TRUST_GATE_OVERRIDE_REASON"] = old_reason
            else:
                os.environ.pop("NOVA_TRUST_GATE_OVERRIDE_REASON", None)

    def test_gate_override_via_combined_env_var(self):
        target = "01_clean_durable_ids"

        def broken_snapshot(fixture):
            snapshot = _fixture_snapshot(fixture)
            if fixture.id == target:
                snapshot["health"]["comparison"]["executive_summary"]["behind_schedule_count"] = 0
            return snapshot

        old_combined = os.environ.get("NOVA_TRUST_GATE_OVERRIDE")
        try:
            os.environ["NOVA_TRUST_GATE_OVERRIDE"] = "ADR-049: Combined override format authorized for testing"
            report = compare_against_baseline(snapshot_fn=broken_snapshot)
            self.assertTrue(report.has_gate_failures)
            self.assertTrue(report.override.is_valid)
            self.assertEqual(report.exit_code, 0)
        finally:
            if old_combined is not None:
                os.environ["NOVA_TRUST_GATE_OVERRIDE"] = old_combined
            else:
                os.environ.pop("NOVA_TRUST_GATE_OVERRIDE", None)

    def test_hard_failure_cannot_be_overridden(self):
        target = "02_mspdi_positional_id"

        def crashing_snapshot(fixture):
            if fixture.id == target:
                raise RuntimeError("simulated parser crash")
            return _fixture_snapshot(fixture)

        report = compare_against_baseline(
            snapshot_fn=crashing_snapshot,
            override_adr="ADR-049",
            override_reason="Hard crash cannot be overridden under any circumstances",
        )
        self.assertTrue(report.has_hard_failure)
        self.assertEqual(report.exit_code, 1, "crashes are hard failures and can never be overridden")


class RegressionCLITests(unittest.TestCase):
    def test_cli_compare_exits_zero_on_unchanged_tree(self):
        from tests.trust.harness import main

        exit_code = main(["compare"])
        self.assertEqual(exit_code, 0)

    def test_cli_compare_with_override_flags(self):
        from tests.trust.harness import main

        exit_code = main([
            "compare",
            "--override-adr", "ADR-049",
            "--override-reason", "CLI comparison with valid recorded ADR and justification",
        ])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()

