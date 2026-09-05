"""
html_formatter_v4.py
====================
Renders the v3 JSON as a "Project Health Dashboard" with client-side
trade filter. The full JSON is embedded in the HTML; clicking a trade
pill filters all sections in real time — no server round-trip.

Input:  data dict produced by compare_v3_agent.analyze()["json"]
Output: self-contained HTML string (style + content + JS)
"""

from __future__ import annotations
import json as _json
import math
from datetime import date as _date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(str(val).replace("%", "").strip())
    except (ValueError, TypeError):
        return default


def _variance_impact(variance_pct: float) -> tuple[str, str]:
    if variance_pct <= -50:
        return "CRITICAL", "v4-imp-critical"
    if variance_pct <= -20:
        return "HIGH RISK", "v4-imp-high"
    return "RISK", "v4-imp-risk"


def _health_meta(health: str) -> tuple[str, str, str]:
    h = health.lower()
    if h == "red":
        return "v4-status-red", "v4-dot-red", "Immediate action required — without changes, project will be delayed"
    if h == "yellow":
        return "v4-status-yellow", "v4-dot-yellow", "Some activities are at risk — close monitoring required"
    return "v4-status-green", "v4-dot-green", "Project is on track — continue monitoring"


def _health_label(health: str) -> str:
    return {"red": "HIGH RISK", "yellow": "AT RISK"}.get(health.lower(), "ON TRACK")


def _donut_svg(actual_pct: float, radius: int = 34) -> str:
    circumference = 2 * math.pi * radius
    filled = circumference * max(0.0, min(100.0, actual_pct)) / 100.0
    gap = circumference - filled
    size = (radius + 20) * 2
    cx = cy = size // 2
    color = "#ef4444" if actual_pct < 50 else "#f59e0b" if actual_pct < 75 else "#10b981"
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#f1f5f9" stroke-width="12"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="{color}" stroke-width="12" '
        f'stroke-dasharray="{filled:.1f} {gap:.1f}" stroke-linecap="round" '
        f'transform="rotate(-90 {cx} {cy})"/>'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="central" '
        f'font-size="20" font-weight="800" fill="#0f172a">{actual_pct:.0f}%</text>'
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" font-size="10" '
        f'fill="#64748b" font-weight="600">ACTUAL</text>'
        f'</svg>'
    )


