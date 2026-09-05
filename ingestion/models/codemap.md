# backend/ingestion/models/

## Responsibility
Domain entities / Pydantic models for the NUSF (Normalized Unified Schedule Format) ingestion pipeline. These types define the canonical schema that raw construction schedule data (from PDF/CSV) is mapped into before downstream processing.

## Design
All models use **Pydantic `BaseModel`** with `Field` descriptors for validation constraints (`ge`, `le`, `default_factory`). Two `str, Enum` classes — `DependencyType` (FS/SS/FF/SF) and `ActivityType` (TASK/SUMMARY/MILESTONE/LOE) — provide closed sets of discriminator values. `Provenance` tracks per-field extraction metadata (source column, row index, AI inference flag, confidence score). `Activity` is the richest entity (~25 fields): it carries schedule attributes (WBS hierarchy, planned/actual dates, duration, percent_complete, discipline, location, predecessors/successors as string ID lists), a `provenance: Dict[str, Provenance]` mapping for traceability, and a `has_logic_warning` / `warning_messages` pair for validation feedback. `Relationship` models a dependency edge with type, lag, and broken/inferred flags. `NormalizedSchedule` is the top-level container — it bundles `ScheduleMetadata`, lists of `Activity` and `Relationship`, and a `validation_issues` list with an aggregate `validation_passed` boolean.

## Data & Control Flow
1. Raw schedule rows are parsed (by code elsewhere in `ingestion/`) into `Activity` and `Relationship` instances with per-field `Provenance` entries.  
2. A `ScheduleMetadata` object is populated from source headers and extraction statistics.  
3. A `NormalizedSchedule` root object is assembled from those parts and returned from the ingestion pipeline.  
4. Consumers (e.g. validation or export modules) read fields from the `NormalizedSchedule` — notably `validation_issues` and `has_logic_warning` on individual activities — to drive downstream decisions.

## Integration Points
- **`ingestion/parsers/`** — constructs `Activity`, `Relationship`, `Provenance`, and `ScheduleMetadata` instances from raw data.  
- **`ingestion/validators/`** — reads `Activity.warning_messages`, `Activity.has_logic_warning`, and writes `ValidationIssue` objects into `NormalizedSchedule.validation_issues`.  
- **`__init__.py`** — re-exports all eight public symbols for convenient imports from `ingestion.models`.

## Public Surface
- `DependencyType` — Enum of precedence diagramming method (PDM) link types: FS, SS, FF, SF.
- `ActivityType` — Enum classifying schedule nodes: TASK, SUMMARY, MILESTONE, LOE.
- `Provenance` — Per-field metadata recording source column, row, AI inference flag, and confidence score.
- `Activity` — Normalized schedule activity with WBS, dates, durations, discipline, logic links, provenance, and validation warnings.
- `Relationship` — Dependency edge between two activities with type, lag, and broken/inferred status.
- `ValidationIssue` — Diagnostic record with severity level, category, activity ID, message, and remediation suggestion.
- `ScheduleMetadata` — Top-level schedule summary: project name, source system, date range, parse quality score, and timing.
- `NormalizedSchedule` — Root container model holding metadata, activities, relationships, and validation issues.
