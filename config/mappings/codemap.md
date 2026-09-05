# backend/config/mappings/

## Responsibility
Per-format YAML lookup tables that map semantic field names (e.g. `planned_start`, `discipline`) to source-specific column headers. These static mappings are merged with heuristic recognition results in the normalization pipeline, providing a configurable fallback when heuristics return no match.

## Design
Each `.yaml` file is a flat dictionary of `semantic_role: raw_column_header` pairs. Both `csv.yaml` and `pdf.yaml` contain identical Danish-to-English mappings (13 keys each) covering fields such as `source_id` → `"Id"`, `name` → `"Opgavenavn"`, `planned_start` → `"Startdato"`, `duration` → `"Varighed"`, `discipline` → `"Ansvarlig"`, and `area` → `"omr."`. The key set is fixed; there is no nested structure or schema versioning. The files are consumed exclusively through the `FieldMapper` class, which merges the static YAML content with a runtime `heuristic_map` — heuristics take priority, static config fills gaps.

## Data & Control Flow
1. `engine.py` receives a `source_system` string (e.g. `"csv"`, `"pdf"`) from the extraction layer.
2. `engine.py` constructs a `FieldMapper(source_system, recognition.column_map)` in `NormalizationEngine.normalize()` (line 154).
3. `FieldMapper.__init__()` calls `_load_yaml_mapping(source_system)`, which resolves `<source_system>.yaml` inside `_CONFIG_DIR` (line 15: `config/mappings/`) and parses it via `yaml.safe_load()` or the fallback `_parse_simple_yaml()`.
4. `FieldMapper.get(semantic_role)` returns the heuristic value if present, otherwise the static YAML value (line 68).
5. `engine.py` calls `mapper.get(...)` for each of 18 semantic roles (lines 156–175) to resolve the raw column name before extracting cell values from rows.

## Integration Points
- **Loader:** `backend/ingestion/normalization/mappings.py` — `FieldMapper` class, `_load_yaml_mapping()`.
- **Consumer:** `backend/ingestion/normalization/engine.py` — `NormalizationEngine.normalize()` reads resolved column names and builds `Activity` objects.
- **Fallback parser:** `mappings._parse_simple_yaml()` — used when the `yaml` package is unavailable.

## File Inventory
| File | Purpose | Loaded By |
|---|---|---|
| `csv.yaml` | Static mapping of 13 semantic roles to Danish CSV column headers | `mappings._load_yaml_mapping("csv")` |
| `pdf.yaml` | Static mapping of 13 semantic roles to Danish PDF-extracted column headers | `mappings._load_yaml_mapping("pdf")` |
