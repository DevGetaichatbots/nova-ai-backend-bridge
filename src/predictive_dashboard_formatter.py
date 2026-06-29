

from __future__ import annotations
import json as _json
import html as _html


# ── Helpers ──────────────────────────────────────────────────────────────────

def _e(text) -> str:
    return _html.escape(str(text)) if text is not None else ""


def _si(val, default: int = 0) -> int:
    try:
        return int(round(float(val)))
    except (ValueError, TypeError):
        return default


_TRADE_PREFIXES = [
    ("EL",   ["EL -", "EL-"]),
    ("VVS",  ["VVS -", "VVS-"]),
    ("VENT", ["VENT -", "VENT-"]),
    ("ARK",  ["ARK -", "ARK-"]),
    ("BYGH", ["BYGH -", "BYGH-"]),
]


def _infer_trade(name: str) -> str:
    u = (name or "").upper()
    for code, prefixes in _TRADE_PREFIXES:
        if any(u.startswith(p.upper()) for p in prefixes):
            return code
    return "OTHER"


def _status_cfg(project_status: str, da: bool) -> tuple[str, str, str]:
    s = str(project_status).upper()
    if s == "CRITICAL":
        return "v5-badge-red", "v5-dot-red", ("KRITISK" if da else "CRITICAL")
    if s == "AT_RISK":
        return "v5-badge-amber", "v5-dot-amber", ("I RISIKO" if da else "AT RISK")
    return "v5-badge-green", "v5-dot-green", ("PÅ SPORET" if da else "ON TRACK")


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
*{box-sizing:border-box;}
.v5{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f1f5f9;color:#0f172a;line-height:1.4;-webkit-font-smoothing:antialiased;}

/* Header */
.v5-header{background:#fff;padding:10px 20px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #e2e8f0;}
.v5-logo{width:32px;height:32px;background:linear-gradient(135deg,#f59e0b,#ef4444);border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.v5-header-text{display:flex;flex-direction:column;}
.v5-header-brand{font-size:9px;font-weight:700;letter-spacing:2px;color:#d97706;text-transform:uppercase;line-height:1;}
.v5-header-title{font-size:18px;font-weight:900;letter-spacing:-0.4px;color:#0f172a;line-height:1.1;}
.v5-header-sub{font-size:11px;color:#94a3b8;}

/* Hero */
.v5-hero{background:#fff;border-bottom:1px solid #e2e8f0;padding:14px 20px;}
.v5-hero-label{font-size:9px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:#94a3b8;margin:0 0 10px 0;}
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
.v5-filter-group-title{font-size:9px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;color:#94a3b8;margin:0 0 6px 0;}
.v5-filter-opts{display:flex;flex-direction:column;gap:3px;}
.v5-filter-opt{display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:6px;font-size:11px;font-weight:500;color:#334155;cursor:pointer;border:1px solid transparent;transition:all .12s;user-select:none;}
.v5-filter-opt:hover{background:#f1f5f9;}
.v5-filter-opt.active{background:rgba(37,99,235,0.08);border-color:rgba(37,99,235,0.2);color:#1d4ed8;font-weight:700;}
.v5-filter-opt-dot{width:8px;height:8px;border-radius:50%;background:#e2e8f0;flex-shrink:0;transition:background .12s;}
.v5-filter-opt.active .v5-filter-opt-dot{background:#2563eb;}
.v5-filter-count{margin-left:auto;font-size:9px;color:#94a3b8;font-weight:600;}
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

/* Charts */
.pd-chart-card{overflow:hidden;}
.pd-chart-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid #f1f5f9;flex-wrap:wrap;}
.pd-chart-metrics{display:flex;gap:8px;flex-wrap:wrap;}
.pd-chart-chip{min-width:88px;padding:7px 10px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;}
.pd-chart-chip-label{display:block;font-size:9px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;color:#64748b;}
.pd-chart-chip-value{display:block;margin-top:2px;font-size:18px;font-weight:900;line-height:1;color:#0f172a;}
.pd-chart-chip-value.good{color:#059669;}
.pd-chart-chip-value.warn{color:#d97706;}
.pd-chart-chip-value.bad{color:#dc2626;}
.pd-curve-wrap{position:relative;height:248px;border:1px solid #e2e8f0;border-radius:10px;background:linear-gradient(180deg,#ffffff 0%,#f8fafc 100%);overflow:hidden;}
.pd-curve-wrap svg{display:block;width:100%;height:100%;}
.pd-curve-zone-good{fill:rgba(16,185,129,.08);}
.pd-curve-zone-warn{fill:rgba(245,158,11,.08);}
.pd-curve-zone-bad{fill:rgba(239,68,68,.08);}
.pd-curve-grid{stroke:#e2e8f0;stroke-width:1;}
.pd-curve-axis-label{font-size:10px;font-weight:700;fill:#94a3b8;}
.pd-curve-target{fill:none;stroke:#94a3b8;stroke-width:3;stroke-dasharray:7 7;stroke-linecap:round;}
.pd-curve-actual{fill:none;stroke:#2563eb;stroke-width:4;stroke-linecap:round;filter:drop-shadow(0 6px 10px rgba(37,99,235,.18));}
.pd-curve-point{fill:#2563eb;stroke:#fff;stroke-width:3;}
.pd-curve-target-point{fill:#94a3b8;stroke:#fff;stroke-width:2;}
.pd-curve-legend{display:flex;align-items:center;gap:14px;margin-top:10px;font-size:11px;color:#64748b;font-weight:700;flex-wrap:wrap;}
.pd-legend-line{display:inline-block;width:24px;height:0;border-top:3px solid #2563eb;vertical-align:middle;margin-right:5px;}
.pd-legend-line.target{border-top-color:#94a3b8;border-top-style:dashed;}
.pd-delay-note{margin-left:auto;color:#dc2626;}
.pd-bar-list{display:flex;flex-direction:column;gap:10px;}
.pd-bar-row{display:grid;grid-template-columns:minmax(92px,140px) 1fr auto;gap:10px;align-items:center;}
.pd-bar-label{font-size:11px;font-weight:700;color:#334155;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.pd-bar-track{height:12px;border-radius:999px;background:#e2e8f0;overflow:hidden;position:relative;}
.pd-bar-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,#2563eb,#60a5fa);}
.pd-bar-fill-warn{background:linear-gradient(90deg,#f59e0b,#fbbf24);}
.pd-bar-fill-bad{background:linear-gradient(90deg,#ef4444,#fb7185);}
.pd-bar-fill-good{background:linear-gradient(90deg,#10b981,#34d399);}
.pd-bar-value{font-size:11px;font-weight:800;color:#0f172a;white-space:nowrap;}
@media(max-width:900px){
  .pd-chart-metrics{width:100%;}
  .pd-chart-chip{flex:1;}
  .pd-curve-wrap{height:220px;}
  .pd-bar-row{grid-template-columns:88px 1fr auto;}
}

/* Scrollable tables */
.v5-scroll-wrap{max-height:300px;overflow-y:auto;border-radius:7px;border:1px solid #f1f5f9;scrollbar-width:thin;}
.v5-table{width:100%;border-collapse:separate;border-spacing:0;font-size:11px;}
.v5-table thead th{background:#f8fafc;font-weight:700;color:#475569;text-transform:uppercase;font-size:9px;letter-spacing:0.3px;padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:left;position:sticky;top:0;z-index:1;}
.v5-table tbody td{padding:6px 8px;border-bottom:1px solid #f8fafc;color:#334155;vertical-align:top;}
.v5-table tbody tr:last-child td{border-bottom:none;}
.v5-table tbody tr:hover{background:#fafafa;}
.v5-act-name{font-weight:600;color:#0f172a;max-width:220px;word-break:break-word;}

/* Priority badges */
.pd-pri{display:inline-flex;align-items:center;padding:2px 7px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:0.2px;white-space:nowrap;}
.pd-pri-critical{background:rgba(239,68,68,0.12);color:#b91c1c;border:1px solid rgba(239,68,68,0.2);}
.pd-pri-important{background:rgba(245,158,11,0.12);color:#92400e;border:1px solid rgba(245,158,11,0.2);}
.pd-pri-monitor{background:rgba(6,182,212,0.1);color:#0e7490;border:1px solid rgba(6,182,212,0.2);}

/* Task type badge */
.pd-type{display:inline-flex;align-items:center;padding:1px 5px;border-radius:4px;font-size:9px;font-weight:600;white-space:nowrap;}

/* Overdue days pill */
.pd-days{font-size:10px;font-weight:700;color:#dc2626;white-space:nowrap;}
.pd-days-ok{color:#059669;}

/* Root cause card */
.pd-rc-item{padding:10px 0;border-bottom:1px solid #f1f5f9;}
.pd-rc-item:last-child{border-bottom:none;}
.pd-rc-title{font-size:12px;font-weight:700;color:#0f172a;margin-bottom:2px;}
.pd-rc-id{font-size:9px;font-weight:800;color:#94a3b8;letter-spacing:0.5px;margin-bottom:4px;}
.pd-rc-why{font-size:11px;color:#475569;margin-bottom:3px;}
.pd-rc-consequence{font-size:10.5px;color:#dc2626;font-weight:500;}
.pd-rc-downstream{font-size:10px;color:#64748b;margin-top:2px;}

/* Executive action card */
.pd-action-item{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid #f1f5f9;}
.pd-action-item:last-child{border-bottom:none;}
.pd-action-rank{width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#ef4444,#b91c1c);color:#fff;font-size:13px;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.pd-action-rank-2{background:linear-gradient(135deg,#f59e0b,#d97706);}
.pd-action-rank-3{background:linear-gradient(135deg,#3b82f6,#2563eb);}
.pd-action-body{flex:1;min-width:0;}
.pd-action-text{font-size:12px;font-weight:700;color:#0f172a;margin-bottom:3px;line-height:1.3;}
.pd-action-meta{font-size:10px;color:#64748b;}
.pd-action-meta strong{color:#334155;}
.pd-action-manpower{font-size:10px;color:#64748b;margin-top:3px;padding:3px 6px;background:#f8fafc;border-radius:4px;border-left:2px solid #e2e8f0;}

/* Area risk card */
.pd-area-item{padding:8px 0;border-bottom:1px solid #f1f5f9;}
.pd-area-item:last-child{border-bottom:none;}
.pd-area-name{font-size:12px;font-weight:700;color:#0f172a;margin-bottom:3px;}
.pd-area-summary{font-size:10.5px;color:#64748b;line-height:1.4;}
.pd-area-pills{display:flex;gap:4px;margin-bottom:4px;flex-wrap:wrap;}
.pd-area-pill{font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;}
.pd-area-pill-red{background:rgba(239,68,68,0.1);color:#dc2626;}
.pd-area-pill-amber{background:rgba(245,158,11,0.1);color:#b45309;}
.pd-area-pill-blue{background:rgba(6,182,212,0.1);color:#0891b2;}

/* Delay driver */
.pd-driver-item{padding:8px 0;border-bottom:1px solid #f1f5f9;}
.pd-driver-item:last-child{border-bottom:none;}
.pd-driver-text{font-size:11.5px;font-weight:600;color:#0f172a;}

/* Full-width delayed table */
.pd-full-table-wrap{max-height:360px;overflow-y:auto;border-radius:7px;border:1px solid #f1f5f9;scrollbar-width:thin;}

/* Prediction box */
.pd-snapshot-box{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:12px 14px;}
.pd-snapshot-headline{font-size:12px;font-weight:700;color:#92400e;margin-bottom:6px;}
.pd-snapshot-text{font-size:11.5px;color:#78350f;line-height:1.5;}
.pd-snapshot-drivers{margin-top:8px;display:flex;flex-direction:column;gap:3px;}
.pd-snapshot-driver{display:flex;align-items:flex-start;gap:6px;font-size:11px;color:#b45309;}

/* Critical card accent */
.pd-critical-card{border-left:3px solid #dc2626;}

/* Area badge in tables */
.v5-loc-badge{display:inline-flex;align-items:center;gap:3px;padding:1px 5px;border-radius:4px;font-size:9px;font-weight:600;background:#f1f5f9;color:#475569;white-space:nowrap;}

/* Colour helpers */
.c-red{color:#dc2626!important;} .c-green{color:#059669!important;} .c-amber{color:#b45309!important;}
"""

# ── JavaScript filter engine ──────────────────────────────────────────────────

_JS = r"""
(function() {
  var D = window.__pdData;
  if (!D) return;
  var DA = D.language === 'da';
  var LOC = {
    criticalNow: DA ? 'Kritisk Nu' : 'Critical Now',
    importantNext: DA ? 'Vigtig Næste' : 'Important Next',
    monitor: DA ? 'Overvåg' : 'Monitor',
    allDelayed: DA ? 'Alle forsinkede aktiviteter' : 'All Delayed Activities',
    noCritical: DA ? 'Ingen kritiske aktiviteter' : 'No critical activities',
    noImportant: DA ? 'Ingen vigtige aktiviteter' : 'No important activities',
    noMonitor: DA ? 'Ingen overvågningsaktiviteter' : 'No monitor activities',
    noDelayedMatch: DA ? 'Ingen forsinkede aktiviteter matcher filtrene' : 'No delayed activities match current filters',
    noChartData: DA ? 'Ingen data tilgængelig for de valgte filtre' : 'No data available for the current filters',
    delayedActivities: DA ? 'forsinkede aktiviteter' : 'delayed activities',
    activities: DA ? 'aktiviteter' : 'activities',
    severeBacklog: DA ? 'Alvorlig backlog' : 'Severe backlog',
    overDays: DA ? 'over 60d' : 'over 60d',
    riskByArea: DA ? 'Risiko pr. område' : 'Risk by Area',
    overdueMix: DA ? 'Forsinkelsesfordeling' : 'Overdue Distribution',
    agingCurve: DA ? 'Forsinkelseskurve' : 'Delay Aging Curve',
    agingCurveSub: DA ? 'Hvor hurtigt forsinkelserne vokser ind i ældre bucket-niveauer' : 'How quickly delays age into older overdue buckets',
    areaBarSub: DA ? 'Filtreret antal forsinkede aktiviteter pr. område' : 'Filtered delayed activity count by area',
    overdueBarSub: DA ? 'Antal forsinkede aktiviteter i hver forsinkelsesgruppe' : 'Delayed activity count in each overdue bucket',
    targetLabel: DA ? 'Mål' : 'Target',
    currentLabel: DA ? 'Aktuel' : 'Current',
    upto30: DA ? '<=30d' : '<=30d',
    over60: DA ? '60+d' : '60+d',
    over90: DA ? '90+d' : '90+d'
  };

  var TRADE_PFX = {
    'EL':   ['EL -','EL-'],
    'VVS':  ['VVS -','VVS-'],
    'VENT': ['VENT -','VENT-'],
    'ARK':  ['ARK -','ARK-'],
    'BYGH': ['BYGH -','BYGH-']
  };

  var AF = { trade:'ALL', area:'ALL', type:'ALL' };

  function inTrade(tc, name, code) {
    if (code === 'ALL') return true;
    if (tc && tc !== 'OTHER') return tc === code;
    if (!TRADE_PFX[code]) return true;
    var u = (name||'').toUpperCase();
    return TRADE_PFX[code].some(function(p){ return u.indexOf(p.toUpperCase())===0; });
  }

  function matchAct(item) {
    if (!inTrade(item.trade_code, item.task_name, AF.trade)) return false;
    if (AF.area !== 'ALL' && (item.area||'') !== AF.area) return false;
    if (AF.type !== 'ALL' && (item.task_type||'') !== AF.type) return false;
    return true;
  }

  function filt(arr) { return (arr||[]).filter(matchAct); }

  function el(id){ return document.getElementById(id); }
  function pct(part, total) { return total > 0 ? Math.round((part / total) * 100) : 0; }
  function clamp(val, lo, hi) { return Math.max(lo, Math.min(hi, val)); }
  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function priLabel(p) {
    if ((p||'').indexOf('CRITICAL') >= 0) return ['CRITICAL','pd-pri-critical'];
    if ((p||'').indexOf('IMPORTANT') >= 0) return ['IMPORTANT','pd-pri-important'];
    return ['MONITOR','pd-pri-monitor'];
  }

  function typeStyle(t) {
    var styles = {
      'Coordination':{'color':'#7c3aed','bg':'#f5f3ff'},
      'Design':{'color':'#2563eb','bg':'#eff6ff'},
      'Bygherre':{'color':'#c026d3','bg':'#fdf4ff'},
      'Production':{'color':'#059669','bg':'#ecfdf5'},
      'Procurement':{'color':'#d97706','bg':'#fffbeb'},
      'Milestone':{'color':'#64748b','bg':'#f8fafc'}
    };
    return styles[t]||{'color':'#64748b','bg':'#f8fafc'};
  }

  function daysCell(days) {
    if (!days || days <= 0) return '<td></td>';
    var cls = days > 30 ? 'c-red' : days > 7 ? 'c-amber' : '';
    return '<td class="pd-days ' + cls + '">' + days + 'd</td>';
  }

  function areaBadge(area) {
    if (!area) return '';
    return '<span class="v5-loc-badge">' + area + '</span>';
  }

  function actRow(item) {
    var pl = priLabel(item.priority);
    var ts = typeStyle(item.task_type);
    return '<tr>' +
      '<td class="v5-act-name">' + (item.task_name||'') + '</td>' +
      '<td>' + areaBadge(item.area) + '</td>' +
      '<td><span class="pd-pri ' + pl[1] + '">' + pl[0] + '</span></td>' +
      '<td><span class="pd-type" style="color:' + ts.color + ';background:' + ts.bg + '">' + (item.task_type||'') + '</span></td>' +
      daysCell(item.days_overdue) +
      '</tr>';
  }

  function renderCritical(acts) {
    var hdr = el('pd-critical-hdr');
    if (hdr) hdr.textContent = LOC.criticalNow + ' (' + acts.length + ')';
    var tb = el('pd-critical-tbody');
    if (!tb) return;
    if (!acts.length) {
      tb.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">' + LOC.noCritical + ' ✓</td></tr>';
      return;
    }
    tb.innerHTML = acts.slice(0,30).map(actRow).join('');
  }

  function renderImportant(acts) {
    var hdr = el('pd-important-hdr');
    if (hdr) hdr.textContent = LOC.importantNext + ' (' + acts.length + ')';
    var tb = el('pd-important-tbody');
    if (!tb) return;
    if (!acts.length) {
      tb.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">' + LOC.noImportant + '</td></tr>';
      return;
    }
    tb.innerHTML = acts.slice(0,30).map(actRow).join('');
  }

  function renderMonitor(acts) {
    var hdr = el('pd-monitor-hdr');
    if (hdr) hdr.textContent = LOC.monitor + ' (' + acts.length + ')';
    var tb = el('pd-monitor-tbody');
    if (!tb) return;
    if (!acts.length) {
      tb.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">' + LOC.noMonitor + '</td></tr>';
      return;
    }
    tb.innerHTML = acts.slice(0,50).map(actRow).join('');
  }

  function renderAllDelayed(acts) {
    var hdr = el('pd-all-hdr');
    if (hdr) hdr.textContent = LOC.allDelayed + ' (' + acts.length + ')';
    var tb = el('pd-all-tbody');
    if (!tb) return;
    if (!acts.length) {
      tb.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#64748b;padding:14px">' + LOC.noDelayedMatch + '</td></tr>';
      return;
    }
    tb.innerHTML = acts.map(actRow).join('');
  }

  function renderKPIs(filtered, critical, important, monitor) {
    var ec = el('pd-kpi-critical'); if (ec) ec.textContent = critical.length;
    var ei = el('pd-kpi-important'); if (ei) ei.textContent = important.length;
    var em = el('pd-kpi-monitor'); if (em) em.textContent = monitor.length;
    var ed = el('pd-kpi-delayed'); if (ed) ed.textContent = filtered.length;
  }

  function updateFilterCounts(all) {
    document.querySelectorAll('[data-filter-dim]').forEach(function(opt) {
      var dim = opt.getAttribute('data-filter-dim');
      var val = opt.getAttribute('data-filter-val');
      var cntEl = opt.querySelector('.v5-filter-count');
      if (!cntEl) return;
      if (val === 'ALL') {
        cntEl.textContent = all.length;
        return;
      }
      var saved = AF[dim];
      AF[dim] = val;
      var cnt = filt(all).length;
      AF[dim] = saved;
      cntEl.textContent = cnt;
    });
  }

  function bucketData(acts) {
    var defs = [
      { key:'b0', label:'0-7d', min:0, max:7, cls:'good' },
      { key:'b1', label:'8-30d', min:8, max:30, cls:'warn' },
      { key:'b2', label:'31-60d', min:31, max:60, cls:'warn' },
      { key:'b3', label:'61-90d', min:61, max:90, cls:'bad' },
      { key:'b4', label:'91+d', min:91, max:100000, cls:'bad' }
    ];
    defs.forEach(function(d){ d.count = 0; });
    acts.forEach(function(act) {
      var days = Number(act.days_overdue || 0);
      defs.some(function(d) {
        if (days >= d.min && days <= d.max) {
          d.count += 1;
          return true;
        }
        return false;
      });
    });
    return defs;
  }

  function renderOverdueBars(acts) {
    var hdr = el('pd-overdue-bars-hdr');
    if (hdr) hdr.textContent = LOC.overdueMix + ' (' + acts.length + ')';
    var sub = el('pd-overdue-bars-sub');
    if (sub) sub.textContent = LOC.overdueBarSub;
    var wrap = el('pd-overdue-bars');
    if (!wrap) return;
    if (!acts.length) {
      wrap.innerHTML = '<p style="color:#64748b;font-size:12px;padding:8px 0">' + LOC.noChartData + '</p>';
      return;
    }
    var buckets = bucketData(acts);
    var maxVal = Math.max.apply(null, buckets.map(function(b){ return b.count; })) || 1;
    wrap.innerHTML = buckets.map(function(bucket) {
      var fillCls = bucket.cls === 'bad' ? 'pd-bar-fill-bad' : bucket.cls === 'warn' ? 'pd-bar-fill-warn' : 'pd-bar-fill-good';
      var width = Math.max((bucket.count / maxVal) * 100, bucket.count ? 6 : 0);
      return '<div class="pd-bar-row">' +
        '<div class="pd-bar-label">' + bucket.label + '</div>' +
        '<div class="pd-bar-track"><div class="pd-bar-fill ' + fillCls + '" style="width:' + width.toFixed(1) + '%"></div></div>' +
        '<div class="pd-bar-value">' + bucket.count + '</div>' +
      '</div>';
    }).join('');
  }

  function renderAreaBars(acts) {
    var hdr = el('pd-area-bars-hdr');
    var wrap = el('pd-area-bars');
    if (hdr) hdr.textContent = LOC.riskByArea + ' (' + acts.length + ')';
    if (!wrap) return;
    if (!acts.length) {
      wrap.innerHTML = '<p style="color:#64748b;font-size:12px;padding:8px 0">' + LOC.noChartData + '</p>';
      return;
    }

    var areas = {};
    acts.forEach(function(act) {
      var key = (act.area || 'Unassigned').trim() || 'Unassigned';
      if (!areas[key]) areas[key] = { label:key, count:0, critical:0 };
      areas[key].count += 1;
      if ((act.priority || '').indexOf('CRITICAL') >= 0) areas[key].critical += 1;
    });

    var rows = Object.keys(areas).map(function(key) { return areas[key]; })
      .sort(function(a, b) {
        if (b.count !== a.count) return b.count - a.count;
        return b.critical - a.critical;
      })
      .slice(0, 7);

    var maxVal = Math.max.apply(null, rows.map(function(r){ return r.count; })) || 1;
    wrap.innerHTML = rows.map(function(row) {
      var width = Math.max((row.count / maxVal) * 100, row.count ? 8 : 0);
      var fillCls = row.critical > 0 ? 'pd-bar-fill-bad' : row.count >= 3 ? 'pd-bar-fill-warn' : 'pd-bar-fill';
      return '<div class="pd-bar-row">' +
        '<div class="pd-bar-label" title="' + esc(row.label) + '">' + esc(row.label) + '</div>' +
        '<div class="pd-bar-track"><div class="pd-bar-fill ' + fillCls + '" style="width:' + width.toFixed(1) + '%"></div></div>' +
        '<div class="pd-bar-value">' + row.count + '</div>' +
      '</div>';
    }).join('');
  }

  function renderDelayCurve(acts) {
    var actualEl = el('pd-curve-actual');
    var targetEl = el('pd-curve-target');
    var gapEl = el('pd-curve-gap');
    var noteEl = el('pd-curve-note');
    var pathActual = el('pd-delay-curve-actual');
    var pathTarget = el('pd-delay-curve-target');
    var points = el('pd-delay-curve-points');
    var grid = el('pd-delay-curve-grid');

    if (!pathActual || !pathTarget || !points || !grid) return;

    if (!acts.length) {
      if (actualEl) actualEl.textContent = '0%';
      if (targetEl) targetEl.textContent = '0%';
      if (gapEl) {
        gapEl.textContent = '0 pp';
        gapEl.className = 'pd-chart-chip-value good';
      }
      if (noteEl) noteEl.textContent = LOC.noChartData;
      var severeEmptyEl = el('pd-curve-severe');
      var criticalEmptyEl = el('pd-curve-critical');
      if (severeEmptyEl) severeEmptyEl.textContent = '0';
      if (criticalEmptyEl) criticalEmptyEl.textContent = '0';
      pathActual.setAttribute('d', '');
      pathTarget.setAttribute('d', '');
      points.innerHTML = '';
      grid.innerHTML = '';
      return;
    }

    var thresholds = [7, 14, 30, 60, 90, 120];
    var labels = ['7d', '14d', '30d', '60d', '90d', '120+d'];
    var target = [28, 44, 68, 86, 95, 100];
    var actual = thresholds.map(function(limit) {
      var count = acts.filter(function(act) {
        return Number(act.days_overdue || 0) <= limit;
      }).length;
      return pct(count, acts.length);
    });

    var actual30 = actual[2] || 0;
    var severe60 = acts.filter(function(act) { return Number(act.days_overdue || 0) >= 60; }).length;
    var severe90 = acts.filter(function(act) { return Number(act.days_overdue || 0) >= 90; }).length;
    var gap = actual30 - target[2];

    if (actualEl) actualEl.textContent = actual30 + '%';
    if (targetEl) targetEl.textContent = target[2] + '%';
    if (gapEl) {
      gapEl.textContent = (gap >= 0 ? '+' : '') + gap + ' pp';
      gapEl.className = 'pd-chart-chip-value ' + (gap >= 0 ? 'good' : 'bad');
    }
    if (noteEl) {
      noteEl.textContent = LOC.severeBacklog + ': ' + severe60 + ' ' + LOC.over60;
    }

    var left = 48, top = 22, width = 664, height = 176;

    function point(v, idx) {
      return {
        x: left + (width / (actual.length - 1)) * idx,
        y: top + height - (clamp(v, 0, 100) / 100) * height
      };
    }

    function curvePath(values) {
      var pts = values.map(point);
      var d = 'M ' + pts[0].x.toFixed(1) + ' ' + pts[0].y.toFixed(1);
      for (var i = 1; i < pts.length; i++) {
        var prev = pts[i - 1];
        var cur = pts[i];
        var mid = (prev.x + cur.x) / 2;
        d += ' C ' + mid.toFixed(1) + ' ' + prev.y.toFixed(1) + ' ' + mid.toFixed(1) + ' ' + cur.y.toFixed(1) + ' ' + cur.x.toFixed(1) + ' ' + cur.y.toFixed(1);
      }
      return d;
    }

    grid.innerHTML = [0, 25, 50, 75, 100].map(function(v) {
      var y = top + height - (v / 100) * height;
      return '<line class="pd-curve-grid" x1="' + left + '" y1="' + y.toFixed(1) + '" x2="' + (left + width) + '" y2="' + y.toFixed(1) + '"></line>' +
        '<text class="pd-curve-axis-label" x="14" y="' + (y + 4).toFixed(1) + '">' + v + '%</text>';
    }).join('') + labels.map(function(lbl, idx) {
      var x = left + (width / (labels.length - 1)) * idx;
      return '<text class="pd-curve-axis-label" text-anchor="middle" x="' + x.toFixed(1) + '" y="228">' + lbl + '</text>';
    }).join('');

    pathTarget.setAttribute('d', curvePath(target));
    pathActual.setAttribute('d', curvePath(actual));
    points.innerHTML = target.map(function(v, idx) {
      var p = point(v, idx);
      return '<circle class="pd-curve-target-point" cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="3"></circle>';
    }).join('') + actual.map(function(v, idx) {
      var p = point(v, idx);
      return '<circle class="pd-curve-point" cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="' + (idx === actual.length - 1 ? 5 : 4) + '"></circle>';
    }).join('');

    var severeEl = el('pd-curve-severe');
    var criticalEl = el('pd-curve-critical');
    if (severeEl) severeEl.textContent = severe60;
    if (criticalEl) criticalEl.textContent = severe90;
  }

  function render() {
    var all = D.delayed_activities || [];
    var filtered = filt(all);
    var critical  = filtered.filter(function(i){ return (i.priority||'').indexOf('CRITICAL') >= 0; });
    var important = filtered.filter(function(i){ return (i.priority||'').indexOf('IMPORTANT') >= 0; });
    var monitor   = filtered.filter(function(i){ return (i.priority||'').indexOf('MONITOR') >= 0; });

    renderKPIs(filtered, critical, important, monitor);
    renderDelayCurve(filtered);
    renderAreaBars(filtered);
    renderOverdueBars(filtered);
    renderCritical(critical);
    renderImportant(important);
    renderMonitor(monitor);
    renderAllDelayed(filtered);
    updateFilterCounts(all);
  }

  window.pdSetFilter = function(dim, val) {
    AF[dim] = val;
    document.querySelectorAll('[data-filter-dim="' + dim + '"]').forEach(function(opt) {
      opt.classList.toggle('active', opt.getAttribute('data-filter-val') === val);
    });
    render();
  };

  document.addEventListener('DOMContentLoaded', function(){ render(); });
  if (document.readyState !== 'loading') { render(); }
})();
"""


# ── Build dashboard data payload ──────────────────────────────────────────────

def _build_dashboard_data(predictive_json: dict) -> dict:
    delayed = predictive_json.get("delayed_activities", [])
    for act in delayed:
        act["trade_code"] = _infer_trade(act.get("task_name", ""))

    areas = sorted(set(a.get("area", "").strip() for a in delayed if a.get("area", "").strip()))
    trades_present = sorted(set(a["trade_code"] for a in delayed if a.get("trade_code") and a["trade_code"] != "OTHER"))
    task_types_present = sorted(set(a.get("task_type", "") for a in delayed if a.get("task_type")))

    drivers_raw = predictive_json.get("predictive_snapshot", {}).get("main_delay_drivers", [])

    return {
        "insight_data": predictive_json.get("insight_data", {}),
        "schedule_overview": predictive_json.get("schedule_overview", {}),
        "delayed_activities": delayed,
        "root_cause_analysis": predictive_json.get("root_cause_analysis", []),
        "executive_actions": predictive_json.get("executive_actions", []),
        "summary_by_area": predictive_json.get("summary_by_area", []),
        "predictive_snapshot": predictive_json.get("predictive_snapshot", {}),
        "management_conclusion": predictive_json.get("management_conclusion", ""),
        "delay_drivers": drivers_raw,
        "filter_options": {
            "areas": areas,
            "trades": trades_present,
            "task_types": task_types_present,
        },
    }


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _sidebar(data: dict, da: bool) -> str:
    fo = data.get("filter_options", {})
    areas = fo.get("areas", [])
    trades = fo.get("trades", [])
    types = fo.get("task_types", [])

    trade_lbl = "Fag / Trade" if da else "Trade"
    area_lbl = "Område / Area" if da else "Area"
    type_lbl = "Opgavetype" if da else "Task Type"

    parts = ['<div class="v5-sidebar">']

    # Trade filter (only if trades detected)
    if trades:
        parts.append(f'<div class="v5-filter-group">')
        parts.append(f'<p class="v5-filter-group-title">{trade_lbl}</p>')
        parts.append('<div class="v5-filter-opts">')
        for code in ["ALL"] + trades:
            lbl = code if code != "ALL" else ("Alle fag" if da else "All Trades")
            parts.append(
                f'<div class="v5-filter-opt active" data-filter-dim="trade" data-filter-val="{code}" '
                f'onclick="pdSetFilter(\'trade\',\'{code}\')">'
                f'<span class="v5-filter-opt-dot"></span>{lbl}'
                f'<span class="v5-filter-count"></span></div>'
            )
        parts.append('</div></div>')
        parts.append('<div class="v5-sidebar-divider"></div>')

    # Area filter
    if areas:
        parts.append('<div class="v5-filter-group">')
        parts.append(f'<p class="v5-filter-group-title">{area_lbl}</p>')
        parts.append('<div class="v5-filter-opts">')
        all_lbl = "Alle områder" if da else "All Areas"
        parts.append(
            f'<div class="v5-filter-opt active" data-filter-dim="area" data-filter-val="ALL" '
            f'onclick="pdSetFilter(\'area\',\'ALL\')">'
            f'<span class="v5-filter-opt-dot"></span>{all_lbl}'
            f'<span class="v5-filter-count"></span></div>'
        )
        for area in areas[:20]:
            ea = _html.escape(area)
            parts.append(
                f'<div class="v5-filter-opt" data-filter-dim="area" data-filter-val="{ea}" '
                f'onclick="pdSetFilter(\'area\',\'{ea}\')">'
                f'<span class="v5-filter-opt-dot"></span>{ea}'
                f'<span class="v5-filter-count"></span></div>'
            )
        parts.append('</div></div>')
        parts.append('<div class="v5-sidebar-divider"></div>')

    # Task Type filter
    if types:
        parts.append('<div class="v5-filter-group">')
        parts.append(f'<p class="v5-filter-group-title">{type_lbl}</p>')
        parts.append('<div class="v5-filter-opts">')
        all_lbl = "Alle typer" if da else "All Types"
        parts.append(
            f'<div class="v5-filter-opt active" data-filter-dim="type" data-filter-val="ALL" '
            f'onclick="pdSetFilter(\'type\',\'ALL\')">'
            f'<span class="v5-filter-opt-dot"></span>{all_lbl}'
            f'<span class="v5-filter-count"></span></div>'
        )
        for tt in types:
            et = _html.escape(tt)
            parts.append(
                f'<div class="v5-filter-opt" data-filter-dim="type" data-filter-val="{et}" '
                f'onclick="pdSetFilter(\'type\',\'{et}\')">'
                f'<span class="v5-filter-opt-dot"></span>{et}'
                f'<span class="v5-filter-count"></span></div>'
            )
        parts.append('</div></div>')

    parts.append('</div>')
    return "\n".join(parts)


# ── Card builders ─────────────────────────────────────────────────────────────

def _activity_table_header(da: bool) -> str:
    lbl_task = "Opgave" if da else "Task"
    lbl_area = "Område" if da else "Area"
    lbl_pri  = "Prioritet" if da else "Priority"
    lbl_type = "Type"
    lbl_days = "Dage over" if da else "Overdue"
    return (
        f'<thead><tr>'
        f'<th>{lbl_task}</th><th>{lbl_area}</th>'
        f'<th>{lbl_pri}</th><th>{lbl_type}</th><th>{lbl_days}</th>'
        f'</tr></thead>'
    )


def _card_critical_now(da: bool) -> str:
    title = "Kritisk Nu" if da else "Critical Now"
    sub = "Kræver øjeblikkelig handling" if da else "Requires immediate action"
    hdr = _activity_table_header(da)
    return f"""
<div class="v5-card pd-critical-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#dc2626">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
    </div>
    <div>
      <p class="v5-card-title" id="pd-critical-hdr">{title}</p>
      <p class="v5-card-sub">{sub}</p>
    </div>
  </div>
  <div class="v5-scroll-wrap">
    <table class="v5-table">{hdr}<tbody id="pd-critical-tbody"></tbody></table>
  </div>
</div>"""


def _card_important_next(da: bool) -> str:
    title = "Vigtig Næste" if da else "Important Next"
    sub = "Adresser inden for 2 uger" if da else "Address within 2 weeks"
    hdr = _activity_table_header(da)
    return f"""
<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#d97706">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
    </div>
    <div>
      <p class="v5-card-title" id="pd-important-hdr">{title}</p>
      <p class="v5-card-sub">{sub}</p>
    </div>
  </div>
  <div class="v5-scroll-wrap">
    <table class="v5-table">{hdr}<tbody id="pd-important-tbody"></tbody></table>
  </div>
</div>"""


def _card_root_causes(root_causes: list, da: bool) -> str:
    title = "Rodårsager til forsinkelser" if da else "Root Causes of Delays"
    sub = "Hvad driver alle forsinkelserne" if da else "What is driving all the delays"
    if not root_causes:
        body = '<p style="color:#64748b;font-size:12px;padding:8px 0">Ingen rodårsager identificeret</p>' if da else '<p style="color:#64748b;font-size:12px;padding:8px 0">No root causes identified</p>'
    else:
        items = []
        for rc in root_causes[:8]:
            pt_icon = {
                "Coordination blockage": "🔗",
                "Design input missing": "✏️",
                "Bygherre decision pending": "👤",
                "Production delay": "🔧",
                "Procurement delay": "📦",
            }.get(rc.get("problem_type", ""), "⚠️")
            days = _si(rc.get("days_overdue", 0))
            days_str = f'<span style="color:#dc2626;font-weight:700">{days}d overdue</span>' if days > 0 else ""
            consequences = _e(rc.get("consequence_if_unresolved", ""))
            why = _e(rc.get("why_it_matters", ""))
            downstream = _e(rc.get("downstream_impact", ""))
            task_name = _e(rc.get("task_name", ""))
            human_label = _e(rc.get("human_label", ""))
            task_id = _e(rc.get("id", ""))
            items.append(f"""
<div class="pd-rc-item">
  <div class="pd-rc-id">{pt_icon} ID {task_id} — {rc.get("problem_type","")}</div>
  <div class="pd-rc-title">{task_name}</div>
  {"<div class='pd-rc-why'>"+human_label+"</div>" if human_label else ""}
  <div style="display:flex;align-items:center;gap:8px;margin:3px 0">{days_str}</div>
  {"<div class='pd-rc-why'>"+why+"</div>" if why else ""}
  {"<div class='pd-rc-downstream'>↳ "+downstream+"</div>" if downstream else ""}
  {"<div class='pd-rc-consequence'>⛔ "+consequences+"</div>" if consequences else ""}
</div>""")
        body = "\n".join(items)

    return f"""
<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#7c3aed">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
    </div>
    <div>
      <p class="v5-card-title">{title}</p>
      <p class="v5-card-sub">{sub}</p>
    </div>
  </div>
  {body}
</div>"""


def _card_executive_actions(actions: list, da: bool) -> str:
    title = "Hvad skal du gøre nu" if da else "What Should You Do Now"
    sub = "Top 3 handlinger for projektledelsen" if da else "Top 3 actions for project management"
    if not actions:
        body = '<p style="color:#64748b;font-size:12px;padding:8px 0">Ingen handlinger</p>'
    else:
        rank_cls = {1: "", 2: " pd-action-rank-2", 3: " pd-action-rank-3"}
        items = []
        for act in actions[:3]:
            r = _si(act.get("rank", 1))
            rc = rank_cls.get(r, "")
            action_text = _e(act.get("action", ""))
            responsible = _e(act.get("responsible", ""))
            deadline = _e(act.get("deadline", ""))
            manpower_helps = act.get("manpower_helps", False)
            manpower_note = _e(act.get("manpower_note", ""))
            mp_icon = "✅" if manpower_helps else "❌"
            mp_lbl = ("Ekstra mandskab hjælper" if da else "Extra manpower helps") if manpower_helps else ("Ekstra mandskab hjælper ikke" if da else "Extra manpower won't help")
            items.append(f"""
<div class="pd-action-item">
  <div class="pd-action-rank{rc}">{r}</div>
  <div class="pd-action-body">
    <div class="pd-action-text">{action_text}</div>
    <div class="pd-action-meta">
      <strong>{"Ansvarlig" if da else "Who"}:</strong> {responsible} &nbsp;·&nbsp;
      <strong>{"Deadline" if da else "When"}:</strong> {deadline}
    </div>
    {f'<div class="pd-action-manpower">{mp_icon} {mp_lbl} — {manpower_note}</div>' if manpower_note else ''}
  </div>
</div>""")
        body = "\n".join(items)

    return f"""
<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#059669">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/></svg>
    </div>
    <div>
      <p class="v5-card-title">{title}</p>
      <p class="v5-card-sub">{sub}</p>
    </div>
  </div>
  {body}
</div>"""


def _card_area_risk(summary_by_area: list, da: bool) -> str:
    title = "Risiko pr. område" if da else "Risk by Area"
    sub = "Hvilke dele af projektet er mest udsat" if da else "Which parts of the project are most at risk"
    if not summary_by_area:
        body = '<p style="color:#64748b;font-size:12px;padding:8px 0">Ingen områdedata</p>'
    else:
        items = []
        for entry in summary_by_area[:10]:
            area = _e(entry.get("area", ""))
            critical_c = _si(entry.get("critical_count", 0))
            important_c = _si(entry.get("important_count", 0))
            monitor_c = _si(entry.get("monitor_count", 0))
            summary_text = _e(entry.get("summary", ""))
            pills = []
            if critical_c:
                pills.append(f'<span class="pd-area-pill pd-area-pill-red">{critical_c} {"Kritisk" if da else "Critical"}</span>')
            if important_c:
                pills.append(f'<span class="pd-area-pill pd-area-pill-amber">{important_c} {"Vigtig" if da else "Important"}</span>')
            if monitor_c:
                pills.append(f'<span class="pd-area-pill pd-area-pill-blue">{monitor_c} {"Overvåg" if da else "Monitor"}</span>')
            items.append(f"""
<div class="pd-area-item">
  <div class="pd-area-name">{area}</div>
  <div class="pd-area-pills">{''.join(pills)}</div>
  {f'<div class="pd-area-summary">{summary_text}</div>' if summary_text else ''}
</div>""")
        body = "\n".join(items)

    return f"""
<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#0891b2">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>
    </div>
    <div>
      <p class="v5-card-title">{title}</p>
      <p class="v5-card-sub">{sub}</p>
    </div>
  </div>
  {body}
</div>"""


def _card_all_delayed(da: bool) -> str:
    title = "Alle forsinkede aktiviteter" if da else "All Delayed Activities"
    sub = "Filtreret efter valgte kriterier" if da else "Filtered by selected criteria"
    hdr = _activity_table_header(da)
    return f"""
<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#334155">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 16h8"/><path d="M7 11h12"/><path d="M7 6h3"/></svg>
    </div>
    <div>
      <p class="v5-card-title" id="pd-all-hdr">{title}</p>
      <p class="v5-card-sub">{sub}</p>
    </div>
  </div>
  <div class="pd-full-table-wrap">
    <table class="v5-table">{hdr}<tbody id="pd-all-tbody"></tbody></table>
  </div>
</div>"""


def _card_monitor(da: bool) -> str:
    title = "Overvåg" if da else "Monitor"
    sub = "Ikke kritisk endnu, men hold øje" if da else "Not critical yet — keep an eye on these"
    hdr = _activity_table_header(da)
    return f"""
<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#0891b2">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/></svg>
    </div>
    <div>
      <p class="v5-card-title" id="pd-monitor-hdr">{title}</p>
      <p class="v5-card-sub">{sub}</p>
    </div>
  </div>
  <div class="v5-scroll-wrap">
    <table class="v5-table">{hdr}<tbody id="pd-monitor-tbody"></tbody></table>
  </div>
</div>"""


def _card_delay_curve(da: bool) -> str:
    title = "Forsinkelseskurve" if da else "Delay Aging Curve"
    sub = "Hvor hurtigt forsinkelserne vokser ind i ældre bucket-niveauer" if da else "How quickly delays age into older overdue buckets"
    actual_lbl = "Aktuel <=30d" if da else "Current <=30d"
    target_lbl = "Mål <=30d" if da else "Target <=30d"
    gap_lbl = "Gap" if da else "Gap"
    severe_lbl = "60+d" if da else "60+d"
    critical_lbl = "90+d" if da else "90+d"
    note_lbl = "Alvorlig backlog" if da else "Severe backlog"
    target_line = "Mål" if da else "Target"
    actual_line = "Aktuel" if da else "Current"
    note_empty = "Ingen data" if da else "No data"
    return f"""
<div class="v5-card pd-chart-card">
  <div class="pd-chart-head">
    <div style="display:flex;align-items:center;gap:8px;">
      <div class="v5-card-icon" style="background:linear-gradient(135deg,#2563eb,#1d4ed8)">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
      </div>
      <div>
        <p class="v5-card-title">{title}</p>
        <p class="v5-card-sub">{sub}</p>
      </div>
    </div>
    <div class="pd-chart-metrics">
      <div class="pd-chart-chip">
        <span class="pd-chart-chip-label">{actual_lbl}</span>
        <span class="pd-chart-chip-value" id="pd-curve-actual">0%</span>
      </div>
      <div class="pd-chart-chip">
        <span class="pd-chart-chip-label">{target_lbl}</span>
        <span class="pd-chart-chip-value" id="pd-curve-target">0%</span>
      </div>
      <div class="pd-chart-chip">
        <span class="pd-chart-chip-label">{gap_lbl}</span>
        <span class="pd-chart-chip-value" id="pd-curve-gap">0 pp</span>
      </div>
      <div class="pd-chart-chip">
        <span class="pd-chart-chip-label">{severe_lbl}</span>
        <span class="pd-chart-chip-value bad" id="pd-curve-severe">0</span>
      </div>
      <div class="pd-chart-chip">
        <span class="pd-chart-chip-label">{critical_lbl}</span>
        <span class="pd-chart-chip-value bad" id="pd-curve-critical">0</span>
      </div>
    </div>
  </div>
  <div class="pd-curve-wrap">
    <svg id="pd-delay-curve" viewBox="0 0 760 250" role="img" aria-label="{title}">
      <rect class="pd-curve-zone-good" x="48" y="22" width="664" height="52"></rect>
      <rect class="pd-curve-zone-warn" x="48" y="74" width="664" height="52"></rect>
      <rect class="pd-curve-zone-bad" x="48" y="126" width="664" height="72"></rect>
      <g id="pd-delay-curve-grid"></g>
      <path id="pd-delay-curve-target" class="pd-curve-target" d=""></path>
      <path id="pd-delay-curve-actual" class="pd-curve-actual" d=""></path>
      <g id="pd-delay-curve-points"></g>
    </svg>
  </div>
  <div class="pd-curve-legend">
    <span><span class="pd-legend-line target"></span>{target_line}</span>
    <span><span class="pd-legend-line"></span>{actual_line}</span>
    <span class="pd-delay-note">{note_lbl}: <strong id="pd-curve-note">{note_empty}</strong></span>
  </div>
</div>"""


def _card_area_bars(da: bool) -> str:
    title = "Risiko pr. område" if da else "Risk by Area"
    sub = "Filtreret antal forsinkede aktiviteter pr. område" if da else "Filtered delayed activity count by area"
    return f"""
<div class="v5-card pd-chart-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#0891b2">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>
    </div>
    <div>
      <p class="v5-card-title" id="pd-area-bars-hdr">{title}</p>
      <p class="v5-card-sub">{sub}</p>
    </div>
  </div>
  <div class="pd-bar-list" id="pd-area-bars"></div>
</div>"""


def _card_overdue_bars(da: bool) -> str:
    title = "Forsinkelsesfordeling" if da else "Overdue Distribution"
    sub = "Antal forsinkede aktiviteter i hver forsinkelsesgruppe" if da else "Delayed activity count in each overdue bucket"
    return f"""
<div class="v5-card pd-chart-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#d97706">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 16h8"/><path d="M7 11h12"/><path d="M7 6h3"/></svg>
    </div>
    <div>
      <p class="v5-card-title" id="pd-overdue-bars-hdr">{title}</p>
      <p class="v5-card-sub" id="pd-overdue-bars-sub">{sub}</p>
    </div>
  </div>
  <div class="pd-bar-list" id="pd-overdue-bars"></div>
</div>"""


def _card_delay_drivers(drivers: list, snapshot: dict, conclusion: str, da: bool) -> str:
    title = "Forsinkelsesdrivere & prognose" if da else "Delay Drivers & Forecast"
    sub = "Hvad driver forsinkelserne, og hvad forventes at ske" if da else "What is driving delays and what is expected to happen"

    driver_html = ""
    if drivers:
        driver_items = []
        for d in drivers:
            driver_items.append(f'<div class="pd-driver-item"><div class="pd-driver-text">◆ {_e(str(d))}</div></div>')
        driver_html = "\n".join(driver_items)
    else:
        driver_html = f'<p style="color:#64748b;font-size:11px">{"Ingen driverdata" if da else "No driver data available"}</p>'

    what_will = _e(snapshot.get("what_will_happen", ""))
    delay_impact = _e(snapshot.get("estimated_delay_impact", ""))
    confidence = _e(snapshot.get("confidence_level", ""))

    snapshot_html = ""
    if what_will:
        snapshot_html = f"""
<div class="pd-snapshot-box" style="margin-top:12px">
  <div class="pd-snapshot-headline">
    {"Prognose" if da else "Forecast"} — {delay_impact} &nbsp;<span style="font-size:10px;color:#b45309;font-weight:600">({confidence} {"konfidenstillid" if da else "confidence"})</span>
  </div>
  <div class="pd-snapshot-text">{what_will}</div>
</div>"""

    conclusion_html = ""
    if conclusion:
        conclusion_html = f"""
<div style="margin-top:12px;padding:10px 12px;background:#f8fafc;border-radius:7px;border:1px solid #e2e8f0">
  <div style="font-size:9px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#94a3b8;margin-bottom:5px">
    {"Ledelseskonklusion" if da else "Management Conclusion"}
  </div>
  <div style="font-size:11.5px;color:#334155;line-height:1.5">{_e(conclusion)}</div>
</div>"""

    return f"""
<div class="v5-card">
  <div class="v5-card-header">
    <div class="v5-card-icon" style="background:#f59e0b">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
    </div>
    <div>
      <p class="v5-card-title">{title}</p>
      <p class="v5-card-sub">{sub}</p>
    </div>
  </div>
  {driver_html}
  {snapshot_html}
  {conclusion_html}
</div>"""


# ── Main formatter ────────────────────────────────────────────────────────────

def format_predictive_as_dashboard_html(predictive_json: dict, language: str = "en") -> str:
    da = language == "da"

    data = _build_dashboard_data(predictive_json)
    data["language"] = language
    id_data = data.get("insight_data", {})
    so = data.get("schedule_overview", {})
    snapshot = data.get("predictive_snapshot", {})
    conclusion = data.get("management_conclusion", "")
    root_causes = data.get("root_cause_analysis", [])
    exec_actions = data.get("executive_actions", [])
    area_summary = data.get("summary_by_area", [])
    drivers = data.get("delay_drivers", [])

    project_status = str(id_data.get("project_status", "AT_RISK"))
    badge_cls, dot_cls, status_lbl = _status_cfg(project_status, da)
    schedule_name = _e(id_data.get("schedule_name", so.get("schedule_name", "")))
    ref_date = _e(id_data.get("reference_date", so.get("reference_date", "")))
    total = _si(id_data.get("total_activities", so.get("total_activities", 0)))
    delayed_count = _si(id_data.get("delayed_count", 0))
    critical_count = _si(id_data.get("critical_count", 0))
    important_count = _si(id_data.get("important_count", 0))
    monitor_count = _si(id_data.get("monitor_count", 0))
    most_overdue = _si(id_data.get("most_overdue_days", 0))
    areas_affected = _si(id_data.get("areas_affected", 0))

    json_str = _json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    header_title = "RISIKO-DASHBOARD" if da else "RISK DASHBOARD"
    header_sub = "Hvad er bagud? Hvad er kritisk? Hvad skal du gøre?" if da else "What's behind? What's critical? What needs action?"

    parts: list[str] = []
    a = parts.append

    a(f"<style>{_CSS}</style>")
    a(f"<script>window.__pdData = {json_str};</script>")
    a('<div class="v5">')

    # ── Header ────────────────────────────────────────────────────────────────
    a(f'''<div class="v5-header">
  <div class="v5-logo">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>
      <path d="M12 9v4"/><path d="M12 17h.01"/>
    </svg>
  </div>
  <div class="v5-header-text">
    <p class="v5-header-brand">Nova Insight</p>
    <h1 class="v5-header-title">{header_title} — {schedule_name}</h1>
    <p class="v5-header-sub">{header_sub} &nbsp;·&nbsp; {"Referencedato" if da else "Reference date"}: {ref_date}</p>
  </div>
  <div style="margin-left:auto">
    <span class="v5-badge {badge_cls}">
      <span class="v5-dot {dot_cls}"></span>{status_lbl}
    </span>
  </div>
</div>''')

    # ── Hero KPI pills ────────────────────────────────────────────────────────
    a('<div class="v5-hero">')
    a(f'<p class="v5-hero-label">{"Projektstatus overblik" if da else "Project Status Overview"}</p>')
    a('<div class="v5-kpi-row">')

    def kpi(num_id, num_val, lbl, sub, bg_color, icon_path):
        return f'''<div class="v5-kpi-pill">
  <div class="v5-kpi-icon" style="background:{bg_color}">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">{icon_path}</svg>
  </div>
  <div class="v5-kpi-num" id="{num_id}">{num_val}</div>
  <div class="v5-kpi-lbl">{lbl}</div>
  <div class="v5-kpi-sub">{sub}</div>
</div>'''

    a(kpi("", total,
          "Aktiviteter" if da else "Total Activities",
          "i tidsplan" if da else "in schedule",
          "#64748b",
          '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 16h8"/><path d="M7 11h12"/><path d="M7 6h3"/>'))
    a(kpi("pd-kpi-delayed", delayed_count,
          "Forsinkede" if da else "Delayed",
          "aktiviteter" if da else "activities",
          "#dc2626" if delayed_count > 0 else "#059669",
          '<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>'))
    a(kpi("pd-kpi-critical", critical_count,
          "Kritisk Nu" if da else "Critical Now",
          "kræver handling" if da else "need action",
          "#b91c1c",
          '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>'))
    a(kpi("pd-kpi-important", important_count,
          "Vigtig Næste" if da else "Important Next",
          "adresser snart" if da else "address soon",
          "#d97706",
          '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'))
    a(kpi("pd-kpi-monitor", monitor_count,
          "Overvåg" if da else "Monitor",
          "lav risiko" if da else "low risk",
          "#0891b2",
          '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/>'))
    a(kpi("", most_overdue,
          "Maks. dage over" if da else "Most Overdue",
          "dage" if da else "calendar days",
          "#7c3aed",
          '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>'))
    a(kpi("", areas_affected,
          "Områder ramt" if da else "Areas Affected",
          "sektioner" if da else "project sections",
          "#0891b2",
          '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>'))

    a('</div></div>')

    # ── Page body ─────────────────────────────────────────────────────────────
    a('<div class="v5-page-body">')
    a(_sidebar(data, da))
    a('<div class="v5-main">')

    # Row 1: Delay Curve
    a(_card_delay_curve(da))

    # Row 2: Bar charts
    a('<div class="v5-row-2col">')
    a(_card_area_bars(da))
    a(_card_overdue_bars(da))
    a('</div>')

    # Row 3: Critical Now | Important Next
    a('<div class="v5-row-2col">')
    a(_card_critical_now(da))
    a(_card_important_next(da))
    a('</div>')

    # Row 4: Root Causes (full width)
    a(_card_root_causes(root_causes, da))

    # Row 5: Executive Actions | Area Risk
    a('<div class="v5-row-2col">')
    a(_card_executive_actions(exec_actions, da))
    a(_card_area_risk(area_summary, da))
    a('</div>')

    # Row 6: All Delayed Activities (full width)
    a(_card_all_delayed(da))

    # Row 7: Monitor + Delay Drivers
    a('<div class="v5-row-2col">')
    a(_card_monitor(da))
    a(_card_delay_drivers(drivers, snapshot, conclusion, da))
    a('</div>')

    a('</div>')  # .v5-main
    a('</div>')  # .v5-page-body
    a('</div>')  # .v5

    a(f"<script>{_JS}</script>")

    return "\n".join(parts)
