# backend/ingestion/validation/

## Responsibility

Structural and logical integrity validation for normalized ingestion data. Enforces four rules (101–104) on a `NormalizedSchedule`, producing `ValidationIssue` objects that are attached to the schedule. Error-level issues cause the pipeline to reject the schedule; warning-level issues are attached without blocking ingestion.

## Design

**Rule-based Collector pattern.** `ValidationEngine.validate()` (defined in `engine.py`) runs four private rule methods (`_rule_101` through `_rule_104`), each collecting a list of `ValidationIssue` objects into a single accumulator. The accumulator is then scanned for any `LEVEL_ERROR` issues to set `schedule.validation_passed`.

**Factory helpers for issues.** `issues.py` provides four factory functions (`rule_101_date_logic`, `rule_102_circular`, `rule_103_dangling`, `rule_104_out_of_sequence`) that construct `ValidationIssue` instances with a consistent level, category, message, and remediation string. Issue levels (`LEVEL_ERROR`, `LEVEL_WARNING`, `LEVEL_INFO`) and categories (`CAT_STRUCTURAL`, `CAT_LOGICAL`, `CAT_QUALITY`) are module-level constants.

**Iterative DFS for cycle detection.** `_rule_102` uses an explicit stack-based DFS with a `Set`-backed `on_stack` to detect circular dependency chains without hitting Python recursion limits.

**Entry point.** `ValidationEngine` is the sole public class, re-exported via `__init__.py`.

## Data & Control Flow

1. `ValidationEngine.validate(schedule)` is called by the pipeline with a fully normalized `NormalizedSchedule`.
2. Each rule method iterates over `schedule.activities` or `schedule.relationships`, appending issues to a list.
3. After all rules run, the accumulator is checked for any issue with `level == LEVEL_ERROR`.
4. `schedule.validation_issues` is set to the issue list; `schedule.validation_passed` is set to `False` if any error-level issue exists, else `True`.
5. The mutated `NormalizedSchedule` is returned to the pipeline, which either rejects (on error) or continues (on warning/clean).

## Integration Points

- **Depends on:** `ingestion.models.nusf` — provides `NormalizedSchedule` and `ValidationIssue` data classes.
- **Consumed by:** `ingestion.pipeline` — calls `ValidationEngine.validate()` after normalization and before the writer stage.
- **All issues currently use `LEVEL_WARNING`**, meaning no schedule is ever blocked by validation today (`engine.py` lines 64–65, 70, 74, 78 document this explicitly).

## Public Surface

- `ValidationEngine` (`engine.py`/`__init__.py`) — Class with a single public method `validate(schedule)` that runs all rules and returns the annotated schedule.
- `LEVEL_ERROR` / `LEVEL_WARNING` / `LEVEL_INFO` (`issues.py`) — String constants for issue severity levels.
- `CAT_STRUCTURAL` / `CAT_LOGICAL` / `CAT_QUALITY` (`issues.py`) — String constants for issue categories.
- `rule_101_date_logic(activity_id, start, finish)` (`issues.py`) — Factory for inverted-date warnings.
- `rule_102_circular(activity_ids)` (`issues.py`) — Factory for circular-dependency warnings.
- `rule_103_dangling(relationship_desc, missing_id)` (`issues.py`) — Factory for dangling-reference warnings.
- `rule_104_out_of_sequence(activity_id, task_name)` (`issues.py`) — Factory for out-of-sequence progress warnings.
