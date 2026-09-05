"""
Shared OCR client for Nova's Azure Document Intelligence integration.

This package is the single source of truth for:
- Submitting a PDF to Azure Document Intelligence's `prebuilt-layout` model.
- Polling the operation URL until the analysis completes.
- Parsing the response into structured tables whose cells carry the
  TL-1.2 evidence fields (`spans`, `page_number`, `bounding_box`,
  `ocr_confidence`).

TL-1.3 extracted this code from two previously-duplicate
implementations:

- `src/azure_ocr.py` (used by the legacy `/upload` raw path)
- `ingestion/extractors/pdf.py` (used by the NUSF pipeline)

Both paths now import from this package. They differ only in what they
do with the structured output:

- `src.azure_ocr.AzureDocumentIntelligence.extract_from_pdf` exposes
  the rich cell dicts in its return shape.
- `ingestion.extractors.pdf.PDFExtractor.extract_from_bytes` runs
  schedule-aware post-processing (header detection, table merging,
  text-layer fallback) on top of the same structured output.

The v2 router in `ingestion/routes/` was designed precisely so
`ingestion/` would not import from `src/` — the dependency direction
is preserved here: both `src.azure_ocr` and `ingestion.extractors.pdf`
import from `ocr_client`, never from each other.

See `changes/trust-layer/plan/phase-1-provenance.md` (TL-1.3) and
ADR-011 for the architectural rationale and the Q-1 resolution.
"""
from .azure import (
    API_VERSION,
    derive_cell_confidence,
    parse_tables,
    poll_results,
    submit_pdf,
    word_confidences_in_span,
)

__all__ = [
    "API_VERSION",
    "submit_pdf",
    "poll_results",
    "parse_tables",
    "word_confidences_in_span",
    "derive_cell_confidence",
]
