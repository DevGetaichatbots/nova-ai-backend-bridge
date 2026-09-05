"""
Azure Document Intelligence OCR
===============================
AI-powered document analysis for extracting text and tables from PDFs.
Optimized for construction schedules and structured data.

The HTTP layer, polling, and table-parsing logic now live in
`ocr_client` (TL-1.3 extraction; see ADR-011). This module is a thin
wrapper that:

- enforces the credential contract on construction,
- exposes `AzureDocumentIntelligence.extract_from_pdf` (legacy
  `/upload` raw path's public API),
- keeps `extract_from_pdf`'s return shape unchanged,
- preserves the `_parse_tables`, `_word_confidences_in_span`, and
  `_derive_cell_confidence` methods as shims that delegate to
  `ocr_client` so pre-TL-1.3 tests and callers keep working.

The v2 router in `ingestion/routes/` and the legacy `/upload` route
both depend on this class's public API; the refactor is additive on
top of that surface.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

from ocr_client import (
    derive_cell_confidence as _derive_cell_confidence,
    parse_tables as _parse_tables,
    poll_results as _poll_results,
    submit_pdf as _submit_pdf,
    word_confidences_in_span as _word_confidences_in_span,
)


logger = logging.getLogger(__name__)


class AzureDocumentIntelligence:
    """
    Azure Document Intelligence OCR service.

    Usage:
        ocr = AzureDocumentIntelligence()
        result = ocr.extract_from_pdf(pdf_bytes, "filename.pdf")
    """

    API_VERSION = "2024-11-30"

    def __init__(self):
        self.endpoint = os.environ.get(
            "AZURE_DOC_INTELLIGENCE_ENDPOINT", ""
        ).rstrip("/")
        self.key = os.environ.get("AZURE_DOC_INTELLIGENCE_KEY", "")

        if not self.endpoint or not self.key:
            raise ValueError(
                "Missing Azure credentials. Set AZURE_DOC_INTELLIGENCE_ENDPOINT "
                "and AZURE_DOC_INTELLIGENCE_KEY environment variables."
            )

        logger.info("Azure Document Intelligence initialized")

    def _is_valid_pdf(self, pdf_bytes: bytes) -> bool:
        return pdf_bytes[:4] == b"%PDF" if len(pdf_bytes) >= 4 else False

    def _submit_pdf(self, pdf_bytes: bytes, filename: str) -> Optional[str]:
        """Backwards-compatible shim. New code should call
        `ocr_client.submit_pdf` directly."""
        return _submit_pdf(pdf_bytes, filename, self.endpoint, self.key)

    def _poll_results(
        self,
        operation_url: str,
        filename: str,
        timeout: int = 180,
    ) -> Optional[Dict]:
        """Backwards-compatible shim. New code should call
        `ocr_client.poll_results` directly."""
        return _poll_results(operation_url, filename, self.key, timeout=timeout)

    def _parse_tables(self, result: Dict, filename: str) -> List[Dict]:
        """Backwards-compatible shim. New code should call
        `ocr_client.parse_tables` directly."""
        return _parse_tables(result, filename)

    # The two confidence helpers below are exposed as static methods so
    # existing test code (which calls `AzureDocumentIntelligence._x(...)`
    # directly) keeps working without churn. The implementation is in
    # `ocr_client.azure`; these shims are the only reason the methods
    # appear on the class at all.
    @staticmethod
    def _word_confidences_in_span(
        span_start: int,
        span_length: int,
        pages_words: List[Dict],
    ) -> List[float]:
        return _word_confidences_in_span(span_start, span_length, pages_words)

    @staticmethod
    def _derive_cell_confidence(
        cell_spans: List[Dict],
        pages_words: List[Dict],
    ) -> Optional[float]:
        return _derive_cell_confidence(cell_spans, pages_words)

    def extract_from_pdf(
        self,
        pdf_bytes: bytes,
        filename: str = "document.pdf",
        timeout: int = 180,
    ) -> Dict:
        """
        Extract content from PDF using Azure Document Intelligence.

        Args:
            pdf_bytes: Raw PDF file bytes
            filename: Name of the file (for logging)
            timeout: Max seconds to wait for Azure (default 180)

        Returns:
            Dict with:
            - success: bool
            - raw_markdown: Full markdown content from Azure
            - table_rows: List of parsed table rows
            - error: Error message if failed
        """
        if not self._is_valid_pdf(pdf_bytes):
            return {
                "success": False,
                "raw_markdown": "",
                "table_rows": [],
                "error": "Invalid PDF file (missing %PDF header)",
            }

        operation_url = self._submit_pdf(pdf_bytes, filename)
        if not operation_url:
            return {
                "success": False,
                "raw_markdown": "",
                "table_rows": [],
                "error": "Failed to submit PDF to Azure",
            }

        result = self._poll_results(operation_url, filename, timeout)
        if not result:
            return {
                "success": False,
                "raw_markdown": "",
                "table_rows": [],
                "error": "Azure analysis timed out or failed",
            }

        raw_markdown = result.get("analyzeResult", {}).get("content", "")
        tables = self._parse_tables(result, filename)
        pages = self._extract_pages(result, filename)

        logger.info(
            f"[{filename}] Extracted {len(raw_markdown)} chars, "
            f"{len(tables)} tables, {len(pages)} pages"
        )

        return {
            "success": True,
            "raw_markdown": raw_markdown,
            "tables": tables,
            "pages": pages,
            "error": None,
        }

    def _extract_pages(self, result: Dict, filename: str) -> List[Dict]:
        """Extract page-level content with page numbers."""
        try:
            analyze_result = result.get("analyzeResult", {})
            pages_data = analyze_result.get("pages", [])
            content = analyze_result.get("content", "")

            if not pages_data:
                if content:
                    return [
                        {
                            "content": content,
                            "page_number": 1,
                            "total_pages": 1,
                        }
                    ]
                return []

            pages = []
            for page in pages_data:
                page_num = page.get("pageNumber", 1)
                spans = page.get("spans", [])

                page_text = ""
                for span in spans:
                    offset = span.get("offset", 0)
                    length = span.get("length", 0)
                    page_text += content[offset:offset + length]

                if page_text.strip():
                    pages.append({
                        "content": page_text,
                        "page_number": page_num,
                        "total_pages": len(pages_data),
                    })

            if not pages and content:
                return [
                    {
                        "content": content,
                        "page_number": 1,
                        "total_pages": 1,
                    }
                ]

            return pages

        except Exception as e:
            logger.error(f"[{filename}] Error extracting pages: {e}")
            return []

    @staticmethod
    def check_credentials() -> tuple:
        endpoint = os.environ.get("AZURE_DOC_INTELLIGENCE_ENDPOINT", "")
        key = os.environ.get("AZURE_DOC_INTELLIGENCE_KEY", "")

        if not endpoint:
            return False, "AZURE_DOC_INTELLIGENCE_ENDPOINT not set"
        if not key:
            return False, "AZURE_DOC_INTELLIGENCE_KEY not set"

        return True, "Azure Document Intelligence configured"
