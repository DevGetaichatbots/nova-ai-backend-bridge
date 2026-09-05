"""Brief §40 audit log and reconstruction chain (TL-9.2).

Brief §40's test:
    "If K&L asks 'Why did Nova say this on 12 August?' you should
    be able to reconstruct the answer."

The chain strictly spans nine stages:
1. schedule_uploaded  (filename, file sha256 hash, size, timestamp)
2. parser_version      (parser name, version, format detector)
3. ocr_provider        (provider, API version, model ID)
4. confidence_results  (confidence summary, unverified counts, OCR scores)
5. matches_generated   (match algorithm, candidate scores, L1/L2/L3 counts)
6. manual_corrections  (applied confirmed mappings, user overrides)
7. analysis_version    (comparison engine, rules version)
8. agent_answer        (model, prompt version, findings/response summary)
9. evidence_used       (deterministic facts referenced, source IDs, row/page refs)

Do-not rules:
- Do NOT log raw document contents into the audit trail. Reference them by hash/filename;
  duplicating client project data multiplies the handling obligation.
- The log is append-only and immutable.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from src.trust.versioning import (
    ALL_VERSION_DIMENSIONS,
    DEFAULT_ANALYSIS_ENGINE_VERSION,
    DEFAULT_MANUAL_CORRECTIONS,
    DEFAULT_MATCHING_ALGORITHM_VERSION,
    DEFAULT_MODEL_VERSION,
    DEFAULT_PARSER_VERSION,
    DEFAULT_PROMPT_VERSION,
    DEFAULT_SCHEDULE_REVISION,
    AnalysisVersions,
)

logger = logging.getLogger(__name__)


class AuditStage(str, Enum):
    """The nine mandatory stages in the Brief §40 audit chain."""

    SCHEDULE_UPLOADED = "schedule_uploaded"
    PARSER_VERSION = "parser_version"
    OCR_PROVIDER = "ocr_provider"
    CONFIDENCE_RESULTS = "confidence_results"
    MATCHES_GENERATED = "matches_generated"
    MANUAL_CORRECTIONS = "manual_corrections"
    ANALYSIS_VERSION = "analysis_version"
    AGENT_ANSWER = "agent_answer"
    EVIDENCE_USED = "evidence_used"


ALL_BRIEF_40_STAGES: Tuple[AuditStage, ...] = (
    AuditStage.SCHEDULE_UPLOADED,
    AuditStage.PARSER_VERSION,
    AuditStage.OCR_PROVIDER,
    AuditStage.CONFIDENCE_RESULTS,
    AuditStage.MATCHES_GENERATED,
    AuditStage.MANUAL_CORRECTIONS,
    AuditStage.ANALYSIS_VERSION,
    AuditStage.AGENT_ANSWER,
    AuditStage.EVIDENCE_USED,
)


def _compute_entry_hash(
    prev_hash: str,
    stage: str,
    timestamp: str,
    data: Dict[str, Any],
    versions: Optional[Dict[str, str]] = None,
) -> str:
    """Compute SHA-256 tamper-evident hash chaining previous hash to this entry."""
    canonical_json = json.dumps(data, sort_keys=True, default=str)
    if versions:
        ver_json = json.dumps(versions, sort_keys=True, default=str)
        raw = f"{prev_hash}|{stage}|{timestamp}|{canonical_json}|{ver_json}"
    else:
        raw = f"{prev_hash}|{stage}|{timestamp}|{canonical_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuditChainEntry(BaseModel):
    """An immutable, tamper-evident entry in the Brief §40 audit chain."""

    stage: AuditStage
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    data: Dict[str, Any] = Field(default_factory=dict)
    versions: Optional[Dict[str, str]] = None
    prev_hash: str = "GENESIS"
    hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.hash:
            self.hash = _compute_entry_hash(
                self.prev_hash, self.stage.value, self.timestamp, self.data, self.versions
            )


class ImmutableAuditError(Exception):
    """Raised when attempting to modify or delete an audit trail entry."""


class AnalysisAuditTrail(BaseModel):
    """Append-only audit trail for an analysis run, satisfying Brief §40."""

    analysis_id: str
    project_id: Optional[str] = None
    company_id: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    entries: List[AuditChainEntry] = Field(default_factory=list)
    versions: Optional[AnalysisVersions] = None

    def set_versions(self, versions: AnalysisVersions | Dict[str, str]) -> None:
        """Set or update the trail's version manifest."""
        if isinstance(versions, dict):
            self.versions = AnalysisVersions(**versions)
        else:
            self.versions = versions

    def get_versions(self) -> Dict[str, str]:
        """Return the seven Brief §41 version dimensions."""
        if self.versions:
            return self.versions.to_dict()

        # Extract from recorded stage entries if versions object was not explicitly set
        parser_info = self.get_stage(AuditStage.PARSER_VERSION)
        matches_info = self.get_stage(AuditStage.MATCHES_GENERATED)
        analysis_info = self.get_stage(AuditStage.ANALYSIS_VERSION)
        answer_info = self.get_stage(AuditStage.AGENT_ANSWER)
        schedule_info = self.get_stage(AuditStage.SCHEDULE_UPLOADED)
        corrections_info = self.get_stage(AuditStage.MANUAL_CORRECTIONS)

        p_data = parser_info.data if parser_info else {}
        m_data = matches_info.data if matches_info else {}
        an_data = analysis_info.data if analysis_info else {}
        ans_data = answer_info.data if answer_info else {}
        s_data = schedule_info.data if schedule_info else {}
        c_data = corrections_info.data if corrections_info else {}

        return AnalysisVersions(
            parser=p_data.get("parser_version") or p_data.get("version") or p_data.get("parser") or DEFAULT_PARSER_VERSION,
            matching_algorithm=m_data.get("algorithm_version") or m_data.get("matching_algorithm") or DEFAULT_MATCHING_ALGORITHM_VERSION,
            analysis_engine=an_data.get("engine_version") or an_data.get("version") or an_data.get("engine") or DEFAULT_ANALYSIS_ENGINE_VERSION,
            prompt=ans_data.get("prompt_version") or ans_data.get("prompt") or DEFAULT_PROMPT_VERSION,
            model=ans_data.get("model_version") or ans_data.get("model") or DEFAULT_MODEL_VERSION,
            schedule_revision=s_data.get("schedule_revision") or s_data.get("revision") or DEFAULT_SCHEDULE_REVISION,
            manual_corrections=c_data.get("corrections_version") or c_data.get("corrections") or DEFAULT_MANUAL_CORRECTIONS,
        ).to_dict()

    def add_entry(
        self,
        stage: AuditStage,
        data: Dict[str, Any],
        versions: Optional[AnalysisVersions | Dict[str, str]] = None,
    ) -> AuditChainEntry:
        """Append an entry to the audit chain with cryptographic chaining."""
        # Sanity check: Do not log raw document contents (Brief §40 Do-not rule)
        sanitized_data = _sanitize_audit_data(data)

        prev_hash = self.entries[-1].hash if self.entries else "GENESIS"
        ts = datetime.now(timezone.utc).isoformat()

        ver_dict = None
        if versions is not None:
            ver_dict = versions.to_dict() if isinstance(versions, AnalysisVersions) else dict(versions)
        elif self.versions is not None:
            ver_dict = self.versions.to_dict()

        entry_hash = _compute_entry_hash(prev_hash, stage.value, ts, sanitized_data, ver_dict)

        entry = AuditChainEntry(
            stage=stage,
            timestamp=ts,
            data=sanitized_data,
            versions=ver_dict,
            prev_hash=prev_hash,
            hash=entry_hash,
        )
        self.entries.append(entry)
        return entry

    def get_stage(self, stage: AuditStage) -> Optional[AuditChainEntry]:
        """Retrieve the latest recorded entry for a given stage."""
        for entry in reversed(self.entries):
            if entry.stage == stage:
                return entry
        return None

    def get_stages(self, stage: AuditStage) -> List[AuditChainEntry]:
        """Retrieve all recorded entries for a given stage in order."""
        return [entry for entry in self.entries if entry.stage == stage]

    def has_stage(self, stage: AuditStage) -> bool:
        return any(entry.stage == stage for entry in self.entries)

    def is_complete(self) -> bool:
        """Check whether every one of Brief §40's nine stages has been logged."""
        logged_stages = {entry.stage for entry in self.entries}
        return all(stage in logged_stages for stage in ALL_BRIEF_40_STAGES)

    def missing_stages(self) -> List[AuditStage]:
        """List any Brief §40 stages not yet recorded in this audit trail."""
        logged_stages = {entry.stage for entry in self.entries}
        return [s for s in ALL_BRIEF_40_STAGES if s not in logged_stages]

    def verify_integrity(self) -> bool:
        """Verify that no entry in the cryptographic chain has been tampered with."""
        if not self.entries:
            return True

        prev_hash = "GENESIS"
        for entry in self.entries:
            if entry.prev_hash != prev_hash:
                logger.warning(
                    f"Audit chain broken at stage {entry.stage}: expected prev_hash {prev_hash}, got {entry.prev_hash}"
                )
                return False

            expected_hash = _compute_entry_hash(
                prev_hash, entry.stage.value, entry.timestamp, entry.data, entry.versions
            )
            if entry.hash != expected_hash:
                logger.warning(
                    f"Audit entry hash mismatch at stage {entry.stage}: expected {expected_hash}, got {entry.hash}"
                )
                return False

            prev_hash = entry.hash
        return True

    def reconstruct_answer(self) -> Dict[str, Any]:
        """Reconstruct the explanation for 'Why did Nova say this?' per Brief §40."""
        schedule_info = self.get_stage(AuditStage.SCHEDULE_UPLOADED)
        parser_info = self.get_stage(AuditStage.PARSER_VERSION)
        ocr_info = self.get_stage(AuditStage.OCR_PROVIDER)
        confidence_info = self.get_stage(AuditStage.CONFIDENCE_RESULTS)
        matches_info = self.get_stage(AuditStage.MATCHES_GENERATED)
        corrections_info = self.get_stage(AuditStage.MANUAL_CORRECTIONS)
        analysis_info = self.get_stage(AuditStage.ANALYSIS_VERSION)
        answer_info = self.get_stage(AuditStage.AGENT_ANSWER)
        evidence_info = self.get_stage(AuditStage.EVIDENCE_USED)

        return {
            "analysis_id": self.analysis_id,
            "reconstructed_at": datetime.now(timezone.utc).isoformat(),
            "audit_trail_intact": self.verify_integrity(),
            "is_complete": self.is_complete(),
            "versions": self.get_versions(),
            "schedule": schedule_info.data if schedule_info else None,
            "parser": parser_info.data if parser_info else None,
            "ocr": ocr_info.data if ocr_info else None,
            "confidence": confidence_info.data if confidence_info else None,
            "matching": matches_info.data if matches_info else None,
            "human_corrections": corrections_info.data if corrections_info else None,
            "analysis_engine": analysis_info.data if analysis_info else None,
            "agent_response": answer_info.data if answer_info else None,
            "evidence": evidence_info.data if evidence_info else None,
        }


