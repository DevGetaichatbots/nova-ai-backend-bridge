"""
PDF Extractor
=============
Wraps Azure Document Intelligence OCR to extract table rows from PDFs.

The Azure HTTP layer (submit / poll / parse) lives in `ocr_client`
since TL-1.3; this module keeps the schedule-aware post-processing
that is specific to the NUSF pipeline — header detection, table
merging, and the embedded-text-layer fallback for very large digital
PDFs where Azure returns headers but no data rows.

Self-registers to ExtractorRegistry on import.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ingestion.extractors.base import BaseExtractor
from ingestion.extractors.registry import ExtractorRegistry
from ocr_client import (
    parse_tables,
    poll_results,
    submit_pdf,
)


logger = logging.getLogger(__name__)


KNOWN_SCHEDULE_HEADERS = {
    "id", "entydigt id", "etage", "omr.", "ansvarlig", "opgavenavn",
    "opgavetilstand", "varighed", "startdato", "slutdato",
    "% arbejde færdigt", "% færdigt", "foregående opgaver",
    "efterfølgende opgaver", "bemærkn.", "bemærkn",
    "task name", "duration", "start", "finish", "start date",
    "end date", "% complete", "predecessors", "successors",
    "responsible", "area", "tbs", "navn", "aktivitetstype",
    "fremdrift", "lokation", "name", "planned_start_date",
    "planned_end_date", "actual_completion_pct",
}

GANTT_NOISE_RE = re.compile(
    r"^(kvt\d|kvt \d|\d{4}\s*kvt|uge\s*\d|jan|feb|mar|apr|maj|jun|"
    r"jul|aug|sep|okt|nov|dec|q[1-4]|col\d+|\d{4}\s+\d{4}"
    r"|\d{4}$)",          # bare 4-digit year (e.g. "2026", "2027") is Gantt
    re.IGNORECASE,
)

MS_PROJECT_FALLBACK = {
    9: ["Id", "Opgavetilstand", "Opgavenavn", "Varighed", "Startdato",
        "Slutdato", "% arbejde færdigt", "Foregående opgaver", "Efterfølgende opgaver"],
}


def _header_score(row_vals: List) -> int:
    cleaned = [str(v).strip().lower() for v in row_vals if str(v).strip()]
    return sum(
        1 for v in cleaned
        if v in KNOWN_SCHEDULE_HEADERS or any(kh in v for kh in KNOWN_SCHEDULE_HEADERS)
    )


def _is_schedule_col(header: str) -> bool:
    h = header.strip().lower()
    if not h:
        return False
    if h in KNOWN_SCHEDULE_HEADERS:
        return True
    if GANTT_NOISE_RE.match(h):
        return False
    if h.startswith("col") and h[3:].isdigit():
        return False
    return True


def _detect_header_row(rows: List[List[str]], col_count: int):
    """Locate the header row in a parsed table.

    Returns `(header_row, data_rows, header_row_idx)`:
    - `header_row`: the chosen header (real row or MS Project fallback).
    - `data_rows`: every row that is *not* the header, in original order.
    - `header_row_idx`: the original index of the chosen header row in
      `rows` (`-1` if no header was detected — the fallback path).

    TL-1.4: the third tuple element is the join key that maps a
    `data_rows` element back to its original row index in the source
    table, which is what makes cell-to-row threading work during the
    merge in `_tables_to_headers_and_rows`. `best_idx == 0` means
    the header was at the top (the simple case); `best_idx > 0` is
    the "table opens with a legend or summary table" case the
    comment below describes.
    """
    if not rows:
        return [], [], -1

    best_score = _header_score(rows[0])
    best_idx = 0
    for i in range(1, min(5, len(rows))):
        s = _header_score(rows[i])
        if s > best_score:
            best_score = s
            best_idx = i

    if best_score >= 3:
        header_row = rows[best_idx]
        data_rows = [r for i, r in enumerate(rows) if i != best_idx and (i != 0 or best_idx == 0)]
        if best_idx > 0:
            data_rows = [r for i, r in enumerate(rows) if i != best_idx and i != 0]
        return header_row, data_rows, best_idx

    fallback = MS_PROJECT_FALLBACK.get(col_count)
    if not fallback:
        closest = min(MS_PROJECT_FALLBACK.keys(), key=lambda k: abs(k - col_count))
        fb = MS_PROJECT_FALLBACK[closest]
        fallback = fb + [f"Col{i+1}" for i in range(closest, col_count)] if col_count > closest else fb[:col_count]

    skip_rows = set()
    for ri in range(min(5, len(rows))):
        row_vals = [str(v).strip().lower() for v in rows[ri] if str(v).strip()]
        if row_vals and not any(v.isdigit() for v in row_vals):
            skip_rows.add(ri)
    data_rows = [r for i, r in enumerate(rows) if i not in skip_rows]
    # No header was detected — `header_row_idx = -1` signals "no
    # original header row to skip" to the cell-threading code in
    # `_tables_to_headers_and_rows`. Every row in `data_rows` is
    # treated as a data row.
    return fallback, data_rows, -1


def _build_unified_ocr_cell(
    ocr_cell: Dict,
    *,
    col_name: str,
    row_idx: int,
    source_document: str,
) -> Dict:
    """Transform an OCR cell dict (from `ocr_client.parse_tables`) into
    the unified provenance-bearing shape that flows through
    `_tables_to_headers_and_rows` → `normalize()` → `Provenance`.

    The output shape mirrors `_make_textlayer_cell` (TL-1.3), so the
    normalization engine can look up cells from either OCR or
    text-layer paths with the same logic. The TL-1.2 evidence fields
    (`ocr_confidence`, `page_number`, `bounding_box`, `spans`) pass
    through verbatim — including the load-bearing `None` sentinels
    (ADR-010) — so `Provenance.ocr_confidence=None` for unresolvable
    cells survives into the activity model without coercion.
    """
    return {
        "content": ocr_cell.get("content", ""),
        "ocr_confidence": ocr_cell.get("ocr_confidence"),
        "page_number": ocr_cell.get("page_number"),
        "bounding_box": ocr_cell.get("bounding_box"),
        "spans": ocr_cell.get("spans"),
        "extraction_method": "ocr_table",
        "source_field": col_name,
        "source_row": row_idx,
        "source_document": source_document,
    }


def _tables_to_headers_and_rows(tables: List[Dict], filename: str):
    """Merge every parsed table into a single `(headers, rows, cells)`
    triple under a canonical schema.

    Returns:
    - `canonical_headers`: list of column names in the merged schema.
    - `all_data_rows`: list of rows, each a list of strings, in canonical
      column order.
    - `all_cells`: parallel 2D list — `all_cells[i][j]` is the provenance-
      bearing cell dict for the value at row `i`, canonical column `j`,
      or `None` if that cell was empty / could not be mapped.

    TL-1.4: `all_cells` is the join surface between extraction and
    normalization. Each cell dict carries the TL-1.2 evidence fields
    (`ocr_confidence`, `page_number`, `bounding_box`) plus the
    `source_field` (canonical column name) and `source_row` (output
    row index) so `Provenance` construction in `engine.py` can attach
    the evidence to the right `Activity` field without re-scanning.
    """
    # ------------------------------------------------------------------
    # Phase 1: parse every table independently, score each by how many
    # recognised schedule columns it contains.  The table with the highest
    # score becomes the canonical header schema.  Using the FIRST table as
    # the canonical template fails when the PDF opens with a small summary
    # or legend table (e.g. 2-col ["Id","Opgavetilstand"]) that then blocks
    # every subsequent wider table.
    # ------------------------------------------------------------------
    parsed: List[dict] = []  # {score, sched_headers, sched_data, header_row_idx, cells_by_row}

    for table in tables:
        col_count = table.get("column_count", 0)
        rows = table.get("rows", [])
        if not rows:
            continue

        header_row, data_rows, header_row_idx = _detect_header_row(rows, col_count)
        header_clean = [str(h).strip() for h in header_row]

        sched_indices = [i for i, h in enumerate(header_clean) if _is_schedule_col(h)]
        if not sched_indices:
            sched_indices = list(range(len(header_clean)))

        sched_headers = [header_clean[i] for i in sched_indices]
        sched_data = [
            [row[i].strip() if i < len(row) else "" for i in sched_indices]
            for row in data_rows
        ]

        if not sched_data:
            continue

        # Build a lookup `original_row_idx → [cell, ...]` from the
        # input table's rich cells (TL-1.2 evidence included). Keys are
        # the row indices from `table["cells"][k]["row"]` — the same
        # row indices that `_detect_header_row` used to identify the
        # header. We keep every cell (including header cells) here so
        # the merge step can decide which to drop.
        cells_by_row: Dict[int, List[Dict]] = {}
        for cell in table.get("cells", []) or []:
            cells_by_row.setdefault(cell.get("row", 0), []).append(cell)

        score = _header_score(sched_headers)
        logger.info(
            f"[{filename}] Phase1 table: score={score}, "
            f"cols={len(sched_headers)}, rows={len(sched_data)}, "
            f"headers={sched_headers}"
        )
        parsed.append({
            "score": score,
            "col_count": len(sched_headers),
            "sched_headers": sched_headers,
            "sched_data": sched_data,
            "sched_indices": sched_indices,
            "header_row_idx": header_row_idx,
            "cells_by_row": cells_by_row,
        })

    if not parsed:
        return [], [], []

    # Pick canonical: highest recognised-header score first,
    # break ties by column count (wider table wins).
    parsed.sort(key=lambda t: (t["score"], t["col_count"]), reverse=True)
    canonical_headers = parsed[0]["sched_headers"]

    logger.info(
        f"[{filename}] Canonical table: score={parsed[0]['score']}, "
        f"cols={parsed[0]['col_count']}, headers={canonical_headers}"
    )

    # ------------------------------------------------------------------
    # Phase 2: merge all tables into the canonical schema.
    # ------------------------------------------------------------------
    all_data_rows: List[List[str]] = []
    all_cells: List[List[Optional[Dict]]] = []
    canon_low = [h.lower().strip() for h in canonical_headers]

    for entry in parsed:
        sched_headers = entry["sched_headers"]
        sched_data = entry["sched_data"]
        table_low = [h.lower().strip() for h in sched_headers]
        sched_indices = entry["sched_indices"]
        header_row_idx = entry["header_row_idx"]
        cells_by_row = entry["cells_by_row"]

        col_map: dict = {}
        for ci, ch in enumerate(canon_low):
            for fi, fh in enumerate(table_low):
                if fh == ch:
                    col_map[ci] = fi
                    break

        # Reverse map for cell lookup: input_col → canonical_col.
        # Built once per input table. O(cols); trivial.
        rev_col_map: Dict[int, int] = {fi: ci for ci, fi in col_map.items()}

        # Require at least 50% column overlap (relaxed from 60% to handle
        # multi-page tables that may omit repeated header columns).
        min_req = max(1, int(0.5 * len(canonical_headers)))
        if len(col_map) < min_req:
            logger.info(
                f"[{filename}] Skipping table with {len(sched_headers)} cols "
                f"(overlap {len(col_map)}/{len(canonical_headers)} < {min_req}): "
                f"{sched_headers}"
            )
            continue

        mapped_rows = [
            [row[col_map[ci]] if ci in col_map and col_map[ci] < len(row) else ""
             for ci in range(len(canonical_headers))]
            for row in sched_data
        ]

        # Build the parallel cell grid for this input table. We need
        # to map each `mapped_row[i]` (i-th row from this input
        # table's `sched_data`) back to the original row index in
        # `table["cells"]`. `_detect_header_row` produced `data_rows`
        # by filtering out the header row from the original `rows`;
        # the cell `row` indices are those original indices, so we
        # reconstruct them here.
        def _original_row_idx(input_row_idx: int) -> int:
            """Map a `data_rows` index (post header-filter) to the
            original `table["cells"][k]["row"]` index for this table.
            The mapping depends on where the header was found."""
            if header_row_idx < 0:
                # Fallback path: no header detected, every row is data.
                return input_row_idx
            if header_row_idx == 0:
                # Header at the top — data starts at original index 1.
                return input_row_idx + 1
            # Header at a non-zero index — data_rows[i] comes from the
            # original row that survived the filter. The filter keeps
            # rows 0..header_row_idx-1 and header_row_idx+1..end, so
            # data_rows[i] for i < header_row_idx is original row i+1
            # (skipping row 0), and data_rows[i] for i >= header_row_idx
            # is original row i+2 (skipping row 0 AND the header).
            if input_row_idx < header_row_idx:
                return input_row_idx + 1
            return input_row_idx + 2

        contributed = 0
        for input_row_idx, row in enumerate(mapped_rows):
            cleaned = [str(v).strip() for v in row]
            if any(cleaned):
                while len(cleaned) < len(canonical_headers):
                    cleaned.append("")
                output_row_idx = len(all_data_rows)
                all_data_rows.append(cleaned[:len(canonical_headers)])

                # TL-1.4: build the parallel cell row. Each cell
                # carries its TL-1.2 evidence (when present); empty
                # positions stay `None` so downstream can tell apart
                # "no cell at this position" from "cell with None
                # fields" (which is a meaningful signal — see
                # ADR-009 / ADR-010).
                cell_row: List[Optional[Dict]] = [None] * len(canonical_headers)
                original_row_idx = _original_row_idx(input_row_idx)
                for input_cell in cells_by_row.get(original_row_idx, []):
                    input_col = input_cell.get("col")
                    if input_col is None:
                        # Defensive: a malformed cell without a column
                        # index cannot be threaded to a canonical column.
                        # Skip silently — the corresponding output cell
                        # position stays `None` and downstream `normalize()`
                        # falls back to legacy Provenance for that field.
                        continue
                    canon_col = rev_col_map.get(input_col)
                    if canon_col is None:
                        # Cell at a column we didn't keep (filtered out
                        # by `_is_schedule_col`). Drop silently.
                        continue
                    cell_row[canon_col] = _build_unified_ocr_cell(
                        input_cell,
                        col_name=canonical_headers[canon_col],
                        row_idx=output_row_idx,
                        source_document=filename,
                    )
                all_cells.append(cell_row)

                contributed += 1

        logger.info(
            f"[{filename}] Merged table: {len(sched_headers)} cols, "
            f"{len(sched_data)} raw rows → {contributed} kept "
            f"(overlap {len(col_map)}/{len(canonical_headers)}): {sched_headers}"
        )

    logger.info(
        f"[{filename}] Table merge complete: {len(all_data_rows)} total rows "
        f"from canonical schema {canonical_headers}"
    )
    return canonical_headers, all_data_rows, all_cells


# ----------------------------------------------------------------------
# Embedded-text-layer fallback
# ----------------------------------------------------------------------
# Azure Document Intelligence fails on very large digital PDFs (e.g. A0
# MS-Project "Samlet tidsplan" exports): it detects the table grid but
# downsamples the page so hard the body text is unreadable, returning
# populated header cells and empty data cells → 0 usable rows. These PDFs
# carry a perfect embedded text layer, so when OCR yields nothing we read
# the text layer directly and rebuild the columns from word coordinates.
#
# TL-1.3: this fallback also returns rich cell dicts with provenance
# hints (`extraction_method="ocr_text_layer"`, `ocr_confidence=None`,
# `page_number` from pdfplumber). The cells carry enough information
# for downstream `Activity` construction (TL-1.4) to set the right
# `Provenance.extraction_method` and `Provenance.ocr_confidence=None`
# for these "unrated" values — see ADR-011.

_TEXTLAYER_HEADERS = [
    "Id", "Opgavenavn", "Varighed", "Startdato", "Slutdato",
    "% arbejde færdigt", "Foregående opgaver",
]
_TEXTLAYER_FIELD_KEYS = [
    "id", "name", "duration", "start_date", "finish_date",
    "percent_complete", "predecessors",
]
_DATE_TOKEN_RE = re.compile(r"\d{1,2}-\d{1,2}-\d{2,4}")
# Header labels that are reliably isolated in MS Project exports (Danish + English).
_ANCHOR_LABELS = {
    "id": ("id",),
    "duration": ("varighed", "duration"),
    "start": ("startdato", "start"),
    "finish": ("slutdato", "finish"),
    "pct": ("%",),
}
_GANTT_MONTHS = {
    "jan", "feb", "mar", "apr", "maj", "may", "jun",
    "jul", "aug", "sep", "okt", "oct", "nov", "dec",
}


def _cluster_word_rows(words: List[dict], y_tol: float = 3.0) -> List[List[dict]]:
    rows: List[List] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(w["top"] - rows[-1][0]) <= y_tol:
            rows[-1][1].append(w)
        else:
            rows.append([w["top"], [w]])
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in rows]


def _find_column_anchors(words: List[dict]):
    """Locate header-word x-positions and where the Gantt chart begins."""
    top_band = [w for w in words if w["top"] < 130]
    anchors: Dict[str, float] = {}
    for role, labels in _ANCHOR_LABELS.items():
        for w in top_band:
            if w["text"].strip().lower() in labels and role not in anchors:
                anchors[role] = w["x0"]
                break
    gantt_x = min(
        (w["x0"] for w in top_band if w["text"].strip().lower() in _GANTT_MONTHS),
        default=float("inf"),
    )
    return anchors, gantt_x


def _make_textlayer_cell(
    text: str,
    *,
    page_number: int,
    source_field: str,
    source_document: str,
) -> Dict[str, Any]:
    """Build a provenance-bearing cell dict for the text-layer fallback.

    `ocr_confidence` is `None` (no OCR — this is a precise text-layer
    read). `extraction_method` is `"ocr_text_layer"` so downstream
    `Provenance` construction (TL-1.4) can mark these as unrated.
    `bounding_box` and `spans` are `None`: pdfplumber gives per-word
    geometry but no concept of an Azure cell, and the text-layer
    fallback rebuilds cells from word coordinates rather than from
    a tabulated grid.
    """
    return {
        "content": text,
        "extraction_method": "ocr_text_layer",
        "ocr_confidence": None,
        "page_number": page_number,
        "bounding_box": None,
        "spans": None,
        "source_field": source_field,
        "raw_value": text,
        "normalized_value": text,
        "source_document": source_document,
        "is_ai_inferred": False,
        # Column-mapping confidence does not apply here either; the
        # header was identified by coordinate proximity to known
        # anchor labels, not by an Azure cell-mapping step.
        "confidence": None,
    }


def _extract_text_layer(pdf_bytes: bytes, filename: str):
    """
    Rebuild schedule rows from the PDF's embedded text layer by bucketing
    words into columns using coordinates derived from the header row.

    Returns `(headers, rows, cells)`:
    - `headers`: column header strings (existing API).
    - `rows`:    2D grid of cell-text strings (existing API, kept for
                 backwards compatibility with downstream consumers that
                 read `rows` directly).
    - `cells`:   2D grid of rich provenance-bearing cell dicts, one per
                 `rows[i][j]`. Each cell carries
                 `extraction_method="ocr_text_layer"`,
                 `ocr_confidence=None`, `page_number`, and other
                 TL-1.3 provenance fields so TL-1.4 can mark these as
                 unrated without further classification work.

    Returns `([], [], [])` if no recognizable schedule table is found —
    the caller then keeps the (empty) OCR result.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning(f"[{filename}] pdfplumber not installed — text-layer fallback unavailable")
        return [], [], []

    all_rows: List[List[str]] = []
    all_cell_rows: List[List[Dict[str, Any]]] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                words = page.extract_words()
                anchors, gantt_x = _find_column_anchors(words)
                if not {"id", "duration", "start", "finish"} <= anchors.keys():
                    continue  # header row not found on this page

                id_x = anchors["id"]
                dur_x = anchors["duration"]
                start_x = anchors["start"]
                finish_x = anchors["finish"]
                pct_x = anchors.get("pct", finish_x + 25)
                # Column x-ranges [lo, hi). Words are assigned by their CENTER
                # so sub-pixel boundary overlaps don't leak into a neighbour.
                # "left" spans Id + any secondary id/task-mode columns + name;
                # it's split apart per row below because the Id value's
                # indentation and the presence of an "Entydigt id" column vary
                # between exports.
                cols = [
                    ("left", id_x - 8, dur_x),
                    ("dur", dur_x, start_x),
                    ("start", start_x, finish_x),
                    ("finish", finish_x, pct_x),
                    ("pct", pct_x, pct_x + 26),
                    ("pred", pct_x + 26, gantt_x),
                ]

                for row_words in _cluster_word_rows(words):
                    if row_words and row_words[0]["top"] < 125:
                        continue  # header band
                    buckets: Dict[str, List[str]] = {k: [] for k, _, _ in cols}
                    for w in row_words:
                        cx = (w["x0"] + w["x1"]) / 2
                        for k, lo, hi in cols:
                            if lo <= cx < hi:
                                buckets[k].append(w["text"])
                                break

                    # First token is the MS Project Id; drop any following
                    # standalone integer ids (e.g. "Entydigt id"); rest = name.
                    left = buckets["left"]
                    if not left or not left[0].isdigit():
                        continue  # wrapped continuation line / non-task row
                    rid = left[0]
                    name_tokens = left[1:]
                    while name_tokens and name_tokens[0].isdigit():
                        name_tokens.pop(0)
                    name = " ".join(name_tokens).strip()
                    if not name:
                        continue

                    dur = " ".join(buckets["dur"]).strip()
                    dates = _DATE_TOKEN_RE.findall(" ".join(buckets["start"] + buckets["finish"]))
                    start = dates[0] if len(dates) >= 1 else ""
                    finish = dates[1] if len(dates) >= 2 else ""
                    pct = " ".join(buckets["pct"]).strip()
                    # Predecessors are numeric/`;`-separated; strip trailing
                    # resource labels (letters) that abut the column.
                    pred = re.sub(r"[A-Za-zÆØÅæøå();].*$", "", " ".join(buckets["pred"])).strip()

                    # Build the parallel rich-cell row. One cell per
                    # column in `_TEXTLAYER_HEADERS`, with the right
                    # `source_field` for downstream Provenance
                    # construction (TL-1.4).
                    row_texts = [rid, name, dur, start, finish, pct, pred]
                    cell_row = [
                        _make_textlayer_cell(
                            text,
                            page_number=page.page_number,
                            source_field=_TEXTLAYER_FIELD_KEYS[i],
                            source_document=filename,
                        )
                        for i, text in enumerate(row_texts)
                    ]
                    all_rows.append(row_texts)
                    all_cell_rows.append(cell_row)
    except Exception as e:
        logger.warning(f"[{filename}] Text-layer extraction failed: {e}")
        return [], [], []

    if not all_rows:
        return [], [], []

    logger.info(
        f"[{filename}] Text-layer fallback recovered {len(all_rows)} rows "
        f"from embedded text layer"
    )
    return list(_TEXTLAYER_HEADERS), all_rows, all_cell_rows


