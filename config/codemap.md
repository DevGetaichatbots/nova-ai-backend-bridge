# backend/config/

## Responsibility

Static configuration package acting as a data directory of YAML-based column-mapping profiles and a Python package marker (`__init__.py` is empty). These profiles define how raw column names from external project-schedule sources (CSV, PDF) map to canonical semantic roles used throughout the ingestion pipeline.

## Design

- **File-system-separated concerns**: Each source system gets its own YAML file under `mappings/` — `csv.yaml` and `pdf.yaml`.
- **Client-side loading**: The YAML files are not loaded by this package itself. Instead, the consumer (`ingestion/normalization/mappings.py`) builds a `_CONFIG_DIR = Path(__file__).parent.parent.parent / "config" / "mappings"` path and loads the file via `_load_yaml_mapping()` at `FieldMapper` construction time.
- **No Python runtime abstraction**: The `__init__.py` exports nothing. All configuration data is read directly from the filesystem by downstream code.

## Data & Control Flow

1. `FieldMapper(source_system, heuristic_map)` is instantiated with a source system name (e.g. `"csv"`).
2. `_load_yaml_mapping(source_system)` resolves `<source_system>.yaml` under `config/mappings/`.
3. The YAML is deserialised (via `yaml.safe_load` or a fallback `_parse_simple_yaml` which does no deps).
4. `FieldMapper.get(semantic_role)` returns the raw column name, preferring heuristic results over static YAML values.
5. A merged dict is available via `FieldMapper.all_mappings()`.

## Integration Points

- `backend/ingestion/normalization/mappings.py` — creates `FieldMapper` instances and loads the YAML profiles by filesystem path.
- Downstream callers of `FieldMapper` inside the ingestion pipeline (normalization engine, extractors).

## Sub-Module Map

| Subdirectory | Responsibility Summary | Detailed Map |
|---|---|---|
| `mappings/` | Column-mapping YAML files (`csv.yaml`, `pdf.yaml`) defining Danish-to-semantic field name translations for each source system. | [codemap](mappings/codemap.md) |
