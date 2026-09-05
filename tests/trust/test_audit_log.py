"""Tests for TL-9.2 — Audit log (Brief §40).

Acceptance criteria from changes/trust-layer/plan/phase-9-evidence-audit.md:
- AC1: Every stage in the brief §40 chain logged
- AC2: Log is append-only and tamper-evident
- AC3: A past analysis can be fully reconstructed from the log
- AC4: Relationship to existing unused log_audit_event decided and recorded

Do-not rule:
- Do not log raw document contents into the audit trail. Reference them by hash/filename;
  duplicating client project data multiplies the handling obligation.
"""
from __future__ import annotations

import pytest

from src.trust.audit import (
    ALL_BRIEF_40_STAGES,
    AnalysisAuditTrail,
    AuditChainEntry,
    AuditStage,
    AuditStore,
    _sanitize_audit_data,
)


class TestBrief40AuditStages:
    """AC1: Every stage in the brief §40 chain logged."""

    def test_all_nine_brief_40_stages_exist(self):
        """Brief §40 specifies nine distinct stages in the reconstruction chain."""
        expected_stages = [
            "schedule_uploaded",
            "parser_version",
            "ocr_provider",
            "confidence_results",
            "matches_generated",
            "manual_corrections",
            "analysis_version",
            "agent_answer",
            "evidence_used",
        ]
        assert len(ALL_BRIEF_40_STAGES) == 9
        for s in expected_stages:
            assert any(stage.value == s for stage in ALL_BRIEF_40_STAGES)

    def test_audit_trail_tracks_completion_status(self):
        """Trail reports incomplete until all 9 stages are recorded."""
        trail = AnalysisAuditTrail(analysis_id="test_cmp_100")
        assert trail.is_complete() is False
        assert len(trail.missing_stages()) == 9

        # Add 8 stages
        for stage in ALL_BRIEF_40_STAGES[:-1]:
            trail.add_entry(stage, {"info": f"test for {stage.value}"})

        assert trail.is_complete() is False
        assert trail.missing_stages() == [ALL_BRIEF_40_STAGES[-1]]

        # Add the 9th stage
        trail.add_entry(ALL_BRIEF_40_STAGES[-1], {"info": "evidence"})
        assert trail.is_complete() is True
        assert len(trail.missing_stages()) == 0


class TestAuditAppendOnlyAndTamperEvident:
    """AC2: Log is append-only, immutable, and tamper-evident."""

    def test_entries_are_cryptographically_chained(self):
        """Each entry carries SHA-256 hash chaining to the previous entry."""
        trail = AnalysisAuditTrail(analysis_id="cmp_crypto_1")
        e1 = trail.add_entry(AuditStage.SCHEDULE_UPLOADED, {"filename": "july.pdf"})
        assert e1.prev_hash == "GENESIS"
        assert len(e1.hash) == 64

        e2 = trail.add_entry(AuditStage.PARSER_VERSION, {"parser": "nusf_parser_v1"})
        assert e2.prev_hash == e1.hash
        assert len(e2.hash) == 64

        e3 = trail.add_entry(AuditStage.OCR_PROVIDER, {"ocr": "azure_di_v2"})
        assert e3.prev_hash == e2.hash

        assert trail.verify_integrity() is True

    def test_tampering_with_entry_data_fails_integrity_check(self):
        """Altering entry data breaks cryptographic verification."""
        trail = AnalysisAuditTrail(analysis_id="cmp_tamper_1")
        trail.add_entry(AuditStage.SCHEDULE_UPLOADED, {"filename": "clean.pdf"})
        trail.add_entry(AuditStage.PARSER_VERSION, {"parser": "nusf"})
        assert trail.verify_integrity() is True

        # Tamper with first entry
        trail.entries[0].data["filename"] = "corrupted.pdf"
        assert trail.verify_integrity() is False

    def test_tampering_with_hash_chain_fails_integrity_check(self):
        """Breaking the prev_hash pointer fails verification."""
        trail = AnalysisAuditTrail(analysis_id="cmp_tamper_2")
        trail.add_entry(AuditStage.SCHEDULE_UPLOADED, {"filename": "clean.pdf"})
        trail.add_entry(AuditStage.PARSER_VERSION, {"parser": "nusf"})

        trail.entries[1].prev_hash = "FORGED_HASH"
        assert trail.verify_integrity() is False


