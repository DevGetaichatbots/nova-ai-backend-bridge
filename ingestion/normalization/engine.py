"""
Normalization Engine
====================
Transforms raw extracted {headers, rows} into a fully typed NormalizedSchedule.

Also provides the bridge function to_compact_csv_chunks() which converts the
original extracted headers and rows into the same compact semicolon-separated
CSV chunk format produced by src/pdf_processor.rows_to_compact_csv_chunks(),
so existing LLM agents consume it unchanged.

Key design decision: the bridge operates on the ORIGINAL extracted headers and
rows (not the NormalizedSchedule objects), preserving column provenance exactly.
"""
from __future__ import annotations
import csv
import io
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from ingestion.models.nusf import (
    Activity, ActivityType, NormalizedSchedule, Provenance,
    Relationship, ScheduleMetadata, ValidationIssue,
)
from ingestion.normalization.dates import parse_date, parse_duration_to_hours
from ingestion.normalization.mappings import FieldMapper
from ingestion.normalization.relationships import build_relationships
from ingestion.recognition.heuristics import RecognitionResult

logger = logging.getLogger(__name__)

_CSV_SEP = ";"
_MAX_CHUNK_ROWS = 250

_SKIP_HEADERS = {"opg", "opgavetilstand"}


def _serialize_row(vals: List[str], sep: str = _CSV_SEP) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=sep, quoting=csv.QUOTE_MINIMAL, lineterminator="")
    writer.writerow(vals)
    return buf.getvalue()


def _get_val(row: List[str], headers: List[str], col_name: Optional[str]) -> str:
    if not col_name:
        return ""
    try:
        idx = headers.index(col_name)
        return row[idx].strip() if idx < len(row) else ""
    except ValueError:
        return ""


def _pct_to_float(raw: str) -> float:
    if not raw:
        return 0.0
    v = raw.strip().rstrip("%").replace(",", ".")
    try:
        return min(100.0, max(0.0, float(v)))
    except ValueError:
        return 0.0


def _detect_activity_type(duration_raw: str, name: str) -> ActivityType:
    dur_lower = duration_raw.strip().lower()
    if dur_lower in ("0d", "0", ""):
        return ActivityType.MILESTONE
    name_lower = name.lower()
    if any(kw in name_lower for kw in ("summary", "phase", "opsummering", "overordnet")):
        return ActivityType.SUMMARY
    return ActivityType.TASK


