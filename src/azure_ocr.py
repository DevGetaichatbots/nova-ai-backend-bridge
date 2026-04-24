"""
Azure Document Intelligence OCR
===============================
AI-powered document analysis for extracting text and tables from PDFs.
Optimized for construction schedules and structured data.
"""
import os
import re
import time
import logging
import requests
from typing import Optional, Dict, List

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
        self.endpoint = os.environ.get("AZURE_DOC_INTELLIGENCE_ENDPOINT", "").rstrip('/')
        self.key = os.environ.get("AZURE_DOC_INTELLIGENCE_KEY", "")
        
        if not self.endpoint or not self.key:
            raise ValueError(
                "Missing Azure credentials. Set AZURE_DOC_INTELLIGENCE_ENDPOINT "
                "and AZURE_DOC_INTELLIGENCE_KEY environment variables."
            )
        
        logger.info(f"Azure Document Intelligence initialized")
    
    def _is_valid_pdf(self, pdf_bytes: bytes) -> bool:
        return pdf_bytes[:4] == b'%PDF' if len(pdf_bytes) >= 4 else False
    
    def _submit_pdf(self, pdf_bytes: bytes, filename: str) -> Optional[str]:
        url = (
            f"{self.endpoint}/documentintelligence/documentModels/"
            f"prebuilt-layout:analyze?api-version={self.API_VERSION}"
            f"&outputContentFormat=markdown"
        )
        
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "application/pdf"
        }
        
        try:
            logger.info(f"[{filename}] Submitting PDF to Azure ({len(pdf_bytes)} bytes)...")
            response = requests.post(url, headers=headers, data=pdf_bytes, timeout=60)
            response.raise_for_status()
            
            operation_url = response.headers.get("Operation-Location")
            if not operation_url:
                logger.error(f"[{filename}] No Operation-Location in response")
                return None
            
            logger.info(f"[{filename}] Operation started")
            return operation_url
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[{filename}] Failed to submit PDF: {e}")
            return None
    
    def _poll_results(self, operation_url: str, filename: str,
                      timeout: int = 180) -> Optional[Dict]:
        headers = {"Ocp-Apim-Subscription-Key": self.key}
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time

            if elapsed > timeout:
                logger.error(f"[{filename}] Polling timeout after {timeout}s")
                return None

            # Adaptive back-off: 1s for the first 30s, then 2s after that.
            # Avoids hammering Azure on slow jobs while staying responsive on fast ones.
            poll_interval = 1 if elapsed < 30 else 2

            try:
                response = requests.get(operation_url, headers=headers, timeout=30)
                response.raise_for_status()
                result = response.json()

                status = result.get("status", "unknown")
                logger.info(f"[{filename}] Status: {status} (elapsed: {elapsed:.1f}s, next poll in {poll_interval}s)")

                if status == "succeeded":
                    logger.info(f"[{filename}] Extraction complete in {elapsed:.1f}s")
                    return result
                elif status == "failed":
                    error = result.get("error", {})
                    logger.error(f"[{filename}] Extraction failed: {error}")
                    return None
                elif status in ["notStarted", "running"]:
                    time.sleep(poll_interval)
                else:
                    logger.warning(f"[{filename}] Unknown status: {status}")
                    time.sleep(poll_interval)

            except requests.exceptions.RequestException as e:
                logger.error(f"[{filename}] Polling error: {e}")
                time.sleep(poll_interval)
    
    def _parse_tables(self, result: Dict, filename: str) -> List[Dict]:
        """
        Extract structured table data from Azure response.
        Uses Azure's table objects for accurate cell/row/column data.
        Handles merged cells (rowSpan, columnSpan).
        """
        try:
            analyze_result = result.get("analyzeResult", {})
            tables = analyze_result.get("tables", [])
            
            if not tables:
                return []
            
            structured_tables = []
            for table_idx, table in enumerate(tables):
                row_count = table.get("rowCount", 0)
                col_count = table.get("columnCount", 0)
                cells_data = table.get("cells", [])
                
                grid = [[{"content": "", "row_span": 1, "col_span": 1} for _ in range(col_count)] for _ in range(row_count)]
                
                cells_list = []
                for cell in cells_data:
                    row_idx = cell.get("rowIndex", 0)
                    col_idx = cell.get("columnIndex", 0)
                    cell_content = cell.get("content", "")
                    row_span = cell.get("rowSpan", 1)
                    col_span = cell.get("columnSpan", 1)
                    kind = cell.get("kind", "content")
                    
                    cell_info = {
                        "content": cell_content,
                        "row": row_idx,
                        "col": col_idx,
                        "row_span": row_span,
                        "col_span": col_span,
                        "kind": kind
                    }
                    cells_list.append(cell_info)
                    
                    if 0 <= row_idx < row_count and 0 <= col_idx < col_count:
                        grid[row_idx][col_idx] = {
                            "content": cell_content,
                            "row_span": row_span,
                            "col_span": col_span
                        }
                        for r in range(row_idx, min(row_idx + row_span, row_count)):
                            for c in range(col_idx, min(col_idx + col_span, col_count)):
                                if r != row_idx or c != col_idx:
                                    grid[r][c] = {
                                        "content": f"^{cell_content[:20]}..." if len(cell_content) > 20 else f"^{cell_content}",
                                        "row_span": 0,
                                        "col_span": 0,
                                        "merged_from": [row_idx, col_idx]
                                    }
                
                bounding_regions = table.get("boundingRegions", [])
                page_numbers = list(set(br.get("pageNumber", 1) for br in bounding_regions))
                
                header_cells = [c for c in cells_data if c.get("kind") == "columnHeader"]
                if header_cells:
                    header_row_indices = set(hc.get("rowIndex", 0) for hc in header_cells)
                    sample = [hc.get("content", "")[:30] for hc in header_cells[:5]]
                    logger.info(f"[{filename}] Table {table_idx}: Azure marked {len(header_cells)} columnHeader cells in rows {header_row_indices} (sample: {sample}) — ignored, using fallback header detection")

                simple_rows = []
                for row in grid:
                    simple_row = [cell["content"] if cell["content"] and not cell["content"].startswith("^") else "" for cell in row]
                    simple_rows.append(simple_row)
                
                structured_tables.append({
                    "table_id": table_idx,
                    "row_count": row_count,
                    "column_count": col_count,
                    "page_numbers": sorted(page_numbers),
                    "rows": simple_rows,
                    "cells": cells_list,
                    "has_merged_cells": any(c.get("row_span", 1) > 1 or c.get("col_span", 1) > 1 for c in cells_list)
                })
            
            logger.info(f"[{filename}] Extracted {len(structured_tables)} structured tables")
            return structured_tables
            
        except Exception as e:
            logger.error(f"[{filename}] Error parsing tables: {e}")
            return []
    
    def extract_from_pdf(self, pdf_bytes: bytes, filename: str = "document.pdf",
                         timeout: int = 180) -> Dict:
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
                "error": "Invalid PDF file (missing %PDF header)"
            }
        
        operation_url = self._submit_pdf(pdf_bytes, filename)
        if not operation_url:
            return {
                "success": False,
                "raw_markdown": "",
                "table_rows": [],
                "error": "Failed to submit PDF to Azure"
            }
        
        result = self._poll_results(operation_url, filename, timeout)
        if not result:
            return {
                "success": False,
                "raw_markdown": "",
                "table_rows": [],
                "error": "Azure analysis timed out or failed"
            }
        
        raw_markdown = result.get("analyzeResult", {}).get("content", "")
        tables = self._parse_tables(result, filename)
        pages = self._extract_pages(result, filename)
        
        logger.info(f"[{filename}] Extracted {len(raw_markdown)} chars, {len(tables)} tables, {len(pages)} pages")
        
        return {
            "success": True,
            "raw_markdown": raw_markdown,
            "tables": tables,
            "pages": pages,
            "error": None
        }
    
    def _extract_pages(self, result: Dict, filename: str) -> List[Dict]:
        """Extract page-level content with page numbers."""
        try:
            analyze_result = result.get("analyzeResult", {})
            pages_data = analyze_result.get("pages", [])
            content = analyze_result.get("content", "")
            
            if not pages_data:
                if content:
                    return [{"content": content, "page_number": 1, "total_pages": 1}]
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
                        "total_pages": len(pages_data)
                    })
            
            if not pages and content:
                return [{"content": content, "page_number": 1, "total_pages": 1}]
            
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
