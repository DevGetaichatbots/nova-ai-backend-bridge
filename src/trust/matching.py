"""Nova Trust Layer — Match confidence level model (TL-3.1, brief §12).

Defines the 5-level match confidence hierarchy:
- L1_EXACT_VERIFIED_ID: Same verified durable source identifier (very high)
- L2_STRONG_MULTI_FIELD: Name + location + trade + building/floor align (high)
- L3_PARTIAL: Name + location align, other fields differ or missing (medium)
- L4_FUZZY: Similarity exists, evidence insufficient (low)
- L5_NO_RELIABLE_MATCH: Refuses to match (must not match)

Categorical by design (brief §23: avoid unsupported precision).
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional, Any
from pydantic import BaseModel, Field, model_validator

from src.trust.vocabulary import TrustState


class MatchLevel(str, Enum):
    L1_EXACT_VERIFIED_ID = "L1_EXACT_VERIFIED_ID"
    L2_STRONG_MULTI_FIELD = "L2_STRONG_MULTI_FIELD"
    L3_PARTIAL = "L3_PARTIAL"
    L4_FUZZY = "L4_FUZZY"
    L5_NO_RELIABLE_MATCH = "L5_NO_RELIABLE_MATCH"


class MatchResult(BaseModel):
    level: MatchLevel = Field(..., description="Categorical match level")
    method: str = Field(..., description="Human-readable explanation of match method")
    evidence: List[str] = Field(default_factory=list, description="Fields that aligned to produce match")
    matched_id: Optional[str] = Field(None, description="Matched counterpart activity ID")
    candidates: List[dict[str, Any]] = Field(default_factory=list, description="Candidate matches for ambiguity review")
    requires_verification: bool = Field(False, description="Flag indicating match needs manual review")

    @model_validator(mode="after")
    def validate_match_invariants(self) -> MatchResult:
        if self.level == MatchLevel.L5_NO_RELIABLE_MATCH and self.matched_id is not None:
            raise ValueError("L5_NO_RELIABLE_MATCH cannot have a non-null matched_id")
        if self.level in (MatchLevel.L4_FUZZY, MatchLevel.L5_NO_RELIABLE_MATCH):
            self.requires_verification = True
        return self


def to_trust_state(level: MatchLevel) -> TrustState:
    """Map a categorical MatchLevel into user-facing TrustState (brief §12, ADR-015)."""
    if level == MatchLevel.L1_EXACT_VERIFIED_ID:
        return TrustState.VERIFIED
    elif level in (MatchLevel.L2_STRONG_MULTI_FIELD, MatchLevel.L3_PARTIAL):
        return TrustState.REVIEW
    else:  # L4_FUZZY, L5_NO_RELIABLE_MATCH
        return TrustState.UNVERIFIED


__all__ = [
    "MatchLevel",
    "MatchResult",
    "to_trust_state",
]
