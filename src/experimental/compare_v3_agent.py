import logging
import json
from datetime import datetime, date
from ..vector_store import vector_store_manager
from src.config import settings
from openai import AzureOpenAI

logger = logging.getLogger(__name__)

SCOPE_FILTER_MAP = {
    "electrical": ["EL -", "EL-", "TEK -", "TEK-", "SOLCELLER", "LODRET FØRING", "FØRINGSVEJE", "LAVSPÆNDING", "BELYSNING", "SVAGSTRØM"],
    "electric":   ["EL -", "EL-", "TEK -", "TEK-"],
    "el":         ["EL -", "EL-"],
    "bms":        ["TEK -", "TEK-", "BMS"],
    "automation": ["TEK -", "TEK-", "BMS"],
    "plumbing":   ["VVS -", "VVS-", "GULVVARME", "FALDSTAMME", "AFLØB", "SKAKTE", "RØR", "VARME", "VAND"],
    "vvs":        ["VVS -", "VVS-"],
    "sanitary":   ["VVS -", "VVS-"],
    "water":      ["VVS -", "VVS-"],
    "heating":    ["VVS -", "VVS-", "GULVVARME", "VARME"],
    "concrete":   ["BE -", "BE-", "BET -", "BETON"],
    "structural": ["KL -", "KL-", "STÅL", "ELEMENT", "ELEM -", "ELEM-"],
    "masonry":    ["MU -", "MU-", "MU2 -", "MURVÆRK"],
    "brickwork":  ["MU -", "MU-", "MU2 -"],
    "carpentry":  ["TØ -", "TØ-", "TRÆ", "VINDUE"],
    "windows":    ["TØ -", "TØ-", "VINDUE"],
    "flooring":   ["GU -", "GU-", "GULV", "TERMOGULV", "TRÆGULV"],
    "painting":   ["MAL -", "MAL-"],
    "facade":     ["FAC -", "FAC-", "SKALMURING"],
    "roofing":    ["TAG -", "TAG-", "PAP"],
    "interior":   ["INV -", "INV-", "INVENTAR", "MONTAGE"],
    "elements":   ["ELEM -", "ELEM-", "ELEMENT"],
}


def _resolve_scope_prefixes(scope_filter: str) -> list[str]:
    filter_lower = scope_filter.lower()
    prefixes = []
    for keyword, codes in SCOPE_FILTER_MAP.items():
        if keyword in filter_lower:
            prefixes.extend(codes)
    seen = set()
    result = []
    for p in prefixes:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _activity_in_scope(name: str, prefixes: list[str]) -> bool:
    if not prefixes:
        return True
    name_upper = name.upper()
    for p in prefixes:
        if name_upper.startswith(p.upper()) or p.upper() in name_upper:
            return True
    return False


def _parse_date(val: str) -> date | None:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _compute_project_health(data: dict) -> str:
    ponr = data.get("point_of_no_return", [])
    for item in ponr:
        if str(item.get("classification", "")).upper() == "RED":
            return "Red"
    not_started = data.get("not_started_overdue", [])
    stage_mismatch = [
        i for i in data.get("stage_mismatch", [])
        if "mismatch" in str(i.get("status", "")).lower()
    ]
    progress = [
        i for i in data.get("progress_vs_expected", [])
        if str(i.get("status", "")).lower() == "behind"
    ]
    if not_started or stage_mismatch or progress:
        return "Yellow"
    return "Green"


