"""
Config-Driven Field Mapper
==========================
Loads YAML mapping profiles from config/mappings/.
Merges static config with heuristic recognition results.
"""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config" / "mappings"


def _load_yaml_mapping(source_system: str) -> Dict[str, str]:
    filename = _CONFIG_DIR / f"{source_system.lower()}.yaml"
    if not filename.exists():
        return {}

    try:
        import yaml  # type: ignore
        with open(filename, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except ImportError:
        return _parse_simple_yaml(filename)
    except Exception as e:
        logger.warning(f"Failed to load mapping file {filename}: {e}")
        return {}


def _parse_simple_yaml(path: Path) -> Dict[str, str]:
    """Minimal YAML key: value parser (no deps)."""
    result = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    key, _, val = line.partition(":")
                    result[key.strip()] = val.strip().strip('"').strip("'")
    except Exception:
        pass
    return result


class FieldMapper:
    """
    Merges static YAML config with heuristic recognition result.
    Static config takes precedence over heuristics only where heuristics
    gave no result.
    """

    def __init__(self, source_system: str, heuristic_map: Dict[str, str]):
        self._static = _load_yaml_mapping(source_system)
        self._heuristic = heuristic_map

    def get(self, semantic_role: str) -> Optional[str]:
        """
        Returns the raw column name for a given semantic role.
        Priority: heuristic > static config.
        """
        return self._heuristic.get(semantic_role) or self._static.get(semantic_role)

    def all_mappings(self) -> Dict[str, str]:
        merged = dict(self._static)
        merged.update(self._heuristic)
        return merged
