"""Tests for the validation-level contract (TL-0.5).

The plan's `Acceptance criteria` for TL-0.5 explicitly require that:

- Docstring and emitted levels agree for all four rules
- A fixture with a circular dependency produces `validation_passed = False`
- A fixture with only warnings still produces `validation_passed = True`

These drive `ValidationEngine` directly against minimal in-memory
`NormalizedSchedule` fixtures, so they do not depend on the
`tests/trust/fixtures/` corpus and they do not depend on Azure OCR or
the LLM. They are permanent regression tests for the level contract.
"""
from __future__ import annotations

import inspect
from datetime import datetime

import pytest

from ingestion.models.nusf import (
    Activity,
    ActivityType,
    DependencyType,
    NormalizedSchedule,
    Provenance,
    Relationship,
    ScheduleMetadata,
    ValidationIssue,
)
from ingestion.validation import engine as engine_module
from ingestion.validation.engine import ValidationEngine
from ingestion.validation.issues import (
    LEVEL_ERROR,
    LEVEL_WARNING,
    rule_101_date_logic,
    rule_102_circular,
    rule_103_dangling,
    rule_104_out_of_sequence,
)


# ---------------------------------------------------------------------------
# Minimal schedule builders
# ---------------------------------------------------------------------------

def _provenance() -> dict:
    """Bare-minimum provenance mapping — one field, full confidence."""
    return {
        "name": Provenance(source_field="Name", column_mapping_confidence=1.0),
    }


def _make_activity(
    internal_id: str,
    *,
    source_id: str | None = None,
    name: str | None = None,
    planned_start: datetime | None = None,
    planned_finish: datetime | None = None,
    actual_start: datetime | None = None,
    percent_complete: float = 0.0,
) -> Activity:
    return Activity(
        internal_id=internal_id,
        source_id=source_id if source_id is not None else internal_id,
        name=name or internal_id,
        planned_start=planned_start or datetime(2026, 1, 1),
        planned_finish=planned_finish or datetime(2026, 1, 2),
        actual_start=actual_start,
        duration_hours=8,
        percent_complete=percent_complete,
        activity_type=ActivityType.TASK,
        provenance=_provenance(),
    )


def _make_schedule(
    activities: list[Activity],
    relationships: list[Relationship] | None = None,
    *,
    filename: str = "synthetic.csv",
) -> NormalizedSchedule:
    return NormalizedSchedule(
        metadata=ScheduleMetadata(
            project_name="Synthetic",
            source_system="CSV",
            source_filename=filename,
            data_date=datetime(2026, 1, 15),
            total_activities=len(activities),
            total_relationships=len(relationships or []),
            earliest_date=datetime(2026, 1, 1),
            latest_date=datetime(2026, 1, 31),
            duration_days=30,
            parse_quality_score=1.0,
        ),
        activities=activities,
        relationships=relationships or [],
        validation_passed=True,  # provisional; engine overwrites
    )


# ---------------------------------------------------------------------------
# AC1 — Docstring and emitted levels agree for all four rules
# ---------------------------------------------------------------------------

class TestLevelAgreement:
    """The plan states: 'Decide the intended level per rule and make code
    and docstring agree.' The 'code' half is the `level` argument inside
    each `rule_*` factory in `issues.py`; the 'docstring' half is the
    table at the top of `engine.py`. These tests pin both halves to the
    levels chosen in TL-0.5 (recorded in ADR-007)."""

    EXPECTED_LEVELS: dict[str, str] = {
        "101": LEVEL_WARNING,  # date inversion — auto-swapped upstream
        "102": LEVEL_ERROR,    # circular dependency — structurally unsafe
        "103": LEVEL_WARNING,  # dangling reference
        "104": LEVEL_WARNING,  # out-of-sequence progress
    }

    def test_rule_factory_levels_match_contract(self):
        """The factory's emitted level equals the contract."""
        # rule 101
        issue = rule_101_date_logic("A1", "2026-01-02", "2026-01-01")
        assert issue.level == self.EXPECTED_LEVELS["101"]
        # rule 102
        issue = rule_102_circular(["A1", "A2", "A1"])
        assert issue.level == self.EXPECTED_LEVELS["102"]
        # rule 103
        issue = rule_103_dangling("pred=A → succ=B", "A")
        assert issue.level == self.EXPECTED_LEVELS["103"]
        # rule 104
        issue = rule_104_out_of_sequence("A1", "Activity One")
        assert issue.level == self.EXPECTED_LEVELS["104"]

    def test_docstring_levels_match_contract(self):
        """The engine module docstring table documents the same levels
        the factories emit. We parse the four `Rule NNN:` lines and
        check the level token in each."""
        # The table lives at the module level (above the class) because
        # that is where the plan/audit-audience expects to read it.
        docstring = inspect.getdoc(engine_module) or ""
        # Expected substring fragments the docstring must contain, one per rule.
        expected_fragments = {
            "101": "Rule 101:",
            "102": "Rule 102:",
            "103": "Rule 103:",
            "104": "Rule 104:",
        }
        for rule_no, fragment in expected_fragments.items():
            line = next(
                (ln for ln in docstring.splitlines() if ln.strip().startswith(fragment)),
                None,
            )
            assert line is not None, (
                f"engine.py docstring is missing the table entry for "
                f"{fragment!r}; either it was removed or renamed."
            )
            expected_level = self.EXPECTED_LEVELS[rule_no]
            assert expected_level in line, (
                f"engine.py docstring line for {rule_no!r} does not mention "
                f"its contracted level {expected_level!r}; got: {line!r}"
            )

    def test_rule_102_is_the_only_error(self):
        """Defence-in-depth: only one rule is contracted to be ERROR.
        If a future task promotes another rule to ERROR without updating
        this test, the test surfaces the decision — promoting everything
        to ERROR is explicitly the failure mode the plan warns against
        ('Do not make every rule ERROR')."""
        error_rules = [
            n for n, lvl in self.EXPECTED_LEVELS.items() if lvl == LEVEL_ERROR
        ]
        assert error_rules == ["102"], (
            f"only Rule 102 is contracted to ERROR; got {error_rules!r}. "
            "If you meant to promote another rule, update this test AND "
            "record the rationale in DECISIONS.md."
        )


