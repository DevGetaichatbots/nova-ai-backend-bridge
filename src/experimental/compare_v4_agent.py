import logging
import json
import re
from datetime import datetime, date
from ..vector_store import vector_store_manager
from src.config import settings
from openai import AzureOpenAI
from .compare_v3_agent import (
    SCOPE_FILTER_MAP,
    _resolve_scope_prefixes,
    _activity_in_scope,
    _parse_date,
    _compute_project_health,
    _postprocess_v3,
    CompareV3Agent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Location extraction — Python-side, regex-based
# ---------------------------------------------------------------------------

_FLOOR_PAT: list[tuple] = [
    (re.compile(r'\bkælder\b', re.I),               'Basement'),
    (re.compile(r'\bbasement\b', re.I),              'Basement'),
    (re.compile(r'\bstue\b', re.I),                  'Ground Floor'),
    (re.compile(r'\bground\s*floor\b', re.I),        'Ground Floor'),
    (re.compile(r'\b(\d+)\.\s*sal\b', re.I),         lambda m: f'{m.group(1)}. Floor'),
    (re.compile(r'\betage\s+(\d+)\b', re.I),         lambda m: f'{m.group(1)}. Floor'),
    (re.compile(r'\bniveau\s+(\d+)\b', re.I),        lambda m: f'Level {m.group(1)}'),
    (re.compile(r'\b(\d+)(st|nd|rd|th)\s*fl', re.I),lambda m: f'{m.group(1)}. Floor'),
    (re.compile(r'\btag\b', re.I),                   'Roof'),
    (re.compile(r'\broof\b', re.I),                  'Roof'),
    (re.compile(r'\bpentthouse\b', re.I),            'Roof'),
]

_AREA_PAT: list[tuple] = [
    (re.compile(r'\bbygning\s+([A-Z\d]+)\b', re.I), lambda m: f'Building {m.group(1).upper()}'),
    (re.compile(r'\bbuilding\s+([A-Z\d]+)\b', re.I),lambda m: f'Building {m.group(1).upper()}'),
    (re.compile(r'\bblok\s+([A-Z\d]+)\b', re.I),    lambda m: f'Block {m.group(1).upper()}'),
    (re.compile(r'\bzone\s+([A-Z\d]+)\b', re.I),    lambda m: f'Zone {m.group(1).upper()}'),
    (re.compile(r'\bøst(?:lig)?\b', re.I),           'East Wing'),
    (re.compile(r'\beast\s*wing\b', re.I),           'East Wing'),
    (re.compile(r'\bvest(?:lig)?\b', re.I),          'West Wing'),
    (re.compile(r'\bwest\s*wing\b', re.I),           'West Wing'),
    (re.compile(r'\bnord\b|\bnorth\b', re.I),        'North Wing'),
    (re.compile(r'\bsyd\b|\bsouth\b', re.I),         'South Wing'),
]

_PHASE_PAT: list[tuple] = [
    (re.compile(r'\bfase\s+(\d+)\b', re.I),          lambda m: f'Phase {m.group(1)}'),
    (re.compile(r'\bphase\s+(\d+)\b', re.I),         lambda m: f'Phase {m.group(1)}'),
    (re.compile(r'\betape\s+(\d+)\b', re.I),         lambda m: f'Etape {m.group(1)}'),
    (re.compile(r'\bstg[\.\s](\d[\d\.]*)\b', re.I), lambda m: f'Stage {m.group(1)}'),
    (re.compile(r'\bsection\s+(\d+)\b', re.I),       lambda m: f'Section {m.group(1)}'),
    (re.compile(r'\bafsnit\s+(\d+)\b', re.I),        lambda m: f'Section {m.group(1)}'),
    (re.compile(r'\bp(\d+)[\.\-]', re.I),            lambda m: f'Phase {m.group(1)}'),
]


def _extract_location(name: str) -> dict:
    floor = area = phase = ""
    for pat, res in _FLOOR_PAT:
        m = pat.search(name)
        if m:
            floor = res(m) if callable(res) else res
            break
    for pat, res in _AREA_PAT:
        m = pat.search(name)
        if m:
            area = res(m) if callable(res) else res
            break
    for pat, res in _PHASE_PAT:
        m = pat.search(name)
        if m:
            phase = res(m) if callable(res) else res
            break
    return {"floor": floor, "area": area, "phase": phase}


def _attach_locations(items: list[dict]) -> list[dict]:
    result = []
    for item in items:
        item = dict(item)
        if "location" not in item:
            item["location"] = _extract_location(item.get("activity", ""))
        result.append(item)
    return result


def _compute_filter_options(data: dict) -> dict:
    areas: set[str] = set()
    floors: set[str] = set()
    phases: set[str] = set()
    for section in ("progress_vs_expected", "not_started_overdue", "point_of_no_return", "critical_path_activities"):
        for item in data.get(section, []):
            loc = item.get("location", {})
            if loc.get("area"):  areas.add(loc["area"])
            if loc.get("floor"): floors.add(loc["floor"])
            if loc.get("phase"): phases.add(loc["phase"])
    return {
        "areas":  sorted(areas),
        "floors": sorted(floors),
        "phases": sorted(phases),
    }


def _safe(val, default: float = 0.0) -> float:
    try:
        return float(str(val).replace("%", "").strip())
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Post-processing — extends v3 with location, CP, drivers, summary
# ---------------------------------------------------------------------------

def _postprocess_v4(
    data: dict,
    scope_prefixes: list[str],
    reference_date: str,
    old_filename: str,
    new_filename: str,
) -> dict:
    result = _postprocess_v3(data, scope_prefixes, reference_date)

    result["progress_vs_expected"] = _attach_locations(result["progress_vs_expected"])
    result["not_started_overdue"]  = _attach_locations(result["not_started_overdue"])
    result["point_of_no_return"]   = _attach_locations(result["point_of_no_return"])

    cp_raw = data.get("critical_path_activities", [])
    critical_path: list[dict] = []
    for item in cp_raw:
        if not isinstance(item, dict):
            continue
        name = item.get("activity", "")
        if scope_prefixes and not _activity_in_scope(name, scope_prefixes):
            continue
        item = dict(item)
        item.setdefault("location", _extract_location(name))
        critical_path.append(item)
    result["critical_path_activities"] = critical_path

    result["delay_drivers"] = [
        d for d in data.get("delay_drivers", []) if isinstance(d, dict)
    ][:5]

    result["filter_options"] = _compute_filter_options(result)

    sn_raw = data.get("summary_notes", {})
    progress = result["progress_vs_expected"]
    overall_new = (
        sum(_safe(i.get("actual_pct", 0)) for i in progress) / max(len(progress), 1)
        if progress else 0.0
    )
    overall_old = _safe(sn_raw.get("overall_progress_old_pct", 0))

    result["summary_notes"] = {
        "overall_progress_old_pct":  round(overall_old, 1),
        "overall_progress_new_pct":  round(overall_new, 1),
        "overall_progress_delta":    round(overall_new - overall_old, 1),
        "finished_activities":       sum(1 for i in progress if _safe(i.get("actual_pct", 0)) >= 99),
        "delayed_activities":        result["executive_summary"]["behind_schedule_count"],
        "total_activities":          result["executive_summary"]["selected_activities"],
        "added_count":               len(result["changed_activities"]["added"]),
        "removed_count":             len(result["changed_activities"]["removed"]),
        "reporting_period_old":      sn_raw.get("reporting_period_old", old_filename),
        "reporting_period_new":      sn_raw.get("reporting_period_new", reference_date),
    }

    result["executive_summary"]["critical_path_count"] = len(critical_path)
    result["executive_summary"]["overall_progress_pct"] = round(overall_new, 1)

    return result


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class CompareV4Agent(CompareV3Agent):

    def analyze(
        self,
        scope_filter: str,
        reference_date: str,
        table_names: list[str],
        session_id: str,
        old_filename: str,
        new_filename: str,
        top_k: int = 50,
    ) -> dict:
        scope_prefixes = _resolve_scope_prefixes(scope_filter)
        logger.info(f"  V4 scope filter '{scope_filter}' → prefixes: {scope_prefixes}")

        true_selected_count = 0
        trade_counts = {"EL": 0, "VVS": 0, "VENT": 0, "ARK": 0, "BYGH": 0, "ALL": 0}
        try:
            if len(table_names) > 1:
                new_table = table_names[1]
                new_chunks = vector_store_manager.fetch_all_from_stores(
                    [new_table], chunk_type="table"
                ).get(new_table, [])
                unique_names: set[str] = set()
                for chunk in new_chunks:
                    content = chunk.get("content", "")
                    for line in content.strip().split("\n"):
                        if ";" in line and "planned_start_date" not in line and "planned_start" not in line and "FORMAT:" not in line:
                            parts = line.split(";")
                            if parts:
                                name = parts[0].strip()
                                if name and _activity_in_scope(name, scope_prefixes):
                                    unique_names.add(name)
                true_selected_count = len(unique_names)
                for name in unique_names:
                    trade_counts["ALL"] += 1
                    u = name.upper()
                    if u.startswith("EL -") or u.startswith("EL-"):     trade_counts["EL"]   += 1
                    if u.startswith("VVS -") or u.startswith("VVS-"):   trade_counts["VVS"]  += 1
                    if u.startswith("VENT -") or u.startswith("VENT-"): trade_counts["VENT"] += 1
                    if u.startswith("ARK -") or u.startswith("ARK-"):   trade_counts["ARK"]  += 1
                    if u.startswith("BYGH -") or u.startswith("BYGH-"): trade_counts["BYGH"] += 1
                logger.info(f"  V4 true selected count: {true_selected_count} (trades: {trade_counts})")
        except Exception as ex:
            logger.error(f"V4 activity count error: {ex}")

        context, total_chunks = self._retrieve_context(table_names, old_filename, new_filename)

        prefix_hint = ""
        if scope_prefixes:
            prefix_hint = (
                f"\nACTIVITY PREFIX WHITELIST (STRICT): Only include activities whose names start with "
                f"one of these prefixes (case-insensitive): {', '.join(scope_prefixes)}\n"
                f"EXCLUDE any activity that does NOT start with one of these prefixes.\n"
            )

        ref_day   = reference_date.split('-')[0] if '-' in reference_date else '?'
        ref_month = reference_date.split('-')[1] if '-' in reference_date else '?'

        system_prompt = f"""You are a strict data-extraction parser for construction project schedules. Output ONLY valid JSON. No markdown, no code fences, no explanation.

DATE FORMAT: All dates in the data and the reference date use DD-MM-YYYY format (day first).
Reference date {reference_date} means day {ref_day}, month {ref_month} — parse accordingly.

=== SCOPE RULES ===
{prefix_hint}
Scope filter: "{scope_filter}"
- Only process activities whose names begin with the whitelisted prefixes.
- Do NOT invent or extrapolate activity names not verbatim in the data.

=== SECTION 1: executive_summary ===
- selected_activities: count of in-scope activities found in the NEW schedule.
- added_activities: count of activities in NEW but not in OLD.
- recommended_action: ONE short management sentence naming the single most urgent activity. No fluff.
- Leave project_health, behind_schedule_count, ahead_of_schedule_count, critical_count, point_of_no_return_count as 0/"Green" — computed server-side.

=== SECTION 2: changed_activities ===
- added: activity names present in NEW but completely absent from OLD.
- removed: activity names present in OLD but completely absent from NEW.
- changes: For each activity where start date, finish date, or duration differs between schedules, emit one row per changed field.
  change_type must be exactly one of: "Duration", "Start Date", "Finish Date".
  OMIT any entry where old == new. One row per changed field.

=== SECTION 3: not_started_overdue ===
Activities in NEW schedule where % complete == 0 AND start_date < reference date ({reference_date}).
Fields: id (string or ""), activity, start_date, finish_date, progress_pct (must be 0).

=== SECTION 4: progress_vs_expected — MANDATORY, DO NOT SKIP ===
For EVERY in-scope activity in the NEW schedule that has a start_date and finish_date:
  Step 1: Parse reference_date, start_date, finish_date as DD-MM-YYYY.
  Step 2: elapsed_days = reference_date - start_date (in calendar days).
  Step 3: total_days = finish_date - start_date (in calendar days).
  Step 4: expected_pct = (elapsed_days / total_days) × 100, clamped to [0, 100].
  Step 5: actual_pct = the % complete value from the NEW schedule data.
  Step 6: variance_pct = actual_pct - expected_pct (negative means behind schedule).
  Step 7: status = "behind" if variance_pct < -5, "ahead" if variance_pct > 5, else "on_schedule".
  Include ALL activities where |variance_pct| >= 1. If an activity's start is after reference_date, skip it.
Fields: activity, start_date, finish_date, actual_pct (number), expected_pct (number, rounded to 1 decimal), variance_pct (number, rounded to 1 decimal), status.

=== SECTION 5: stage_mismatch — MANDATORY, DO NOT SKIP ===
Re-use the same calculation from Section 4.
  difference_pct = actual_pct - expected_pct.
  status: "Critical Mismatch" if |difference_pct| >= 50, "Mismatch" if |difference_pct| >= 10, "OK" otherwise.
  Include ALL in-scope activities (even OK ones).
Fields: activity, actual_pct (number), expected_pct (number), difference_pct (number), status.

=== SECTION 6: point_of_no_return ===
For each activity where status == "behind" in Section 4:
  remaining_days = finish_date - reference_date (calendar days).
  work_remaining_pct = 100 - actual_pct.
  If remaining_days <= 0: classification = "Red", assessment = "POINT OF NO RETURN".
  Else if work_remaining_pct / remaining_days > 2 × (expected_pct / elapsed_days): classification = "Red".
  Else if work_remaining_pct / remaining_days > 1.5 × (expected_pct / elapsed_days): classification = "Yellow".
  Else: classification = "Green".
  recommendation: ONE action sentence.
Fields: activity, actual_pct, expected_pct, variance_pct, remaining_time (e.g. "14 days"), classification, assessment ("POINT OF NO RETURN"|"HIGH RISK"|"RECOVERABLE"), recommendation.

=== SECTION 7: action_recommendations ===
For each activity classified "Red" in Section 6, OR "Critical Mismatch" in Section 5:
  issue: one-line description of the problem.
  actions: array of 3–5 short action strings (no prose, no numbering).
Fields: activity, issue, actions.

=== SECTION 8: critical_path_activities ===
Identify in-scope activities on the Critical Path (zero or near-zero total float/slack).
Look for explicit "Total Float" = 0, "Free Float" = 0, or activities marked "Critical" in the data.
If no float data is available, identify activities whose delay would directly delay the project completion date (the longest dependency chain).
Include only in-scope activities. Limit to the 20 most critical.
Fields: activity, start_date, finish_date, actual_pct (number), float_days (number, use 0 if on critical path).

=== SECTION 9: delay_drivers ===
Identify the top 3-5 root causes of schedule delays visible across the data.
Focus on trade-wide or area-wide patterns (not individual activities).
Example: "VVS plumbing behind across multiple floors", "Phase 2 not yet started".
Fields: driver (short label, max 60 chars), description (1 clear sentence), affected_count (integer).

=== SECTION 10: summary_notes ===
From the OLD schedule data only, extract:
  - overall_progress_old_pct: average % complete across all OLD schedule activities (number)
  - reporting_period_old: date label of the OLD schedule (string, e.g. "01-03-2026")
  - reporting_period_new: date label of the NEW schedule (string, e.g. "31-05-2026")
These three fields only — all other summary metrics are computed server-side.

=== OUTPUT FORMAT ===
{{
  "executive_summary": {{
    "project_health": "Green",
    "selected_activities": 0,
    "added_activities": 0,
    "behind_schedule_count": 0,
    "ahead_of_schedule_count": 0,
    "critical_count": 0,
    "point_of_no_return_count": 0,
    "recommended_action": ""
  }},
  "changed_activities": {{
    "added": [],
    "removed": [],
    "changes": [{{"activity": "", "change_type": "", "old": "", "new": ""}}]
  }},
  "not_started_overdue": [{{"id": "", "activity": "", "start_date": "", "finish_date": "", "progress_pct": 0}}],
  "progress_vs_expected": [{{"activity": "", "start_date": "", "finish_date": "", "actual_pct": 0, "expected_pct": 0, "variance_pct": 0, "status": ""}}],
  "stage_mismatch": [{{"activity": "", "actual_pct": 0, "expected_pct": 0, "difference_pct": 0, "status": ""}}],
  "point_of_no_return": [{{"activity": "", "actual_pct": 0, "expected_pct": 0, "variance_pct": 0, "remaining_time": "", "classification": "", "assessment": "", "recommendation": ""}}],
  "action_recommendations": [{{"activity": "", "issue": "", "actions": []}}],
  "critical_path_activities": [{{"activity": "", "start_date": "", "finish_date": "", "actual_pct": 0, "float_days": 0}}],
  "delay_drivers": [{{"driver": "", "description": "", "affected_count": 0}}],
  "summary_notes": {{"overall_progress_old_pct": 0, "reporting_period_old": "", "reporting_period_new": ""}}
}}
"""

        user_prompt = f"""SCOPE FILTER: {scope_filter}
REFERENCE DATE: {reference_date}

SCHEDULE DATA:
{context}

Extract all sections per the rules above. Output ONLY the JSON object."""

        logger.info(f"  Calling Azure OpenAI ({settings.AZURE_OPENAI_CHAT_DEPLOYMENT}) for Compare V4...")

        try:
            response = self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0,
                top_p=0.1,
                seed=42,
                max_tokens=16384,
            )
            text = response.choices[0].message.content or ""
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]

            data = json.loads(text.strip())
            data = _postprocess_v4(data, scope_prefixes, reference_date, old_filename, new_filename)
            if true_selected_count > 0:
                data["executive_summary"]["selected_activities"] = true_selected_count
                data["executive_summary"]["trade_counts"] = trade_counts

            logger.info(
                f"  V4 complete: cp={len(data['critical_path_activities'])}, "
                f"drivers={len(data['delay_drivers'])}, "
                f"filters={data['filter_options']}, "
                f"health={data['executive_summary']['project_health']}"
            )
            return {"json": data, "context_chunks": total_chunks}

        except Exception as e:
            logger.error(f"Error in CompareV4Agent: {e}")
            es = {
                "project_health": "Red",
                "selected_activities": true_selected_count or 0,
                "added_activities": 0,
                "behind_schedule_count": 0,
                "ahead_of_schedule_count": 0,
                "critical_count": 0,
                "critical_path_count": 0,
                "point_of_no_return_count": 0,
                "overall_progress_pct": 0,
                "recommended_action": "Analysis failed — please retry.",
            }
            empty: dict = {
                "executive_summary": es,
                "changed_activities": {"added": [], "removed": [], "changes": []},
                "not_started_overdue": [],
                "progress_vs_expected": [],
                "stage_mismatch": [],
                "point_of_no_return": [],
                "action_recommendations": [],
                "critical_path_activities": [],
                "delay_drivers": [],
                "summary_notes": {
                    "overall_progress_old_pct": 0,
                    "overall_progress_new_pct": 0,
                    "overall_progress_delta": 0,
                    "finished_activities": 0,
                    "delayed_activities": 0,
                    "total_activities": 0,
                    "added_count": 0,
                    "removed_count": 0,
                    "reporting_period_old": old_filename,
                    "reporting_period_new": reference_date,
                },
                "filter_options": {"areas": [], "floors": [], "phases": []},
                "error": str(e),
            }
            return {"json": empty, "context_chunks": 0}


compare_v4_agent = CompareV4Agent()