def _chart_svg(progress_items: list[dict]) -> str:
    W, H = 380, 160
    PL, PR, PT, PB = 36, 16, 16, 28
    cw, ch = W - PL - PR, H - PT - PB
    if not progress_items:
        return (f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
                f'<text x="{W//2}" y="{H//2}" text-anchor="middle" font-size="13" fill="#94a3b8">No progress data</text>'
                f'</svg>')
    items = sorted(progress_items, key=lambda i: _safe_float(i.get("expected_pct", 0)))
    n = len(items)
    x = lambda i: PL + (i / max(n - 1, 1)) * cw
    y = lambda p: PT + ch - (_safe_float(p) / 100.0) * ch
    planned = " ".join(f"{x(i):.1f},{y(it.get('expected_pct', 0)):.1f}" for i, it in enumerate(items))
    actual  = " ".join(f"{x(i):.1f},{y(it.get('actual_pct', 0)):.1f}"   for i, it in enumerate(items))
    y_grids  = "".join(f'<line x1="{PL}" y1="{y(p):.1f}" x2="{PL+cw}" y2="{y(p):.1f}" stroke="#f1f5f9" stroke-width="1"/>' for p in [25, 50, 75, 100])
    y_labels = "".join(f'<text x="{PL-6}" y="{y(p):.1f}" text-anchor="end" font-size="9" fill="#94a3b8" dominant-baseline="central">{p}%</text>' for p in [0, 25, 50, 75, 100])
    return (
        f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" style="overflow:visible">'
        f'<rect x="{PL}" y="{PT}" width="{cw}" height="{y(90)-PT:.1f}" fill="rgba(16,185,129,0.06)"/>'
        f'<rect x="{PL}" y="{y(90):.1f}" width="{cw}" height="{y(70)-y(90):.1f}" fill="rgba(245,158,11,0.06)"/>'
        f'<rect x="{PL}" y="{y(70):.1f}" width="{cw}" height="{y(0)-y(70):.1f}" fill="rgba(239,68,68,0.06)"/>'
        f'{y_grids}{y_labels}'
        f'<polyline points="{planned}" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,3"/>'
        f'<polyline points="{actual}" fill="none" stroke="#0ea5e9" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<line x1="{PL}" y1="{H-8}" x2="{PL+20}" y2="{H-8}" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,3"/>'
        f'<text x="{PL+24}" y="{H-4}" font-size="9" fill="#64748b">Planned</text>'
        f'<line x1="{PL+80}" y1="{H-8}" x2="{PL+100}" y2="{H-8}" stroke="#0ea5e9" stroke-width="2.5"/>'
        f'<text x="{PL+104}" y="{H-4}" font-size="9" fill="#64748b">Actual</text>'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
*{box-sizing:border-box;}
.v4{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;color:#0f172a;line-height:1.4;-webkit-font-smoothing:antialiased;}
/* Header — clean white strip */
.v4-header{background:#fff;padding:10px 24px 10px;display:flex;align-items:center;gap:12px;margin-bottom:12px;border-bottom:1px solid #e2e8f0;}
.v4-brand-logo{width:30px;height:30px;background:linear-gradient(135deg,#00D6D6,#38bdf8);border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.v4-header-titles{display:flex;flex-direction:column;}
.v4-header-super{font-size:9px;font-weight:700;letter-spacing:2px;color:#2563eb;text-transform:uppercase;margin:0;line-height:1;}
.v4-header-title{font-size:20px;font-weight:900;letter-spacing:-0.5px;color:#0f172a;margin:0;line-height:1.1;}
.v4-header-sub{font-size:11px;color:#94a3b8;margin-top:1px;}
/* Body */
.v4-body{padding:0 16px 12px;}
.v4-section-label{font-size:9px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#94a3b8;margin:0 0 6px 0;}
/* KPI strip */
.v4-kpi-strip{display:flex;align-items:stretch;gap:8px;margin-bottom:10px;flex-wrap:wrap;}
.v4-status-block{background:#fff;border-radius:10px;padding:12px 16px;box-shadow:0 1px 4px rgba(0,0,0,0.06);min-width:170px;flex-shrink:0;display:flex;flex-direction:column;justify-content:center;}
.v4-status-badge{display:inline-flex;align-items:center;gap:8px;padding:7px 14px;border-radius:40px;font-size:17px;font-weight:900;letter-spacing:0.3px;margin-bottom:5px;transition:all .2s;}
.v4-status-red{background:rgba(239,68,68,0.1);color:#dc2626;border:2px solid rgba(239,68,68,0.25);}
.v4-status-yellow{background:rgba(245,158,11,0.1);color:#b45309;border:2px solid rgba(245,158,11,0.25);}
.v4-status-green{background:rgba(16,185,129,0.1);color:#059669;border:2px solid rgba(16,185,129,0.25);}
.v4-status-sub{font-size:10px;color:#64748b;line-height:1.3;transition:all .2s;}
.v4-metric-pills{flex:1;display:flex;gap:8px;flex-wrap:wrap;}
.v4-metric-pill{flex:1;min-width:90px;background:#fff;border-radius:10px;padding:10px 12px;box-shadow:0 1px 4px rgba(0,0,0,0.06);display:flex;flex-direction:column;}
.v4-pill-icon{width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;margin-bottom:6px;flex-shrink:0;}
.v4-pill-num{font-size:24px;font-weight:900;line-height:1;color:#0f172a;transition:all .25s;}
.v4-pill-num.red{color:#dc2626;} .v4-pill-num.green{color:#059669;} .v4-pill-num.amber{color:#b45309;} .v4-pill-num.blue{color:#2563eb;}
.v4-pill-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;color:#475569;margin-top:3px;}
.v4-pill-sub{font-size:9px;color:#94a3b8;margin-top:1px;transition:all .25s;}
.v4-dot{display:inline-block;width:7px;height:7px;border-radius:50%;flex-shrink:0;}
.v4-dot-red{background:#ef4444;} .v4-dot-yellow{background:#f59e0b;} .v4-dot-green{background:#10b981;}
/* Cards */
.v4-card{background:#fff;border-radius:10px;padding:12px 14px;box-shadow:0 1px 4px rgba(0,0,0,0.06);height:100%;box-sizing:border-box;}
.v4-card-header{display:flex;align-items:center;gap:8px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #f1f5f9;}
.v4-card-icon{width:26px;height:26px;border-radius:7px;display:flex;align-items:center;justify-content:center;color:#fff;flex-shrink:0;}
.v4-card-hd{font-size:11px;font-weight:800;color:#0f172a;margin:0;letter-spacing:0.2px;}
.v4-card-sub{font-size:9px;color:#94a3b8;margin-top:1px;}
/* Grids */
.v4-grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:10px;}
@media(max-width:1100px){.v4-grid-3{grid-template-columns:1fr 1fr;}.v4-grid-3>*:last-child{grid-column:1/-1;}}
/* Tables */
.v4-table-wrap{overflow-x:auto;border-radius:8px;border:1px solid #f1f5f9;}
.v4-table{width:100%;border-collapse:separate;border-spacing:0;font-size:11.5px;}
.v4-table th{background:#f8fafc;font-weight:700;color:#475569;text-transform:uppercase;font-size:9px;letter-spacing:0.4px;padding:6px 10px;border-bottom:1px solid #e2e8f0;text-align:left;}
.v4-table td{padding:6px 10px;border-bottom:1px solid #f8fafc;color:#334155;}
.v4-table tbody tr:last-child td{border-bottom:none;}
.v4-table tbody tr:hover{background:#fafafa;}
.v4-table .rank{font-weight:800;color:#94a3b8;font-size:11px;min-width:18px;}
.v4-table .act-name{font-weight:600;color:#0f172a;}
.v4-table .deviation{font-weight:700;color:#dc2626;}
/* Impact badges */
.v4-imp{display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:5px;font-size:9px;font-weight:700;letter-spacing:0.3px;white-space:nowrap;}
.v4-imp-critical{background:rgba(239,68,68,0.12);color:#b91c1c;border:1px solid rgba(239,68,68,0.25);}
.v4-imp-high{background:rgba(245,158,11,0.12);color:#92400e;border:1px solid rgba(245,158,11,0.25);}
.v4-imp-risk{background:rgba(245,158,11,0.08);color:#b45309;border:1px solid rgba(245,158,11,0.2);}
/* Badges */
.v4-badge{display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:5px;font-size:10px;font-weight:600;border:1px solid transparent;}
.b-red{background:rgba(239,68,68,0.1);color:#dc2626;border-color:rgba(239,68,68,0.2);}
.b-green{background:rgba(16,185,129,0.1);color:#059669;border-color:rgba(16,185,129,0.2);}
.var-neg{color:#dc2626;font-weight:700;} .var-pos{color:#059669;font-weight:700;}
/* PONR */
.v4-ponr-count{font-size:32px;font-weight:900;color:#dc2626;line-height:1;margin-bottom:1px;transition:all .25s;display:inline;}
.v4-ponr-count-lbl{font-size:10px;color:#64748b;margin-bottom:8px;}
.v4-ponr-list{list-style:none;padding:0;margin:0 0 8px 0;}
.v4-ponr-list li{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid #f1f5f9;font-size:11.5px;}
.v4-ponr-list li:last-child{border-bottom:none;}
.v4-ponr-num{width:16px;height:16px;border-radius:50%;background:#fecaca;color:#dc2626;font-size:9px;font-weight:800;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.v4-ponr-name{font-weight:600;color:#0f172a;flex:1;font-size:11px;}
.v4-delay-box{background:linear-gradient(135deg,#fef2f2,#fff);border:1px solid #fecaca;border-radius:8px;padding:8px 12px;display:flex;align-items:center;gap:10px;}
.v4-delay-num{font-size:28px;font-weight:900;color:#dc2626;line-height:1;}
.v4-delay-lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#b91c1c;}
/* What Should I Do */
.v4-wsid-tag{font-size:9px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:#64748b;margin-bottom:4px;}
.v4-wsid-activity{font-size:13px;font-weight:800;color:#0f172a;margin-bottom:2px;line-height:1.2;}
.v4-wsid-problem{font-size:11px;color:#64748b;margin-bottom:8px;}
.v4-wsid-body-inner{display:flex;gap:12px;align-items:flex-start;}
.v4-donut-wrap{flex-shrink:0;}
.v4-actions-list{list-style:none;padding:0;margin:0;flex:1;}
.v4-actions-list li{display:flex;align-items:flex-start;gap:6px;font-size:11px;color:#334155;padding:3px 0;border-bottom:1px solid #f8fafc;}
.v4-actions-list li:last-child{border-bottom:none;}
.v4-action-check{width:13px;height:13px;border-radius:50%;background:rgba(16,185,129,0.12);color:#059669;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;}
/* Trade Filter */
.v4-scope-pills{display:flex;flex-direction:column;gap:4px;}
.v4-scope-pill{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:7px;background:#f8fafc;border:1px solid #e2e8f0;font-size:11.5px;font-weight:600;color:#334155;cursor:pointer;transition:all .15s;user-select:none;}
.v4-scope-pill:hover{background:#f1f5f9;border-color:#cbd5e1;}
.v4-scope-pill.active{background:rgba(37,99,235,0.08);border-color:rgba(37,99,235,0.25);color:#1d4ed8;}
.v4-check{width:14px;height:14px;border-radius:3px;border:2px solid #e2e8f0;flex-shrink:0;display:flex;align-items:center;justify-content:center;transition:all .15s;}
.v4-check.checked{background:#2563eb;border-color:#2563eb;}
/* Change KPIs */
.v4-change-kpi-row{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;}
.v4-change-kpi{flex:1;min-width:60px;text-align:center;padding:6px 4px;border-radius:7px;background:#f8fafc;border:1px solid #e2e8f0;}
.v4-change-kpi-num{font-size:18px;font-weight:900;line-height:1;transition:all .25s;}
.v4-change-kpi-num.add{color:#059669;} .v4-change-kpi-num.rem{color:#dc2626;} .v4-change-kpi-num.chg{color:#2563eb;} .v4-change-kpi-num.dur{color:#7c3aed;}
.v4-change-kpi-lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px;color:#64748b;margin-top:2px;}
.v4-table-group-lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;color:#64748b;margin:8px 0 4px 0;transition:all .25s;}
/* Chart */
.v4-chart-wrap{display:flex;justify-content:center;overflow:hidden;}
.v4-band-label{display:flex;justify-content:flex-end;gap:6px;margin-bottom:3px;}
.v4-band-tag{font-size:9px;font-weight:700;letter-spacing:0.3px;padding:1px 6px;border-radius:3px;}
.v4-band-tag.on{background:rgba(16,185,129,0.1);color:#059669;}
.v4-band-tag.risk{background:rgba(245,158,11,0.1);color:#b45309;}
.v4-band-tag.beh{background:rgba(239,68,68,0.1);color:#dc2626;}
.v4-projected-delay{display:flex;align-items:center;gap:6px;font-size:10px;color:#64748b;margin-top:6px;}
.v4-projected-delay strong{color:#dc2626;}
/* AI Insights */
.v4-insights-section{margin-top:4px;}
.v4-insights-strip{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;}
@media(max-width:1000px){.v4-insights-strip{grid-template-columns:repeat(3,1fr);}}
.v4-insight-card{background:#fff;border-radius:10px;padding:10px 12px;box-shadow:0 1px 4px rgba(0,0,0,0.06);display:flex;flex-direction:column;gap:5px;}
.v4-insight-icon{width:26px;height:26px;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.v4-insight-label{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#64748b;}
.v4-insight-value{font-size:11px;font-weight:600;color:#0f172a;line-height:1.3;transition:all .25s;}
.v4-insight-action{font-size:10px;color:#2563eb;font-weight:600;cursor:pointer;}
"""

# ---------------------------------------------------------------------------
# JavaScript — client-side trade filter engine
# ---------------------------------------------------------------------------

_JS = r"""
(function() {
  var D = window.__v4Data;
  if (!D) return;

  var PREFIXES = {
    'EL':   ['EL -','EL-'],
    'VVS':  ['VVS -','VVS-'],
    'VENT': ['VENT -','VENT-'],
    'ARK':  ['ARK -','ARK-'],
    'BYGH': ['BYGH -','BYGH-']
  };
  var activeTrade = 'ALL';

  function inTrade(name, code) {
    if (code === 'ALL' || !PREFIXES[code]) return true;
    var u = (name || '').toUpperCase();
    return PREFIXES[code].some(function(p) { return u.indexOf(p.toUpperCase()) === 0; });
  }
  function filterObj(arr, code) {
    return (arr || []).filter(function(i) { return inTrade(i.activity || '', code); });
  }
  function filterStr(arr, code) {
    return (arr || []).filter(function(s) { return inTrade(s, code); });
  }
  function el(id) { return document.getElementById(id); }
  function safeFloat(v) { return parseFloat(('' + v).replace('%','').trim()) || 0; }

  function impactLabel(v) {
    if (v <= -50) return ['CRITICAL','v4-imp-critical'];
    if (v <= -20) return ['HIGH RISK','v4-imp-high'];
    return ['RISK','v4-imp-risk'];
  }

  function computeHealth(behindCt, ponrCt) {
    if (ponrCt > 0 && behindCt > 0) return 'Red';
    if (behindCt > 0) return 'Yellow';
    return 'Green';
  }

  function renderStatus(health) {
    var wrap = el('v4-status-badge-wrap');
    if (!wrap) return;
    var cfg = {
      'Red':    {cls:'v4-status-red',   dot:'v4-dot-red',   label:'HIGH RISK', sub:'Immediate action required — without changes, project will be delayed'},
      'Yellow': {cls:'v4-status-yellow',dot:'v4-dot-yellow',label:'AT RISK',   sub:'Some activities are at risk — close monitoring required'},
      'Green':  {cls:'v4-status-green', dot:'v4-dot-green', label:'ON TRACK',  sub:'Project is on track — continue monitoring'}
    };
    var c = cfg[health] || cfg['Green'];
    var badge = wrap.querySelector('.v4-status-badge');
    if (badge) badge.className = 'v4-status-badge ' + c.cls;
    var dot = wrap.querySelector('.v4-status-dot');
    if (dot) dot.className = 'v4-dot ' + c.dot;
    var lbl = el('v4-status-label');
    if (lbl) lbl.textContent = c.label;
    var sub = el('v4-status-sub-text');
    if (sub) sub.textContent = c.sub;
  }

  function renderTop5(progress) {
    var tbody = el('v4-top5-tbody');
    if (!tbody) return;
    var sorted = progress.slice().sort(function(a,b){ return safeFloat(a.variance_pct) - safeFloat(b.variance_pct); }).slice(0,5);
    if (!sorted.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#64748b;padding:16px">No delayed activities for this trade ✓</td></tr>';
      return;
    }
    tbody.innerHTML = sorted.map(function(item, i) {
      var v = safeFloat(item.variance_pct);
      var imp = impactLabel(v);
      var vStr = (v >= 0 ? '+' : '') + v.toFixed(0) + '%';
      return '<tr><td class="rank">' + (i+1) + '</td>' +
        '<td class="act-name">' + (item.activity||'') + '</td>' +
        '<td class="deviation">' + vStr + '</td>' +
        '<td><span class="v4-imp ' + imp[1] + '">' + imp[0] + '</span></td></tr>';
    }).join('');
  }

  function renderPONR(items) {
    var numEl  = el('v4-ponr-count-num');
    var listEl = el('v4-ponr-list-ol');
    var delayEl= el('v4-delay-box-wrap');
    if (numEl) numEl.textContent = items.length;
    if (listEl) {
      if (!items.length) {
        listEl.innerHTML = '<li style="color:#64748b;font-size:13px;padding:8px 0;border:none;list-style:none">No activities at point of no return ✓</li>';
      } else {
        listEl.innerHTML = items.slice(0,5).map(function(item, i) {
          var cls = (item.classification||'').toLowerCase() === 'red' ? 'v4-dot-red' : 'v4-dot-yellow';
          return '<li><div class="v4-ponr-num">' + (i+1) + '</div>' +
            '<span class="v4-ponr-name">' + (item.activity||'') + '</span>' +
            '<span class="v4-dot ' + cls + '"></span></li>';
        }).join('');
      }
    }
    if (delayEl) delayEl.style.display = items.length ? '' : 'none';
  }

  function donutSVG(pct) {
    var r = 44, c = 2 * Math.PI * r;
    var filled = c * Math.min(100, Math.max(0, pct)) / 100;
    var gap = c - filled;
    var sz = (r + 20) * 2, cx = sz / 2, cy = sz / 2;
    var color = pct < 50 ? '#ef4444' : pct < 75 ? '#f59e0b' : '#10b981';
    return '<div class="v4-donut-wrap"><svg width="'+sz+'" height="'+sz+'" viewBox="0 0 '+sz+' '+sz+'">' +
      '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="#f1f5f9" stroke-width="12"/>' +
      '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="'+color+'" stroke-width="12" ' +
      'stroke-dasharray="'+filled.toFixed(1)+' '+gap.toFixed(1)+'" stroke-linecap="round" ' +
      'transform="rotate(-90 '+cx+' '+cy+')"/>' +
      '<text x="'+cx+'" y="'+cy+'" text-anchor="middle" dominant-baseline="central" font-size="20" font-weight="800" fill="#0f172a">'+Math.round(pct)+'%</text>' +
      '<text x="'+cx+'" y="'+(cy+18)+'" text-anchor="middle" font-size="10" fill="#64748b" font-weight="600">ACTUAL</text>' +
      '</svg></div>';
  }

  function renderWhatToDo(recs, progress) {
    var sec = el('v4-wsid-body');
    if (!sec) return;
    if (!recs.length) {
      sec.innerHTML = '<div style="padding:20px 0;color:#64748b;font-size:13px;text-align:center">No critical actions required ✓</div>';
      return;
    }
    var top = recs[0];
    var name = top.activity || '';
    var issue = top.issue || '';
    var actions = top.actions || [];
    var pi = progress.filter(function(p){ return p.activity === name; })[0];
    var pct = pi ? safeFloat(pi.actual_pct) : 0;
    var v = pi ? safeFloat(pi.variance_pct) : -50;
    var imp = impactLabel(v);
    sec.innerHTML =
      '<div class="v4-wsid-tag">Most Critical Activity <span class="v4-imp '+imp[1]+'" style="margin-left:6px">'+imp[0]+'</span></div>' +
      '<div class="v4-wsid-activity">'+name+'</div>' +
      '<div class="v4-wsid-problem">'+issue+'</div>' +
      '<div class="v4-wsid-body-inner">' +
      donutSVG(pct) +
      '<ul class="v4-actions-list">' +
      actions.slice(0,6).map(function(a) {
        return '<li><div class="v4-action-check"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></div>'+a+'</li>';
      }).join('') +
      '</ul></div>';
  }

  function renderSchedule(behind, ahead) {
    var blbl = el('v4-behind-lbl');
    var bt   = el('v4-behind-tbody');
    var albl = el('v4-ahead-lbl');
    var at   = el('v4-ahead-tbody');
    if (blbl) blbl.textContent = 'Behind Schedule (' + behind.length + ')';
    if (bt) {
      if (!behind.length) {
        bt.innerHTML = '<tr><td colspan="4" style="color:#64748b;text-align:center;padding:12px">No activities behind schedule ✓</td></tr>';
      } else {
        bt.innerHTML = behind.slice(0,6).map(function(i) {
          var v = safeFloat(i.variance_pct);
          return '<tr><td class="act-name" style="max-width:160px;white-space:normal">'+i.activity+'</td>' +
            '<td>'+Math.round(safeFloat(i.expected_pct))+'%</td>' +
            '<td>'+Math.round(safeFloat(i.actual_pct))+'%</td>' +
            '<td class="var-neg">'+(v>=0?'+':'')+v.toFixed(0)+'%</td></tr>';
        }).join('');
      }
    }
    if (albl) albl.textContent = 'Ahead of Schedule (' + ahead.length + ')';
    if (at) {
      if (!ahead.length) {
        at.innerHTML = '<tr><td colspan="4" style="color:#64748b;text-align:center;padding:12px">No activities ahead of schedule</td></tr>';
      } else {
        at.innerHTML = ahead.slice(0,4).map(function(i) {
          var v = safeFloat(i.variance_pct);
          return '<tr><td class="act-name" style="max-width:160px;white-space:normal">'+i.activity+'</td>' +
            '<td>'+Math.round(safeFloat(i.expected_pct))+'%</td>' +
            '<td>'+Math.round(safeFloat(i.actual_pct))+'%</td>' +
            '<td class="var-pos">+'+(Math.abs(v)).toFixed(0)+'%</td></tr>';
        }).join('');
      }
    }
  }

  function renderChart(progress) {
    var wrap = el('v4-chart-wrap');
    if (!wrap) return;
    var W=380, H=160, PL=36, PR=16, PT=16, PB=28;
    var cw=W-PL-PR, ch=H-PT-PB;
    if (!progress.length) {
      wrap.innerHTML = '<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'"><text x="'+(W/2)+'" y="'+(H/2)+'" text-anchor="middle" font-size="13" fill="#94a3b8">No data for this trade</text></svg>';
      return;
    }
    var items = progress.slice().sort(function(a,b){ return safeFloat(a.expected_pct)-safeFloat(b.expected_pct); });
    var n = items.length;
    var x = function(i){ return PL + (i/Math.max(n-1,1))*cw; };
    var y = function(p){ return PT + ch - safeFloat(p)/100*ch; };
    var pPts = items.map(function(it,i){ return x(i).toFixed(1)+','+y(it.expected_pct).toFixed(1); }).join(' ');
    var aPts = items.map(function(it,i){ return x(i).toFixed(1)+','+y(it.actual_pct).toFixed(1); }).join(' ');
    var grids=[25,50,75,100].map(function(p){
      return '<line x1="'+PL+'" y1="'+y(p).toFixed(1)+'" x2="'+(PL+cw)+'" y2="'+y(p).toFixed(1)+'" stroke="#f1f5f9" stroke-width="1"/>';
    }).join('');
    var labels=[0,25,50,75,100].map(function(p){
      return '<text x="'+(PL-6)+'" y="'+y(p).toFixed(1)+'" text-anchor="end" font-size="9" fill="#94a3b8" dominant-baseline="central">'+p+'%</text>';
    }).join('');
    wrap.innerHTML = '<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'" style="overflow:visible">'+
      '<rect x="'+PL+'" y="'+PT+'" width="'+cw+'" height="'+(y(90)-PT).toFixed(1)+'" fill="rgba(16,185,129,0.06)"/>'+
      '<rect x="'+PL+'" y="'+y(90).toFixed(1)+'" width="'+cw+'" height="'+(y(70)-y(90)).toFixed(1)+'" fill="rgba(245,158,11,0.06)"/>'+
      '<rect x="'+PL+'" y="'+y(70).toFixed(1)+'" width="'+cw+'" height="'+(y(0)-y(70)).toFixed(1)+'" fill="rgba(239,68,68,0.06)"/>'+
      grids+labels+
      '<polyline points="'+pPts+'" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,3"/>'+
      '<polyline points="'+aPts+'" fill="none" stroke="#0ea5e9" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'+
      '<line x1="'+PL+'" y1="'+(H-8)+'" x2="'+(PL+20)+'" y2="'+(H-8)+'" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,3"/>'+
      '<text x="'+(PL+24)+'" y="'+(H-4)+'" font-size="9" fill="#64748b">Planned</text>'+
      '<line x1="'+(PL+80)+'" y1="'+(H-8)+'" x2="'+(PL+100)+'" y2="'+(H-8)+'" stroke="#0ea5e9" stroke-width="2.5"/>'+
      '<text x="'+(PL+104)+'" y="'+(H-4)+'" font-size="9" fill="#64748b">Actual</text>'+
      '</svg>';
  }

  function renderInsights(behind, ponrItems, recs) {
    var strip = el('v4-insights-strip');
    if (!strip) return;
    var cards = strip.querySelectorAll('.v4-insight-card');
    var yc = ponrItems.filter(function(i){ return (i.classification||'').toLowerCase()==='yellow'; }).length;
    var critCt = ponrItems.filter(function(i){ var c=(i.classification||'').toLowerCase(); return c==='red'||c==='yellow'; }).length;
    if (cards[0]) {
      var v = cards[0].querySelector('.v4-insight-value');
      if (v) v.textContent = behind.length
        ? (behind[0].activity || 'Unknown') + ' is the main driver of delay'
        : 'No significant delays detected';
    }
    if (cards[1]) {
      var v = cards[1].querySelector('.v4-insight-value');
      if (v) v.textContent = yc + ' of ' + ponrItems.length + ' at-risk activities can still be recovered';
    }
    if (cards[2]) {
      var v = cards[2].querySelector('.v4-insight-value');
      if (v) v.textContent = 'Additional resources recommended for ' + Math.max(behind.length, recs.length) + ' activities';
    }
    if (cards[3]) {
      var v = cards[3].querySelector('.v4-insight-value');
      if (v) v.textContent = 'Delay will impact ' + critCt + ' downstream activities';
    }
  }

  function renderActionRequired(notStarted, behind, ahead) {
    var overdueTbody = el('v4-overdue-start-tbody');
    var overdueSub   = el('v4-overdue-start-sub');
    if (overdueTbody) {
      if (overdueSub) overdueSub.textContent = '0% progress, start date passed (' + notStarted.length + ')';
      if (!notStarted.length) {
        overdueTbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#64748b;padding:16px">No overdue starts ✓</td></tr>';
      } else {
        overdueTbody.innerHTML = notStarted.map(function(item) {
          return '<tr><td style="color:#64748b;">' + (item.id || '—') + '</td>' +
            '<td class="act-name" style="max-width:180px;white-space:normal">' + (item.activity || '') + '</td>' +
            '<td>' + (item.start_date || '') + '</td>' +
            '<td>' + (item.finish_date || '') + '</td></tr>';
        }).join('');
      }
    }

    var behindTbody = el('v4-behind-schedule-tbody');
    var behindSub   = el('v4-behind-schedule-sub');
    if (behindTbody) {
      if (behindSub) behindSub.textContent = 'Actual progress is behind expected (' + behind.length + ')';
      if (!behind.length) {
        behindTbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:16px">No activities behind schedule ✓</td></tr>';
      } else {
        behindTbody.innerHTML = behind.map(function(item) {
          var v = safeFloat(item.variance_pct);
          return '<tr><td style="color:#64748b;">—</td>' +
            '<td class="act-name" style="max-width:180px;white-space:normal">' + (item.activity || '') + '</td>' +
            '<td>' + Math.round(safeFloat(item.actual_pct)) + '%</td>' +
            '<td>' + Math.round(safeFloat(item.expected_pct)) + '%</td>' +
            '<td class="var-neg">' + (v >= 0 ? '+' : '') + v.toFixed(0) + '%</td></tr>';
        }).join('');
      }
    }

    var aheadTbody = el('v4-ahead-schedule-tbody');
    var aheadSub   = el('v4-ahead-schedule-sub');
    if (aheadTbody) {
      if (aheadSub) aheadSub.textContent = 'Actual progress exceeds expected (' + ahead.length + ')';
      if (!ahead.length) {
        aheadTbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:16px">No activities ahead of schedule</td></tr>';
      } else {
        aheadTbody.innerHTML = ahead.map(function(item) {
          var v = safeFloat(item.variance_pct);
          return '<tr><td style="color:#64748b;">—</td>' +
            '<td class="act-name" style="max-width:180px;white-space:normal">' + (item.activity || '') + '</td>' +
            '<td>' + Math.round(safeFloat(item.actual_pct)) + '%</td>' +
            '<td>' + Math.round(safeFloat(item.expected_pct)) + '%</td>' +
            '<td class="var-pos">+' + Math.abs(v).toFixed(0) + '%</td></tr>';
        }).join('');
      }
    }
  }

  function render(code) {
    var ch = D.changed_activities || {};
    var progress    = filterObj(D.progress_vs_expected, code);
    var ponr        = filterObj(D.point_of_no_return, code);
    var recs        = filterObj(D.action_recommendations, code);
    var changes     = filterObj(ch.changes, code);
    var added       = filterStr(ch.added, code);
    var removed     = filterStr(ch.removed, code);
    var notStarted  = filterObj(D.not_started_overdue, code);

    var behind      = progress.filter(function(i){ return (i.status||'').toLowerCase()==='behind'; });
    var ahead       = progress.filter(function(i){ return (i.status||'').toLowerCase()==='ahead'; });
    var redPonr     = ponr.filter(function(i){ return (i.classification||'').toLowerCase()==='red'; });
    var yellowPonr  = ponr.filter(function(i){ return (i.classification||'').toLowerCase()==='yellow'; });
    var critPonr    = redPonr.concat(yellowPonr);

    var tradeCounts = (D.executive_summary||{}).trade_counts || {};
    var totalAll    = (D.executive_summary||{}).selected_activities || 0;
    var sel         = (code === 'ALL') ? totalAll : (tradeCounts[code] || progress.length || totalAll);
    var changedCt   = changes.length;
    var critCt      = ponr.filter(function(i){ var c=(i.classification||'').toLowerCase(); return c==='red'||c==='yellow'; }).length;
    var pct         = sel ? Math.round(changedCt/sel*100) : 0;
    var durCt       = changes.filter(function(c){ return (c.change_type||'').toLowerCase().indexOf('duration')>=0; }).length;
    var dateCt      = changedCt - durCt;

    // KPIs
    var eKA = el('v4-kpi-analyzed'); if (eKA) eKA.textContent = sel;
    var eKC = el('v4-kpi-changed');  if (eKC) eKC.textContent = changedCt;
    var eKP = el('v4-kpi-changed-pct'); if (eKP) eKP.textContent = pct + '% of total activities';
    var eKCr= el('v4-kpi-critical'); if (eKCr) eKCr.textContent = critCt;
    var eKB = el('v4-kpi-behind');   if (eKB) eKB.textContent = behind.length;
    var eKAh= el('v4-kpi-ahead');    if (eKAh) eKAh.textContent = ahead.length;
    var eKPn= el('v4-kpi-ponr');     if (eKPn) eKPn.textContent = redPonr.length;

    // Change KPIs
    var eCA = el('v4-change-add'); if (eCA) eCA.textContent = added.length;
    var eCR = el('v4-change-rem'); if (eCR) eCR.textContent = removed.length;
    var eCD = el('v4-change-date'); if (eCD) eCD.textContent = dateCt;
    var eCDu= el('v4-change-dur'); if (eCDu) eCDu.textContent = durCt;

    renderStatus(computeHealth(behind.length, critPonr.length));
    renderTop5(progress);
    renderPONR(critPonr);
    renderWhatToDo(recs, progress);
    renderSchedule(behind, ahead);
    renderChart(progress);
    renderInsights(behind, critPonr, recs);
    renderActionRequired(notStarted, behind, ahead);
  }

  // Expose globally so onclick handlers work
  window.v4SetFilter = function(code) {
    activeTrade = code;
    document.querySelectorAll('.v4-scope-pill').forEach(function(pill) {
      var tc = pill.getAttribute('data-trade');
      pill.classList.toggle('active', tc === code);
      var ck = pill.querySelector('.v4-check');
      if (ck) {
        ck.classList.toggle('checked', tc === code);
        ck.innerHTML = tc === code
          ? '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>'
          : '';
      }
    });
    render(code);
  };

  // Initialise on load — ALL selected by default
  document.addEventListener('DOMContentLoaded', function() { render('ALL'); });
  // Also fire immediately in case DOM is already ready
  if (document.readyState !== 'loading') { render('ALL'); }
})();
"""


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def format_compare_v4_as_html(data: dict, language: str = "en") -> str:  # noqa: C901
    parts: list[str] = []
    a = parts.append

    # ── Top-level data extraction (for initial Python render) ─────────────
    es = data.get("executive_summary", {})
    health = str(es.get("project_health", "Green"))
    selected_activities = int(es.get("selected_activities", 0))
    behind_count = int(es.get("behind_schedule_count", 0))
    ahead_count  = int(es.get("ahead_of_schedule_count", 0))
    critical_count = int(es.get("critical_count", 0))
    ponr_count   = int(es.get("point_of_no_return_count", 0))

    changes      = data.get("changed_activities", {})
    added_list   = changes.get("added", [])
    removed_list = changes.get("removed", [])
    flat_changes = changes.get("changes", [])
    changed_count = len(flat_changes)
    changed_pct  = round(changed_count / max(selected_activities, 1) * 100)

    progress_items = data.get("progress_vs_expected", [])
    behind_items   = [i for i in progress_items if "behind" in str(i.get("status", "")).lower()]
    ahead_items    = [i for i in progress_items if "ahead"  in str(i.get("status", "")).lower()]
    top5_issues    = sorted(progress_items, key=lambda i: _safe_float(i.get("variance_pct", 0)))[:5]

    not_started_items = data.get("not_started_overdue", [])
    ponr_items     = data.get("point_of_no_return", [])
    red_ponr       = [i for i in ponr_items if str(i.get("classification", "")).upper() == "RED"]
    yellow_ponr    = [i for i in ponr_items if str(i.get("classification", "")).upper() == "YELLOW"]
    all_critical   = red_ponr + yellow_ponr

    action_recs    = data.get("action_recommendations", [])

    badge_cls, dot_cls, status_sub = _health_meta(health)
    status_label = _health_label(health)

    est_delay_days = ""
    for item in all_critical:
        rem = str(item.get("remaining_time", "")).lower()
        if rem.startswith("-") or "insufficient" in rem:
            try:
                d = abs(int("".join(c for c in rem if c.isdigit())))
                est_delay_days = str(d)
                break
            except ValueError:
                pass
    if not est_delay_days and all_critical:
        est_delay_days = "?"

    dur_changes  = sum(1 for c in flat_changes if "duration" in str(c.get("change_type", "")).lower())
    date_changes = changed_count - dur_changes

    today_str = _date.today().strftime("%b %d, %Y")

    # ── Embed full JSON for JS ─────────────────────────────────────────────
    json_str = _json.dumps(data, ensure_ascii=False, separators=(',', ':'))

    # ── Style ─────────────────────────────────────────────────────────────
    a(f"<style>{_CSS}</style>")
    a(f'<script>window.__v4Data = {json_str};</script>')
    a('<div class="v4">')

    # ── Header ────────────────────────────────────────────────────────────
    a('''<div class="v4-header">
  <div class="v4-brand-logo">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
      <path d="M2 20h20M6 20V10M12 20V4M18 20v-6"/>
    </svg>
  </div>
  <div class="v4-header-titles">
    <p class="v4-header-super">Nova Insight</p>
    <h1 class="v4-header-title">PROJECT HEALTH DASHBOARD</h1>
    <p class="v4-header-sub">Instant overview. Smarter decisions.</p>
  </div>
</div>''')

    a('<div class="v4-body">')

    # ── KPI Strip ─────────────────────────────────────────────────────────
    a('<p class="v4-section-label">PROJECT STATUS</p>')
    a('<div class="v4-kpi-strip">')

    # Status block
    a(f'''<div class="v4-status-block" id="v4-status-badge-wrap">
  <div class="v4-status-badge {badge_cls}">
    <span class="v4-dot {dot_cls} v4-status-dot"></span>
    <span id="v4-status-label">{status_label}</span>
  </div>
  <p class="v4-status-sub" id="v4-status-sub-text">{status_sub}</p>
</div>''')

    # Metric pills — each number gets an id for JS updates
    a('<div class="v4-metric-pills">')
    pills = [
        ("v4-kpi-analyzed", "Activities\nAnalyzed",   str(selected_activities), "",      "rgba(14,165,233,0.12)",  "#0284c7",
         '<path d="M3 3h18v18H3z"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
         "100% of schedule"),
        ("v4-kpi-changed",  "Changed\nActivities",   str(changed_count),        "blue",  "rgba(124,58,237,0.12)",  "#7c3aed",
         '<path d="M16 3h5v5M4 20L21 3M21 16v5h-5M4 4l5 5"/>',
         f'<span id="v4-kpi-changed-pct">{changed_pct}% of total activities</span>'),
        ("v4-kpi-critical", "Critical\nActivities",  str(critical_count),       "red",   "rgba(239,68,68,0.12)",   "#dc2626",
         '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>',
         "Require attention"),
        ("v4-kpi-behind",   "Behind\nSchedule",      str(behind_count),         "red",   "rgba(239,68,68,0.12)",   "#dc2626",
         '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
         "Need recovery"),
        ("v4-kpi-ahead",    "Ahead of\nSchedule",    str(ahead_count),          "green", "rgba(16,185,129,0.12)",  "#059669",
         '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
         "On track"),
        ("v4-kpi-ponr",     "Point of\nNo Return",   str(ponr_count),           "red",   "rgba(239,68,68,0.12)",   "#dc2626",
         '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
         "At risk of late finish"),
    ]
    for pid, label, val, num_cls, icon_bg, icon_stroke, icon_path_d, sub in pills:
        display_label = label.replace("\n", " ")
        a(f'''<div class="v4-metric-pill">
  <div class="v4-pill-icon" style="background:{icon_bg}">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{icon_stroke}" stroke-width="2.5">{icon_path_d}</svg>
  </div>
  <div class="v4-pill-num {num_cls}" id="{pid}">{val}</div>
  <div class="v4-pill-label">{display_label}</div>
  <div class="v4-pill-sub">{sub}</div>
</div>''')
    a('</div>')  # metric-pills
    a('</div>')  # kpi-strip

    # ── Action Required Today Section ─────────────────────────────────────
    a('<p class="v4-section-label">ACTION REQUIRED TODAY</p>')
    a('<div class="v4-grid-3">')

    # Card 1: Overdue Start (0% Progress)
    a(f'''<div class="v4-card">
  <div class="v4-card-header">
    <div class="v4-card-icon" style="background:linear-gradient(135deg,#ef4444,#dc2626)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
    </div>
    <div>
      <p class="v4-card-hd">OVERDUE START (0% PROGRESS)</p>
      <p class="v4-card-sub" id="v4-overdue-start-sub">0% progress, start date passed ({len(not_started_items)})</p>
    </div>
  </div>
  <div class="v4-table-wrap">
    <table class="v4-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Activity Name</th>
          <th>Planned Start</th>
          <th>Planned Finish</th>
        </tr>
      </thead>
      <tbody id="v4-overdue-start-tbody">''')
    if not_started_items:
        for item in not_started_items:
            id_ = item.get("id", "—") or "—"
            name = item.get("activity", "")
            start = item.get("start_date", "")
            finish = item.get("finish_date", "")
            a(f'        <tr><td style="color:#64748b;">{id_}</td><td class="act-name" style="max-width:180px;white-space:normal">{name}</td><td>{start}</td><td>{finish}</td></tr>')
    else:
        a('        <tr><td colspan="4" style="text-align:center;color:#64748b;padding:16px">No overdue starts ✓</td></tr>')
    a('''      </tbody>
    </table>
  </div>
</div>''')

    # Card 2: Behind Schedule (Progress Mismatch)
    a(f'''<div class="v4-card">
  <div class="v4-card-header">
    <div class="v4-card-icon" style="background:linear-gradient(135deg,#f59e0b,#d97706)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
      </svg>
    </div>
    <div>
      <p class="v4-card-hd">BEHIND SCHEDULE</p>
      <p class="v4-card-sub" id="v4-behind-schedule-sub">Actual progress is behind expected ({len(behind_items)})</p>
    </div>
  </div>
  <div class="v4-table-wrap">
    <table class="v4-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Activity Name</th>
          <th>Actual</th>
          <th>Expected</th>
          <th>Deviation</th>
        </tr>
      </thead>
      <tbody id="v4-behind-schedule-tbody">''')
    if behind_items:
        for item in behind_items:
            name = item.get("activity", "")
            act = _safe_float(item.get("actual_pct", 0))
            exp = _safe_float(item.get("expected_pct", 0))
            var = _safe_float(item.get("variance_pct", 0))
            a(f'        <tr><td style="color:#64748b;">—</td><td class="act-name" style="max-width:180px;white-space:normal">{name}</td><td>{act:.0f}%</td><td>{exp:.0f}%</td><td class="var-neg">{var:+.0f}%</td></tr>')
    else:
        a('        <tr><td colspan="5" style="text-align:center;color:#64748b;padding:16px">No activities behind schedule ✓</td></tr>')
    a('''      </tbody>
    </table>
  </div>
</div>''')

    # Card 3: Ahead of Schedule
    a(f'''<div class="v4-card">
  <div class="v4-card-header">
    <div class="v4-card-icon" style="background:linear-gradient(135deg,#10b981,#059669)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>
      </svg>
    </div>
    <div>
      <p class="v4-card-hd">AHEAD OF SCHEDULE</p>
      <p class="v4-card-sub" id="v4-ahead-schedule-sub">Actual progress exceeds expected ({len(ahead_items)})</p>
    </div>
  </div>
  <div class="v4-table-wrap">
    <table class="v4-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Activity Name</th>
          <th>Actual</th>
          <th>Expected</th>
          <th>Ahead</th>
        </tr>
      </thead>
      <tbody id="v4-ahead-schedule-tbody">''')
    if ahead_items:
        for item in ahead_items:
            name = item.get("activity", "")
            act = _safe_float(item.get("actual_pct", 0))
            exp = _safe_float(item.get("expected_pct", 0))
            var = _safe_float(item.get("variance_pct", 0))
            a(f'        <tr><td style="color:#64748b;">—</td><td class="act-name" style="max-width:180px;white-space:normal">{name}</td><td>{act:.0f}%</td><td>{exp:.0f}%</td><td class="var-pos">{var:+.0f}%</td></tr>')
    else:
        a('        <tr><td colspan="5" style="text-align:center;color:#64748b;padding:16px">No activities ahead of schedule</td></tr>')
    a('''      </tbody>
    </table>
  </div>
</div>''')

    a('</div>')  # grid-3

    # ── Row 2: Top Issues | PONR | What Should I Do ───────────────────────
    a('<div class="v4-grid-3">')

    # ── Left: Top 5 Issues ────────────────────────────────────────────────
    a('''<div class="v4-card">
  <div class="v4-card-header">
    <div class="v4-card-icon" style="background:linear-gradient(135deg,#dc2626,#b91c1c)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>
        <polyline points="16 7 22 7 22 13"/>
      </svg>
    </div>
    <div><p class="v4-card-hd">TOP 5 ISSUES REQUIRING ACTION</p><p class="v4-card-sub">Activities most behind schedule</p></div>
  </div>
  <div class="v4-table-wrap"><table class="v4-table">
    <thead><tr><th>#</th><th>Activity</th><th>Deviation</th><th>Impact</th></tr></thead>
    <tbody id="v4-top5-tbody">''')
    if top5_issues:
        for idx, item in enumerate(top5_issues, 1):
            var = _safe_float(item.get("variance_pct", 0))
            imp_label, imp_cls = _variance_impact(var)
            var_str = f"{var:+.0f}%"
            a(f'<tr><td class="rank">{idx}</td><td class="act-name">{item.get("activity","")}</td>'
              f'<td class="deviation">{var_str}</td><td><span class="v4-imp {imp_cls}">{imp_label}</span></td></tr>')
    else:
        a('<tr><td colspan="4" style="text-align:center;color:#64748b;padding:16px">No delayed activities found ✓</td></tr>')
    a('''    </tbody>
  </table></div>
  <div style="margin-top:14px;display:flex;align-items:center;gap:6px;font-size:12px;color:#2563eb;font-weight:600;cursor:pointer">View all issues →</div>
</div>''')

    # ── Centre: PONR ──────────────────────────────────────────────────────
    a(f'''<div class="v4-card">
  <div class="v4-card-header">
    <div class="v4-card-icon" style="background:linear-gradient(135deg,#7c3aed,#6d28d9)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
      </svg>
    </div>
    <div><p class="v4-card-hd">POINT OF NO RETURN</p><p class="v4-card-sub">Activities that cannot reach their finish date</p></div>
  </div>
  <div class="v4-ponr-count" id="v4-ponr-count-num">{len(all_critical)}</div>
  <div class="v4-ponr-count-lbl">Activities at risk of not finishing on time</div>
  <ol class="v4-ponr-list" id="v4-ponr-list-ol">''')
    if all_critical:
        for i, item in enumerate(all_critical[:5], 1):
            dot = "v4-dot-red" if str(item.get("classification","")).upper() == "RED" else "v4-dot-yellow"
            a(f'<li><div class="v4-ponr-num">{i}</div>'
              f'<span class="v4-ponr-name">{item.get("activity","")}</span>'
              f'<span class="v4-dot {dot}"></span></li>')
    else:
        a('<li style="color:#64748b;font-size:13px;padding:8px 0;border:none;list-style:none">No activities at point of no return ✓</li>')
    a('  </ol>')

    delay_display = "none" if not est_delay_days else ""
    a(f'''  <div id="v4-delay-box-wrap" style="display:{delay_display}">
    <div class="v4-delay-box">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2">
        <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>
        <line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
      </svg>
      <div>
        <div class="v4-delay-lbl">Estimated Project Delay</div>
        <div style="display:flex;align-items:baseline;gap:6px">
          <span class="v4-delay-num">{est_delay_days or "?"}</span>
          <span style="font-size:14px;font-weight:700;color:#dc2626">Working Days</span>
        </div>
      </div>
    </div>
  </div>
  <div style="margin-top:12px;display:flex;align-items:center;gap:6px;font-size:12px;color:#2563eb;font-weight:600;cursor:pointer">View recovery plan →</div>
</div>''')

    # ── Right: What Should I Do ───────────────────────────────────────────
    a('<div class="v4-card">')
    a('''  <div class="v4-card-header">
    <div class="v4-card-icon" style="background:linear-gradient(135deg,#0ea5e9,#0284c7)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
    </div>
    <div><p class="v4-card-hd">WHAT SHOULD I DO?</p><p class="v4-card-sub">Top recommended action</p></div>
  </div>''')
    a('  <div id="v4-wsid-body">')
    if action_recs:
        top_rec  = action_recs[0]
        act_name = top_rec.get("activity", "")
        issue    = top_rec.get("issue", "")
        actions  = top_rec.get("actions", [])
        actual_pct_val = next(
            (_safe_float(p.get("actual_pct", 0)) for p in progress_items if p.get("activity") == act_name),
            _safe_float(all_critical[0].get("actual_pct", 0)) if all_critical else 0.0
        )
        imp_var = next(
            (_safe_float(p.get("variance_pct", 0)) for p in progress_items if p.get("activity") == act_name),
            -50.0
        )
        imp_label, imp_cls = _variance_impact(imp_var)
        a(f'    <div class="v4-wsid-tag">Most Critical Activity <span class="v4-imp {imp_cls}" style="margin-left:6px">{imp_label}</span></div>')
        a(f'    <div class="v4-wsid-activity">{act_name}</div>')
        a(f'    <div class="v4-wsid-problem">{issue}</div>')
        a('    <div class="v4-wsid-body-inner">')
        a(f'      <div class="v4-donut-wrap">{_donut_svg(actual_pct_val)}</div>')
        if actions:
            a('      <ul class="v4-actions-list">')
            for action in actions[:6]:
                a(f'        <li><div class="v4-action-check"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></div>{action}</li>')
            a('      </ul>')
        a('    </div>')
        a('    <div style="margin-top:12px;display:flex;align-items:center;gap:6px;font-size:12px;color:#2563eb;font-weight:600;cursor:pointer">View full action plan →</div>')
    else:
        a('    <div style="padding:20px 0;color:#64748b;font-size:13px;text-align:center">No critical actions required ✓</div>')
    a('  </div>')  # v4-wsid-body
    a('</div>')    # card

    a('</div>')    # grid-3 (row 2)

    # ── Row 3: Trade Filter | Schedule Tables | Chart ─────────────────────
    a('<div class="v4-grid-3">')

    # ── Left: Trade Filter ────────────────────────────────────────────────
    a('''<div class="v4-card">
  <div class="v4-card-header">
    <div class="v4-card-icon" style="background:linear-gradient(135deg,#475569,#334155)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
      </svg>
    </div>
    <div><p class="v4-card-hd">TRADE FILTER</p><p class="v4-card-sub">Select trade to view details</p></div>
  </div>
  <div class="v4-scope-pills">''')

    _trades = [
        ("EL",   "Electrical"),
        ("VVS",  "Plumbing"),
        ("VENT", "Ventilation"),
        ("ARK",  "Architectural"),
        ("BYGH", "Client"),
        ("ALL",  "All trades"),
    ]
    for code, label in _trades:
        is_active = code == "ALL"
        active_cls = "active" if is_active else ""
        check_content = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>' if is_active else ""
        a(f'    <div class="v4-scope-pill {active_cls}" data-trade="{code}" onclick="v4SetFilter(\'{code}\')">'
          f'      <div class="v4-check {"checked" if is_active else ""}">{check_content}</div>'
          f'      <strong>{code}</strong>&nbsp;&nbsp;{label}'
          f'    </div>')

    a('  </div>')

    # Change KPIs below the filter
    a(f'''  <div style="margin-top:16px">
    <p class="v4-section-label">Schedule Changes</p>
    <div class="v4-change-kpi-row">
      <div class="v4-change-kpi">
        <div class="v4-change-kpi-num add" id="v4-change-add">{len(added_list)}</div>
        <div class="v4-change-kpi-lbl">Added</div>
      </div>
      <div class="v4-change-kpi">
        <div class="v4-change-kpi-num rem" id="v4-change-rem">{len(removed_list)}</div>
        <div class="v4-change-kpi-lbl">Removed</div>
      </div>
      <div class="v4-change-kpi">
        <div class="v4-change-kpi-num chg" id="v4-change-date">{date_changes}</div>
        <div class="v4-change-kpi-lbl">Date Chgd</div>
      </div>
      <div class="v4-change-kpi">
        <div class="v4-change-kpi-num dur" id="v4-change-dur">{dur_changes}</div>
        <div class="v4-change-kpi-lbl">Dur. Chgd</div>
      </div>
    </div>
  </div>
</div>''')

    # ── Centre: Schedule Tables ───────────────────────────────────────────
    a('<div class="v4-card">')
    a('''  <div class="v4-card-header">
    <div class="v4-card-icon" style="background:linear-gradient(135deg,#f59e0b,#d97706)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
      </svg>
    </div>
    <div><p class="v4-card-hd">SCHEDULE OVERVIEW</p><p class="v4-card-sub">Behind &amp; ahead of schedule breakdown</p></div>
  </div>''')

    # Behind schedule table
    a(f'  <p class="v4-table-group-lbl" style="color:#dc2626" id="v4-behind-lbl">Behind Schedule ({len(behind_items)})</p>')
    a('  <div class="v4-table-wrap"><table class="v4-table">')
    a('    <thead><tr><th>Activity</th><th>Should Be</th><th>Actual</th><th>Deviation</th></tr></thead>')
    a('    <tbody id="v4-behind-tbody">')
    if behind_items:
        for item in behind_items[:6]:
            exp = _safe_float(item.get("expected_pct", 0))
            act = _safe_float(item.get("actual_pct", 0))
            var = _safe_float(item.get("variance_pct", 0))
            a(f'      <tr><td class="act-name" style="max-width:160px;white-space:normal">{item.get("activity","")}</td>'
              f'<td>{exp:.0f}%</td><td>{act:.0f}%</td><td class="var-neg">{var:+.0f}%</td></tr>')
    else:
        a('      <tr><td colspan="4" style="color:#64748b;text-align:center;padding:12px">No activities behind schedule ✓</td></tr>')
    a('    </tbody></table></div>')

    # Ahead of schedule table
    a(f'  <p class="v4-table-group-lbl" style="color:#059669;margin-top:14px" id="v4-ahead-lbl">Ahead of Schedule ({len(ahead_items)})</p>')
    a('  <div class="v4-table-wrap"><table class="v4-table">')
    a('    <thead><tr><th>Activity</th><th>Should Be</th><th>Actual</th><th>Ahead</th></tr></thead>')
    a('    <tbody id="v4-ahead-tbody">')
    if ahead_items:
        for item in ahead_items[:4]:
            exp = _safe_float(item.get("expected_pct", 0))
            act = _safe_float(item.get("actual_pct", 0))
            var = _safe_float(item.get("variance_pct", 0))
            a(f'      <tr><td class="act-name" style="max-width:160px;white-space:normal">{item.get("activity","")}</td>'
              f'<td>{exp:.0f}%</td><td>{act:.0f}%</td><td class="var-pos">{var:+.0f}%</td></tr>')
    else:
        a('      <tr><td colspan="4" style="color:#64748b;text-align:center;padding:12px">No activities ahead of schedule</td></tr>')
    a('    </tbody></table></div>')
    a('</div>')  # card

    # ── Right: Progress Chart ─────────────────────────────────────────────
    a('''<div class="v4-card">
  <div class="v4-card-header">
    <div class="v4-card-icon" style="background:linear-gradient(135deg,#10b981,#059669)">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>
      </svg>
    </div>
    <div><p class="v4-card-hd">OVERALL PROGRESS</p><p class="v4-card-sub">Planned vs actual progress</p></div>
  </div>
  <div class="v4-band-label">
    <span class="v4-band-tag on">&gt;90% ON TRACK</span>
    <span class="v4-band-tag risk">70–90% AT RISK</span>
    <span class="v4-band-tag beh">&lt;70% BEHIND</span>
  </div>''')
    a(f'  <div class="v4-chart-wrap" id="v4-chart-wrap">{_chart_svg(progress_items)}</div>')
    if est_delay_days:
        a(f'  <div class="v4-projected-delay">'
          f'    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
          f'    Projected delay&nbsp;<strong>{est_delay_days} working days</strong>'
          f'  </div>')
    a('</div>')  # card
    a('</div>')  # grid-3 (row 3)

    # ── AI Insights Strip ─────────────────────────────────────────────────
    a('<div class="v4-insights-section">')
    a('<p class="v4-section-label">AI INSIGHTS</p>')
    a('<div class="v4-insights-strip" id="v4-insights-strip">')

    insights = [
        ("Delay Driver",
         (behind_items[0].get("activity", "Unknown") + " is the main driver of delay") if behind_items else "No significant delays detected",
         "See details",
         "rgba(239,68,68,0.12)", "#dc2626",
         '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>'),
        ("Recovery Possible",
         f"{len(yellow_ponr)} of {len(all_critical)} at-risk activities can still be recovered",
         "See recovery plan",
         "rgba(245,158,11,0.12)", "#b45309",
         '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>'),
        ("Resource Gap",
         f"Additional resources recommended for {max(behind_count, len(action_recs))} activities",
         "See resource plan",
         "rgba(14,165,233,0.12)", "#0284c7",
         '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'),
        ("High Impact",
         f"Delay will impact {critical_count} downstream activities",
         "See impact",
         "rgba(245,158,11,0.12)", "#b45309",
         '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
        ("Next Review",
         "Daily review recommended for critical activities",
         "Set reminders",
         "rgba(124,58,237,0.12)", "#7c3aed",
         '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>'),
    ]
    for label, value, action, icon_bg, icon_stroke, icon_path in insights:
        a(f'''<div class="v4-insight-card">
  <div class="v4-insight-icon" style="background:{icon_bg}">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="{icon_stroke}" stroke-width="2">{icon_path}</svg>
  </div>
  <div class="v4-insight-label">{label}</div>
  <div class="v4-insight-value">{value}</div>
  <div class="v4-insight-action">{action} →</div>
</div>''')

    a('</div>')  # insights-strip
    a('</div>')  # insights-section

    a('</div>')  # v4-body
    a('</div>')  # v4

    # ── JS block ──────────────────────────────────────────────────────────
    a(f'<script>{_JS}</script>')

    return "\n".join(parts)
