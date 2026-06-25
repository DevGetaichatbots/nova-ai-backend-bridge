"""
html_formatter_v5.py
====================
Renders the v4 agent JSON as the v5 Project Health Dashboard.

Layout
------
  HEADER  (full-width)
  HERO    (full-width) — big Overall Progress numbers + 6 KPI pills
  ┌──────────────┬──────────────────────────────────────────────────┐
  │  LEFT SIDEBAR│  MAIN CONTENT                                    │
  │  Trade       │  Row 1: Behind Schedule | Ahead of Schedule     │
  │  Area        │  Row 2: Critical Activities (full-width)         │
  │  Floor       │  Row 3: What Should I Do | High Risk of         │
  │  Phase       │          Missing Deadline                        │
  │              │  Row 4: Schedule Comparison (full-width)         │
  │              │  Row 5: Summary & Notes | Delay Drivers          │
  └──────────────┴──────────────────────────────────────────────────┘
"""

from __future__ import annotations
import json as _json
import math
from datetime import date as _date


def _sf(val, default: float = 0.0) -> float:
    try:
        return float(str(val).replace("%", "").strip())
    except (ValueError, TypeError):
        return default


def _health_cls(health: str) -> tuple[str, str, str]:
    h = health.lower()
    if h == "red":
        return "v5-badge-red", "v5-dot-red", "Immediate action required"
    if h == "yellow":
        return "v5-badge-amber", "v5-dot-amber", "Some activities at risk"
    return "v5-badge-green", "v5-dot-green", "Project is on track"


def _delta_badge(delta: float, language: str = "en") -> str:
    da = language == "da"
    pp_lbl = "pp ændring" if da else "pp change"
    if delta > 0:
        color, sign = "#059669", "+"
    elif delta < 0:
        color, sign = "#dc2626", ""
    else:
        color, sign = "#64748b", ""
    return (
        f'<div style="display:inline-flex;flex-direction:column;align-items:center;'
        f'background:{"rgba(5,150,105,0.1)" if delta>=0 else "rgba(220,38,38,0.1)"};'
        f'border:1.5px solid {"rgba(5,150,105,0.25)" if delta>=0 else "rgba(220,38,38,0.25)"};'
        f'border-radius:10px;padding:8px 14px;min-width:72px;">'
        f'<span style="font-size:22px;font-weight:900;color:{color};line-height:1">'
        f'{sign}{delta:.1f}</span>'
        f'<span style="font-size:9px;font-weight:700;color:{color};letter-spacing:0.5px;'
        f'text-transform:uppercase;margin-top:2px">{pp_lbl}</span>'
        f'</div>'
    )


def _imp_label_py(var: float, da: bool) -> tuple[str, str]:
    if var <= -50:
        return ("KRITISK" if da else "CRITICAL"), "v5-imp-critical"
    if var <= -20:
        return ("HØJ RISIKO" if da else "HIGH RISK"), "v5-imp-high"
    return ("RISIKO" if da else "RISK"), "v5-imp-risk"


