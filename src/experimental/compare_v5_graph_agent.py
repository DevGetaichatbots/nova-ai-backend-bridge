"""
compare_v5_graph_agent.py
=========================
Analysis agent for the v5 graph dashboard variant.

The graph dashboard uses the same JSON contract as v5. The difference is the
formatter: the dashboard renders the Overall Progress curve from
summary_notes and progress_vs_expected.
"""

from __future__ import annotations

import json
import logging
import re

from ..vector_store import vector_store_manager
from src.config import settings
from .compare_v4_agent import CompareV4Agent
from .nusf_compare_engine import build_progress_history_from_nusf_sources, compare_nusf_chunks, parse_nusf_chunks


logger = logging.getLogger(__name__)


def _top_items(items: list[dict], limit: int = 25) -> list[dict]:
    return items[:limit] if isinstance(items, list) else []


def _clean_json_response(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip() or "{}")


def _trade_code_from_text(value: str) -> str | None:
    text = str(value or "").upper()
    if text.startswith("EL -") or text.startswith("EL-") or "ELECTRICAL" in text:
        return "EL"
    if text.startswith("VVS -") or text.startswith("VVS-") or "PLUMBING" in text:
        return "VVS"
    if text.startswith("VENT -") or text.startswith("VENT-") or "VENTILATION" in text:
        return "VENT"
    if text.startswith("ARK -") or text.startswith("ARK-") or "ARCHITECTURE" in text:
        return "ARK"
    if text.startswith("BYGH -") or text.startswith("BYGH-") or "CIVIL" in text:
        return "BYGH"
    return None


def _norm_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _merge_location(existing: dict, proposed: dict) -> dict:
    existing = existing if isinstance(existing, dict) else {}
    proposed = proposed if isinstance(proposed, dict) else {}
    return {
        "area": existing.get("area") or proposed.get("area", ""),
        "floor": existing.get("floor") or proposed.get("floor", ""),
        "phase": existing.get("phase") or proposed.get("phase", ""),
    }


def _recompute_filters(data: dict) -> None:
    areas: set[str] = set(data.get("filter_options", {}).get("areas", []))
    floors: set[str] = set(data.get("filter_options", {}).get("floors", []))
    phases: set[str] = set(data.get("filter_options", {}).get("phases", []))
    for section in ("progress_vs_expected", "not_started_overdue", "point_of_no_return", "critical_path_activities", "action_recommendations"):
        for item in data.get(section, []):
            loc = item.get("location", {}) if isinstance(item, dict) else {}
            if loc.get("area"):
                areas.add(loc["area"])
            if loc.get("floor"):
                floors.add(loc["floor"])
            if loc.get("phase"):
                phases.add(loc["phase"])
    data["filter_options"] = {"areas": sorted(areas), "floors": sorted(floors), "phases": sorted(phases)}


def _apply_activity_enrichment(data: dict, enrichments: list[dict]) -> None:
    if not enrichments:
        return

    by_name = {
        _norm_name(item.get("activity")): item
        for item in enrichments
        if isinstance(item, dict) and item.get("activity")
    }
    seen_trade_names: set[str] = set()

    for section in ("progress_vs_expected", "not_started_overdue", "point_of_no_return", "critical_path_activities", "action_recommendations"):
        for item in data.get(section, []):
            if not isinstance(item, dict):
                continue
            key = _norm_name(item.get("activity"))
            enrichment = by_name.get(key)
            if not enrichment:
                continue
            item["location"] = _merge_location(item.get("location", {}), enrichment.get("location", {}))
            trade_code = str(enrichment.get("trade_code") or "").upper()
            if trade_code in {"EL", "VVS", "VENT", "ARK", "BYGH"}:
                item["trade_code"] = trade_code
                if not _trade_code_from_text(item.get("activity", "")):
                    seen_trade_names.add(f"{trade_code}:{key}")

    trade_counts = data.get("executive_summary", {}).get("trade_counts", {})
    for marker in seen_trade_names:
        trade_code = marker.split(":", 1)[0]
        trade_counts[trade_code] = int(trade_counts.get(trade_code, 0)) + 1

    _recompute_filters(data)


