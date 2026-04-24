"""
Premium Structured HTML Converter — SaaS Section-Grouped Layout
Each task category gets its own card with header + table.
Parses 10 sections: DATA_TRUST → EXECUTIVE_TOP → BIGGEST_RISK → ESTIMATED_IMPACT →
CONFIDENCE_LEVEL → ROOT_CAUSE_ANALYSIS → RECOMMENDED_ACTIONS →
COMPARISON TABLES → SUMMARY_OF_CHANGES → PROJECT_HEALTH
"""

import re
import json
import html
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import base64


SVG_ICONS = {
    "table": '<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2"/><path d="M3 9h18M3 15h18M9 3v18" stroke="currentColor" stroke-width="2"/></svg>',
    "summary": '<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="2" fill="currentColor" opacity="0.15"/><path d="M7 8h10M7 12h10M7 16h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    "pulse": '<svg width="28" height="28" viewBox="0 0 24 24" fill="none"><path d="M22 12h-4l-3 9L9 3l-3 9H2" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "download": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    "executive": '<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "rootcause": '<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="2"/><path d="M21 21l-4.35-4.35" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    "impact": '<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" stroke-width="2"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2"/></svg>',
    "added": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#10b981" opacity="0.15"/><path d="M12 8v8M8 12h8" stroke="#10b981" stroke-width="2.5" stroke-linecap="round"/></svg>',
    "removed": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#ef4444" opacity="0.15"/><path d="M8 12h8" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round"/></svg>',
    "moved": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#f59e0b" opacity="0.15"/><path d="M8 12h8M12 8l4 4-4 4" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "delayed": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#ef4444" opacity="0.15"/><path d="M12 6v6l3 3" stroke="#ef4444" stroke-width="2" stroke-linecap="round"/></svg>',
    "accelerated": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#10b981" opacity="0.15"/><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" transform="scale(0.6) translate(8,8)"/></svg>',
    "critical": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 22h20L12 2z" fill="#f59e0b" opacity="0.15"/><path d="M12 9v4M12 17h.01" stroke="#f59e0b" stroke-width="2.5" stroke-linecap="round"/></svg>',
    "risks": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" fill="#ef4444" opacity="0.15"/><path d="M12 8v4M12 16h.01" stroke="#ef4444" stroke-width="2.5" stroke-linecap="round"/></svg>',
    "default": '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="2" fill="#06b6d4" opacity="0.15"/><path d="M9 9h6M9 12h6M9 15h4" stroke="#06b6d4" stroke-width="2" stroke-linecap="round"/></svg>',
}


def _mini_svg(name: str, size: int = 14, color: str = "currentColor") -> str:
    sw = "2"
    b = f'width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"'
    icons = {
        "dot": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="{color}" stroke="none"><circle cx="12" cy="12" r="5"/></svg>',
        "chevron-right": f'<svg {b}><path d="m9 18 6-6-6-6"/></svg>',
        "arrow-right": f'<svg {b}><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>',
        "check": f'<svg {b}><path d="M20 6 9 17l-5-5"/></svg>',
        "x": f'<svg {b}><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
        "circle-check": f'<svg {b}><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>',
        "circle-x": f'<svg {b}><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>',
        "info": f'<svg {b}><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
        "alert-circle": f'<svg {b}><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>',
        "alert-triangle": f'<svg {b}><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
        "shield-check": f'<svg {b}><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>',
        "shield-alert": f'<svg {b}><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>',
        "octagon-alert": f'<svg {b}><path d="M12 16h.01"/><path d="M12 8v4"/><path d="M15.312 2H8.688a2 2 0 0 0-1.414.586l-4.688 4.688A2 2 0 0 0 2 8.688v6.624a2 2 0 0 0 .586 1.414l4.688 4.688A2 2 0 0 0 8.688 22h6.624a2 2 0 0 0 1.414-.586l4.688-4.688A2 2 0 0 0 22 15.312V8.688a2 2 0 0 0-.586-1.414l-4.688-4.688A2 2 0 0 0 15.312 2z"/></svg>',
        "clock": f'<svg {b}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        "zap": f'<svg {b}><path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/></svg>',
        "plus": f'<svg {b}><path d="M5 12h14"/><path d="M12 5v14"/></svg>',
        "minus": f'<svg {b}><path d="M5 12h14"/></svg>',
        "edit": f'<svg {b}><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>',
    }
    return icons.get(name, icons["dot"])


CATEGORY_CONFIG = {
    "removed": {
        "label": "Removed Tasks",
        "label_da": "Fjernede Opgaver",
        "color": "#ef4444",
        "bg": "rgba(239, 68, 68, 0.04)",
        "border": "rgba(239, 68, 68, 0.12)",
    },
    "added": {
        "label": "Added Tasks",
        "label_da": "Tilføjede Opgaver",
        "color": "#10b981",
        "bg": "rgba(16, 185, 129, 0.04)",
        "border": "rgba(16, 185, 129, 0.12)",
    },
    "moved": {
        "label": "Modified / Moved Tasks",
        "label_da": "Ændrede / Flyttede Opgaver",
        "color": "#f59e0b",
        "bg": "rgba(245, 158, 11, 0.04)",
        "border": "rgba(245, 158, 11, 0.12)",
    },
    "delayed": {
        "label": "Delayed Tasks",
        "label_da": "Forsinkede Opgaver",
        "color": "#ef4444",
        "bg": "rgba(239, 68, 68, 0.04)",
        "border": "rgba(239, 68, 68, 0.12)",
    },
    "accelerated": {
        "label": "Accelerated Tasks",
        "label_da": "Fremskyndede Opgaver",
        "color": "#10b981",
        "bg": "rgba(16, 185, 129, 0.04)",
        "border": "rgba(16, 185, 129, 0.12)",
    },
    "rescheduled": {
        "label": "Rescheduled Tasks",
        "label_da": "Omplanlagte Opgaver",
        "color": "#0ea5e9",
        "bg": "rgba(14, 165, 233, 0.04)",
        "border": "rgba(14, 165, 233, 0.12)",
    },
    "critical": {
        "label": "Critical Path",
        "label_da": "Kritisk Vej",
        "color": "#f59e0b",
        "bg": "rgba(245, 158, 11, 0.04)",
        "border": "rgba(245, 158, 11, 0.12)",
    },
    "risks": {
        "label": "Risks",
        "label_da": "Risici",
        "color": "#ef4444",
        "bg": "rgba(239, 68, 68, 0.04)",
        "border": "rgba(239, 68, 68, 0.12)",
    },
    "default": {
        "label": "Other Tasks",
        "label_da": "Andre Opgaver",
        "color": "#06b6d4",
        "bg": "rgba(6, 182, 212, 0.04)",
        "border": "rgba(6, 182, 212, 0.12)",
    },
}

CATEGORY_ORDER = [
    "removed",
    "added",
    "delayed",
    "accelerated",
    "rescheduled",
    "moved",
    "critical",
    "risks",
    "default",
]


SECTION_PATTERNS = {
    "data_trust": [r"^##\s*DATA_TRUST", r"^##\s*DATAGRUNDLAG"],
    "executive_top": [r"^##\s*EXECUTIVE_TOP", r"^##\s*LEDELSESOVERBLIK"],
    "biggest_risk": [r"^##\s*BIGGEST_RISK", r"^##\s*STØRSTE_RISIKO"],
    "estimated_impact": [r"^##\s*ESTIMATED_IMPACT", r"^##\s*ESTIMERET_KONSEKVENS"],
    "confidence": [r"^##\s*CONFIDENCE_LEVEL", r"^##\s*TILLIDSNIVEAU"],
    "root_cause": [
        r"^##\s*ROOT_CAUSE_ANALYSIS",
        r"^##\s*Root\s+Cause\s+Analysis",
        r"^##\s*ÅRSAGSANALYSE",
        r"^##\s*Årsagsanalyse",
    ],
    "executive": [
        r"^##\s*RECOMMENDED_ACTIONS",
        r"^##\s*ANBEFALEDE_HANDLINGER",
        r"^##\s*EXECUTIVE_ACTIONS",
        r"^##\s*Executive\s+Actions",
        r"^##\s*HANDLINGSPLAN",
        r"^##\s*Handlingsplan",
        r"^##\s*LEDELSESHANDLINGER",
        r"^##\s*Ledelseshandlinger",
    ],
    "impact": [
        r"^##\s*IMPACT_ASSESSMENT",
        r"^##\s*Impact\s+Assessment",
        r"^##\s*KONSEKVENSVURDERING",
        r"^##\s*Konsekvensvurdering",
    ],
    "summary": [
        r"^##\s*SUMMARY_OF_CHANGES",
        r"^##\s*Summary\s+of\s+Changes",
        r"^##\s*OPSUMMERING_AF_ÆNDRINGER",
        r"^##\s*Opsummering\s+af\s+Ændringer",
    ],
    "health": [
        r"^##\s*PROJECT_HEALTH",
        r"^##\s*Project\s+Health",
        r"^##\s*PROJEKTSUNDHED",
        r"^##\s*Projektsundhed",
    ],
}

SECTION_ORDER = [
    "data_trust",
    "executive_top",
    "biggest_risk",
    "estimated_impact",
    "confidence",
    "root_cause",
    "executive",
    "impact",
    "summary",
    "health",
]


def _safe_eval_arithmetic(expr: str) -> int:
    expr = expr.strip()
    if not re.match(r"^[\d\s\(\)\+\-\*\/\.]+$", expr):
        return 0
    tokens = re.findall(r"[\d\.]+|[\+\-\*\/\(\)]", expr)
    if not tokens:
        return 0
    result = 0.0
    current = 0.0
    op = "+"
    i = 0
    depth = 0
    for t in tokens:
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
        elif t in ("+", "-", "*", "/"):
            op = t
        else:
            try:
                val = float(t)
            except ValueError:
                return 0
            if op == "+":
                result += current
                current = val
            elif op == "-":
                result += current
                current = -val
            elif op == "*":
                current *= val
            elif op == "/":
                current = current / val if val != 0 else 0
            op = "+"
    result += current
    return int(result) if result == int(result) else 0


def _sanitize_health_data_json(raw_json: str) -> str:
    def _replace_math(m):
        val = _safe_eval_arithmetic(m.group(1))
        return f": {val}"

    raw_json = re.sub(
        r":\s*([\d\s\(\)\+\-\*\/\.]+(?:[\+\-\*\/][\d\s\(\)\.]+)+)",
        _replace_math,
        raw_json,
    )
    raw_json = re.sub(r':\s*">[^"]*"', ": 0", raw_json)
    raw_json = re.sub(r":\s*>(\d+)", r": \1", raw_json)
    raw_json = re.sub(r":\s*null\b", ": 0", raw_json)
    raw_json = re.sub(r':\s*"-"', ': "0"', raw_json)
    return raw_json


def parse_structured_response(markdown: str) -> Dict:
    empty = {
        "data_trust_section": "",
        "executive_top_section": "",
        "decision_engine_data": None,
        "executive_section": "",
        "tables_section": "",
        "root_cause_section": "",
        "impact_section": "",
        "summary_section": "",
        "health_section": "",
        "health_data": None,
    }
    if not markdown:
        return empty

    found = {}
    for key, patterns in SECTION_PATTERNS.items():
        for p in patterns:
            m = re.search(p, markdown, re.MULTILINE | re.IGNORECASE)
            if m:
                found[key] = m.start()
                break

    boundaries = sorted(found.items(), key=lambda x: x[1])

    sections = {}
    for i, (key, start) in enumerate(boundaries):
        end = boundaries[i + 1][1] if i + 1 < len(boundaries) else len(markdown)
        sections[key] = markdown[start:end].strip()

    first_section_start = boundaries[0][1] if boundaries else len(markdown)
    pre_content = markdown[:first_section_start].strip()

    decision_engine_data = None
    for section_key in [
        "executive_top",
        "biggest_risk",
        "estimated_impact",
        "confidence",
    ]:
        section_text = sections.get(section_key, "")
        de_match = re.search(r"<!--DECISION_ENGINE:(.*?)-->", section_text, re.DOTALL)
        if de_match:
            try:
                decision_engine_data = json.loads(de_match.group(1))
            except:
                pass
            break
    if not decision_engine_data:
        de_match = re.search(r"<!--DECISION_ENGINE:(.*?)-->", markdown, re.DOTALL)
        if de_match:
            try:
                decision_engine_data = json.loads(de_match.group(1))
            except:
                pass

    if not decision_engine_data:
        for search_text in [
            sections.get("executive_top", ""),
            sections.get("executive", ""),
            markdown,
        ]:
            if not search_text:
                continue
            es_match = re.search(r"<!--EXEC_SUMMARY:(.*?)-->", search_text, re.DOTALL)
            if es_match:
                try:
                    exec_summary_data = json.loads(es_match.group(1))
                    decision_engine_data = {
                        "project_status": exec_summary_data.get(
                            "project_status", "AT_RISK"
                        ),
                        "biggest_issue": (
                            exec_summary_data.get("critical_findings", [""])[0]
                            if exec_summary_data.get("critical_findings")
                            else ""
                        ),
                        "impact_time": "See analysis below",
                        "impact_cost": exec_summary_data.get("risk_level", "MEDIUM"),
                        "impact_phases": "See analysis below",
                        "why": "See root cause analysis",
                        "focus": "See recommended actions",
                        "biggest_risk": (
                            exec_summary_data.get("critical_findings", [""])[0]
                            if exec_summary_data.get("critical_findings")
                            else ""
                        ),
                        "risk_blocking": "See impact assessment",
                        "risk_delay": "See analysis below",
                        "confidence": "MEDIUM",
                        "confidence_basis": "Based on available schedule data analysis",
                    }
                    break
                except:
                    pass

    # Inject risk_action into decision_engine_data from ➡️ marker in biggest_risk section
    _br_section_text = sections.get("biggest_risk", "")
    if _br_section_text and decision_engine_data and not decision_engine_data.get("risk_action"):
        for _line in _br_section_text.split("\n"):
            _s = _line.strip()
            if "\u27a1" in _s or "➡" in _s:
                import re as _re
                _action = _re.sub(
                    r"[\u27a1\ufe0f\s]*(?:YOUR\s+NEXT\s+ACTION|DIN\s+N[Ææ]STE\s+HANDLING)?[\:\-]?\s*",
                    "", _s, flags=_re.IGNORECASE
                ).strip()
                if _action:
                    decision_engine_data["risk_action"] = _action
                    break

    tables_part = ""
    if "executive" in sections:
        exec_section = sections["executive"]
        table_start_in_exec = -1
        for table_pattern in [
            r"^###\s+(?:Delayed|Accelerated|Added|Removed|Modified|Critical|Risks|Forsink|Fremskynd|Tilføj|Fjern|Ændr|Kritisk|Risici)",
            r"^\|.*\|.*\|",
        ]:
            tm = re.search(table_pattern, exec_section, re.MULTILINE | re.IGNORECASE)
            if tm:
                if table_start_in_exec == -1 or tm.start() < table_start_in_exec:
                    table_start_in_exec = tm.start()

        if table_start_in_exec > 0:
            sections["executive"] = exec_section[:table_start_in_exec].strip()
            tables_part = exec_section[table_start_in_exec:].strip()

    if not tables_part:
        collected_tables = []
        for section_key in list(sections.keys()):
            if section_key in ["health", "summary"]:
                continue
            section_text = sections.get(section_key, "")
            table_start = -1
            for tp in [
                r"^###\s+(?:Delayed|Accelerated|Added|Removed|Modified|Critical|Risks|Forsink|Fremskynd|Tilføj|Fjern|Ændr|Kritisk|Risici)",
                r"^\|.*\|.*\|",
            ]:
                tm = re.search(tp, section_text, re.MULTILINE | re.IGNORECASE)
                if tm:
                    if table_start == -1 or tm.start() < table_start:
                        table_start = tm.start()
            if table_start > 0:
                collected_tables.append(section_text[table_start:].strip())
                sections[section_key] = section_text[:table_start].strip()
        if collected_tables:
            tables_part = "\n\n".join(collected_tables)

    if not tables_part:
        tables_part = pre_content

    exec_section_clean = sections.get("executive", "")
    exec_section_clean = re.sub(
        r"<!--EXEC_SUMMARY:.*?-->", "", exec_section_clean, flags=re.DOTALL
    ).strip()
    exec_section_clean = re.sub(
        r"<!--DECISION_ENGINE:.*?-->", "", exec_section_clean, flags=re.DOTALL
    ).strip()

    extra_decision_content = []
    for dk in ["executive_top", "estimated_impact", "confidence"]:
        raw = sections.get(dk, "")
        cleaned = re.sub(r"<!--DECISION_ENGINE:.*?-->", "", raw, flags=re.DOTALL)
        cleaned = re.sub(r"<!--EXEC_SUMMARY:.*?-->", "", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"^##\s+\S+.*$", "", cleaned, flags=re.MULTILINE).strip()
        if cleaned:
            extra_decision_content.append(cleaned)
    extra_decision_text = "\n\n".join(extra_decision_content).strip()

    if not tables_part and pre_content:
        has_table = bool(re.search(r"^\|.*\|.*\|", pre_content, re.MULTILINE))
        has_heading = bool(
            re.search(
                r"^###\s+(?:Delayed|Accelerated|Added|Removed|Modified)",
                pre_content,
                re.MULTILINE | re.IGNORECASE,
            )
        )
        if has_table or has_heading:
            tables_part = pre_content
            pre_content = ""

    orphan_content = ""
    if pre_content and not tables_part:
        orphan_content = pre_content

    result = {
        "data_trust_section": sections.get("data_trust", ""),
        "executive_top_section": sections.get("executive_top", ""),
        "biggest_risk_section": sections.get("biggest_risk", ""),
        "decision_engine_data": decision_engine_data,
        "extra_decision_content": extra_decision_text,
        "executive_section": exec_section_clean,
        "tables_section": tables_part,
        "root_cause_section": sections.get("root_cause", ""),
        "impact_section": sections.get("impact", ""),
        "summary_section": sections.get("summary", ""),
        "health_section": sections.get("health", ""),
        "health_data": None,
        "orphan_content": orphan_content,
    }

    health_match = re.search(
        r"<!--HEALTH_DATA:(.*?)-->", result["health_section"], re.DOTALL
    )
    if health_match:
        try:
            sanitized = _sanitize_health_data_json(health_match.group(1))
            result["health_data"] = json.loads(sanitized)
        except:
            pass
        result["health_section"] = re.sub(
            r"<!--HEALTH_DATA:.*?-->", "", result["health_section"], flags=re.DOTALL
        ).strip()

    return result


