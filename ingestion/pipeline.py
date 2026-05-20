"""
Ingestion Pipeline Orchestrator
================================
Single entry point: IngestionPipeline.run_from_bytes(file_bytes, filename)

Chains:
  Detect → Extract → Recognize → (AI fallback if needed) → Normalize → Validate
  → returns (NormalizedSchedule, compact_csv_chunks)

The compact_csv_chunks list is identical in format to the output of
src/pdf_processor.rows_to_compact_csv_chunks() because the bridge operates
on the original extracted headers and rows, applying the same filtering logic.
Downstream vector store and LLM agents are unchanged.
"""
from __future__ import annotations
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ingestion.detector import FormatDetector
from ingestion.extractors.registry import ExtractorRegistry
from ingestion.models.nusf import NormalizedSchedule
from ingestion.normalization.engine import NormalizationEngine
from ingestion.recognition.ai_fallback import AIFallbackRecognizer
from ingestion.recognition.heuristics import HeuristicRecognizer, RecognitionResult
from ingestion.validation.engine import ValidationEngine

import ingestion.extractors.csv as _  # noqa: F401 — triggers self-registration
import ingestion.extractors.excel as _  # noqa: F401 — triggers self-registration
import ingestion.extractors.pdf as _  # noqa: F401 — triggers self-registration
import ingestion.extractors.mpp as _  # noqa: F401 — triggers self-registration
import ingestion.extractors.mspdi as _  # noqa: F401 — triggers self-registration

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when the pipeline cannot proceed (unsupported format, validation ERROR, etc.)."""
    def __init__(self, message: str, issues: list = None):
        super().__init__(message)
        self.issues = issues or []


class IngestionPipeline:
    """
    Universal schedule ingestion pipeline.

    Usage:
        pipeline = IngestionPipeline()
        schedule, chunks = pipeline.run_from_bytes(file_bytes, "schedule.pdf")
    """

    def __init__(self):
        self._detector = FormatDetector()
        self._heuristics = HeuristicRecognizer()
        self._ai_fallback = AIFallbackRecognizer()
        self._normalizer = NormalizationEngine()
        self._validator = ValidationEngine()

    def run(
        self,
        file_path: Path,
        filename: str = None,
    ) -> Tuple[NormalizedSchedule, List[Dict[str, Any]]]:
        """
        Full pipeline run from a file path on disk.
        filename defaults to file_path.name if not provided.
        """
        file_path = Path(file_path)
        if filename is None:
            filename = file_path.name
        return self.run_from_bytes(file_path.read_bytes(), filename)

    def run_from_bytes(
        self,
        file_bytes: bytes,
        filename: str,
    ) -> Tuple[NormalizedSchedule, List[Dict[str, Any]]]:
        """
        Full pipeline run from raw bytes.

        Returns:
            (NormalizedSchedule, compact_csv_chunks)

        Raises:
            PipelineError: on unsupported format, validation errors, or extraction failure.
        """
        logger.info(f"[{filename}] Pipeline start — {len(file_bytes)} bytes")

        mime_type, source_system = self._detector.detect_from_bytes(file_bytes, filename)
        logger.info(f"[{filename}] Detected: source_system={source_system}, mime={mime_type}")

        if source_system == "XLS_LEGACY":
            raise PipelineError(
                f"'{filename}' appears to be a legacy Excel 97-2003 (.xls) file, "
                f"which is not supported. Please save the file as .xlsx (Excel Workbook) "
                f"and upload again."
            )

        if source_system == "UNKNOWN":
            raise PipelineError(
                f"Unsupported file format for '{filename}'. "
                f"Supported formats: PDF, CSV, XLSX (Excel), MPP (Microsoft Project binary), "
                f"XML (Microsoft Project XML export)."
            )

        if source_system not in ExtractorRegistry.available():
            raise PipelineError(
                f"No extractor registered for source system '{source_system}'. "
                f"Available: {ExtractorRegistry.available()}"
            )

        extractor = ExtractorRegistry.get(source_system)

        try:
            if hasattr(extractor, "extract_from_bytes"):
                extracted = extractor.extract_from_bytes(file_bytes, filename)
            else:
                with tempfile.NamedTemporaryFile(
                    suffix=Path(filename).suffix, delete=False
                ) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = Path(tmp.name)
                extracted = extractor.extract(tmp_path)
                tmp_path.unlink(missing_ok=True)
        except Exception as e:
            raise PipelineError(f"Extraction failed for '{filename}': {e}") from e

        headers = extracted.get("headers", [])
        rows = extracted.get("rows", [])

        logger.info(
            f"[{filename}] Extracted {len(rows)} rows, "
            f"{len(headers)} headers: {headers}"
        )

        if not headers:
            raise PipelineError(
                f"No column headers could be extracted from '{filename}'. "
                f"The file may be empty or in an unrecognized layout."
            )

        recognition = self._heuristics.recognize(headers)
        logger.info(f"[{filename}] Heuristic recognition: {recognition}")

        if recognition.ai_needed:
            logger.info(
                f"[{filename}] Critical fields missing — invoking AI fallback recognizer. "
                f"Headers sent: {headers}"
            )
            ai_map = self._ai_fallback.recognize(headers)
            logger.info(f"[{filename}] AI fallback returned: {ai_map}")
            if ai_map:
                merged_map = dict(recognition.column_map)
                for role, col in ai_map.items():
                    if role not in merged_map:
                        merged_map[role] = col
                recognition = RecognitionResult(
                    column_map=merged_map,
                    match_key=recognition.match_key,
                    format_label=recognition.format_label,
                    ai_needed=True,
                    confidence=max(recognition.confidence, 0.5),
                )
                logger.info(
                    f"[{filename}] After AI fallback — column_map: {recognition.column_map}"
                )

        # Always produce compact CSV chunks from raw OCR/CSV rows — this mirrors
        # the existing src/pdf_processor behaviour and keeps LLM agents working
        # even when structured normalization cannot fully parse the headers.
        chunks = self._normalizer.to_compact_csv_chunks(headers, rows, filename)

        schedule = self._normalizer.normalize(
            extracted=extracted,
            recognition=recognition,
            source_system=source_system,
            filename=filename,
        )

        if not schedule.activities:
            if not chunks:
                raise PipelineError(
                    f"No data could be extracted from '{filename}'. "
                    f"Raw headers from OCR: {headers}. "
                    f"Data rows extracted: {len(rows)}. "
                    f"Columns recognized: {list(recognition.column_map.keys())}. "
                    f"Column map: {recognition.column_map}."
                )
            # Chunks exist but structured normalization failed — log and continue.
            # The LLM agents will still receive the raw table data via chunks.
            logger.warning(
                f"[{filename}] Structured normalization produced 0 activities "
                f"(columns recognized: {list(recognition.column_map.keys())}). "
                f"Proceeding with {len(chunks)} raw chunk(s) for LLM agents. "
                f"Raw headers: {headers}"
            )
            return schedule, chunks

        schedule = self._validator.validate(schedule)

        if not schedule.validation_passed:
            error_issues = [i for i in schedule.validation_issues if i.level == "ERROR"]
            raise PipelineError(
                f"Validation failed for '{filename}': "
                f"{len(error_issues)} ERROR-level issue(s) found. "
                f"First: {error_issues[0].message if error_issues else 'unknown'}",
                issues=schedule.validation_issues,
            )

        logger.info(
            f"[{filename}] Pipeline complete: "
            f"{schedule.metadata.total_activities} activities, "
            f"{len(chunks)} chunks, "
            f"warnings={len([i for i in schedule.validation_issues if i.level != 'ERROR'])}, "
            f"quality={schedule.metadata.parse_quality_score}"
        )

        return schedule, chunks
