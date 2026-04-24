import json
import html
from typing import Dict, List, Optional


def _e(text) -> str:
    if text is None:
        return ""
    return html.escape(str(text))


def _safe_int(val) -> int:
    try:
        return int(round(float(val)))
    except (ValueError, TypeError):
        return 0


def _svg(name: str, size: int = 16, color: str = "currentColor") -> str:
    sw = "1.75"
    base = f'width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"'
    icons = {
        "clock": f'<svg {base}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        "alert-circle": f'<svg {base}><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>',
        "alert-triangle": f'<svg {base}><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
        "activity": f'<svg {base}><path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/></svg>',
        "search": f'<svg {base}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
        "check-square": f'<svg {base}><path d="M21 10.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12.5"/><path d="m9 11 3 3L22 4"/></svg>',
        "users": f'<svg {base}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
        "grid": f'<svg {base}><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>',
        "link": f'<svg {base}><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
        "compass": f'<svg {base}><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/><circle cx="12" cy="12" r="2"/></svg>',
        "pen-tool": f'<svg {base}><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/></svg>',
        "user": f'<svg {base}><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
        "tool": f'<svg {base}><path d="M15.707 21.293a1 1 0 0 1-1.414 0l-1.586-1.586a1 1 0 0 1 0-1.414l5.586-5.586a1 1 0 0 1 1.414 0l1.586 1.586a1 1 0 0 1 0 1.414z"/><path d="m18 13-1.375-6.874a1 1 0 0 0-.746-.776L3.235 2.028a1 1 0 0 0-1.207 1.207L5.35 15.879a1 1 0 0 0 .776.746L13 18"/><path d="m2.3 2.3 7.286 7.286"/><circle cx="11" cy="11" r="2"/></svg>',
        "package": f'<svg {base}><path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>',
        "flag": f'<svg {base}><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" x2="4" y1="22" y2="15"/></svg>',
        "zap": f'<svg {base}><path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/></svg>',
        "target": f'<svg {base}><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
        "arrow-right": f'<svg {base}><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>',
        "pause": f'<svg {base}><rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/></svg>',
        "refresh": f'<svg {base}><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>',
        "play": f'<svg {base}><polygon points="6 3 20 12 6 21 6 3"/></svg>',
        "clipboard": f'<svg {base}><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>',
        "calendar": f'<svg {base}><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/></svg>',
        "bar-chart": f'<svg {base}><path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 16h8"/><path d="M7 11h12"/><path d="M7 6h3"/></svg>',
        "file-text": f'<svg {base}><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>',
        "shield": f'<svg {base}><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/></svg>',
        "trending-up": f'<svg {base}><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>',
        "circle-dot": f'<svg {base}><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/></svg>',
        "gauge": f'<svg {base}><path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/></svg>',
        "hard-hat": f'<svg {base}><path d="M2 18a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v2z"/><path d="M10 15V6.5a1.5 1.5 0 0 1 3 0V15"/><path d="M4 15v-3a8 8 0 0 1 16 0v3"/></svg>',
        "scan-search": f'<svg {base}><path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3"/><path d="m16 16-1.9-1.9"/></svg>',
        "workflow": f'<svg {base}><rect width="8" height="8" x="3" y="3" rx="2"/><path d="M7 11v4a2 2 0 0 0 2 2h4"/><rect width="8" height="8" x="13" y="13" rx="2"/></svg>',
        "list-checks": f'<svg {base}><path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/></svg>',
        "megaphone": f'<svg {base}><path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/></svg>',
        "truck": f'<svg {base}><path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/></svg>',
        "circle-check": f'<svg {base}><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>',
        "chevron-right": f'<svg {base}><path d="m9 18 6-6-6-6"/></svg>',
        "shield-check": f'<svg {base}><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>',
        "shield-alert": f'<svg {base}><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>',
        "octagon-alert": f'<svg {base}><path d="M12 16h.01"/><path d="M12 8v4"/><path d="M15.312 2H8.688a2 2 0 0 0-1.414.586l-4.688 4.688A2 2 0 0 0 2 8.688v6.624a2 2 0 0 0 .586 1.414l4.688 4.688A2 2 0 0 0 8.688 22h6.624a2 2 0 0 0 1.414-.586l4.688-4.688A2 2 0 0 0 22 15.312V8.688a2 2 0 0 0-.586-1.414l-4.688-4.688A2 2 0 0 0 15.312 2z"/></svg>',
        "layers": f'<svg {base}><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/></svg>',
        "split": f'<svg {base}><path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/></svg>',
    }
    return icons.get(name, "")


def _icon_box(icon_name: str, color: str, size: int = 16) -> str:
    return f'<span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;flex-shrink:0;">{_svg(icon_name, size, color)}</span>'


PRIORITY_STYLES = {
    "CRITICAL_NOW": {"color": "#dc2626", "bg": "#fef2f2", "border": "#fecaca", "label_en": "CRITICAL NOW", "label_da": "KRITISK NU"},
    "IMPORTANT_NEXT": {"color": "#d97706", "bg": "#fffbeb", "border": "#fde68a", "label_en": "IMPORTANT NEXT", "label_da": "VIGTIG NÆSTE"},
    "MONITOR": {"color": "#0891b2", "bg": "#ecfeff", "border": "#a5f3fc", "label_en": "MONITOR", "label_da": "OVERVÅG"},
}

TASK_TYPE_STYLES = {
    "Coordination": {"color": "#7c3aed", "bg": "#f5f3ff", "label_da": "Koordinering"},
    "Design": {"color": "#2563eb", "bg": "#eff6ff", "label_da": "Design"},
    "Bygherre": {"color": "#c026d3", "bg": "#fdf4ff", "label_da": "Bygherre"},
    "Production": {"color": "#059669", "bg": "#ecfdf5", "label_da": "Produktion"},
    "Procurement": {"color": "#d97706", "bg": "#fffbeb", "label_da": "Indkøb"},
    "Milestone": {"color": "#64748b", "bg": "#f8fafc", "label_da": "Milepæl"},
}

PROBLEM_TYPE_ICON_MAP = {
    "Coordination blockage": "link",
    "Design input missing": "pen-tool",
    "Bygherre decision pending": "user",
    "Production delay": "tool",
    "Procurement delay": "package",
}

RESOURCE_TYPE_CONFIG = {
    "coordination_bottleneck": {"icon": "link", "color": "#7c3aed", "bg": "#f5f3ff", "label_en": "Coordination", "label_da": "Koordinering"},
    "design_dependency": {"icon": "pen-tool", "color": "#2563eb", "bg": "#eff6ff", "label_en": "Design", "label_da": "Design"},
    "bygherre_escalation": {"icon": "user", "color": "#c026d3", "bg": "#fdf4ff", "label_en": "Bygherre", "label_da": "Bygherre"},
    "production_manpower": {"icon": "tool", "color": "#059669", "bg": "#ecfdf5", "label_en": "Production", "label_da": "Produktion"},
    "management_attention": {"icon": "clipboard", "color": "#ea580c", "bg": "#fff7ed", "label_en": "Management", "label_da": "Ledelse"},
    "procurement_dependency": {"icon": "package", "color": "#d97706", "bg": "#fffbeb", "label_en": "Procurement", "label_da": "Indkøb"},
}

ACTION_TYPE_ICON_MAP = {
    "coordination": "link",
    "bygherre_decision": "user",
    "design_input": "pen-tool",
    "freeze_downstream": "pause",
    "reassess": "refresh",
    "release_work": "play",
    "escalation": "zap",
    "procurement": "package",
}

FORCEABLE_STYLES = {
    "possible": {"color": "#059669", "bg": "#ecfdf5", "border": "#6ee7b7", "icon": "check-square", "label_en": "POSSIBLE", "label_da": "MULIG"},
    "limited": {"color": "#d97706", "bg": "#fffbeb", "border": "#fde68a", "icon": "alert-triangle", "label_en": "LIMITED", "label_da": "BEGRÆNSET"},
    "not_recommended": {"color": "#dc2626", "bg": "#fef2f2", "border": "#fecaca", "icon": "alert-circle", "label_en": "NOT RECOMMENDED", "label_da": "FRARÅDES"},
}

