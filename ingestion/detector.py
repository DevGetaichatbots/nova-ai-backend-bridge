"""
Format Detector
===============
Identifies file type and source system from MIME type (python-magic) and binary header.
Uses python-magic when libmagic is available; falls back to pure binary header inspection
when the native library is not installed (e.g. Replit / NixOS without libmagic).
Supports: PDF, CSV, XLSX (Excel Open XML), MPP (Microsoft Project binary),
          MSPDI (Microsoft Project XML export).
Legacy binary .xls (Excel 97-2003 / OLE2) is detected but routed to XLS_LEGACY
so the pipeline can surface a clear, actionable error.
.mpp files also use OLE2 magic bytes — disambiguated from .xls via file extension.
MSPDI detection requires BOTH a .xml extension AND the MS Project namespace in the
first 2 KB — generic XML files are rejected as UNKNOWN.
"""
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF"
_XER_MARKERS = (b"ERPROJ", b"SYSASCT")
_MSPDI_NS = b"schemas.microsoft.com/project"   # content sniff for MS Project XML
_XLSX_MAGIC = b"PK\x03\x04"          # ZIP/OOXML — .xlsx
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"     # OLE2 compound document — legacy .xls / .mpp

try:
    import magic as _magic_lib
    _MAGIC_AVAILABLE = True
    logger.debug("python-magic/libmagic available — using MIME-type detection")
except (ImportError, Exception):
    _MAGIC_AVAILABLE = False
    logger.debug("libmagic not available — using binary header heuristics fallback")


def _mime_from_magic(file_path: Path) -> str:
    """Try MIME detection via python-magic; return '' on failure."""
    if not _MAGIC_AVAILABLE:
        return ""
    try:
        return _magic_lib.from_file(str(file_path), mime=True) or ""
    except Exception:
        return ""


def _mime_from_bytes_magic(data: bytes) -> str:
    """Try MIME detection from bytes via python-magic; return '' on failure."""
    if not _MAGIC_AVAILABLE:
        return ""
    try:
        return _magic_lib.from_buffer(data, mime=True) or ""
    except Exception:
        return ""


def _source_from_mime(mime: str, ext: str) -> str | None:
    """Map MIME type to SOURCE_SYSTEM string, or None if unknown."""
    if mime == "application/pdf":
        return "PDF"
    if mime in ("text/csv", "text/plain") and ext in (".csv", ".tsv"):
        return "CSV"
    # .mpp uses the same OLE2/MIME as .xls — disambiguate by extension first
    if ext == ".mpp":
        return "MPP"
    # xlsx / Office Open XML — openpyxl can handle this
    if mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return "EXCEL"
    if mime in ("application/vnd.ms-excel",) or (
        "excel" in mime and "openxmlformats" not in mime
    ):
        # Legacy binary .xls — openpyxl cannot open it
        return "XLS_LEGACY"
    if "spreadsheet" in mime:
        # Generic spreadsheet MIME (e.g. ODS) — try EXCEL and let extractor fail gracefully
        return "EXCEL"
    # text/xml with .xml extension: must also sniff the namespace to distinguish
    # MS Project XML from any other XML file — return None and let _detect_by_header
    # perform the namespace content check.
    return None


def _detect_by_header(header: bytes, ext: str) -> tuple[str, str]:
    """
    Pure binary-header + extension detection (libmagic fallback).
    `header` should be the first 2 KB of the file for MSPDI namespace sniffing.
    SOURCE_SYSTEM values: PDF | CSV | PRIMAVERA_XER | MSPDI | EXCEL | XLS_LEGACY | MPP | UNKNOWN
    """
    if header[:4] == _PDF_MAGIC:
        return ("application/pdf", "PDF")
    if any(m in header for m in _XER_MARKERS) or ext == ".xer":
        return ("text/plain", "PRIMAVERA_XER")
    # .mpp must be checked before .xls — both use OLE2 magic bytes
    if ext == ".mpp" and header[:4] == _XLS_MAGIC:
        return ("application/vnd.ms-project", "MPP")
    # .mpp files created with newer Project versions may use ZIP container
    if ext == ".mpp" and header[:4] == _XLSX_MAGIC:
        return ("application/vnd.ms-project", "MPP")
    # Unrecognised binary with .mpp extension — still route to MPP extractor
    if ext == ".mpp":
        return ("application/vnd.ms-project", "MPP")
    if header[:4] == _XLSX_MAGIC and ext in (".xlsx", ".xls"):
        return (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "EXCEL",
        )
    if header[:4] == _XLS_MAGIC or (ext == ".xls" and header[:4] != _XLSX_MAGIC):
        return ("application/vnd.ms-excel", "XLS_LEGACY")
    # MSPDI: .xml + MS Project namespace in first 2 KB — must check content,
    # not just extension, to avoid routing generic XML files to the MSPDI extractor.
    if ext == ".xml" and _MSPDI_NS in header:
        return ("text/xml", "MSPDI")
    if ext in (".csv", ".tsv"):
        return ("text/csv", "CSV")
    try:
        header.decode("utf-8")
        if b";" in header or b"," in header:
            return ("text/csv", "CSV")
    except UnicodeDecodeError:
        pass
    return ("application/octet-stream", "UNKNOWN")


class FormatDetector:
    def detect(self, file_path: Path) -> tuple[str, str]:
        """
        Returns (MIME_TYPE, SOURCE_SYSTEM_IDENTIFIER).
        Tries python-magic first; falls back to byte-header inspection.
        SOURCE_SYSTEM values: PDF | CSV | PRIMAVERA_XER | MSPDI | EXCEL | XLS_LEGACY | MPP | UNKNOWN
        """
        ext = file_path.suffix.lower()
        mime = _mime_from_magic(file_path)
        if mime:
            source = _source_from_mime(mime, ext)
            if source:
                logger.debug(f"[{file_path.name}] magic: {mime} → {source}")
                return (mime, source)

        try:
            with open(file_path, "rb") as f:
                header = f.read(2048)
        except OSError as e:
            logger.error(f"Cannot read file header: {e}")
            return ("application/octet-stream", "UNKNOWN")

        result = _detect_by_header(header, ext)
        logger.debug(f"[{file_path.name}] header heuristic → {result}")
        return result

    def detect_from_bytes(self, file_bytes: bytes, filename: str) -> tuple[str, str]:
        """Detect format from raw bytes and filename without writing to disk."""
        ext = Path(filename).suffix.lower()
        header = file_bytes[:2048]

        mime = _mime_from_bytes_magic(header)
        if mime:
            source = _source_from_mime(mime, ext)
            if source:
                logger.debug(f"[{filename}] magic: {mime} → {source}")
                return (mime, source)

        result = _detect_by_header(header, ext)
        logger.debug(f"[{filename}] header heuristic → {result}")
        return result


detector = FormatDetector()