class PDFExtractor(BaseExtractor):
    def __init__(self):
        self._endpoint = os.environ.get("AZURE_DOC_INTELLIGENCE_ENDPOINT", "").rstrip("/")
        self._key = os.environ.get("AZURE_DOC_INTELLIGENCE_KEY", "")

    def extract(self, file_path: Path) -> Dict[str, Any]:
        return self.extract_from_bytes(file_path.read_bytes(), file_path.name)

    def extract_text_layer(self, pdf_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
        """
        Rebuild the schedule from the PDF's embedded text layer, bypassing OCR.
        Returns an extraction dict (same shape as extract_from_bytes) or None if
        no recognizable schedule table is found. Used by the pipeline as a
        retry when OCR-based normalization yields no activities.
        """
        headers, rows, cells = _extract_text_layer(pdf_bytes, filename)
        if not rows:
            return None
        return {
            "source_system": self.source_system(),
            "headers": headers,
            "rows": rows,
            "cells": cells,
            "file_name": filename,
            "raw_text": "",
        }

    def extract_from_bytes(self, pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
        if not self._endpoint or not self._key:
            raise ValueError(
                "Azure Document Intelligence credentials not configured. "
                "Set AZURE_DOC_INTELLIGENCE_ENDPOINT and AZURE_DOC_INTELLIGENCE_KEY."
            )
        if pdf_bytes[:4] != b"%PDF":
            raise ValueError(f"[{filename}] Invalid PDF — missing %PDF header")

        logger.info(f"[{filename}] Submitting PDF to Azure OCR ({len(pdf_bytes)} bytes)...")
        op_url = submit_pdf(pdf_bytes, filename, self._endpoint, self._key)
        if not op_url:
            raise ValueError(f"[{filename}] Failed to submit PDF to Azure Document Intelligence")

        result = poll_results(op_url, filename, self._key)
        if not result:
            raise ValueError(f"[{filename}] Azure OCR timed out or failed")

        raw_markdown = result.get("analyzeResult", {}).get("content", "")
        tables = parse_tables(result, filename)
        headers, rows, ocr_cells = _tables_to_headers_and_rows(tables, filename)

        logger.info(
            f"[{filename}] OCR complete: {len(tables)} tables, "
            f"{len(headers)} cols, {len(rows)} data rows, "
            f"{sum(1 for r in (ocr_cells or []) for c in r if c is not None)} cells"
        )

        # OCR-first, text-layer fallback: Azure fails on very large digital
        # PDFs (e.g. A0 landscape), returning headers but no data rows at all.
        # When OCR extracts literally nothing, rebuild from the embedded text
        # layer. (The garbled-OCR case — rows present but unparseable — is
        # handled downstream in the pipeline on a 0-activities result.)
        # TL-1.4: cells threaded through to the normalization engine for
        # Provenance construction. OCR path (`ocr_cells`) has
        # `Optional[Dict]` per cell position (empty positions are
        # `None`); text-layer path (`tl_cells` below) has `Dict` per
        # cell position (every position populated). Python's type
        # system treats these as incompatible lists, so the variable
        # is un-annotated here and the runtime contract is documented
        # at the `_extract_text_layer` and `_tables_to_headers_and_rows`
        # return shapes.
        cells = ocr_cells
        if not rows:
            logger.warning(
                f"[{filename}] OCR produced 0 data rows — trying embedded text-layer fallback"
            )
            tl_headers, tl_rows, tl_cells = _extract_text_layer(pdf_bytes, filename)
            if tl_rows:
                headers, rows = tl_headers, tl_rows
                cells = tl_cells
                logger.info(
                    f"[{filename}] Using text-layer result: {len(headers)} cols, "
                    f"{len(rows)} rows"
                )

        return {
            "source_system": self.source_system(),
            "headers": headers,
            "rows": rows,
            "cells": cells,
            "file_name": filename,
            "raw_text": raw_markdown,
        }

    def source_system(self) -> str:
        return "PDF"


_pdf_extractor_instance = PDFExtractor()
ExtractorRegistry.register("PDF", _pdf_extractor_instance)