CONSTRAINT_TYPE_CONFIG = {
    "coordination_dependency": {"icon": "workflow", "color": "#7c3aed", "label_en": "Coordination", "label_da": "Koordinering"},
    "design_input_required": {"icon": "pen-tool", "color": "#2563eb", "label_en": "Design Input", "label_da": "Designinput"},
    "bygherre_decision_required": {"icon": "megaphone", "color": "#c026d3", "label_en": "Client Decision", "label_da": "Bygherrebeslutning"},
    "procurement_waiting": {"icon": "truck", "color": "#d97706", "label_en": "Procurement", "label_da": "Indkøb"},
    "execution_capacity": {"icon": "hard-hat", "color": "#059669", "label_en": "Execution", "label_da": "Udførelse"},
    "milestone_gate": {"icon": "flag", "color": "#64748b", "label_en": "Milestone", "label_da": "Milepæl"},
    "cascading_dependencies": {"icon": "split", "color": "#ea580c", "label_en": "Cascading", "label_da": "Kaskade"},
}


def _severity_color(days: int) -> dict:
    if days >= 120:
        return {"color": "#dc2626", "bg": "#fef2f2", "border": "#fecaca"}
    if days >= 60:
        return {"color": "#ea580c", "bg": "#fff7ed", "border": "#fed7aa"}
    if days >= 30:
        return {"color": "#d97706", "bg": "#fffbeb", "border": "#fde68a"}
    return {"color": "#0891b2", "bg": "#ecfeff", "border": "#a5f3fc"}


def _render_project_status_card(data: Dict, lang: str) -> str:
    ins = data.get("insight_data", {})
    status = ins.get("project_status", "")
    risk = ins.get("risk_level", "")
    findings = ins.get("critical_findings", [])
    consequences = ins.get("consequences_if_no_action", [])

    if not status and not findings:
        return ""

    status_config = {
        "STABLE": {"color": "#10b981", "bg": "#ecfdf5", "border": "#a7f3d0", "svg": "shield-check", "label_en": "STABLE", "label_da": "STABIL"},
        "AT_RISK": {"color": "#d97706", "bg": "#fffbeb", "border": "#fde68a", "svg": "alert-triangle", "label_en": "AT RISK", "label_da": "I RISIKO"},
        "CRITICAL": {"color": "#dc2626", "bg": "#fef2f2", "border": "#fecaca", "svg": "octagon-alert", "label_en": "CRITICAL", "label_da": "KRITISK"},
    }
    risk_config = {
        "LOW": {"color": "#10b981", "svg": "shield-check", "label_en": "Low", "label_da": "Lav"},
        "MEDIUM": {"color": "#d97706", "svg": "alert-circle", "label_en": "Medium", "label_da": "Moderat"},
        "HIGH": {"color": "#dc2626", "svg": "alert-triangle", "label_en": "High", "label_da": "Høj"},
    }

    sc = status_config.get(status, status_config["AT_RISK"])
    rc = risk_config.get(risk, risk_config["MEDIUM"])

    status_label = sc["label_da"] if lang == "da" else sc["label_en"]
    risk_label = rc["label_da"] if lang == "da" else rc["label_en"]
    proj_title = "PROJEKTSTATUS" if lang == "da" else "PROJECT STATUS"
    risk_title = "Risikoniveau" if lang == "da" else "Risk Level"
    findings_title = "Kritiske Fund" if lang == "da" else "Critical Findings"
    cons_title = "Hvis ingen handling tages" if lang == "da" else "If No Action Is Taken"

    findings_html = ""
    for f in findings[:3]:
        findings_html += f'<div style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;"><span style="display:inline-flex;margin-top:4px;flex-shrink:0;">{_svg("chevron-right", 12, sc["color"])}</span><span style="font-size:13px;color:#334155;line-height:1.55;font-weight:500;">{_e(f)}</span></div>'

    cons_html = ""
    if consequences:
        cons_items = ""
        for c in consequences[:3]:
            cons_items += f'<div style="display:flex;align-items:flex-start;gap:8px;padding:3px 0;"><span style="display:inline-flex;margin-top:2px;flex-shrink:0;">{_svg("arrow-right", 13, "#dc2626")}</span><span style="font-size:12px;color:#991b1b;line-height:1.5;">{_e(c)}</span></div>'
        cons_html = f'''
    <div style="margin-top:14px;padding:12px 16px;background:#fef2f2;border-radius:10px;border:1px solid #fecaca;">
      <div style="font-size:10px;font-weight:700;color:#991b1b;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px;">{cons_title}</div>
      {cons_items}
    </div>'''

    return f'''
<div id="predictive-project-status" style="margin:0 0 18px;padding:22px 24px;background:linear-gradient(135deg,{sc["bg"]},#ffffff);border-radius:14px;border:1px solid {sc["border"]};border-left:5px solid {sc["color"]};box-shadow:0 2px 8px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:16px;">
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="display:inline-flex;">{_svg(sc["svg"], 22, sc["color"])}</span>
      <span style="font-size:11px;font-weight:800;color:{sc["color"]};text-transform:uppercase;letter-spacing:1.2px;">{proj_title}</span>
      <span style="padding:4px 14px;border-radius:20px;font-size:13px;font-weight:800;color:{sc["color"]};background:white;border:2px solid {sc["color"]};">{status_label}</span>
    </div>
    <div style="display:flex;align-items:center;gap:6px;padding:4px 12px;border-radius:8px;background:white;border:1px solid {rc["color"]}30;">
      <span style="display:inline-flex;">{_svg(rc["svg"], 14, rc["color"])}</span>
      <span style="font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;">{risk_title}:</span>
      <span style="font-size:12px;font-weight:800;color:{rc["color"]};">{risk_label}</span>
    </div>
  </div>
  <div style="margin-bottom:4px;">
    <div style="font-size:10px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px;">{findings_title}</div>
    {findings_html}
  </div>
  {cons_html}
</div>'''


