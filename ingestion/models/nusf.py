from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
import uuid


class DependencyType(str, Enum):
    FS = "FS"
    SS = "SS"
    FF = "FF"
    SF = "SF"


class ActivityType(str, Enum):
    TASK = "TASK"
    SUMMARY = "SUMMARY"
    MILESTONE = "MILESTONE"
    LOE = "LOE"


class Provenance(BaseModel):
    source_field: str = Field(..., description="Original raw column header or field name")
    source_row: Optional[int] = Field(None, description="Zero-indexed row number from raw extraction")
    is_ai_inferred: bool = Field(False, description="Flag indicating if the field required AI extraction fallback")
    column_mapping_confidence: float = Field(
        1.0, ge=0.0, le=1.0,
        description=(
            "Confidence score for header/column recognition mapping. "
            "Disambiguated in TL-1.6 from value-level OCR confidence (ocr_confidence)."
        )
    )

    # --- TL-1.1: extended evidence fields (additive, D3). All optional with
    # safe defaults so existing construction sites remain valid. See
    # changes/trust-layer/plan/phase-1-provenance.md (TL-1.1) and ADR-009.
    # ---
    raw_value: Optional[str] = Field(
        None,
        description=(
            "Exactly what was read from the source, before any normalization. "
            "For OCR-derived fields this is the cell text before date/number parsing."
        ),
    )
    normalized_value: Optional[str] = Field(
        None,
        description=(
            "What the raw value was turned into by normalization (date parsing, "
            "number cleanup, etc.). `None` when normalization was a no-op."
        ),
    )
    ocr_confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description=(
            "Per-cell OCR confidence for the originating cell, derived in TL-1.2 "
            "as the *minimum* of the constituent word confidences (not the mean — "
            "a single misread digit in a date ruins the field). `None` is a load-"
            "bearing sentinel meaning 'not OCR-derived'; it must never be coerced "
            "to 1.0 or any other default. The brief's Do-not rule for TL-1.2 makes "
            "the 'unknown = 1.0' failure mode the worst possible outcome."
        ),
    )
    page_number: Optional[int] = Field(
        None,
        ge=1,
        description=(
            "Page number in the source document where the originating cell was "
            "read. `None` when not OCR-derived or when page information was not "
            "captured."
        ),
    )
    bounding_box: Optional[list] = Field(
        None,
        description=(
            "Polygon coordinates for the originating cell as a flat list of "
            "floats (Azure's `boundingRegions[].polygon` shape). `None` when not "
            "OCR-derived or when geometry was not captured."
        ),
    )
    source_document: Optional[str] = Field(
        None,
        description=(
            "Original filename or URI of the source document the value was read "
            "from. `None` when not captured (legacy paths pre-TL-1.1)."
        ),
    )
    extraction_method: str = Field(
        "unknown",
        description=(
            "How this value was obtained. Canonical values: `ocr_table`, "
            "`ocr_text_layer`, `csv_cell`, `excel_cell`, `mpp_field`, "
            "`mspdi_field`, `ai_inferred`, `derived`. `unknown` means the field "
            "has not yet been classified — TL-1.5 will retire the catch-all "
            "fallback path that produces it."
        ),
    )