def detect_category(text: str) -> str:
    lower = text.lower()
    if any(
        k in lower
        for k in ["removed", "fjern", "not present in new", "dropped", "slettet"]
    ):
        return "removed"
    if any(k in lower for k in ["added", "tilføj", "not present in old", "ny "]):
        return "added"
    if any(k in lower for k in ["delayed", "later", "forsink", "senere"]):
        return "delayed"
    if any(k in lower for k in ["earlier", "accelerat", "tidligere", "fremskynd"]):
        return "accelerated"
    if any(k in lower for k in ["moved", "modified", "ændr", "flytt", "changed"]):
        return "moved"
    if any(k in lower for k in ["critical", "kritisk"]):
        return "critical"
    if any(k in lower for k in ["risk", "risiko"]):
        return "risks"
    return "default"


def _detect_section_category(heading: str) -> str:
    lower = heading.lower()
    if any(k in lower for k in ["removed", "fjern", "slettet", "dropped"]):
        return "removed"
    if any(k in lower for k in ["added", "tilføj", "nye ", "ny ", "new task"]):
        return "added"
    if any(k in lower for k in ["delayed", "forsink", "senere", "later"]):
        return "delayed"
    if any(k in lower for k in ["accelerat", "fremskynd", "earlier", "tidligere"]):
        return "accelerated"
    if any(k in lower for k in ["moved", "modified", "ændr", "flytt", "changed"]):
        return "moved"
    if any(k in lower for k in ["critical", "kritisk"]):
        return "critical"
    if any(k in lower for k in ["risk", "risiko"]):
        return "risks"
    return "default"


def parse_tables_by_section(markdown: str) -> Dict[str, Dict]:
    if not markdown or "|" not in markdown:
        return {}

    sections: Dict[str, Dict] = {}
    lines = markdown.split("\n")
    current_category = None
    current_headers = []

    for line in lines:
        stripped = line.strip()

        heading_match = re.match(r"^#{1,4}\s+(.+)$", stripped)
        if heading_match:
            heading_text = heading_match.group(1).strip()
            cat = _detect_section_category(heading_text)
            if cat not in sections:
                sections[cat] = {"headers": [], "rows": [], "heading": heading_text}
            current_category = cat
            current_headers = []
            continue

        showing_match = re.match(
            r"^[\*]*Showing\s+\d+\s+of\s+(\d+)", stripped, re.IGNORECASE
        )
        if showing_match and current_category and current_category in sections:
            sections[current_category]["overflow_note"] = stripped.strip("*").strip()
            continue

        remaining_match = re.match(
            r"^[\*]*Remaining\s+task\s+IDs?:", stripped, re.IGNORECASE
        )
        if remaining_match and current_category and current_category in sections:
            existing = sections[current_category].get("overflow_note", "")
            sections[current_category]["overflow_note"] = (
                existing + " " + stripped.strip("*").strip()
            ).strip()
            continue

        bold_heading = re.match(r"^\*\*([^*]+)\*\*\s*$", stripped)
        if bold_heading and "|" not in stripped:
            heading_text = bold_heading.group(1).strip().rstrip(":")
            cat = _detect_section_category(heading_text)
            if cat not in sections:
                sections[cat] = {"headers": [], "rows": [], "heading": heading_text}
            current_category = cat
            current_headers = []
            continue

        if not stripped.startswith("|") or not stripped.endswith("|"):
            if (
                re.match(r"^\*?Note:", stripped, re.IGNORECASE)
                or "truncated" in stripped.lower()
            ):
                continue
            continue

        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]

        if all(c in ("...", "…", "") for c in cells):
            continue

        if current_category is None:
            cat = detect_category(" ".join(cells))
            if cat not in sections:
                sections[cat] = {"headers": [], "rows": [], "heading": ""}
            current_category = cat

        if not current_headers:
            current_headers = cells
            if (
                current_category in sections
                and not sections[current_category]["headers"]
            ):
                sections[current_category]["headers"] = cells
            continue

        if current_category in sections:
            sections[current_category]["rows"].append(cells)
        else:
            cat = detect_category(" ".join(cells))
            if cat not in sections:
                sections[cat] = {"headers": current_headers, "rows": [], "heading": ""}
            sections[cat]["rows"].append(cells)

    return sections


def escape_html(text: str) -> str:
    if not text:
        return ""
    return html.escape(str(text))


def get_status_badge(value: str) -> str:
    if not value or value in ["—", "-", "n/a", ""]:
        return '<span style="color:#94a3b8;">—</span>'

    lower = value.lower().strip()
    if any(x in lower for x in ["added", "new", "earlier", "tidligere", "tilføjet"]):
        return f'<span style="display:inline-flex;padding:5px 12px;border-radius:8px;font-size:12px;font-weight:600;background:rgba(16,185,129,0.12);color:#059669;border:1px solid rgba(16,185,129,0.2);">{escape_html(value)}</span>'
    if any(
        x in lower
        for x in ["removed", "later", "senere", "delayed", "forsinket", "fjernet"]
    ):
        return f'<span style="display:inline-flex;padding:5px 12px;border-radius:8px;font-size:12px;font-weight:600;background:rgba(239,68,68,0.12);color:#dc2626;border:1px solid rgba(239,68,68,0.2);">{escape_html(value)}</span>'
    if any(x in lower for x in ["moved", "modified", "changed", "ændret", "flyttet"]):
        return f'<span style="display:inline-flex;padding:5px 12px;border-radius:8px;font-size:12px;font-weight:600;background:rgba(245,158,11,0.12);color:#d97706;border:1px solid rgba(245,158,11,0.2);">{escape_html(value)}</span>'
    return f'<span style="display:inline-flex;padding:5px 12px;border-radius:8px;font-size:12px;font-weight:600;background:rgba(100,116,139,0.1);color:#475569;border:1px solid rgba(100,116,139,0.15);">{escape_html(value)}</span>'


def _render_cell(cell: str, header_name: str, is_first: bool, accent_color: str) -> str:
    if is_first:
        return f'<span style="color:#1e293b;font-weight:600;">{escape_html(cell or "—")}</span>'

    h_lower = header_name.lower()

    if any(
        x in h_lower for x in ["status", "difference", "forskel", "change", "ændring"]
    ):
        return get_status_badge(cell)

    if any(x in h_lower for x in ["week", "uge", "id"]):
        if not cell or cell in ["—", "-"]:
            return '<span style="color:#94a3b8;">—</span>'
        return f'<span style="display:inline-block;padding:4px 10px;border-radius:6px;font-weight:600;background:linear-gradient(135deg,#e0f7f7,#d1fae5);color:#0e7490;font-size:13px;border:1px solid rgba(6,182,212,0.2);">{escape_html(cell)}</span>'

    if any(x in h_lower for x in ["slutdato", "startdato", "date", "dato"]):
        if not cell or cell in ["—", "-"]:
            return '<span style="color:#94a3b8;">—</span>'
        return f'<span style="color:#334155;font-weight:500;font-size:13px;">{escape_html(cell)}</span>'

    if any(x in h_lower for x in ["varighed", "duration"]):
        if not cell or cell in ["—", "-"]:
            return '<span style="color:#94a3b8;">—</span>'
        return f'<span style="display:inline-block;padding:3px 8px;border-radius:6px;background:rgba(100,116,139,0.08);color:#475569;font-size:13px;font-weight:500;">{escape_html(cell)}</span>'

    return f'<span style="color:#475569;font-size:14px;line-height:1.5;">{escape_html(cell or "—")}</span>'


def _build_section_card(
    category: str,
    headers: List[str],
    rows: List[List[str]],
    language: str,
    table_id_suffix: str,
    overflow_note: str = None,
) -> str:
    if not rows:
        return ""

    config = CATEGORY_CONFIG.get(category, CATEGORY_CONFIG["default"])
    label = config["label_da"] if language == "da" else config["label"]
    color = config["color"]
    bg = config["bg"]
    border_color = config["border"]
    icon = SVG_ICONS.get(category, SVG_ICONS["default"])
    count = len(rows)

    parts = [
        f"""
<div class="category-section" style="margin:0 0 24px 0;border-radius:16px;overflow:hidden;border:1px solid {border_color};background:#ffffff;box-shadow:0 2px 12px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:10px;padding:16px 20px;background:{bg};border-bottom:2px solid {color}25;">
    <span style="color:{color};flex-shrink:0;">{icon}</span>
    <span style="font-size:15px;font-weight:700;color:{color};text-transform:uppercase;letter-spacing:0.8px;">{label}</span>
    <span style="padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;background:{color}18;color:{color};min-width:22px;text-align:center;">{count}</span>
  </div>
  <div style="overflow-x:auto;">
    <table style="width:100%;min-width:600px;border-collapse:separate;border-spacing:0;">
      <thead>
        <tr style="background:linear-gradient(135deg,#0f172a,#1e293b);">"""
    ]

    for idx, header in enumerate(headers):
        is_last = idx == len(headers) - 1
        br = "" if is_last else "border-right:1px solid rgba(255,255,255,0.08);"
        parts.append(f"""
          <th style="padding:14px 16px;text-align:left;font-size:11px;font-weight:700;color:rgba(255,255,255,0.9);text-transform:uppercase;letter-spacing:1px;{br}white-space:nowrap;">{escape_html(header)}</th>""")

    parts.append("""
        </tr>
      </thead>
      <tbody>""")

    for row_idx, row in enumerate(rows):
        row_bg = "#ffffff" if row_idx % 2 == 0 else "#f8fafc"
        parts.append(f"""
        <tr style="background:{row_bg};transition:background 0.15s ease;">""")

        for cell_idx, cell in enumerate(row):
            is_last = cell_idx == len(row) - 1
            br = "" if is_last else "border-right:1px solid #f1f5f9;"
            header_name = headers[cell_idx] if cell_idx < len(headers) else ""
            content = _render_cell(cell, header_name, cell_idx == 0, color)
            parts.append(f"""
          <td style="padding:14px 16px;font-size:14px;{br}border-bottom:1px solid #f1f5f9;vertical-align:middle;">{content}</td>""")

        parts.append("""
        </tr>""")

    parts.append("""
      </tbody>
    </table>
  </div>""")

    if overflow_note:
        parts.append(f"""
  <div style="padding:12px 20px;background:#f0fdfa;border-top:1px solid #ccfbf1;font-size:13px;color:#0d9488;font-weight:500;">
    {escape_html(overflow_note)}
  </div>""")

    parts.append("""
</div>""")

    return "".join(parts)


def _build_empty_category_note(category: str, language: str) -> str:
    config = CATEGORY_CONFIG.get(category, CATEGORY_CONFIG["default"])
    label = config["label_da"] if language == "da" else config["label"]
    color = config["color"]
    icon = SVG_ICONS.get(category, SVG_ICONS["default"])
    no_text = "Ingen" if language == "da" else "No"
    found_text = (
        "fundet i de hentede data"
        if language == "da"
        else "found in the retrieved data"
    )

    return f"""
<div style="display:flex;align-items:center;gap:10px;padding:14px 20px;margin:0 0 12px 0;border-radius:12px;background:rgba(248,250,252,0.8);border:1px solid #e2e8f0;">
  <span style="color:{color};opacity:0.5;">{icon}</span>
  <span style="font-size:14px;color:#94a3b8;font-weight:500;">{no_text} {label.lower()} {found_text}</span>
</div>"""