def _render_hero(data: Dict, lang: str) -> str:
    ins = data.get("insight_data", {})
    total = _safe_int(ins.get("total_activities", 0))
    delayed = _safe_int(ins.get("delayed_count", 0))
    critical = _safe_int(ins.get("critical_count", 0))
    important = _safe_int(ins.get("important_count", 0))
    monitor = _safe_int(ins.get("monitor_count", 0))
    root_causes = _safe_int(ins.get("root_cause_count", 0))
    most_overdue = _safe_int(ins.get("most_overdue_days", 0))
    areas = _safe_int(ins.get("areas_affected", 0))
    primary_risk = _e(ins.get("primary_risk", ""))

    if critical == 0 and delayed == 0:
        sc, sbg, sb = "#0d9488", "#f0fdfa", "#99f6e4"
        sl = "Ingen forsinkelser" if lang == "da" else "No Delays"
    elif critical <= 3:
        sc, sbg, sb = "#d97706", "#fffbeb", "#fde68a"
        sl = "Moderat risiko" if lang == "da" else "Moderate Risk"
    elif critical <= 8:
        sc, sbg, sb = "#ea580c", "#fff7ed", "#fed7aa"
        sl = "Alvorlig risiko" if lang == "da" else "Serious Risk"
    else:
        sc, sbg, sb = "#dc2626", "#fef2f2", "#fecaca"
        sl = "Kritisk risiko" if lang == "da" else "Critical Risk"

    pct = min(round((delayed / max(total, 1)) * 100), 100) if total > 0 else 0
    bc = "#0d9488" if pct < 15 else ("#d97706" if pct < 30 else ("#ea580c" if pct < 50 else "#dc2626"))

    cl = "Kritisk" if lang == "da" else "Critical"
    il = "Vigtig" if lang == "da" else "Important"
    ml = "Overvåg" if lang == "da" else "Monitor"

    risk_html = ""
    if primary_risk and primary_risk.lower() not in ("", "none", "n/a"):
        rl = "Primær risiko" if lang == "da" else "Primary Risk"
        risk_html = f'<div style="margin-top:14px;padding:10px 14px;background:#fef2f2;border-radius:8px;border:1px solid #fecaca;"><div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">{_svg("alert-triangle", 12, "#991b1b")}<span style="font-size:10px;color:#991b1b;text-transform:uppercase;font-weight:700;letter-spacing:0.8px;">{rl}</span></div><div style="font-size:13px;color:#991b1b;font-weight:600;line-height:1.5;">{primary_risk}</div></div>'

    return f'''
<div id="predictive-overview" style="margin:0 0 22px;background:#fff;border-radius:16px;border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.06);">
  <div style="background:linear-gradient(135deg,#f0fdfa,#ecfeff);padding:28px 28px 22px;border-bottom:1px solid #e2e8f0;">
    <div style="display:flex;align-items:center;gap:28px;flex-wrap:wrap;">
      <div style="text-align:center;flex-shrink:0;min-width:110px;">
        <div style="font-size:56px;font-weight:900;color:{sc};line-height:1;">{delayed}</div>
        <div style="font-size:10px;color:#64748b;text-transform:uppercase;font-weight:700;letter-spacing:1.5px;margin-top:4px;">{"FORSINKEDE" if lang == "da" else "DELAYED"}</div>
      </div>
      <div style="flex:1;min-width:220px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
          <span style="display:inline-block;padding:5px 16px;border-radius:20px;font-size:12px;font-weight:700;color:{sc};background:{sbg};border:1px solid {sb};">{sl}</span>
        </div>
        <div style="margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
            <span style="font-size:11px;color:#64748b;font-weight:600;">{"Forsinkede af total" if lang == "da" else "Delayed of total"}</span>
            <span style="font-size:12px;color:#1a202c;font-weight:700;">{delayed}/{total} ({pct}%)</span>
          </div>
          <div style="height:10px;background:#e2e8f0;border-radius:5px;overflow:hidden;"><div style="height:100%;width:{min(pct,100)}%;background:linear-gradient(90deg,{bc},{bc}cc);border-radius:5px;"></div></div>
        </div>
        <div style="display:flex;gap:16px;margin-top:14px;flex-wrap:wrap;">
          <div style="display:flex;align-items:center;gap:6px;padding:4px 12px;background:#fef2f2;border-radius:8px;border:1px solid #fecaca;"><span style="width:8px;height:8px;border-radius:50%;background:#dc2626;display:inline-block;"></span><span style="font-size:12px;color:#991b1b;font-weight:700;">{critical}</span><span style="font-size:11px;color:#991b1b;font-weight:600;">{cl}</span></div>
          <div style="display:flex;align-items:center;gap:6px;padding:4px 12px;background:#fffbeb;border-radius:8px;border:1px solid #fde68a;"><span style="width:8px;height:8px;border-radius:50%;background:#d97706;display:inline-block;"></span><span style="font-size:12px;color:#92400e;font-weight:700;">{important}</span><span style="font-size:11px;color:#92400e;font-weight:600;">{il}</span></div>
          <div style="display:flex;align-items:center;gap:6px;padding:4px 12px;background:#ecfeff;border-radius:8px;border:1px solid #a5f3fc;"><span style="width:8px;height:8px;border-radius:50%;background:#0891b2;display:inline-block;"></span><span style="font-size:12px;color:#155e75;font-weight:700;">{monitor}</span><span style="font-size:11px;color:#155e75;font-weight:600;">{ml}</span></div>
        </div>
        {risk_html}
      </div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(5,1fr);border-top:1px solid #edf2f7;">
    <div style="padding:16px;text-align:center;border-right:1px solid #edf2f7;"><div style="font-size:22px;font-weight:800;color:#1a202c;">{total}</div><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;letter-spacing:.8px;margin-top:3px;">{"Aktiviteter" if lang == "da" else "Activities"}</div></div>
    <div style="padding:16px;text-align:center;border-right:1px solid #edf2f7;"><div style="font-size:22px;font-weight:800;color:{sc};">{delayed}</div><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;letter-spacing:.8px;margin-top:3px;">{"Forsinkede" if lang == "da" else "Delayed"}</div></div>
    <div style="padding:16px;text-align:center;border-right:1px solid #edf2f7;"><div style="font-size:22px;font-weight:800;color:#dc2626;">{critical}</div><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;letter-spacing:.8px;margin-top:3px;">{"Kritiske" if lang == "da" else "Critical"}</div></div>
    <div style="padding:16px;text-align:center;border-right:1px solid #edf2f7;"><div style="font-size:22px;font-weight:800;color:#7c3aed;">{root_causes}</div><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;letter-spacing:.8px;margin-top:3px;">{"Grundårsager" if lang == "da" else "Root Causes"}</div></div>
    <div style="padding:16px;text-align:center;"><div style="font-size:22px;font-weight:800;color:#1a202c;">{areas}</div><div style="font-size:9px;color:#64748b;text-transform:uppercase;font-weight:700;letter-spacing:.8px;margin-top:3px;">{"Områder" if lang == "da" else "Areas"}</div></div>
  </div>
</div>'''


def _render_management_conclusion(data: Dict, lang: str) -> str:
    text = _e(data.get("management_conclusion", ""))
    if not text:
        return ""
    label = "Ledelseskonklusion" if lang == "da" else "Management Conclusion"
    sub = "Overordnet vurdering og anbefaling" if lang == "da" else "Executive assessment and recommendation"
    return f'''
<div id="predictive-management-conclusion" class="module-card" style="margin:0 0 16px;padding:22px 24px;background:linear-gradient(135deg,#f0fdfa,#ecfeff);border-radius:14px;border:1px solid #99f6e4;border-left:5px solid #0d9488;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #99f6e4;">
    <div style="width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:#0d948812;border:1px solid #0d948822;">{_svg("activity", 18, "#0d9488")}</div>
    <div><h3 style="font-size:16px;font-weight:700;color:#1a202c;margin:0;">{label}</h3><p style="margin:0;font-size:11px;color:#94a3b8;font-weight:500;">{sub}</p></div>
  </div>
  <p style="margin:0;color:#374151;line-height:1.9;font-size:14.5px;font-weight:500;">{text}</p>
</div>'''


def _render_schedule_overview(data: Dict, lang: str) -> str:
    ov = data.get("schedule_overview", {})
    if not ov:
        return ""
    label = "Tidsplanoversigt" if lang == "da" else "Schedule Overview"

    fields = [
        ("clipboard", "Tidsplan" if lang == "da" else "Schedule", _e(ov.get("schedule_name", ""))),
        ("calendar", "Referencedato" if lang == "da" else "Reference Date", _e(ov.get("reference_date", ""))),
        ("bar-chart", "Total aktiviteter" if lang == "da" else "Total Activities", str(ov.get("total_activities", 0))),
        ("alert-circle", "Forsinkede" if lang == "da" else "Delayed", str(ov.get("delayed_count", 0))),
        ("tool", "Områder" if lang == "da" else "Areas", ", ".join(ov.get("areas_covered", []))),
    ]

    fields_html = ""
    for icon_name, name, val in fields:
        fields_html += f'<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #f1f5f9;align-items:center;">{_icon_box(icon_name, "#64748b", 14)}<span style="font-size:12px;color:#64748b;font-weight:600;min-width:120px;">{name}</span><span style="font-size:13px;color:#1a202c;font-weight:600;">{val}</span></div>'

    return f'''
<div id="predictive-schedule-overview" class="module-card" style="margin:0 0 16px;padding:22px 24px;background:#fff;border-radius:14px;border:1px solid #e2e8f0;border-left:5px solid #0d9488;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f1f5f9;">
    <div style="width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:#0d948812;border:1px solid #0d948822;">{_svg("clock", 18, "#0d9488")}</div>
    <h3 style="font-size:16px;font-weight:700;color:#1a202c;margin:0;">{label}</h3>
  </div>
  {fields_html}
</div>'''