class Activity(BaseModel):
    internal_id: str = Field(..., description="Stable, globally unique ID (derived UUID) — internal handle, never displayed")
    source_id: Optional[str] = Field(None, description="Unchanged native ID from original format, or None if no ID column existed in source")
    stable_key: Optional[str] = Field(None, description="Stable comparison key for old/new matching")
    match_key: Optional[str] = Field(None, description="Internal join key, may be composite, NEVER displayed")
    match_method: Optional[str] = Field(None, description="Method used to establish match identity: verified_source_id, stable_key, name_location_composite, positional")
    name: str = Field(..., description="Activity description/name")

    wbs_code: Optional[str] = Field(None, description="Work Breakdown Structure hierarchical identifier")
    wbs_level: int = Field(0, ge=0, description="WBS hierarchy depth (0 is root)")
    parent_id: Optional[str] = Field(None, description="Internal ID of the parent activity")

    planned_start: datetime = Field(..., description="Scheduled or baseline start timestamp")
    planned_finish: datetime = Field(..., description="Scheduled or baseline finish timestamp")
    actual_start: Optional[datetime] = Field(None, description="Actual start timestamp")
    actual_finish: Optional[datetime] = Field(None, description="Actual finish timestamp")
    duration_hours: int = Field(..., ge=0, description="Duration in standard working hours")

    percent_complete: float = Field(0.0, ge=0.0, le=100.0, description="Percentage completion [0.0 - 100.0]")
    activity_type: ActivityType = Field(ActivityType.TASK, description="Operational classification of active node")

    discipline: Optional[str] = Field(None, description="Department, trade, or discipline tag")
    location_path: Optional[str] = Field(None, description="Original location hierarchy/path when provided")
    area: Optional[str] = Field(None, description="Normalized dashboard area/group")
    floor: Optional[str] = Field(None, description="Normalized dashboard floor/level")
    phase: Optional[str] = Field(None, description="Project phase or segment")
    is_late: Optional[bool] = Field(None, description="Source late/behind flag where available")
    inspected_status: Optional[str] = Field(None, description="Source inspection/completion status where available")
    critical_flag: Optional[bool] = Field(None, description="Source critical path flag where available")
    total_float: Optional[float] = Field(None, description="Source total float/slack in days where available")

    predecessors: List[str] = Field(default_factory=list, description="Array of predecessor internal_ids")
    successors: List[str] = Field(default_factory=list, description="Array of successor internal_ids")

    has_logic_warning: bool = Field(False, description="True if validation anomalies are associated")
    warning_messages: List[str] = Field(default_factory=list, description="Descriptions of semantic validation failures")

    provenance: Dict[str, Provenance] = Field(..., description="Field-to-provenance mapping dictionary")


class Relationship(BaseModel):
    predecessor_id: str = Field(..., description="Internal ID of predecessor activity")
    successor_id: str = Field(..., description="Internal ID of successor activity")
    lag_hours: int = Field(0, description="Offset lag in hours (can be negative)")
    type: DependencyType = Field(DependencyType.FS, description="Dependency link sequence type")
    is_broken: bool = Field(False, description="Flag indicating invalid, unlinked, or circular paths")
    is_ai_inferred: bool = Field(False, description="True if relationship was derived using AI mapping")


class ValidationIssue(BaseModel):
    level: str = Field(..., description="Severity classification: ERROR | WARNING | INFO")
    category: str = Field(..., description="Anomaly classification: STRUCTURAL | LOGICAL | QUALITY")
    activity_id: Optional[str] = Field(None, description="Associated Activity internal_id (if applicable)")
    message: str = Field(..., description="Detailed issue summary and diagnostic description")
    remediation: Optional[str] = Field(None, description="Actionable suggestion to resolve validation error")


class ScheduleMetadata(BaseModel):
    nusf_version: str = Field("2.0", description="Target schema iteration version")
    parser_version: str = Field("nusf-pipeline-v2.1", description="Parser engine version used for extraction")
    project_name: str = Field(..., description="Extracted project title")
    source_system: str = Field(..., description="Original platform, e.g. PDF | CSV")
    source_filename: str = Field(..., description="Native filename uploaded")
    data_date: datetime = Field(..., description="Schedule data reporting cut-off date")

    total_activities: int = Field(..., ge=0)
    total_relationships: int = Field(..., ge=0)
    earliest_date: datetime = Field(..., description="Min date boundary")
    latest_date: datetime = Field(..., description="Max date boundary")
    duration_days: int = Field(..., ge=0, description="Overall duration calculated from min/max dates")

    parse_quality_score: float = Field(..., ge=0.0, le=1.0, description="Ratio of successfully mapped fields")
    parse_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Pipeline processing date")
    parse_duration_seconds: float = Field(0.0, description="Runtime duration of pipeline processing")


class NormalizedSchedule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Ingested schedule instance UUID")
    metadata: ScheduleMetadata = Field(..., description="Metadata and overall schedule attributes")
    activities: List[Activity] = Field(..., description="Parsed and normalized activity listing")
    relationships: List[Relationship] = Field(..., description="Parsed dependency networks")
    validation_issues: List[ValidationIssue] = Field(default_factory=list, description="Validation issues caught")
    validation_passed: bool = Field(..., description="Passed threshold requirements flag")
