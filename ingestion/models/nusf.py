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
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence metric for parsed values")


class Activity(BaseModel):
    internal_id: str = Field(..., description="Stable, globally unique ID (derived UUID)")
    source_id: str = Field(..., description="Unchanged native ID from original format")
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
    phase: Optional[str] = Field(None, description="Project phase or segment")

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
    nusf_version: str = Field("1.0", description="Target schema iteration version")
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
