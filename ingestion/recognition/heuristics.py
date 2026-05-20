"""
Heuristic Header Recognizer
============================
Maps raw column headers to NUSF semantic roles using a token dictionary
and Jaro-Winkler fuzzy matching (threshold 0.85).

Supported semantic roles:
  source_id, name, planned_start, planned_finish, duration,
  percent_complete, wbs_code, predecessors, successors, discipline,
  area, floor, remarks, actual_start, actual_finish, actual_progress

Also detects the stable matching key (format type) for the schedule:
  tbs | id | entydigt_id | name_location | row_index
"""
from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

JARO_WINKLER_THRESHOLD = 0.85
_P = 0.1


def _jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    len_s1, len_s2 = len(s1), len(s2)
    if len_s1 == 0 or len_s2 == 0:
        return 0.0
    match_dist = max(len_s1, len_s2) // 2 - 1
    match_dist = max(0, match_dist)

    s1_matches = [False] * len_s1
    s2_matches = [False] * len_s2
    matches = 0
    transpositions = 0

    for i in range(len_s1):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len_s2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len_s1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    return (matches / len_s1 + matches / len_s2 + (matches - transpositions / 2) / matches) / 3


def _jaro_winkler(s1: str, s2: str) -> float:
    j = _jaro(s1, s2)
    prefix = 0
    for i in range(min(4, min(len(s1), len(s2)))):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break
    return j + prefix * _P * (1 - j)


TOKEN_MAP: Dict[str, List[str]] = {
    "source_id": [
        "id", "nr", "nummer", "task id", "taskid", "task_id", "act id",
        "activity id", "uid", "unique id", "row id",
    ],
    "wbs_code": [
        "tbs", "wbs", "wbs code", "wbs_code", "wbs-code", "hierarchical code",
        "structure code", "aktivitetskode",
    ],
    "entydigt_id": [
        "entydigt id", "entydigt_id", "unique task id", "unique id",
    ],
    "name": [
        "opgavenavn", "aktivitet", "task name", "taskname", "aktivitetsnavn",
        "beskrivelse", "description", "name", "navn", "task description",
        "activity name", "activity description", "opg.navn", "opgavenavn/aktivitet",
    ],
    "planned_start": [
        "startdato", "start", "start date", "startdate", "planned start",
        "planned_start", "planned_start_date", "planlagt start",
        "baseline start", "early start",
        "dato fra", "fra dato", "start dato", "fra", "begyndelsesdato",
    ],
    "planned_finish": [
        "slutdato", "finish", "end date", "enddate", "planned finish",
        "planned_finish", "planned_end_date", "planned end", "planlagt slut",
        "baseline finish", "early finish", "slut", "færdigdato",
        "dato til", "til dato", "slut dato", "til", "afslutningsdato",
    ],
    "duration": [
        "varighed", "duration", "planned_shift_duration", "planned duration",
        "baseline duration", "original duration", "længde",
    ],
    "percent_complete": [
        "% arbejde færdigt", "% færdigt", "% complete", "percent complete",
        "fremdrift", "completion", "progress", "actual_completion_pct",
        "pct complete", "pct_complete", "completion %",
    ],
    "predecessors": [
        "foregående opgaver", "predecessors", "predecessor", "foregående",
        "dependencies", "depends on", "forudgående",
    ],
    "successors": [
        "efterfølgende opgaver", "successors", "successor", "efterfølgende",
    ],
    "discipline": [
        "ansvarlig", "responsible", "trade", "discipline", "resource",
        "task_group_name", "faggruppe", "fag", "actual_by",
    ],
    "area": [
        "omr.", "omr", "område", "area", "zone", "location", "location_path",
        "lokation", "sektor", "sector",
    ],
    "floor": [
        "etage", "floor", "niveau", "level", "sal",
    ],
    "remarks": [
        "bemærkn.", "bemærkn", "bemærkning", "bemærkninger", "notes",
        "remarks", "comments", "is_flagged", "flag",
    ],
    "actual_start": [
        "actual start", "actual_start", "actual_start_date", "faktisk start",
        "virkelig start",
    ],
    "actual_finish": [
        "actual finish", "actual_finish", "actual_end_date", "faktisk slut",
        "virkelig slut", "actual_completion_date",
    ],
    "actual_progress": [
        "actual_completion_pct", "actual progress", "faktisk fremdrift",
    ],
    "activity_type": [
        "aktivitetstype", "task type", "type", "activity type",
    ],
    "is_late": [
        "is_late", "late", "forsinket flag",
    ],
    "inspected_type": [
        "inspectedtype", "inspection status", "accepted",
    ],
}

