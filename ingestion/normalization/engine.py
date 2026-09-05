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
import re
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


def _truthy(raw: str) -> Optional[bool]:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value in ("true", "1", "yes", "ja", "y"):
        return True
    if value in ("false", "0", "no", "nej", "n"):
        return False
    return None


def _stable_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _split_location_path(value: str) -> List[str]:
    return [part.strip() for part in re.split(r"\s*/\s*", str(value or "")) if part.strip()]


def _floor_from_path_part(part: str) -> str:
    value = str(part or "").strip()
    lower = value.lower()
    if not value:
        return ""
    if lower in ("st.", "st", "stue"):
        return "Ground Floor"
    if "kælder" in lower or "kaelder" in lower or "basement" in lower:
        match = re.search(r"-\s*(\d+)", value)
        return f"Basement -{match.group(1)}" if match else "Basement"
    match = re.fullmatch(r"(\d+)\.", value)
    if match:
        return f"{match.group(1)}. Floor"
    match = re.search(r"\b(\d+)\.\s*sal\b", value, re.I)
    if match:
        return f"{match.group(1)}. Floor"
    return ""


def _has_cell_evidence(cells, headers: List[str], row_idx: int,
                        col_name: Optional[str]) -> bool:
    """True iff a non-None cell exists at `(row_idx, col_name)` in `cells`.

    `FieldMapper.get()` returns the static YAML column mapping even
    when the column does not appear in the data's `headers` (e.g.
    `duration → "Varighed"` in `pdf.yaml`). Without this check, the
    engine would treat a column that doesn't actually exist in the
    source as "mapped" and emit a Provenance with `extraction_method`
    `"unknown"` — the worst of both worlds (looks like real
    provenance, isn't). This helper says "if the cell is missing,
    fall through to the derived/omitted path".

    Defined at module level so the closure does not get recreated
    per loop iteration.
    """
    if not col_name or not cells or col_name not in headers:
        return False
    try:
        col_idx = headers.index(col_name)
        if row_idx < len(cells) and col_idx < len(cells[row_idx]):
            return cells[row_idx][col_idx] is not None
    except ValueError:
        pass
    return False


def _build_field_provenance(
    field_col: Optional[str],
    row_idx: int,
    raw_value,
    normalized_value,
    recognition: "RecognitionResult",
    cells,
    headers: List[str],
    filename: str,
    *,
    default_extraction_method: str = "unknown",
    source_field_override: Optional[str] = None,
):
    """Build Provenance for `field_col` at `row_idx`.

    TL-1.4 + TL-1.5: if `cells` is available and contains a non-None
    cell at `(row_idx, col_idx)` for `field_col`, the resulting
    Provenance carries the full TL-1.1 / TL-1.2 evidence set
    (raw/normalized values, OCR confidence, page number, bounding
    box, source document, extraction method). Otherwise the legacy
    four-field shape is returned (with `raw_value` and
    `normalized_value` populated so AC2 is always satisfiable).

    `default_extraction_method` is used in the no-cell fallback
    branch — TL-1.5 derives fields like `duration_hours` (from a
    date delta) and `area` / `floor` / `phase` (from a parsed
    `location_path`) and needs those fields marked
    `extraction_method="derived"` so downstream consumers can
    distinguish "read from source" from "computed by Nova".

    `source_field_override` substitutes for `field_col` in the
    fallback branch — for derived fields with no source column,
    `field_col=None` and we still need a meaningful
    `source_field` value (e.g. "computed_from_location_path")
    rather than an empty string.

    The legacy path is silent — never throws, never fabricates an
    OCR confidence. Defined at module level so the closure does
    not get recreated per loop iteration inside
    `NormalizeEngine.normalize()`.
    """
    cell: Optional[Dict] = None
    if cells is not None and field_col is not None and field_col in headers:
        try:
            col_idx = headers.index(field_col)
            if row_idx < len(cells) and col_idx < len(cells[row_idx]):
                cell = cells[row_idx][col_idx]
        except ValueError:
            cell = None

    if cell is not None:
        return Provenance(
            source_field=field_col or "",
            source_row=row_idx,
            is_ai_inferred=recognition.ai_needed,
            column_mapping_confidence=recognition.confidence,
            raw_value=raw_value,
            normalized_value=normalized_value,
            ocr_confidence=cell.get("ocr_confidence"),
            page_number=cell.get("page_number"),
            bounding_box=cell.get("bounding_box"),
            source_document=cell.get("source_document", filename),
            extraction_method=cell.get("extraction_method", "unknown"),
        )
    # Fallback — no cell, or column unmapped, or cell position
    # is empty. TL-1.5: callers can mark derived fields via
    # `default_extraction_method="derived"`. Legacy callers (no
    # derived support) pass through with the default `"unknown"`.
    return Provenance(
        source_field=source_field_override or field_col or "",
        source_row=row_idx,
        is_ai_inferred=recognition.ai_needed,
        column_mapping_confidence=recognition.confidence,
        raw_value=raw_value,
        normalized_value=normalized_value,
        ocr_confidence=None,
        page_number=None,
        bounding_box=None,
        source_document=filename if not cell else None,
        extraction_method=default_extraction_method,
    )


