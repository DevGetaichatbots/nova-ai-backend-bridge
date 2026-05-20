from abc import ABC, abstractmethod
from typing import Dict, Any
from pathlib import Path


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, file_path: Path) -> Dict[str, Any]:
        """Read native file stream and convert to intermediate Python data structures.

        Returns a dictionary containing:
          - 'headers': List[str]  — raw column header strings
          - 'rows':    List[List[str]]  — data rows (parallel to headers)
          - 'file_name': str  — original filename
          - 'source_system': str  — uppercase source system identifier
          - 'raw_text': str  — optional full raw text content (may be empty)
        """

    @abstractmethod
    def source_system(self) -> str:
        """Returns standard system uppercase identifier (e.g. 'CSV', 'PDF')."""