def _render_delayed_table(data: Dict, lang: str) -> str:
    activities = data.get("delayed_activities", [])
    if not activities:
        return ""

    label = "Forsinkede Aktiviteter" if lang == "da" else "Delayed Activities"
    sub = f"{len(activities)} {'aktiviteter fundet' if lang == 'da' else 'activities found'}"

    headers = ["Id", "Opgavenavn", "Startdato", "Slutdato", "Varighed", "% færdigt",
               "Dage Forsinket" if lang == "da" else "Days Overdue",
               "Opgavetype" if lang == "da" else "Task Type",
               "Prioritet" if lang == "da" else "Priority"]

    header_html = ""
    for i, h in enumerate(headers):
        align = "right" if i == 6 else ("center" if i >= 7 else "left")
        header_html += f'<th style="padding:12px 14px;text-align:{align};font-size:11px;font-weight:700;color:#134e4a;text-transform:uppercase;letter-spacing:.8px;white-space:nowrap;border-bottom:2px solid #99f6e4;background:linear-gradient(135deg,#f0fdfa,#ecfeff);">{h}</th>'

    rows_html = ""
    for idx, act in enumerate(activities):
        bg = "#f7fafc" if idx % 2 == 0 else "#ffffff"
        days = _safe_int(act.get("days_overdue", 0))
        sev = _severity_color(days)
        priority = act.get("priority", "MONITOR")
        p_style = PRIORITY_STYLES.get(priority, PRIORITY_STYLES["MONITOR"])
        p_label = p_style[f"label_{lang}"] if f"label_{lang}" in p_style else p_style.get("label_en", priority)
        task_type = act.get("task_type", "Production")
        t_style = TASK_TYPE_STYLES.get(task_type, TASK_TYPE_STYLES["Production"])
        t_label = t_style.get("label_da", task_type) if lang == "da" else task_type

        days_label = f"{days} {'dage' if lang == 'da' else 'days'}"

        human_label = _e(act.get("human_label", ""))
        task_name_cell = f'<span style="color:#4a5568;font-size:13px;">{_e(act.get("task_name",""))}</span>'
        if human_label:
            task_name_cell = f'<div><span style="color:#4a5568;font-size:13px;">{_e(act.get("task_name",""))}</span><br><span style="color:#7c3aed;font-size:11px;font-weight:600;font-style:italic;">{human_label}</span></div>'

        cells = [
            f'<span style="font-weight:700;color:#1a202c;font-size:13px;font-family:\'SF Mono\',\'Cascadia Code\',monospace;">{_e(act.get("id",""))}</span>',
            task_name_cell,
            f'<span style="color:#4a5568;font-size:13px;">{_e(act.get("start_date",""))}</span>',
            f'<span style="color:#4a5568;font-size:13px;">{_e(act.get("end_date",""))}</span>',
            f'<span style="color:#4a5568;font-size:13px;">{_e(act.get("duration",""))}</span>',
            f'<span style="color:#dc2626;font-weight:600;font-size:13px;">{_e(act.get("progress","0%"))}</span>',
            f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;color:{sev["color"]};background:{sev["bg"]};border:1px solid {sev["border"]};">{days_label}</span>',
            f'<span style="display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;color:{t_style["color"]};background:{t_style["bg"]};white-space:nowrap;">{t_label}</span>',
            f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;color:{p_style["color"]};background:{p_style["bg"]};border:1px solid {p_style["border"]};white-space:nowrap;">{p_label}</span>',
        ]

        aligns = ["left","left","left","left","left","left","right","center","center"]
        tds = ""
        for ci, (cell, align) in enumerate(zip(cells, aligns)):
            tds += f'<td style="padding:11px 14px;border-bottom:1px solid #edf2f7;vertical-align:middle;text-align:{align};">{cell}</td>'

        rows_html += f'<tr style="background:{bg};transition:background .15s;" onmouseover="this.style.background=\'#edf2f7\'" onmouseout="this.style.background=\'{bg}\'">{tds}</tr>'

    return f'''
<div id="predictive-delayed-activities" class="module-card" style="margin:0 0 16px;padding:22px 24px;background:#fff;border-radius:14px;border:1px solid #e2e8f0;border-left:5px solid #0d9488;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f1f5f9;">
    <div style="width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:#dc262612;border:1px solid #dc262622;">{_svg("alert-circle", 18, "#dc2626")}</div>
    <div><h3 style="font-size:16px;font-weight:700;color:#1a202c;margin:0;">{label}</h3><p style="margin:0;font-size:11px;color:#94a3b8;font-weight:500;">{sub}</p></div>
  </div>
  <div style="overflow-x:auto;border-radius:12px;background:#fff;border:1px solid #e2e8f0;box-shadow:0 1px 3px rgba(0,0,0,.06);">
    <table style="width:100%;min-width:950px;border-collapse:collapse;"><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>
  </div>
</div>'''


def _render_root_cause_analysis(data: Dict, lang: str) -> str:
    rcs = data.get("root_cause_analysis", [])
    dcs = data.get("downstream_consequences", [])
    if not rcs and not dcs:
        return ""

    label = "Årsagsanalyse" if lang == "da" else "Root Cause Analysis"
    sub = "Grundårsager vs. afledte konsekvenser" if lang == "da" else "Root causes vs. downstream consequences"

    cards_html = ""
    for rc in rcs:
        problem_type = rc.get("problem_type", "")
        icon_name = PROBLEM_TYPE_ICON_MAP.get(problem_type, "search")
        affected = rc.get("affected_task_ids", [])
        affected_text = ", ".join(affected) if affected else ("Ingen" if lang == "da" else "None")

        fields = [
            ("clock", "#dc2626", "Status", f'{rc.get("days_overdue", 0)} {"dage forsinket" if lang == "da" else "days overdue"}, 0%'),
            ("search", "#7c3aed", "Problemtype" if lang == "da" else "Problem Type", _e(problem_type)),
            ("zap", "#d97706", "Hvorfor det er vigtigt" if lang == "da" else "Why It Matters", _e(rc.get("why_it_matters", ""))),
            ("link", "#2563eb", "Nedstrømseffekt" if lang == "da" else "Downstream Impact", _e(rc.get("downstream_impact", ""))),
            ("alert-triangle", "#ea580c", "Konsekvens hvis uløst" if lang == "da" else "If Unresolved", _e(rc.get("consequence_if_unresolved", ""))),
            ("target", "#64748b", "Berørte opgaver" if lang == "da" else "Affected Tasks", affected_text),
        ]

        fields_html = ""
        for f_icon, f_color, f_name, f_val in fields:
            fields_html += f'''<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #f0fdf4;align-items:flex-start;">
  {_icon_box(f_icon, f_color, 14)}
  <div style="flex:1;min-width:0;"><div style="font-size:11px;font-weight:700;color:{f_color};text-transform:uppercase;letter-spacing:.6px;margin-bottom:3px;">{f_name}</div><div style="font-size:13px;color:#374151;line-height:1.6;">{f_val}</div></div>
</div>'''

        rc_human = _e(rc.get("human_label", ""))
        rc_label_tag = f'<span style="padding:2px 10px;border-radius:12px;font-size:11px;font-weight:700;color:#7c3aed;background:#f5f3ff;border:1px solid #ddd6fe;font-style:italic;">{rc_human}</span>' if rc_human else ""
        cards_html += f'''<div style="margin:14px 0;background:#fff;border-radius:12px;border:1px solid #99f6e4;border-left:4px solid #0d9488;overflow:hidden;box-shadow:0 1px 3px rgba(13,148,136,.08);">
  <div style="padding:14px 18px;background:linear-gradient(135deg,#f0fdfa,#ecfeff);border-bottom:1px solid #99f6e4;">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
      {_svg(icon_name, 14, "#0d9488")}
      <span style="display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;color:#134e4a;background:#f0fdfa;border:1px solid #99f6e4;font-family:'SF Mono','Cascadia Code',monospace;">ID {_e(rc.get("id",""))}</span>
      {rc_label_tag}
      <span style="font-size:13px;font-weight:600;color:#475569;">{_e(rc.get("task_name",""))}</span>
    </div>
  </div>
  <div style="padding:6px 18px 14px;">{fields_html}</div>
</div>'''

    dc_html = ""
    if dcs:
        dc_label = "Afledte konsekvenser" if lang == "da" else "Downstream Consequences"
        dc_sub = "Løses når grundårsagen er adresseret" if lang == "da" else "Will likely resolve when root cause is addressed"
        items = ""
        for dc in dcs:
            dc_hl = _e(dc.get("human_label", ""))
            dc_hl_part = f' <em style="color:#7c3aed;font-size:11px;">· {dc_hl}</em>' if dc_hl else ""
            items += f'<div style="padding:8px 14px;border-bottom:1px solid #f1f5f9;font-size:13px;color:#64748b;line-height:1.6;display:flex;align-items:flex-start;gap:8px;">{_svg("arrow-right", 14, "#94a3b8")}<span>ID <strong style="font-family:\'SF Mono\',\'Cascadia Code\',monospace;color:#475569;">{_e(dc.get("id",""))}</strong>{dc_hl_part} ({_e(dc.get("task_name",""))}) — {"blokeret af" if lang == "da" else "blocked by"} ID {_e(dc.get("blocked_by_id",""))}</span></div>'
        dc_html = f'''<div style="margin:20px 0 8px;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;overflow:hidden;">
  <div style="padding:12px 16px;background:#f1f5f9;border-bottom:1px solid #e2e8f0;"><h4 style="margin:0;color:#475569;font-size:13px;font-weight:700;">{dc_label}</h4><p style="margin:3px 0 0;color:#94a3b8;font-size:11px;">{dc_sub}</p></div>
  {items}
</div>'''

    return f'''
<div id="predictive-root-cause" class="module-card" style="margin:0 0 16px;padding:22px 24px;background:#fff;border-radius:14px;border:1px solid #e2e8f0;border-left:5px solid #0d9488;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f1f5f9;">
    <div style="width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:#7c3aed12;border:1px solid #7c3aed22;">{_svg("scan-search", 18, "#7c3aed")}</div>
    <div><h3 style="font-size:16px;font-weight:700;color:#1a202c;margin:0;">{label}</h3><p style="margin:0;font-size:11px;color:#94a3b8;font-weight:500;">{sub}</p></div>
  </div>
  {cards_html}
  {dc_html}
</div>'''


