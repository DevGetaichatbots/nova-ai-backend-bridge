from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from .diffs import diff_activities

logger = logging.getLogger(__name__)
logger.info("[version_1_0.adapters] module loaded — IDENTITY_FIX_2026_07_27 logging active")


def _sf(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(str(value).replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _si(value: Any, default: int = 0) -> int:
    try:
        return int(round(_sf(value, default)))
    except (TypeError, ValueError):
        return default


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and str(value).strip() != "":
            return value
    return ""


def _parse_date(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_date(value: datetime | None) -> str:
    return value.strftime("%d-%m-%Y") if value else ""


def _derive_schedule_date(rows: list[dict], side: str) -> str:
    candidates: list[datetime] = []
    side_keys = {
        "old": ("old_start", "old_finish"),
        "new": ("new_start", "new_finish"),
    }.get(side, ())
    for row in rows:
        for key in side_keys:
            parsed = _parse_date(row.get(key))
            if parsed:
                candidates.append(parsed)
    if not candidates:
        return ""
    return _format_date(min(candidates))


def _status_health(value: str) -> str:
    val = str(value or "").lower()
    if val == "red":
        return "critical"
    if val == "yellow":
        return "at_risk"
    return "stable"


def _infer_trade(*values: Any) -> str:
    text = " ".join(str(v or "") for v in values).upper()
    if text.startswith("EL -") or text.startswith("EL-") or " ELECTRICAL" in f" {text}":
        return "EL"
    if text.startswith("VVS -") or text.startswith("VVS-") or " PLUMBING" in f" {text}":
        return "VVS"
    if text.startswith("VENT -") or text.startswith("VENT-") or "VENTILATION" in text:
        return "VENT"
    if text.startswith("ARK -") or text.startswith("ARK-") or "ARCHITECTURE" in text:
        return "ARK"
    if text.startswith("BYGH -") or text.startswith("BYGH-") or "CIVIL" in text:
        return "BYGH"
    return _clean(values[-1]) if values and _clean(values[-1]) else ""


def _row_location(item: dict) -> dict:
    loc = item.get("location") if isinstance(item.get("location"), dict) else {}
    return {
        "area": _clean(item.get("area") or loc.get("area")),
        "floor": _clean(item.get("floor") or loc.get("floor")),
        "phase": _clean(item.get("phase") or loc.get("phase")),
        "location": _clean(item.get("location_path") or item.get("location_text")),
    }


_activity_row_log_count = 0
_ACTIVITY_ROW_LOG_LIMIT = 8


def _activity_row(item: dict, *, task_key: str = "activity") -> dict:
    global _activity_row_log_count
    loc = _row_location(item)
    task_name = _clean(item.get(task_key) or item.get("task_name") or item.get("name"))
    trade = _clean(item.get("trade") or item.get("trade_code") or item.get("resource") or item.get("discipline"))
    if not trade:
        trade = _infer_trade(task_name, item.get("task_group_name"), item.get("discipline"))
    location_text = loc["location"] or " / ".join(p for p in [loc["area"], loc["floor"], loc["phase"]] if p)
    out_id = _clean(item.get("id") or item.get("source_id"))
    if _activity_row_log_count < _ACTIVITY_ROW_LOG_LIMIT:
        _activity_row_log_count += 1
        logger.info(
            f"[version_1_0.adapters][_activity_row #{_activity_row_log_count}] "
            f"task={task_name!r} input_id={item.get('id')!r} input_source_id={item.get('source_id')!r} -> output_id={out_id!r}"
        )
    return {
        "id": out_id,
        "task_name": task_name,
        "phase": loc["phase"],
        "area": loc["area"],
        "floor": loc["floor"],
        "location": location_text,
        "resource": _clean(item.get("resource") or item.get("responsible") or item.get("discipline")),
        "trade": trade,
        "start_date": _clean(item.get("start_date")),
        "finish_date": _clean(item.get("finish_date") or item.get("end_date")),
        "duration": _clean(item.get("duration")),
        "old_start": _clean(item.get("old_start")),
        "new_start": _clean(item.get("new_start")),
        "old_finish": _clean(item.get("old_finish")),
        "new_finish": _clean(item.get("new_finish")),
        "old_duration": _clean(item.get("old_duration")),
        "new_duration": _clean(item.get("new_duration")),
        "float_days": _clean(_first_present(item.get("float_days"), item.get("total_float"), item.get("float"))),
        "actual_pct": _sf(item.get("actual_pct") or item.get("progress")),
        "expected_pct": _sf(item.get("expected_pct") or item.get("planned_pct")),
        "deviation": _sf(item.get("variance_pct") or item.get("difference_pct") or item.get("deviation")),
        "status": _clean(item.get("status") or item.get("priority") or item.get("assessment")),
        "days_overdue": _si(item.get("days_overdue"), 0),
        "priority": _clean(item.get("priority")),
    }


def _filters(rows: list[dict], extra_task_types: list[str] | None = None) -> dict:
    def _clean_meta(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()

    areas = sorted({v for v in (_clean_meta(r.get("area")) for r in rows) if v})
    floors = sorted({v for v in (_clean_meta(r.get("floor")) for r in rows) if v})
    phases = sorted({v for v in (_clean_meta(r.get("phase")) for r in rows) if v})
    trades = sorted({v for v in (_clean_meta(r.get("trade")) for r in rows) if v})
    task_types = sorted(set(extra_task_types or []))
    return {
        "areas": areas,
        "floors": floors,
        "phases": phases,
        "trades": trades,
        "task_types": task_types,
    }


def _identity(row: dict) -> str:
    return (
        _clean(row.get("id"))
        or _clean(row.get("source_id"))
        or f'{_clean(row.get("task_name"))}|{_clean(row.get("area"))}|{_clean(row.get("phase"))}'
    ).casefold()


def _unique_count(rows: list[dict]) -> int:
    keys = {_identity(row) for row in rows if _identity(row)}
    return len(keys)


def _changed_activity_count(changed_rows: list[dict], changed: dict) -> int:
    added = changed.get("added", []) if isinstance(changed.get("added"), list) else []
    removed = changed.get("removed", []) if isinstance(changed.get("removed"), list) else []
    changed_unique = _unique_count(changed_rows)
    added_unique = len({_clean(item).casefold() for item in added if _clean(item)})
    removed_unique = len({_clean(item).casefold() for item in removed if _clean(item)})
    return changed_unique + added_unique + removed_unique


def _area_progress(rows: list[dict], total_rows: int = 0) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = row.get("area") or row.get("phase") or row.get("trade") or "Unassigned"
        groups[key].append(row)

    result = []
    for label, items in groups.items():
        actual = sum(_sf(i.get("actual_pct")) for i in items) / max(len(items), 1)
        expected_values = [_sf(i.get("expected_pct")) for i in items if i.get("expected_pct") not in (None, "")]
        expected = sum(expected_values) / max(len(expected_values), 1) if expected_values else actual
        deviation = actual - expected
        result.append(
            {
                "label": label,
                "count": len(items),
                "actual_pct": round(actual, 1),
                "expected_pct": round(expected, 1),
                "deviation": round(deviation, 1),
            }
        )

    if not result and total_rows:
        result.append({"label": "All", "count": total_rows, "actual_pct": 0, "expected_pct": 0, "deviation": 0})
    return sorted(result, key=lambda row: (row["actual_pct"], -row["count"]))[:15]


def _graph_points_from_history(data: dict) -> dict | None:
    for key in ("progress_history", "graph_history", "historical_progress", "progress_over_time"):
        raw = data.get(key)
        if not isinstance(raw, list) or len(raw) < 2:
            continue
        planned = []
        actual = []
        forecast = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            label = _clean(item.get("label") or item.get("date") or item.get("period") or f"P{idx + 1}")
            planned_value = item.get("planned_pct", item.get("expected_pct", item.get("planned")))
            actual_value = item.get("actual_pct", item.get("actual", item.get("progress_pct")))
            forecast_value = item.get("forecast_pct", item.get("forecast"))
            if planned_value not in (None, ""):
                planned.append({"label": label, "value": round(_sf(planned_value), 1)})
            if actual_value not in (None, ""):
                actual.append({"label": label, "value": round(_sf(actual_value), 1)})
            if forecast_value not in (None, ""):
                forecast.append({"label": label, "value": round(_sf(forecast_value), 1)})
        if len(planned) >= 2 and len(actual) >= 2:
            gap = actual[-1]["value"] - planned[-1]["value"]
            return {
                "type": "progress",
                "planned": planned,
                "actual": actual,
                "forecast": forecast if len(forecast) >= 2 else [],
                "today_label": actual[-1]["label"],
                "actual_now": actual[-1]["value"],
                "planned_now": planned[-1]["value"],
                "gap": round(gap, 1),
                "history_quality": "historical",
            }
    return None


def _health_graph(data: dict, progress_rows: list[dict]) -> dict:
    historical = _graph_points_from_history(data)
    if historical:
        return historical

    sn = data.get("summary_notes", {})
    old_pct = _sf(sn.get("overall_progress_old_pct"))
    actual_now = _sf(sn.get("overall_progress_new_pct"))
    planned_now = _sf(sn.get("mean_expected_pct_all") or actual_now)
    period_old = _clean(sn.get("reporting_period_old")) or "Previous"
    period_new = _clean(sn.get("reporting_period_new")) or "Current"
    has_old = old_pct > 0
    has_current = actual_now > 0 or planned_now > 0 or bool(progress_rows)
    if not has_current:
        return {"type": "empty", "points": [], "quality": "missing_progress"}

    planned_points = []
    actual_points = []
    if has_old:
        planned_points.append({"label": period_old, "value": old_pct})
        actual_points.append({"label": period_old, "value": old_pct})
    planned_points.append({"label": period_new, "value": planned_now})
    actual_points.append({"label": period_new, "value": actual_now})

    gap = actual_now - planned_now
    return {
        "type": "progress",
        "planned": planned_points,
        "actual": actual_points,
        "forecast": [],
        "today_label": period_new,
        "actual_now": round(actual_now, 1),
        "planned_now": round(planned_now, 1),
        "gap": round(gap, 1),
        "history_quality": "two_extracts",
        "delay_label": f"{abs(round(gap))} pp behind" if gap < 0 else "",
    }


def _predictive_graph(delayed_rows: list[dict], total: int, delayed_count: int) -> dict:
    if not delayed_rows:
        return {
            "type": "progress",
            "planned": [{"label": "Now", "value": 100}],
            "actual": [{"label": "Now", "value": 100}],
            "forecast": [],
            "today_label": "Now",
            "actual_now": 100,
            "planned_now": 100,
            "gap": 0,
            "delay_label": "",
        }

    buckets = [
        ("0-7d", 0, 7),
        ("8-30d", 8, 30),
        ("31-60d", 31, 60),
        ("61-90d", 61, 90),
        ("91+d", 91, math.inf),
    ]
    points = []
    for label, lo, hi in buckets:
        count = sum(1 for row in delayed_rows if lo <= _si(row.get("days_overdue")) <= hi)
        points.append({"label": label, "value": count})
    risk_pct = round((delayed_count / max(total, 1)) * 100, 1)
    return {
        "type": "risk_buckets",
        "points": points,
        "delayed_count": delayed_count,
        "actual_now": risk_pct,
        "planned_now": 0,
        "gap": -risk_pct,
        "delay_label": f"{delayed_count} delayed",
    }


def adapt_health_dashboard(data: dict, language: str = "en") -> dict:
    es = data.get("executive_summary", {})
    sn = data.get("summary_notes", {})
    changed = data.get("changed_activities", {})
    progress_items = data.get("progress_vs_expected", [])
    stage_items = data.get("stage_mismatch", [])
    ponr_items = data.get("point_of_no_return", [])
    critical_path_items = data.get("critical_path_activities", [])

    logger.info(
        f"[version_1_0.adapters][adapt_health_dashboard] input counts: "
        f"progress_vs_expected={len(progress_items)} stage_mismatch={len(stage_items)} "
        f"point_of_no_return={len(ponr_items)} critical_path_activities={len(critical_path_items)} "
        f"changes={len(changed.get('changes', []))} "
        f"sample_progress_id={progress_items[0].get('id') if progress_items else None!r}"
    )

    behind = [_activity_row(i) for i in progress_items if str(i.get("status", "")).lower() == "behind"]
    ahead = [_activity_row(i) for i in progress_items if str(i.get("status", "")).lower() == "ahead"]
    stage_rows = [_activity_row(i) for i in stage_items]
    critical_path_rows = [_activity_row(i) for i in critical_path_items]
    changed_rows = []
    change_items = changed.get("changes", [])
    logger.info(
        f"[version_1_0.adapters][changed_activities] {len(change_items)} raw change records; "
        f"sample_act_id_source={[ (c.get('id'), c.get('activity')) for c in change_items[:5] ]!r}"
    )

    activity_diffs = diff_activities(change_items)

    for ad in activity_diffs:
        change_details = [
            {
                "field": fd.field,
                "old": fd.old,
                "new": fd.new,
                "delta_text": fd.delta,
                "tone": fd.semantic,
                "verified": fd.verify == "verified",
            }
            for fd in ad.field_diffs
        ]
        legacy_old = (
            "Multiple"
            if len(ad.field_diffs) > 1
            else (ad.field_diffs[0].old if ad.field_diffs else "-")
        )
        legacy_new = (
            "Multiple"
            if len(ad.field_diffs) > 1
            else (ad.field_diffs[0].new if ad.field_diffs else "-")
        )
        changed_rows.append(
            {
                "id": ad.activity_id,
                "source_id": ad.activity_id,
                "task_name": ad.activity_name,
                "phase": ad.phase,
                "area": ad.area,
                "floor": "",
                "location": ad.area,
                "resource": ad.trade,
                "trade": ad.trade,
                "task_type": "",
                "change_details": change_details,
                "changed_fields": list(ad.changed_fields),
                "changed_field_count": len(ad.changed_fields),
                "impact_score": ad.impact_score,
                "verify": ad.verify,
                "changes_list": [
                    f"{fd.field}: {fd.old} -> {fd.new}" for fd in ad.field_diffs
                ],
                "change_type": ", ".join(ad.changed_fields),
                "old_start": "",
                "new_start": "",
                "old_finish": "",
                "new_finish": "",
                "old_duration": "",
                "new_duration": "",
                "old": legacy_old,
                "new": legacy_new,
            }
        )

    all_rows = behind + ahead + stage_rows + changed_rows + critical_path_rows
    total = _si(es.get("selected_activities") or sn.get("total_activities"), len(all_rows))
    critical = _si(es.get("critical_count") or es.get("critical_path_count"), len(critical_path_rows))
    ponr_red = sum(1 for i in ponr_items if str(i.get("classification", "")).upper() == "RED")
    changed_count = _changed_activity_count(changed_rows, changed)
    summary = {
        "overall_progress": round(_sf(sn.get("overall_progress_new_pct") or es.get("overall_progress_pct")), 1),
        "completed_activities": _si(sn.get("finished_activities")),
        "delayed_activities": _si(sn.get("delayed_activities") or es.get("behind_schedule_count"), len(behind)),
        "total_activities": total,
        "added_activities": _si(sn.get("added_count") or es.get("added_activities")),
        "removed_activities": _si(sn.get("removed_count")),
        "reporting_period_old": _derive_schedule_date(changed_rows, "old") or _clean(sn.get("reporting_period_old") or ""),
        "reporting_period": _derive_schedule_date(all_rows, "new") or _clean(sn.get("reporting_period_new") or sn.get("reporting_period") or ""),
        "reporting_period_new": _derive_schedule_date(changed_rows, "new") or _clean(sn.get("reporting_period_new") or ""),
        "notes": _clean(es.get("health_override_reason") or es.get("data_quality_warning") or ""),
    }
    graph = _health_graph(data, progress_items)
    warnings = []
    if es.get("data_quality_warning"):
        warnings.append(es.get("data_quality_warning"))

    return {
        "mode": "health",
        "language": language,
        "status": _status_health(es.get("project_health")),
        "title_key": "health_title",
        "kpis": [
            {"key": "activities_analyzed", "value": total, "tone": "neutral"},
            {"key": "changed_table", "value": changed_count, "tone": "blue"},
            {"key": "critical_path_table", "value": critical, "tone": "red"},
            {"key": "behind_table", "value": len(behind), "tone": "red"},
            {"key": "ahead_table", "value": len(ahead), "tone": "green"},
            {"key": "point_no_return", "value": ponr_red, "tone": "red"},
        ],
        "filters": _filters(all_rows),
        "graph": graph,
        "area_progress": _area_progress([_activity_row(i) for i in progress_items], total),
        "current_extract_source": [_activity_row(i) for i in progress_items],
        "tables": {
            "behind": behind,
            "ahead": ahead,
            "changed": changed_rows,
            "stage": stage_rows,
            "critical_path": critical_path_rows,
        },
        "table_counts": {
            "changed_table": changed_count,
        },
        "summary": summary,
        "actions": [],
        "warnings": warnings,
    }


def adapt_predictive_dashboard(data: dict, language: str = "en") -> dict:
    insight = data.get("insight_data", {})
    overview = data.get("schedule_overview", {})
    delayed_raw = data.get("delayed_activities", [])
    delayed_rows = []
    task_types = []
    for item in delayed_raw:
        row = _activity_row(item, task_key="task_name")
        row["task_type"] = _clean(item.get("task_type"))
        if row["task_type"]:
            task_types.append(row["task_type"])
        delayed_rows.append(row)

    critical = [r for r in delayed_rows if r.get("priority") == "CRITICAL_NOW"]
    important = [r for r in delayed_rows if r.get("priority") == "IMPORTANT_NEXT"]
    monitor = [r for r in delayed_rows if r.get("priority") == "MONITOR"]
    total = _si(insight.get("total_activities") or overview.get("total_activities"), len(delayed_rows))
    delayed_count = len(delayed_rows)
    if total < delayed_count:
        total = delayed_count

    area_rows = []
    for entry in data.get("summary_by_area", []):
        area_rows.append(
            {
                "label": _clean(entry.get("area")),
                "count": _si(entry.get("delayed_count")),
                "actual_pct": max(0, 100 - _si(entry.get("delayed_count"))),
                "expected_pct": 100,
                "deviation": -_si(entry.get("delayed_count")),
            }
        )

    return {
        "mode": "predictive",
        "language": language,
        "status": str(insight.get("project_status", "AT_RISK")).lower(),
        "title_key": "predictive_title",
        "kpis": [
            {"key": "activities_analyzed", "value": total, "tone": "neutral"},
            {"key": "delayed_activities", "value": delayed_count, "tone": "red"},
            {"key": "critical_activities", "value": len(critical), "tone": "red"},
            {"key": "important_next", "value": len(important), "tone": "amber"},
            {"key": "monitor", "value": len(monitor), "tone": "blue"},
            {"key": "highest_risk", "value": _si(insight.get("most_overdue_days")), "tone": "red", "suffix": "d"},
        ],
        "filters": _filters(delayed_rows, task_types),
        "graph": _predictive_graph(delayed_rows, total, delayed_count),
        "area_progress": area_rows or _area_progress(delayed_rows, total),
        "current_extract_source": delayed_rows,
        "tables": {
            "critical": critical,
            "important": important,
            "monitor": monitor,
            "all_delayed": delayed_rows,
        },
        "actions": data.get("executive_actions", [])[:3],
        "root_causes": data.get("root_cause_analysis", [])[:8],
        "warnings": [],
    }