def _postprocess_v3(data: dict, scope_prefixes: list[str], reference_date: str) -> dict:
    def _in_scope(name: str) -> bool:
        return _activity_in_scope(name, scope_prefixes)

    def _dedup(lst, key_fn):
        seen = set()
        out = []
        for item in lst:
            k = key_fn(item)
            if k not in seen:
                seen.add(k)
                out.append(item)
        return out

    # changed_activities
    changes_raw = data.get("changed_activities", {})
    added = [a for a in changes_raw.get("added", []) if isinstance(a, str) and _in_scope(a)]
    removed = [a for a in changes_raw.get("removed", []) if isinstance(a, str) and _in_scope(a)]

    added_set = {a.upper() for a in added}
    _valid_change_types = {"duration", "start date", "finish date"}

    flat_changes = []
    for item in changes_raw.get("changes", []):
        if not isinstance(item, dict):
            continue
        name = item.get("activity", "")
        # Skip if this activity is newly added — it has no old values to compare
        if name.upper() in added_set:
            continue
        # Only allow schedule-relevant change types
        ctype = str(item.get("change_type", "")).strip().lower()
        if ctype not in _valid_change_types:
            continue
        old_val = str(item.get("old", "")).strip()
        new_val = str(item.get("new", "")).strip()
        if old_val == new_val:
            continue
        # Require both old and new values to be present
        if not old_val or not new_val:
            continue
        if not _in_scope(name):
            continue
        flat_changes.append(item)
    flat_changes = _dedup(flat_changes, lambda i: f"{i.get('activity')}|{i.get('change_type')}|{i.get('old')}|{i.get('new')}")

    # not_started_overdue — enforce the rule in Python regardless of LLM output
    ref = _parse_date(reference_date) if reference_date and reference_date != "Unknown" else None
    not_started = []
    for item in data.get("not_started_overdue", []):
        if not isinstance(item, dict):
            continue
        name = item.get("activity", "")
        if not _in_scope(name):
            continue
        pct = item.get("progress_pct", item.get("progress", -1))
        try:
            pct = float(str(pct).replace("%", ""))
        except (ValueError, TypeError):
            pct = -1
        if pct != 0:
            continue
        if ref:
            start = _parse_date(str(item.get("start_date", "")))
            if start and start >= ref:
                continue  # hasn't missed its start yet
        not_started.append(item)
    not_started = _dedup(not_started, lambda i: i.get("activity", ""))

    # progress_vs_expected
    progress = []
    for item in data.get("progress_vs_expected", []):
        if not isinstance(item, dict):
            continue
        if _in_scope(item.get("activity", "")):
            progress.append(item)
    progress = _dedup(progress, lambda i: i.get("activity", ""))
    # Sort: most negative variance first
    def _var_float(i):
        try:
            return float(str(i.get("variance_pct", "0")).replace("%", ""))
        except (ValueError, TypeError):
            return 0
    progress.sort(key=_var_float)

    # stage_mismatch
    mismatch = []
    for item in data.get("stage_mismatch", []):
        if not isinstance(item, dict):
            continue
        if _in_scope(item.get("activity", "")):
            mismatch.append(item)
    mismatch = _dedup(mismatch, lambda i: i.get("activity", ""))

    # point_of_no_return — enforce classification↔assessment consistency
    _ponr_map = {
        "RED":    "POINT OF NO RETURN",
        "YELLOW": "HIGH RISK",
        "GREEN":  "RECOVERABLE",
    }
    ponr = []
    for item in data.get("point_of_no_return", []):
        if not isinstance(item, dict):
            continue
        if not _in_scope(item.get("activity", "")):
            continue
        cls = str(item.get("classification", "")).strip().upper()
        if cls not in _ponr_map:
            cls = "YELLOW"  # default to high risk if LLM returned garbage
        item = dict(item)
        item["classification"] = cls.capitalize() if cls != "RED" else "Red"
        item["classification"] = {"RED": "Red", "YELLOW": "Yellow", "GREEN": "Green"}[cls]
        item["assessment"] = _ponr_map[cls]
        ponr.append(item)
    ponr = _dedup(ponr, lambda i: i.get("activity", ""))

    # action_recommendations
    actions = []
    for item in data.get("action_recommendations", []):
        if not isinstance(item, dict):
            continue
        if _in_scope(item.get("activity", "")):
            actions.append(item)
    actions = _dedup(actions, lambda i: i.get("activity", ""))

    result = {
        "changed_activities": {
            "added": added,
            "removed": removed,
            "changes": flat_changes,
        },
        "not_started_overdue": not_started,
        "progress_vs_expected": progress,
        "stage_mismatch": mismatch,
        "point_of_no_return": ponr,
        "action_recommendations": actions,
    }

    # executive_summary — compute counts Python-side, not from LLM
    es_raw = data.get("executive_summary", {})
    behind_count = sum(1 for i in progress if str(i.get("status", "")).lower() == "behind")
    ahead_count = sum(1 for i in progress if str(i.get("status", "")).lower() == "ahead")
    critical_count = sum(
        1 for i in ponr
        if str(i.get("classification", "")).upper() in ("RED", "YELLOW")
    )
    ponr_red_count = sum(1 for i in ponr if str(i.get("classification", "")).upper() == "RED")

    result["executive_summary"] = {
        "project_health": _compute_project_health(result),
        "selected_activities": es_raw.get("selected_activities", len(progress) + len(not_started)),
        "added_activities": len(added),
        "behind_schedule_count": behind_count,
        "ahead_of_schedule_count": ahead_count,
        "critical_count": critical_count,
        "point_of_no_return_count": ponr_red_count,
        "recommended_action": es_raw.get("recommended_action", ""),
    }

    return result