class TestPastAnalysisReconstruction:
    """AC3: A past analysis can be fully reconstructed from the log."""

    def test_reconstruct_past_analysis_narrative(self):
        """Given a complete audit trail, reconstructs 'Why did Nova say this?'."""
        trail = AnalysisAuditTrail(analysis_id="cmp_kl_2026_08_12", project_id="proj_kl_hospital")

        trail.add_entry(
            AuditStage.SCHEDULE_UPLOADED,
            {"filename": "rev12.pdf", "file_sha256": "abc123def", "filesize_bytes": 1024000},
        )
        trail.add_entry(
            AuditStage.PARSER_VERSION,
            {"parser": "nusf_extractor", "version": "1.4.0", "format": "mspdi_xml"},
        )
        trail.add_entry(
            AuditStage.OCR_PROVIDER,
            {"provider": "azure_document_intelligence", "api_version": "2024-02-29-preview"},
        )
        trail.add_entry(
            AuditStage.CONFIDENCE_RESULTS,
            {"mean_ocr_confidence": 0.96, "critical_fields_verified": 420, "unverified_fields": 2},
        )
        trail.add_entry(
            AuditStage.MATCHES_GENERATED,
            {"matched_activities": 180, "unmatched": 12, "algorithm": "nusf_compare_v2"},
        )
        trail.add_entry(
            AuditStage.MANUAL_CORRECTIONS,
            {"applied_mappings_count": 3, "resolved_review_items": ["item_44", "item_45"]},
        )
        trail.add_entry(
            AuditStage.ANALYSIS_VERSION,
            {"engine": "nusf_compare_engine", "version": "1.0.0", "rules": "ERROR_ONLY"},
        )
        trail.add_entry(
            AuditStage.AGENT_ANSWER,
            {"model": "gpt-4.1", "prompt_version": "v1.2", "headline": "Project delayed by 14 days"},
        )
        trail.add_entry(
            AuditStage.EVIDENCE_USED,
            {
                "critical_path_activities": ["ACT-101", "ACT-105"],
                "root_cause_id": "ACT-101",
                "source_page": 14,
            },
        )

        reconstruction = trail.reconstruct_answer()

        assert reconstruction["analysis_id"] == "cmp_kl_2026_08_12"
        assert reconstruction["audit_trail_intact"] is True
        assert reconstruction["is_complete"] is True
        assert reconstruction["schedule"]["filename"] == "rev12.pdf"
        assert reconstruction["parser"]["version"] == "1.4.0"
        assert reconstruction["ocr"]["provider"] == "azure_document_intelligence"
        assert reconstruction["confidence"]["mean_ocr_confidence"] == 0.96
        assert reconstruction["matching"]["matched_activities"] == 180
        assert len(reconstruction["human_corrections"]["resolved_review_items"]) == 2
        assert reconstruction["analysis_engine"]["version"] == "1.0.0"
        assert reconstruction["agent_response"]["model"] == "gpt-4.1"
        assert reconstruction["evidence"]["root_cause_id"] == "ACT-101"


class TestDoNotRuleRawContentsExcluded:
    """Do-not rule: Do not log raw document contents into the audit trail."""

    def test_sanitize_replaces_raw_bytes_with_hash(self):
        """Raw bytes are replaced with sha256 hash and byte count."""
        raw_pdf = b"%PDF-1.4 minimal binary data content for schedule"
        data = {
            "filename": "huge_schedule.pdf",
            "file_bytes": raw_pdf,
            "metadata": {"author": "KL Planning"},
        }
        sanitized = _sanitize_audit_data(data)

        assert "file_bytes" not in sanitized
        assert "file_bytes_sha256" in sanitized
        assert "file_bytes_size_bytes" in sanitized
        assert sanitized["file_bytes_size_bytes"] == len(raw_pdf)
        assert sanitized["filename"] == "huge_schedule.pdf"

    def test_sanitize_never_stores_large_file_strings(self):
        """Large raw text dumps in file_data keys are converted to hashes."""
        data = {
            "file_data": "A" * 2000,
            "title": "Clean Title",
        }
        sanitized = _sanitize_audit_data(data)
        assert "file_data" not in sanitized
        assert "file_data_sha256" in sanitized
        assert sanitized["title"] == "Clean Title"


class TestAuditStoreScoping:
    """Retention and tenant scoping consistent with the rest of the system."""

    def test_audit_store_scopes_by_project_and_company(self):
        """AuditStore retrieves trails filtered strictly by project and company."""
        store = AuditStore()
        t1 = store.get_or_create("cmp_1", project_id="proj_A", company_id="comp_1")
        t2 = store.get_or_create("cmp_2", project_id="proj_A", company_id="comp_1")
        t3 = store.get_or_create("cmp_3", project_id="proj_B", company_id="comp_2")

        t1.add_entry(AuditStage.SCHEDULE_UPLOADED, {"fn": "1.pdf"})
        t2.add_entry(AuditStage.SCHEDULE_UPLOADED, {"fn": "2.pdf"})
        t3.add_entry(AuditStage.SCHEDULE_UPLOADED, {"fn": "3.pdf"})

        assert len(store.list_by_project("proj_A")) == 2
        assert len(store.list_by_project("proj_B")) == 1
        assert len(store.list_by_company("comp_1")) == 2
        assert len(store.list_by_company("comp_2")) == 1