def generate_table_html(tables_section: str, language: str = "en") -> str:
    sections = parse_tables_by_section(tables_section)

    total_tasks = sum(len(s["rows"]) for s in sections.values())
    if total_tasks == 0:
        return ""

    date_str = datetime.now().strftime("%Y-%m-%d")
    table_id = f"tbl_{datetime.now().strftime('%H%M%S')}"

    all_rows_for_csv = []
    csv_headers = []
    for cat in CATEGORY_ORDER:
        if cat in sections and sections[cat]["rows"]:
            if not csv_headers and sections[cat]["headers"]:
                csv_headers = sections[cat]["headers"]
            all_rows_for_csv.extend(sections[cat]["rows"])
    csv_data = base64.b64encode(
        json.dumps([csv_headers] + all_rows_for_csv).encode()
    ).decode()

    download_js = f"(function(){{try{{var d=document.getElementById('csvData_{table_id}');var f=document.getElementById('csvFilename_{table_id}');if(!d||!f)return;var j=decodeURIComponent(escape(atob(d.textContent)));var dt=JSON.parse(j);var fn=f.textContent;var csv=dt.map(function(r){{return r.map(function(c){{var v=String(c||'');if(v.search(/[,\\\"\\\\n]/)!==-1)v='\"'+v.replace(/\"/g,'\"\"')+'\"';return v;}}).join(',')}}).join('\\n');var b=new Blob(['\\uFEFF'+csv],{{type:'text/csv;charset=utf-8;'}});var u=URL.createObjectURL(b);var l=document.createElement('a');l.href=u;l.download=fn;document.body.appendChild(l);l.click();document.body.removeChild(l);URL.revokeObjectURL(u);}}catch(e){{alert('CSV Error: '+e.message);}}}})()".replace(
        "'", "&#39;"
    )

    parts = [
        f'''
<div id="section-comparison" class="comparison-results" style="margin-bottom:32px;">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;flex-wrap:wrap;gap:16px;">
    <div style="display:flex;align-items:center;gap:14px;">
      <div style="width:48px;height:48px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#06b6d4,#0891b2);box-shadow:0 6px 20px rgba(6,182,212,0.25);">
        <span style="color:white;">{SVG_ICONS["table"]}</span>
      </div>
      <div>
        <h3 style="font-size:22px;font-weight:800;color:#0f172a;margin:0;">{"Sammenligningsresultater" if language == "da" else "Comparison Results"}</h3>
        <p style="font-size:13px;color:#64748b;margin:4px 0 0 0;">{total_tasks} {"opgaver analyseret" if language == "da" else "tasks analyzed"}</p>
      </div>
    </div>
    <button type="button" onclick="{download_js}"
            style="display:inline-flex;align-items:center;gap:8px;padding:12px 24px;border-radius:12px;font-weight:600;font-size:13px;color:white;background:linear-gradient(135deg,#00D6D6,#00B8B8);border:none;cursor:pointer;box-shadow:0 4px 16px rgba(0,214,214,0.3);transition:all 0.2s ease;">
      {SVG_ICONS["download"]}
      <span>{"Eksporter CSV" if language == "da" else "Export CSV"}</span>
    </button>
  </div>

  <div id="csvData_{table_id}" style="display:none;">{csv_data}</div>
  <div id="csvFilename_{table_id}" style="display:none;">comparison_results_{date_str}.csv</div>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:10px;margin-bottom:24px;">'''
    ]

    for cat in CATEGORY_ORDER:
        if cat not in sections or not sections[cat]["rows"]:
            continue
        config = CATEGORY_CONFIG[cat]
        color = config["color"]
        label_short = (
            (config["label_da"] if language == "da" else config["label"])
            .split("/")[0]
            .replace("Tasks", "")
            .replace("Opgaver", "")
            .strip()
        )
        count = len(sections[cat]["rows"])
        parts.append(f"""
    <div style="text-align:center;padding:14px 8px;background:linear-gradient(135deg,{color}0a,{color}04);border-radius:12px;border:1px solid {color}18;">
      <div style="font-size:24px;font-weight:800;color:{color};">{count}</div>
      <div style="font-size:10px;color:#64748b;text-transform:uppercase;margin-top:3px;font-weight:600;letter-spacing:0.5px;">{label_short}</div>
    </div>""")

    parts.append("""
  </div>""")

    for cat in CATEGORY_ORDER:
        if cat not in sections:
            continue
        sec = sections[cat]
        if sec["rows"]:
            parts.append(
                _build_section_card(
                    cat,
                    sec["headers"],
                    sec["rows"],
                    language,
                    table_id,
                    overflow_note=sec.get("overflow_note"),
                )
            )
        else:
            parts.append(_build_empty_category_note(cat, language))

    parts.append("""
</div>""")

    return "".join(parts)


def _inline_markdown(text: str) -> str:
    parts = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text)
    result = []
    for part in parts:
        bold = re.match(r"^\*\*([^*]+)\*\*$", part)
        italic = re.match(r"^\*([^*]+)\*$", part)
        if bold:
            result.append(
                f'<strong style="color:#1e293b;font-weight:700;">{escape_html(bold.group(1))}</strong>'
            )
        elif italic:
            result.append(f"<em>{escape_html(italic.group(1))}</em>")
        else:
            result.append(escape_html(part))
    text = "".join(result)
    text = text.replace(
        "🔴",
        f'<span style="display:inline-flex;vertical-align:middle;margin:0 1px;">{_mini_svg("dot", 10, "#ef4444")}</span>',
    )
    text = text.replace(
        "🟠",
        f'<span style="display:inline-flex;vertical-align:middle;margin:0 1px;">{_mini_svg("dot", 10, "#f59e0b")}</span>',
    )
    text = text.replace(
        "🟢",
        f'<span style="display:inline-flex;vertical-align:middle;margin:0 1px;">{_mini_svg("dot", 10, "#10b981")}</span>',
    )
    return text


def _render_section_header(title: str, icon: str, color: str) -> str:
    return f"""<div style="display:flex;align-items:center;gap:14px;margin-bottom:24px;padding-bottom:16px;border-bottom:2px solid {color}18;">
      <div style="width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,{color},{color}dd);box-shadow:0 4px 14px {color}30;">
        <span style="color:white;">{icon}</span>
      </div>
      <h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0;letter-spacing:-0.3px;">{title}</h2>
    </div>"""