def _sanitize_audit_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure raw file bytes or enormous text dumps are not logged into the audit trail."""
    sanitized: Dict[str, Any] = {}
    for k, v in data.items():
        k_lower = k.lower()
        if isinstance(v, (bytes, bytearray)):
            # Replace raw bytes with hash and length reference
            sanitized[f"{k}_sha256"] = hashlib.sha256(v).hexdigest()
            sanitized[f"{k}_size_bytes"] = len(v)
        elif "raw_file" in k_lower or "pdf_bytes" in k_lower or "file_data" in k_lower:
            if isinstance(v, str) and len(v) > 500:
                sanitized[f"{k}_sha256"] = hashlib.sha256(v.encode("utf-8")).hexdigest()
            else:
                sanitized[k] = v
        elif isinstance(v, dict):
            sanitized[k] = _sanitize_audit_data(v)
        elif isinstance(v, list):
            sanitized[k] = [
                _sanitize_audit_data(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            sanitized[k] = v
    return sanitized


class AuditStore:
    """In-memory append-only audit trail repository with tenant scoping."""

    def __init__(self) -> None:
        self._trails: Dict[str, AnalysisAuditTrail] = {}

    def get_or_create(
        self,
        analysis_id: str,
        project_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> AnalysisAuditTrail:
        """Get existing trail or create a new one."""
        if analysis_id not in self._trails:
            self._trails[analysis_id] = AnalysisAuditTrail(
                analysis_id=analysis_id,
                project_id=project_id,
                company_id=company_id,
            )
        return self._trails[analysis_id]

    def get(self, analysis_id: str) -> Optional[AnalysisAuditTrail]:
        """Retrieve audit trail by analysis_id."""
        return self._trails.get(analysis_id)

    def list_by_project(self, project_id: str) -> List[AnalysisAuditTrail]:
        """Retrieve all audit trails for a given project."""
        return [
            t for t in self._trails.values() if t.project_id == project_id
        ]

    def list_by_company(self, company_id: str) -> List[AnalysisAuditTrail]:
        """Retrieve all audit trails for a company (tenant scoping)."""
        return [
            t for t in self._trails.values() if t.company_id == company_id
        ]


# Global in-memory audit store instance
audit_store = AuditStore()
