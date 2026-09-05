from __future__ import annotations

import csv
import io
import logging
import re
from collections import defaultdict
from datetime import date, datetime
from statistics import mean, median
from typing import Any, Callable, Optional

from src.trust.match_mapping import VerifiedMapping
from src.trust.matching import MatchLevel, MatchResult, to_trust_state

# Brief §41 versioning: matching algorithm and comparison engine dimensions (TL-9.3)
MATCHING_ALGORITHM_VERSION = "nusf-matcher-v3.2"
ANALYSIS_ENGINE_VERSION = "nusf-compare-engine-v1.4"

logger = logging.getLogger(__name__)
logger.info("[nusf_compare_engine] module loaded — IDENTITY_FIX_2026_07_27 (stable-id detection, name+date fallback, dashboard identity_label) active")


_STABLE_ID_HEADERS = {"entydigt id", "entydigt_id", "unique id", "unique_id", "unique task id"}
_POSITIONAL_ID_HEADERS = {"id", "d i", "source_id"}


def _norm_header(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in _STABLE_ID_HEADERS or raw in _POSITIONAL_ID_HEADERS:
        return "source_id"
    if raw in ("opgavenavn", "opg.navn", "task name", "name", "opgavenavn/aktivitet"):
        return "name"
    if "slutdato" in raw or "planned_finish" in raw or ("finish" in raw and "actual" not in raw) or "end date" in raw: 
        return "planned_finish"
    if "startdato" in raw or "planned_start" in raw or ("start" in raw and "actual" not in raw): 
        return "planned_start"
    if "varighed" in raw or "duration" in raw: 
        return "duration_hours"
    if "%" in raw or "færdigt" in raw or "erdigt" in raw or "complete" in raw: 
        return "percent_complete"
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")


def _norm_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _parse_bool(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "ja"}


def _parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value or "").replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


_DURATION_NUM_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)")


def _parse_duration_days(value: Any) -> float:
    """Parse a duration cell into a day-equivalent float.

    Duration text may carry a unit suffix produced by the MPP/MSPDI
    extractors ("73.0d", "5.0w", "160.0h") or be a bare number from a PDF
    table (assumed to already be in days, matching the convention used
    throughout Nova for an unsuffixed duration). Feeding a suffixed value
    straight into ``_parse_float`` fails (the trailing letter is not
    numeric) and silently returns 0.0 for both sides, so a genuine duration
    change on an MPP/MSPDI-sourced schedule was never detected at all.
    Comparing "5.0w" against "35.0d" as raw floats (5 vs 35) would also
    wrongly register as a large change even though they are equal. Both
    problems are avoided by normalising to days here (8 working hours/day,
    5 working days/week - matching ingestion.extractors.mpp._duration_to_days
    and version_1_0.diffs._parse_duration_days).
    """
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    normalized = raw.replace(",", ".")
    m = _DURATION_NUM_RE.search(normalized)
    if not m:
        return 0.0
    amount = _parse_float(m.group(1))
    unit = normalized[m.end():].strip().lower()
    if unit.startswith("w") or unit.startswith("u"):  # week / uge
        return amount * 5.0
    if unit.startswith("h") or unit.startswith("t"):  # hour / time
        return amount / 8.0
    return amount  # "d", "dage", trailing junk, or no suffix - already days