def _js_lang_pack(language: str) -> str:
    da = language == "da"
    pack = {
        "behindSchedule":   "Bagud i planen" if da else "Behind Schedule",
        "noBehind":         "Ingen aktiviteter bagud i planen ✓" if da else "No activities behind schedule ✓",
        "aheadOfSchedule":  "Foran planen" if da else "Ahead of Schedule",
        "noAhead":          "Ingen aktiviteter foran planen" if da else "No activities ahead of schedule",
        "criticalActivities": "Kritiske aktiviteter — Kræver øjeblikkelig handling" if da else "Critical Activities — Require Immediate Attention",
        "noCritical":       "Ingen kritiske aktiviteter ✓" if da else "No critical activities ✓",
        "impCritical":      "KRITISK" if da else "CRITICAL",
        "impHighRisk":      "HØJ RISIKO" if da else "HIGH RISK",
        "impRisk":          "RISIKO" if da else "RISK",
        "mostCritical":     "Mest kritisk" if da else "Most Critical",
        "noCriticalActions":"Ingen kritiske handlinger kræves ✓" if da else "No critical actions required ✓",
        "noPonrRed":        "Ingen aktiviteter ved point of no return ✓" if da else "No activities at point of no return ✓",
        "noPonrAmber":      "Ingen aktiviteter i genopretningsvinduet" if da else "No activities in recovery window",
        "none":             "Ingen" if da else "None",
        "noScheduleChanges":"Ingen tidsplanændringer" if da else "No schedule changes",
        "criticalPath":     "Kritiske sti-aktiviteter" if da else "Critical Path Activities",
        "noCriticalPath":   "Ingen data for kritisk sti" if da else "No critical path data available",
        "highRisk":         "HØJ RISIKO" if da else "HIGH RISK",
        "atRisk":           "I RISIKO" if da else "AT RISK",
        "onTrack":          "PÅ SPORET" if da else "ON TRACK",
        "actual":           "FAKTISK" if da else "ACTUAL",
        "workingDays":      " arbejdsdage" if da else " working days",
        "noDelay":          "ingen" if da else "none",
    }
    return f"window.__v5Lang = {_json.dumps(pack, ensure_ascii=False)};"


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
*{box-sizing:border-box;}
.v5{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;color:#0f172a;line-height:1.4;-webkit-font-smoothing:antialiased;}

/* Header */
.v5-header{background:#fff;padding:10px 20px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #e2e8f0;margin-bottom:0;}
.v5-logo{width:32px;height:32px;background:linear-gradient(135deg,#00D6D6,#38bdf8);border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.v5-header-text{display:flex;flex-direction:column;}
.v5-header-brand{font-size:9px;font-weight:700;letter-spacing:2px;color:#2563eb;text-transform:uppercase;line-height:1;}
.v5-header-title{font-size:18px;font-weight:900;letter-spacing:-0.4px;color:#0f172a;line-height:1.1;}
.v5-header-sub{font-size:11px;color:#94a3b8;}

/* Hero — Overall Progress */
.v5-hero{background:#fff;border-bottom:1px solid #e2e8f0;padding:16px 20px;}
.v5-hero-label{font-size:9px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#94a3b8;margin:0 0 12px 0;}
.v5-progress-hero{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:16px;}
.v5-progress-panel{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:14px 20px;min-width:180px;flex:1;max-width:260px;}
.v5-progress-panel-label{font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#64748b;margin-bottom:4px;}
.v5-progress-date{font-size:11px;color:#94a3b8;margin-bottom:6px;}
.v5-progress-pct{font-size:52px;font-weight:900;line-height:1;letter-spacing:-2px;color:#0f172a;}
.v5-progress-pct.green{color:#059669;} .v5-progress-pct.amber{color:#b45309;} .v5-progress-pct.red{color:#dc2626;}
.v5-progress-stats{display:flex;gap:12px;margin-top:8px;flex-wrap:wrap;}
.v5-progress-stat{font-size:10px;color:#64748b;}
.v5-progress-stat strong{color:#0f172a;font-weight:700;}
.v5-progress-arrow{font-size:28px;color:#94a3b8;flex-shrink:0;align-self:center;}

/* KPI pills row */
.v5-kpi-row{display:flex;gap:8px;flex-wrap:wrap;}
.v5-kpi-pill{flex:1;min-width:100px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;gap:4px;box-shadow:0 1px 3px rgba(0,0,0,0.04);}
.v5-kpi-icon{width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.v5-kpi-num{font-size:26px;font-weight:900;line-height:1;transition:all .2s;}
.v5-kpi-lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px;color:#475569;}
.v5-kpi-sub{font-size:9px;color:#94a3b8;transition:all .2s;}

/* Status badge */
.v5-badge{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:30px;font-size:14px;font-weight:800;border:2px solid transparent;}
.v5-badge-red{background:rgba(239,68,68,0.1);color:#dc2626;border-color:rgba(239,68,68,0.25);}
.v5-badge-amber{background:rgba(245,158,11,0.1);color:#b45309;border-color:rgba(245,158,11,0.25);}
.v5-badge-green{background:rgba(16,185,129,0.1);color:#059669;border-color:rgba(16,185,129,0.25);}
.v5-dot{display:inline-block;width:7px;height:7px;border-radius:50%;}
.v5-dot-red{background:#ef4444;} .v5-dot-amber{background:#f59e0b;} .v5-dot-green{background:#10b981;}

/* Page body */
.v5-page-body{display:flex;align-items:flex-start;min-height:600px;}

/* Sidebar */
.v5-sidebar{width:210px;min-width:210px;background:#fff;border-right:1px solid #e2e8f0;padding:12px;position:sticky;top:0;align-self:flex-start;flex-shrink:0;}
.v5-filter-group{margin-bottom:14px;}
.v5-filter-group-title{font-size:9px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:#94a3b8;margin:0 0 6px 0;display:flex;align-items:center;justify-content:space-between;cursor:pointer;user-select:none;}
.v5-filter-opts{display:flex;flex-direction:column;gap:3px;}
.v5-filter-opt{display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:6px;font-size:11px;font-weight:500;color:#334155;cursor:pointer;border:1px solid transparent;transition:all .12s;user-select:none;}
.v5-filter-opt:hover{background:#f1f5f9;}
.v5-filter-opt.active{background:rgba(37,99,235,0.08);border-color:rgba(37,99,235,0.2);color:#1d4ed8;font-weight:700;}
.v5-filter-opt-dot{width:8px;height:8px;border-radius:50%;background:#e2e8f0;flex-shrink:0;transition:background .12s;}
.v5-filter-opt.active .v5-filter-opt-dot{background:#2563eb;}
.v5-filter-count{margin-left:auto;font-size:9px;color:#94a3b8;font-weight:600;}
.v5-filter-empty{font-size:10px;color:#94a3b8;padding:4px 8px;font-style:italic;}
.v5-sidebar-divider{height:1px;background:#f1f5f9;margin:8px 0;}

/* Main content */
.v5-main{flex:1;min-width:0;padding:14px 16px;display:flex;flex-direction:column;gap:12px;}

/* Cards */
.v5-card{background:#fff;border-radius:10px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,0.05);border:1px solid #e2e8f0;}
.v5-card-header{display:flex;align-items:center;gap:8px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #f1f5f9;}
.v5-card-icon{width:26px;height:26px;border-radius:7px;display:flex;align-items:center;justify-content:center;color:#fff;flex-shrink:0;}
.v5-card-title{font-size:11px;font-weight:800;color:#0f172a;margin:0;letter-spacing:0.2px;}
.v5-card-sub{font-size:9px;color:#94a3b8;margin-top:1px;}

/* Two-column rows */
.v5-row-2col{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
@media(max-width:900px){.v5-row-2col{grid-template-columns:1fr;}}

/* Scrollable tables */
.v5-scroll-wrap{max-height:300px;overflow-y:auto;border-radius:7px;border:1px solid #f1f5f9;scrollbar-width:thin;}
.v5-table{width:100%;border-collapse:separate;border-spacing:0;font-size:11px;}
.v5-table thead th{background:#f8fafc;font-weight:700;color:#475569;text-transform:uppercase;font-size:9px;letter-spacing:0.3px;padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:left;position:sticky;top:0;z-index:1;}
.v5-table tbody td{padding:6px 8px;border-bottom:1px solid #f8fafc;color:#334155;vertical-align:top;}
.v5-table tbody tr:last-child td{border-bottom:none;}
.v5-table tbody tr:hover{background:#fafafa;}
.v5-act-name{font-weight:600;color:#0f172a;max-width:200px;word-break:break-word;}
.v5-var-neg{font-weight:700;color:#dc2626;}
.v5-var-pos{font-weight:700;color:#059669;}
.v5-loc-badge{display:inline-flex;align-items:center;gap:3px;padding:1px 5px;border-radius:4px;font-size:9px;font-weight:600;background:#f1f5f9;color:#475569;white-space:nowrap;}

/* Critical Activities card */
.v5-critical-card{border-left:3px solid #dc2626;}
.v5-critical-card .v5-card-header{border-bottom-color:rgba(239,68,68,0.1);}

/* PONR split card */
.v5-ponr-section{padding:8px 0;}
.v5-ponr-section+.v5-ponr-section{border-top:1px solid #f1f5f9;}
.v5-ponr-section-title{font-size:9px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;margin-bottom:6px;display:flex;align-items:center;gap:6px;}
.v5-ponr-list{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:4px;}
.v5-ponr-item{display:flex;align-items:flex-start;gap:6px;font-size:11px;}
.v5-ponr-num{width:16px;height:16px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:8px;font-weight:800;flex-shrink:0;margin-top:1px;}
.v5-ponr-num-red{background:#fecaca;color:#dc2626;}
.v5-ponr-num-amber{background:#fef3c7;color:#b45309;}
.v5-ponr-name{font-weight:600;color:#0f172a;flex:1;}
.v5-ponr-rec{font-size:10px;color:#64748b;margin-top:1px;}

/* Impact badges */
.v5-imp{display:inline-flex;align-items:center;padding:1px 6px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:0.2px;white-space:nowrap;}
.v5-imp-critical{background:rgba(239,68,68,0.12);color:#b91c1c;border:1px solid rgba(239,68,68,0.2);}
.v5-imp-high{background:rgba(245,158,11,0.12);color:#92400e;border:1px solid rgba(245,158,11,0.2);}
.v5-imp-risk{background:rgba(245,158,11,0.08);color:#b45309;border:1px solid rgba(245,158,11,0.15);}

/* WSID */
.v5-wsid-tag{font-size:9px;font-weight:800;letter-spacing:0.8px;text-transform:uppercase;color:#64748b;margin-bottom:3px;}
.v5-wsid-activity{font-size:13px;font-weight:800;color:#0f172a;margin-bottom:2px;line-height:1.2;}
.v5-wsid-issue{font-size:11px;color:#64748b;margin-bottom:8px;}
.v5-wsid-inner{display:flex;gap:10px;align-items:flex-start;}
.v5-actions-list{list-style:none;padding:0;margin:0;flex:1;}
.v5-actions-list li{display:flex;align-items:flex-start;gap:5px;font-size:10.5px;color:#334155;padding:3px 0;border-bottom:1px solid #f8fafc;}
.v5-actions-list li:last-child{border-bottom:none;}
.v5-action-check{width:13px;height:13px;border-radius:50%;background:rgba(16,185,129,0.12);color:#059669;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;}

/* Change section */
.v5-change-kpis{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap;}
.v5-change-kpi{flex:1;min-width:60px;text-align:center;padding:7px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px;}
.v5-change-kpi-num{font-size:20px;font-weight:900;line-height:1;}
.v5-change-kpi-lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.2px;color:#64748b;margin-top:1px;}
.v5-change-section{margin-top:10px;}
.v5-change-section-lbl{font-size:9px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;color:#94a3b8;margin:6px 0 4px 0;}

/* Summary & Notes */
.v5-summary-row{display:flex;align-items:baseline;justify-content:space-between;padding:5px 0;border-bottom:1px solid #f8fafc;font-size:11.5px;}
.v5-summary-row:last-child{border-bottom:none;}
.v5-summary-lbl{color:#64748b;font-weight:500;}
.v5-summary-val{font-weight:700;color:#0f172a;text-align:right;}
.v5-summary-delta{font-size:10px;font-weight:700;margin-left:6px;}
.v5-summary-delta.pos{color:#059669;} .v5-summary-delta.neg{color:#dc2626;} .v5-summary-delta.neu{color:#64748b;}

/* Delay Drivers */
.v5-driver-item{padding:8px 0;border-bottom:1px solid #f8fafc;}
.v5-driver-item:last-child{border-bottom:none;}
.v5-driver-name{font-size:12px;font-weight:700;color:#0f172a;margin-bottom:2px;}
.v5-driver-desc{font-size:10.5px;color:#64748b;line-height:1.4;}
.v5-driver-count{font-size:9px;font-weight:700;color:#2563eb;margin-top:2px;}

/* Donut */
.v5-donut-wrap{flex-shrink:0;}

/* Colour helpers */
.c-red{color:#dc2626!important;} .c-green{color:#059669!important;} .c-amber{color:#b45309!important;} .c-blue{color:#2563eb!important;}
"""


# ---------------------------------------------------------------------------
# JavaScript — client-side 4-dimension filter engine (uses window.__v5Lang)
# ---------------------------------------------------------------------------

_JS = r"""
(function() {
  var D = window.__v5Data;
  if (!D) return;
  var L = window.__v5Lang||{};

  var TRADE_PFX = {
    'EL':   ['EL -','EL-'],
    'VVS':  ['VVS -','VVS-'],
    'VENT': ['VENT -','VENT-'],
    'ARK':  ['ARK -','ARK-'],
    'BYGH': ['BYGH -','BYGH-']
  };

  var AF = { trade:'ALL', area:'ALL', floor:'ALL', phase:'ALL' };

  function inTrade(name, code) {
    if (code === 'ALL' || !TRADE_PFX[code]) return true;
    var u = (name||'').toUpperCase();
    return TRADE_PFX[code].some(function(p){ return u.indexOf(p.toUpperCase())===0; });
  }

  function matchAll(item) {
    var name = typeof item==='string' ? item : (item.activity||'');
    var loc  = (typeof item==='object' && item.location) ? item.location : {};
    if (!inTrade(name, AF.trade)) return false;
    if (AF.area  !=='ALL' && (loc.area  ||'')!==AF.area)  return false;
    if (AF.floor !=='ALL' && (loc.floor ||'')!==AF.floor) return false;
    if (AF.phase !=='ALL' && (loc.phase ||'')!==AF.phase) return false;
    return true;
  }

  function filt(arr) { return (arr||[]).filter(matchAll); }
  function filtStr(arr) { return (arr||[]).filter(function(s){ return matchAll(s); }); }

  function el(id){ return document.getElementById(id); }
  function sf(v){ return parseFloat((''+(v||0)).replace('%','').trim())||0; }

  function impLabel(v) {
    if (v<=-50) return [L.impCritical||'CRITICAL','v5-imp-critical'];
    if (v<=-20) return [L.impHighRisk||'HIGH RISK','v5-imp-high'];
    return [L.impRisk||'RISK','v5-imp-risk'];
  }

  function locBadge(item) {
    var loc = item.location||{};
    var parts = [loc.area, loc.floor, loc.phase].filter(Boolean);
    if (!parts.length) return '';
    return parts.map(function(p){
      return '<span class="v5-loc-badge">'+p+'</span>';
    }).join(' ');
  }

  function donut(pct) {
    var r=38, c=2*Math.PI*r, f=c*Math.min(100,Math.max(0,pct))/100, g=c-f;
    var sz=(r+18)*2, cx=sz/2, cy=sz/2;
    var col=pct<50?'#ef4444':pct<75?'#f59e0b':'#10b981';
    return '<div class="v5-donut-wrap"><svg width="'+sz+'" height="'+sz+'" viewBox="0 0 '+sz+' '+sz+'">'+
      '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="#f1f5f9" stroke-width="11"/>'+
      '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="'+col+'" stroke-width="11" '+
      'stroke-dasharray="'+f.toFixed(1)+' '+g.toFixed(1)+'" stroke-linecap="round" '+
      'transform="rotate(-90 '+cx+' '+cy+')"/>'+
      '<text x="'+cx+'" y="'+cy+'" text-anchor="middle" dominant-baseline="central" font-size="18" font-weight="900" fill="#0f172a">'+Math.round(pct)+'%</text>'+
      '<text x="'+cx+'" y="'+(cy+15)+'" text-anchor="middle" font-size="9" fill="#64748b" font-weight="600">'+(L.actual||'ACTUAL')+'</text>'+
      '</svg></div>';
  }

  function renderKPIs(behind, ahead, critPonr, cp) {
    var eB=el('v5-kpi-behind'); if(eB) eB.textContent=behind.length;
    var eA=el('v5-kpi-ahead');  if(eA) eA.textContent=ahead.length;
    var eC=el('v5-kpi-critical');if(eC)eC.textContent=critPonr.length;
    var eP=el('v5-kpi-cp');     if(eP) eP.textContent=cp.length;
    var eH=el('v5-kpi-highrisk');if(eH)eH.textContent=critPonr.filter(function(i){return (i.classification||'').toLowerCase()==='red';}).length;
    var sel=(D.executive_summary||{}).selected_activities||0;
    var tc=(D.executive_summary||{}).trade_counts||{};
    var sel2=(AF.trade==='ALL')?sel:(tc[AF.trade]||sel);
    var eAn=el('v5-kpi-analyzed');if(eAn)eAn.textContent=sel2;
  }

  function renderBehind(behind) {
    var hdr=el('v5-behind-hdr');
    if(hdr)hdr.textContent=(L.behindSchedule||'Behind Schedule')+' ('+behind.length+')';
    var tb=el('v5-behind-tbody'); if(!tb)return;
    if(!behind.length){
      tb.innerHTML='<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">'+(L.noBehind||'No activities behind schedule ✓')+'</td></tr>';
      return;
    }
    tb.innerHTML=behind.map(function(i){
      var v=sf(i.variance_pct);
      return '<tr><td class="v5-act-name">'+i.activity+'</td>'+
        '<td>'+locBadge(i)+'</td>'+
        '<td>'+Math.round(sf(i.expected_pct))+'%</td>'+
        '<td>'+Math.round(sf(i.actual_pct))+'%</td>'+
        '<td class="v5-var-neg">'+(v>=0?'+':'')+v.toFixed(0)+'%</td></tr>';
    }).join('');
  }

  function renderAhead(ahead) {
    var hdr=el('v5-ahead-hdr');
    if(hdr)hdr.textContent=(L.aheadOfSchedule||'Ahead of Schedule')+' ('+ahead.length+')';
    var tb=el('v5-ahead-tbody'); if(!tb)return;
    if(!ahead.length){
      tb.innerHTML='<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">'+(L.noAhead||'No activities ahead of schedule')+'</td></tr>';
      return;
    }
    tb.innerHTML=ahead.map(function(i){
      var v=sf(i.variance_pct);
      return '<tr><td class="v5-act-name">'+i.activity+'</td>'+
        '<td>'+locBadge(i)+'</td>'+
        '<td>'+Math.round(sf(i.expected_pct))+'%</td>'+
        '<td>'+Math.round(sf(i.actual_pct))+'%</td>'+
        '<td class="v5-var-pos">+'+Math.abs(v).toFixed(0)+'%</td></tr>';
    }).join('');
  }

  function renderCritical(critPonr) {
    var hdr=el('v5-critical-hdr');
    if(hdr)hdr.textContent=(L.criticalActivities||'Critical Activities — Require Immediate Attention')+' ('+critPonr.length+')';
    var ct=el('v5-critical-count'); if(ct)ct.textContent=critPonr.length;
    var tb=el('v5-critical-tbody'); if(!tb)return;
    if(!critPonr.length){
      tb.innerHTML='<tr><td colspan="6" style="text-align:center;color:#64748b;padding:14px">'+(L.noCritical||'No critical activities ✓')+'</td></tr>';
      return;
    }
    tb.innerHTML=critPonr.map(function(i,idx){
      var v=sf(i.variance_pct);
      var imp=impLabel(v);
      return '<tr>'+
        '<td style="color:#94a3b8;font-size:10px">'+(idx+1)+'</td>'+
        '<td class="v5-act-name">'+i.activity+'</td>'+
        '<td>'+locBadge(i)+'</td>'+
        '<td>'+Math.round(sf(i.actual_pct))+'%</td>'+
        '<td class="v5-var-neg">'+(v>=0?'+':'')+v.toFixed(0)+'%</td>'+
        '<td><span class="v5-imp '+imp[1]+'">'+imp[0]+'</span></td>'+
        '<td style="font-size:10px;color:#64748b">'+i.remaining_time+'</td></tr>';
    }).join('');
  }

  function renderWsid(recs, progress) {
    var sec=el('v5-wsid-body'); if(!sec)return;
    if(!recs.length){
      sec.innerHTML='<div style="padding:16px 0;color:#64748b;font-size:12px;text-align:center">'+(L.noCriticalActions||'No critical actions required ✓')+'</div>';
      return;
    }
    var top=recs[0];
    var name=top.activity||'';
    var pi=progress.filter(function(p){return p.activity===name;})[0];
    var pct=pi?sf(pi.actual_pct):0;
    var v=pi?sf(pi.variance_pct):-50;
    var imp=impLabel(v);
    sec.innerHTML=
      '<div class="v5-wsid-tag">'+(L.mostCritical||'Most Critical')+' <span class="v5-imp '+imp[1]+'" style="margin-left:5px">'+imp[0]+'</span></div>'+
      '<div class="v5-wsid-activity">'+name+'</div>'+
      '<div class="v5-wsid-issue">'+(top.issue||'')+'</div>'+
      '<div class="v5-wsid-inner">'+
      donut(pct)+
      '<ul class="v5-actions-list">'+
      (top.actions||[]).slice(0,6).map(function(a){
        return '<li><div class="v5-action-check"><svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></div>'+a+'</li>';
      }).join('')+
      '</ul></div>';
  }

  function renderPonr(redPonr, yellowPonr) {
    var rc=el('v5-ponr-red-count');   if(rc)rc.textContent=redPonr.length;
    var yc=el('v5-ponr-amber-count'); if(yc)yc.textContent=yellowPonr.length;

    var rl=el('v5-ponr-red-list'); if(rl){
      if(!redPonr.length){
        rl.innerHTML='<li style="color:#64748b;font-size:11px;list-style:none;padding:4px 0">'+(L.noPonrRed||'No activities at point of no return ✓')+'</li>';
      } else {
        rl.innerHTML=redPonr.slice(0,6).map(function(i,idx){
          return '<li class="v5-ponr-item">'+
            '<div class="v5-ponr-num v5-ponr-num-red">'+(idx+1)+'</div>'+
            '<div><div class="v5-ponr-name">'+i.activity+'</div>'+
            '<div class="v5-ponr-rec">'+(i.recommendation||i.remaining_time||'')+'</div></div></li>';
        }).join('');
      }
    }
    var yl=el('v5-ponr-amber-list'); if(yl){
      if(!yellowPonr.length){
        yl.innerHTML='<li style="color:#64748b;font-size:11px;list-style:none;padding:4px 0">'+(L.noPonrAmber||'No activities in recovery window')+'</li>';
      } else {
        yl.innerHTML=yellowPonr.slice(0,6).map(function(i,idx){
          return '<li class="v5-ponr-item">'+
            '<div class="v5-ponr-num v5-ponr-num-amber">'+(idx+1)+'</div>'+
            '<div><div class="v5-ponr-name">'+i.activity+'</div>'+
            '<div class="v5-ponr-rec">'+(i.recommendation||i.remaining_time||'')+'</div></div></li>';
        }).join('');
      }
    }
  }

  function renderChanges(ch, added, removed) {
    var durCt  = ch.filter(function(c){return (c.change_type||'').toLowerCase().indexOf('duration')>=0;}).length;
    var dateCt = ch.length - durCt;
    var eAdd=el('v5-chg-add');  if(eAdd) eAdd.textContent=added.length;
    var eRem=el('v5-chg-rem');  if(eRem) eRem.textContent=removed.length;
    var eDt=el('v5-chg-date');  if(eDt)  eDt.textContent=dateCt;
    var eDu=el('v5-chg-dur');   if(eDu)  eDu.textContent=durCt;

    var addTb=el('v5-added-tbody'); if(addTb){
      addTb.innerHTML=!added.length
        ? '<tr><td colspan="1" style="color:#64748b;font-size:11px;padding:8px">'+(L.none||'None')+'</td></tr>'
        : added.slice(0,20).map(function(a){return '<tr><td style="font-size:11px;padding:4px 8px;color:#0f172a">'+a+'</td></tr>';}).join('');
    }
    var remTb=el('v5-removed-tbody'); if(remTb){
      remTb.innerHTML=!removed.length
        ? '<tr><td colspan="1" style="color:#64748b;font-size:11px;padding:8px">'+(L.none||'None')+'</td></tr>'
        : removed.slice(0,20).map(function(a){return '<tr><td style="font-size:11px;padding:4px 8px;color:#dc2626">'+a+'</td></tr>';}).join('');
    }
    var chTb=el('v5-changes-tbody'); if(chTb){
      chTb.innerHTML=!ch.length
        ? '<tr><td colspan="4" style="text-align:center;color:#64748b;padding:12px">'+(L.noScheduleChanges||'No schedule changes')+'</td></tr>'
        : ch.map(function(c){
            var isDate=(c.change_type||'').toLowerCase().indexOf('date')>=0;
            var isDur=(c.change_type||'').toLowerCase().indexOf('dur')>=0;
            var dot=isDate?'style="color:#2563eb"':isDur?'style="color:#7c3aed"':'';
            return '<tr><td class="v5-act-name">'+c.activity+'</td>'+
              '<td '+dot+' style="font-size:10px;font-weight:700">'+c.change_type+'</td>'+
              '<td style="font-size:11px;color:#64748b">'+c.old+'</td>'+
              '<td style="font-size:11px;font-weight:600">'+c.new+'</td></tr>';
          }).join('');
    }
  }

  function renderCP(cp) {
    var hdr=el('v5-cp-hdr');
    if(hdr)hdr.textContent=(L.criticalPath||'Critical Path Activities')+' ('+cp.length+')';
    var tb=el('v5-cp-tbody'); if(!tb)return;
    if(!cp.length){
      tb.innerHTML='<tr><td colspan="5" style="text-align:center;color:#64748b;padding:12px">'+(L.noCriticalPath||'No critical path data available')+'</td></tr>';
      return;
    }
    tb.innerHTML=cp.map(function(i){
      var pct=sf(i.actual_pct);
      var color=pct<25?'#dc2626':pct<75?'#b45309':'#059669';
      return '<tr>'+
        '<td class="v5-act-name">'+i.activity+'</td>'+
        '<td>'+locBadge(i)+'</td>'+
        '<td style="font-weight:700;color:'+color+'">'+Math.round(pct)+'%</td>'+
        '<td style="font-size:10px">'+i.start_date+'</td>'+
        '<td style="font-size:10px">'+i.finish_date+'</td></tr>';
    }).join('');
  }

  function renderStatus(behindLen, critLen) {
    var health=critLen>0&&behindLen>0?'Red':behindLen>0?'Yellow':'Green';
    var cfg={
      'Red':   {bc:'v5-badge-red',   dc:'v5-dot-red',   lbl:L.highRisk||'HIGH RISK'},
      'Yellow':{bc:'v5-badge-amber', dc:'v5-dot-amber', lbl:L.atRisk||'AT RISK'},
      'Green': {bc:'v5-badge-green', dc:'v5-dot-green', lbl:L.onTrack||'ON TRACK'},
    };
    var c=cfg[health]||cfg['Green'];
    var wrap=el('v5-status-badge-wrap');
    if(wrap){
      var badge=wrap.querySelector('.v5-badge');
      if(badge) badge.className='v5-badge '+c.bc;
      var dot=wrap.querySelector('.v5-dot');
      if(dot)   dot.className='v5-dot '+c.dc;
      var lbl=el('v5-status-lbl');
      if(lbl)   lbl.textContent=c.lbl;
    }
  }

  function render() {
    var ch=D.changed_activities||{};
    var progress   = filt(D.progress_vs_expected);
    var ponr       = filt(D.point_of_no_return);
    var recs       = filt(D.action_recommendations);
    var changes    = filt(ch.changes);
    var added      = filtStr(ch.added);
    var removed    = filtStr(ch.removed);
    var cp         = filt(D.critical_path_activities);
    var behind     = progress.filter(function(i){return (i.status||'').toLowerCase()==='behind';});
    var ahead      = progress.filter(function(i){return (i.status||'').toLowerCase()==='ahead';});
    var redPonr    = ponr.filter(function(i){return (i.classification||'').toLowerCase()==='red';});
    var yellowPonr = ponr.filter(function(i){return (i.classification||'').toLowerCase()==='yellow';});
    var critPonr   = redPonr.concat(yellowPonr);

    renderStatus(behind.length, critPonr.length);
    renderKPIs(behind, ahead, critPonr, cp);
    renderBehind(behind);
    renderAhead(ahead);
    renderCritical(critPonr);
    renderWsid(recs, progress);
    renderPonr(redPonr, yellowPonr);
    renderChanges(changes, added, removed);
    renderCP(cp);
  }

  window.v5SetFilter = function(dim, val) {
    AF[dim] = val;
    document.querySelectorAll('[data-filter-dim="'+dim+'"]').forEach(function(opt){
      var isActive = opt.getAttribute('data-filter-val') === val;
      opt.classList.toggle('active', isActive);
    });
    render();
  };

  document.addEventListener('DOMContentLoaded', function(){ render(); });
  if (document.readyState !== 'loading') { render(); }
})();
"""


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def format_compare_v5_as_html(data: dict, language: str = "en") -> str:  # noqa: C901
    parts: list[str] = []
    a = parts.append
    da = language == "da"

    es       = data.get("executive_summary", {})
    sn       = data.get("summary_notes", {})
    fo       = data.get("filter_options", {})
    health   = str(es.get("project_health", "Green"))
    sel_act  = int(es.get("selected_activities", 0))
    behind_n = int(es.get("behind_schedule_count", 0))
    ahead_n  = int(es.get("ahead_of_schedule_count", 0))
    crit_n   = int(es.get("critical_count", 0))
    cp_n     = int(es.get("critical_path_count", 0))
    ponr_n   = int(es.get("point_of_no_return_count", 0))

    progress_items = data.get("progress_vs_expected", [])
    behind_items   = [i for i in progress_items if "behind" in str(i.get("status", "")).lower()]
    ahead_items    = [i for i in progress_items if "ahead"  in str(i.get("status", "")).lower()]
    ponr_items     = data.get("point_of_no_return", [])
    red_ponr       = [i for i in ponr_items if str(i.get("classification", "")).upper() == "RED"]
    yellow_ponr    = [i for i in ponr_items if str(i.get("classification", "")).upper() == "YELLOW"]
    all_crit       = red_ponr + yellow_ponr
    cp_items       = data.get("critical_path_activities", [])
    action_recs    = data.get("action_recommendations", [])
    not_started    = data.get("not_started_overdue", [])
    changes_raw    = data.get("changed_activities", {})
    added_list     = changes_raw.get("added", [])
    removed_list   = changes_raw.get("removed", [])
    flat_changes   = changes_raw.get("changes", [])
    drivers        = data.get("delay_drivers", [])

    badge_cls, dot_cls, _ = _health_cls(health)
    if da:
        status_label = {"red": "HØJ RISIKO", "yellow": "I RISIKO"}.get(health.lower(), "PÅ SPORET")
    else:
        status_label = {"red": "HIGH RISK", "yellow": "AT RISK"}.get(health.lower(), "ON TRACK")

    old_pct    = _sf(sn.get("overall_progress_old_pct", 0))
    new_pct    = _sf(sn.get("overall_progress_new_pct", 0))
    delta      = _sf(sn.get("overall_progress_delta", 0))
    period_old = str(sn.get("reporting_period_old", "Forrige tidsplan" if da else "Previous Schedule"))
    period_new = str(sn.get("reporting_period_new", "Nuværende tidsplan" if da else "Current Schedule"))
    finished_n = int(sn.get("finished_activities", 0))
    delayed_n  = int(sn.get("delayed_activities", behind_n))
    total_n    = int(sn.get("total_activities", sel_act))
    added_n    = int(sn.get("added_count", len(added_list)))
    removed_n  = int(sn.get("removed_count", len(removed_list)))

    new_pct_color = "red" if new_pct < 50 else "amber" if new_pct < 75 else "green"

    dur_changes  = sum(1 for c in flat_changes if "duration" in str(c.get("change_type", "")).lower())
    date_changes = len(flat_changes) - dur_changes

    json_str = _json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    # -- Boilerplate --
    a(f"<style>{_CSS}</style>")
    a(f"<script>{_js_lang_pack(language)}</script>")
    a(f"<script>window.__v5Data = {json_str};</script>")
    a('<div class="v5">')

    # ── Header ────────────────────────────────────────────────────────────
    header_title = "PROJEKTSUNDHEDSDASHBOARD" if da else "PROJECT HEALTH DASHBOARD"
    header_sub   = "Er vi på sporet? Hvor er problemet? Hvad skal jeg gøre?" if da else "Are we on track? Where is the problem? What should I do?"
    a(f'''<div class="v5-header">
  <div class="v5-logo">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
      <path d="M2 20h20M6 20V10M12 20V4M18 20v-6"/>
    </svg>
  </div>
  <div class="v5-header-text">
    <p class="v5-header-brand">Nova Insight</p>
    <h1 class="v5-header-title">{header_title}</h1>
    <p class="v5-header-sub">{header_sub}</p>
  </div>
  <div style="margin-left:auto" id="v5-status-badge-wrap">''')
    a(f'    <span class="v5-badge {badge_cls}"><span class="v5-dot {dot_cls}"></span>'
      f'<span id="v5-status-lbl">{status_label}</span></span>')
    a('  </div>\n</div>')

    # ── Hero: Overall Progress ─────────────────────────────────────────────
    hero_label  = "Samlet projektfremskridt" if da else "Overall Project Progress"
    prev_lbl    = "Forrige tidsplan" if da else "Previous Schedule"
    curr_lbl    = "Nuværende tidsplan" if da else "Current Schedule"
    total_word  = "i alt" if da else "total"
    late_word   = "forsinket" if da else "late"
    finish_word = "afsluttet" if da else "finished"

    a('<div class="v5-hero">')
    a(f'<p class="v5-hero-label">{hero_label}</p>')
    a('<div class="v5-progress-hero">')

    if old_pct > 0:
        old_color = "red" if old_pct < 50 else "amber" if old_pct < 75 else "green"
        a(f'''<div class="v5-progress-panel">
  <div class="v5-progress-panel-label">{prev_lbl}</div>
  <div class="v5-progress-date">{period_old}</div>
  <div class="v5-progress-pct {old_color}">{old_pct:.1f}%</div>
  <div class="v5-progress-stats">
    <span class="v5-progress-stat"><strong>{total_n}</strong> {total_word}</span>
    <span class="v5-progress-stat"><strong>{delayed_n}</strong> {late_word}</span>
  </div>
</div>''')
        a('<div class="v5-progress-arrow">→</div>')

    a(f'''<div class="v5-progress-panel" style="border-color:{"#fca5a5" if new_pct_color=="red" else "#fcd34d" if new_pct_color=="amber" else "#6ee7b7"};">
  <div class="v5-progress-panel-label">{curr_lbl}</div>
  <div class="v5-progress-date">{period_new}</div>
  <div class="v5-progress-pct {new_pct_color}">{new_pct:.1f}%</div>
  <div class="v5-progress-stats">
    <span class="v5-progress-stat"><strong>{total_n}</strong> {total_word}</span>
    <span class="v5-progress-stat"><strong>{delayed_n}</strong> {late_word}</span>
    <span class="v5-progress-stat"><strong>{finished_n}</strong> {finish_word}</span>
  </div>
</div>''')

    if old_pct > 0:
        a(_delta_badge(delta, language))

    a('</div>')  # progress-hero

    # KPI pills
    a('<div class="v5-kpi-row">')
    pills_cfg = [
        ("v5-kpi-highrisk", str(ponr_n),  "c-red",   "rgba(239,68,68,0.12)",  "#dc2626",
         '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
         "Høj risiko" if da else "High Risk"),
        ("v5-kpi-analyzed", str(sel_act), "c-blue",  "rgba(14,165,233,0.12)", "#0284c7",
         '<path d="M3 3h18v18H3z"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
         "Aktiviteter" if da else "Activities"),
        ("v5-kpi-critical", str(crit_n),  "c-red",   "rgba(239,68,68,0.12)",  "#dc2626",
         '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>',
         "Kritisk" if da else "Critical"),
        ("v5-kpi-cp",       str(cp_n),    "c-blue",  "rgba(124,58,237,0.12)", "#7c3aed",
         '<path d="M18 20V10M12 20V4M6 20v-6"/><circle cx="18" cy="8" r="2"/><circle cx="12" cy="2" r="2"/><circle cx="6" cy="12" r="2"/>',
         "Kritisk sti" if da else "Critical Path"),
        ("v5-kpi-behind",   str(behind_n),"c-red",   "rgba(239,68,68,0.12)",  "#dc2626",
         '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
         "Bagud" if da else "Behind"),
        ("v5-kpi-ahead",    str(ahead_n), "c-green", "rgba(16,185,129,0.12)", "#059669",
         '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
         "Foran" if da else "Ahead"),
    ]
    for pid, val, num_cls, icon_bg, icon_color, icon_path, lbl in pills_cfg:
        a(f'''<div class="v5-kpi-pill">
  <div class="v5-kpi-icon" style="background:{icon_bg}">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="{icon_color}" stroke-width="2.5">{icon_path}</svg>
  </div>
  <div class="v5-kpi-num {num_cls}" id="{pid}">{val}</div>
  <div class="v5-kpi-lbl">{lbl}</div>
</div>''')
    a('</div>')  # kpi-row
    a('</div>')  # hero

    # ── Page body ─────────────────────────────────────────────────────────
    a('<div class="v5-page-body">')

    # ── LEFT SIDEBAR ──────────────────────────────────────────────────────
    a('<div class="v5-sidebar">')

    trade_title = "Fag" if da else "Trade"
    trade_opts = [
        ("ALL",  "Alle fag" if da else "All Trades",   ""),
        ("EL",   "El" if da else "Electrical",         str(es.get("trade_counts", {}).get("EL", ""))),
        ("VVS",  "VVS",                                str(es.get("trade_counts", {}).get("VVS", ""))),
        ("VENT", "Ventilation",                        str(es.get("trade_counts", {}).get("VENT", ""))),
        ("ARK",  "Arkitektur" if da else "Architecture", str(es.get("trade_counts", {}).get("ARK", ""))),
        ("BYGH", "Byggeri" if da else "Civil Works",   str(es.get("trade_counts", {}).get("BYGH", ""))),
    ]
    a('<div class="v5-filter-group">')
    a(f'<p class="v5-filter-group-title">{trade_title}</p>')
    a('<div class="v5-filter-opts">')
    for code, label, count in trade_opts:
        active_cls = "active" if code == "ALL" else ""
        count_html = f'<span class="v5-filter-count">{count}</span>' if count else ""
        a(f'<div class="v5-filter-opt {active_cls}" data-filter-dim="trade" data-filter-val="{code}" '
          f'onclick="v5SetFilter(\'trade\',\'{code}\')">'
          f'<span class="v5-filter-opt-dot"></span>{label}{count_html}</div>')
    a('</div></div>')

    a('<div class="v5-sidebar-divider"></div>')

    all_lbl = "Alle" if da else "All"
    sidebar_groups = [
        ("area",  "Område" if da else "Area",  fo.get("areas",  [])),
        ("floor", "Etage" if da else "Floor",  fo.get("floors", [])),
        ("phase", "Fase" if da else "Phase",   fo.get("phases", [])),
    ]
    for dim, title, opts in sidebar_groups:
        a(f'<div class="v5-filter-group">')
        a(f'<p class="v5-filter-group-title">{title}</p>')
        a('<div class="v5-filter-opts">')
        a(f'<div class="v5-filter-opt active" data-filter-dim="{dim}" data-filter-val="ALL" '
          f'onclick="v5SetFilter(\'{dim}\',\'ALL\')">'
          f'<span class="v5-filter-opt-dot"></span>{all_lbl}</div>')
        if opts:
            for opt in opts:
                safe_opt = opt.replace("'", "\\'")
                a(f'<div class="v5-filter-opt" data-filter-dim="{dim}" data-filter-val="{opt}" '
                  f'onclick="v5SetFilter(\'{dim}\',\'{safe_opt}\')">'
                  f'<span class="v5-filter-opt-dot"></span>{opt}</div>')
        else:
            no_data = f"Ingen {title.lower()} data" if da else f"No {title.lower()} data"
            a(f'<p class="v5-filter-empty">{no_data}</p>')
        a('</div></div>')
        a('<div class="v5-sidebar-divider"></div>')

    a('</div>')  # sidebar

    # ── MAIN CONTENT ──────────────────────────────────────────────────────
    a('<div class="v5-main">')

    # ── Row 1: Behind | Ahead ─────────────────────────────────────────────
    a('<div class="v5-row-2col">')

    # Behind
    behind_title = f"{'Bagud i planen' if da else 'Behind Schedule'} ({len(behind_items)})"
    behind_sub   = "Faktisk fremskridt under forventet" if da else "Actual progress below expected"
    bh = ["Aktivitet", "Placering", "Forventet", "Faktisk", "Forskel"] if da else ["Activity", "Location", "Expected", "Actual", "Gap"]
    behind_empty = "Ingen aktiviteter bagud i planen ✓" if da else "No activities behind schedule ✓"

    a(f'''<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:linear-gradient(135deg,#f59e0b,#d97706)">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
      </svg>
    </div>
    <div>
      <p class="v5-card-title" id="v5-behind-hdr">{behind_title}</p>
      <p class="v5-card-sub">{behind_sub}</p>
    </div>
  </div>
  <div class="v5-scroll-wrap">
    <table class="v5-table">
      <thead><tr>{''.join(f'<th>{h}</th>' for h in bh)}</tr></thead>
      <tbody id="v5-behind-tbody">''')
    if behind_items:
        for i in behind_items:
            var = _sf(i.get("variance_pct", 0))
            loc = i.get("location", {})
            loc_parts = [p for p in [loc.get("area"), loc.get("floor"), loc.get("phase")] if p]
            loc_html = "".join(f'<span class="v5-loc-badge">{p}</span>' for p in loc_parts)
            a(f'<tr><td class="v5-act-name">{i.get("activity","")}</td>'
              f'<td>{loc_html}</td>'
              f'<td>{_sf(i.get("expected_pct",0)):.0f}%</td>'
              f'<td>{_sf(i.get("actual_pct",0)):.0f}%</td>'
              f'<td class="v5-var-neg">{var:+.0f}%</td></tr>')
    else:
        a(f'<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">{behind_empty}</td></tr>')
    a('      </tbody>\n    </table>\n  </div>\n</div>')

    # Ahead
    ahead_title = f"{'Foran planen' if da else 'Ahead of Schedule'} ({len(ahead_items)})"
    ahead_sub   = "Faktisk fremskridt over forventet" if da else "Actual progress exceeds expected"
    ah = ["Aktivitet", "Placering", "Forventet", "Faktisk", "Forspring"] if da else ["Activity", "Location", "Expected", "Actual", "Lead"]
    ahead_empty = "Ingen aktiviteter foran planen" if da else "No activities ahead of schedule"

    a(f'''<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:linear-gradient(135deg,#10b981,#059669)">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>
      </svg>
    </div>
    <div>
      <p class="v5-card-title" id="v5-ahead-hdr">{ahead_title}</p>
      <p class="v5-card-sub">{ahead_sub}</p>
    </div>
  </div>
  <div class="v5-scroll-wrap">
    <table class="v5-table">
      <thead><tr>{''.join(f'<th>{h}</th>' for h in ah)}</tr></thead>
      <tbody id="v5-ahead-tbody">''')
    if ahead_items:
        for i in ahead_items:
            var = _sf(i.get("variance_pct", 0))
            loc = i.get("location", {})
            loc_parts = [p for p in [loc.get("area"), loc.get("floor"), loc.get("phase")] if p]
            loc_html = "".join(f'<span class="v5-loc-badge">{p}</span>' for p in loc_parts)
            a(f'<tr><td class="v5-act-name">{i.get("activity","")}</td>'
              f'<td>{loc_html}</td>'
              f'<td>{_sf(i.get("expected_pct",0)):.0f}%</td>'
              f'<td>{_sf(i.get("actual_pct",0)):.0f}%</td>'
              f'<td class="v5-var-pos">{var:+.0f}%</td></tr>')
    else:
        a(f'<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">{ahead_empty}</td></tr>')
    a('      </tbody>\n    </table>\n  </div>\n</div>')

    a('</div>')  # row-2col

    # ── Row 2: Critical Activities ─────────────────────────────────────────
    crit_title = (
        f"{'Kritiske aktiviteter — Kræver øjeblikkelig handling' if da else 'Critical Activities — Require Immediate Attention'}"
        f" ({len(all_crit)})"
    )
    crit_sub   = ("Høj risiko + aktiviteter med lukket genopretningsvindue — sorteret efter alvorlighed"
                  if da else "High risk + recovery window closing activities — sorted by severity")
    ch_hdr = ["#", "Aktivitet", "Placering", "Faktisk", "Forskel", "Risiko", "Resterende"] if da else ["#", "Activity", "Location", "Actual", "Gap", "Risk", "Remaining"]
    crit_empty = "Ingen kritiske aktiviteter ✓" if da else "No critical activities ✓"

    a(f'''<div class="v5-card v5-critical-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:linear-gradient(135deg,#dc2626,#b91c1c)">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    </div>
    <div>
      <p class="v5-card-title" id="v5-critical-hdr">{crit_title}</p>
      <p class="v5-card-sub">{crit_sub}</p>
    </div>
  </div>
  <div class="v5-scroll-wrap">
    <table class="v5-table">
      <thead><tr>{''.join(f'<th>{h}</th>' for h in ch_hdr)}</tr></thead>
      <tbody id="v5-critical-tbody">''')
    if all_crit:
        for idx, i in enumerate(all_crit, 1):
            var = _sf(i.get("variance_pct", 0))
            imp_label, imp_cls = _imp_label_py(var, da)
            loc = i.get("location", {})
            loc_parts = [p for p in [loc.get("area"), loc.get("floor"), loc.get("phase")] if p]
            loc_html = "".join(f'<span class="v5-loc-badge">{p}</span>' for p in loc_parts)
            a(f'<tr><td style="color:#94a3b8;font-size:10px">{idx}</td>'
              f'<td class="v5-act-name">{i.get("activity","")}</td>'
              f'<td>{loc_html}</td>'
              f'<td>{_sf(i.get("actual_pct",0)):.0f}%</td>'
              f'<td class="v5-var-neg">{var:+.0f}%</td>'
              f'<td><span class="v5-imp {imp_cls}">{imp_label}</span></td>'
              f'<td style="font-size:10px;color:#64748b">{i.get("remaining_time","—")}</td></tr>')
    else:
        a(f'<tr><td colspan="7" style="text-align:center;color:#64748b;padding:14px">{crit_empty}</td></tr>')
    a('      </tbody>\n    </table>\n  </div>\n</div>')

    # ── Row 3: Critical Path ───────────────────────────────────────────────
    cp_title = f"{'Kritiske sti-aktiviteter' if da else 'Critical Path Activities'} ({len(cp_items)})"
    cp_sub   = ("Nul float — enhver forsinkelse her forsinker direkte projektafslutningen"
                if da else "Zero float — any delay here directly delays project completion")
    cp_hdr   = ["Aktivitet", "Placering", "Faktisk %", "Start", "Slut", "Float"] if da else ["Activity", "Location", "Actual %", "Start", "Finish", "Float"]
    cp_empty = "Ingen data for kritisk sti" if da else "No critical path data available"

    a(f'''<div class="v5-card" style="border-left:3px solid #7c3aed;">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:linear-gradient(135deg,#7c3aed,#6d28d9)">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <path d="M18 20V10M12 20V4M6 20v-6"/><circle cx="18" cy="8" r="2"/><circle cx="12" cy="2" r="2"/><circle cx="6" cy="12" r="2"/>
      </svg>
    </div>
    <div>
      <p class="v5-card-title" id="v5-cp-hdr">{cp_title}</p>
      <p class="v5-card-sub">{cp_sub}</p>
    </div>
  </div>
  <div class="v5-scroll-wrap" style="max-height:220px;">
    <table class="v5-table">
      <thead><tr>{''.join(f'<th>{h}</th>' for h in cp_hdr)}</tr></thead>
      <tbody id="v5-cp-tbody">''')
    if cp_items:
        for i in cp_items:
            pct = _sf(i.get("actual_pct", 0))
            pct_color = "#dc2626" if pct < 25 else "#b45309" if pct < 75 else "#059669"
            loc = i.get("location", {})
            loc_parts = [p for p in [loc.get("area"), loc.get("floor"), loc.get("phase")] if p]
            loc_html = "".join(f'<span class="v5-loc-badge">{p}</span>' for p in loc_parts)
            float_days = i.get("float_days", 0)
            a(f'<tr><td class="v5-act-name">{i.get("activity","")}</td>'
              f'<td>{loc_html}</td>'
              f'<td style="font-weight:700;color:{pct_color}">{pct:.0f}%</td>'
              f'<td style="font-size:10px">{i.get("start_date","")}</td>'
              f'<td style="font-size:10px">{i.get("finish_date","")}</td>'
              f'<td style="font-size:10px;color:#7c3aed;font-weight:700">{float_days}d</td></tr>')
    else:
        a(f'<tr><td colspan="6" style="text-align:center;color:#64748b;padding:12px">{cp_empty}</td></tr>')
    a('      </tbody>\n    </table>\n  </div>\n</div>')

    # ── Row 4: WSID | High Risk of Missing Deadline ────────────────────────
    a('<div class="v5-row-2col">')

    # What Should I Do
    wsid_title        = "Hvad skal jeg gøre?" if da else "What Should I Do?"
    wsid_sub          = "AI-anbefalet prioriteret handling" if da else "AI-recommended priority action"
    wsid_most_crit    = "Mest kritisk aktivitet" if da else "Most Critical Activity"
    wsid_empty        = "Ingen kritiske handlinger kræves ✓" if da else "No critical actions required ✓"

    top_rec = action_recs[0] if action_recs else {}
    top_act = top_rec.get("activity", "")
    top_pi  = next((i for i in progress_items if i.get("activity") == top_act), {})
    top_pct = _sf(top_pi.get("actual_pct", 0))
    top_var = _sf(top_pi.get("variance_pct", -50))
    wsid_imp_label, wsid_imp_cls = _imp_label_py(top_var, da)

    r_donut  = 38
    r_circum = 2 * math.pi * r_donut
    r_filled = r_circum * max(0, min(100, top_pct)) / 100
    r_gap    = r_circum - r_filled
    r_sz     = (r_donut + 18) * 2
    r_cx     = r_cy = r_sz // 2
    r_color  = "#ef4444" if top_pct < 50 else "#f59e0b" if top_pct < 75 else "#10b981"
    actual_lbl = "FAKTISK" if da else "ACTUAL"

    a(f'''<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:linear-gradient(135deg,#2563eb,#1d4ed8)">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/>
      </svg>
    </div>
    <div>
      <p class="v5-card-title">{wsid_title}</p>
      <p class="v5-card-sub">{wsid_sub}</p>
    </div>
  </div>
  <div id="v5-wsid-body">''')
    if action_recs:
        a(f'<div class="v5-wsid-tag">{wsid_most_crit} '
          f'<span class="v5-imp {wsid_imp_cls}" style="margin-left:5px">{wsid_imp_label}</span></div>')
        a(f'<div class="v5-wsid-activity">{top_act}</div>')
        a(f'<div class="v5-wsid-issue">{top_rec.get("issue","")}</div>')
        a('<div class="v5-wsid-inner">')
        a(f'<div class="v5-donut-wrap"><svg width="{r_sz}" height="{r_sz}" viewBox="0 0 {r_sz} {r_sz}">'
          f'<circle cx="{r_cx}" cy="{r_cy}" r="{r_donut}" fill="none" stroke="#f1f5f9" stroke-width="11"/>'
          f'<circle cx="{r_cx}" cy="{r_cy}" r="{r_donut}" fill="none" stroke="{r_color}" stroke-width="11" '
          f'stroke-dasharray="{r_filled:.1f} {r_gap:.1f}" stroke-linecap="round" '
          f'transform="rotate(-90 {r_cx} {r_cy})"/>'
          f'<text x="{r_cx}" y="{r_cy}" text-anchor="middle" dominant-baseline="central" '
          f'font-size="18" font-weight="900" fill="#0f172a">{top_pct:.0f}%</text>'
          f'<text x="{r_cx}" y="{r_cy+15}" text-anchor="middle" font-size="9" fill="#64748b" font-weight="600">{actual_lbl}</text>'
          f'</svg></div>')
        a('<ul class="v5-actions-list">')
        for act in (top_rec.get("actions", []))[:6]:
            a(f'<li><div class="v5-action-check">'
              f'<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">'
              f'<polyline points="20 6 9 17 4 12"/></svg></div>{act}</li>')
        a('</ul></div>')
    else:
        a(f'<div style="padding:16px 0;color:#64748b;font-size:12px;text-align:center">{wsid_empty}</div>')
    a('  </div>\n</div>')

    # High Risk of Missing Deadline (PONR)
    ponr_title       = "Høj risiko for at misse deadline" if da else "High Risk of Missing Deadline"
    ponr_sub         = "Vurdering af genopretningsvindue pr. aktivitet" if da else "Recovery window assessment per activity"
    ponr_red_title   = "Genopretning ikke længere mulig" if da else "Recovery No Longer Possible"
    ponr_red_empty   = "Ingen aktiviteter ved point of no return ✓" if da else "No activities at point of no return ✓"
    ponr_amber_title = "Genopretningsvindue lukker" if da else "Recovery Window Closing"
    ponr_amber_empty = "Ingen aktiviteter i genopretningsvinduet" if da else "No activities in recovery window"

    a(f'''<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:linear-gradient(135deg,#7c3aed,#6d28d9)">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
      </svg>
    </div>
    <div>
      <p class="v5-card-title">{ponr_title}</p>
      <p class="v5-card-sub">{ponr_sub}</p>
    </div>
  </div>

  <div class="v5-ponr-section">
    <div class="v5-ponr-section-title" style="color:#dc2626">
      <span class="v5-dot v5-dot-red"></span>
      {ponr_red_title}
      <span id="v5-ponr-red-count" style="margin-left:auto;font-size:11px;font-weight:700">{len(red_ponr)}</span>
    </div>
    <ul class="v5-ponr-list" id="v5-ponr-red-list">''')
    if red_ponr:
        for idx, i in enumerate(red_ponr[:6], 1):
            a(f'<li class="v5-ponr-item">'
              f'<div class="v5-ponr-num v5-ponr-num-red">{idx}</div>'
              f'<div><div class="v5-ponr-name">{i.get("activity","")}</div>'
              f'<div class="v5-ponr-rec">{i.get("recommendation") or i.get("remaining_time","")}</div>'
              f'</div></li>')
    else:
        a(f'<li style="color:#64748b;font-size:11px;list-style:none;padding:4px 0">{ponr_red_empty}</li>')
    a(f'''    </ul>
  </div>

  <div class="v5-ponr-section">
    <div class="v5-ponr-section-title" style="color:#b45309">
      <span class="v5-dot v5-dot-amber"></span>
      {ponr_amber_title}
      <span id="v5-ponr-amber-count" style="margin-left:auto;font-size:11px;font-weight:700">{len(yellow_ponr)}</span>
    </div>
    <ul class="v5-ponr-list" id="v5-ponr-amber-list">''')
    if yellow_ponr:
        for idx, i in enumerate(yellow_ponr[:6], 1):
            a(f'<li class="v5-ponr-item">'
              f'<div class="v5-ponr-num v5-ponr-num-amber">{idx}</div>'
              f'<div><div class="v5-ponr-name">{i.get("activity","")}</div>'
              f'<div class="v5-ponr-rec">{i.get("recommendation") or i.get("remaining_time","")}</div>'
              f'</div></li>')
    else:
        a(f'<li style="color:#64748b;font-size:11px;list-style:none;padding:4px 0">{ponr_amber_empty}</li>')
    a('    </ul>\n  </div>\n</div>')

    a('</div>')  # row-2col

    # ── Row 5: Schedule Comparison ─────────────────────────────────────────
    sc_title      = "Tidsplansammenligning — Ændringer mellem tidsplaner" if da else "Schedule Comparison — Changes Between Schedules"
    added_lbl     = "Tilføjet" if da else "Added"
    removed_lbl   = "Fjernet" if da else "Removed"
    date_chg_lbl  = "Datoændringer" if da else "Date Changes"
    dur_chg_lbl   = "Varighed ændringer" if da else "Duration Changes"
    added_act_lbl = "Tilføjede aktiviteter" if da else "Added Activities"
    rem_act_lbl   = "Fjernede aktiviteter" if da else "Removed Activities"
    none_lbl      = "Ingen" if da else "None"
    changed_lbl   = "Ændrede aktiviteter" if da else "Changed Activities"
    sc_hdr        = ["Aktivitet", "Ændring", "Før", "Efter"] if da else ["Activity", "Change", "Before", "After"]
    no_chg_lbl    = "Ingen tidsplanændringer fundet" if da else "No schedule changes found"

    a(f'''<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:linear-gradient(135deg,#0ea5e9,#0284c7)">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <path d="M16 3h5v5M4 20L21 3M21 16v5h-5M4 4l5 5"/>
      </svg>
    </div>
    <div>
      <p class="v5-card-title">{sc_title}</p>
      <p class="v5-card-sub">{period_old} → {period_new}</p>
    </div>
  </div>

  <div class="v5-change-kpis">
    <div class="v5-change-kpi">
      <div class="v5-change-kpi-num c-green" id="v5-chg-add">{len(added_list)}</div>
      <div class="v5-change-kpi-lbl">{added_lbl}</div>
    </div>
    <div class="v5-change-kpi">
      <div class="v5-change-kpi-num c-red" id="v5-chg-rem">{len(removed_list)}</div>
      <div class="v5-change-kpi-lbl">{removed_lbl}</div>
    </div>
    <div class="v5-change-kpi">
      <div class="v5-change-kpi-num c-blue" id="v5-chg-date">{date_changes}</div>
      <div class="v5-change-kpi-lbl">{date_chg_lbl}</div>
    </div>
    <div class="v5-change-kpi">
      <div class="v5-change-kpi-num" style="color:#7c3aed" id="v5-chg-dur">{dur_changes}</div>
      <div class="v5-change-kpi-lbl">{dur_chg_lbl}</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">
    <div>
      <p class="v5-change-section-lbl">+ {added_act_lbl} ({len(added_list)})</p>
      <div class="v5-scroll-wrap" style="max-height:140px;">
        <table class="v5-table"><tbody id="v5-added-tbody">''')
    if added_list:
        for act in added_list:
            a(f'<tr><td style="font-size:11px;padding:4px 8px;color:#0f172a">{act}</td></tr>')
    else:
        a(f'<tr><td style="color:#64748b;font-size:11px;padding:8px">{none_lbl}</td></tr>')
    a(f'''        </tbody></table>
      </div>
    </div>
    <div>
      <p class="v5-change-section-lbl">− {rem_act_lbl} ({len(removed_list)})</p>
      <div class="v5-scroll-wrap" style="max-height:140px;">
        <table class="v5-table"><tbody id="v5-removed-tbody">''')
    if removed_list:
        for act in removed_list:
            a(f'<tr><td style="font-size:11px;padding:4px 8px;color:#dc2626">{act}</td></tr>')
    else:
        a(f'<tr><td style="color:#64748b;font-size:11px;padding:8px">{none_lbl}</td></tr>')
    a(f'''        </tbody></table>
      </div>
    </div>
  </div>

  <p class="v5-change-section-lbl">~ {changed_lbl} ({len(flat_changes)})</p>
  <div class="v5-scroll-wrap" style="max-height:200px;">
    <table class="v5-table">
      <thead><tr>{''.join(f'<th>{h}</th>' for h in sc_hdr)}</tr></thead>
      <tbody id="v5-changes-tbody">''')
    if flat_changes:
        for c in flat_changes:
            ct = str(c.get("change_type", ""))
            color = "#2563eb" if "date" in ct.lower() else "#7c3aed" if "dur" in ct.lower() else "#0f172a"
            a(f'<tr><td class="v5-act-name">{c.get("activity","")}</td>'
              f'<td style="font-size:10px;font-weight:700;color:{color}">{ct}</td>'
              f'<td style="font-size:11px;color:#64748b">{c.get("old","")}</td>'
              f'<td style="font-size:11px;font-weight:600">{c.get("new","")}</td></tr>')
    else:
        a(f'<tr><td colspan="4" style="text-align:center;color:#64748b;padding:12px">{no_chg_lbl}</td></tr>')
    a('      </tbody>\n    </table>\n  </div>\n</div>')

    # ── Row 6: Summary & Notes | Delay Drivers ────────────────────────────
    a('<div class="v5-row-2col">')

    # Summary
    summary_title = "Oversigt &amp; noter" if da else "Summary &amp; Notes"
    summary_sub   = "Oversigt over rapporteringsperiode" if da else "Reporting period overview"
    scope_delta        = added_n - removed_n
    delta_progress_sign = "+" if delta > 0 else ""
    delta_scope_sign    = "+" if scope_delta > 0 else ""
    added_word   = "tilføjet" if da else "added"
    removed_word = "fjernet" if da else "removed"

    a(f'''<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:linear-gradient(135deg,#0f172a,#334155)">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
        <polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>
      </svg>
    </div>
    <div>
      <p class="v5-card-title">{summary_title}</p>
      <p class="v5-card-sub">{summary_sub}</p>
    </div>
  </div>''')

    summary_rows = [
        ("Samlet fremskridt" if da else "Overall Progress",
         f"{old_pct:.1f}% → {new_pct:.1f}%",
         f"{delta_progress_sign}{delta:.1f} pp",
         "pos" if delta >= 0 else "neg"),
        ("Afsluttede aktiviteter" if da else "Finished Activities",
         str(finished_n), "", "neu"),
        ("Forsinkede aktiviteter" if da else "Delayed Activities",
         str(delayed_n), "", "neg" if delayed_n > 0 else "neu"),
        ("Samlede aktiviteter" if da else "Total Activities",
         str(total_n), "", "neu"),
        ("Omfangsændring" if da else "Scope Change",
         f"+{added_n} {added_word} / −{removed_n} {removed_word}",
         f"{delta_scope_sign}{scope_delta}",
         "pos" if scope_delta >= 0 else "neg"),
        ("Rapporteringsperiode" if da else "Reporting Period",
         f"{period_old} → {period_new}", "", "neu"),
    ]
    for lbl, val, d, dcls in summary_rows:
        delta_span = f'<span class="v5-summary-delta {dcls}">{d}</span>' if d else ""
        a(f'<div class="v5-summary-row"><span class="v5-summary-lbl">{lbl}</span>'
          f'<span class="v5-summary-val">{val} {delta_span}</span></div>')
    a('</div>')

    # Delay Drivers
    drivers_title = "Forsinkelsesdrivere" if da else "Delay Drivers"
    drivers_sub   = "Årsager til tidsplanforsinkelser" if da else "Root causes of schedule delays"
    affects_tmpl  = "Påvirker ~{} aktiviteter" if da else "Affects ~{} activities"
    no_drivers    = "Ingen data for forsinkelsesdrivere" if da else "No delay driver data available"

    a(f'''<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:linear-gradient(135deg,#ef4444,#dc2626)">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
      </svg>
    </div>
    <div>
      <p class="v5-card-title">{drivers_title}</p>
      <p class="v5-card-sub">{drivers_sub}</p>
    </div>
  </div>''')
    if drivers:
        for d in drivers:
            a(f'<div class="v5-driver-item">'
              f'<div class="v5-driver-name">{d.get("driver","")}</div>'
              f'<div class="v5-driver-desc">{d.get("description","")}</div>'
              f'<div class="v5-driver-count">{affects_tmpl.format(d.get("affected_count",0))}</div>'
              f'</div>')
    else:
        a(f'<p style="color:#64748b;font-size:12px;padding:8px 0">{no_drivers}</p>')
    a('</div>')

    a('</div>')  # row-2col
    a('</div>')  # main
    a('</div>')  # page-body
    a(f'<script>{_JS}</script>')
    a('</div>')  # v5

    return "\n".join(parts)