def _render_priority_actions(data: Dict, lang: str) -> str:
    actions = data.get("priority_actions", [])
    if not actions:
        return ""

    label = "Prioriterede Handlinger" if lang == "da" else "Priority Actions"
    sub = "Prioriteret handlingsrækkefølge" if lang == "da" else "Prioritized action sequence"

    items_html = ""
    for act in actions:
        step = act.get("step", 0)
        action_text = _e(act.get("action", ""))
        a_type = act.get("action_type", "coordination")
        icon_name = ACTION_TYPE_ICON_MAP.get(a_type, "clipboard")

        items_html += f'''<div style="display:flex;gap:14px;padding:14px 0;border-bottom:1px solid #f1f5f9;align-items:flex-start;">
  <div style="display:flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#0d9488,#0891b2);color:white;font-size:14px;font-weight:800;flex-shrink:0;box-shadow:0 2px 4px rgba(13,148,136,.2);">{step}</div>
  <div style="flex:1;padding-top:5px;">
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">{_icon_box(icon_name, "#64748b", 13)}<span style="font-size:10px;color:#64748b;text-transform:uppercase;font-weight:600;letter-spacing:.5px;">{a_type.replace("_"," ")}</span></div>
    <p style="margin:0;font-size:14px;color:#374151;line-height:1.7;font-weight:500;">{action_text}</p>
  </div>
</div>'''

    return f'''
<div id="predictive-priority-actions" class="module-card" style="margin:0 0 16px;padding:22px 24px;background:#fff;border-radius:14px;border:1px solid #e2e8f0;border-left:5px solid #059669;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f1f5f9;">
    <div style="width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:#05966912;border:1px solid #05966922;">{_svg("list-checks", 18, "#059669")}</div>
    <div><h3 style="font-size:16px;font-weight:700;color:#1a202c;margin:0;">{label}</h3><p style="margin:0;font-size:11px;color:#94a3b8;font-weight:500;">{sub}</p></div>
  </div>
  {items_html}
</div>'''


def _render_resource_assessment(data: Dict, lang: str) -> str:
    items = data.get("resource_assessment", [])
    if not items:
        return ""

    label = "Ressourcevurdering" if lang == "da" else "Resource Assessment"
    sub = "Mandskab vs. koordinering vs. beslutning" if lang == "da" else "Manpower vs. coordination vs. decision"

    cards_html = ""
    for item in items:
        r_type = item.get("resource_type", "management_attention")
        r_config = RESOURCE_TYPE_CONFIG.get(r_type, RESOURCE_TYPE_CONFIG["management_attention"])
        r_label = r_config[f"label_{lang}"] if f"label_{lang}" in r_config else r_config.get("label_en", r_type)
        ra_human = _e(item.get("human_label", ""))
        ra_human_tag = f'<span style="padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;color:#7c3aed;background:#f5f3ff;border:1px solid #ddd6fe;font-style:italic;">{ra_human}</span>' if ra_human else ""

        cards_html += f'''<div style="display:flex;gap:12px;padding:14px 16px;margin:8px 0;background:#fff;border-radius:10px;border:1px solid #e2e8f0;align-items:flex-start;transition:all .15s;" onmouseover="this.style.borderColor='#cbd5e1';this.style.boxShadow='0 2px 6px rgba(0,0,0,.04)'" onmouseout="this.style.borderColor='#e2e8f0';this.style.boxShadow='none'">
  <div style="width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;background:{r_config["bg"]};border:1px solid {r_config["color"]}22;flex-shrink:0;">{_svg(r_config["icon"], 16, r_config["color"])}</div>
  <div style="flex:1;min-width:0;">
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;flex-wrap:wrap;">
      <span style="font-weight:700;color:#1a202c;font-size:13px;font-family:'SF Mono','Cascadia Code',monospace;">ID {_e(item.get("id",""))}</span>
      {ra_human_tag}
      <span style="display:inline-block;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:700;color:{r_config["color"]};background:{r_config["bg"]};">{r_label}</span>
    </div>
    <p style="margin:0 0 4px;color:#475569;font-size:12px;font-weight:600;">{_e(item.get("task_name",""))}</p>
    <p style="margin:0;color:#4a5568;font-size:13px;line-height:1.7;">{_e(item.get("assessment",""))}</p>
  </div>
</div>'''

    return f'''
<div id="predictive-resource-assessment" class="module-card" style="margin:0 0 16px;padding:22px 24px;background:#fff;border-radius:14px;border:1px solid #e2e8f0;border-left:5px solid #0d9488;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f1f5f9;">
    <div style="width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:#d9770612;border:1px solid #d9770622;">{_svg("users", 18, "#d97706")}</div>
    <div><h3 style="font-size:16px;font-weight:700;color:#1a202c;margin:0;">{label}</h3><p style="margin:0;font-size:11px;color:#94a3b8;font-weight:500;">{sub}</p></div>
  </div>
  {cards_html}
</div>'''


