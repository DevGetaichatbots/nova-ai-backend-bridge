import logging
import json
from ..vector_store import vector_store_manager
from src.config import settings
from openai import AzureOpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scope filter → activity prefix/keyword mapping
# Maps generic English filter terms to Danish activity code prefixes and
# keywords that appear in the Katrinetorvet CSV schedules.
# ---------------------------------------------------------------------------
SCOPE_FILTER_MAP = {
    # Electrical / BMS
    "electrical": ["EL -", "EL-", "TEK -", "TEK-", "SOLCELLER", "LODRET FØRING", "FØRINGSVEJE", "LAVSPÆNDING", "BELYSNING", "SVAGSTRØM"],
    "electric":   ["EL -", "EL-", "TEK -", "TEK-"],
    "el":         ["EL -", "EL-"],
    "bms":        ["TEK -", "TEK-", "BMS"],
    "automation": ["TEK -", "TEK-", "BMS"],
    # Plumbing / VVS
    "plumbing":   ["VVS -", "VVS-", "GULVVARME", "FALDSTAMME", "AFLØB", "SKAKTE", "RØR", "VARME", "VAND"],
    "vvs":        ["VVS -", "VVS-"],
    "sanitary":   ["VVS -", "VVS-"],
    "water":      ["VVS -", "VVS-"],
    "heating":    ["VVS -", "VVS-", "GULVVARME", "VARME"],
    # Concrete / Structural
    "concrete":   ["BE -", "BE-", "BET -", "BETON"],
    "structural": ["KL -", "KL-", "STÅL", "ELEMENT", "ELEM -", "ELEM-"],
    # Masonry
    "masonry":    ["MU -", "MU-", "MU2 -", "MURVÆRK"],
    "brickwork":  ["MU -", "MU-", "MU2 -"],
    # Carpentry / Windows / Doors
    "carpentry":  ["TØ -", "TØ-", "TRÆ", "VINDUE"],
    "windows":    ["TØ -", "TØ-", "VINDUE"],
    # Flooring
    "flooring":   ["GU -", "GU-", "GULV", "TERMOGULV", "TRÆGULV"],
    # Painting
    "painting":   ["MAL -", "MAL-"],
    # Facade / Cladding
    "facade":     ["FAC -", "FAC-", "SKALMURING"],
    # Roofing
    "roofing":    ["TAG -", "TAG-", "PAP"],
    # Inventory / Interior
    "interior":   ["INV -", "INV-", "INVENTAR", "MONTAGE"],
    # Elements / Prefab
    "elements":   ["ELEM -", "ELEM-", "ELEMENT"],
}

def _resolve_scope_prefixes(scope_filter: str) -> list[str]:
    """
    Given a free-text scope_filter (e.g. "Electrical, BMS and Plumbing"),
    return a list of activity name prefixes/keywords that should be included.
    Falls back to an empty list (= include everything) if nothing matches.
    """
    filter_lower = scope_filter.lower()
    prefixes = []
    for keyword, codes in SCOPE_FILTER_MAP.items():
        if keyword in filter_lower:
            prefixes.extend(codes)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for p in prefixes:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def _activity_in_scope(name: str, prefixes: list[str]) -> bool:
    """Return True if the activity name starts with (or contains) any scope prefix."""
    if not prefixes:
        return True  # no filter → include all
    name_upper = name.upper()
    for p in prefixes:
        if name_upper.startswith(p.upper()) or p.upper() in name_upper:
            return True
    return False