def _parse_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.split(" ")[-1]
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%y", "%y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_date_from_text(value: Any) -> date | None:
    raw = str(value or "")
    patterns = [
        r"\b(\d{2})[-_/\.](\d{2})[-_/\.](\d{4})\b",
        r"\b(\d{4})[-_/\.](\d{2})[-_/\.](\d{2})\b",
        r"\b(\d{2})[-_/\.](\d{2})[-_/\.](\d{2})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if not match:
            continue
        parts = match.groups()
        if len(parts[0]) == 4:
            candidate = f"{parts[0]}-{parts[1]}-{parts[2]}"
            parsed = _parse_date(candidate)
        else:
            year = parts[2]
            if len(year) == 2:
                year = f"20{year}"
            candidate = f"{parts[0]}-{parts[1]}-{year}"
            parsed = _parse_date(candidate)
        if parsed:
            return parsed
    return None


def _date_text(value: Any) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%d-%m-%Y") if parsed else str(value or "").strip()


def _date_label(value: date | None, fallback: str) -> str:
    return value.strftime("%d-%m-%Y") if value else str(fallback or "").strip()


def _split_rows(line: str) -> list[str]:
    return next(csv.reader(io.StringIO(line), delimiter=";"))


def _is_stable_id_header(raw: str) -> bool:
    return raw in _STABLE_ID_HEADERS


def _is_nusf_header(parts: list[str]) -> bool:
    headers = {_norm_header(part) for part in parts}
    return "name" in headers and (
        "stable_key" in headers or "source_id" in headers
    ) and (
        "planned_finish" in headers or "planned_end_date" in headers
    )


def _deduplicate_rows(rows: list[dict]) -> list[dict]:
    """Remove duplicate activities by identity key, keeping the last occurrence."""
    seen = {}
    for row in rows:
        key = row.get("_identity", "")
        if key:
            seen[key] = row  # last occurrence wins
    return list(seen.values())

def parse_nusf_chunks(chunks: list[dict]) -> list[dict]:
    rows: list[dict] = []
    headers: list[str] | None = None
    source_id_is_stable = False

    for chunk in chunks or []:
        content = str(chunk.get("content", ""))
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or ";" not in line or line.startswith("FORMAT:"):
                continue

            parts = [part.strip() for part in _split_rows(line)]
            if _is_nusf_header(parts):
                headers = [_norm_header(part) for part in parts]
                # A bare "Id"/"D I" column is MS Project's row/display position — it
                # renumbers whenever tasks are added/reordered, so it's not safe to use
                # for cross-version identity. Only "Entydigt Id"/"Unique Id"-style
                # columns (or an already-normalized stable_key/source_id) are durable.
                source_id_is_stable = any(
                    _is_stable_id_header(part.strip().lower())
                    for part, header in zip(parts, headers)
                    if header == "source_id"
                )
                logger.info(
                    f"[nusf_compare_engine][parse:header] raw_headers={parts} "
                    f"normalized={headers} id_column_stable={source_id_is_stable}"
                )
                continue
            if not headers:
                continue

            row = {header: parts[idx].strip() if idx < len(parts) else "" for idx, header in enumerate(headers)}
            name = row.get("name", "").strip()
            if not name:
                continue

            stable_key = row.get("stable_key", "").strip()
            trusted_source_id = row.get("source_id", "").strip() if source_id_is_stable else ""
            identity = (
                stable_key
                or trusted_source_id
                or f"{_norm_key(name)}|{_norm_key(row.get('location_path', ''))}|{_norm_key(row.get('planned_start', ''))}"
            )
            if stable_key or trusted_source_id:
                # A genuinely stable id (Entydigt Id/Unique Id) is already a good label as-is.
                identity_label = stable_key or trusted_source_id
            else:
                # No durable id in the source (e.g. MS Project's positional "Id" column) —
                # show what we actually matched on so a PM can see why two rows were
                # treated as the same/different activity.
                label_parts = [name]
                loc_part = row.get("location_path", "").strip()
                if loc_part:
                    label_parts.append(loc_part)
                date_part = _date_text(row.get("planned_start"))
                if date_part:
                    label_parts.append(date_part)
                identity_label = " — ".join(label_parts)
            row["_identity"] = identity
            row["_identity_label"] = identity_label
            rows.append(row)

    deduped = _deduplicate_rows(rows)
    stable_count = sum(1 for r in deduped if r.get("stable_key", "").strip() or (source_id_is_stable and r.get("source_id", "").strip()))
    fallback_count = len(deduped) - stable_count
    sample = deduped[0] if deduped else None
    logger.info(
        f"[nusf_compare_engine][parse:summary] raw_rows={len(rows)} unique_activities={len(deduped)} "
        f"stable_id={stable_count} name_date_fallback={fallback_count} "
        f"sample_source_id={sample.get('source_id') if sample else None!r} "
        f"sample_identity_label={sample.get('_identity_label') if sample else None!r}"
    )
    return deduped


def _trade_code(row: dict) -> str | None:
    text = " ".join([row.get("name", ""), row.get("discipline", ""), row.get("activity_type", "")]).upper()
    if text.startswith("EL -") or text.startswith("EL-") or "ELECTRICAL" in text:
        return "EL"
    if text.startswith("VVS -") or text.startswith("VVS-") or "PLUMBING" in text or "SPRINKLER" in text:
        return "VVS"
    if text.startswith("VENT -") or text.startswith("VENT-") or "VENTILATION" in text:
        return "VENT"
    if text.startswith("ARK -") or text.startswith("ARK-") or "ARCHITECTURE" in text:
        return "ARK"
    if text.startswith("BYGH -") or text.startswith("BYGH-") or "CIVIL" in text or "GULV" in text or "BETON" in text or "POREBETON" in text or "ISOLERING" in text or "VINDUER" in text or "FACADE" in text or "MEMBRAN" in text or "LANDSKAB" in text or "ASFALT" in text:
        return "BYGH"
    return None


def _path_parts(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*/\s*", str(value or "")) if part.strip()]


def _floor_from_path_part(part: str) -> str:
    value = str(part or "").strip()
    lower = value.casefold()
    if not value:
        return ""
    if lower in {"st.", "st", "stue"}:
        return "Ground Floor"
    if "basement" in lower or "kaelder" in lower or "kælder" in lower:
        match = re.search(r"-\s*(\d+)", value)
        return f"Basement -{match.group(1)}" if match else "Basement"
    match = re.fullmatch(r"(\d+)\.", value)
    if match:
        return f"{match.group(1)}. Floor"
    match = re.search(r"\b(\d+)\.\s*sal\b", value, re.I)
    if match:
        return f"{match.group(1)}. Floor"
    return ""


def _infer_area_from_name(name: str) -> str:
    """Extract area/section from H8-style activity names like '1/A_Udearealer_NK'."""
    m = re.search(r'_(NK|AP)\b', name)
    if m:
        return m.group(1)
    sections = re.findall(r'\b(Udearealer|Kælder|Stueplan|1\.sal|2\.sal|3\.sal|4\.sal|5\.sal)\b', name, re.I)
    if sections:
        return sections[0]
    return ""

def _location(row: dict) -> dict:
    parts = _path_parts(row.get("location_path", ""))
    path_area = parts[1] if len(parts) > 1 else ""
    path_floor = ""
    path_phase = ""
    for part in reversed(parts[1:]):
        path_floor = _floor_from_path_part(part)
        if path_floor:
            break
    for part in parts[2:]:
        if _floor_from_path_part(part):
            continue
        path_phase = part
        break
    if not path_area:
        path_area = _infer_area_from_name(row.get("name", ""))

    return {
        "area": row.get("area", "").strip() or path_area,
        "floor": row.get("floor", "").strip() or path_floor,
        "phase": row.get("phase", "").strip() or path_phase,
    }


def _dashboard_meta(row: dict) -> dict:
    loc = _location(row)
    trade = _trade_code(row) or row.get("discipline", "").strip()
    return {
        "id": row.get("source_id", "").strip(),
        "source_id": row.get("source_id", "").strip(),
        "location": loc,
        "area": loc.get("area", ""),
        "floor": loc.get("floor", ""),
        "phase": loc.get("phase", ""),
        "location_path": row.get("location_path", "").strip() or row.get("wbs_code", "").strip(),
        "resource": row.get("discipline", "").strip(),
        "trade": trade,
        "trade_code": trade,
        "duration": str(row.get("duration_hours", "")).strip(),
    }


def _collect_filters(sections: list[dict]) -> dict:
    """Build sidebar filter options only from activities that appear in dashboard sections.
    Scanning all rows causes orphaned floor/phase labels with no matching activities."""
    areas: set[str] = set()
    floors: set[str] = set()
    phases: set[str] = set()
    for item in sections:
        loc = item.get("location", {}) if isinstance(item, dict) else {}
        if loc.get("area"):
            areas.add(loc["area"])
        if loc.get("floor"):
            floors.add(loc["floor"])
        if loc.get("phase"):
            phases.add(loc["phase"])
    return {"areas": sorted(areas), "floors": sorted(floors), "phases": sorted(phases)}


def _expected_progress(start: date, finish: date, ref: date) -> float:
    total_days = max((finish - start).days, 1)
    elapsed_days = (ref - start).days
    return round(max(0.0, min(100.0, (elapsed_days / total_days) * 100.0)), 1)


def _progress_status(
    actual: float,
    expected: float,
    late_flag: bool,
    planned_finish: date | None = None,
    actual_finish: date | None = None,
) -> str:
    """Classify an activity as ahead/behind/on_schedule.

    When an actual finish date is recorded, it is direct evidence of whether the
    activity beat or missed its own deadline, so it takes priority over the
    time-elapsed variance estimate below. That estimate clamps "expected
    progress" at 100% once the planned window has closed (see
    _expected_progress), which makes a genuinely early finish mathematically
    indistinguishable from an on-time one once evaluated after the deadline —
    "ahead" would otherwise become unreachable for any activity whose window
    has already elapsed.
    """
    if actual_finish and planned_finish:
        if actual_finish < planned_finish:
            return "ahead"
        if actual_finish > planned_finish:
            return "behind"
        return "on_schedule"
    if late_flag:
        return "behind"
    variance = actual - expected
    if variance < -5:
        return "behind"
    if variance > 5:
        return "ahead"
    return "on_schedule"


def _project_health(behind_count: int, red_ponr_count: int, critical_count: int, yellow_ponr_count: int = 0) -> str:
    if red_ponr_count or critical_count:
        return "Red"
    if yellow_ponr_count >= 3 or behind_count >= 5:
        return "Yellow"
    if behind_count:
        return "Yellow"
    return "Green"


def _rescale_progress_if_fractional(rows: list[dict]) -> None:
    """Detect 0-to-1 decimal progress scale (e.g. Fremdrift=0.75 means 75%) and
    convert to 0-100. Needed because some scheduling tools export progress as a
    fraction rather than a percentage, and normalization stores it verbatim."""
    nonzero = [_parse_float(r.get("percent_complete")) for r in rows
               if str(r.get("percent_complete", "")).strip() not in ("", "0")]
    if nonzero and max(nonzero) <= 1.0:
        for row in rows:
            raw = str(row.get("percent_complete", "")).strip()
            if raw:
                try:
                    row["percent_complete"] = str(round(float(raw.replace(",", ".")) * 100.0, 1))
                except ValueError:
                    pass


def build_progress_history_from_nusf_sources(sources: list[tuple[str, list[dict]]], reference_date: str) -> list[dict]:
    ref = _parse_date(reference_date) or date.today()
    points: list[dict] = []
    seen: set[str] = set()

    for idx, (label, chunks) in enumerate(sources or []):
        rows = parse_nusf_chunks(chunks)
        if not rows:
            continue
        _rescale_progress_if_fractional(rows)
        point_date = _parse_date_from_text(label)
        actual_values = [_parse_float(row.get("percent_complete")) for row in rows]
        actual = round(mean(actual_values), 1) if actual_values else 0.0

        expected_values: list[float] = []
        if point_date:
            for row in rows:
                start = _parse_date(row.get("planned_start"))
                finish = _parse_date(row.get("planned_finish"))
                if start and finish:
                    expected_values.append(_expected_progress(start, finish, point_date) if start <= point_date else 0.0)
                else:
                    expected_values.append(0.0)
        planned = round(mean(expected_values), 1) if expected_values else None
        sort_date = point_date or ref
        unique_key = point_date.isoformat() if point_date else f"idx-{idx}-{label}"
        if unique_key in seen:
            continue
        seen.add(unique_key)
        point = {
            "label": _date_label(point_date, label or f"Extract {idx + 1}"),
            "date": sort_date.isoformat(),
            "actual_pct": actual,
        }
        if planned is not None:
            point["planned_pct"] = planned
        points.append(point)

    points.sort(key=lambda item: item.get("date", ""))
    if len(points) < 2:
        return []

    # If dates were not available, planned progress would be fabricated. Keep the
    # actual trend points only in that case; the V1 formatter will fall back to
    # the two-extract graph until planned values are real.
    if sum(1 for point in points if "planned_pct" in point) < 2:
        return points
    return points


def _values_differ(change_type: str, old_val: str, new_val: str) -> bool:
    """Compare values semantically, not just by string equality."""
    if old_val == new_val:
        return False
    if change_type in ("Start Date", "Finish Date"):
        old_date = _parse_date(old_val)
        new_date = _parse_date(new_val)
        if old_date and new_date:
            return old_date != new_date
        return old_date != new_date
    if change_type == "Duration":
        old_f = _parse_duration_days(old_val)
        new_f = _parse_duration_days(new_val)
        return abs(old_f - new_f) > 0.5
    if change_type == "Progress":
        old_f = _parse_float(old_val)
        new_f = _parse_float(new_val)
        return abs(old_f - new_f) > 0.5
    return old_val.strip() != new_val.strip()

def _infer_ref_date_from_data(rows: list[dict]) -> date:
    """Derive a reference date from the schedule data itself.

    Prefers the date implied by each in-progress activity's own reported
    percent_complete (start + pct * duration). The median of these implied
    "as of" dates is a much better proxy for "when was this schedule current"
    than the schedule's own max finish date: a rolling look-ahead schedule
    typically mixes a few long-running summary/parent tasks (which push the
    max finish date far out) with many short tasks that finish much earlier —
    anchoring on the max date makes those shorter tasks' windows look fully
    closed regardless of actual progress, making "ahead of schedule"
    unreachable for reasons unrelated to real performance.

    Falls back to the latest finish/start date, then today, if no activity
    has usable in-progress (0 < pct < 100) data.
    """
    implied: list[float] = []
    for row in rows:
        start = _parse_date(row.get("planned_start"))
        finish = _parse_date(row.get("planned_finish"))
        pct = _parse_float(row.get("percent_complete"))
        if start and finish and finish > start and 0 < pct < 100:
            implied.append(start.toordinal() + (pct / 100.0) * (finish - start).days)
    if implied:
        return date.fromordinal(round(median(implied)))

    dates = []
    for row in rows:
        for field in ("planned_finish", "planned_start"):
            d = _parse_date(row.get(field))
            if d:
                dates.append(d)
    return max(dates) if dates else date.today()


def _schedule_date_range(rows: list[dict]) -> tuple[date, date] | None:
    """Earliest planned_start .. latest planned_finish across the schedule, if any dates exist."""
    starts = [_parse_date(row.get("planned_start")) for row in rows]
    finishes = [_parse_date(row.get("planned_finish")) for row in rows]
    dates = [d for d in starts + finishes if d]
    return (min(dates), max(dates)) if dates else None


def _resolve_reference_date(reference_date: str, rows: list[dict]) -> date:
    """Resolve the reference date to compare progress against.

    An explicit reference_date is honored only if it actually falls within
    the schedule's own date range. A caller-supplied date outside that range
    (e.g. a UI date-picker defaulting to "today" against a schedule whose
    dates are all in the past/future, as happens with historical/demo data)
    is treated as unreliable and replaced with a date derived from the data
    itself — otherwise every activity's expected-progress window would be
    fully closed (or not yet open), making "ahead of schedule" unreachable
    for reasons that have nothing to do with actual project performance.
    """
    explicit = _parse_date(reference_date)
    date_range = _schedule_date_range(rows)
    if explicit and date_range:
        lo, hi = date_range
        if lo <= explicit <= hi:
            return explicit
        inferred = _infer_ref_date_from_data(rows)
        logger.info(
            f"[nusf_compare_engine][reference_date] explicit={explicit} falls outside "
            f"schedule range [{lo}, {hi}] — using inferred date {inferred} instead"
        )
        return inferred
    if explicit:
        return explicit
    return _infer_ref_date_from_data(rows)

def _extract_period_label_from_filename(filename: str) -> str:
    if not filename:
        return ""
    m = re.search(r'Uge\s*(\d+-\d+)', filename, re.IGNORECASE)
    if m:
        return f"Week {m.group(1)}"
    return ""

def _group_key(row: dict) -> str:
    loc = _location(row)
    loc_text = row.get("location_path", "").strip() or " / ".join(
        p for p in [loc.get("area"), loc.get("floor"), loc.get("phase")] if p
    )
    return f"{_norm_key(row.get('name', ''))}|{_norm_key(loc_text)}"


def _date_distance(old_row: dict, new_row: dict) -> int:
    old_start = _parse_date(old_row.get("planned_start"))
    old_finish = _parse_date(old_row.get("planned_finish"))
    new_start = _parse_date(new_row.get("planned_start"))
    new_finish = _parse_date(new_row.get("planned_finish"))
    dist = 0
    dist += abs((old_start - new_start).days) if old_start and new_start else 9999
    dist += abs((old_finish - new_finish).days) if old_finish and new_finish else 9999
    return dist


# UNCALIBRATED — pending EXT-1 real K&L schedule data calibration (TL-3.6)
_AMBIGUITY_MARGIN_DAYS = 3


def _evaluate_match_level(old_row: dict, new_row: dict) -> tuple[MatchLevel, str, list[str]]:
    old_sid = str(old_row.get("source_id") or "").strip()
    new_sid = str(new_row.get("source_id") or "").strip()
    old_mm = str(old_row.get("match_method") or "").strip()
    new_mm = str(new_row.get("match_method") or "").strip()

    if (
        old_sid
        and new_sid
        and old_sid == new_sid
        and old_mm in ("verified_source_id", "stable_key")
        and new_mm in ("verified_source_id", "stable_key")
    ):
        return MatchLevel.L1_EXACT_VERIFIED_ID, "verified_source_id", ["source_id"]

    evidence = ["name", "location"]
    old_trade = _norm_key(old_row.get("discipline") or old_row.get("trade") or "")
    new_trade = _norm_key(new_row.get("discipline") or new_row.get("trade") or "")
    trade_aligns = bool(old_trade and new_trade and old_trade == new_trade)
    if trade_aligns:
        evidence.append("trade")

    old_phase = _norm_key(old_row.get("phase") or old_row.get("floor") or "")
    new_phase = _norm_key(new_row.get("phase") or new_row.get("floor") or "")
    phase_aligns = bool(old_phase and new_phase and old_phase == new_phase)
    if phase_aligns:
        evidence.append("phase")

    if trade_aligns and phase_aligns:
        return MatchLevel.L2_STRONG_MULTI_FIELD, "name_location_trade_phase", evidence
    return MatchLevel.L3_PARTIAL, "name_location", evidence


def _resolve_activity_matches(
    old_rows: list[dict],
    new_rows: list[dict],
    *,
    mapping_lookup: Optional[Callable[[str], Optional[VerifiedMapping]]] = None,
) -> tuple[dict[str, dict], dict[str, MatchResult]]:
    """Pair old-schedule activities to new-schedule activities using MatchLevel rules.

    Replaces greedy nearest-date matching with ambiguity detection (TL-3.3):
    Refuses forced pairing when candidates are ambiguous, returning L4_FUZZY with
    requires_verification = True.

    TL-8.4 (brief §26): `mapping_lookup`, when given, is consulted first —
    a human-confirmed `VerifiedMapping` (TL-8.3) resolves at human-verified
    confidence and never reaches the ambiguity-detection steps below it.
    The caller supplies `mapping_lookup` as a closure bound to one project
    (`MatchMappingStore.active_mapping` partially applied on `project_id`)
    so this function itself stays pure and project-agnostic — it never
    imports or constructs a `MatchMappingStore`.
    """
    matches: dict[str, dict] = {}
    match_results: dict[str, MatchResult] = {}
    used_old_ids: set[str] = set()

    # Step 0: human-verified mappings (TL-8.4). Consulted before anything
    # else — a confirmed mapping is the strongest evidence available,
    # stronger than a freshly-recomputed verified-source-id match, since
    # a human already looked at this exact ambiguity and resolved it.
    if mapping_lookup is not None:
        old_by_id = {row["_identity"]: row for row in old_rows}
        for new_row in new_rows:
            new_id = new_row["_identity"]
            mapping = mapping_lookup(_group_key(new_row))
            if mapping is None:
                continue

            # Do-not (TL-8.4 AC4): a mapping that contradicts strong,
            # freshly-computed source evidence must raise a conflict, not
            # silently win. "Contradicts" here means: this new row itself
            # carries a verified source id, and that id points to a
            # DIFFERENT old activity than the mapping says.
            own_sid = str(new_row.get("source_id") or "").strip()
            own_mm = str(new_row.get("match_method") or "").strip()
            has_own_verified_id = bool(own_sid) and own_mm in ("verified_source_id", "stable_key")
            verified_target = None
            if has_own_verified_id:
                for old_row in old_rows:
                    old_sid = str(old_row.get("source_id") or "").strip()
                    old_mm = str(old_row.get("match_method") or "").strip()
                    if old_sid == own_sid and old_mm in ("verified_source_id", "stable_key"):
                        verified_target = old_row["_identity"]
                        break

            if mapping.old_activity_id is None:
                # A human confirmed "no match" for this slot — honour it,
                # never re-propose the same ambiguity (skip normal
                # matching for this new_row entirely).
                match_results[new_id] = MatchResult(
                    level=MatchLevel.L5_NO_RELIABLE_MATCH,
                    method="human_verified_no_match",
                    evidence=["human_verified_mapping"],
                    matched_id=None,
                    requires_verification=False,
                )
                continue

            if verified_target is not None and verified_target != mapping.old_activity_id:
                match_results[new_id] = MatchResult(
                    level=MatchLevel.L4_FUZZY,
                    method="mapping_conflict",
                    evidence=[],
                    matched_id=None,
                    candidates=[
                        {"matched_id": mapping.old_activity_id, "source": "human_mapping"},
                        {"matched_id": verified_target, "source": "verified_source_id"},
                    ],
                    requires_verification=True,
                )
                continue

            mapped_old = old_by_id.get(mapping.old_activity_id)
            if mapped_old is None or mapping.old_activity_id in used_old_ids:
                # The mapped counterpart is gone from this upload (renamed
                # out of matching, deleted, or already consumed) — fall
                # through to normal matching rather than pairing to
                # nothing; TL-8.5's invalidation is the caller's job to
                # run before this point, not this function's.
                continue

            matches[new_id] = mapped_old
            used_old_ids.add(mapping.old_activity_id)
            match_results[new_id] = MatchResult(
                level=MatchLevel.L1_EXACT_VERIFIED_ID,
                method="human_verified",
                evidence=["human_verified_mapping"],
                matched_id=mapping.old_activity_id,
                requires_verification=False,
            )

    # Step 1: L1 Exact Verified ID matching
    old_by_verified_id: dict[str, dict] = {}
    for row in old_rows:
        sid = str(row.get("source_id") or "").strip()
        mm = str(row.get("match_method") or "").strip()
        if sid and mm in ("verified_source_id", "stable_key"):
            old_by_verified_id[sid] = row

    for new_row in new_rows:
        new_id = new_row["_identity"]
        if new_id in match_results:
            continue  # TL-8.4: already resolved by a human-verified mapping (Step 0)
        sid = str(new_row.get("source_id") or "").strip()
        mm = str(new_row.get("match_method") or "").strip()
        if sid and mm in ("verified_source_id", "stable_key") and sid in old_by_verified_id:
            old_row = old_by_verified_id[sid]
            matches[new_id] = old_row
            used_old_ids.add(old_row["_identity"])
            match_results[new_id] = MatchResult(
                level=MatchLevel.L1_EXACT_VERIFIED_ID,
                method="verified_source_id",
                evidence=["source_id"],
                matched_id=old_row["_identity"],
                requires_verification=False,
            )

    # Step 2: Group unmatched rows by name + location
    old_groups: dict[str, list[dict]] = defaultdict(list)
    for row in old_rows:
        if row["_identity"] not in used_old_ids:
            old_groups[_group_key(row)].append(row)

    new_groups: dict[str, list[dict]] = defaultdict(list)
    for row in new_rows:
        # TL-8.4: also skip anything Step 0 already resolved (matched,
        # human-confirmed no-match, or flagged as a mapping conflict) —
        # `matches` alone misses the latter two, which never entered it.
        if row["_identity"] not in matches and row["_identity"] not in match_results:
            new_groups[_group_key(row)].append(row)

    for key, new_group in new_groups.items():
        old_group = old_groups.get(key)
        if not old_group:
            continue

        if len(old_group) == 1 and len(new_group) == 1:
            old_row = old_group[0]
            new_row = new_group[0]
            new_id = new_row["_identity"]
            level, method, evidence = _evaluate_match_level(old_row, new_row)
            matches[new_id] = old_row
            used_old_ids.add(old_row["_identity"])
            match_results[new_id] = MatchResult(
                level=level,
                method=method,
                evidence=evidence,
                matched_id=old_row["_identity"],
                requires_verification=False,
            )
            continue

        # Ambiguity check for multi-candidate groups
        for new_row in new_group:
            new_id = new_row["_identity"]
            cand_distances = sorted(
                [(_date_distance(old_row, new_row), old_row) for old_row in old_group],
                key=lambda c: c[0],
            )
            if not cand_distances:
                continue

            if (
                len(cand_distances) >= 2
                and (cand_distances[1][0] - cand_distances[0][0]) < _AMBIGUITY_MARGIN_DAYS
            ):
                # Ambiguous! Refuse to match (TL-3.3)
                cand_list = [
                    {"matched_id": c[1]["_identity"], "date_distance": c[0]} for c in cand_distances
                ]
                match_results[new_id] = MatchResult(
                    level=MatchLevel.L4_FUZZY,
                    method="ambiguous_candidates",
                    evidence=["name", "location"],
                    matched_id=None,
                    candidates=cand_list,
                    requires_verification=True,
                )
            else:
                best_dist, best_old = cand_distances[0]
                if best_old["_identity"] not in used_old_ids:
                    level, method, evidence = _evaluate_match_level(best_old, new_row)
                    matches[new_id] = best_old
                    used_old_ids.add(best_old["_identity"])
                    match_results[new_id] = MatchResult(
                        level=level,
                        method=method,
                        evidence=evidence,
                        matched_id=best_old["_identity"],
                        requires_verification=False,
                    )

    # Step 3: Classify remaining unmatched new_rows and old_rows
    for new_row in new_rows:
        new_id = new_row["_identity"]
        if new_id not in match_results:
            match_results[new_id] = MatchResult(
                level=MatchLevel.L5_NO_RELIABLE_MATCH,
                method="unmatched",
                evidence=[],
                matched_id=None,
                requires_verification=True,
            )

    for old_row in old_rows:
        old_id = old_row["_identity"]
        if old_id not in match_results and old_id not in used_old_ids:
            match_results[old_id] = MatchResult(
                level=MatchLevel.L5_NO_RELIABLE_MATCH,
                method="unmatched",
                evidence=[],
                matched_id=None,
                requires_verification=True,
            )

    return matches, match_results


def compare_nusf_chunks(old_chunks: list[dict], new_chunks: list[dict], reference_date: str) -> dict:
    old_rows = parse_nusf_chunks(old_chunks)
    new_rows = parse_nusf_chunks(new_chunks)
    _rescale_progress_if_fractional(old_rows)
    _rescale_progress_if_fractional(new_rows)
    new_by_id = {row["_identity"]: row for row in new_rows}
    ref = _resolve_reference_date(reference_date, new_rows)
    old_ref = _infer_ref_date_from_data(old_rows)

    matches, match_results = _resolve_activity_matches(old_rows, new_rows)
    matched_old_ids = {id(old) for old in matches.values()}
    added_rows = [row for row in new_rows if row["_identity"] not in matches]
    removed_rows = [row for row in old_rows if id(row) not in matched_old_ids]
    added_ids = [row["_identity"] for row in added_rows]
    removed_ids = [row["_identity"] for row in removed_rows]
    requires_verification_rows = [
        row
        for row in new_rows
        if match_results.get(
            row["_identity"],
            MatchResult(level=MatchLevel.L5_NO_RELIABLE_MATCH, method="unmatched"),
        ).requires_verification
    ]

    logger.info(
        f"[nusf_compare_engine][compare:match] old_rows={len(old_rows)} new_rows={len(new_rows)} "
        f"matched={len(matches)} added={len(added_rows)} removed={len(removed_rows)}"
    )

    changes: list[dict] = []
    for new_key, old in matches.items():
        new = new_by_id[new_key]
        name = new.get("name") or old.get("name") or new_key
        comparisons = [
            ("Start Date", _date_text(old.get("planned_start")), _date_text(new.get("planned_start"))),
            ("Finish Date", _date_text(old.get("planned_finish")), _date_text(new.get("planned_finish"))),
            ("Duration", str(old.get("duration_hours", "")).strip(), str(new.get("duration_hours", "")).strip()),
            ("Progress", str(old.get("percent_complete", "")).strip(), str(new.get("percent_complete", "")).strip()),
        ]
        for change_type, old_val, new_val in comparisons:
            if _values_differ(change_type, old_val, new_val):
                changes.append(
                    {
                        "activity": name,
                        "change_type": change_type,
                        "old": old_val,
                        "new": new_val,
                        "start_date": _date_text(new.get("planned_start")),
                        "finish_date": _date_text(new.get("planned_finish")),
                        "old_start": _date_text(old.get("planned_start")),
                        "new_start": _date_text(new.get("planned_start")),
                        "old_finish": _date_text(old.get("planned_finish")),
                        "new_finish": _date_text(new.get("planned_finish")),
                        "old_duration": str(old.get("duration_hours", "")).strip(),
                        "new_duration": str(new.get("duration_hours", "")).strip(),
                        **_dashboard_meta(new),
                    }
                )

    progress: list[dict] = []
    not_started: list[dict] = []
    stage_mismatch: list[dict] = []
    ponr: list[dict] = []
    action_recommendations: list[dict] = []
    critical_path: list[dict] = []
    _all_expected: list[float] = []  # expected progress for every row (0 if not yet started)

    for row in new_rows:
        name = row.get("name", "")
        start = _parse_date(row.get("planned_start"))
        finish = _parse_date(row.get("planned_finish"))
        actual = round(_parse_float(row.get("percent_complete")), 1)
        loc = _location(row)
        late_flag = _parse_bool(row.get("is_late"))

        old_row = matches.get(row.get("_identity"))
        old_pct = round(_parse_float(old_row.get("percent_complete")), 1) if old_row else 0.0

        if start and finish:
            _all_expected.append(old_pct)
        else:
            _all_expected.append(0.0)

        if start and start < ref and actual <= 0:
            not_started.append(
                {
                    "id": row.get("source_id", ""),
                    "activity": name,
                    "start_date": _date_text(row.get("planned_start")),
                    "finish_date": _date_text(row.get("planned_finish")),
                    "progress_pct": 0,
                    **_dashboard_meta(row),
                }
            )

        if start and finish and start <= ref:
            expected = _expected_progress(start, finish, ref)
            variance = round(actual - expected, 1)
            actual_finish = _parse_date(row.get("actual_finish"))
            status = _progress_status(actual, expected, late_flag, finish, actual_finish)
            item = {
                "activity": name,
                "start_date": _date_text(row.get("planned_start")),
                "finish_date": _date_text(row.get("planned_finish")),
                "actual_pct": actual,
                "expected_pct": expected,
                "variance_pct": variance,
                "status": status,
                "late_flag": late_flag,
                **_dashboard_meta(row),
            }
            if abs(variance) >= 1 or late_flag or status in ("ahead", "behind"):
                progress.append(item)

            mismatch_status = "OK"
            if abs(variance) >= 50:
                mismatch_status = "Critical Mismatch"
            elif abs(variance) >= 10 or late_flag:
                mismatch_status = "Mismatch"
            stage_mismatch.append(
                {
                    "activity": name,
                    "actual_pct": actual,
                    "expected_pct": expected,
                    "difference_pct": variance,
                    "status": mismatch_status,
                    **_dashboard_meta(row),
                }
            )

            if status == "behind":
                remaining_days = (finish - ref).days
                # late_flag alone (1 day late) is not PONR Red — only extreme variance or
                # imminent deadline warrants Red; late_flag already drives "behind" status above.
                classification = "Red" if remaining_days <= 7 or variance <= -25 else "Yellow"
                assessment = "POINT OF NO RETURN" if classification == "Red" else "HIGH RISK"
                recommendation = f"Recover {name} before the finish date."
                ponr_item = {
                    "activity": name,
                    "actual_pct": actual,
                    "expected_pct": expected,
                    "variance_pct": variance,
                    "remaining_time": f"{remaining_days} days",
                    "classification": classification,
                    "assessment": assessment,
                    "recommendation": recommendation,
                    **_dashboard_meta(row),
                }
                ponr.append(ponr_item)
                if classification == "Red":
                    action_recommendations.append(
                        {
                            "activity": name,
                            "issue": f"{name} is behind expected progress.",
                            "actions": ["Review manpower", "Confirm blockers", "Update recovery plan"],
                            **_dashboard_meta(row),
                        }
                    )

        critical_flag = _parse_bool(row.get("critical_flag"))
        total_float_raw = str(row.get("total_float", "")).strip()
        total_float = _parse_float(total_float_raw, default=999999.0)
        if critical_flag or (total_float_raw and total_float <= 0):
            critical_path.append(
                {
                    "activity": name,
                    "start_date": _date_text(row.get("planned_start")),
                    "finish_date": _date_text(row.get("planned_finish")),
                    "actual_pct": actual,
                    "float_days": total_float if total_float_raw else 0,
                    **_dashboard_meta(row),
                }
            )

    trade_counts = {"EL": 0, "VVS": 0, "VENT": 0, "ARK": 0, "BYGH": 0, "ALL": len(new_rows)}
    for row in new_rows:
        trade = _trade_code(row)
        if trade:
            trade_counts[trade] += 1

    behind_count = sum(1 for item in progress if item.get("status") == "behind")
    ahead_count = sum(1 for item in progress if item.get("status") == "ahead")
    red_ponr_count = sum(1 for item in ponr if str(item.get("classification", "")).upper() == "RED")
    yellow_ponr_count = sum(1 for item in ponr if str(item.get("classification", "")).upper() == "YELLOW")
    old_progress = round(mean([_parse_float(row.get("percent_complete")) for row in old_rows]), 1) if old_rows else 0.0
    new_progress = round(mean([_parse_float(row.get("percent_complete")) for row in new_rows]), 1) if new_rows else 0.0

    if new_progress < 5.0 and new_rows:
        nonzero_progress = [_parse_float(r.get("percent_complete")) for r in new_rows if _parse_float(r.get("percent_complete")) > 0]
        if nonzero_progress:
            new_progress = round(mean(nonzero_progress), 1)
            old_nonzero = [_parse_float(r.get("percent_complete")) for r in old_rows if _parse_float(r.get("percent_complete")) > 0]
            if old_nonzero:
                old_progress = round(mean(old_nonzero), 1)

    mean_expected_all = round(mean(_all_expected), 1) if _all_expected else 0.0

    # Use the computed date as the period label when the caller passes an invalid date
    # (e.g. "Unknown") — prevents "Unknown" appearing in the dashboard period card.
    period_label = reference_date if _parse_date(reference_date) else ref.strftime("%d-%m-%Y")

    # Detect schedules where no progress data was recorded at all.
    past_activities = sum(
        1 for row in new_rows
        if _parse_date(row.get("planned_start")) and _parse_date(row.get("planned_start")) < ref
    )
    data_quality_warning = (
        "No progress data found: all activities show 0% complete. "
        "The schedule may be a plan-only export without actual progress recorded. "
        "Progress-based analysis is unreliable."
        if new_progress == 0.0 and past_activities > 0 else ""
    )

    delay_drivers = []
    if behind_count:
        area_counts: dict[str, int] = {}
        for item in progress:
            if item.get("status") != "behind":
                continue
            area = item.get("location", {}).get("area") or "Unassigned area"
            area_counts[area] = area_counts.get(area, 0) + 1
        for area, count in sorted(area_counts.items(), key=lambda pair: pair[1], reverse=True)[:5]:
            delay_drivers.append(
                {
                    "driver": f"{area} behind",
                    "description": f"{count} activities are behind expected progress in {area}.",
                    "affected_count": count,
                }
            )

    requires_verification_list = [
        {
            "activity": row.get("name", ""),
            "id": row.get("source_id", ""),
            "level": match_results[row["_identity"]].level.value,
            "method": match_results[row["_identity"]].method,
            "candidates": match_results[row["_identity"]].candidates,
            "reason": (
                "Nova found insufficient evidence to reliably match this activity between the two schedules. "
                "The activity has therefore been excluded from confirmed comparison results."
            ),
            "match_key": _group_key(row),
            **_dashboard_meta(row),
        }
        for row in requires_verification_rows
    ]

    return {
        "executive_summary": {
            "project_health": _project_health(behind_count, red_ponr_count, len(critical_path), yellow_ponr_count),
            "selected_activities": len(new_rows),
            "added_activities": len(added_ids),
            "behind_schedule_count": behind_count,
            "ahead_of_schedule_count": ahead_count,
            "critical_count": len(critical_path),
            "critical_path_count": len(critical_path),
            "point_of_no_return_count": red_ponr_count,
            "overall_progress_pct": new_progress,
            "recommended_action": action_recommendations[0]["issue"] if action_recommendations else "",
            "trade_counts": trade_counts,
            "data_quality_warning": data_quality_warning,
            "requires_verification_count": len(requires_verification_rows),
            "confirmed_activities_count": len(new_rows) - len(requires_verification_rows),
        },
        "changed_activities": {
            "added": [row.get("name", row.get("_identity", "")) for row in added_rows],
            "removed": [row.get("name", row.get("_identity", "")) for row in removed_rows],
            "changes": changes,
        },
        "not_started_overdue": not_started,
        "progress_vs_expected": progress,
        "stage_mismatch": stage_mismatch,
        "point_of_no_return": ponr,
        "action_recommendations": action_recommendations,
        "critical_path_activities": critical_path,
        "delay_drivers": delay_drivers,
        "requires_verification_activities": requires_verification_list,
        "summary_notes": {
            "overall_progress_old_pct": old_progress,
            "overall_progress_new_pct": new_progress,
            "overall_progress_delta": round(new_progress - old_progress, 1),
            "finished_activities": sum(1 for row in new_rows if _parse_float(row.get("percent_complete")) >= 99),
            "delayed_activities": behind_count,
            "total_activities": len(new_rows),
            "added_count": len(added_ids),
            "removed_count": len(removed_ids),
            "requires_verification_count": len(requires_verification_rows),
            "reporting_period_old": "",
            "reporting_period_new": period_label,
            "mean_expected_pct_all": mean_expected_all,
            "current_data_date": ref.strftime("%d %B %Y") if ref else "",
            "previous_data_date": old_ref.strftime("%d %B %Y") if old_ref else "",
        },
        "filter_options": _collect_filters(progress + ponr + critical_path + not_started),
        "_activity_index": [
            {
                "activity": row.get("name", ""),
                "start_date": _date_text(row.get("planned_start")),
                "finish_date": _date_text(row.get("planned_finish")),
                "actual_pct": round(_parse_float(row.get("percent_complete")), 1),
                **_dashboard_meta(row),
            }
            for row in new_rows
        ],
        "versions": {
            "parser": "nusf-pipeline-v2.1",
            "matching_algorithm": MATCHING_ALGORITHM_VERSION,
            "analysis_engine": ANALYSIS_ENGINE_VERSION,
            "prompt": "comparison-prompt-v1.0",
            "model": "deterministic-comparison-engine",
            "schedule_revision": period_label or "rev:current",
            "manual_corrections": f"corrections-applied:{sum(1 for r in match_results.values() if r.method == 'human_verified')}" if any(r.method == "human_verified" for r in match_results.values()) else "corrections:none",
        },
    }
