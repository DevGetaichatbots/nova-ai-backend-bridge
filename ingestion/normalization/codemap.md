# backend/ingestion/normalization/

## Responsibility

Normalization pipeline that transforms raw extracted schedule records (headers + rows) into canonical `NormalizedSchedule` objects (NUSF model). Also provides bridge serializers (`to_compact_csv_chunks`, `to_nusf_chunks`) that emit semicolon-separated CSV chunks consumed by LLM agents and vector-store endpoints.

## Design

**Pipeline pattern** — `NormalizationEngine.normalize()` (in `engine.py`) orchestrates a sequential transform: field resolution via `FieldMapper`, date/duration parsing via `parse_date`/`parse_duration_to_hours` (`dates.py`), dependency graph construction via `build_relationships` (`relationships.py`), and assembly of a typed `NormalizedSchedule`. The `FieldMapper` (`mappings.py`) implements a **Config‑Driven Mapper** that loads per-source-system YAML field mappings from `config/mappings/<source>.yaml`, merged with heuristic column maps produced by the recognition stage (heuristic takes priority). Relationship resolution (`relationships.py`) uses a regex-based dependency token parser supporting FS/SS/FF/SF types with hour-level lag, and marks broken references with `is_broken=True`. Date parsing (`dates.py`) handles Danish day-prefixed, ISO 8601, European dd-mm-yyyy, American mm/dd/yyyy, and Primavera formats, returning UTC-aware `datetime` objects.

## Data & Control Flow

1. `NormalizationEngine.normalize()` receives raw `{headers, rows}` dict + `RecognitionResult` + source metadata.  
2. `FieldMapper` resolves semantic roles (e.g. `"name"`, `"planned_start"`) to concrete column names via `mapper.get()`.  
3. Each row is iterated: date strings are parsed, duration strings converted to hours, activity type detected via heuristics (milestone/summary/task), and location paths decomposed into `area`/`floor`/`phase`.  
4. A `Provenance` record is attached per field tracking source column, row index, inference flag, and confidence.  
5. Raw predecessor/successor strings are collected keyed by internal UUID; `build_relationships()` parses these into typed `Relationship` objects with deduplication.  
6. Relationship edges are back-populated onto `Activity.predecessors`/`Activity.successors` lists.  
7. A `ScheduleMetadata` object is computed (activity count, date range, quality score, parse duration) and the final `NormalizedSchedule` is returned.

## Integration Points

- **Upstream**: consumes `RecognitionResult` from `ingestion.recognition.heuristics` (`engine.py` line 31).  
- **Model layer**: depends on `ingestion.models.nusf` for `NormalizedSchedule`, `Activity`, `Relationship`, `Provenance`, `ActivityType`, `DependencyType` etc.  
- **Config**: loads YAML mapping files from `backend/config/mappings/<source_system>.yaml` via `mappings.py` line 18.  
- **Downstream**: callers (API endpoints / vector-store ingestion) consume the returned `NormalizedSchedule` or the CSV chunks from `to_compact_csv_chunks()` / `to_nusf_chunks()`.

## Public Surface

- `__init__.NormalizationEngine` — re-exported alias for `engine.NormalizationEngine`.  
- `engine.NormalizationEngine.normalize()` — core method: raw data → `NormalizedSchedule`.  
- `engine.NormalizationEngine.to_compact_csv_chunks()` — bridge: original headers/rows → compact CSV chunks (legacy LLM format).  
- `engine.to_nusf_chunks()` — standalone function: `NormalizedSchedule` → NUSF-format CSV chunks (v2 endpoints).  
- `dates.parse_date()` — parse a date string from multiple known formats; returns UTC-aware `datetime` or `None`.  
- `dates.parse_duration_to_hours()` — convert duration strings (`"50d"`, `"3u"`, `"48"`) to integer working hours.  
- `mappings.FieldMapper` — loads per-source YAML config and merges with heuristic recognition map; provides `get(semantic_role)` and `all_mappings()`.  
- `relationships.build_relationships()` — build typed `Relationship` objects from raw predecessor/successor dictionaries.  
- `relationships.parse_predecessor_string()` — parse a single predecessor field value into `(source_id, dep_type, lag_hours)` tuples.