# ---------------------------------------------------------------------------
# AC2 — A schedule with a circular dependency produces
#        validation_passed = False (and the right error level)
# ---------------------------------------------------------------------------

class TestCircularDependencyGates:
    def _schedule_with_cycle(self) -> NormalizedSchedule:
        # Two activities with A → B and B → A.
        a = _make_activity("a-uuid", source_id="A", name="A")
        b = _make_activity("b-uuid", source_id="B", name="B")
        rels = [
            Relationship(
                predecessor_id="a-uuid",
                successor_id="b-uuid",
                type=DependencyType.FS,
            ),
            Relationship(
                predecessor_id="b-uuid",
                successor_id="a-uuid",
                type=DependencyType.FS,
            ),
        ]
        return _make_schedule([a, b], rels, filename="circular.csv")

    def test_circular_schedule_fails_validation(self):
        engine = ValidationEngine()
        sched = self._schedule_with_cycle()
        result = engine.validate(sched)
        assert result.validation_passed is False, (
            "a schedule with a circular dependency must produce "
            "validation_passed=False; this is the structural-safety "
            "guarantee that ADR-007 commits to."
        )

    def test_circular_schedule_emits_rule_102_at_error_level(self):
        engine = ValidationEngine()
        sched = self._schedule_with_cycle()
        result = engine.validate(sched)
        rule_102_errors = [
            i for i in result.validation_issues
            if "Rule 102" in i.message and i.level == LEVEL_ERROR
        ]
        assert rule_102_errors, (
            "expected at least one Rule 102 ERROR issue on a cyclic schedule"
        )


# ---------------------------------------------------------------------------
# AC3 — A schedule with only warnings still passes validation
# ---------------------------------------------------------------------------

class TestWarningsOnlyStillPass:
    def _schedule_with_only_warnings(self) -> NormalizedSchedule:
        """One activity with `percent_complete > 0` and no `actual_start`
        triggers Rule 104 (out-of-sequence progress) at WARNING. No
        inversions, no cycles, no dangling refs."""
        a = _make_activity(
            "a-uuid",
            source_id="A",
            name="In Progress Task",
            percent_complete=25.0,
            actual_start=None,  # explicit; this is what triggers Rule 104
        )
        return _make_schedule([a], relationships=[], filename="warnings.csv")

    def test_warnings_only_schedule_passes(self):
        engine = ValidationEngine()
        sched = self._schedule_with_only_warnings()
        result = engine.validate(sched)
        assert result.validation_passed is True, (
            "a schedule that fires only Rule 104 (WARNING) must still "
            "produce validation_passed=True; if this fails, either Rule "
            "104 was promoted to ERROR or the engine's gating logic "
            "regressed."
        )

    def test_warnings_only_emits_rule_104_at_warning(self):
        engine = ValidationEngine()
        sched = self._schedule_with_only_warnings()
        result = engine.validate(sched)
        rule_104_issues = [i for i in result.validation_issues if "Rule 104" in i.message]
        assert rule_104_issues, "expected Rule 104 to fire on this fixture"
        assert all(i.level == LEVEL_WARNING for i in rule_104_issues), (
            f"Rule 104 issues must all be WARNING; got "
            f"{[i.level for i in rule_104_issues]!r}"
        )


# ---------------------------------------------------------------------------
# Defence-in-depth: a pristine schedule passes, with no issues.
# ---------------------------------------------------------------------------

class TestPristineSchedule:
    def test_clean_schedule_emits_no_issues_and_passes(self):
        a = _make_activity(
            "a-uuid", source_id="A", name="Clean Task",
            percent_complete=0.0, actual_start=None,
        )
        b = _make_activity(
            "b-uuid", source_id="B", name="Clean Task 2",
            percent_complete=0.0, actual_start=None,
        )
        rels = [
            Relationship(
                predecessor_id="a-uuid",
                successor_id="b-uuid",
                type=DependencyType.FS,
            ),
        ]
        sched = _make_schedule([a, b], rels, filename="clean.csv")
        engine = ValidationEngine()
        result = engine.validate(sched)
        assert result.validation_passed is True
        assert result.validation_issues == []


# ---------------------------------------------------------------------------
# Structural invariant: the `engine.py` module exposes the right symbols.
# ---------------------------------------------------------------------------

class TestEngineSurface:
    def test_engine_exposes_validation_engine_class(self):
        assert hasattr(engine_module, "ValidationEngine")

    def test_engine_imports_level_error_constant(self):
        """Defence-in-depth: the `has_errors` check in `validate()` keys
        on `LEVEL_ERROR`. If someone deletes the import (or renames the
        constant in `issues.py` without updating the import), the gating
        silently breaks — `has_errors` always evaluates to False and
        `validation_passed` is always True. This test catches that."""
        assert hasattr(engine_module, "LEVEL_ERROR")
        assert engine_module.LEVEL_ERROR == "ERROR"