class CompareV3Agent:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

    def _get_doc_label(self, table_name: str, old_filename: str, new_filename: str) -> str:
        if old_filename and ('old' in table_name.lower() or old_filename in table_name):
            return f"OLD Schedule ({old_filename})"
        return f"NEW Schedule ({new_filename})"

    def _retrieve_context(self, table_names: list[str], old_filename: str, new_filename: str) -> tuple[str, int]:
        logger.info(f"  Fetching all table chunks from {len(table_names)} stores for Compare V3...")
        all_table_results = vector_store_manager.fetch_all_from_stores(table_names, chunk_type="table")

        MAX_CONTEXT_BYTES = 1_900_000
        per_store_budget = MAX_CONTEXT_BYTES // max(len(table_names), 1)

        context_parts = []
        total_chunks = 0
        total_skipped = 0

        for table_name in table_names:
            doc_label = self._get_doc_label(table_name, old_filename, new_filename)
            table_results = all_table_results.get(table_name, {})

            if isinstance(table_results, dict) and "error" in table_results:
                context_parts.append(f"\n[{doc_label}: {table_name}]\nError: {table_results['error']}\n")
                continue

            results = list(table_results) if table_results else []
            if not results:
                context_parts.append(f"\n[{doc_label}: {table_name}]\nNo data chunks found.\n")
                continue

            store_parts = []
            store_bytes = 0
            included = 0
            skipped = 0

            for i, result in enumerate(results, 1):
                chunk_text = f"--- Data {i} ---\n{result['content']}\n"
                chunk_bytes = len(chunk_text.encode("utf-8"))
                if store_bytes + chunk_bytes > per_store_budget:
                    skipped += 1
                    continue
                store_parts.append(chunk_text)
                store_bytes += chunk_bytes
                included += 1

            total_chunks += included
            total_skipped += skipped
            label = f"\n[{doc_label}: {table_name}] — {included} chunks"
            if skipped:
                label += f" [WARNING: {skipped} chunks omitted — exceeds size limit]"
            context_parts.append(label)
            context_parts.extend(store_parts)

        if total_skipped:
            logger.warning(f"  Context truncated: {total_chunks} chunks sent, {total_skipped} omitted")
        else:
            logger.info(f"  Chunks sent to LLM: {total_chunks}")

        return "\n\n".join(context_parts), total_chunks

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
        logger.info(f"  Scope filter '{scope_filter}' resolved to prefixes: {scope_prefixes}")

        # Count true selected activities in python from vector store
        true_selected_count = 0
        trade_counts = {"EL": 0, "VVS": 0, "VENT": 0, "ARK": 0, "BYGH": 0, "ALL": 0}
        try:
            if len(table_names) > 1:
                new_table = table_names[1]
                new_chunks = vector_store_manager.fetch_all_from_stores([new_table], chunk_type="table").get(new_table, [])
                unique_names = set()
                for chunk in new_chunks:
                    content = chunk.get("content", "")
                    for line in content.strip().split('\n'):
                        if ';' in line and 'planned_start_date' not in line and 'FORMAT:' not in line:
                            parts = line.split(';')
                            if parts:
                                name = parts[0].strip()
                                if name and _activity_in_scope(name, scope_prefixes):
                                    unique_names.add(name)
                
                true_selected_count = len(unique_names)
                
                # Also calculate trade counts for the dashboard JS filter
                for name in unique_names:
                    trade_counts["ALL"] += 1
                    u_name = name.upper()
                    if u_name.startswith("EL -") or u_name.startswith("EL-"): trade_counts["EL"] += 1
                    if u_name.startswith("VVS -") or u_name.startswith("VVS-"): trade_counts["VVS"] += 1
                    if u_name.startswith("VENT -") or u_name.startswith("VENT-"): trade_counts["VENT"] += 1
                    if u_name.startswith("ARK -") or u_name.startswith("ARK-"): trade_counts["ARK"] += 1
                    if u_name.startswith("BYGH -") or u_name.startswith("BYGH-"): trade_counts["BYGH"] += 1
                
                logger.info(f"  Computed true selected activities count Python-side: {true_selected_count} (Trades: {trade_counts})")
        except Exception as ex:
            logger.error(f"Error computing true selected activities: {ex}")

        context, total_chunks = self._retrieve_context(table_names, old_filename, new_filename)

        prefix_hint = ""
        if scope_prefixes:
            prefix_hint = (
                f"\nACTIVITY PREFIX WHITELIST (STRICT): Only include activities whose names start with "
                f"one of these prefixes (case-insensitive): {', '.join(scope_prefixes)}\n"
                f"EXCLUDE any activity that does NOT start with one of these prefixes.\n"
            )

        system_prompt = f"""You are a strict data-extraction parser for construction project schedules. Output ONLY valid JSON. No markdown, no code fences, no explanation.

DATE FORMAT: All dates in the data and the reference date use DD-MM-YYYY format (day first).
Reference date {reference_date} means day {reference_date.split('-')[0]}, month {reference_date.split('-')[1] if '-' in reference_date else '?'} — parse accordingly.

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
- changes: MANDATORY — compare OLD vs NEW for every in-scope activity. For each activity where start date, finish date, or duration differs between schedules, emit one row per changed field.
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
Re-use the same calculation from Section 4. For every activity computed above:
  difference_pct = actual_pct - expected_pct (same as variance_pct).
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
  "action_recommendations": [{{"activity": "", "issue": "", "actions": []}}]
}}
"""

        user_prompt = f"""SCOPE FILTER: {scope_filter}
REFERENCE DATE: {reference_date}

SCHEDULE DATA:
{context}

Extract all sections per the rules above. Output ONLY the JSON object."""

        logger.info(f"  Calling Azure OpenAI ({settings.AZURE_OPENAI_CHAT_DEPLOYMENT}) for Compare V3...")

        try:
            response = self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
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
            data = _postprocess_v3(data, scope_prefixes, reference_date)
            if true_selected_count > 0:
                data["executive_summary"]["selected_activities"] = true_selected_count
                data["executive_summary"]["trade_counts"] = trade_counts

            logger.info(
                f"  V3 post-processed: "
                f"added={len(data['changed_activities']['added'])}, "
                f"removed={len(data['changed_activities']['removed'])}, "
                f"changes={len(data['changed_activities']['changes'])}, "
                f"not_started={len(data['not_started_overdue'])}, "
                f"progress={len(data['progress_vs_expected'])}, "
                f"mismatch={len(data['stage_mismatch'])}, "
                f"ponr={len(data['point_of_no_return'])}, "
                f"actions={len(data['action_recommendations'])}, "
                f"health={data['executive_summary']['project_health']}"
            )

            return {"json": data, "context_chunks": total_chunks}

        except Exception as e:
            logger.error(f"Error in CompareV3Agent: {e}")
            empty: dict = {
                "executive_summary": {
                    "project_health": "Red",
                    "selected_activities": true_selected_count or 0,
                    "added_activities": 0,
                    "behind_schedule_count": 0,
                    "ahead_of_schedule_count": 0,
                    "critical_count": 0,
                    "point_of_no_return_count": 0,
                    "recommended_action": "Analysis failed — please retry.",
                },
                "changed_activities": {"added": [], "removed": [], "changes": []},
                "not_started_overdue": [],
                "progress_vs_expected": [],
                "stage_mismatch": [],
                "point_of_no_return": [],
                "action_recommendations": [],
                "error": str(e),
            }
            return {"json": empty, "context_chunks": 0}


compare_v3_agent = CompareV3Agent()