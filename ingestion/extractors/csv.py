"""
CSV Extractor
=============
Reads semicolon- or comma-delimited CSV/TSV schedule files.
Handles BOM, encoding detection (utf-8-sig, latin-1), and multiple delimiters.
Self-registers to ExtractorRegistry on import.
"""
import csv
import io
import logging
from pathlib import Path
from typing import Dict, Any, List

from ingestion.extractors.base import BaseExtractor
from ingestion.extractors.registry import ExtractorRegistry

logger = logging.getLogger(__name__)

_CANDIDATE_DELIMITERS = [";", ",", "\t", "|"]


def _decode_bytes(file_bytes: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("latin-1", errors="replace")


def _detect_delimiter(sample: str) -> str:
    counts = {d: sample.count(d) for d in _CANDIDATE_DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _read_csv_text(text: str) -> tuple[List[str], List[List[str]]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        reader = csv.reader(io.StringIO(text), dialect)
    except csv.Error:
        delimiter = _detect_delimiter(sample)
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)

    rows = list(reader)
    if not rows:
        return [], []

    headers = [h.strip() for h in rows[0]]
    data_rows = [[c.strip() for c in row] for row in rows[1:] if any(c.strip() for c in row)]
    return headers, data_rows


class CSVExtractor(BaseExtractor):
    def extract(self, file_path: Path) -> Dict[str, Any]:
        raw_bytes = file_path.read_bytes()
        return self.extract_from_bytes(raw_bytes, file_path.name)

    def extract_from_bytes(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        text = _decode_bytes(file_bytes)
        headers, data_rows = _read_csv_text(text)

        logger.info(f"[{filename}] CSV extracted: {len(headers)} columns, {len(data_rows)} data rows")

        return {
            "source_system": self.source_system(),
            "headers": headers,
            "rows": data_rows,
            "file_name": filename,
            "raw_text": text,
        }

    def source_system(self) -> str:
        return "CSV"


_csv_extractor_instance = CSVExtractor()
ExtractorRegistry.register("CSV", _csv_extractor_instance)