class NormalizationEngine:
    """
    Converts raw extracted data into NormalizedSchedule (for validation and NUSF model),
    and bridges the original extracted data to compact CSV for LLM agents.
    """

    def normalize(
        self,
        extracted: Dict[str, Any],
        recognition: RecognitionResult,
        source_system: str,
        filename: str,
    ) -> NormalizedSchedule:
        t0 = time.time()
        headers: List[str] = extracted.get("headers", [])
        rows: List[List[str]] = extracted.get("rows", [])

        mapper = FieldMapper(source_system, recognition.column_map)

        name_col = mapper.get("name")
        start_col = mapper.get("planned_start")
        finish_col = mapper.get("planned_finish")
        dur_col = mapper.get("duration")
        pct_col = mapper.get("percent_complete")
        id_col = mapper.get("source_id")
        wbs_col = mapper.get("wbs_code")
        entydigt_col = mapper.get("entydigt_id")
        disc_col = mapper.get("discipline")
        area_col = mapper.get("area")
        floor_col = mapper.get("floor")
        pred_col = mapper.get("predecessors")
        succ_col = mapper.get("successors")
        actual_start_col = mapper.get("actual_start")
        actual_finish_col = mapper.get("actual_finish")
        act_type_col = mapper.get("activity_type")

        effective_id_col = entydigt_col or id_col

        activities: List[Activity] = []
        source_id_to_internal: Dict[str, str] = {}
        raw_predecessors: Dict[str, str] = {}
        raw_successors: Dict[str, str] = {}

        min_date: Optional[datetime] = None
        max_date: Optional[datetime] = None

        _skip_empty = 0
        _skip_no_date = 0

        for row_idx, row in enumerate(rows):
            raw_name = _get_val(row, headers, name_col)
            raw_start = _get_val(row, headers, start_col)
            raw_finish = _get_val(row, headers, finish_col)

            if not raw_name and not raw_start and not raw_finish:
                _skip_empty += 1
                continue

            planned_start = parse_date(raw_start)
            planned_finish = parse_date(raw_finish)

            if not planned_start and not planned_finish:
                _skip_no_date += 1
                logger.debug(
                    f"[{filename}] Row {row_idx} skipped — no parseable dates "
                    f"(start={raw_start!r}, finish={raw_finish!r}, name={raw_name[:40]!r})"
                )
                continue

            if not planned_start:
                planned_start = planned_finish
            if not planned_finish:
                planned_finish = planned_start

            date_swapped = False
            if planned_start > planned_finish:
                planned_start, planned_finish = planned_finish, planned_start
                date_swapped = True

            raw_dur = _get_val(row, headers, dur_col)
            duration_hours = parse_duration_to_hours(raw_dur)
            if duration_hours == 0 and planned_start != planned_finish:
                delta = planned_finish - planned_start
                duration_hours = max(0, int(delta.total_seconds() / 3600))

            raw_pct = _get_val(row, headers, pct_col)
            pct = _pct_to_float(raw_pct)

            raw_source_id = _get_val(row, headers, effective_id_col)
            if not raw_source_id:
                raw_source_id = str(row_idx + 1)

            raw_wbs = _get_val(row, headers, wbs_col)
            raw_disc = _get_val(row, headers, disc_col)
            raw_area = _get_val(row, headers, area_col)
            raw_floor = _get_val(row, headers, floor_col)

            if raw_floor and raw_area:
                discipline = f"{raw_floor} / {raw_area}"
            elif raw_floor:
                discipline = raw_floor
            elif raw_disc:
                discipline = raw_disc
            elif raw_area:
                discipline = raw_area
            else:
                discipline = None

            raw_act_type = _get_val(row, headers, act_type_col)
            act_type = _detect_activity_type(raw_dur, raw_name)
            if raw_act_type:
                if any(kw in raw_act_type.lower() for kw in ("milestone", "milepæl")):
                    act_type = ActivityType.MILESTONE
                elif any(kw in raw_act_type.lower() for kw in ("summary", "overordnet")):
                    act_type = ActivityType.SUMMARY

            actual_start = parse_date(_get_val(row, headers, actual_start_col)) if actual_start_col else None
            actual_finish = parse_date(_get_val(row, headers, actual_finish_col)) if actual_finish_col else None

            internal_id = str(uuid.uuid4())

            provenance: Dict[str, Provenance] = {}
            if name_col:
                provenance["name"] = Provenance(
                    source_field=name_col, source_row=row_idx,
                    is_ai_inferred=recognition.ai_needed,
                    confidence=recognition.confidence,
                )
            if start_col:
                provenance["planned_start"] = Provenance(
                    source_field=start_col, source_row=row_idx,
                    is_ai_inferred=recognition.ai_needed,
                    confidence=recognition.confidence,
                )
            if finish_col:
                provenance["planned_finish"] = Provenance(
                    source_field=finish_col, source_row=row_idx,
                    is_ai_inferred=recognition.ai_needed,
                    confidence=recognition.confidence,
                )
            if not provenance:
                provenance["_row"] = Provenance(
                    source_field=f"row_{row_idx}",
                    source_row=row_idx,
                    is_ai_inferred=False,
                    confidence=1.0,
                )

            activity = Activity(
                internal_id=internal_id,
                source_id=raw_source_id,
                name=raw_name or f"Activity {row_idx + 1}",
                wbs_code=raw_wbs or None,
                wbs_level=raw_wbs.count(".") if raw_wbs else 0,
                planned_start=planned_start,
                planned_finish=planned_finish,
                actual_start=actual_start,
                actual_finish=actual_finish,
                duration_hours=duration_hours,
                percent_complete=pct,
                activity_type=act_type,
                discipline=discipline,
                provenance=provenance,
                has_logic_warning=date_swapped,
                warning_messages=(
                    ["Start/finish dates were inverted in source data and have been auto-corrected."]
                    if date_swapped else []
                ),
            )

            activities.append(activity)
            source_id_to_internal[raw_source_id] = internal_id

            raw_pred = _get_val(row, headers, pred_col) if pred_col else ""
            raw_succ = _get_val(row, headers, succ_col) if succ_col else ""
            if raw_pred:
                raw_predecessors[internal_id] = raw_pred
            if raw_succ:
                raw_successors[internal_id] = raw_succ

            if min_date is None or planned_start < min_date:
                min_date = planned_start
            if max_date is None or planned_finish > max_date:
                max_date = planned_finish

        relationships: List[Relationship] = build_relationships(
            source_id_to_internal, raw_predecessors, raw_successors
        )

        for rel in relationships:
            if not rel.is_broken:
                for act in activities:
                    if act.internal_id == rel.successor_id:
                        if rel.predecessor_id not in act.predecessors:
                            act.predecessors.append(rel.predecessor_id)
                    if act.internal_id == rel.predecessor_id:
                        if rel.successor_id not in act.successors:
                            act.successors.append(rel.successor_id)

        now = datetime.now(tz=timezone.utc)
        min_date = min_date or now
        max_date = max_date or now
        duration_days = max(0, (max_date - min_date).days)

        quality_score = len(activities) / max(len(rows), 1)

        metadata = ScheduleMetadata(
            project_name=filename.rsplit(".", 1)[0],
            source_system=source_system,
            source_filename=filename,
            data_date=now,
            total_activities=len(activities),
            total_relationships=len(relationships),
            earliest_date=min_date,
            latest_date=max_date,
            duration_days=duration_days,
            parse_quality_score=round(min(1.0, quality_score), 4),
            parse_duration_seconds=round(time.time() - t0, 3),
        )

        schedule = NormalizedSchedule(
            metadata=metadata,
            activities=activities,
            relationships=relationships,
            validation_issues=[],
            validation_passed=True,
        )

        swapped = sum(1 for a in activities if a.has_logic_warning)
        logger.info(
            f"[{filename}] Normalized: {len(activities)} activities, "
            f"{len(relationships)} relationships, "
            f"skipped_empty={_skip_empty}, skipped_no_date={_skip_no_date}, "
            f"date_swaps={swapped}, "
            f"quality={quality_score:.2f}, "
            f"elapsed={metadata.parse_duration_seconds}s"
        )

        return schedule

    def to_compact_csv_chunks(
        self,
        headers: List[str],
        data_rows: List[List[str]],
        source: str,
    ) -> List[Dict[str, Any]]:
        """
        Bridge: converts original extracted headers and rows to compact semicolon-separated
        CSV chunks. Output format is IDENTICAL to src/pdf_processor.rows_to_compact_csv_chunks()
        so the existing vector store and LLM agents consume it unchanged.

        Filters out skip-only headers (opg, opgavetilstand) as the production function does.
        Preserves ALL remaining original columns, including schedule-specific ones.
        """
        if not headers or not data_rows:
            return []

        display_headers = [h for h in headers if h.strip().lower() not in _SKIP_HEADERS]
        keep_indices = [i for i, h in enumerate(headers) if h.strip().lower() not in _SKIP_HEADERS]

        header_line = _serialize_row(display_headers)

        chunks = []
        total_stored = 0
        for batch_start in range(0, len(data_rows), _MAX_CHUNK_ROWS):
            batch = data_rows[batch_start: batch_start + _MAX_CHUNK_ROWS]
            compact_lines = []
            for row in batch:
                vals = [row[idx].strip() if idx < len(row) else "" for idx in keep_indices]
                compact_lines.append(_serialize_row(vals))

            if compact_lines:
                content = (
                    "FORMAT: CSV — each row = one activity. "
                    "Columns separated by semicolon (values with semicolons are quoted).\n"
                    f"{header_line}\n"
                    + "\n".join(compact_lines)
                )
                part_num = batch_start // _MAX_CHUNK_ROWS + 1
                total_stored += len(compact_lines)
                chunks.append({
                    "content": content,
                    "metadata": {
                        "type": "table",
                        "source": source,
                        "part": part_num,
                        "row_count": len(compact_lines),
                    },
                })

        logger.info(
            f"[{source}] Bridge: {len(chunks)} chunks, "
            f"{total_stored}/{len(data_rows)} rows, "
            f"{len(display_headers)} columns"
        )
        return chunks


