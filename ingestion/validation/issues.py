"""
Validation Issue Classifications
=================================
Constants and factory helpers for the 4 core validation rules.
"""
from ingestion.models.nusf import ValidationIssue

LEVEL_ERROR = "ERROR"
LEVEL_WARNING = "WARNING"
LEVEL_INFO = "INFO"

CAT_STRUCTURAL = "STRUCTURAL"
CAT_LOGICAL = "LOGICAL"
CAT_QUALITY = "QUALITY"


def rule_101_date_logic(activity_id: str, start: str, finish: str) -> ValidationIssue:
    return ValidationIssue(
        level=LEVEL_WARNING,
        category=CAT_STRUCTURAL,
        activity_id=activity_id,
        message=f"Rule 101: planned_start ({start}) > planned_finish ({finish}). Dates were auto-corrected by swapping.",
        remediation="Verify start/finish date columns in source file are not transposed.",
    )


def rule_102_circular(activity_ids: list) -> ValidationIssue:
    ids_str = " → ".join(activity_ids)
    return ValidationIssue(
        level=LEVEL_WARNING,
        category=CAT_LOGICAL,
        activity_id=activity_ids[0] if activity_ids else None,
        message=f"Rule 102: Circular dependency detected: {ids_str}",
        remediation="Remove or redirect one of the dependency links that creates this cycle.",
    )


def rule_103_dangling(relationship_desc: str, missing_id: str) -> ValidationIssue:
    return ValidationIssue(
        level=LEVEL_WARNING,
        category=CAT_STRUCTURAL,
        activity_id=None,
        message=f"Rule 103: Dangling reference — {relationship_desc} references unknown activity '{missing_id}'.",
        remediation="Verify that the referenced activity exists in the schedule or remove the link.",
    )


def rule_104_out_of_sequence(activity_id: str, task_name: str) -> ValidationIssue:
    return ValidationIssue(
        level=LEVEL_WARNING,
        category=CAT_QUALITY,
        activity_id=activity_id,
        message=(
            f"Rule 104: Activity '{task_name}' (id={activity_id}) has "
            f"percent_complete > 0 but no actual_start date recorded."
        ),
        remediation="Record an actual_start date for this in-progress activity.",
    )