def _merge_llm_analysis(base: dict, llm_data: dict) -> dict:
    if not isinstance(llm_data, dict):
        return base

    llm_summary = llm_data.get("executive_summary", {})
    recommended_action = str(llm_summary.get("recommended_action", "")).strip() if isinstance(llm_summary, dict) else ""
    if recommended_action:
        base["executive_summary"]["recommended_action"] = recommended_action

    for key in ("delay_drivers", "action_recommendations"):
        value = llm_data.get(key)
        if isinstance(value, list) and value:
            base[key] = value

    critical_path = llm_data.get("critical_path_activities")
    if isinstance(critical_path, list) and critical_path:
        base["critical_path_activities"] = critical_path
        base["executive_summary"]["critical_path_count"] = len(critical_path)
        base["executive_summary"]["critical_count"] = len(critical_path)

    health_override = str(llm_data.get("project_health_override", "")).strip()
    if health_override in ("Red", "Yellow", "Green"):
        base["executive_summary"]["project_health"] = health_override
        reason = str(llm_data.get("health_override_reason", "")).strip()
        if reason:
            base["executive_summary"]["health_override_reason"] = reason

    enrichments = llm_data.get("activity_enrichment")
    if isinstance(enrichments, list):
        _apply_activity_enrichment(base, enrichments)

    return base


def _build_llm_packet(data: dict, reference_date: str, old_filename: str, new_filename: str) -> dict:
    return {
        "reference_date": reference_date,
        "old_filename": old_filename,
        "new_filename": new_filename,
        "deterministic_summary": data.get("executive_summary", {}),
        "summary_notes": data.get("summary_notes", {}),
        "filter_options": data.get("filter_options", {}),
        "changed_activities": {
            "added": data.get("changed_activities", {}).get("added", [])[:25],
            "removed": data.get("changed_activities", {}).get("removed", [])[:25],
            "changes": _top_items(data.get("changed_activities", {}).get("changes", []), 50),
        },
        "top_behind": _top_items(
            sorted(
                [i for i in data.get("progress_vs_expected", []) if i.get("status") == "behind"],
                key=lambda item: float(item.get("variance_pct", 0)),
            ),
            50,
        ),
        "top_ahead": _top_items([i for i in data.get("progress_vs_expected", []) if i.get("status") == "ahead"], 25),
        "not_started_overdue": _top_items(data.get("not_started_overdue", []), 50),
        "point_of_no_return": _top_items(data.get("point_of_no_return", []), 50),
        "stage_mismatch": _top_items(
            [i for i in data.get("stage_mismatch", []) if str(i.get("status", "")).lower() != "ok"],
            50,
        ),
        "all_activities": _top_items(data.get("_activity_index", []), 150),
    }


