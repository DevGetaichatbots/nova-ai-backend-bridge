"""Brief §41 versioning: seven independent version dimensions (TL-9.3).

Brief §41:
    "Results will change over time, and without versions nobody can
    explain why."

The seven independent version dimensions:
1. parser: Parser name and version (e.g. nusf-pipeline-v2.1)
2. matching_algorithm: Matching algorithm version (e.g. nusf-matcher-v3.2)
3. analysis_engine: Comparison engine version (e.g. nusf-compare-engine-v1.4)
4. prompt: Prompt template version or hash (e.g. predictive-prompt-v2.1)
5. model: LLM deployment / model version (e.g. azure-gpt-4o)
6. schedule_revision: Schedule revision identifier or hash
7. manual_corrections: Manual corrections version (e.g. corrections-v1 or corrections:none)

Do-not rule:
    Do NOT use a single global version number. Brief §41 lists seven independent
    dimensions precisely because they change independently.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

# Canonical default versions
DEFAULT_PARSER_VERSION = "nusf-pipeline-v2.1"
DEFAULT_MATCHING_ALGORITHM_VERSION = "nusf-matcher-v3.2"
DEFAULT_ANALYSIS_ENGINE_VERSION = "nusf-compare-engine-v1.4"
DEFAULT_PREDICTIVE_ENGINE_VERSION = "predictive-graph-engine-v1.0"
DEFAULT_PROMPT_VERSION = "predictive-prompt-v2.1"
DEFAULT_COMPARISON_PROMPT_VERSION = "comparison-prompt-v1.0"
DEFAULT_MODEL_VERSION = "azure-gpt-4o"
DEFAULT_SCHEDULE_REVISION = "rev:current"
DEFAULT_MANUAL_CORRECTIONS = "corrections:none"

ALL_VERSION_DIMENSIONS: Tuple[str, ...] = (
    "parser",
    "matching_algorithm",
    "analysis_engine",
    "prompt",
    "model",
    "schedule_revision",
    "manual_corrections",
)


def compute_prompt_version_hash(prompt_text: str, prefix: str = "prompt") -> str:
    """Derive a deterministic prompt version hash from template text."""
    h = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}:{h}"


class AnalysisVersions(BaseModel):
    """The seven independent version dimensions mandated by Brief §41."""

    parser: str = Field(default=DEFAULT_PARSER_VERSION, description="Parser version")
    matching_algorithm: str = Field(
        default=DEFAULT_MATCHING_ALGORITHM_VERSION,
        description="Matching algorithm version",
    )
    analysis_engine: str = Field(
        default=DEFAULT_ANALYSIS_ENGINE_VERSION,
        description="Comparison engine version",
    )
    prompt: str = Field(default=DEFAULT_PROMPT_VERSION, description="Prompt version or hash")
    model: str = Field(default=DEFAULT_MODEL_VERSION, description="Model deployment version")
    schedule_revision: str = Field(
        default=DEFAULT_SCHEDULE_REVISION, description="Schedule revision or hash"
    )
    manual_corrections: str = Field(
        default=DEFAULT_MANUAL_CORRECTIONS, description="Manual corrections version"
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            alias_map = {
                "parser_version": "parser",
                "matching_algorithm_version": "matching_algorithm",
                "analysis_engine_version": "analysis_engine",
                "prompt_version": "prompt",
                "model_version": "model",
                "manual_corrections_version": "manual_corrections",
            }
            res = dict(data)
            for old_key, new_key in alias_map.items():
                if old_key in res and new_key not in res:
                    res[new_key] = res.pop(old_key)
            return res
        return data

    @property
    def parser_version(self) -> str:
        return self.parser

    @property
    def matching_algorithm_version(self) -> str:
        return self.matching_algorithm

    @property
    def analysis_engine_version(self) -> str:
        return self.analysis_engine

    @property
    def prompt_version(self) -> str:
        return self.prompt

    @property
    def model_version(self) -> str:
        return self.model

    @property
    def manual_corrections_version(self) -> str:
        return self.manual_corrections

    def to_dict(self) -> Dict[str, str]:
        """Return dict of all seven independent dimensions."""
        return {
            "parser": self.parser,
            "matching_algorithm": self.matching_algorithm,
            "analysis_engine": self.analysis_engine,
            "prompt": self.prompt,
            "model": self.model,
            "schedule_revision": self.schedule_revision,
            "manual_corrections": self.manual_corrections,
        }

    def stamp_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Stamp the seven version dimensions into an analysis result dictionary."""
        result["versions"] = self.to_dict()
        return result

    def is_distinguishable_from(
        self, other: AnalysisVersions | Dict[str, Any]
    ) -> bool:
        """Check if two version sets differ in any of the seven dimensions."""
        other_dict = other.to_dict() if isinstance(other, AnalysisVersions) else other
        my_dict = self.to_dict()
        return any(my_dict.get(dim) != other_dict.get(dim) for dim in ALL_VERSION_DIMENSIONS)

    def diff(
        self, other: AnalysisVersions | Dict[str, Any]
    ) -> Dict[str, Tuple[str, str]]:
        """Return dimensions that differ as a dict of dimension -> (self_version, other_version)."""
        other_dict = other.to_dict() if isinstance(other, AnalysisVersions) else other
        my_dict = self.to_dict()
        return {
            dim: (my_dict[dim], other_dict.get(dim, ""))
            for dim in ALL_VERSION_DIMENSIONS
            if my_dict.get(dim) != other_dict.get(dim)
        }
