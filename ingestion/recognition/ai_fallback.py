"""
AI Fallback Recognizer
======================
Fires only when heuristics cannot resolve critical fields (name, planned_start, planned_finish).
Calls Azure OpenAI to map raw headers to NUSF semantic roles.
Results are cached in-memory by sorted-header hash to avoid redundant API calls.
"""
from __future__ import annotations
import hashlib
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_SESSION_CACHE: Dict[str, Dict[str, str]] = {}

_SYSTEM_PROMPT = (
    "You are a construction schedule column header mapper. "
    "Given a list of raw column headers from a project schedule, "
    "map each of these target fields to the most semantically matching raw header.\n\n"
    "Target fields to map:\n"
    "  source_id, name, planned_start, planned_finish, duration, percent_complete, "
    "predecessors, successors, discipline, area, wbs_code\n\n"
    "Rules:\n"
    "- Only map a target field if you are confident (>80%) in the match.\n"
    "- If no good match exists for a field, omit it from the response.\n"
    "- Respond with a strict JSON object only — no markdown, no explanation.\n"
    "- Keys are target field names, values are the exact raw header string.\n\n"
    "Example: {\"name\": \"Opgavenavn\", \"planned_start\": \"Startdato\", \"planned_finish\": \"Slutdato\"}"
)


def _cache_key(headers: List[str]) -> str:
    normalized = sorted(h.strip().lower() for h in headers)
    return hashlib.md5("|".join(normalized).encode()).hexdigest()


class AIFallbackRecognizer:
    """
    Calls Azure OpenAI to map ambiguous column headers to NUSF semantic roles.
    Results are cached per session by header set hash.
    """

    def __init__(self):
        self._endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self._api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        self._deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1")
        self._api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")

    def recognize(self, headers: List[str]) -> Optional[Dict[str, str]]:
        """
        Returns a partial column_map from header names to semantic roles,
        or None if the API call fails.
        """
        key = _cache_key(headers)
        if key in _SESSION_CACHE:
            logger.info(f"AI fallback: cache hit for header set {key[:8]}")
            return _SESSION_CACHE[key]

        if not self._endpoint or not self._api_key:
            logger.warning("AI fallback: Azure OpenAI credentials not configured — skipping")
            return None

        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=self._api_key,
                api_version=self._api_version,
            )

            user_message = f"Raw column headers: {json.dumps(headers)}"

            response = client.chat.completions.create(
                model=self._deployment,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                max_tokens=512,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content or "{}"
            mapping = json.loads(raw)

            if not isinstance(mapping, dict):
                logger.warning("AI fallback: unexpected response format")
                return None

            _SESSION_CACHE[key] = mapping
            logger.info(
                f"AI fallback: resolved {len(mapping)} fields for header set {key[:8]}: "
                f"{list(mapping.keys())}"
            )
            return mapping

        except Exception as e:
            logger.error(f"AI fallback recognition failed: {e}")
            return None
