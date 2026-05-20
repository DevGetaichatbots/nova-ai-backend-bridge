"""
PDF Extractor
=============
Wraps Azure Document Intelligence OCR to extract table rows from PDFs.
Re-implements OCR call independently from src/ — same Azure credentials,
same table parsing logic, but no import from src/.
Self-registers to ExtractorRegistry on import.
"""
import csv
import io
import logging
import os
import re
import time
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

from ingestion.extractors.base import BaseExtractor
from ingestion.extractors.registry import ExtractorRegistry

logger = logging.getLogger(__name__)

_API_VERSION = "2024-11-30"

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
    if not rows:
        return [], []

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
        return header_row, data_rows

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
    return fallback, data_rows


def _submit_pdf(pdf_bytes: bytes, filename: str, endpoint: str, key: str) -> Optional[str]:
    url = (
        f"{endpoint.rstrip('/')}/documentintelligence/documentModels/"
        f"prebuilt-layout:analyze?api-version={_API_VERSION}"
        f"&outputContentFormat=markdown"
    )
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/pdf"}
    try:
        response = requests.post(url, headers=headers, data=pdf_bytes, timeout=60)
        response.raise_for_status()
        return response.headers.get("Operation-Location")
    except requests.exceptions.RequestException as e:
        logger.error(f"[{filename}] Submit failed: {e}")
        return None


def _poll_results(operation_url: str, filename: str, key: str, timeout: int = 180) -> Optional[Dict]:
    headers = {"Ocp-Apim-Subscription-Key": key}
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            logger.error(f"[{filename}] OCR polling timeout after {timeout}s")
            return None
        interval = 1 if elapsed < 30 else 2
        try:
            resp = requests.get(operation_url, headers=headers, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            status = result.get("status", "unknown")
            if status == "succeeded":
                return result
            elif status == "failed":
                logger.error(f"[{filename}] OCR failed: {result.get('error', {})}")
                return None
            time.sleep(interval)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{filename}] Polling error: {e}")
            time.sleep(interval)


def _parse_ocr_tables(result: Dict, filename: str) -> List[Dict]:
    tables = result.get("analyzeResult", {}).get("tables", [])
    structured = []
    for ti, table in enumerate(tables):
        row_count = table.get("rowCount", 0)
        col_count = table.get("columnCount", 0)
        cells_data = table.get("cells", [])

        grid = [["" for _ in range(col_count)] for _ in range(row_count)]
        for cell in cells_data:
            ri = cell.get("rowIndex", 0)
            ci = cell.get("columnIndex", 0)
            content = cell.get("content", "")
            rs = cell.get("rowSpan", 1)
            cs = cell.get("columnSpan", 1)
            if 0 <= ri < row_count and 0 <= ci < col_count:
                grid[ri][ci] = content
                for r in range(ri, min(ri + rs, row_count)):
                    for c in range(ci, min(ci + cs, col_count)):
                        if r != ri or c != ci:
                            grid[r][c] = ""

        simple_rows = [[cell for cell in row] for row in grid]
        structured.append({
            "table_id": ti,
            "row_count": row_count,
            "column_count": col_count,
            "rows": simple_rows,
        })
    return structured


def _tables_to_headers_and_rows(tables: List[Dict], filename: str):
    # ------------------------------------------------------------------
    # Phase 1: parse every table independently, score each by how many
    # recognised schedule columns it contains.  The table with the highest
    # score becomes the canonical header schema.  Using the FIRST table as
    # the canonical template fails when the PDF opens with a small summary
    # or legend table (e.g. 2-col ["Id","Opgavetilstand"]) that then blocks
    # every subsequent wider table.
    # ------------------------------------------------------------------
    parsed: List[dict] = []  # {score, sched_headers, sched_data}

    for table in tables:
        col_count = table.get("column_count", 0)
        rows = table.get("rows", [])
        if not rows:
            continue

        header_row, data_rows = _detect_header_row(rows, col_count)
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
        })

    if not parsed:
        return [], []

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
    canon_low = [h.lower().strip() for h in canonical_headers]

    for entry in parsed:
        sched_headers = entry["sched_headers"]
        sched_data = entry["sched_data"]
        table_low = [h.lower().strip() for h in sched_headers]

        col_map: dict = {}
        for ci, ch in enumerate(canon_low):
            for fi, fh in enumerate(table_low):
                if fh == ch:
                    col_map[ci] = fi
                    break

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

        contributed = 0
        for row in mapped_rows:
            cleaned = [str(v).strip() for v in row]
            if any(cleaned):
                while len(cleaned) < len(canonical_headers):
                    cleaned.append("")
                all_data_rows.append(cleaned[:len(canonical_headers)])
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
    return canonical_headers, all_data_rows


class PDFExtractor(BaseExtractor):
    def __init__(self):
        self._endpoint = os.environ.get("AZURE_DOC_INTELLIGENCE_ENDPOINT", "").rstrip("/")
        self._key = os.environ.get("AZURE_DOC_INTELLIGENCE_KEY", "")

    def extract(self, file_path: Path) -> Dict[str, Any]:
        return self.extract_from_bytes(file_path.read_bytes(), file_path.name)

    def extract_from_bytes(self, pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
        if not self._endpoint or not self._key:
            raise ValueError(
                "Azure Document Intelligence credentials not configured. "
                "Set AZURE_DOC_INTELLIGENCE_ENDPOINT and AZURE_DOC_INTELLIGENCE_KEY."
            )
        if pdf_bytes[:4] != b"%PDF":
            raise ValueError(f"[{filename}] Invalid PDF — missing %PDF header")

        logger.info(f"[{filename}] Submitting PDF to Azure OCR ({len(pdf_bytes)} bytes)...")
        op_url = _submit_pdf(pdf_bytes, filename, self._endpoint, self._key)
        if not op_url:
            raise ValueError(f"[{filename}] Failed to submit PDF to Azure Document Intelligence")

        result = _poll_results(op_url, filename, self._key)
        if not result:
            raise ValueError(f"[{filename}] Azure OCR timed out or failed")

        raw_markdown = result.get("analyzeResult", {}).get("content", "")
        tables = _parse_ocr_tables(result, filename)
        headers, rows = _tables_to_headers_and_rows(tables, filename)

        logger.info(
            f"[{filename}] OCR complete: {len(tables)} tables, "
            f"{len(headers)} cols, {len(rows)} data rows"
        )

        return {
            "source_system": self.source_system(),
            "headers": headers,
            "rows": rows,
            "file_name": filename,
            "raw_text": raw_markdown,
        }

    def source_system(self) -> str:
        return "PDF"


_pdf_extractor_instance = PDFExtractor()
ExtractorRegistry.register("PDF", _pdf_extractor_instance)