def _location_parts(location_path: str, area_raw: str = "", floor_raw: str = "") -> tuple[str, str, str]:
    parts = _split_location_path(location_path)
    area = _stable_text(area_raw)
    floor = _stable_text(floor_raw)
    phase = ""

    if parts:
        area = area or (parts[1] if len(parts) > 1 else "")
        for part in reversed(parts[1:]):
            floor = floor or _floor_from_path_part(part)
            if floor:
                break
        for part in parts[2:]:
            if _floor_from_path_part(part):
                continue
            phase = part
            break

    return area, floor, phase


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
        # TL-1.4: per-cell provenance threaded through from the
        # extractors (`ingestion/extractors/pdf.py`). The cells are a
        # parallel 2D grid (`cells[row_idx][col_idx]` → cell dict or
        # `None`); the dict carries the TL-1.2 evidence fields
        # (`ocr_confidence`, `page_number`, `bounding_box`) plus
        # `extraction_method`. `None` is the load-bearing sentinel
        # meaning "no cell at this position" (ADR-009 / ADR-010).
        # When `cells` is absent (non-OCR sources pre-TL-1.9, or
        # legacy data), the Provenance construction falls back to the
        # pre-TL-1.4 four-field shape — no throw, no fabricated
        # evidence.
        cells = extracted.get("cells")

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
        is_late_col = mapper.get("is_late")
        inspected_col = mapper.get("inspected_type")
        critical_col = mapper.get("critical_flag")
        total_float_col = mapper.get("total_float")

        effective_id_col = entydigt_col or id_col
        if recognition.match_key == "tbs" and wbs_col:
            effective_id_col = wbs_col

        activities: List[Activity] = []
        source_id_to_internal: Dict[str, str] = {}
        raw_predecessors: Dict[str, str] = {}
        raw_successors: Dict[str, str] = {}

        min_date: Optional[datetime] = None
        max_date: Optional[datetime] = None

        _skip_empty = 0
        _skip_no_date = 0
        _skip_partial_date = 0

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

            if not planned_start or not planned_finish:
                # Exactly one of start/finish is missing here (both-missing was
                # already skipped above). Previously this silently set the
                # missing date equal to the one present, producing a false
                # start == finish (zero-duration, "complete") activity. Skip
                # instead of fabricating a date the source data doesn't have.
                _skip_partial_date += 1
                logger.debug(
                    f"[{filename}] Row {row_idx} skipped — only one of start/finish present "
                    f"(start={raw_start!r}, finish={raw_finish!r}, name={raw_name[:40]!r})"
                )
                continue

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

            raw_source_id_val = _get_val(row, headers, effective_id_col)
            raw_source_id = raw_source_id_val.strip() if raw_source_id_val and raw_source_id_val.strip() else None
            raw_location_path = _get_val(row, headers, area_col)

            id_is_durable = recognition.match_key in ("entydigt_id", "tbs")
            if recognition.match_key == "name_location":
                stable_key = f"{_stable_text(raw_name)} | {_stable_text(raw_location_path)}"
            else:
                stable_key = raw_source_id if (id_is_durable and raw_source_id) else ""

            if raw_source_id and id_is_durable:
                act_match_key = raw_source_id
                act_match_method = "verified_source_id"
            elif stable_key:
                act_match_key = stable_key
                act_match_method = "name_location_composite" if recognition.match_key == "name_location" else "stable_key"
            else:
                act_match_key = f"{_stable_text(raw_name)} | {_stable_text(raw_location_path)}"
                act_match_method = "positional" if recognition.match_key in ("id", "row_index") else "name_location_composite"

            raw_wbs = _get_val(row, headers, wbs_col)
            raw_disc = _get_val(row, headers, disc_col)
            raw_area = raw_location_path
            raw_floor = _get_val(row, headers, floor_col)
            area, floor, phase = _location_parts(raw_location_path, raw_area if recognition.match_key != "name_location" else "", raw_floor)

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
            is_late = _truthy(_get_val(row, headers, is_late_col)) if is_late_col else None
            inspected_status = _get_val(row, headers, inspected_col) if inspected_col else None
            critical_flag = _truthy(_get_val(row, headers, critical_col)) if critical_col else None
            raw_float = _get_val(row, headers, total_float_col) if total_float_col else ""
            try:
                total_float = float(str(raw_float).replace(",", ".")) if raw_float else None
            except ValueError:
                total_float = None

            internal_id = str(uuid.uuid4())

            provenance: Dict[str, Provenance] = {}
            # TL-1.5: every critical field gets a Provenance entry
            # built from its originating cell (when one exists), or
            # marked `extraction_method="derived"` when the value was
            # computed by Nova rather than read. Secondary fields
            # follow the same rule but only when the source data
            # carries the value. The legacy `_row` fallback is
            # preserved as a last resort, marked
            # `extraction_method="unknown"` so it cannot be confused
            # with real provenance. Every Provenance carries
            # `raw_value` / `normalized_value` so the pre- vs post-
            # normalization distinction (AC2) is always visible.
            # Note: `row_idx` is NOT in this dict — every call site
            # below passes it positionally to keep the helper's
            # positional contract (field_col, row_idx, raw_value,
            # normalized_value, ...) intact.
            common_kwargs = {
                "recognition": recognition,
                "cells": cells, "headers": headers, "filename": filename,
            }

            # --- Critical fields (brief §6) ---

            # 1. source_id (verbatim from document, or None if no ID column existed).
            if raw_source_id is not None and effective_id_col:
                provenance["source_id"] = _build_field_provenance(
                    effective_id_col, row_idx,
                    raw_value=raw_source_id,
                    normalized_value=raw_source_id,
                    **common_kwargs,
                )
            else:
                provenance["source_id"] = _build_field_provenance(
                    None, row_idx,
                    raw_value=None,
                    normalized_value=None,
                    default_extraction_method="derived",
                    source_field_override="unverified",
                    **common_kwargs,
                )

            # 2. name (read).
            if name_col:
                provenance["name"] = _build_field_provenance(
                    name_col, row_idx,
                    raw_value=raw_name, normalized_value=raw_name,
                    **common_kwargs,
                )

            # 3. planned_start (read + parsed).
            if start_col:
                provenance["planned_start"] = _build_field_provenance(
                    start_col, row_idx,
                    raw_value=raw_start,
                    normalized_value=(
                        planned_start.isoformat() if planned_start else None
                    ),
                    **common_kwargs,
                )

            # 4. planned_finish (read + parsed).
            if finish_col:
                provenance["planned_finish"] = _build_field_provenance(
                    finish_col, row_idx,
                    raw_value=raw_finish,
                    normalized_value=(
                        planned_finish.isoformat() if planned_finish else None
                    ),
                    **common_kwargs,
                )

            # 5. duration_hours. Read from `dur_col` when present;
            # when the source value is 0/empty and a non-zero
            # duration was *derived* from the planned start/finish
            # delta (engine.py:306–308), the Provenance marks it
            # `extraction_method="derived"` so downstream consumers
            # can distinguish "read from source" from "computed by
            # Nova" (ADR-013). Without this distinction a trust
            # layer downstream would have no way to know whether
            # the duration is sourced or computed.
            #
            # `_has_cell_evidence` is checked first because the
            # static YAML config can map `duration → "Varighed"`
            # even when the source data does not actually carry a
            # Varighed column. Without this check, `dur_col` would
            # be truthy and the engine would emit a Provenance with
            # `extraction_method="unknown"` for a field that was
            # never actually read.
            if _has_cell_evidence(cells, headers, row_idx, dur_col):
                provenance["duration_hours"] = _build_field_provenance(
                    dur_col, row_idx,
                    raw_value=raw_dur, normalized_value=str(duration_hours),
                    **common_kwargs,
                )
            elif duration_hours > 0:
                provenance["duration_hours"] = _build_field_provenance(
                    None, row_idx,
                    raw_value=(
                        f"start={planned_start.isoformat()},"
                        f"finish={planned_finish.isoformat()}"
                    ),
                    normalized_value=str(duration_hours),
                    default_extraction_method="derived",
                    source_field_override="computed_from_planned_start_finish",
                    **common_kwargs,
                )

            # 6. percent_complete (read + parsed by `_pct_to_float`).
            # AC1: always emit a Provenance entry for this critical field
            # when the column is mapped, even on the legacy path
            # (cells=None). `_build_field_provenance` handles the
            # cell-vs-no-cell distinction and emits `ocr_confidence=None`
            # in the fallback — that is the correct honest encoding for
            # "not OCR-derived" per ADR-009 / ADR-010.
            if pct_col:
                provenance["percent_complete"] = _build_field_provenance(
                    pct_col, row_idx,
                    raw_value=raw_pct, normalized_value=str(pct),
                    **common_kwargs,
                )

            # --- Secondary fields (brief §6) ---

            # 7. location_path (read from area column).
            if _has_cell_evidence(cells, headers, row_idx, area_col) and raw_location_path:
                provenance["location_path"] = _build_field_provenance(
                    area_col, row_idx,
                    raw_value=raw_location_path,
                    normalized_value=raw_location_path,
                    **common_kwargs,
                )

            # 8. area. Read from `area_col` if it had a real value;
            # otherwise derived from `location_path` via `_location_parts`.
            if _has_cell_evidence(cells, headers, row_idx, area_col) and area:
                provenance["area"] = _build_field_provenance(
                    area_col, row_idx,
                    raw_value=raw_location_path,
                    normalized_value=area,
                    **common_kwargs,
                )
            elif area:
                provenance["area"] = _build_field_provenance(
                    None, row_idx,
                    raw_value=raw_location_path,
                    normalized_value=area,
                    default_extraction_method="derived",
                    source_field_override="computed_from_location_path",
                    **common_kwargs,
                )

            # 9. floor. Read from `floor_col`; else derived.
            if _has_cell_evidence(cells, headers, row_idx, floor_col) and floor:
                provenance["floor"] = _build_field_provenance(
                    floor_col, row_idx,
                    raw_value=raw_floor,
                    normalized_value=floor,
                    **common_kwargs,
                )
            elif floor:
                provenance["floor"] = _build_field_provenance(
                    None, row_idx,
                    raw_value=raw_location_path,
                    normalized_value=floor,
                    default_extraction_method="derived",
                    source_field_override="computed_from_location_path",
                    **common_kwargs,
                )

            # 10. phase. Always derived from `location_path`
            # (no direct column source in the current schema).
            if phase:
                provenance["phase"] = _build_field_provenance(
                    None, row_idx,
                    raw_value=raw_location_path,
                    normalized_value=phase,
                    default_extraction_method="derived",
                    source_field_override="computed_from_location_path",
                    **common_kwargs,
                )

            # 11. discipline. Read from `disc_col` if it carried a
            # value; else derived from area/floor (the
            # engine.py:336–345 fallback chain). The
            # `source_field_override` says "we computed this from
            # area/floor" so the derived provenance reads true.
            if _has_cell_evidence(cells, headers, row_idx, disc_col) and discipline:
                provenance["discipline"] = _build_field_provenance(
                    disc_col, row_idx,
                    raw_value=raw_disc,
                    normalized_value=discipline,
                    **common_kwargs,
                )
            elif discipline:
                disc_raw = raw_disc or (
                    f"floor={raw_floor},area={raw_area}"
                    if (raw_floor or raw_area)
                    else None
                )
                if disc_raw:
                    provenance["discipline"] = _build_field_provenance(
                        area_col or floor_col, row_idx,
                        raw_value=disc_raw,
                        normalized_value=discipline,
                        default_extraction_method="derived",
                        source_field_override="computed_from_area_floor",
                        **common_kwargs,
                    )

            # 12. critical_flag (read + boolean-parsed).
            if _has_cell_evidence(cells, headers, row_idx, critical_col) and critical_flag is not None:
                provenance["critical_flag"] = _build_field_provenance(
                    critical_col, row_idx,
                    raw_value=str(critical_flag),
                    normalized_value=str(critical_flag),
                    **common_kwargs,
                )

            # 13. total_float (read + float-parsed).
            if _has_cell_evidence(cells, headers, row_idx, total_float_col) and total_float is not None:
                provenance["total_float"] = _build_field_provenance(
                    total_float_col, row_idx,
                    raw_value=raw_float, normalized_value=str(total_float),
                    **common_kwargs,
                )

            # --- Last-resort fallback ---
            # Only emitted when *no* field above produced a
            # Provenance entry — i.e. we know we saw this row but
            # cannot say anything specific about where any value
            # came from. Marked `extraction_method="unknown"` so it
            # cannot be confused with real provenance (ADR-013).
            if not provenance:
                provenance["_row"] = Provenance(
                    source_field=f"row_{row_idx}",
                    source_row=row_idx,
                    is_ai_inferred=False,
                    column_mapping_confidence=1.0,
                    raw_value=None,
                    normalized_value=None,
                    ocr_confidence=None,
                    page_number=None,
                    bounding_box=None,
                    source_document=filename,
                    extraction_method="unknown",
                )

            activity = Activity(
                internal_id=internal_id,
                source_id=raw_source_id,
                stable_key=stable_key,
                match_key=act_match_key,
                match_method=act_match_method,
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
                location_path=raw_location_path or None,
                area=area or None,
                floor=floor or None,
                phase=phase or None,
                is_late=is_late,
                inspected_status=inspected_status or None,
                critical_flag=critical_flag,
                total_float=total_float,
                provenance=provenance,
                has_logic_warning=date_swapped,
                warning_messages=(
                    ["Start/finish dates were inverted in source data and have been auto-corrected."]
                    if date_swapped else []
                ),
            )

            activities.append(activity)
            if raw_source_id:
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
            f"skipped_partial_date={_skip_partial_date}, "
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
      source_id, stable_key, name, planned_start, planned_finish,
      percent_complete, activity_type, wbs_code, discipline, location_path,
      area, floor, phase, duration_hours, actual_start, actual_finish,
      is_late, inspected_status, critical_flag, total_float, predecessors, successors
    """
    NUSF_HEADERS = [
        "source_id", "stable_key", "name", "planned_start", "planned_finish",
        "percent_complete", "activity_type", "wbs_code", "discipline",
        "location_path", "area", "floor", "phase", "duration_hours",
        "actual_start", "actual_finish", "is_late", "inspected_status",
        "critical_flag", "total_float", "predecessors", "successors",
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
                act.source_id or "",
                act.stable_key or "",
                act.name,
                _fmt_dt(act.planned_start),
                _fmt_dt(act.planned_finish),
                str(act.percent_complete),
                act.activity_type.value,
                act.wbs_code or "",
                act.discipline or "",
                act.location_path or "",
                act.area or "",
                act.floor or "",
                act.phase or "",
                str(act.duration_hours),
                _fmt_dt(act.actual_start),
                _fmt_dt(act.actual_finish),
                "" if act.is_late is None else str(bool(act.is_late)).lower(),
                act.inspected_status or "",
                "" if act.critical_flag is None else str(bool(act.critical_flag)).lower(),
                "" if act.total_float is None else str(act.total_float),
                ",".join(act.predecessors),
                ",".join(act.successors),
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