def _parse_exec_summary(content: str) -> Optional[Dict]:
    m = re.search(r"<!--EXEC_SUMMARY:(.*?)-->", content, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except:
        return None


def _render_exec_summary_card(summary_data: Dict, language: str) -> str:
    status = summary_data.get("project_status", "AT_RISK")
    risk = summary_data.get("risk_level", "MEDIUM")
    findings = summary_data.get("critical_findings", [])
    consequences = summary_data.get("consequences_if_no_action", [])

    status_config = {
        "STABLE": {
            "color": "#10b981",
            "bg": "#ecfdf5",
            "border": "#a7f3d0",
            "svg": "shield-check",
            "label_en": "STABLE",
            "label_da": "STABIL",
        },
        "AT_RISK": {
            "color": "#d97706",
            "bg": "#fffbeb",
            "border": "#fde68a",
            "svg": "alert-triangle",
            "label_en": "AT RISK",
            "label_da": "I RISIKO",
        },
        "CRITICAL": {
            "color": "#dc2626",
            "bg": "#fef2f2",
            "border": "#fecaca",
            "svg": "octagon-alert",
            "label_en": "CRITICAL",
            "label_da": "KRITISK",
        },
    }
    risk_config = {
        "LOW": {
            "color": "#10b981",
            "svg": "shield-check",
            "label_en": "Low",
            "label_da": "Lav",
        },
        "MEDIUM": {
            "color": "#d97706",
            "svg": "alert-circle",
            "label_en": "Medium",
            "label_da": "Moderat",
        },
        "HIGH": {
            "color": "#dc2626",
            "svg": "alert-triangle",
            "label_en": "High",
            "label_da": "Høj",
        },
    }

    sc = status_config.get(status, status_config["AT_RISK"])
    rc = risk_config.get(risk, risk_config["MEDIUM"])

    status_label = sc["label_da"] if language == "da" else sc["label_en"]
    risk_label = rc["label_da"] if language == "da" else rc["label_en"]
    proj_status_title = "PROJEKTSTATUS" if language == "da" else "PROJECT STATUS"
    risk_title = "Risikoniveau" if language == "da" else "Risk Level"
    findings_title = "Kritiske Fund" if language == "da" else "Critical Findings"
    consequences_title = (
        "Hvis ingen handling tages" if language == "da" else "If No Action Is Taken"
    )

    findings_html = ""
    for f in findings[:3]:
        findings_html += f'<div style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;"><span style="display:inline-flex;margin-top:4px;flex-shrink:0;">{_mini_svg("chevron-right", 12, sc["color"])}</span><span style="font-size:13px;color:#334155;line-height:1.55;font-weight:500;">{escape_html(f)}</span></div>'

    consequences_html = ""
    if consequences:
        cons_items = ""
        for c in consequences[:3]:
            cons_items += f'<div style="display:flex;align-items:flex-start;gap:8px;padding:3px 0;"><span style="display:inline-flex;margin-top:2px;flex-shrink:0;">{_mini_svg("arrow-right", 13, "#dc2626")}</span><span style="font-size:12px;color:#991b1b;line-height:1.5;">{escape_html(c)}</span></div>'
        consequences_html = f"""
    <div style="margin-top:14px;padding:12px 16px;background:#fef2f2;border-radius:10px;border:1px solid #fecaca;">
      <div style="font-size:10px;font-weight:700;color:#991b1b;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px;">{consequences_title}</div>
      {cons_items}
    </div>"""

    return f"""
<div style="margin:0 0 18px 0;padding:22px 24px;background:linear-gradient(135deg,{sc["bg"]},#ffffff);border-radius:14px;border:1px solid {sc["border"]};border-left:5px solid {sc["color"]};box-shadow:0 2px 8px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:16px;">
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="display:inline-flex;">{_mini_svg(sc["svg"], 22, sc["color"])}</span>
      <span style="font-size:11px;font-weight:800;color:{sc["color"]};text-transform:uppercase;letter-spacing:1.2px;">{proj_status_title}</span>
      <span style="padding:4px 14px;border-radius:20px;font-size:13px;font-weight:800;color:{sc["color"]};background:white;border:2px solid {sc["color"]};">{status_label}</span>
    </div>
    <div style="display:flex;align-items:center;gap:6px;padding:4px 12px;border-radius:8px;background:white;border:1px solid {rc["color"]}30;">
      <span style="display:inline-flex;">{_mini_svg(rc["svg"], 14, rc["color"])}</span>
      <span style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;">{risk_title}:</span>
      <span style="font-size:12px;font-weight:800;color:{rc["color"]};">{risk_label}</span>
    </div>
  </div>
  <div style="margin-bottom:4px;">
    <div style="font-size:10px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px;">{findings_title}</div>
    {findings_html}
  </div>
  {consequences_html}
</div>"""


def _render_decision_engine_cards(de_data: Optional[Dict], language: str = "en") -> str:
    if not de_data:
        return ""

    status = de_data.get("project_status", "AT_RISK")
    status_config = {
        "STABLE": {
            "color": "#10b981",
            "bg": "#ecfdf5",
            "border": "#a7f3d0",
            "svg": "shield-check",
            "label_en": "STABLE",
            "label_da": "STABIL",
        },
        "AT_RISK": {
            "color": "#d97706",
            "bg": "#fffbeb",
            "border": "#fde68a",
            "svg": "alert-triangle",
            "label_en": "AT RISK",
            "label_da": "I RISIKO",
        },
        "CRITICAL": {
            "color": "#dc2626",
            "bg": "#fef2f2",
            "border": "#fecaca",
            "svg": "octagon-alert",
            "label_en": "CRITICAL",
            "label_da": "KRITISK",
        },
    }
    sc = status_config.get(status, status_config["AT_RISK"])
    status_label = sc["label_da"] if language == "da" else sc["label_en"]

    biggest_issue = escape_html(str(de_data.get("biggest_issue", "")))
    why = escape_html(str(de_data.get("why", "")))
    focus = escape_html(str(de_data.get("focus", "")))
    biggest_risk = escape_html(str(de_data.get("biggest_risk", "")))
    risk_blocking = escape_html(str(de_data.get("risk_blocking", "")))
    risk_delay = escape_html(str(de_data.get("risk_delay", "")))
    risk_next_action = escape_html(str(de_data.get("risk_next_action", "")))
    if_nothing_delay = escape_html(str(de_data.get("if_nothing_delay", "")))
    if_nothing_bottleneck = escape_html(str(de_data.get("if_nothing_bottleneck", "")))
    if_nothing_next_issue = escape_html(str(de_data.get("if_nothing_next_issue", "")))
    impact_time = escape_html(str(de_data.get("impact_time", "")))
    impact_cost = escape_html(str(de_data.get("impact_cost", "")))
    impact_phases = escape_html(str(de_data.get("impact_phases", "")))
    confidence = de_data.get("confidence", "MEDIUM")
    confidence_basis = escape_html(str(de_data.get("confidence_basis", "")))

    conf_config = {
        "HIGH": {"color": "#10b981", "label_en": "HIGH", "label_da": "HØJ"},
        "MEDIUM": {"color": "#d97706", "label_en": "MEDIUM", "label_da": "MODERAT"},
        "LOW": {"color": "#dc2626", "label_en": "LOW", "label_da": "LAV"},
    }
    cc = conf_config.get(confidence, conf_config["MEDIUM"])

    top_title = "Ledelsesoverblik" if language == "da" else "Executive Overview"
    top_subtitle = "5-sekunders overblik" if language == "da" else "5-second overview"
    issue_label = "Største problem" if language == "da" else "Biggest Issue"
    impact_label = "Konsekvens" if language == "da" else "Impact"
    why_label = "Hvorfor" if language == "da" else "Why"
    focus_label = "Fokus" if language == "da" else "Focus"
    risk_title = "Største Risiko" if language == "da" else "Biggest Risk"
    blocking_label = "Blokerer" if language == "da" else "What It Blocks"
    delay_label = "Potentiel forsinkelse" if language == "da" else "Potential Delay"
    action_label = "Næste handling" if language == "da" else "Next Action"
    if_nothing_title = "Hvis intet ændres" if language == "da" else "If Nothing Changes"
    if_nothing_delay_label = "Estimeret forsinkelse" if language == "da" else "Estimated Delay"
    if_nothing_bottleneck_label = "Næste flaskehals" if language == "da" else "Next Bottleneck"
    if_nothing_next_issue_label = "Næste kritiske problem" if language == "da" else "Next Critical Issue"
    impact_title = "Estimeret Konsekvens" if language == "da" else "Estimated Impact"
    time_label = "Tid" if language == "da" else "Time"
    cost_label = "Omkostning" if language == "da" else "Cost"
    phases_label = "Faser" if language == "da" else "Phases"
    conf_title = "Tillidsniveau" if language == "da" else "Confidence Level"
    basis_label = "Grundlag" if language == "da" else "Basis"

    executive_top_html = f"""
<div id="section-executive-overview" style="margin:0 0 16px 0;padding:24px;background:linear-gradient(135deg,{sc["bg"]},#ffffff);border-radius:16px;border:1px solid {sc["border"]};border-left:5px solid {sc["color"]};box-shadow:0 2px 10px rgba(0,0,0,0.05);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:18px;">
    <div style="width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,{sc["color"]},{sc["color"]}dd);box-shadow:0 4px 14px {sc["color"]}30;">
      <span style="color:white;">{_mini_svg(sc["svg"], 22, "white")}</span>
    </div>
    <div>
      <h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0;">{top_title}</h2>
      <div style="font-size:12px;color:#64748b;margin-top:2px;">{top_subtitle}</div>
    </div>
    <span style="margin-left:auto;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:800;color:{sc["color"]};background:white;border:2px solid {sc["color"]};">{status_label}</span>
  </div>
  <div style="display:grid;gap:12px;">
    <div style="padding:14px 18px;background:white;border-radius:12px;border:1px solid #e2e8f0;">
      <div style="font-size:10px;font-weight:700;color:{sc["color"]};text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;">{issue_label}</div>
      <div style="font-size:14px;font-weight:600;color:#0f172a;line-height:1.5;">{biggest_issue}</div>
    </div>
    <div style="padding:12px 18px;background:#fefce8;border-radius:10px;border:1px solid #fde68a;">
      <div style="font-size:10px;font-weight:700;color:#b45309;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">{impact_label}</div>
      <div style="font-size:13px;font-weight:600;color:#78350f;line-height:1.5;">{impact_time}</div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
      <div style="padding:12px 16px;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;">
        <div style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">{why_label}</div>
        <div style="font-size:13px;color:#334155;line-height:1.5;">{why}</div>
      </div>
      <div style="padding:12px 16px;background:#f0fdfa;border-radius:10px;border:1px solid #ccfbf1;">
        <div style="font-size:10px;font-weight:700;color:#0d9488;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;">{focus_label}</div>
        <div style="font-size:13px;color:#0f766e;line-height:1.5;">{focus}</div>
      </div>
    </div>
  </div>
</div>"""

    _next_action_row = (
        f'<div style="margin-top:10px;padding:10px 14px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0;">'
        f'<div style="font-size:10px;font-weight:700;color:#15803d;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:3px;">➡️ {action_label}</div>'
        f'<div style="font-size:12px;color:#14532d;line-height:1.5;">{risk_next_action}</div>'
        f"</div>"
    ) if risk_next_action else ""

    _if_nothing_row = (
        f'<div style="margin-top:10px;padding:12px 14px;background:#fffbeb;border-radius:8px;border:1px solid #fde68a;">'
        f'<div style="font-size:10px;font-weight:700;color:#b45309;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:7px;">⏩ {if_nothing_title}</div>'
        f'<div style="display:grid;gap:5px;">'
        f'<div style="font-size:11px;color:#78350f;line-height:1.5;"><span style="font-weight:700;color:#92400e;">{if_nothing_delay_label}:</span> {if_nothing_delay}</div>'
        f'<div style="font-size:11px;color:#78350f;line-height:1.5;"><span style="font-weight:700;color:#92400e;">{if_nothing_bottleneck_label}:</span> {if_nothing_bottleneck}</div>'
        f'<div style="font-size:11px;color:#78350f;line-height:1.5;"><span style="font-weight:700;color:#92400e;">{if_nothing_next_issue_label}:</span> {if_nothing_next_issue}</div>'
        f"</div></div>"
    ) if if_nothing_delay else ""

    biggest_risk_html = f"""
<div id="section-biggest-risk" style="margin:0 0 16px 0;padding:20px 24px;background:linear-gradient(135deg,#fef2f2,#ffffff);border-radius:14px;border:1px solid #fecaca;border-left:4px solid #ef4444;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
    <span style="display:inline-flex;">{_mini_svg("alert-triangle", 20, "#ef4444")}</span>
    <span style="font-size:14px;font-weight:800;color:#dc2626;text-transform:uppercase;letter-spacing:0.5px;">{risk_title}</span>
  </div>
  <div style="font-size:14px;font-weight:600;color:#0f172a;line-height:1.55;margin-bottom:12px;">{biggest_risk}</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
    <div style="padding:10px 14px;background:white;border-radius:8px;border:1px solid #fecaca;">
      <div style="font-size:10px;font-weight:700;color:#991b1b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:3px;">{blocking_label}</div>
      <div style="font-size:12px;color:#7f1d1d;line-height:1.5;">{risk_blocking}</div>
    </div>
    <div style="padding:10px 14px;background:white;border-radius:8px;border:1px solid #fecaca;">
      <div style="font-size:10px;font-weight:700;color:#991b1b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:3px;">{delay_label}</div>
      <div style="font-size:12px;color:#7f1d1d;line-height:1.5;">{risk_delay}</div>
    </div>
  </div>
  {_next_action_row}
  {_if_nothing_row}
</div>"""

    estimated_impact_html = f"""
<div id="section-estimated-impact" style="margin:0 0 16px 0;padding:20px 24px;background:linear-gradient(135deg,#fffbeb,#ffffff);border-radius:14px;border:1px solid #fde68a;border-left:4px solid #d97706;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
    <span style="display:inline-flex;">{_mini_svg("alert-circle", 20, "#d97706")}</span>
    <span style="font-size:14px;font-weight:800;color:#b45309;text-transform:uppercase;letter-spacing:0.5px;">{impact_title}</span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">
    <div style="padding:14px;background:white;border-radius:10px;border:1px solid #fde68a;text-align:center;">
      <div style="font-size:10px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">{time_label}</div>
      <div style="font-size:13px;font-weight:700;color:#78350f;line-height:1.4;">{impact_time}</div>
    </div>
    <div style="padding:14px;background:white;border-radius:10px;border:1px solid #fde68a;text-align:center;">
      <div style="font-size:10px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">{cost_label}</div>
      <div style="font-size:13px;font-weight:700;color:#78350f;line-height:1.4;">{impact_cost}</div>
    </div>
    <div style="padding:14px;background:white;border-radius:10px;border:1px solid #fde68a;text-align:center;">
      <div style="font-size:10px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">{phases_label}</div>
      <div style="font-size:13px;font-weight:700;color:#78350f;line-height:1.4;">{impact_phases}</div>
    </div>
  </div>
</div>"""

    conf_label = cc["label_da"] if language == "da" else cc["label_en"]
    confidence_html = f"""
<div id="section-confidence-level" style="margin:0 0 20px 0;padding:16px 24px;background:linear-gradient(135deg,#f8fafc,#ffffff);border-radius:14px;border:1px solid #e2e8f0;border-left:4px solid {cc["color"]};box-shadow:0 1px 4px rgba(0,0,0,0.03);">
  <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
    <div style="display:flex;align-items:center;gap:8px;">
      <span style="display:inline-flex;">{_mini_svg("shield-check", 18, cc["color"])}</span>
      <span style="font-size:13px;font-weight:800;color:#475569;text-transform:uppercase;letter-spacing:0.5px;">{conf_title}</span>
    </div>
    <span style="padding:4px 14px;border-radius:20px;font-size:12px;font-weight:800;color:{cc["color"]};background:white;border:2px solid {cc["color"]};">{conf_label}</span>
    <span style="font-size:12px;color:#64748b;font-style:italic;flex:1;min-width:200px;">{basis_label}: {confidence_basis}</span>
  </div>
</div>"""

    return (
        executive_top_html + biggest_risk_html + estimated_impact_html + confidence_html
    )


def generate_executive_html(content: str, language: str = "en") -> str:
    if not content or not content.strip():
        return ""

    content = re.sub(r"<!--EXEC_SUMMARY:.*?-->", "", content, flags=re.DOTALL).strip()
    content = re.sub(
        r"<!--DECISION_ENGINE:.*?-->", "", content, flags=re.DOTALL
    ).strip()

    if not content.strip():
        return ""

    title = "Anbefalede Handlinger" if language == "da" else "Recommended Actions"
    icon = SVG_ICONS.get("executive", SVG_ICONS["default"])
    color = "#0d9488"

    subtitle = (
        "Baseret på analysen — de vigtigste næste skridt"
        if language == "da"
        else "Based on the analysis — your most important next steps"
    )

    lines = content.split("\n")
    action_cards = []
    current_card = None

    def _priority_label(dot_color):
        if dot_color == "#ef4444":
            return (
                ("Critical", "Kritisk") if language != "da" else ("Kritisk", "Kritisk")
            )
        elif dot_color == "#f59e0b":
            return ("Important", "Vigtig") if language != "da" else ("Vigtig", "Vigtig")
        else:
            return ("Low", "Lav") if language != "da" else ("Lav", "Lav")

    def flush_card():
        nonlocal current_card
        if current_card:
            dot_color = current_card["color"]
            num = current_card["num"]
            priority_text = _priority_label(dot_color)[0]

            why_html = ""
            if current_card.get("why"):
                why_label = "Hvorfor" if language == "da" else "Why"
                why_html = f"""<div style="margin:10px 0 0 0;padding:10px 14px;background:linear-gradient(135deg,#f8fafc,#f1f5f9);border-radius:10px;border:1px solid #e2e8f0;">
                  <div style="display:flex;align-items:flex-start;gap:8px;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" style="flex-shrink:0;margin-top:2px;"><circle cx="12" cy="12" r="10" stroke="#0d9488" stroke-width="2"/><path d="M12 16v-4M12 8h.01" stroke="#0d9488" stroke-width="2.5" stroke-linecap="round"/></svg>
                    <div><span style="font-size:10px;font-weight:700;color:#0d9488;text-transform:uppercase;letter-spacing:0.5px;">{why_label}</span><div style="font-size:13px;color:#475569;line-height:1.5;margin-top:2px;">{current_card["why"]}</div></div>
                  </div>
                </div>"""

            pills = []
            pills.append(
                f'<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:{dot_color}10;border:1px solid {dot_color}25;border-radius:6px;font-size:11px;font-weight:700;color:{dot_color};text-transform:uppercase;letter-spacing:0.3px;"><span style="width:6px;height:6px;border-radius:50%;background:{dot_color};"></span>{priority_text}</span>'
            )

            if current_card.get("role"):
                role_label = current_card["role"]
                pills.append(f"""<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:#6366f108;border:1px solid #6366f120;border-radius:6px;">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" stroke="#6366f1" stroke-width="2.5"/><circle cx="12" cy="7" r="4" stroke="#6366f1" stroke-width="2.5"/></svg>
                  <span style="font-size:11px;font-weight:600;color:#4f46e5;">{role_label}</span>
                </span>""")

            if current_card.get("effort"):
                effort_label = current_card["effort"]
                pills.append(f"""<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:#f59e0b08;border:1px solid #f59e0b20;border-radius:6px;">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="#d97706" stroke-width="2"/><path d="M12 6v6l4 2" stroke="#d97706" stroke-width="2" stroke-linecap="round"/></svg>
                  <span style="font-size:11px;font-weight:600;color:#b45309;">{effort_label}</span>
                </span>""")

            pills_html = f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;">{"".join(pills)}</div>'

            related_html = ""
            if current_card.get("related"):
                ids_data = current_card["related"]
                related_html = f"""<div style="display:flex;align-items:flex-start;gap:6px;margin-top:8px;padding:6px 10px;background:#8b5cf606;border-radius:6px;">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" style="flex-shrink:0;margin-top:3px;"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" stroke="#8b5cf6" stroke-width="2.5" stroke-linecap="round"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" stroke="#8b5cf6" stroke-width="2.5" stroke-linecap="round"/></svg>
                  <span style="font-size:11px;font-weight:500;color:#64748b;line-height:1.4;overflow-wrap:break-word;">{ids_data}</span>
                </div>"""

            body_html = "".join(current_card["body"]) if current_card["body"] else ""

            action_cards.append(f"""
    <div style="margin:0 0 14px 0;background:white;border-radius:14px;border:1px solid #e2e8f0;box-shadow:0 1px 4px rgba(0,0,0,0.04);overflow:hidden;">
      <div style="display:flex;align-items:stretch;">
        <div style="width:4px;background:{dot_color};flex-shrink:0;"></div>
        <div style="flex:1;padding:18px 22px;">
          <div style="display:flex;align-items:flex-start;gap:12px;">
            <div style="width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,{dot_color},{dot_color}cc);color:white;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px;flex-shrink:0;box-shadow:0 2px 6px {dot_color}35;">{num}</div>
            <div style="flex:1;min-width:0;">
              <div style="font-size:14px;font-weight:700;color:#0f172a;line-height:1.55;">{current_card["title"]}</div>
              {body_html}
              {why_html}
              {pills_html}
              {related_html}
            </div>
          </div>
        </div>
      </div>
    </div>""")
            current_card = None

    for line in lines:
        line = line.strip()
        if not line or line in ["---", "***"]:
            continue

        if re.match(r"^##\s", line):
            continue

        priority_match = re.match(
            r"^(?:🔴|🟠|🟢)?\s*\*\*(\d+)[\.\)]\s*(.+?)\*\*\s*$", line
        )
        if not priority_match:
            priority_match = re.match(
                r"^(?:🔴|🟠|🟢)?\s*(\d+)[\.\)]\s*\*\*(.+?)\*\*\s*$", line
            )
        if not priority_match:
            priority_match = re.match(
                r"^(?:🔴|🟠|🟢)?\s*\*\*(?:Action|Handling|Anbefaling)\s*(\d+)[:\.\)]\s*(.+?)\*\*\s*$",
                line,
                re.IGNORECASE,
            )
        if priority_match:
            flush_card()
            num = priority_match.group(1)
            text = escape_html(priority_match.group(2))
            dot = ""
            if "🔴" in line:
                dot = "critical"
            elif "🟠" in line:
                dot = "important"
            elif "🟢" in line:
                dot = "low"
            dot_color = {
                "critical": "#ef4444",
                "important": "#f59e0b",
                "low": "#10b981",
            }.get(dot, color)
            current_card = {
                "num": num,
                "title": text,
                "color": dot_color,
                "body": [],
                "why": "",
                "role": "",
                "effort": "",
                "related": "",
            }
            continue

        if current_card:
            why_match = re.match(
                r"^(?:\*\*)?WHY(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if why_match:
                current_card["why"] = escape_html(why_match.group(1).strip())
                continue

            what_match = re.match(
                r"^(?:\*\*)?WHAT(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if what_match:
                what_text = escape_html(what_match.group(1).strip())
                if not current_card["title"]:
                    current_card["title"] = what_text
                else:
                    current_card["body"].append(
                        f'<p style="margin:4px 0;color:#475569;font-size:13px;line-height:1.6;">{what_text}</p>'
                    )
                continue

            priority_field = re.match(
                r"^(?:\*\*)?PRIORITY(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if priority_field:
                pval = priority_field.group(1).strip().lower()
                if "critical" in pval or "🔴" in pval or "kritisk" in pval:
                    current_card["color"] = "#ef4444"
                elif "important" in pval or "🟠" in pval or "vigtig" in pval:
                    current_card["color"] = "#f59e0b"
                elif "low" in pval or "🟢" in pval or "lav" in pval:
                    current_card["color"] = "#10b981"
                continue

            role_match = re.match(
                r"^(?:\*\*)?ROLE(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if role_match:
                current_card["role"] = escape_html(role_match.group(1).strip())
                continue

            effort_match = re.match(
                r"^(?:\*\*)?EFFORT(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if effort_match:
                current_card["effort"] = escape_html(effort_match.group(1).strip())
                continue

            who_match = re.match(
                r"^(?:\*\*)?WHO(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if who_match:
                current_card["role"] = escape_html(who_match.group(1).strip())
                continue

            when_match = re.match(
                r"^(?:\*\*)?WHEN(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if when_match:
                when_text = escape_html(when_match.group(1).strip())
                current_card["body"].append(
                    f'<p style="margin:4px 0;color:#475569;font-size:13px;line-height:1.6;"><strong style="color:#1e293b;font-weight:700;">When:</strong> {when_text}</p>'
                )
                continue

            related_match = re.match(
                r"^(?:\*\*)?RELATED(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if related_match:
                raw_ids = related_match.group(1).strip()
                id_list = [
                    x.strip() for x in re.split(r"[,;]\s*", raw_ids) if x.strip()
                ]
                if len(id_list) > 10:
                    visible = escape_html(", ".join(id_list[:10]))
                    rest_count = len(id_list) - 10
                    current_card["related"] = (
                        f'{visible} <span style="color:#8b5cf6;font-weight:600;">+{rest_count} more</span>'
                    )
                else:
                    current_card["related"] = escape_html(", ".join(id_list))
                continue

            impact_match = re.match(
                r"^(?:↳\s*)?(?:\*\*)?IMPACT(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if impact_match:
                if not current_card["why"]:
                    current_card["why"] = escape_html(impact_match.group(1).strip())
                continue

            deadline_match = re.match(
                r"^(?:\*\*)?DEADLINE(?:\*\*)?:\s*(.+)$", line, re.IGNORECASE
            )
            if deadline_match:
                dl_text = escape_html(deadline_match.group(1).strip())
                current_card["body"].append(
                    f'<p style="margin:4px 0;color:#475569;font-size:13px;line-height:1.6;"><strong style="color:#1e293b;font-weight:700;">Deadline:</strong> {dl_text}</p>'
                )
                continue

            text = _inline_markdown(line)
            current_card["body"].append(
                f'<p style="margin:4px 0;color:#475569;font-size:13px;line-height:1.6;">{text}</p>'
            )
            continue

        text = _inline_markdown(line)
        action_cards.append(
            f'<p style="margin:8px 0;color:#475569;font-size:14px;line-height:1.7;">{text}</p>'
        )

    flush_card()

    return f"""
<div id="section-recommended-actions" class="executive-section" style="margin:0 0 24px 0;padding:28px;background:linear-gradient(145deg,#f0fdfa,#f8fffe,#ffffff);border-radius:16px;border:1px solid rgba(13,148,136,0.15);box-shadow:0 1px 3px rgba(0,0,0,0.03);">
  {_render_section_header(title, icon, color)}
  <div style="margin:-8px 0 18px 0;padding:8px 14px;background:#f0fdfa;border-radius:8px;border:1px solid #ccfbf1;">
    <span style="font-size:13px;color:#0f766e;font-style:italic;">{subtitle}</span>
  </div>
  {"".join(action_cards)}
</div>"""


def generate_root_cause_html(content: str, language: str = "en") -> str:
    if not content or not content.strip():
        return ""

    title = "Årsagsanalyse" if language == "da" else "Root Cause Analysis"
    icon = SVG_ICONS.get("rootcause", SVG_ICONS["default"])
    color = "#6366f1"

    lines = content.split("\n")
    processed = []
    current_cause_items = []
    in_cause_block = False

    def flush_cause_items():
        nonlocal current_cause_items
        if current_cause_items:
            processed.append(
                '<div style="display:flex;flex-direction:column;gap:10px;margin-top:12px;">'
            )
            for item in current_cause_items:
                processed.append(item)
            processed.append("</div>")
            current_cause_items = []

    for line in lines:
        line = line.strip()
        if not line or line in ["---", "***"]:
            continue

        if re.match(r"^##\s", line):
            continue

        sub_header = re.match(r"^###\s*(.+)$", line)
        if sub_header:
            flush_cause_items()
            header_text = escape_html(sub_header.group(1).strip())
            in_cause_block = True
            processed.append(f"""
    <div style="margin:16px 0 12px 0;padding:14px 18px;background:linear-gradient(135deg,#6366f108,#6366f103);border-radius:10px;border-left:3px solid #6366f1;">
      <h3 style="font-size:15px;font-weight:700;color:#312e81;margin:0;line-height:1.4;">{header_text}</h3>
    </div>""")
            continue

        label_value = re.match(r"^\*\*([^*]+?):\*\*\s*(.+)$", line)
        if label_value:
            label = escape_html(label_value.group(1).strip())
            value = _inline_markdown(label_value.group(2).strip())

            label_lower = label.lower()
            if any(k in label_lower for k in ["manpower", "mandskab", "adding"]):
                will_help = any(
                    k in value.lower()
                    for k in ["will not", "useless", "hjælper ikke", "no ", "ikke"]
                )
                badge_color = "#ef4444" if will_help else "#10b981"
                badge_svg = (
                    _mini_svg("circle-x", 14, badge_color)
                    if will_help
                    else _mini_svg("circle-check", 14, badge_color)
                )
                current_cause_items.append(f"""<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;background:white;border-radius:10px;border:1px solid #e2e8f0;">
                  <div style="width:24px;height:24px;border-radius:6px;background:{badge_color}12;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">
                    {badge_svg}
                  </div>
                  <div><span style="font-size:11px;font-weight:700;color:#6366f1;text-transform:uppercase;letter-spacing:0.5px;">{label}</span><div style="font-size:13px;color:#475569;line-height:1.5;margin-top:2px;">{value}</div></div>
                </div>""")
            elif any(
                k in label_lower for k in ["affected", "berørt", "task", "opgave"]
            ):
                current_cause_items.append(f"""<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;background:white;border-radius:10px;border:1px solid #e2e8f0;">
                  <div style="width:24px;height:24px;border-radius:6px;background:#8b5cf612;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" stroke="#8b5cf6" stroke-width="2.5"/><rect x="9" y="3" width="6" height="4" rx="1" stroke="#8b5cf6" stroke-width="2"/></svg>
                  </div>
                  <div><span style="font-size:11px;font-weight:700;color:#8b5cf6;text-transform:uppercase;letter-spacing:0.5px;">{label}</span><div style="font-size:13px;color:#475569;line-height:1.5;margin-top:2px;">{value}</div></div>
                </div>""")
            elif any(
                k in label_lower
                for k in ["required", "action", "handling", "key", "nøgle", "insight"]
            ):
                current_cause_items.append(f"""<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;background:white;border-radius:10px;border:1px solid #e2e8f0;">
                  <div style="width:24px;height:24px;border-radius:6px;background:#0d948812;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" stroke="#0d9488" stroke-width="2.5" stroke-linecap="round"/><polyline points="22 4 12 14.01 9 11.01" stroke="#0d9488" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </div>
                  <div><span style="font-size:11px;font-weight:700;color:#0d9488;text-transform:uppercase;letter-spacing:0.5px;">{label}</span><div style="font-size:13px;color:#475569;line-height:1.5;margin-top:2px;">{value}</div></div>
                </div>""")
            else:
                current_cause_items.append(f"""<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;background:white;border-radius:10px;border:1px solid #e2e8f0;">
                  <div style="width:24px;height:24px;border-radius:6px;background:#64748b12;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">
                    {_mini_svg("info", 14, "#64748b")}
                  </div>
                  <div><span style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;">{label}</span><div style="font-size:13px;color:#475569;line-height:1.5;margin-top:2px;">{value}</div></div>
                </div>""")
            continue

        bold_only = re.match(r"^\*\*([^*]+)\*\*\s*$", line)
        if bold_only:
            flush_cause_items()
            header_text = escape_html(bold_only.group(1).rstrip(":"))
            processed.append(
                f'<h4 style="font-size:13px;font-weight:700;color:#6366f1;margin:18px 0 8px 0;text-transform:uppercase;letter-spacing:0.5px;">{header_text}</h4>'
            )
            continue

        if line.startswith("• ") or line.startswith("* ") or line.startswith("- "):
            item_text = _inline_markdown(line[2:])
            current_cause_items.append(f"""<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 14px;">
              <span style="display:inline-flex;margin-top:4px;flex-shrink:0;">{_mini_svg("chevron-right", 12, "#6366f1")}</span>
              <span style="font-size:13px;color:#475569;line-height:1.6;">{item_text}</span>
            </div>""")
            continue

        flush_cause_items()
        text = _inline_markdown(line)
        processed.append(
            f'<p style="margin:8px 0;color:#475569;font-size:14px;line-height:1.7;">{text}</p>'
        )

    flush_cause_items()

    return f"""
<div id="section-root-cause" class="root-cause-section" style="margin:0 0 24px 0;padding:28px;background:linear-gradient(145deg,#eef2ff,#f5f3ff,#ffffff);border-radius:16px;border:1px solid rgba(99,102,241,0.12);box-shadow:0 1px 3px rgba(0,0,0,0.03);">
  {_render_section_header(title, icon, color)}
  {"".join(processed)}
</div>"""


def generate_impact_html(content: str, language: str = "en") -> str:
    if not content or not content.strip():
        return ""

    title = "Konsekvensvurdering" if language == "da" else "Impact Assessment"
    icon = SVG_ICONS.get("impact", SVG_ICONS["default"])
    color = "#d97706"

    lines = content.split("\n")
    processed = []
    list_items = []
    in_consequences_block = False
    consequences_items = []

    def flush_list():
        nonlocal list_items
        if list_items:
            processed.append(
                '<div style="display:flex;flex-direction:column;gap:6px;margin:8px 0;">'
            )
            for item in list_items:
                processed.append(item)
            processed.append("</div>")
            list_items = []

    def flush_consequences():
        nonlocal consequences_items, in_consequences_block
        if consequences_items:
            cons_title = (
                "Hvis ingen handling tages"
                if language == "da"
                else "If No Action Is Taken"
            )
            cons_html = ""
            for c in consequences_items:
                cons_html += f'<div style="display:flex;align-items:flex-start;gap:10px;padding:6px 0;"><span style="display:inline-flex;margin-top:2px;flex-shrink:0;">{_mini_svg("arrow-right", 14, "#dc2626")}</span><span style="font-size:13px;color:#991b1b;line-height:1.6;font-weight:500;">{c}</span></div>'
            processed.append(f"""
    <div style="margin:20px 0 8px 0;padding:18px 22px;background:linear-gradient(135deg,#fef2f2,#fff1f2);border-radius:12px;border:1px solid #fecaca;border-left:4px solid #dc2626;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" stroke="#dc2626" stroke-width="2"/><path d="M12 9v4M12 17h.01" stroke="#dc2626" stroke-width="2.5" stroke-linecap="round"/></svg>
        <span style="font-size:12px;font-weight:800;color:#991b1b;text-transform:uppercase;letter-spacing:0.8px;">{cons_title}</span>
      </div>
      {cons_html}
    </div>""")
            consequences_items = []
        in_consequences_block = False

    for line in lines:
        line = line.strip()
        if not line or line in ["---", "***"]:
            if not in_consequences_block:
                flush_list()
            continue

        if re.match(r"^##\s", line):
            continue

        consequences_header = re.match(
            r"^###\s*CONSEQUENCES_IF_NO_ACTION", line, re.IGNORECASE
        )
        if consequences_header:
            flush_list()
            in_consequences_block = True
            continue

        if in_consequences_block:
            if re.match(r"^###\s", line):
                flush_consequences()
            elif (
                line.startswith("• ") or line.startswith("* ") or line.startswith("- ")
            ):
                consequences_items.append(_inline_markdown(line[2:]))
                continue
            elif re.match(r"^\*\*[^*]+\*\*", line):
                continue
            else:
                continue

        sub_header = re.match(r"^###\s*(.+)$", line)
        if sub_header:
            flush_list()
            header_text = escape_html(sub_header.group(1).strip())
            processed.append(f"""
    <div style="margin:16px 0 12px 0;padding:14px 18px;background:linear-gradient(135deg,#f59e0b08,#f59e0b03);border-radius:10px;border-left:3px solid #d97706;">
      <h3 style="font-size:15px;font-weight:700;color:#92400e;margin:0;line-height:1.4;">{header_text}</h3>
    </div>""")
            continue

        label_value = re.match(r"^\*\*([^*]+?):\*\*\s*(.+)$", line)
        if label_value:
            flush_list()
            label = escape_html(label_value.group(1).strip())
            value = _inline_markdown(label_value.group(2).strip())
            processed.append(f"""<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;margin:6px 0;background:white;border-radius:10px;border:1px solid #e2e8f0;">
              <div style="width:24px;height:24px;border-radius:6px;background:#d9770612;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">
                {_mini_svg("alert-circle", 14, "#d97706")}
              </div>
              <div><span style="font-size:11px;font-weight:700;color:#d97706;text-transform:uppercase;letter-spacing:0.5px;">{label}</span><div style="font-size:13px;color:#475569;line-height:1.5;margin-top:2px;">{value}</div></div>
            </div>""")
            continue

        bold_only = re.match(r"^\*\*([^*]+)\*\*\s*$", line)
        if bold_only:
            flush_list()
            header_text = escape_html(bold_only.group(1).rstrip(":"))
            processed.append(
                f'<h4 style="font-size:13px;font-weight:700;color:#d97706;margin:18px 0 8px 0;text-transform:uppercase;letter-spacing:0.5px;">{header_text}</h4>'
            )
            continue

        if line.startswith("• ") or line.startswith("* ") or line.startswith("- "):
            item_text = _inline_markdown(line[2:])
            list_items.append(f"""<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 14px;">
              <span style="display:inline-flex;margin-top:4px;flex-shrink:0;">{_mini_svg("chevron-right", 12, "#d97706")}</span>
              <span style="font-size:13px;color:#475569;line-height:1.6;">{item_text}</span>
            </div>""")
            continue

        flush_list()
        text = _inline_markdown(line)
        processed.append(
            f'<p style="margin:8px 0;color:#475569;font-size:14px;line-height:1.7;">{text}</p>'
        )

    flush_list()
    flush_consequences()

    return f"""
<div id="section-impact" class="impact-section" style="margin:0 0 24px 0;padding:28px;background:linear-gradient(145deg,#fffbeb,#fefce8,#ffffff);border-radius:16px;border:1px solid rgba(217,119,6,0.12);box-shadow:0 1px 3px rgba(0,0,0,0.03);">
  {_render_section_header(title, icon, color)}
  {"".join(processed)}
</div>"""


def _fix_summary_counts(
    text: str, actual_counts: Dict[str, int], total_data_rows: int = 0
) -> str:
    count_map = {
        "added": [
            "added",
            "new activities added",
            "new activities",
            "tilføjede",
            "nye aktiviteter",
        ],
        "removed": [
            "removed",
            "activities removed",
            "activities dropped",
            "fjernede",
            "aktiviteter fjernet",
        ],
        "delayed": ["delayed", "activities delayed", "forsinkede"],
        "accelerated": ["accelerated", "activities accelerated", "fremskyndede"],
        "moved": ["modified", "activities modified", "ændrede"],
    }
    for cat_key, keywords in count_map.items():
        if cat_key not in actual_counts:
            continue
        real_count = actual_counts[cat_key]
        for kw in keywords:
            text = re.sub(
                rf"(\d+\+?\s*(?:activities?\s+)?{re.escape(kw)})",
                lambda m, rc=real_count, k=kw: re.sub(
                    r"\d+\+?", str(rc), m.group(0), count=1
                ),
                text,
                flags=re.IGNORECASE,
            )
    if total_data_rows > 0:
        text = re.sub(
            r"[\d,.]+\+?\s*(?:tasks?|activities?|opgaver?)\s+(?:analyzed|analyseret|across)",
            lambda m: re.sub(
                r"[\d,.]+\+?", f"{total_data_rows:,}", m.group(0), count=1
            ),
            text,
            flags=re.IGNORECASE,
        )
    return text


def generate_summary_html(
    summary_content: str,
    language: str = "en",
    actual_counts: Dict[str, int] = None,
    total_data_rows: int = 0,
) -> str:
    if not summary_content or not summary_content.strip():
        return ""

    if actual_counts:
        summary_content = _fix_summary_counts(
            summary_content, actual_counts, total_data_rows
        )

    title = "Opsummering af Ændringer" if language == "da" else "Summary of Changes"
    icon = SVG_ICONS["summary"]
    color = "#8b5cf6"

    lines = summary_content.split("\n")
    processed = []
    list_items = []

    def flush_list():
        nonlocal list_items
        if list_items:
            processed.append(
                '<div style="display:flex;flex-direction:column;gap:6px;margin:8px 0;">'
            )
            for item in list_items:
                processed.append(item)
            processed.append("</div>")
            list_items = []

    for line in lines:
        line = line.strip()
        if not line or line in ["---", "***"]:
            flush_list()
            continue

        if re.match(
            r"^##\s*(SUMMARY_OF_CHANGES|OPSUMMERING_AF_ÆNDRINGER|Summary\s+of\s+Changes)",
            line,
            re.IGNORECASE,
        ):
            continue

        sub_header = re.match(r"^###\s*(.+)$", line)
        if sub_header:
            flush_list()
            header_text = escape_html(sub_header.group(1).strip())
            processed.append(f"""
    <div style="margin:16px 0 12px 0;padding:14px 18px;background:linear-gradient(135deg,#8b5cf608,#8b5cf603);border-radius:10px;border-left:3px solid #8b5cf6;">
      <h3 style="font-size:15px;font-weight:700;color:#5b21b6;margin:0;line-height:1.4;">{header_text}</h3>
    </div>""")
            continue

        bold_match = re.match(r"^\*\*([^*]+):\*\*$", line) or re.match(
            r"^\*\*([^*]+)\*\*$", line
        )
        if bold_match:
            flush_list()
            header_text = escape_html(bold_match.group(1).rstrip(":"))
            processed.append(
                f'<h4 style="font-size:13px;font-weight:700;color:#7c3aed;margin:18px 0 8px 0;text-transform:uppercase;letter-spacing:0.5px;">{header_text}</h4>'
            )
            continue

        label_value = re.match(r"^\*\*([^*]+?):\*\*\s*(.+)$", line)
        if label_value:
            flush_list()
            label = escape_html(label_value.group(1).strip())
            value = _inline_markdown(label_value.group(2).strip())
            processed.append(f"""<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;margin:6px 0;background:white;border-radius:10px;border:1px solid #e2e8f0;">
              <div style="width:24px;height:24px;border-radius:6px;background:#8b5cf612;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">
                {_mini_svg("info", 14, "#8b5cf6")}
              </div>
              <div><span style="font-size:11px;font-weight:700;color:#8b5cf6;text-transform:uppercase;letter-spacing:0.5px;">{label}</span><div style="font-size:13px;color:#475569;line-height:1.5;margin-top:2px;">{value}</div></div>
            </div>""")
            continue

        if line.startswith("• ") or line.startswith("* ") or line.startswith("- "):
            item_text = _inline_markdown(line[2:])
            list_items.append(f"""<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 14px;">
              <span style="display:inline-flex;margin-top:4px;flex-shrink:0;">{_mini_svg("chevron-right", 12, "#8b5cf6")}</span>
              <span style="font-size:13px;color:#475569;line-height:1.6;">{item_text}</span>
            </div>""")
            continue

        flush_list()
        text = _inline_markdown(line)
        processed.append(
            f'<p style="margin:8px 0;color:#475569;font-size:14px;line-height:1.7;">{text}</p>'
        )

    flush_list()

    return f"""
<div id="section-summary" class="summary-section" style="margin:0 0 24px 0;padding:28px;background:linear-gradient(145deg,#f5f3ff,#faf5ff,#ffffff);border-radius:16px;border:1px solid rgba(139,92,246,0.12);box-shadow:0 1px 3px rgba(0,0,0,0.03);">
  {_render_section_header(title, icon, color)}
  {"".join(processed)}
</div>"""


def generate_health_html(
    health_content: str,
    health_data: Optional[Dict],
    language: str = "en",
    actual_counts: Dict[str, int] = None,
    total_data_rows: int = 0,
) -> str:
    if not health_content or not health_content.strip():
        return ""

    if actual_counts:
        health_content = _fix_summary_counts(
            health_content, actual_counts, total_data_rows
        )

    status = "on_track"
    if health_data and health_data.get("status"):
        status = health_data["status"]
    else:
        _hcl = health_content.lower()
        if "critical" in _hcl or "high risk" in _hcl or "kritisk" in _hcl or "høj risiko" in _hcl:
            status = "critical"
        elif "at risk" in _hcl or "attention" in _hcl or "risiko" in _hcl or "opmærksomhed" in _hcl:
            status = "at_risk"

    status_config = {
        "on_track": {
            "color": "#10b981",
            "grad_from": "#ecfdf5",
            "grad_mid": "#f0fdf4",
            "label_en": "On Track",
            "label_da": "På Rette Spor",
        },
        "stable": {
            "color": "#10b981",
            "grad_from": "#ecfdf5",
            "grad_mid": "#f0fdf4",
            "label_en": "On Track",
            "label_da": "På Rette Spor",
        },
        "at_risk": {
            "color": "#f59e0b",
            "grad_from": "#fffbeb",
            "grad_mid": "#fefce8",
            "label_en": "At Risk",
            "label_da": "Risiko",
        },
        "attention": {
            "color": "#f59e0b",
            "grad_from": "#fffbeb",
            "grad_mid": "#fefce8",
            "label_en": "At Risk",
            "label_da": "Risiko",
        },
        "critical": {
            "color": "#ef4444",
            "grad_from": "#fef2f2",
            "grad_mid": "#fff1f2",
            "label_en": "Critical",
            "label_da": "Kritisk",
        },
        "high_risk": {
            "color": "#ef4444",
            "grad_from": "#fef2f2",
            "grad_mid": "#fff1f2",
            "label_en": "Critical",
            "label_da": "Kritisk",
        },
    }

    config = status_config.get(status, status_config["stable"])
    color = config["color"]
    grad_from = config["grad_from"]
    grad_mid = config["grad_mid"]
    status_label = config["label_da"] if language == "da" else config["label_en"]

    header_text = "Projektsundhed" if language == "da" else "Project Health"
    icon = SVG_ICONS["pulse"]

    lines = health_content.split("\n")
    processed = []
    list_items = []

    def flush_list():
        nonlocal list_items
        if list_items:
            processed.append(
                '<div style="display:flex;flex-direction:column;gap:6px;margin:8px 0;">'
            )
            for item in list_items:
                processed.append(item)
            processed.append("</div>")
            list_items = []

    for line in lines:
        line = line.strip()
        if not line or line == "---":
            flush_list()
            continue

        if re.match(r"^##\s*(PROJECT_HEALTH|PROJEKTSUNDHED)", line, re.IGNORECASE):
            continue

        if re.match(r"^\*\*Status:\*\*", line, re.IGNORECASE):
            continue

        sub_header = re.match(r"^###\s*(.+)$", line)
        if sub_header:
            flush_list()
            h_text = escape_html(sub_header.group(1).strip())
            processed.append(f"""
    <div style="margin:16px 0 12px 0;padding:14px 18px;background:linear-gradient(135deg,{color}08,{color}03);border-radius:10px;border-left:3px solid {color};">
      <h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0;line-height:1.4;">{h_text}</h3>
    </div>""")
            continue

        label_value = re.match(r"^\*\*([^*]+?):\*\*\s*(.+)$", line)
        if label_value:
            flush_list()
            label = escape_html(label_value.group(1).strip())
            value = _inline_markdown(label_value.group(2).strip())
            processed.append(f"""<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 14px;margin:6px 0;background:white;border-radius:10px;border:1px solid #e2e8f0;">
              <div style="width:24px;height:24px;border-radius:6px;background:{color}12;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;">
                {_mini_svg("info", 14, color)}
              </div>
              <div><span style="font-size:11px;font-weight:700;color:{color};text-transform:uppercase;letter-spacing:0.5px;">{label}</span><div style="font-size:13px;color:#475569;line-height:1.5;margin-top:2px;">{value}</div></div>
            </div>""")
            continue

        bold_match = re.match(r"^\*\*([^*]+)\*\*$", line)
        if bold_match:
            flush_list()
            h_text = escape_html(bold_match.group(1).rstrip(":"))
            processed.append(
                f'<h4 style="font-size:13px;font-weight:700;color:{color};margin:18px 0 8px 0;text-transform:uppercase;letter-spacing:0.5px;">{h_text}</h4>'
            )
            continue

        if line.startswith("• ") or line.startswith("* ") or line.startswith("- "):
            item_text = _inline_markdown(line[2:])
            list_items.append(f"""<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 14px;">
              <span style="display:inline-flex;margin-top:4px;flex-shrink:0;">{_mini_svg("chevron-right", 12, color)}</span>
              <span style="font-size:13px;color:#475569;line-height:1.6;">{item_text}</span>
            </div>""")
            continue

        flush_list()
        text = _inline_markdown(line)
        processed.append(
            f'<p style="margin:8px 0;color:#475569;font-size:14px;line-height:1.7;">{text}</p>'
        )

    flush_list()

    metrics_html = ""
    if health_data:
        metrics = []
        metric_items = [
            (
                "delayed_count",
                "#ef4444",
                "Forsinket" if language == "da" else "Delayed",
            ),
            (
                "accelerated_count",
                "#10b981",
                "Fremskyndet" if language == "da" else "Accelerated",
            ),
            ("added_count", "#06b6d4", "Tilføjet" if language == "da" else "Added"),
            ("removed_count", "#ef4444", "Fjernet" if language == "da" else "Removed"),
        ]
        for key, m_color, m_label in metric_items:
            val = health_data.get(key)
            if val is not None:
                if isinstance(val, int):
                    display_val = str(val)
                elif isinstance(val, str) and val.isdigit():
                    display_val = val
                else:
                    continue
                metrics.append(
                    f'<div style="text-align:center;padding:14px 10px;background:white;border-radius:10px;border:1px solid {m_color}20;"><div style="font-size:24px;font-weight:800;color:{m_color};">{display_val}</div><div style="font-size:10px;color:#64748b;text-transform:uppercase;margin-top:3px;font-weight:600;">{m_label}</div></div>'
                )

        if metrics:
            metrics_html = f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:10px;margin-top:20px;padding-top:20px;border-top:1px solid {color}15;">{"".join(metrics)}</div>'

    status_badge = f"""<div style="display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:50px;background:white;border:1px solid {color}25;">
        <div style="width:8px;height:8px;border-radius:50%;background:{color};box-shadow:0 0 6px {color}60;"></div>
        <span style="font-size:13px;font-weight:700;color:{color};">{status_label}</span>
      </div>"""

    risk_badge_html = ""
    if health_data and health_data.get("risk_level"):
        rl = health_data["risk_level"]
        rl_config = {
            "LOW": {
                "color": "#10b981",
                "label_en": "Low Risk",
                "label_da": "Lav Risiko",
            },
            "MEDIUM": {
                "color": "#d97706",
                "label_en": "Medium Risk",
                "label_da": "Moderat Risiko",
            },
            "HIGH": {
                "color": "#dc2626",
                "label_en": "High Risk",
                "label_da": "Høj Risiko",
            },
        }
        rl_c = rl_config.get(rl, rl_config["MEDIUM"])
        rl_label = rl_c["label_da"] if language == "da" else rl_c["label_en"]
        rl_svg_name = {
            "LOW": "shield-check",
            "MEDIUM": "alert-circle",
            "HIGH": "alert-triangle",
        }.get(rl, "alert-circle")
        risk_badge_html = f"""<div style="display:flex;align-items:center;gap:6px;padding:6px 14px;border-radius:50px;background:white;border:1px solid {rl_c["color"]}25;">
          <span style="display:inline-flex;">{_mini_svg(rl_svg_name, 14, rl_c["color"])}</span>
          <span style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;">{"Risiko" if language == "da" else "Risk"}:</span>
          <span style="font-size:12px;font-weight:800;color:{rl_c["color"]};">{rl_label}</span>
        </div>"""

    trend_badge_html = ""
    if health_data:
        trend_val = health_data.get("trend", "")
        if not trend_val:
            delayed_c = health_data.get("delayed_count", 0) or 0
            accel_c = health_data.get("accelerated_count", 0) or 0
            delayed_days = health_data.get("delayed_days_total", 0) or 0
            if accel_c > delayed_c:
                trend_val = "improving"
            elif delayed_c > accel_c * 2 or delayed_days > 60:
                trend_val = "worsening"
            else:
                trend_val = "stable"
        _trend_cfg = {
            "improving": {"icon": "⬆️", "color": "#10b981", "label_en": "Improving", "label_da": "Forbedring"},
            "stable":    {"icon": "➡️", "color": "#64748b", "label_en": "Stable",    "label_da": "Stabil"},
            "worsening": {"icon": "⬇️", "color": "#ef4444", "label_en": "Worsening", "label_da": "Forværring"},
        }.get(trend_val, {"icon": "➡️", "color": "#64748b", "label_en": "Stable", "label_da": "Stabil"})
        _trend_label = _trend_cfg["label_da"] if language == "da" else _trend_cfg["label_en"]
        _trend_head = "Tendens" if language == "da" else "Trend"
        trend_badge_html = f"""<div style="display:flex;align-items:center;gap:6px;padding:6px 14px;border-radius:50px;background:white;border:1px solid {_trend_cfg["color"]}25;">
          <span style="font-size:13px;">{_trend_cfg["icon"]}</span>
          <span style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;">{_trend_head}:</span>
          <span style="font-size:12px;font-weight:800;color:{_trend_cfg["color"]};">{_trend_label}</span>
        </div>"""

    conf_badge_html = ""
    if health_data and health_data.get("confidence"):
        _conf_val = str(health_data["confidence"]).upper()
        _conf_cfg = {
            "HIGH":   {"color": "#10b981", "label_en": "High Confidence",   "label_da": "Høj Sikkerhed"},
            "MEDIUM": {"color": "#d97706", "label_en": "Medium Confidence",  "label_da": "Moderat Sikkerhed"},
            "LOW":    {"color": "#dc2626", "label_en": "Low Confidence",     "label_da": "Lav Sikkerhed"},
        }.get(_conf_val, {"color": "#64748b", "label_en": "Confidence", "label_da": "Sikkerhed"})
        _conf_label = _conf_cfg["label_da"] if language == "da" else _conf_cfg["label_en"]
        conf_badge_html = f"""<div style="display:flex;align-items:center;gap:6px;padding:6px 14px;border-radius:50px;background:white;border:1px solid {_conf_cfg["color"]}25;">
          <span style="display:inline-flex;">{_mini_svg("shield-check", 14, _conf_cfg["color"])}</span>
          <span style="font-size:12px;font-weight:800;color:{_conf_cfg["color"]};">{_conf_label}</span>
        </div>"""

    return f"""
<div id="section-health" class="health-section" style="margin:0 0 24px 0;padding:28px;background:linear-gradient(145deg,{grad_from},{grad_mid},#ffffff);border-radius:16px;border:1px solid {color}18;box-shadow:0 1px 3px rgba(0,0,0,0.03);">
  <div style="display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:24px;padding-bottom:16px;border-bottom:2px solid {color}18;flex-wrap:wrap;">
    <div style="display:flex;align-items:center;gap:14px;">
      <div style="width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,{color},{color}dd);box-shadow:0 4px 14px {color}30;">
        <span style="color:white;">{icon}</span>
      </div>
      <h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0;letter-spacing:-0.3px;">{header_text}</h2>
    </div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
      {status_badge}
      {trend_badge_html}
      {risk_badge_html}
      {conf_badge_html}
    </div>
  </div>
  {"".join(processed)}
  {metrics_html}
</div>"""


def _count_actual_table_rows(tables_section: str) -> Dict[str, int]:
    sections = parse_tables_by_section(tables_section)
    counts = {}
    for cat, data in sections.items():
        counts[cat] = len(data.get("rows", []))
    return counts


def format_response_as_html(
    markdown: str,
    language: str = "en",
    total_data_rows: int = 0,
    diff_data: dict = None,
) -> str:
    try:
        return _format_response_internal(
            markdown, language, total_data_rows, diff_data=diff_data
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"HTML formatter error: {e}")
        safe_text = escape_html(markdown)
        return f'<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;padding:24px;"><div style="white-space:pre-wrap;color:#334155;line-height:1.7;font-size:14px;">{safe_text}</div></div>'


def _render_extra_content(content: str) -> str:
    if not content or not content.strip():
        return ""
    lines = content.strip().split("\n")
    parts = []
    for line in lines:
        line = line.strip()
        if not line or line in ["---", "***"]:
            continue
        if line.startswith("• ") or line.startswith("* ") or line.startswith("- "):
            item_text = _inline_markdown(line[2:])
            parts.append(
                f'<div style="display:flex;align-items:flex-start;gap:8px;padding:4px 14px;"><span style="display:inline-flex;margin-top:4px;flex-shrink:0;">{_mini_svg("chevron-right", 12, "#64748b")}</span><span style="font-size:13px;color:#475569;line-height:1.6;">{item_text}</span></div>'
            )
        else:
            text = _inline_markdown(line)
            parts.append(
                f'<p style="margin:6px 0;color:#475569;font-size:13px;line-height:1.6;">{text}</p>'
            )
    if not parts:
        return ""
    return f'<div style="margin:0 0 16px 0;padding:16px 20px;background:#f8fafc;border-radius:12px;border:1px solid #e2e8f0;">{"".join(parts)}</div>'


def _generate_diff_tables_html(diff_data: dict, language: str = "en") -> str:
    if not diff_data:
        return ""

    key_label = diff_data.get("key_label", "TBS")
    parts = []

    def _esc(v):
        return escape_html(str(v)) if v else "—"

    def _priority_badge(shift):
        if shift is None:
            return '<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;background:#fee2e2;color:#dc2626;">🔴 CRITICAL</span>'
        if abs(shift) > 30:
            return '<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;background:#fee2e2;color:#dc2626;">🔴 CRITICAL</span>'
        if abs(shift) > 7:
            return '<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;background:#fef3c7;color:#d97706;">🟠 IMPORTANT</span>'
        return '<span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;background:#ecfdf5;color:#059669;">🟢 LOW</span>'

    def _diff_badge(shift):
        if shift is None:
            return "—"
        color = "#dc2626" if shift > 0 else "#059669"
        sign = "+" if shift > 0 else ""
        return f'<span style="font-weight:700;color:{color};">{sign}{shift}d</span>'

    th_style = 'style="padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#0d9488;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #e2e8f0;background:#f0fdfa;"'
    td_style = 'style="padding:10px 14px;font-size:13px;color:#334155;border-bottom:1px solid #f1f5f9;"'
    table_wrap = 'style="width:100%;border-collapse:collapse;border-radius:12px;overflow:hidden;"'

    delayed = diff_data.get("delayed", [])
    if delayed:
        delayed_sorted = sorted(delayed, key=lambda r: -(r.get("date_shift") or 0))
        rows_html = ""
        for r in delayed_sorted:
            rows_html += f"<tr><td {td_style}>{_priority_badge(r.get('date_shift'))}</td><td {td_style}><strong>{_esc(r['key'])}</strong></td><td {td_style}>{_esc(r['old_name'])}</td><td {td_style}>{_esc(r.get('lokation', ''))}</td><td {td_style}>{_esc(r.get('old_slutdato', ''))}</td><td {td_style}>{_esc(r.get('new_slutdato', ''))}</td><td {td_style}>{_diff_badge(r.get('date_shift'))}</td><td {td_style}>{_esc(r.get('old_varighed', ''))} → {_esc(r.get('new_varighed', ''))}</td></tr>"
        parts.append(f"""<div class="category-section" style="margin:0 0 24px 0;padding:20px;background:#fff;border-radius:16px;border:1px solid #fee2e2;border-left:5px solid #ef4444;box-shadow:0 2px 10px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;"><span style="color:#ef4444;">{_mini_svg("clock", 22, "#ef4444")}</span><span style="font-size:18px;font-weight:800;color:#1e293b;">Delayed Tasks</span><span style="background:#ef4444;color:white;padding:2px 10px;border-radius:20px;font-size:13px;font-weight:700;">{len(delayed)}</span></div>
  <div style="overflow-x:auto;"><table {table_wrap}><thead><tr><th {th_style}>Priority</th><th {th_style}>{key_label}</th><th {th_style}>Navn</th><th {th_style}>Lokation</th><th {th_style}>Slutdato (A)</th><th {th_style}>Slutdato (B)</th><th {th_style}>Difference</th><th {th_style}>Varighed (A) → (B)</th></tr></thead><tbody>{rows_html}</tbody></table></div>
  <div style="margin-top:8px;font-size:12px;color:#94a3b8;">📊 Total: {len(delayed)} entries</div>
</div>""")

    accelerated = diff_data.get("accelerated", [])
    if accelerated:
        accel_sorted = sorted(accelerated, key=lambda r: r.get("date_shift") or 0)
        rows_html = ""
        for r in accel_sorted:
            rows_html += f"<tr><td {td_style}><strong>{_esc(r['key'])}</strong></td><td {td_style}>{_esc(r['old_name'])}</td><td {td_style}>{_esc(r.get('lokation', ''))}</td><td {td_style}>{_esc(r.get('old_slutdato', ''))}</td><td {td_style}>{_esc(r.get('new_slutdato', ''))}</td><td {td_style}>{_diff_badge(r.get('date_shift'))}</td><td {td_style}>{_esc(r.get('old_varighed', ''))} → {_esc(r.get('new_varighed', ''))}</td></tr>"
        parts.append(f"""<div class="category-section" style="margin:0 0 24px 0;padding:20px;background:#fff;border-radius:16px;border:1px solid #d1fae5;border-left:5px solid #10b981;box-shadow:0 2px 10px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;"><span style="color:#10b981;">{_mini_svg("zap", 22, "#10b981")}</span><span style="font-size:18px;font-weight:800;color:#1e293b;">Accelerated Tasks</span><span style="background:#10b981;color:white;padding:2px 10px;border-radius:20px;font-size:13px;font-weight:700;">{len(accelerated)}</span></div>
  <div style="overflow-x:auto;"><table {table_wrap}><thead><tr><th {th_style}>{key_label}</th><th {th_style}>Navn</th><th {th_style}>Lokation</th><th {th_style}>Slutdato (A)</th><th {th_style}>Slutdato (B)</th><th {th_style}>Difference</th><th {th_style}>Varighed (A) → (B)</th></tr></thead><tbody>{rows_html}</tbody></table></div>
  <div style="margin-top:8px;font-size:12px;color:#94a3b8;">📊 Total: {len(accelerated)} entries</div>
</div>""")

    rescheduled = diff_data.get("rescheduled", [])
    if rescheduled:
        resch_sorted = sorted(rescheduled, key=lambda r: abs(r.get("date_shift") or 0), reverse=True)
        rows_html = ""
        for r in resch_sorted:
            ds = r.get("date_shift")
            sds = r.get("start_date_shift")
            shift_str = f"+{ds}d" if ds and ds > 0 else f"{ds}d" if ds else "—"
            rows_html += (
                f"<tr>"
                f"<td {td_style}><strong>{_esc(r['key'])}</strong></td>"
                f"<td {td_style}>{_esc(r['old_name'])}</td>"
                f"<td {td_style}>{_esc(r.get('lokation', ''))}</td>"
                f"<td {td_style}>{_esc(r.get('old_startdato', ''))} → {_esc(r.get('new_startdato', ''))}</td>"
                f"<td {td_style}>{_esc(r.get('old_slutdato', ''))} → {_esc(r.get('new_slutdato', ''))}</td>"
                f"<td {td_style}><span style='font-weight:700;color:#0ea5e9;'>{shift_str}</span></td>"
                f"<td {td_style}>{_esc(r.get('old_varighed', ''))}</td>"
                f"</tr>"
            )
        parts.append(f"""<div class="category-section" style="margin:0 0 24px 0;padding:20px;background:#fff;border-radius:16px;border:1px solid #bae6fd;border-left:5px solid #0ea5e9;box-shadow:0 2px 10px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;"><span style="color:#0ea5e9;">{_mini_svg("moved", 22, "#0ea5e9")}</span><span style="font-size:18px;font-weight:800;color:#1e293b;">Rescheduled Tasks</span><span style="background:#0ea5e9;color:white;padding:2px 10px;border-radius:20px;font-size:13px;font-weight:700;">{len(rescheduled)}</span><span style="margin-left:6px;font-size:12px;color:#64748b;">Whole task window shifted — duration unchanged</span></div>
  <div style="overflow-x:auto;"><table {table_wrap}><thead><tr><th {th_style}>{key_label}</th><th {th_style}>Navn</th><th {th_style}>Lokation</th><th {th_style}>Start A → B</th><th {th_style}>End A → B</th><th {th_style}>Shift</th><th {th_style}>Varighed</th></tr></thead><tbody>{rows_html}</tbody></table></div>
  <div style="margin-top:8px;font-size:12px;color:#94a3b8;">📊 Total: {len(rescheduled)} entries — task windows moved without extension</div>
</div>""")

    added = diff_data.get("added", [])
    if added:
        rows_html = ""
        for r in added:
            rows_html += f"<tr><td {td_style}><strong>{_esc(r['key'])}</strong></td><td {td_style}>{_esc(r.get('name', ''))}</td><td {td_style}>{_esc(r.get('aktivitetstype', ''))}</td><td {td_style}>{_esc(r.get('lokation', ''))}</td><td {td_style}>{_esc(r.get('startdato', ''))}</td><td {td_style}>{_esc(r.get('slutdato', ''))}</td><td {td_style}>{_esc(r.get('varighed', ''))}</td></tr>"
        parts.append(f"""<div class="category-section" style="margin:0 0 24px 0;padding:20px;background:#fff;border-radius:16px;border:1px solid #dbeafe;border-left:5px solid #3b82f6;box-shadow:0 2px 10px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;"><span style="color:#3b82f6;">{_mini_svg("plus", 22, "#3b82f6")}</span><span style="font-size:18px;font-weight:800;color:#1e293b;">Added Tasks</span><span style="background:#3b82f6;color:white;padding:2px 10px;border-radius:20px;font-size:13px;font-weight:700;">{len(added)}</span></div>
  <div style="overflow-x:auto;"><table {table_wrap}><thead><tr><th {th_style}>{key_label}</th><th {th_style}>Navn</th><th {th_style}>Type</th><th {th_style}>Lokation</th><th {th_style}>Startdato</th><th {th_style}>Slutdato</th><th {th_style}>Varighed</th></tr></thead><tbody>{rows_html}</tbody></table></div>
  <div style="margin-top:8px;font-size:12px;color:#94a3b8;">📊 Total: {len(added)} entries</div>
</div>""")

    removed = diff_data.get("removed", [])
    if removed:
        rows_html = ""
        for r in removed:
            rows_html += f"<tr><td {td_style}><strong>{_esc(r['key'])}</strong></td><td {td_style}>{_esc(r.get('name', ''))}</td><td {td_style}>{_esc(r.get('aktivitetstype', ''))}</td><td {td_style}>{_esc(r.get('lokation', ''))}</td><td {td_style}>{_esc(r.get('slutdato', ''))}</td><td {td_style}>{_esc(r.get('varighed', ''))}</td></tr>"
        parts.append(f"""<div class="category-section" style="margin:0 0 24px 0;padding:20px;background:#fff;border-radius:16px;border:1px solid #fecaca;border-left:5px solid #dc2626;box-shadow:0 2px 10px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;"><span style="color:#dc2626;">{_mini_svg("minus", 22, "#dc2626")}</span><span style="font-size:18px;font-weight:800;color:#1e293b;">Removed Tasks</span><span style="background:#dc2626;color:white;padding:2px 10px;border-radius:20px;font-size:13px;font-weight:700;">{len(removed)}</span></div>
  <div style="overflow-x:auto;"><table {table_wrap}><thead><tr><th {th_style}>{key_label}</th><th {th_style}>Navn</th><th {th_style}>Type</th><th {th_style}>Lokation</th><th {th_style}>Slutdato</th><th {th_style}>Varighed</th></tr></thead><tbody>{rows_html}</tbody></table></div>
  <div style="margin-top:8px;font-size:12px;color:#94a3b8;">📊 Total: {len(removed)} entries</div>
</div>""")

    modified = diff_data.get("modified", [])
    if modified:
        rows_html = ""
        for r in modified:
            change_text = "; ".join(
                f"{c['field']}: {_esc(c['old'])} → {_esc(c['new'])}"
                for c in r.get("changes", [])[:3]
            )
            rows_html += f"<tr><td {td_style}><strong>{_esc(r['key'])}</strong></td><td {td_style}>{_esc(r['old_name'])}</td><td {td_style}>{change_text}</td></tr>"
        parts.append(f"""<div class="category-section" style="margin:0 0 24px 0;padding:20px;background:#fff;border-radius:16px;border:1px solid #e9d5ff;border-left:5px solid #8b5cf6;box-shadow:0 2px 10px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;"><span style="color:#8b5cf6;">{_mini_svg("edit", 22, "#8b5cf6")}</span><span style="font-size:18px;font-weight:800;color:#1e293b;">Modified Tasks</span><span style="background:#8b5cf6;color:white;padding:2px 10px;border-radius:20px;font-size:13px;font-weight:700;">{len(modified)}</span></div>
  <div style="overflow-x:auto;"><table {table_wrap}><thead><tr><th {th_style}>{key_label}</th><th {th_style}>Navn</th><th {th_style}>Changes</th></tr></thead><tbody>{rows_html}</tbody></table></div>
  <div style="margin-top:8px;font-size:12px;color:#94a3b8;">📊 Total: {len(modified)} entries</div>
</div>""")

    return "\n".join(parts)


def generate_data_trust_html(content: str, language: str = "en") -> str:
    if not content or not content.strip():
        return ""

    title = "Datagrundlag" if language == "da" else "Data Trust — Analysis Basis"
    data_sub = (
        "📊 Data brugt i denne analyse"
        if language == "da"
        else "📊 Data Used in This Analysis"
    )
    filtered_label = "Hvad blev filtreret fra" if language == "da" else "What was filtered out"
    included_label = "Hvad er inkluderet" if language == "da" else "What is included"
    result_prefix = "Resultat" if language == "da" else "Result"

    lines = content.split("\n")
    col_a_header = "Schedule A (OLD)"
    col_b_header = "Schedule B (NEW)"
    table_rows = []
    in_table = False
    filter_items: list = []
    include_items: list = []
    result_sentence = ""
    current_list: list = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^##\s*(DATA_TRUST|DATAGRUNDLAG)", stripped, re.IGNORECASE):
            continue
        if re.match(r"^📊", stripped):
            continue

        if "|" in stripped:
            if re.match(r"^[\-\|:\s]+$", stripped):
                in_table = True
                continue
            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 3:
                if any(
                    kw in cells[1] for kw in ["Schedule A", "OLD", "Skema A"]
                ) or any(kw in cells[2] for kw in ["Schedule B", "NEW", "Skema B"]):
                    col_a_header = cells[1]
                    col_b_header = cells[2]
                    in_table = True
                    continue
                if in_table:
                    table_rows.append((cells[0], cells[1], cells[2]))
                    continue
            elif len(cells) == 2 and in_table:
                table_rows.append((cells[0], cells[1], ""))
                continue
            in_table = False
            continue

        in_table = False

        low = stripped.lower()
        if "what was filtered" in low or "hvad blev filtreret" in low:
            current_list = filter_items
            continue
        if "what is included" in low or "hvad er inkluderet" in low:
            current_list = include_items
            continue
        if low.startswith("result:") or low.startswith("resultat:"):
            sep = stripped.index(":") + 1
            result_sentence = stripped[sep:].strip()
            current_list = None
            continue
        if stripped.startswith(("- ", "• ", "* ")) and current_list is not None:
            current_list.append(_inline_markdown(stripped[2:]))
            continue

    table_html = ""
    if table_rows:
        rows_html = ""
        for label, val_a, val_b in table_rows:
            rows_html += (
                f"<tr>"
                f'<td style="padding:10px 14px;font-size:13px;font-weight:600;color:#0c4a6e;'
                f"border-bottom:1px solid #e0f2fe;background:#f0f9ff;white-space:nowrap;\">"
                f"{escape_html(label)}</td>"
                f'<td style="padding:10px 14px;font-size:13px;color:#334155;border-bottom:1px solid #e0f2fe;'
                f'text-align:center;">{escape_html(val_a)}</td>'
                f'<td style="padding:10px 14px;font-size:13px;color:#334155;border-bottom:1px solid #e0f2fe;'
                f'text-align:center;">{escape_html(val_b)}</td>'
                f"</tr>"
            )
        table_html = (
            f'<div style="overflow-x:auto;border-radius:10px;border:1px solid #bae6fd;margin:14px 0;">'
            f'<table style="width:100%;border-collapse:collapse;">'
            f"<thead><tr>"
            f'<th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:700;color:#0891b2;'
            f'text-transform:uppercase;letter-spacing:0.5px;background:#e0f2fe;border-bottom:2px solid #bae6fd;"> </th>'
            f'<th style="padding:10px 14px;text-align:center;font-size:11px;font-weight:700;color:#0891b2;'
            f"text-transform:uppercase;letter-spacing:0.5px;background:#e0f2fe;border-bottom:2px solid #bae6fd;\">"
            f"{escape_html(col_a_header)}</th>"
            f'<th style="padding:10px 14px;text-align:center;font-size:11px;font-weight:700;color:#0891b2;'
            f"text-transform:uppercase;letter-spacing:0.5px;background:#e0f2fe;border-bottom:2px solid #bae6fd;\">"
            f"{escape_html(col_b_header)}</th>"
            f"</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table></div>"
        )

    filter_html = ""
    if filter_items:
        items = "".join(
            f'<div style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;">'
            f'<span style="color:#dc2626;font-size:13px;flex-shrink:0;">✕</span>'
            f'<span style="font-size:13px;color:#475569;line-height:1.5;">{item}</span></div>'
            for item in filter_items
        )
        filter_html = (
            f'<div style="padding:12px 16px;background:#fef2f2;border-radius:8px;'
            f'border:1px solid #fecaca;margin-top:10px;">'
            f'<div style="font-size:11px;font-weight:700;color:#dc2626;text-transform:uppercase;'
            f'letter-spacing:0.5px;margin-bottom:6px;">🚫 {escape_html(filtered_label)}</div>'
            f"{items}</div>"
        )

    include_html = ""
    if include_items:
        items = "".join(
            f'<div style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;">'
            f'<span style="color:#059669;font-size:13px;flex-shrink:0;">✓</span>'
            f'<span style="font-size:13px;color:#475569;line-height:1.5;">{item}</span></div>'
            for item in include_items
        )
        include_html = (
            f'<div style="padding:12px 16px;background:#f0fdf4;border-radius:8px;'
            f'border:1px solid #bbf7d0;margin-top:10px;">'
            f'<div style="font-size:11px;font-weight:700;color:#059669;text-transform:uppercase;'
            f'letter-spacing:0.5px;margin-bottom:6px;">✅ {escape_html(included_label)}</div>'
            f"{items}</div>"
        )

    result_html = ""
    if result_sentence:
        result_html = (
            f'<div style="margin-top:14px;padding:14px 18px;background:linear-gradient(135deg,#e0f2fe,#f0f9ff);'
            f'border-radius:10px;border:1px solid #7dd3fc;border-left:4px solid #0891b2;">'
            f'<div style="font-size:13px;font-weight:600;color:#0c4a6e;line-height:1.5;">'
            f"<span style=\"font-size:11px;font-weight:700;color:#0891b2;text-transform:uppercase;"
            f'letter-spacing:0.5px;margin-right:6px;">{escape_html(result_prefix)}:</span>'
            f"{escape_html(result_sentence)}</div></div>"
        )

    if not table_html and not filter_html and not include_html and not result_html:
        text_lines = [
            l.strip()
            for l in content.split("\n")
            if l.strip()
            and not re.match(r"^##\s*(DATA_TRUST|DATAGRUNDLAG)", l.strip(), re.IGNORECASE)
            and not re.match(r"^📊", l.strip())
        ]
        if not text_lines:
            return ""
        body = "".join(
            f'<p style="margin:6px 0;color:#475569;font-size:13px;line-height:1.6;">'
            f"{_inline_markdown(l)}</p>"
            for l in text_lines
        )
        h2_text = "Analysegrundlag" if language == "da" else "Analysis Basis"
        return (
            f'<div id="section-data-trust" class="data-trust-section" style="margin:0 0 16px 0;padding:20px 24px;'
            f'background:linear-gradient(135deg,#f0f9ff,#ffffff);border-radius:14px;'
            f'border:1px solid #bae6fd;border-left:4px solid #0891b2;'
            f'box-shadow:0 1px 4px rgba(0,0,0,0.03);">'
            f'<h2 style="font-size:18px;font-weight:800;color:#0c4a6e;margin:0 0 14px 0;">'
            f'{escape_html(h2_text)}</h2>'
            f"{body}</div>"
        )

    h2_text = "Analysegrundlag" if language == "da" else "Analysis Basis"
    return (
        f'<div id="section-data-trust" class="data-trust-section" style="margin:0 0 16px 0;padding:20px 24px;'
        f'background:linear-gradient(135deg,#f0f9ff,#ffffff);border-radius:14px;'
        f'border:1px solid #bae6fd;border-left:4px solid #0891b2;'
        f'box-shadow:0 1px 4px rgba(0,0,0,0.03);">'
        f'<h2 style="font-size:18px;font-weight:800;color:#0c4a6e;margin:0 0 14px 0;">'
        f'{escape_html(h2_text)}</h2>'
        f"{table_html}{filter_html}{include_html}{result_html}"
        f"</div>"
    )


def generate_biggest_risk_section_html(content: str, language: str = "en") -> str:
    if not content or not content.strip():
        return ""

    issue_label = "Problemet" if language == "da" else "The Issue"
    blocking_label = "Blokerer" if language == "da" else "What It Is Blocking"
    action_label = "Din næste handling" if language == "da" else "Your Next Action"
    title = "Største Risiko" if language == "da" else "Biggest Risk"

    lines = content.split("\n")
    current_part = None
    parts: dict = {"issue": [], "blocking": [], "action": []}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^##\s*(BIGGEST_RISK|STØRSTE_RISIKO)", stripped, re.IGNORECASE):
            continue
        if re.search(r"⚠️", stripped):
            current_part = "issue"
            tail = re.sub(r"⚠️[^\S\r\n]*(?:THE\s+ISSUE|PROBLEMET)?[:\-]?\s*", "", stripped, flags=re.IGNORECASE).strip()
            if tail:
                parts["issue"].append(tail)
            continue
        if re.search(r"🔗", stripped):
            current_part = "blocking"
            tail = re.sub(r"🔗[^\S\r\n]*(?:WHAT\s+IT\s+IS\s+BLOCKING|BLOKERER)?[:\-]?\s*", "", stripped, flags=re.IGNORECASE).strip()
            if tail:
                parts["blocking"].append(tail)
            continue
        if re.search(r"➡️", stripped):
            current_part = "action"
            tail = re.sub(r"➡️[^\S\r\n]*(?:YOUR\s+NEXT\s+ACTION|DIN\s+NÆSTE\s+HANDLING)?[:\-]?\s*", "", stripped, flags=re.IGNORECASE).strip()
            if tail:
                parts["action"].append(tail)
            continue
        if current_part:
            parts[current_part].append(stripped)

    issue_text = " ".join(parts["issue"]).strip()
    blocking_text = " ".join(parts["blocking"]).strip()
    action_text = " ".join(parts["action"]).strip()

    if not issue_text and not blocking_text and not action_text:
        return ""

    def _part(emoji, label, text, bg, border, label_color, text_color):
        if not text:
            return ""
        return (
            f'<div style="padding:12px 16px;background:{bg};border-radius:10px;border:1px solid {border};margin-top:10px;">'
            f'<div style="font-size:11px;font-weight:700;color:{label_color};text-transform:uppercase;'
            f'letter-spacing:0.5px;margin-bottom:4px;">{emoji} {escape_html(label)}</div>'
            f'<div style="font-size:13px;color:{text_color};line-height:1.6;">{escape_html(text)}</div>'
            f"</div>"
        )

    issue_html = _part("⚠️", issue_label, issue_text, "#fef2f2", "#fecaca", "#dc2626", "#7f1d1d")
    blocking_html = _part("🔗", blocking_label, blocking_text, "#fff7ed", "#fed7aa", "#c2410c", "#7c2d12")
    action_html = _part("➡️", action_label, action_text, "#f0fdf4", "#bbf7d0", "#15803d", "#14532d")

    return (
        f'<div id="section-biggest-risk-detail" style="margin:0 0 16px 0;padding:20px 24px;'
        f'background:linear-gradient(135deg,#fef2f2,#ffffff);border-radius:14px;'
        f'border:1px solid #fecaca;border-left:4px solid #ef4444;'
        f'box-shadow:0 1px 4px rgba(0,0,0,0.03);">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">'
        f'<span style="display:inline-flex;">{_mini_svg("alert-triangle", 18, "#ef4444")}</span>'
        f'<span style="font-size:14px;font-weight:800;color:#dc2626;text-transform:uppercase;'
        f'letter-spacing:0.5px;">{escape_html(title)}</span>'
        f"</div>"
        f"{issue_html}{blocking_html}{action_html}"
        f"</div>"
    )


def _format_response_internal(
    markdown: str, language: str, total_data_rows: int = 0, diff_data: dict = None
) -> str:
    parsed = parse_structured_response(markdown)

    if diff_data:
        actual_counts = {
            "delayed": len(diff_data.get("delayed", [])),
            "accelerated": len(diff_data.get("accelerated", [])),
            "added": len(diff_data.get("added", [])),
            "removed": len(diff_data.get("removed", [])),
            "moved": len(diff_data.get("modified", [])),
        }
    else:
        actual_counts = (
            _count_actual_table_rows(parsed["tables_section"])
            if parsed["tables_section"]
            else {}
        )

    data_trust_html = generate_data_trust_html(
        parsed.get("data_trust_section", ""), language
    )
    decision_engine_html = _render_decision_engine_cards(
        parsed.get("decision_engine_data"), language
    )
    extra_decision_html = _render_extra_content(
        parsed.get("extra_decision_content", "")
    )
    executive_html = generate_executive_html(parsed["executive_section"], language)

    if diff_data:
        table_html = _generate_diff_tables_html(diff_data, language)
    else:
        table_html = generate_table_html(parsed["tables_section"], language)

    root_cause_html = generate_root_cause_html(parsed["root_cause_section"], language)
    impact_html = generate_impact_html(parsed["impact_section"], language)
    summary_html = generate_summary_html(
        parsed["summary_section"], language, actual_counts, total_data_rows
    )
    orphan_html = _render_extra_content(parsed.get("orphan_content", ""))

    if not parsed["health_data"]:
        health_match = re.search(r"<!--HEALTH_DATA:(.*?)-->", markdown, re.DOTALL)
        if health_match:
            try:
                sanitized = _sanitize_health_data_json(health_match.group(1))
                parsed["health_data"] = json.loads(sanitized)
                parsed["health_section"] = re.sub(
                    r"<!--HEALTH_DATA:.*?-->",
                    "",
                    parsed["health_section"],
                    flags=re.DOTALL,
                ).strip()
            except:
                parsed["health_section"] = re.sub(
                    r"<!--HEALTH_DATA:.*?-->",
                    "",
                    parsed["health_section"],
                    flags=re.DOTALL,
                ).strip()

    if diff_data and not parsed["health_data"]:
        parsed["health_data"] = {
            "status": "critical"
            if len(diff_data.get("delayed", [])) > 10
            else "at_risk",
            "risk_level": "HIGH"
            if len(diff_data.get("delayed", [])) > 10
            else "MEDIUM",
            "added_count": len(diff_data.get("added", [])),
            "removed_count": len(diff_data.get("removed", [])),
            "delayed_count": len(diff_data.get("delayed", [])),
            "accelerated_count": len(diff_data.get("accelerated", [])),
            "modified_count": len(diff_data.get("modified", [])),
            "critical_path_affected": len(diff_data.get("delayed", [])) > 0,
        }

    if parsed["health_data"]:
        health_data = dict(parsed["health_data"])
        for hd_key, cat_key in [
            ("added_count", "added"),
            ("removed_count", "removed"),
            ("delayed_count", "delayed"),
            ("accelerated_count", "accelerated"),
            ("modified_count", "moved"),
        ]:
            if cat_key in actual_counts:
                health_data[hd_key] = actual_counts[cat_key]
        # Inject confidence from DECISION_ENGINE into health_data for the badge
        if not health_data.get("confidence") and parsed.get("decision_engine_data"):
            de_conf = parsed["decision_engine_data"].get("confidence", "")
            if de_conf:
                health_data["confidence"] = de_conf
        parsed["health_data"] = health_data

    health_html = generate_health_html(
        parsed["health_section"],
        parsed["health_data"],
        language,
        actual_counts,
        total_data_rows,
    )

    styles = """
<style>
.comparison-results .category-section table tr:hover { background: rgba(0,214,214,0.04) !important; }
.comparison-results button:hover { transform: translateY(-1px); box-shadow: 0 8px 24px rgba(0,214,214,0.4) !important; }
.comparison-results table::-webkit-scrollbar { height: 8px; }
.comparison-results table::-webkit-scrollbar-track { background: rgba(0,0,0,0.03); border-radius: 8px; }
.comparison-results table::-webkit-scrollbar-thumb { background: linear-gradient(135deg,#00D6D6,#00B8B8); border-radius: 8px; }
</style>"""

    return f"""
{styles}
<div class="agent-response" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  {orphan_html}
  {data_trust_html}
  {decision_engine_html}
  {extra_decision_html}
  {executive_html}
  {root_cause_html}
  {table_html}
  {impact_html}
  {summary_html}
  {health_html}
</div>"""