def _render_forcing_assessment(data: Dict, lang: str) -> str:
    items = data.get("forcing_assessment", [])
    if not items:
        return ""

    ins = data.get("insight_data", {})
    forceable_count = _safe_int(ins.get("forceable_count", 0))
    not_forceable_count = _safe_int(ins.get("not_forceable_count", 0))

    label = "Forceringsvurdering" if lang == "da" else "Forcing Assessment"
    sub_text = "Kan forsinkelsen accelereres?" if lang == "da" else "Can the delay be accelerated?"
    summary_label = f'{forceable_count} {"kan forceres" if lang == "da" else "forceable"} · {not_forceable_count} {"frarådes" if lang == "da" else "not recommended"}'

    cards_html = ""
    for item in items:
        is_forceable = item.get("is_forceable", "not_recommended")
        f_style = FORCEABLE_STYLES.get(is_forceable, FORCEABLE_STYLES["not_recommended"])
        f_label = f_style[f"label_{lang}"] if f"label_{lang}" in f_style else f_style.get("label_en", is_forceable)

        constraint = item.get("constraint_type", "execution_capacity")
        c_config = CONSTRAINT_TYPE_CONFIG.get(constraint, CONSTRAINT_TYPE_CONFIG["execution_capacity"])
        c_label = c_config[f"label_{lang}"] if f"label_{lang}" in c_config else c_config.get("label_en", constraint)

        coord_cost = item.get("coordination_cost", "medium")
        parallel = item.get("parallelizability", "low")
        speedup = _e(item.get("max_speedup_factor", "1.0x"))
        raw_team = item.get("optimal_team_size", "N/A")
        is_na = not raw_team or raw_team.strip().upper() in ("N/A", "NA", "N/A.", "NOT APPLICABLE")
        if is_na:
            na_msg = "Ikke relevant" if lang == "da" else "Not applicable"
            team_size = f'<span style="color:#94a3b8;font-weight:600;font-size:11px;">{na_msg}</span>'
        else:
            team_size = f'<span style="color:#1a202c;">{_e(raw_team)}</span>'
        ponr = _e(item.get("point_of_no_return", ""))

        coord_label = {"low": ("Lav" if lang == "da" else "Low"), "medium": ("Middel" if lang == "da" else "Medium"), "high": ("Høj" if lang == "da" else "High")}.get(coord_cost, coord_cost)
        parallel_label = {"low": ("Lav" if lang == "da" else "Low"), "medium": ("Middel" if lang == "da" else "Medium"), "high": ("Høj" if lang == "da" else "High")}.get(parallel, parallel)

        coord_color = {"low": "#059669", "medium": "#d97706", "high": "#dc2626"}.get(coord_cost, "#64748b")
        parallel_color = {"low": "#dc2626", "medium": "#d97706", "high": "#059669"}.get(parallel, "#64748b")

        reason_label = "Begrundelse" if lang == "da" else "Reason"
        risk_label = "Risiko ved forcering" if lang == "da" else "Risk if Forced"
        rec_label = "Anbefaling" if lang == "da" else "Recommendation"
        ponr_label = "Point of No Return"
        coord_title = "Koordineringsomkostning" if lang == "da" else "Coordination Cost"
        parallel_title = "Paralleliserbarhed" if lang == "da" else "Parallelizability"
        speedup_title = "Maks. speedup" if lang == "da" else "Max Speedup"
        team_title = "Optimal holdstørrelse" if lang == "da" else "Optimal Team Size"

        fa_human = _e(item.get("human_label", ""))
        fa_human_tag = f'<span style="padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;color:#7c3aed;background:#f5f3ff;border:1px solid #ddd6fe;font-style:italic;white-space:nowrap;">{fa_human}</span>' if fa_human else ""
        cards_html += f'''<div style="margin:12px 0;background:#fff;border-radius:12px;border:1px solid {f_style["border"]};border-left:4px solid {f_style["color"]};overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="padding:14px 18px;background:{f_style["bg"]};border-bottom:1px solid {f_style["border"]};">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
      {_svg(f_style["icon"], 14, f_style["color"])}
      <span style="display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;color:#134e4a;background:#f0fdfa;border:1px solid #99f6e4;font-family:'SF Mono','Cascadia Code',monospace;">ID {_e(item.get("id",""))}</span>
      {fa_human_tag}
      <span style="font-size:13px;font-weight:600;color:#475569;flex:1;min-width:0;">{_e(item.get("task_name",""))}</span>
      <span style="display:inline-block;padding:3px 12px;border-radius:12px;font-size:11px;font-weight:700;color:{f_style["color"]};background:#fff;border:1px solid {f_style["border"]};white-space:nowrap;">{f_label}</span>
      <span style="display:inline-block;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:600;color:{c_config["color"]};background:#f8fafc;border:1px solid #e2e8f0;white-space:nowrap;">{_svg(c_config["icon"], 10, c_config["color"])} {c_label}</span>
    </div>
  </div>
  <div style="padding:14px 18px;">
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;">
      <div style="padding:8px 10px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;text-align:center;">
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:.5px;margin-bottom:3px;">{coord_title}</div>
        <div style="font-size:13px;font-weight:700;color:{coord_color};">{coord_label}</div>
      </div>
      <div style="padding:8px 10px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;text-align:center;">
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:.5px;margin-bottom:3px;">{parallel_title}</div>
        <div style="font-size:13px;font-weight:700;color:{parallel_color};">{parallel_label}</div>
      </div>
      <div style="padding:8px 10px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;text-align:center;">
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:.5px;margin-bottom:3px;">{speedup_title}</div>
        <div style="font-size:13px;font-weight:700;color:#0d9488;">{speedup}</div>
      </div>
      <div style="padding:8px 10px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;text-align:center;">
        <div style="font-size:9px;color:#94a3b8;text-transform:uppercase;font-weight:700;letter-spacing:.5px;margin-bottom:3px;">{team_title}</div>
        <div style="font-size:13px;font-weight:700;">{team_size}</div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px;">
      <div style="padding:10px 14px;background:#f0fdfa;border-radius:8px;border:1px solid #99f6e4;">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">{_svg("scan-search", 12, "#0d9488")}<span style="font-size:10px;color:#0d9488;text-transform:uppercase;font-weight:700;letter-spacing:.6px;">{reason_label}</span></div>
        <div style="font-size:13px;color:#374151;line-height:1.7;">{_e(item.get("reason",""))}</div>
      </div>
      <div style="padding:10px 14px;background:#fef2f2;border-radius:8px;border:1px solid #fecaca;">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">{_svg("alert-triangle", 12, "#dc2626")}<span style="font-size:10px;color:#dc2626;text-transform:uppercase;font-weight:700;letter-spacing:.6px;">{risk_label}</span></div>
        <div style="font-size:13px;color:#374151;line-height:1.7;">{_e(item.get("risk_if_forced",""))}</div>
      </div>
      <div style="padding:10px 14px;background:#ecfdf5;border-radius:8px;border:1px solid #6ee7b7;">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">{_svg("check-square", 12, "#059669")}<span style="font-size:10px;color:#059669;text-transform:uppercase;font-weight:700;letter-spacing:.6px;">{rec_label}</span></div>
        <div style="font-size:13px;color:#374151;line-height:1.7;font-weight:500;">{_e(item.get("recommendation",""))}</div>
      </div>
      <div style="padding:8px 14px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">
        <div style="display:flex;align-items:center;gap:6px;">{_svg("clock", 12, "#64748b")}<span style="font-size:10px;color:#64748b;text-transform:uppercase;font-weight:700;letter-spacing:.6px;">{ponr_label}</span><span style="font-size:12px;color:#475569;font-weight:600;margin-left:6px;">{ponr}</span></div>
      </div>
    </div>
  </div>
</div>'''

    return f'''
<div id="predictive-forcing-assessment" class="module-card" style="margin:0 0 16px;padding:22px 24px;background:#fff;border-radius:14px;border:1px solid #e2e8f0;border-left:5px solid #0d9488;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;padding-bottom:12px;border-bottom:1px solid #f1f5f9;">
    <div style="width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:#ea580c12;border:1px solid #ea580c22;">{_svg("zap", 18, "#ea580c")}</div>
    <div style="flex:1;"><h3 style="font-size:16px;font-weight:700;color:#1a202c;margin:0;">{label}</h3><p style="margin:0;font-size:11px;color:#94a3b8;font-weight:500;">{sub_text}</p></div>
    <span style="font-size:11px;color:#64748b;font-weight:600;background:#f1f5f9;padding:4px 12px;border-radius:8px;">{summary_label}</span>
  </div>
  {cards_html}
</div>'''


def _render_summary_by_area(data: Dict, lang: str) -> str:
    areas = data.get("summary_by_area", [])
    if not areas:
        return ""

    label = "Oversigt efter Område" if lang == "da" else "Summary by Area"

    items_html = ""
    for area in areas:
        d = area.get("delayed_count", 0)
        c = area.get("critical_count", 0)
        i_count = area.get("important_count", 0)
        m = area.get("monitor_count", 0)
        bar_color = "#dc2626" if c > 0 else ("#d97706" if d > 2 else "#0d9488")

        breakdown_parts = []
        if c > 0:
            breakdown_parts.append(f'{c} {"kritisk" if lang == "da" else "critical"}')
        if i_count > 0:
            breakdown_parts.append(f'{i_count} {"vigtig" if lang == "da" else "important"}')
        if m > 0:
            breakdown_parts.append(f'{m} {"overvåg" if lang == "da" else "monitor"}')
        breakdown = ", ".join(breakdown_parts)

        items_html += f'''<div style="display:flex;gap:14px;padding:14px 16px;margin:6px 0;background:#fff;border-radius:10px;border:1px solid #e2e8f0;border-left:4px solid {bar_color};align-items:flex-start;">
  <div style="text-align:center;flex-shrink:0;min-width:40px;"><div style="font-size:22px;font-weight:800;color:{bar_color};line-height:1;">{d}</div><div style="font-size:9px;color:#94a3b8;text-transform:uppercase;font-weight:600;letter-spacing:.5px;margin-top:2px;">{"forsinket" if lang == "da" else "delayed"}</div></div>
  <div style="flex:1;min-width:0;">
    <div style="font-size:14px;font-weight:700;color:#1a202c;margin-bottom:3px;">{_e(area.get("area",""))}</div>
    <div style="font-size:11px;color:#64748b;margin-bottom:4px;">{breakdown}</div>
    <div style="font-size:13px;color:#4a5568;line-height:1.6;">{_e(area.get("summary",""))}</div>
  </div>
</div>'''

    return f'''
<div id="predictive-summary-by-area" class="module-card" style="margin:0 0 16px;padding:22px 24px;background:#fff;border-radius:14px;border:1px solid #e2e8f0;border-left:5px solid #0d9488;transition:all .2s;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #f1f5f9;">
    <div style="width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:#2563eb12;border:1px solid #2563eb22;">{_svg("layers", 18, "#2563eb")}</div>
    <h3 style="font-size:16px;font-weight:700;color:#1a202c;margin:0;">{label}</h3>
  </div>
  {items_html}
</div>'''


