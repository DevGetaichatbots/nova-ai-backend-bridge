"""
Validation Engine
=================
Enforces the 4 structural and logical integrity rules on a NormalizedSchedule.

Rule 101: planned_start <= planned_finish  (ERROR, STRUCTURAL)
Rule 102: No circular dependencies         (ERROR, LOGICAL)
Rule 103: No dangling relationship refs    (WARNING, STRUCTURAL)
Rule 104: No out-of-sequence progress      (WARNING, QUALITY)

Pipeline behaviour:
- ERROR-level issues → validation_passed = False → pipeline returns error
- WARNING-level issues → validation_passed stays True, issues attached to schedule
"""
from __future__ import annotations
import logging
from typing import List, Set, Dict

from ingestion.models.nusf import NormalizedSchedule, ValidationIssue
from ingestion.validation.issues import (
    rule_101_date_logic,
    rule_102_circular,
    rule_103_dangling,
    rule_104_out_of_sequence,
    LEVEL_ERROR,
)

logger = logging.getLogger(__name__)


class ValidationEngine:
    def validate(self, schedule: NormalizedSchedule) -> NormalizedSchedule:
        issues: List[ValidationIssue] = []

        issues.extend(self._rule_101(schedule))
        issues.extend(self._rule_102(schedule))
        issues.extend(self._rule_103(schedule))
        issues.extend(self._rule_104(schedule))

        has_errors = any(i.level == LEVEL_ERROR for i in issues)

        schedule.validation_issues = issues
        schedule.validation_passed = not has_errors

        if issues:
            errors = [i for i in issues if i.level == LEVEL_ERROR]
            warnings = [i for i in issues if i.level != LEVEL_ERROR]
            logger.info(
                f"[{schedule.metadata.source_filename}] Validation: "
                f"{len(errors)} errors, {len(warnings)} warnings, "
                f"passed={schedule.validation_passed}"
            )
        else:
            logger.info(
                f"[{schedule.metadata.source_filename}] Validation: all rules passed"
            )

        return schedule

    def _rule_101(self, schedule: NormalizedSchedule) -> List[ValidationIssue]:
        """
        Rule 101: planned_start <= planned_finish.
        Normalization auto-swaps inverted dates (marked via has_logic_warning),
        so this check catches any remaining inversions as WARNINGs rather than
        hard ERRORs — ensuring files are never blocked by corrected date swaps.
        """
        issues = []
        for act in schedule.activities:
            if act.planned_start > act.planned_finish:
                issues.append(
                    rule_101_date_logic(
                        act.internal_id,
                        act.planned_start.isoformat(),
                        act.planned_finish.isoformat(),
                    )
                )
        return issues

    def _rule_102(self, schedule: NormalizedSchedule) -> List[ValidationIssue]:
        """Detect circular dependencies using iterative DFS (no recursion limit risk)."""
        issues = []
        activity_ids: Set[str] = {a.internal_id for a in schedule.activities}

        adj: Dict[str, List[str]] = {a.internal_id: [] for a in schedule.activities}
        for rel in schedule.relationships:
            if rel.is_broken:
                continue
            if rel.predecessor_id in adj:
                adj[rel.predecessor_id].append(rel.successor_id)

        visited: Set[str] = set()
        reported_cycles: Set[str] = set()

        for start in list(adj.keys()):
            if start in visited:
                continue
            # Iterative DFS — each stack frame: (node, iterator-over-neighbours, path-so-far)
            stack: List[tuple] = [(start, iter(adj.get(start, [])), [start])]
            on_stack: Set[str] = {start}
            visited.add(start)

            while stack:
                node, children, path = stack[-1]
                try:
                    neighbour = next(children)
                    if neighbour not in activity_ids:
                        continue
                    if neighbour in on_stack:
                        cycle_key = "→".join(sorted(path + [neighbour]))
                        if cycle_key not in reported_cycles:
                            reported_cycles.add(cycle_key)
                            issues.append(rule_102_circular(path + [neighbour]))
                    elif neighbour not in visited:
                        visited.add(neighbour)
                        on_stack.add(neighbour)
                        stack.append((neighbour, iter(adj.get(neighbour, [])), path + [neighbour]))
                except StopIteration:
                    stack.pop()
                    on_stack.discard(node)

        return issues

    def _rule_103(self, schedule: NormalizedSchedule) -> List[ValidationIssue]:
        issues = []
        activity_ids: Set[str] = {a.internal_id for a in schedule.activities}
        for rel in schedule.relationships:
            if rel.is_broken:
                missing = rel.predecessor_id if rel.predecessor_id not in activity_ids else rel.successor_id
                missing_source = missing.replace("__unknown_", "")
                issues.append(
                    rule_103_dangling(
                        f"Relationship pred={rel.predecessor_id} → succ={rel.successor_id}",
                        missing_source,
                    )
                )
        return issues

    def _rule_104(self, schedule: NormalizedSchedule) -> List[ValidationIssue]:
        issues = []
        for act in schedule.activities:
            if act.percent_complete > 0 and act.actual_start is None:
                issues.append(rule_104_out_of_sequence(act.internal_id, act.name[:60]))
        return issues
