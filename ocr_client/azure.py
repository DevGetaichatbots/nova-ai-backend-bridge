"""
Shared Azure Document Intelligence client — submit, poll, parse.

Extracted in TL-1.3 from two previously-duplicate implementations
(`src.azure_ocr` and `ingestion.extractors.pdf`). Both now import from
here, preserving the v2-router-enforced dependency direction (neither
`src` nor `ingestion` imports the other).

Public surface:
- `submit_pdf(...)`: POST the PDF; return the operation URL.
- `poll_results(...)`: poll until succeeded/failed; return the
  full Azure response dict.
- `parse_tables(result, filename)`: turn the Azure response into a
  list of structured tables. Each cell carries the TL-1.2 evidence
  fields (`spans`, `page_number`, `bounding_box`, `ocr_confidence`).
- `word_confidences_in_span(...)` / `derive_cell_confidence(...)`:
  helpers, public so test code can drive them directly.

The TL-1.2 design notes (ADR-010) apply here: cell confidence is the
MINIMUM of word confidences; `None` is the load-bearing sentinel for
"not OCR-derived"; the half-open interval `[span_start, span_end)` is
the word/span overlap convention.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

import requests


logger = logging.getLogger(__name__)


API_VERSION = "2024-11-30"


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

def submit_pdf(
    pdf_bytes: bytes,
    filename: str,
    endpoint: str,
    key: str,
) -> Optional[str]:
    """Submit a PDF to Azure Document Intelligence's `prebuilt-layout`
    model and return the operation URL. Returns `None` on failure
    (caller logs and decides how to surface it).

    Both `src.azure_ocr` and `ingestion.extractors.pdf` previously
    duplicated this loop with diverging error messages. They now share
    one implementation; the divergence was a drift risk (TL-1.3 Do).
    """
    url = (
        f"{endpoint.rstrip('/')}/documentintelligence/documentModels/"
        f"prebuilt-layout:analyze?api-version={API_VERSION}"
        f"&outputContentFormat=markdown"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/pdf",
    }
    try:
        logger.info(
            f"[{filename}] Submitting PDF to Azure "
            f"({len(pdf_bytes)} bytes, api={API_VERSION})..."
        )
        response = requests.post(url, headers=headers, data=pdf_bytes, timeout=60)
        response.raise_for_status()
        op_url = response.headers.get("Operation-Location")
        if not op_url:
            logger.error(f"[{filename}] No Operation-Location in Azure response")
            return None
        logger.info(f"[{filename}] Azure operation started")
        return op_url
    except requests.exceptions.RequestException as e:
        logger.error(f"[{filename}] Azure submit failed: {e}")
        return None


def poll_results(
    operation_url: str,
    filename: str,
    key: str,
    timeout: int = 180,
) -> Optional[Dict]:
    """Poll the Azure operation URL until the analysis completes.
    Returns the full Azure response dict on success, `None` on
    failure or timeout.

    Adaptive back-off: 1s for the first 30s, then 2s after that.
    Avoids hammering Azure on slow jobs while staying responsive
    on fast ones. The pattern was identical in both pre-TL-1.3
    implementations; one copy survives here.
    """
    headers = {"Ocp-Apim-Subscription-Key": key}
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            logger.error(f"[{filename}] Azure polling timeout after {timeout}s")
            return None
        interval = 1 if elapsed < 30 else 2
        try:
            resp = requests.get(operation_url, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            status = result.get("status", "unknown")
            logger.info(
                f"[{filename}] Azure status: {status} "
                f"(elapsed: {elapsed:.1f}s, next poll in {interval}s)"
            )
            if status == "succeeded":
                logger.info(f"[{filename}] Azure extraction complete in {elapsed:.1f}s")
                return result
            elif status == "failed":
                logger.error(f"[{filename}] Azure failed: {result.get('error', {})}")
                return None
            elif status in ("notStarted", "running"):
                time.sleep(interval)
            else:
                logger.warning(f"[{filename}] Azure unknown status: {status}")
                time.sleep(interval)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{filename}] Azure polling error: {e}")
            time.sleep(interval)


# ---------------------------------------------------------------------------
# Per-cell OCR confidence helpers
# ---------------------------------------------------------------------------

def word_confidences_in_span(
    span_start: int,
    span_length: int,
    pages_words: List[Dict],
) -> List[float]:
    """Return the word confidences whose `span` overlaps the
    half-open interval `[span_start, span_start + span_length)`.

    Words without a `confidence` field are silently skipped — Azure
    is allowed to omit it; what we cannot do is invent a value.
    Returns an empty list when no word in `pages_words` overlaps,
    so the caller can distinguish "no overlap" from "lowest
    confidence is exactly 0.0".
    """
    if span_length <= 0:
        return []
    span_end = span_start + span_length
    out: List[float] = []
    for word in pages_words:
        word_span = word.get("span") or {}
        word_start = word_span.get("offset", 0)
        word_length = word_span.get("length", 0)
        word_end = word_start + word_length
        if word_end <= span_start:
            continue
        if word_start >= span_end:
            continue
        confidence = word.get("confidence")
        if confidence is None:
            continue
        out.append(float(confidence))
    return out


def derive_cell_confidence(
    cell_spans: List[Dict],
    pages_words: List[Dict],
) -> Optional[float]:
    """Derive a cell's OCR confidence as the *minimum* word
    confidence across all of the cell's spans.

    Returns `None` when:
    - the cell has no spans (Azure response missing them),
    - none of the document's words overlap any of the cell's spans,
    - every overlapping word omitted its confidence.

    Never returns `1.0` as a default. `1.0` means "this was a clean
    OCR read"; treating absence as `1.0` is the "confidently wrong"
    failure the brief exists to prevent (TL-1.2 Do-not rule).
    """
    if not cell_spans:
        return None
    all_confidences: List[float] = []
    for span in cell_spans:
        offset = span.get("offset", 0)
        length = span.get("length", 0)
        all_confidences.extend(
            word_confidences_in_span(offset, length, pages_words)
        )
    if not all_confidences:
        return None
    return min(all_confidences)


# ---------------------------------------------------------------------------
# Table parsing — the rich-cell shape with TL-1.2 evidence fields
# ---------------------------------------------------------------------------

def parse_tables(result: Dict, filename: str) -> List[Dict]:
    """Parse Azure's `tables[]` response into structured table dicts.

    Each returned table has the envelope shape:

    ```
    {
        "table_id":           int,
        "row_count":          int,
        "column_count":       int,
        "page_numbers":       sorted list of int,
        "rows":               2D list of strings (simple grid;
                              the `^...` merged-cell placeholder is
                              stripped here, matching the pre-TL-1.2
                              contract used by downstream consumers),
        "cells":              list of cell dicts with TL-1.2
                              evidence fields,
        "has_merged_cells":   bool,
    }
    ```

    Each cell dict carries:

    - `content`         (pre-TL-1.2)
    - `row`, `col`      (pre-TL-1.2)
    - `row_span`, `col_span`  (pre-TL-1.2)
    - `kind`            (pre-TL-1.2)
    - `spans`           (TL-1.2, additive)
    - `page_number`     (TL-1.2, additive)
    - `bounding_box`    (TL-1.2, additive)
    - `ocr_confidence`  (TL-1.2, additive; min of word confidences or
                        `None` if unresolvable)

    The envelope and the cell keys are additive (D3): no existing
    pre-TL-1.2 key is renamed, removed, or retyped.
    """
    try:
        analyze_result = result.get("analyzeResult", {})
        tables = analyze_result.get("tables", [])
        pages_data = analyze_result.get("pages", [])

        # Flatten every page's `words[]` into one list keyed by span
        # in the shared document content string. Azure reports
        # confidence per word; per-cell confidence is derived by
        # resolving the cell's `spans` against this list.
        pages_words: List[Dict] = []
        for page in pages_data:
            pages_words.extend(page.get("words", []) or [])

        if not tables:
            return []

        structured_tables: List[Dict] = []
        for table_idx, table in enumerate(tables):
            row_count = table.get("rowCount", 0)
            col_count = table.get("columnCount", 0)
            cells_data = table.get("cells", [])

            grid = [
                [{"content": "", "row_span": 1, "col_span": 1} for _ in range(col_count)]
                for _ in range(row_count)
            ]

            cells_list: List[Dict] = []
            for cell in cells_data:
                row_idx = cell.get("rowIndex", 0)
                col_idx = cell.get("columnIndex", 0)
                cell_content = cell.get("content", "")
                row_span = cell.get("rowSpan", 1)
                col_span = cell.get("columnSpan", 1)
                kind = cell.get("kind", "content")

                # --- TL-1.2: capture the evidence Azure was already
                # returning. None of these keys change any existing
                # key on the cell dict; they are additive (D3).
                cell_spans = cell.get("spans", []) or []
                cell_bounding_regions = cell.get("boundingRegions", []) or []
                cell_page_number: Optional[int] = None
                cell_bounding_box: Optional[List[float]] = None
                if cell_bounding_regions:
                    # Most cells are single-page; use the first
                    # region's page + polygon. A cell spanning
                    # multiple pages would need an extended shape;
                    # TL-9.1 (Click-into-evidence) owns that view.
                    first_region = cell_bounding_regions[0]
                    cell_page_number = first_region.get("pageNumber")
                    cell_bounding_box = first_region.get("polygon")
                cell_ocr_confidence = derive_cell_confidence(
                    cell_spans, pages_words,
                )

                cell_info = {
                    "content": cell_content,
                    "row": row_idx,
                    "col": col_idx,
                    "row_span": row_span,
                    "col_span": col_span,
                    "kind": kind,
                    "spans": cell_spans,
                    "page_number": cell_page_number,
                    "bounding_box": cell_bounding_box,
                    "ocr_confidence": cell_ocr_confidence,
                }
                cells_list.append(cell_info)

                if 0 <= row_idx < row_count and 0 <= col_idx < col_count:
                    grid[row_idx][col_idx] = {
                        "content": cell_content,
                        "row_span": row_span,
                        "col_span": col_span,
                    }
                    for r in range(row_idx, min(row_idx + row_span, row_count)):
                        for c in range(col_idx, min(col_idx + col_span, col_count)):
                            if r != row_idx or c != col_idx:
                                grid[r][c] = {
                                    "content": (
                                        f"^{cell_content[:20]}..."
                                        if len(cell_content) > 20
                                        else f"^{cell_content}"
                                    ),
                                    "row_span": 0,
                                    "col_span": 0,
                                    "merged_from": [row_idx, col_idx],
                                }

            bounding_regions = table.get("boundingRegions", [])
            page_numbers = list(
                set(br.get("pageNumber", 1) for br in bounding_regions)
            )

            header_cells = [c for c in cells_data if c.get("kind") == "columnHeader"]
            if header_cells:
                header_row_indices = set(
                    hc.get("rowIndex", 0) for hc in header_cells
                )
                sample = [hc.get("content", "")[:30] for hc in header_cells[:5]]
                logger.info(
                    f"[{filename}] Table {table_idx}: Azure marked "
                    f"{len(header_cells)} columnHeader cells in rows "
                    f"{header_row_indices} (sample: {sample}) — ignored, "
                    f"using fallback header detection"
                )

            simple_rows: List[List[str]] = []
            for row in grid:
                simple_row = [
                    cell["content"]
                    if cell["content"] and not cell["content"].startswith("^")
                    else ""
                    for cell in row
                ]
                simple_rows.append(simple_row)

            structured_tables.append({
                "table_id": table_idx,
                "row_count": row_count,
                "column_count": col_count,
                "page_numbers": sorted(page_numbers),
                "rows": simple_rows,
                "cells": cells_list,
                "has_merged_cells": any(
                    c.get("row_span", 1) > 1 or c.get("col_span", 1) > 1
                    for c in cells_list
                ),
            })

        logger.info(f"[{filename}] Parsed {len(structured_tables)} structured tables")
        return structured_tables

    except Exception as e:
        logger.error(f"[{filename}] Error parsing tables: {e}")
        return []
