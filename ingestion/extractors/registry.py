from typing import Dict
from ingestion.extractors.base import BaseExtractor


class ExtractorRegistry:
    _registry: Dict[str, "BaseExtractor"] = {}

    @classmethod
    def register(cls, source_system: str, extractor: "BaseExtractor") -> None:
        cls._registry[source_system.upper()] = extractor

    @classmethod
    def get(cls, source_system: str) -> "BaseExtractor":
        extractor = cls._registry.get(source_system.upper())
        if not extractor:
            raise ValueError(
                f"No extractor registered for source system: {source_system}. "
                f"Available: {list(cls._registry.keys())}"
            )
        return extractor

    @classmethod
    def available(cls) -> list:
        return list(cls._registry.keys())