def _render_predictive_executive_snapshot(data: Dict, lang: str) -> str:
    snapshot = data.get("predictive_snapshot")
    if not snapshot or not isinstance(snapshot, dict):
        return ""
    what = snapshot.get("what_will_happen", "")
    if not what:
        return ""

    title = "TIDSPLAN PROGNOSE" if lang == "da" else "SCHEDULE OUTLOOK"
    sub = "Hvad sker der, hvis der ikke handles?" if lang == "da" else "What happens if no action is taken?"

    delay_impact = _e(snapshot.get("estimated_delay_impact", ""))
    drivers = snapshot.get("main_delay_drivers", [])

    delay_badge = ""
    if delay_impact:
        delay_badge = f'<div style="display:inline-flex;align-items:center;gap:6px;margin:12px 0 16px;padding:8px 16px;border-radius:10px;background:#fffbeb;border:1.5px solid #fde68a;">{_svg("trending-up", 16, "#d97706")}<span style="font-size:16px;font-weight:900;color:#92400e;letter-spacing:-.3px;">{delay_impact}</span><span style="font-size:11px;color:#b45309;font-weight:600;">{"Estimeret forsinkelse" if lang == "da" else "Estimated delay"}</span></div>'

    drivers_label = "Primære forsinkelsesdrivere" if lang == "da" else "Main delay drivers"
    drivers_html = ""
    if drivers:
        items = "".join(
            f'<div style="padding:10px 14px;background:white;border-radius:8px;border:1px solid #fed7aa;margin-top:8px;display:flex;align-items:flex-start;gap:8px;"><span style="flex-shrink:0;margin-top:2px;">{_svg("chevron-right", 13, "#d97706")}</span><span style="font-size:13px;color:#374151;line-height:1.5;font-weight:500;">{_e(d)}</span></div>'
            for d in drivers[:3]
        )
        drivers_html = f'''<div style="margin-top:4px;">
  <div style="font-size:10px;font-weight:700;color:#ea580c;text-transform:uppercase;letter-spacing:.6px;margin-bottom:4px;">{_e(drivers_label)}</div>
  {items}
</div>'''

    return f'''
<div id="predictive-schedule-outlook" class="module-card" style="margin:0 0 20px;padding:22px 24px;background:linear-gradient(135deg,#fffbeb 0%,#fff7ed 100%);border-radius:14px;border:1px solid #fed7aa;border-left:5px solid #d97706;transition:all .2s;box-shadow:0 2px 10px rgba(217,119,6,.1);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #fde68a;">
    <div style="width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#d97706,#ea580c);box-shadow:0 3px 10px rgba(217,119,6,.3);">{_svg("trending-up", 20, "#fff")}</div>
    <div>
      <h3 style="font-size:17px;font-weight:800;color:#92400e;margin:0;letter-spacing:-.3px;">{title}</h3>
      <p style="margin:0;font-size:11px;color:#94a3b8;font-weight:500;">{sub}</p>
    </div>
  </div>
  <div style="font-size:15px;font-weight:700;color:#0f172a;line-height:1.7;padding:14px 18px;background:white;border-radius:10px;border:1px solid #e2e8f0;">{_e(what)}</div>
  {delay_badge}
  {drivers_html}
</div>'''


def _render_predictive_biggest_risk_card(data: Dict, lang: str) -> str:
    risk = data.get("predictive_biggest_risk")
    if not risk or not isinstance(risk, dict):
        return ""
    risk_title = risk.get("risk_title", "")
    if not risk_title:
        return ""

    will_block = _e(risk.get("will_block", ""))
    prevent = _e(risk.get("prevent_action_now", ""))

    card_title = "STØRSTE PRÆDIKTIVE RISIKO" if lang == "da" else "PREDICTIVE BIGGEST RISK"
    card_sub = "Den enkelt højest-prioriterede risiko der kræver øjeblikkelig handling" if lang == "da" else "The single highest-priority risk requiring immediate action"

    issue_label = "Problemet" if lang == "da" else "The Issue"
    block_label = "Blokerer" if lang == "da" else "What It Will Block"
    prevent_label = "Din næste handling" if lang == "da" else "Your Next Action"

    def _risk_part(emoji, label, text, bg, border, label_color, text_color):
        if not text:
            return ""
        return (
            f'<div style="padding:12px 16px;background:{bg};border-radius:10px;border:1px solid {border};margin-top:10px;">'
            f'<div style="font-size:11px;font-weight:700;color:{label_color};text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">{emoji} {_e(label)}</div>'
            f'<div style="font-size:13px;color:{text_color};line-height:1.6;">{text}</div>'
            f'</div>'
        )

    rows = (
        _risk_part("⚠️", issue_label, _e(risk_title), "#fef2f2", "#fecaca", "#dc2626", "#7f1d1d") +
        _risk_part("🔗", block_label, will_block, "#fff7ed", "#fed7aa", "#c2410c", "#7c2d12") +
        _risk_part("➡️", prevent_label, prevent, "#f0fdf4", "#bbf7d0", "#15803d", "#14532d")
    )

    return f'''
<div id="predictive-biggest-risk" class="module-card" style="margin:0 0 20px;padding:20px 24px;background:linear-gradient(135deg,#fef2f2,#ffffff);border-radius:14px;border:1px solid #fecaca;border-left:4px solid #ef4444;transition:all .2s;box-shadow:0 1px 4px rgba(0,0,0,.03);">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
    <span style="display:inline-flex;">{_svg("alert-triangle", 20, "#ef4444")}</span>
    <span style="font-size:14px;font-weight:800;color:#dc2626;text-transform:uppercase;letter-spacing:.5px;">{card_title}</span>
  </div>
  <div style="font-size:11px;color:#94a3b8;margin-bottom:2px;">{card_sub}</div>
  {rows}
</div>'''


def _render_predictive_confidence(data: Dict, lang: str) -> str:
    snapshot = data.get("predictive_snapshot")
    if not snapshot or not isinstance(snapshot, dict):
        return ""
    confidence = snapshot.get("confidence_level", "")
    basis = _e(snapshot.get("confidence_basis", ""))
    if not confidence:
        return ""

    card_title = "TILLIDSNIVEAU" if lang == "da" else "PREDICTIVE CONFIDENCE"
    basis_label = "Grundlag" if lang == "da" else "Basis"

    conf_config = {
        "HIGH": {"color": "#10b981", "label_en": "HIGH", "label_da": "HØJ"},
        "MEDIUM": {"color": "#d97706", "label_en": "MEDIUM", "label_da": "MODERAT"},
        "LOW": {"color": "#dc2626", "label_en": "LOW", "label_da": "LAV"},
    }
    cc = conf_config.get(confidence, conf_config["MEDIUM"])
    conf_label = cc["label_da"] if lang == "da" else cc["label_en"]

    return f'''
<div id="predictive-confidence" class="module-card" style="margin:0 0 20px 0;padding:16px 24px;background:linear-gradient(135deg,#f8fafc,#ffffff);border-radius:14px;border:1px solid #e2e8f0;border-left:4px solid {cc["color"]};box-shadow:0 1px 4px rgba(0,0,0,.03);">
  <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
    <div style="display:flex;align-items:center;gap:8px;">
      {_svg("shield-check", 18, cc["color"])}
      <span style="font-size:13px;font-weight:800;color:#475569;text-transform:uppercase;letter-spacing:.5px;">{card_title}</span>
    </div>
    <span style="padding:4px 14px;border-radius:20px;font-size:12px;font-weight:800;color:{cc["color"]};background:white;border:2px solid {cc["color"]};">{conf_label}</span>
    <span style="font-size:12px;color:#64748b;font-style:italic;flex:1;min-width:200px;">{basis_label}: {basis}</span>
  </div>
</div>'''