def to_nusf_chunks(schedule: NormalizedSchedule) -> List[Dict[str, Any]]:
    """
    Serialize a NormalizedSchedule into compact semicolon-separated CSV chunks
    using fixed NUSF field names. Used exclusively by v2 endpoints so the LLM
    receives format-agnostic, pre-normalized data regardless of source format.

    Fields emitted (always in this order):
      source_id, name, planned_start, planned_finish, percent_complete,
      activity_type, wbs_code, discipline, duration_hours, actual_start, actual_finish
    """
    NUSF_HEADERS = [
        "source_id", "name", "planned_start", "planned_finish",
        "percent_complete", "activity_type", "wbs_code", "discipline",
        "duration_hours", "actual_start", "actual_finish",
    ]

    def _fmt_dt(dt) -> str:
        return dt.strftime("%d-%m-%Y") if dt else ""

    activities = schedule.activities
    source = schedule.metadata.source_filename
    header_line = _serialize_row(NUSF_HEADERS)

    chunks = []
    total_stored = 0
    for batch_start in range(0, len(activities), _MAX_CHUNK_ROWS):
        batch = activities[batch_start: batch_start + _MAX_CHUNK_ROWS]
        compact_lines = []
        for act in batch:
            compact_lines.append(_serialize_row([
                act.source_id,
                act.name,
                _fmt_dt(act.planned_start),
                _fmt_dt(act.planned_finish),
                str(act.percent_complete),
                act.activity_type.value,
                act.wbs_code or "",
                act.discipline or "",
                str(act.duration_hours),
                _fmt_dt(act.actual_start),
                _fmt_dt(act.actual_finish),
            ]))

        if compact_lines:
            content = (
                "FORMAT: NUSF CSV — each row = one activity. "
                "Columns separated by semicolon. Fields are pre-normalized.\n"
                f"{header_line}\n"
                + "\n".join(compact_lines)
            )
            part_num = batch_start // _MAX_CHUNK_ROWS + 1
            total_stored += len(compact_lines)
            chunks.append({
                "content": content,
                "metadata": {
                    "type": "table",
                    "source": source,
                    "part": part_num,
                    "row_count": len(compact_lines),
                    "format": "nusf",
                },
            })

    logger.info(
        f"[{source}] NUSF chunks: {len(chunks)} chunks, {total_stored} activities"
    )
    return chunks