def _postprocess(data: dict, scope_prefixes: list[str]) -> dict:
    """
    Clean LLM output:
    1. Filter scope_activities to only those matching scope prefixes.
    2. Filter all change/status/variance entries to scope only.
    3. Remove start_changes / finish_changes where old == new (trivial non-change).
    4. Deduplicate all lists.
    """
    # --- scope_activities ---
    raw_scope = data.get("scope_activities", [])
    clean_scope = []
    seen_scope = set()
    for act in raw_scope:
        if act not in seen_scope and _activity_in_scope(act, scope_prefixes):
            seen_scope.add(act)
            clean_scope.append(act)

    # --- changed_activities ---
    changes = data.get("changed_activities", {})

    def _filter_list(lst):
        seen = set()
        out = []
        for item in lst:
            key = item if isinstance(item, str) else str(item)
            if key not in seen:
                name = item if isinstance(item, str) else item.get("activity", "")
                if _activity_in_scope(name, scope_prefixes):
                    seen.add(key)
                    out.append(item)
        return out

    def _filter_changes(lst):
        """Like _filter_list but also drops entries where old == new."""
        seen = set()
        out = []
        for item in lst:
            if not isinstance(item, dict):
                continue
            old_val = str(item.get("old", "")).strip()
            new_val = str(item.get("new", "")).strip()
            if old_val == new_val:
                continue  # trivial non-change
            name = item.get("activity", "")
            key = f"{name}|{old_val}|{new_val}"
            if key not in seen and _activity_in_scope(name, scope_prefixes):
                seen.add(key)
                out.append(item)
        return out

    clean_changes = {
        "added":            _filter_list(changes.get("added", [])),
        "removed":          _filter_list(changes.get("removed", [])),
        "start_changes":    _filter_changes(changes.get("start_changes", [])),
        "finish_changes":   _filter_changes(changes.get("finish_changes", [])),
        "duration_changes": _filter_changes(changes.get("duration_changes", [])),
    }

    # --- progress_status ---
    raw_status = data.get("progress_status", [])
    clean_status = []
    seen_status = set()
    for item in raw_status:
        name = item.get("activity", "")
        if name not in seen_status and _activity_in_scope(name, scope_prefixes):
            seen_status.add(name)
            clean_status.append(item)

    # --- variance_analysis ---
    raw_var = data.get("variance_analysis", [])
    clean_var = []
    seen_var = set()
    for item in raw_var:
        name = item.get("activity", "")
        if name not in seen_var and _activity_in_scope(name, scope_prefixes):
            seen_var.add(name)
            clean_var.append(item)

    return {
        "scope_activities": clean_scope,
        "changed_activities": clean_changes,
        "progress_status": clean_status,
        "variance_analysis": clean_var,
    }