def _render_executive_actions(data: Dict, lang: str) -> str:
    actions = data.get("executive_actions", [])
    if not actions:
        return ""

    title = "PRÆDIKTIVE HANDLINGER" if lang == "da" else "PREDICTIVE ACTIONS"
    sub = "Hvad skal gøres nu for at undgå fremtidige forsinkelser" if lang == "da" else "What must be done now to avoid future delays"
    who_label = "Ansvarlig" if lang == "da" else "Responsible"
    when_label = "Deadline" if lang == "da" else "Deadline"
    tasks_label = "Relaterede opgaver" if lang == "da" else "Related tasks"

    rank_colors = {
        1: {"bg": "#fef2f2", "border": "#fecaca", "accent": "#dc2626", "badge_bg": "#dc2626"},
        2: {"bg": "#fffbeb", "border": "#fde68a", "accent": "#d97706", "badge_bg": "#d97706"},
        3: {"bg": "#f0fdfa", "border": "#99f6e4", "accent": "#0d9488", "badge_bg": "#0d9488"},
    }

    cards_html = ""
    for action in sorted(actions, key=lambda a: a.get("rank", 99)):
        rank = action.get("rank", 1)
        rc = rank_colors.get(rank, rank_colors[3])
        manpower_helps = action.get("manpower_helps", False)
        manpower_note = _e(action.get("manpower_note", ""))
        task_ids = action.get("related_task_ids", [])
        task_ids_html = " ".join(
            f'<span style="display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600;color:#134e4a;background:#f0fdfa;border:1px solid #99f6e4;font-family:\'SF Mono\',\'Cascadia Code\',monospace;">{_e(tid)}</span>'
            for tid in task_ids
        )

        if manpower_helps:
            mp_icon = _svg("circle-check", 14, "#059669")
            mp_color = "#059669"
            mp_bg = "#f0fdf4"
            mp_border = "#bbf7d0"
            mp_label = "Mandskab hjælper" if lang == "da" else "Manpower helps"
        else:
            mp_icon = _svg("alert-triangle", 14, "#dc2626")
            mp_color = "#dc2626"
            mp_bg = "#fef2f2"
            mp_border = "#fecaca"
            mp_label = "Mandskab hjælper IKKE" if lang == "da" else "Manpower will NOT help"

        deadline = _e(action.get("deadline", ""))
        responsible = _e(action.get("responsible", ""))

        meta_parts = []
        if deadline:
            meta_parts.append(f'{_svg("calendar", 13, "#d97706")} <span style="font-size:13px;font-weight:800;color:#92400e;">{deadline}</span>')
        if deadline and responsible:
            meta_parts.append('<span style="color:#cbd5e1;font-size:11px;">|</span>')
        if responsible:
            meta_parts.append(f'{_svg("user", 12, "#64748b")} <span style="font-size:12px;font-weight:600;color:#475569;">{responsible}</span>')
        meta_html = f'<div style="display:flex;align-items:center;gap:6px;margin-top:6px;flex-wrap:wrap;">{"".join(meta_parts)}</div>' if meta_parts else ""

        cards_html += f'''<div style="margin:10px 0;background:#fff;border-radius:12px;border:1px solid {rc["border"]};border-left:4px solid {rc["badge_bg"]};overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.04);">
  <div style="padding:16px 18px;">
    <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px;">
      <div style="width:32px;height:32px;border-radius:9px;display:flex;align-items:center;justify-content:center;background:{rc["badge_bg"]};color:#fff;font-size:16px;font-weight:800;flex-shrink:0;">{rank}</div>
      <div style="flex:1;min-width:0;">
        <div style="font-size:14px;font-weight:700;color:#1a202c;line-height:1.6;">{_e(action.get("action", ""))}</div>
        {meta_html}
      </div>
    </div>
    <div style="display:flex;gap:10px;align-items:stretch;flex-wrap:wrap;">
      <div style="flex:1;min-width:200px;padding:8px 12px;background:{mp_bg};border-radius:8px;border:1px solid {mp_border};">
        <div style="display:flex;align-items:center;gap:5px;margin-bottom:3px;">
          {mp_icon}
          <span style="font-size:10px;color:{mp_color};text-transform:uppercase;font-weight:800;letter-spacing:.5px;">{mp_label}</span>
        </div>
        <div style="font-size:12px;color:#374151;line-height:1.5;font-weight:500;">{manpower_note}</div>
      </div>
      <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap;padding:8px 12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">
        <span style="font-size:10px;color:#94a3b8;font-weight:600;white-space:nowrap;">{tasks_label}:</span>
        {task_ids_html}
      </div>
    </div>
  </div>
</div>'''

    return f'''
<div id="predictive-actions" class="module-card" style="margin:0 0 20px;padding:22px 24px;background:linear-gradient(135deg,#fff 0%,#f5f3ff 100%);border-radius:14px;border:1px solid #ddd6fe;border-left:5px solid #7c3aed;transition:all .2s;box-shadow:0 2px 10px rgba(124,58,237,.08);">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #ddd6fe;">
    <div style="width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#7c3aed,#6d28d9);box-shadow:0 3px 10px rgba(124,58,237,.3);">{_svg("zap", 20, "#fff")}</div>
    <div>
      <h3 style="font-size:17px;font-weight:800;color:#5b21b6;margin:0;letter-spacing:-.3px;">{title}</h3>
      <p style="margin:0;font-size:11px;color:#94a3b8;font-weight:500;">{sub}</p>
    </div>
  </div>
  {cards_html}
</div>'''


def format_predictive_as_html(raw_input, language: str = "en") -> str:
    if not raw_input:
        return ""

    try:
        if isinstance(raw_input, dict):
            data = raw_input
        elif isinstance(raw_input, str):
            data = json.loads(raw_input)
        else:
            return _fallback_html(str(raw_input))
    except (json.JSONDecodeError, TypeError):
        return _fallback_html(str(raw_input) if raw_input else "")

    try:
        return _build_html(data, language)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Predictive HTML formatter error: {e}")
        return _fallback_html(json.dumps(data, indent=2, ensure_ascii=False))


def _fallback_html(text: str) -> str:
    safe = _e(text)
    return f'<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;padding:24px;background:#fff;border-radius:16px;border:1px solid #e2e8f0;"><h2 style="color:#1a202c;margin-bottom:16px;">Nova Insight Report</h2><div style="white-space:pre-wrap;color:#4a5568;line-height:1.7;font-size:13px;">{safe}</div></div>'


def _build_html(data: Dict, lang: str) -> str:
    title = "Nova Insight" if lang == "da" else "Nova Insight"
    subtitle = "Beslutningsstøtte til projektledere" if lang == "da" else "Decision support for project managers"
    footer = "Genereret af Nova Insight AI" if lang == "da" else "Generated by Nova Insight AI"

    parts = [f'''
<style>
@keyframes novaFadeIn {{ from {{ opacity:0;transform:translateY(10px); }} to {{ opacity:1;transform:translateY(0); }} }}
.nova-report .module-card {{ animation:novaFadeIn .45s ease-out backwards; }}
.nova-report .module-card:nth-child(2) {{ animation-delay:.06s; }}
.nova-report .module-card:nth-child(3) {{ animation-delay:.12s; }}
.nova-report .module-card:nth-child(4) {{ animation-delay:.18s; }}
.nova-report .module-card:nth-child(5) {{ animation-delay:.24s; }}
.nova-report .module-card:nth-child(6) {{ animation-delay:.30s; }}
.nova-report .module-card:nth-child(7) {{ animation-delay:.36s; }}
.nova-report .module-card:nth-child(8) {{ animation-delay:.42s; }}
.nova-report .module-card:nth-child(9) {{ animation-delay:.48s; }}
.nova-report .module-card:nth-child(10) {{ animation-delay:.54s; }}
.nova-report .module-card:hover {{ border-color:#cbd5e1 !important;box-shadow:0 4px 16px rgba(0,0,0,.06) !important; }}
.nova-report table tr:hover {{ background:#edf2f7 !important; }}
.nova-report ::-webkit-scrollbar {{ height:6px; }}
.nova-report ::-webkit-scrollbar-track {{ background:#f1f5f9;border-radius:6px; }}
.nova-report ::-webkit-scrollbar-thumb {{ background:#cbd5e1;border-radius:6px; }}
</style>
<div class="nova-report" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f8fafc;border-radius:20px;padding:32px;border:1px solid #e2e8f0;box-shadow:0 1px 3px rgba(0,0,0,.06);">
  <div style="text-align:center;margin-bottom:28px;padding-bottom:24px;border-bottom:2px solid #edf2f7;">
    <div style="display:inline-flex;align-items:center;gap:14px;margin-bottom:10px;">
      <div style="width:44px;height:44px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#0d9488,#0891b2);box-shadow:0 4px 12px rgba(13,148,136,.25);">{_svg("clock", 24, "white")}</div>
      <div style="text-align:left;"><h2 style="font-size:22px;font-weight:800;color:#1a202c;margin:0;letter-spacing:-.4px;">{title}</h2><p style="font-size:12px;color:#94a3b8;margin:3px 0 0;letter-spacing:.3px;font-weight:500;">{subtitle}</p></div>
    </div>
  </div>''']

    parts.append(_render_predictive_executive_snapshot(data, lang))
    parts.append(_render_predictive_biggest_risk_card(data, lang))
    parts.append(_render_executive_actions(data, lang))
    parts.append(_render_predictive_confidence(data, lang))
    parts.append(_render_hero(data, lang))
    parts.append(_render_project_status_card(data, lang))
    parts.append(_render_schedule_overview(data, lang))
    parts.append(_render_management_conclusion(data, lang))
    parts.append(_render_delayed_table(data, lang))
    parts.append(_render_root_cause_analysis(data, lang))
    parts.append(_render_summary_by_area(data, lang))
    parts.append(_render_priority_actions(data, lang))
    parts.append(_render_resource_assessment(data, lang))
    parts.append(_render_forcing_assessment(data, lang))

    parts.append(f'''
  <div style="margin-top:12px;padding-top:16px;border-top:2px solid #edf2f7;display:flex;align-items:center;justify-content:center;gap:10px;">
    <div style="width:8px;height:8px;border-radius:50%;background:linear-gradient(135deg,#0d9488,#0891b2);box-shadow:0 0 8px rgba(13,148,136,.3);"></div>
    <span style="font-size:11px;color:#94a3b8;letter-spacing:.5px;font-weight:500;">{footer}</span>
  </div>
</div>''')

    return "\n".join(parts)