class CompareV5GraphAgent(CompareV4Agent):
    """V5 graph variant of the comparison agent."""

    def analyze(
        self,
        scope_filter: str,
        reference_date: str,
        table_names: list[str],
        session_id: str,
        old_filename: str,
        new_filename: str,
        top_k: int = 50,
        require_nusf: bool = False,
        language: str = "en",
        history_labels: dict[str, str] | None = None,
    ) -> dict:
        old_chunks: list[dict] = []
        new_chunks: list[dict] = []

        try:
            if len(table_names) >= 2:
                fetched = vector_store_manager.fetch_all_from_stores(table_names, chunk_type="table")
                old_chunks = fetched.get(table_names[0], [])
                new_chunks = fetched.get(table_names[1], [])
                old_rows = parse_nusf_chunks(old_chunks)
                new_rows = parse_nusf_chunks(new_chunks)
                if require_nusf and not old_rows:
                    raise RuntimeError(
                        f"NUSF mode requested but OLD schedule '{old_filename}' is not stored as valid NUSF"
                    )
                if require_nusf and not new_rows:
                    raise RuntimeError(
                        f"NUSF mode requested but NEW schedule '{new_filename}' is not stored as valid NUSF"
                    )
                if old_rows and new_rows:
                    deterministic_data = compare_nusf_chunks(old_chunks, new_chunks, reference_date)
                    history_sources = []
                    history_labels = history_labels or {}
                    for idx, table_name in enumerate(table_names):
                        chunks = fetched.get(table_name, [])
                        if not isinstance(chunks, list):
                            continue
                        if idx == 0:
                            label = old_filename or table_name
                        elif idx == 1:
                            label = new_filename or table_name
                        else:
                            label = history_labels.get(table_name) or table_name
                        history_sources.append((label, chunks))
                    progress_history = build_progress_history_from_nusf_sources(history_sources, reference_date)
                    if progress_history:
                        deterministic_data["progress_history"] = progress_history
                    logger.info("  V5 graph deterministic NUSF facts computed")
                    try:
                        llm_data = self._analyze_nusf_with_llm(
                            deterministic_data,
                            reference_date,
                            old_filename,
                            new_filename,
                            language,
                        )
                        deterministic_data = _merge_llm_analysis(deterministic_data, llm_data)
                        logger.info("  V5 graph LLM NUSF enrichment complete")
                    except Exception as ex:
                        logger.error(f"V5 graph LLM NUSF enrichment failed; using deterministic fallback: {ex}")
                    deterministic_data.pop("_activity_index", None)
                    return {
                        "json": deterministic_data,
                        "context_chunks": len(old_chunks) + len(new_chunks),
                    }
        except Exception as ex:
            logger.error(f"V5 graph deterministic NUSF comparison skipped: {ex}")
            if require_nusf:
                raise

        return super().analyze(
            scope_filter=scope_filter,
            reference_date=reference_date,
            table_names=table_names,
            session_id=session_id,
            old_filename=old_filename,
            new_filename=new_filename,
            top_k=top_k,
            require_nusf=require_nusf,
            language=language,
        )

    def _analyze_nusf_with_llm(
        self,
        deterministic_data: dict,
        reference_date: str,
        old_filename: str,
        new_filename: str,
        language: str = "en",
    ) -> dict:
        packet = _build_llm_packet(deterministic_data, reference_date, old_filename, new_filename)
        language_prompt = (
            "OUTPUT LANGUAGE: Danish. Generate all free-text values in Danish. "
            "Keep JSON keys, enum values, trade codes, and field names unchanged.\n\n"
            if language == "da" else
            "OUTPUT LANGUAGE: English. Generate all free-text values in English. "
            "Keep JSON keys, enum values, trade codes, and field names unchanged.\n\n"
        )
        system_prompt = language_prompt + """You are Nova Insight's senior construction schedule analyst.
The schedule rows have already been normalized to NUSF and exact counts/math have been computed server-side.
Use the provided deterministic facts as ground truth. Do not change exact counts, dates, percentages, or row matching.
Your job is to interpret the facts, identify all risks, infer the critical path, and recommend the most urgent management actions.

ENRICHMENT:
- Fill missing `area`, `floor`, `phase`, and `trade_code` whenever the evidence is visible in the normalized rows, location_path, discipline, WBS, or activity names.
- Prefer deterministic NUSF fields over inference. Only infer when the normalized fields are blank.
- Preserve any existing location values; only add missing details.

CRITICAL PATH:
- If critical_flag or total_float data appears in all_activities, use it directly.
- If no float or critical flag data is present, infer the critical path from all_activities by identifying the longest dependency chain: activities with the latest finish dates per trade or area, behind-schedule activities whose delay would cascade to project completion, and activities that appear to be sequential prerequisites based on their names and trade sequence.
- Always populate critical_path_activities when all_activities is provided. Do not leave it empty. Identify at minimum the 5–15 activities that form the backbone of the schedule.

PROJECT HEALTH OVERRIDE:
- The deterministic health score is conservative and may understate risk.
- Set project_health_override to "Red" if multiple areas are significantly behind, stage mismatches are widespread, or behind activities cover key structural or MEP trades.
- Set project_health_override to "Yellow" if there are notable delays not yet captured as Red PONR.
- Only override when the evidence clearly warrants it. Omit the field if the deterministic score is accurate.

Return ONLY valid JSON with any of these fields:
{
  "executive_summary": {"recommended_action": "one specific action sentence"},
  "project_health_override": "Red|Yellow|Green",
  "health_override_reason": "one sentence explaining the override",
  "delay_drivers": [{"driver": "", "description": "", "affected_count": 0}],
  "action_recommendations": [{"activity": "", "issue": "", "actions": []}],
  "critical_path_activities": [{"activity": "", "start_date": "", "finish_date": "", "actual_pct": 0, "float_days": 0, "location": {"area": "", "floor": "", "phase": ""}}],
  "activity_enrichment": [{"activity": "", "trade_code": "EL|VVS|VENT|ARK|BYGH", "location": {"area": "", "floor": "", "phase": ""}}]
}

Only use activity_enrichment when trade/area/floor/phase is visibly supported by the activity name, discipline, location path, or supplied facts."""
        user_prompt = "DETERMINISTIC_FACTS:\n" + json.dumps(packet, ensure_ascii=False)
        response = self.client.chat.completions.create(
            model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            top_p=0.1,
            seed=42,
            max_tokens=4096,
        )
        text = response.choices[0].message.content or "{}"
        return _clean_json_response(text)


compare_v5_graph_agent = CompareV5GraphAgent()