class CompareV2Agent:
    def __init__(self):
        """
        Dashboard-oriented agent that provides factual output with no AI fluff.
        """
        self.client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )

    def _get_doc_label(self, table_name: str, old_filename: str, new_filename: str) -> str:
        if old_filename and ('old' in table_name.lower() or old_filename in table_name):
            return f"OLD Schedule ({old_filename})" if old_filename else "OLD Schedule"
        return f"NEW Schedule ({new_filename})" if new_filename else "NEW Schedule"

    def _retrieve_context(self, scope_filter: str, table_names: list[str], top_k: int, old_filename: str, new_filename: str):
        # We fetch all table chunks instead of relying on semantic search, because CSV and MPP 
        # uploads currently skip embedding generation (using [0.0]) and semantic search would fail.
        # The LLM will perform the actual scope filtering via the prompt.
        logger.info(f"  Fetching all table chunks from {len(table_names)} stores for Compare V2...")
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
            logger.warning(f"  Context truncated in V2: {total_chunks} chunks sent, {total_skipped} omitted")
        else:
            logger.info(f"  Chunks sent to LLM for V2: {total_chunks}")
                
        return "\n\n".join(context_parts)

    def analyze(self, scope_filter: str, reference_date: str, table_names: list[str], session_id: str, old_filename: str, new_filename: str, top_k: int = 50) -> dict:
        """
        Retrieves context mapping to `scope_filter`, compares the two schedules, and builds the factual dashboard data.
        """
        scope_prefixes = _resolve_scope_prefixes(scope_filter)
        logger.info(f"  Scope filter '{scope_filter}' resolved to prefixes: {scope_prefixes}")

        context = self._retrieve_context(scope_filter, table_names, top_k, old_filename, new_filename)
        
        # Build explicit prefix hint for the LLM so it knows exactly what to include
        prefix_hint = ""
        if scope_prefixes:
            prefix_hint = (
                f"\nACTIVITY PREFIX WHITELIST (STRICT): Only include activities whose names start with "
                f"one of these prefixes (case-insensitive): {', '.join(scope_prefixes)}\n"
                f"EXCLUDE any activity that does NOT start with one of these prefixes, "
                f"regardless of context or relevance.\n"
            )

        system_prompt = f"""You are a strict data-extraction parser. Your ONLY job is to read two construction schedules (OLD and NEW) and output a JSON comparison. You must follow every rule below without exception.

=== SCOPE RULES ===
{prefix_hint}
The scope filter is: "{scope_filter}"
- ONLY process activities whose names begin with the whitelisted prefixes above.
- Activities from other disciplines (e.g. MU, MAL, GU, INV, ELEM, TØ, FAC) are FORBIDDEN in ALL output fields unless they are explicitly in the whitelist.
- Do NOT include any activity you cannot directly find verbatim in the context data. Do NOT invent, extrapolate, or generate numbered variants (e.g. do not produce TEK - X-1, TEK - X-2 … unless ALL of those exact names appear verbatim in the raw data).

=== CHANGE DETECTION RULES ===
For `added`:   List ONLY activity names present in the NEW schedule but completely absent from the OLD schedule. If an activity exists in OLD under ANY name variant, it is NOT added.
For `removed`: List ONLY activity names present in the OLD schedule but completely absent from the NEW schedule.
For `start_changes`: List ONLY activities where the start datetime in NEW differs from the start datetime in OLD. If old value == new value, OMIT the entry entirely — do NOT include it.
For `finish_changes`: List ONLY activities where the finish datetime in NEW differs from the finish datetime in OLD. If old value == new value, OMIT the entry entirely — do NOT include it.
For `duration_changes`: List ONLY activities where the calculated duration in NEW differs from OLD. If old value == new value, OMIT the entry entirely — do NOT include it.

=== PROGRESS RULES ===
For `progress_status`: Compare actual % complete against expected progress based on reference_date, start, and finish. Status must be exactly one of: "ahead", "behind", "on schedule".
For `variance_analysis`: Calculate expected_pct from (reference_date - start) / (finish - start) * 100. Report actual_pct from the NEW schedule data. variance = actual - expected. Only include activities where |variance| >= 1%.

=== OUTPUT FORMAT ===
Output ONLY valid JSON with this exact structure. No markdown, no code fences, no explanation text:
{{
    "scope_activities": ["<exact activity name as it appears in the data>"],
    "changed_activities": {{
        "added":            ["<activity name>"],
        "removed":          ["<activity name>"],
        "start_changes":    [{{"activity": "<name>", "old": "<datetime>", "new": "<datetime>"}}],
        "finish_changes":   [{{"activity": "<name>", "old": "<datetime>", "new": "<datetime>"}}],
        "duration_changes": [{{"activity": "<name>", "old": "<value>", "new": "<value>"}}]
    }},
    "progress_status": [
        {{"activity": "<name>", "status": "behind"}}
    ],
    "variance_analysis": [
        {{"activity": "<name>", "expected_pct": "70%", "actual_pct": "35%", "variance": "-35%", "status": "Critical"}}
    ]
}}
"""
        
        user_prompt = f"""SCOPE FILTER: {scope_filter}
REFERENCE DATE FOR PROGRESS CALCULATION: {reference_date}

CONTEXT DATA:
{context}

Extract and compare ONLY the in-scope activities using the whitelist above. Output ONLY the JSON object.
"""

        logger.info(f"  Calling Azure OpenAI ({settings.AZURE_OPENAI_CHAT_DEPLOYMENT}) for Compare V2...")
        
        try:
            response = self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0,
                top_p=0.1,
                seed=42,
                max_tokens=16384
            )
            text = response.choices[0].message.content or ""
            text = text.strip()
            
            # Clean up potential markdown formatting around JSON
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
                
            data = json.loads(text.strip())

            # Python-side post-processing: enforce scope and strip trivial changes
            data = _postprocess(data, scope_prefixes)
            logger.info(
                f"  Post-processed: {len(data['scope_activities'])} scope acts, "
                f"added={len(data['changed_activities'].get('added',[]))}, "
                f"removed={len(data['changed_activities'].get('removed',[]))}, "
                f"start_changes={len(data['changed_activities'].get('start_changes',[]))}, "
                f"finish_changes={len(data['changed_activities'].get('finish_changes',[]))}, "
                f"duration_changes={len(data['changed_activities'].get('duration_changes',[]))}, "
                f"status_rows={len(data['progress_status'])}, "
                f"variance_rows={len(data['variance_analysis'])}"
            )
            
            return {
                "json": data,
                "context_chunks": top_k * len(table_names)
            }
        except Exception as e:
            logger.error(f"Error in CompareV2Agent: {e}")
            return {
                "json": {
                    "scope_activities": [],
                    "changed_activities": {
                        "added": [], "removed": [],
                        "start_changes": [], "finish_changes": [], "duration_changes": []
                    },
                    "progress_status": [],
                    "variance_analysis": [],
                    "error": str(e)
                },
                "context_chunks": 0
            }

compare_v2_agent = CompareV2Agent()
