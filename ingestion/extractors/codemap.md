# backend/ingestion/extractors/

## Responsibility

Pluggable extractors that decode project-management file formats (PDF, MPP, MSPDI, Excel, CSV) into an intermediate dictionary shape consumed by the ingestion pipeline. Each extractor encapsulates format-specific parsing logic behind a uniform `BaseExtractor` interface.

## Design

**Strategy pattern** via `BaseExtractor` (an ABC defined in `base.py`) with two abstract methods: `extract(file_path: Path) -> Dict[str, Any]` and `source_system() -> str`. The contract return dict always includes keys `headers`, `rows`, `file_name`, `source_system`, and `raw_text`.

**Registry pattern** in `registry.py`: `ExtractorRegistry` holds a class-level `_registry: Dict[str, BaseExtractor]`. Each concrete extractor self-registers on import via a module-level `ExtractorRegistry.register(...)` call — no explicit plugin-discovery loop. The `__init__.py` imports every concrete module for its side-effect registration, then re-exports only `ExtractorRegistry` and `BaseExtractor`.

**Five concrete extractors:**
- `CSVExtractor` — encoding detection (utf-8-sig, latin-1, cp1252), delimiter sniffing via `csv.Sniffer` with fallback to character-frequency heuristic (`csv.py`).
- `ExcelExtractor` — `.xlsx` via `openpyxl` (read-only, data-only); sheet-selection logic preferring active then most-populated sheet; rejects legacy `.xls` at the detector stage (`excel.py`).
- `PDFExtractor` — Azure Document Intelligence OCR (prebuilt-layout, API `2024-11-30`); submits PDF bytes, polls `Operation-Location`, parses table JSON, detects schedule column headers via a known-header set, and merges multiple OCR tables into a canonical schema (`pdf.py`).
- `MPPExtractor` — Microsoft Project `.mpp` via MPXJ v16+ over JPype JVM bridge; thread-safe one-shot JVM start; maps Java task objects to 11-column CSV output with Danish/English headers (`mpp.py`).
- `MspdiExtractor` — MSPDI XML via stdlib `xml.etree.ElementTree`; pure-Python, no JVM; produces the same 11-column schema as MPP; resolves predecessor UIDs to display IDs and resources from assignment elements or "ansvar" extended attribute (`mspdi.py`).

## Data & Control Flow

1. A file path arrives from the ingestion orchestrator (outside this directory).  
2. A detector (in `ingestion/detector/`) identifies the source system string (e.g. `"PDF"`, `"MPP"`).  
3. The pipeline calls `ExtractorRegistry.get(source_system)` to retrieve the matching extractor instance.  
4. It calls `extractor.extract(file_path)`, which reads bytes, parses the format, and returns the standardised dict (`headers`, `rows`, `file_name`, `source_system`, `raw_text`).  
5. The dict proceeds to the normalisation stage (`ingestion/normalizer/`).

## Integration Points

- **Consumer:** `ingestion/detector/` — determines the source system string used to look up the extractor.  
- **Consumer:** `ingestion/normalizer/` — receives the `headers`/`rows` dict produced by any extractor.  
- **Dependency (PDF):** Azure Document Intelligence REST API (`AZURE_DOC_INTELLIGENCE_ENDPOINT`, `AZURE_DOC_INTELLIGENCE_KEY` env vars).  
- **Dependency (MPP):** `JPype1` Python package and JDK 17; `mpxj` Python package (v16+ JARs).  
- **Dependency (Excel):** `openpyxl` Python package.  
- **Dependency (CSV, MSPDI):** Python stdlib only (`csv`, `xml.etree.ElementTree`).

## Public Surface

| Symbol | File | Description |
|---|---|---|
| `BaseExtractor` | `base.py` | Abstract base class with `extract(file_path)` and `source_system()` contract. |
| `ExtractorRegistry` | `registry.py` | Registry with `register()`, `get()`, and `available()` class methods. |
| `CSVExtractor` | `csv.py` | CSV/TSV extractor (delimiter-sniffing, encoding-detection). Source system: `"CSV"`. |
| `ExcelExtractor` | `excel.py` | `.xlsx` extractor via openpyxl. Source system: `"EXCEL"`. |
| `PDFExtractor` | `pdf.py` | PDF extractor via Azure Document Intelligence OCR. Source system: `"PDF"`. |
| `MPPExtractor` | `mpp.py` | `.mpp` extractor via MPXJ/JPype. Source system: `"MPP"`. |
| `MspdiExtractor` | `mspdi.py` | MSPDI XML extractor (pure Python). Source system: `"MSPDI"`. |