CRITICAL_FIELDS = {"name", "planned_start", "planned_finish"}


class RecognitionResult:
    def __init__(
        self,
        column_map: Dict[str, str],
        match_key: str,
        format_label: str,
        ai_needed: bool,
        confidence: float,
    ):
        self.column_map = column_map
        self.match_key = match_key
        self.format_label = format_label
        self.ai_needed = ai_needed
        self.confidence = confidence

    def __repr__(self) -> str:
        return (
            f"RecognitionResult(match_key={self.match_key!r}, "
            f"format={self.format_label!r}, "
            f"ai_needed={self.ai_needed}, "
            f"confidence={self.confidence:.2f}, "
            f"columns={list(self.column_map.keys())})"
        )


def _normalize(s: str) -> str:
    return s.strip().lower()


def _best_match(raw: str, candidates: List[str]) -> Tuple[Optional[str], float]:
    norm_raw = _normalize(raw)
    best_score = 0.0
    best_cand = None
    for cand in candidates:
        if norm_raw == cand:
            return cand, 1.0
        score = _jaro_winkler(norm_raw, cand)
        if score > best_score:
            best_score = score
            best_cand = cand
    return (best_cand if best_score >= JARO_WINKLER_THRESHOLD else None), best_score


class HeuristicRecognizer:
    """
    Maps raw column headers to NUSF semantic roles.

    Usage:
        result = HeuristicRecognizer().recognize(headers)
        # result.column_map  {'planned_start': 'Startdato', 'name': 'Opgavenavn', ...}
        # result.match_key   'tbs' | 'id' | 'entydigt_id' | 'name_location' | 'row_index'
        # result.ai_needed   True if critical fields could not be resolved
    """

    def recognize(self, headers: List[str]) -> RecognitionResult:
        column_map: Dict[str, str] = {}
        score_map: Dict[str, float] = {}
        headers_lower = [_normalize(h) for h in headers]

        for semantic_role, token_list in TOKEN_MAP.items():
            best_header = None
            best_score = 0.0

            for raw_header, norm_header in zip(headers, headers_lower):
                matched, score = _best_match(norm_header, token_list)
                if matched and score > best_score:
                    best_score = score
                    best_header = raw_header

            if best_header and semantic_role not in column_map:
                column_map[semantic_role] = best_header
                score_map[semantic_role] = best_score

        match_key = self._detect_match_key(headers_lower, column_map)
        format_label = self._format_label(match_key, headers_lower)
        ai_needed = not all(f in column_map for f in CRITICAL_FIELDS)

        mapped_critical = sum(1 for f in CRITICAL_FIELDS if f in column_map)
        confidence = mapped_critical / len(CRITICAL_FIELDS)

        logger.info(
            f"HeuristicRecognizer: {len(column_map)} roles mapped, "
            f"match_key={match_key}, ai_needed={ai_needed}, "
            f"confidence={confidence:.2f}"
        )

        return RecognitionResult(
            column_map=column_map,
            match_key=match_key,
            format_label=format_label,
            ai_needed=ai_needed,
            confidence=confidence,
        )

    def _detect_match_key(self, headers_lower: List[str], column_map: Dict[str, str]) -> str:
        if "wbs_code" in column_map and any("tbs" in h for h in headers_lower):
            return "tbs"

        if "entydigt_id" in column_map:
            return "entydigt_id"

        plandisc_cols = {"name", "planned_start_date", "location_path", "actual_completion_pct"}
        if len(plandisc_cols & set(headers_lower)) >= 3:
            return "name_location"

        if "source_id" in column_map:
            return "id"

        return "row_index"

    def _format_label(self, match_key: str, headers_lower: List[str]) -> str:
        labels = {
            "tbs": "Tactplan Export",
            "id": "MS Project Export",
            "entydigt_id": "Detailtidsplan",
            "name_location": "Plandisc Export",
            "row_index": "Structured Table",
        }
        return labels.get(match_key, "Unknown")
