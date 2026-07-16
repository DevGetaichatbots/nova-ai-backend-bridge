from __future__ import annotations

import html as _html
import json as _json
import re as _re
from typing import Any

from .adapters import adapt_health_dashboard, adapt_predictive_dashboard
from .localization import lang_code, t


def _e(value: Any) -> str:
    return _html.escape(str(value)) if value is not None else ""


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.0f}%"
    except (TypeError, ValueError):
        return "0%"


def _tone_class(tone: str) -> str:
    if tone == "red":
        return "ni-red"
    if tone == "green":
        return "ni-green"
    if tone == "amber":
        return "ni-amber"
    if tone == "blue":
        return "ni-blue"
    return "ni-neutral"


def _change_type_cell(value: Any) -> str:
    """Render a comma-separated change_type string as stacked lines.

    Each property (e.g. 'Start Date', 'Finish Date') is placed in its own
    <div> with white-space:nowrap so multi-word labels never break mid-word.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) <= 1:
        return _e(raw)
    return "".join(f'<div style="white-space:nowrap">{_e(p)}</div>' for p in parts)


CSS = """
*{box-sizing:border-box}
.ni-v1{font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#f2f7f7;color:#14212b;line-height:1.35;-webkit-font-smoothing:antialiased}
.ni-header{height:62px;background:linear-gradient(90deg,#ffffff 0%,#f2fbfb 100%);border-bottom:1px solid #cfe4e7;display:flex;align-items:center;padding:0 22px;gap:12px}
.ni-logo{width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,#00b8b8,#0284c7);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900;box-shadow:0 8px 18px rgba(0,184,184,.18)}
.ni-brand{font-size:9px;font-weight:800;letter-spacing:1.8px;text-transform:uppercase;color:#008c8c;margin:0}
.ni-title{font-size:18px;font-weight:900;margin:0;color:#14212b;letter-spacing:0}
.ni-sub{font-size:11px;color:#71828f;margin:0}
.ni-status{margin-left:auto;padding:6px 12px;border-radius:999px;font-size:12px;font-weight:800;text-transform:uppercase}
.ni-status.stable{background:#e6f7ef;color:#047857}.ni-status.at_risk,.ni-status.at-risk{background:#fff3d6;color:#b45309}.ni-status.critical{background:#ffe4e6;color:#be123c}
.ni-kpis{display:grid;grid-template-columns:repeat(6,minmax(118px,1fr));gap:10px;padding:14px 18px;background:linear-gradient(180deg,#e9f7f8,#f5fafb);border-bottom:1px solid #cfe4e7}
.ni-kpi{background:#fff;border:1px solid #dcebed;border-top:3px solid #00a7a7;border-radius:8px;padding:10px 12px;min-height:86px;box-shadow:0 8px 22px rgba(15,82,92,.06)}
.ni-kpi-icon{width:24px;height:24px;border-radius:7px;margin-bottom:6px;display:flex;align-items:center;justify-content:center}
.ni-kpi-value{font-size:28px;font-weight:900;line-height:1}
.ni-kpi-label{margin-top:4px;font-size:10px;font-weight:800;color:#4c5f6b;text-transform:uppercase;letter-spacing:.25px}
.ni-neutral .ni-kpi-icon{background:#e7f2f4;color:#0f4f5a}.ni-neutral .ni-kpi-value{color:#14212b}
.ni-blue{border-top-color:#0284c7}.ni-blue .ni-kpi-icon{background:#dcf7ff;color:#0284c7}.ni-blue .ni-kpi-value{color:#0284c7}
.ni-red{border-top-color:#dc2626}.ni-red .ni-kpi-icon{background:#ffe4e6;color:#dc2626}.ni-red .ni-kpi-value{color:#dc2626}
.ni-green{border-top-color:#059669}.ni-green .ni-kpi-icon{background:#dcfce7;color:#059669}.ni-green .ni-kpi-value{color:#059669}
.ni-amber{border-top-color:#d97706}.ni-amber .ni-kpi-icon{background:#fef3c7;color:#d97706}.ni-amber .ni-kpi-value{color:#d97706}
.ni-body{display:flex;align-items:flex-start;min-height:700px}
.ni-sidebar{width:224px;min-width:224px;position:sticky;top:0;background:#fbfefe;border-right:1px solid #cfe4e7;padding:14px 12px;align-self:flex-start}
.ni-filter-title{font-size:10px;font-weight:900;letter-spacing:1.2px;text-transform:uppercase;color:#71828f;margin:0 0 10px}
.ni-filter-group{margin:0 0 16px}
.ni-filter-label{font-size:9px;font-weight:900;letter-spacing:1px;text-transform:uppercase;color:#7d8d97;margin:0 0 6px}
.ni-filter-opt{width:100%;display:flex;align-items:center;gap:7px;border:1px solid transparent;background:transparent;color:#263845;border-radius:6px;padding:6px 8px;font-size:11px;font-weight:650;text-align:left;cursor:pointer}
.ni-filter-opt:hover{background:#eefafa}.ni-filter-opt.active{background:#e0f7f8;border-color:#7ddfe5;color:#006b73}
.ni-filter-dot{width:8px;height:8px;border-radius:50%;background:#cbd5dc}.ni-filter-opt.active .ni-filter-dot{background:#00a7a7}
.ni-main{flex:1;min-width:0;padding:16px;display:flex;flex-direction:column;gap:14px}
.ni-warnings{background:#fff7ed;border:1px solid #fed7aa;border-left:4px solid #f97316;border-radius:7px;padding:10px 12px;color:#9a3412;font-size:12px;font-weight:700}
.ni-graph-card{background:linear-gradient(135deg,#06343b 0%,#0a4650 58%,#08313b 100%);border:1px solid #0e6770;border-radius:8px;padding:22px 24px 18px;color:#d7eeee;min-height:380px;box-shadow:0 18px 42px rgba(4,47,54,.20)}
.ni-graph-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:14px}
.ni-graph-title{font-size:18px;font-weight:850;letter-spacing:1.4px;text-transform:uppercase;margin:0;color:#eefefe}
.ni-graph-sub{font-size:12px;color:#9ed8dc;margin:4px 0 0}
.ni-graph-stats{display:grid;grid-template-columns:repeat(3,minmax(120px,1fr));gap:10px;margin:0 0 10px}.ni-graph-stat{border:1px solid rgba(151,221,226,.28);background:rgba(4,38,45,.45);border-radius:7px;padding:8px 10px}.ni-graph-stat span{display:block;font-size:9px;font-weight:900;text-transform:uppercase;letter-spacing:.55px;color:#9ed8dc}.ni-graph-stat strong{display:block;margin-top:2px;font-size:18px;line-height:1;color:#eefefe}.ni-graph-stat.delay strong{color:#fbbf24}
.ni-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;font-weight:800;color:#d5f4f5}
.ni-key{display:inline-flex;align-items:center;gap:6px}.ni-key span{width:12px;height:12px;display:inline-block;border-radius:2px}
.ni-key-actual{background:#00d6d6}.ni-key-planned{background:#b7cbd0}.ni-key-forecast{background:#38bdf8}.ni-key-delay{border:1px solid #f59e0b;background:repeating-linear-gradient(135deg,transparent 0,transparent 3px,rgba(245,158,11,.8) 3px,rgba(245,158,11,.8) 5px)}
.ni-graph-svg{width:100%;height:270px;display:block}.ni-grid{stroke:rgba(207,228,231,.18);stroke-width:1}.ni-axis{fill:#a8dce0;font-size:11px;font-weight:750}
.ni-planned{fill:none;stroke:#b7cbd0;stroke-width:3;stroke-linecap:round}.ni-actual{fill:none;stroke:#00d6d6;stroke-width:4;stroke-linecap:round;filter:drop-shadow(0 5px 10px rgba(0,214,214,.22))}.ni-forecast{fill:none;stroke:#38bdf8;stroke-width:3;stroke-linecap:round}
.ni-fill-actual{fill:url(#niActualFill);opacity:.85}.ni-fill-forecast{fill:url(#niForecastFill);opacity:.8}
.ni-gap-area{fill:url(#niGapFill);opacity:.9}
.ni-gap-line{stroke:#f59e0b;stroke-width:3;stroke-linecap:round;filter:drop-shadow(0 3px 8px rgba(245,158,11,.35))}.ni-point-actual{fill:#00d6d6;stroke:#053a43;stroke-width:3}.ni-point-planned{fill:#b7cbd0;stroke:#053a43;stroke-width:3}.ni-point-label{fill:#eaffff;font-size:12px;font-weight:900}.ni-point-label.planned{fill:#d8eaee}.ni-today{stroke:#e2ffff;stroke-width:2;stroke-dasharray:3 5}.ni-callout{fill:#07323a;stroke:#4db9c2;stroke-width:1}.ni-callout-text{fill:#eefefe;font-size:13px;font-weight:800}
.ni-empty-graph{height:250px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(168,220,224,.35);color:#c8eeee;font-weight:800}
.ni-section{background:#fff;border:1px solid #dcebed;border-left:4px solid #00a7a7;border-radius:8px;padding:14px;box-shadow:0 8px 22px rgba(15,82,92,.05)}
.ni-section-red{border-left-color:#dc2626}.ni-section-green{border-left-color:#059669}.ni-section-amber{border-left-color:#d97706}.ni-section-blue{border-left-color:#0284c7}.ni-section-teal{border-left-color:#00a7a7}
.ni-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:10px}
.ni-title-wrap{display:flex;align-items:center;gap:8px}.ni-section-icon{width:26px;height:26px;border-radius:7px;background:#e0f7f8;color:#008c8c;display:flex;align-items:center;justify-content:center;flex-shrink:0}.ni-section-icon.red{background:#ffe4e6;color:#dc2626}.ni-section-icon.green{background:#dcfce7;color:#059669}.ni-section-icon.amber{background:#fef3c7;color:#d97706}.ni-section-icon.blue{background:#dcf7ff;color:#0284c7}
.ni-section-title{font-size:13px;font-weight:900;margin:0;color:#14212b;text-transform:uppercase;letter-spacing:.8px}
.ni-section-sub{font-size:11px;color:#71828f;margin:2px 0 0}
.ni-progress-list{display:grid;grid-template-columns:minmax(170px,240px) 1fr 64px;gap:10px;align-items:center}
.ni-progress-row{display:contents}.ni-progress-label{font-size:12px;font-weight:850;color:#263845;padding:7px 0}.ni-progress-track{height:14px;background:#e3eef0;overflow:hidden;border-radius:3px}.ni-progress-bar{height:100%;background:linear-gradient(90deg,#008c8c,#00c2c2);border-radius:3px}.ni-progress-value{font-size:12px;font-weight:900;text-align:right}
.ni-actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.ni-action{border:1px solid #cfe4e7;border-left:3px solid #00a7a7;border-radius:7px;padding:10px;background:#f8fefe}.ni-action-rank{width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,#00a7a7,#0284c7);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:12px;margin-bottom:8px}.ni-action-text{font-size:12px;font-weight:800;color:#14212b}.ni-action-meta{font-size:11px;color:#63737c;margin-top:6px}
.ni-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:10px}.ni-summary-item{border:1px solid #dcebed;border-left:3px solid #00a7a7;border-radius:7px;background:#f8fefe;padding:9px 10px}.ni-summary-label{font-size:9px;text-transform:uppercase;letter-spacing:.35px;font-weight:900;color:#71828f}.ni-summary-value{margin-top:3px;font-size:15px;font-weight:900;color:#14212b}.ni-summary-note{grid-column:1/-1;font-size:12px;color:#4c5f6b;background:#fbfefe;border:1px solid #e4eff1;border-radius:7px;padding:10px}
.ni-summary-dark{background:linear-gradient(135deg,#06343b 0%,#0a4650 58%,#08313b 100%);border:1px solid #0e6770;border-radius:8px;padding:14px;color:#eefefe;box-shadow:0 8px 22px rgba(4,47,54,.20);margin-bottom:14px}.ni-summary-dark .ni-section-title,.ni-summary-dark .ni-summary-value{color:#eefefe}.ni-summary-dark .ni-summary-label{color:#9ed8dc}.ni-summary-dark .ni-summary-item{background:rgba(4,38,45,.45);border:1px solid rgba(151,221,226,.28)}.ni-summary-dark .ni-summary-note{background:rgba(4,38,45,.45);border:1px solid rgba(151,221,226,.28);color:#d7eeee}
.ni-table-wrap{max-height:360px;overflow:auto;border:1px solid #dcebed;border-radius:7px}.ni-table{width:100%;border-collapse:separate;border-spacing:0;font-size:11px}.ni-table th{position:sticky;top:0;background:#eaf8fa;color:#0f5f68;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.4px;padding:7px 8px;border-bottom:1px solid #bfe5e9;white-space:nowrap;cursor:pointer}.ni-table td{padding:7px 8px;border-bottom:1px solid #eef6f7;color:#263845;vertical-align:top}.ni-table tr:nth-child(even) td{background:#fbfefe}.ni-table tr:last-child td{border-bottom:0}.ni-task{font-weight:800;color:#14212b;min-width:180px}.ni-chip{display:inline-flex;padding:2px 6px;border-radius:4px;background:#e7f7f8;color:#0f5f68;font-size:10px;font-weight:800;margin:1px 2px 1px 0}.ni-neg{color:#dc2626;font-weight:900}.ni-pos{color:#059669;font-weight:900}
.ni-section-red .ni-table th{background:#fff1f2;color:#be123c;border-bottom-color:#fecdd3}.ni-section-green .ni-table th{background:#ecfdf5;color:#047857;border-bottom-color:#bbf7d0}.ni-section-amber .ni-table th{background:#fffbeb;color:#b45309;border-bottom-color:#fde68a}.ni-section-blue .ni-table th{background:#eff8ff;color:#0369a1;border-bottom-color:#bae6fd}
@media(max-width:1050px){.ni-kpis{grid-template-columns:repeat(3,1fr)}.ni-actions{grid-template-columns:1fr}.ni-body{flex-direction:column}.ni-sidebar{position:relative;width:100%;min-width:0;border-right:0;border-bottom:1px solid #dfe7ea}.ni-filter-group{display:inline-block;vertical-align:top;min-width:180px;margin-right:12px}.ni-main{padding:12px}.ni-graph-card{padding:16px}.ni-graph-head{flex-direction:column}.ni-progress-list{grid-template-columns:120px 1fr 48px}}
@media(max-width:640px){.ni-kpis{grid-template-columns:repeat(2,1fr);padding:10px}.ni-kpi{min-height:78px}.ni-kpi-value{font-size:24px}.ni-title{font-size:15px}.ni-graph-svg{height:220px}.ni-table{font-size:10px}}
"""


JS = """
(function(){
  function qsa(sel, root){return Array.prototype.slice.call((root||document).querySelectorAll(sel));}
  function setActive(btn){
    qsa('[data-filter-dim="'+btn.dataset.filterDim+'"]').forEach(function(b){b.classList.toggle('active', b===btn);});
  }
  function activeFilters(){
    var out={area:'ALL',floor:'ALL',phase:'ALL',trade:'ALL',task_type:'ALL'};
    qsa('[data-filter-dim].active').forEach(function(b){out[b.dataset.filterDim]=b.dataset.filterVal;});
    return out;
  }
  function matches(row, f){
    return ['area','floor','phase','trade','task_type'].every(function(k){
      return !f[k] || f[k]==='ALL' || (row.dataset[k]||'')===f[k];
    });
  }
  function esc(v){
    return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});
  }
  function rowMatches(row, f){
    return ['area','floor','phase','trade','task_type'].every(function(k){
      return !f[k] || f[k]==='ALL' || String(row[k]||'')===f[k];
    });
  }
  function groupDim(f){
    if(!f.area || f.area==='ALL') return 'area';
    if(!f.floor || f.floor==='ALL') return 'floor';
    if(!f.phase || f.phase==='ALL') return 'phase';
    if(!f.trade || f.trade==='ALL') return 'trade';
    if(!f.task_type || f.task_type==='ALL') return 'task_type';
    return 'phase';
  }
  function renderCurrentExtract(f){
    var list=document.querySelector('[data-v1-progress-list]');
    if(!list || !window.__novaV1Data) return;
    var source=window.__novaV1Data.current_extract_source||[];
    if(!source.length) return;
    var dim=groupDim(f);
    var groups={};
    source.filter(function(row){return rowMatches(row,f);}).forEach(function(row){
      var label=String(row[dim]||row.area||row.phase||row.trade||list.dataset.unassigned||'Unassigned');
      if(!groups[label]) groups[label]={label:label,count:0,actual:0,expected:0};
      groups[label].count+=1;
      groups[label].actual+=parseFloat(row.actual_pct||0)||0;
      groups[label].expected+=parseFloat(row.expected_pct||0)||0;
    });
    var rows=Object.keys(groups).map(function(k){
      var g=groups[k], count=Math.max(g.count,1);
      return {label:g.label,count:g.count,actual:g.actual/count,expected:g.expected/count};
    }).sort(function(a,b){return a.actual-b.actual || b.count-a.count;}).slice(0,15);
    if(!rows.length){
      list.innerHTML='<div class="ni-progress-label">'+esc(list.dataset.none||'None')+'</div><div class="ni-progress-track"></div><div class="ni-progress-value">0%</div>';
      return;
    }
    list.innerHTML=rows.map(function(row){
      var pct=Math.max(0,Math.min(100,row.actual));
      return '<div class="ni-progress-row" data-v1-progress><div class="ni-progress-label">'+esc(row.label)+'</div><div class="ni-progress-track"><div class="ni-progress-bar" style="width:'+pct.toFixed(1)+'%"></div></div><div class="ni-progress-value">'+Math.round(pct)+'%</div></div>';
    }).join('');
  }
  function applyFilters(){
    var f=activeFilters();
    qsa('[data-v1-row]').forEach(function(row){row.style.display=matches(row,f)?'':'none';});
    renderCurrentExtract(f);
  }
  window.niV1Filter=function(btn){setActive(btn);applyFilters();};
  window.niV1Sort=function(th){
    var table=th.closest('table'); if(!table) return;
    var tbody=table.querySelector('tbody'); if(!tbody) return;
    var key=th.dataset.sortKey;
    var dir=th.dataset.sortDir==='asc'?'desc':'asc';
    qsa('th[data-sort-key]', table).forEach(function(h){h.dataset.sortDir='';});
    th.dataset.sortDir=dir;
    var rows=qsa('tr', tbody);
    rows.sort(function(a,b){
      var av=a.getAttribute('data-sort-'+key)||'', bv=b.getAttribute('data-sort-'+key)||'';
      var an=parseFloat(av), bn=parseFloat(bv);
      if(!isNaN(an)&&!isNaN(bn)) return dir==='asc'?an-bn:bn-an;
      return dir==='asc'?String(av).localeCompare(String(bv)):String(bv).localeCompare(String(av));
    });
    rows.forEach(function(r){tbody.appendChild(r);});
  };
  document.addEventListener('DOMContentLoaded', applyFilters);
  if(document.readyState!=='loading') applyFilters();
})();
"""


_PAYLOAD_SCRIPT_RE = _re.compile(
    r"<script>\s*window\.__novaV1Data=(?P<payload>.*?);\s*</script>",
    _re.DOTALL,
)


def _script_json(value: Any) -> str:
    return (
        _json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _status_label(payload: dict, language: str) -> str:
    status = str(payload.get("status", "at_risk")).replace("_", "-")
    if language == "da":
        return {"stable": "PÅ SPORET", "at-risk": "I RISIKO", "critical": "KRITISK"}.get(status, status.upper())
    return {"stable": "ON TRACK", "at-risk": "AT RISK", "critical": "CRITICAL"}.get(status, status.upper())


def _display_status(value: Any, language: str) -> str:
    raw = str(value or "").strip()
    key = raw.lower().replace("-", "_").replace(" ", "_")
    labels = {
        "en": {
            "behind": "Behind",
            "ahead": "Ahead",
            "critical_now": "Critical now",
            "important_next": "Important next",
            "monitor": "Monitor",
            "critical": "Critical",
            "at_risk": "At risk",
            "stable": "Stable",
        },
        "da": {
            "behind": "Bagud",
            "ahead": "Foran",
            "critical_now": "Kritisk nu",
            "important_next": "Vigtig næste",
            "monitor": "Overvåg",
            "critical": "Kritisk",
            "at_risk": "I risiko",
            "stable": "På sporet",
        },
    }
    return labels.get(language, labels["en"]).get(key, raw)


def _graph_delay_label(graph: dict, language: str) -> str:
    if graph.get("type") == "risk_buckets":
        count = graph.get("delayed_count")
        if count is None:
            match = _re.search(r"\d+", str(graph.get("delay_label", "")))
            count = match.group(0) if match else ""
        if count in (None, ""):
            return ""
        return f"{count} forsinkede" if language == "da" else f"{count} delayed"

    try:
        gap = float(graph.get("gap", 0))
    except (TypeError, ValueError):
        gap = 0
    if gap < 0:
        return f"{abs(round(gap))} pp bagud" if language == "da" else f"{abs(round(gap))} pp behind"
    return str(graph.get("delay_label") or "")


def _display_label(value: Any, language: str) -> str:
    raw = str(value or "")
    key = raw.strip().lower()
    if key == "now":
        return t(language, "now")
    if key == "all":
        return t(language, "all_items")
    if key == "unassigned":
        return t(language, "unassigned")
    return raw


def _warning_text(value: Any, language: str) -> str:
    raw = str(value or "")
    if raw in {"risk_bucket_note"}:
        return t(language, raw)
    return raw


def _svg_icon() -> str:
    return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 6-7"/></svg>'


def _section_icon(title_key: str) -> tuple[str, str]:
    cfg = {
        "behind_table": ("red", '<path d="M3 3v18h18"/><path d="M7 8v8"/><path d="M12 5v11"/><path d="M17 12v4"/>'),
        "ahead_table": ("green", '<path d="M3 17 9 11l4 4 8-9"/><path d="M16 6h5v5"/>'),
        "changed_table": ("blue", '<path d="M16 3h5v5"/><path d="M4 20 21 3"/><path d="M21 16v5h-5"/><path d="M4 4l5 5"/>'),
        "stage_table": ("amber", '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/><path d="M12 8v8"/>'),
        "critical_path_table": ("red", '<path d="M4 19h16"/><path d="M5 16l4-8 4 5 4-7 2 4"/><circle cx="9" cy="8" r="1"/><circle cx="13" cy="13" r="1"/><circle cx="17" cy="6" r="1"/>'),
        "summary_notes": ("blue", '<path d="M4 4h16v16H4z"/><path d="M8 8h8"/><path d="M8 12h8"/><path d="M8 16h5"/>'),
        "actions": ("blue", '<path d="M9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>'),
        "critical_now": ("red", '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>'),
        "important_next": ("amber", '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
        "monitor": ("blue", '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'),
        "all_delayed": ("red", '<path d="M4 4h16v16H4z"/><path d="M8 9h8"/><path d="M8 13h8"/><path d="M8 17h5"/>'),
        "area_progress": ("", '<path d="M3 3v18h18"/><path d="M7 16h3"/><path d="M12 12h3"/><path d="M17 8h3"/>'),
    }
    return cfg.get(title_key, ("", '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>'))


def _section_heading(language: str, title_key: str, count: int | None = None, sub_key: str | None = None) -> str:
    tone, icon = _section_icon(title_key)
    count_text = f" ({count})" if count is not None else ""
    sub = f'<p class="ni-section-sub">{_e(t(language, sub_key))}</p>' if sub_key else ""
    return (
        '<div class="ni-section-head"><div class="ni-title-wrap">'
        f'<div class="ni-section-icon {tone}"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">{icon}</svg></div>'
        f'<div><h2 class="ni-section-title">{_e(t(language, title_key))}{count_text}</h2>{sub}</div>'
        '</div></div>'
    )


def _render_kpis(payload: dict, language: str) -> str:
    parts = ['<div class="ni-kpis">']
    for item in payload.get("kpis", []):
        tone = _tone_class(item.get("tone", "neutral"))
        suffix = _e(item.get("suffix", ""))
        parts.append(
            f'<div class="ni-kpi {tone}">'
            f'<div class="ni-kpi-icon">{_svg_icon()}</div>'
            f'<div class="ni-kpi-value">{_e(item.get("value", 0))}{suffix}</div>'
            f'<div class="ni-kpi-label">{_e(t(language, item.get("key", "")))}</div>'
            f'</div>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def _filter_buttons(language: str, dim: str, values: list[str], label_key: str) -> str:
    parts = [f'<div class="ni-filter-group"><p class="ni-filter-label">{_e(t(language, label_key))}</p>']
    all_label = t(language, "all")
    parts.append(
        f'<button type="button" class="ni-filter-opt active" data-filter-dim="{dim}" data-filter-val="ALL" onclick="niV1Filter(this)">'
        f'<span class="ni-filter-dot"></span>{_e(all_label)}</button>'
    )
    for value in values[:30]:
        ev = _e(value)
        parts.append(
            f'<button type="button" class="ni-filter-opt" data-filter-dim="{dim}" data-filter-val="{ev}" onclick="niV1Filter(this)">'
            f'<span class="ni-filter-dot"></span>{ev}</button>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def _render_sidebar(payload: dict, language: str) -> str:
    filters = payload.get("filters", {})
    return (
        '<aside class="ni-sidebar">'
        f'<p class="ni-filter-title">{_e(t(language, "filters"))}</p>'
        + _filter_buttons(language, "area", filters.get("areas", []), "building")
        + _filter_buttons(language, "phase", filters.get("phases", []), "phase")
        + _filter_buttons(language, "floor", filters.get("floors", []), "floor")
        + _filter_buttons(language, "trade", filters.get("trades", []), "trade")
        + (_filter_buttons(language, "task_type", filters.get("task_types", []), "task_type") if filters.get("task_types") else "")
        + "</aside>"
    )


def _points_path(points: list[dict], left: int, top: int, width: int, height: int) -> str:
    if not points:
        return ""
    if len(points) == 1:
        points = [points[0], points[0]]
    coords = []
    for idx, point in enumerate(points):
        x = left + (width / max(len(points) - 1, 1)) * idx
        y = top + height - (max(0, min(100, float(point.get("value", 0)))) / 100) * height
        coords.append((x, y))
    path = f"M {coords[0][0]:.1f} {coords[0][1]:.1f}"
    for x, y in coords[1:]:
        path += f" L {x:.1f} {y:.1f}"
    return path


def _point_coords(points: list[dict], left: int, top: int, width: int, height: int) -> list[tuple[float, float]]:
    if not points:
        return []
    if len(points) == 1:
        points = [points[0], points[0]]
    coords = []
    for idx, point in enumerate(points):
        x = left + (width / max(len(points) - 1, 1)) * idx
        y = top + height - (max(0, min(100, float(point.get("value", 0)))) / 100) * height
        coords.append((x, y))
    return coords


def _area_path(points: list[dict], left: int, top: int, width: int, height: int) -> str:
    path = _points_path(points, left, top, width, height)
    if not path:
        return ""
    count = max(len(points), 2)
    last_x = left + width
    return f"{path} L {last_x} {top + height} L {left} {top + height} Z"


def _gap_area_path(planned: list[dict], actual: list[dict], left: int, top: int, width: int, height: int) -> str:
    if len(planned) < 2 or len(planned) != len(actual):
        return ""
    planned_coords = []
    actual_coords = []
    for idx, point in enumerate(planned):
        x = left + (width / max(len(planned) - 1, 1)) * idx
        y = top + height - (max(0, min(100, float(point.get("value", 0)))) / 100) * height
        planned_coords.append((x, y))
    for idx, point in enumerate(actual):
        x = left + (width / max(len(actual) - 1, 1)) * idx
        y = top + height - (max(0, min(100, float(point.get("value", 0)))) / 100) * height
        actual_coords.append((x, y))
    if actual_coords[-1][1] <= planned_coords[-1][1]:
        return ""
    path = f"M {planned_coords[0][0]:.1f} {planned_coords[0][1]:.1f}"
    for x, y in planned_coords[1:]:
        path += f" L {x:.1f} {y:.1f}"
    for x, y in reversed(actual_coords):
        path += f" L {x:.1f} {y:.1f}"
    return path + " Z"


def _graph_stat(value: Any) -> str:
    try:
        return f"{float(value):.0f}%"
    except (TypeError, ValueError):
        return "0%"


def _format_float(value: Any, language: str) -> str:
    raw = str(value if value is not None else "").strip()
    if raw == "":
        return t(language, "not_available")
    try:
        number = float(raw.replace(",", "."))
        return f"{number:.0f} d"
    except ValueError:
        return raw


def _render_progress_graph(payload: dict, language: str) -> str:
    graph = payload.get("graph", {})
    title_key = "graph_title_predictive" if payload.get("mode") == "predictive" else "graph_title_health"
    sub_key = "graph_subtitle_predictive" if payload.get("mode") == "predictive" else "graph_subtitle_health"
    is_risk_buckets = graph.get("type") == "risk_buckets"
    is_empty = graph.get("type") == "empty"
    if is_empty:
        body = f'<div class="ni-empty-graph">{_e(t(language, "no_graph_data"))}</div>'
    elif is_risk_buckets:
        pts = graph.get("points", [])
        max_v = max([float(p.get("value", 0)) for p in pts] + [1])
        bars = []
        x = 72
        gap = 18
        bar_w = 92
        for point in pts:
            h = 180 * (float(point.get("value", 0)) / max_v)
            y = 220 - h
            bars.append(
                f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" rx="4" fill="url(#niBarFill)"></rect>'
                f'<text class="ni-axis" text-anchor="middle" x="{x + bar_w/2}" y="244">{_e(_display_label(point.get("label"), language))}</text>'
                f'<text class="ni-axis" text-anchor="middle" x="{x + bar_w/2}" y="{max(y - 8, 18):.1f}">{_e(point.get("value"))}</text>'
            )
            x += bar_w + gap
        body = (
            '<svg class="ni-graph-svg" viewBox="0 0 760 270" role="img">'
            '<defs><linearGradient id="niBarFill" x1="0" y1="1" x2="0" y2="0">'
            '<stop offset="0%" stop-color="#0284c7"/><stop offset="100%" stop-color="#00d6d6"/>'
            '</linearGradient></defs>'
            f'{"".join(bars)}</svg>'
        )
    else:
        left, top, width, height = 48, 22, 660, 190
        planned = graph.get("planned", [])
        actual = graph.get("actual", [])
        forecast = graph.get("forecast", [])
        planned_path = _points_path(planned, left, top, width, height)
        actual_path = _points_path(actual, left, top, width, height)
        forecast_path = _points_path(forecast, left, top, width, height)
        actual_area = _area_path(actual, left, top, width, height)
        gap_area = _gap_area_path(planned, actual, left, top, width, height)
        planned_coords = _point_coords(planned, left, top, width, height)
        actual_coords = _point_coords(actual, left, top, width, height)
        labels = actual or planned
        grid = []
        for val in [0, 25, 50, 75, 100]:
            y = top + height - (val / 100) * height
            grid.append(f'<line class="ni-grid" x1="{left}" y1="{y:.1f}" x2="{left + width}" y2="{y:.1f}"></line>')
            grid.append(f'<text class="ni-axis" x="8" y="{y + 4:.1f}">{val}%</text>')
        if labels:
            for idx, point in enumerate(labels):
                x = left + (width / max(len(labels) - 1, 1)) * idx
                grid.append(f'<text class="ni-axis" text-anchor="middle" x="{x:.1f}" y="248">{_e(_display_label(point.get("label"), language))}</text>')
        callout = ""
        marker = ""
        delay_label = _graph_delay_label(graph, language)
        if planned_coords and actual_coords:
            px, py = planned_coords[-1]
            ax, ay = actual_coords[-1]
            if ay > py:
                marker += f'<line class="ni-gap-line" x1="{ax:.1f}" y1="{py:.1f}" x2="{ax:.1f}" y2="{ay:.1f}"></line>'
            marker += f'<circle class="ni-point-planned" cx="{px:.1f}" cy="{py:.1f}" r="5"></circle>'
            marker += f'<circle class="ni-point-actual" cx="{ax:.1f}" cy="{ay:.1f}" r="6"></circle>'
            label_x = max(left + width - 250, left + 20)
            marker += f'<text class="ni-point-label planned" text-anchor="end" x="{label_x:.1f}" y="{max(py - 8, top + 12):.1f}">{_e(t(language, "planned"))} {_graph_stat(graph.get("planned_now"))}</text>'
            marker += f'<text class="ni-point-label" text-anchor="end" x="{label_x:.1f}" y="{min(ay + 18, top + height - 4):.1f}">{_e(t(language, "actual"))} {_graph_stat(graph.get("actual_now"))}</text>'
        if delay_label:
            callout = (
                '<rect class="ni-callout" x="536" y="166" width="172" height="42" rx="6"></rect>'
                f'<text class="ni-callout-text" x="552" y="192">{_e(delay_label)}</text>'
            )
        body = f"""
<svg class="ni-graph-svg" viewBox="0 0 760 270" role="img">
  <defs>
    <linearGradient id="niActualFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#00d6d6" stop-opacity=".38"/><stop offset="100%" stop-color="#00d6d6" stop-opacity=".04"/></linearGradient>
    <linearGradient id="niForecastFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#38bdf8" stop-opacity=".35"/><stop offset="100%" stop-color="#38bdf8" stop-opacity=".04"/></linearGradient>
    <linearGradient id="niGapFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#f59e0b" stop-opacity=".34"/><stop offset="100%" stop-color="#f59e0b" stop-opacity=".08"/></linearGradient>
  </defs>
  {''.join(grid)}
  <path class="ni-fill-actual" d="{actual_area}"></path>
  <path class="ni-gap-area" d="{gap_area}"></path>
  <path class="ni-planned" d="{planned_path}"></path>
  <path class="ni-actual" d="{actual_path}"></path>
  <path class="ni-forecast" d="{forecast_path}"></path>
  {marker}
  <line class="ni-today" x1="{left + width}" y1="{top - 8}" x2="{left + width}" y2="{top + height + 14}"></line>
  <text class="ni-axis" x="{left + width + 10}" y="{top + 4}">{_e(t(language, "today"))}</text>
  {callout}
</svg>"""
    if is_risk_buckets:
        stats = ""
        legend = f'<span class="ni-key"><span class="ni-key-actual"></span>{_e(t(language, "delayed_activities"))}</span>'
        subtext = _e(t(language, "risk_bucket_note"))
    elif is_empty:
        legend = ""
        stats = ""
        subtext = _e(t(language, sub_key))
    else:
        try:
            gap_value = abs(round(float(graph.get("gap", 0))))
        except (TypeError, ValueError):
            gap_value = 0
        stats = (
            '<div class="ni-graph-stats">'
            f'<div class="ni-graph-stat"><span>{_e(t(language, "actual"))}</span><strong>{_graph_stat(graph.get("actual_now"))}</strong></div>'
            f'<div class="ni-graph-stat"><span>{_e(t(language, "planned"))}</span><strong>{_graph_stat(graph.get("planned_now"))}</strong></div>'
            f'<div class="ni-graph-stat delay"><span>{_e(t(language, "delay"))}</span><strong>{gap_value} pp</strong></div>'
            '</div>'
        )
        legend = (
            f'<span class="ni-key"><span class="ni-key-actual"></span>{_e(t(language, "actual"))}</span>'
            f'<span class="ni-key"><span class="ni-key-planned"></span>{_e(t(language, "planned"))}</span>'
            f'<span class="ni-key"><span class="ni-key-forecast"></span>{_e(t(language, "forecast"))}</span>'
            f'<span class="ni-key"><span class="ni-key-delay"></span>{_e(t(language, "delay"))}</span>'
        )
        subtext = _e(t(language, sub_key))
    return f"""
<section class="ni-graph-card">
  <div class="ni-graph-head">
    <div>
      <h2 class="ni-graph-title">{_e(t(language, title_key))}</h2>
      <p class="ni-graph-sub">{subtext}</p>
    </div>
    <div class="ni-legend">
      {legend}
    </div>
  </div>
  {stats}
  {body}
</section>"""


def _render_area_progress(payload: dict, language: str) -> str:
    rows = payload.get("area_progress", [])
    parts = [
        '<section class="ni-section ni-area-section">',
        _section_heading(language, "area_progress", sub_key="area_progress_sub"),
        f'<div class="ni-progress-list" data-v1-progress-list data-none="{_e(t(language, "none"))}" data-unassigned="{_e(t(language, "unassigned"))}">',
    ]
    for row in rows:
        actual = max(0, min(100, float(row.get("actual_pct", 0))))
        parts.append(
            f'<div class="ni-progress-row" data-v1-progress data-area="{_e(row.get("label"))}">'
            f'<div class="ni-progress-label">{_e(_display_label(row.get("label"), language))}</div>'
            f'<div class="ni-progress-track"><div class="ni-progress-bar" style="width:{actual:.1f}%"></div></div>'
            f'<div class="ni-progress-value">{actual:.0f}%</div>'
            f'</div>'
        )
    parts.append("</div></section>")
    return "\n".join(parts)


def _sort_attrs(row: dict) -> str:
    return (
        f'data-sort-id="{_e(row.get("id"))}" '
        f'data-sort-task="{_e(row.get("task_name"))}" '
        f'data-sort-phase="{_e(row.get("phase"))}" '
        f'data-sort-area="{_e(row.get("area") or row.get("location"))}" '
        f'data-sort-resource="{_e(row.get("trade") or row.get("resource"))}" '
        f'data-sort-actual="{_e(row.get("actual_pct", 0))}" '
        f'data-sort-expected="{_e(row.get("expected_pct", 0))}" '
        f'data-sort-deviation="{_e(row.get("deviation", 0))}" '
        f'data-sort-days="{_e(row.get("days_overdue", 0))}" '
        f'data-sort-float="{_e(row.get("float_days", 0))}"'
    )


def _filter_attrs(row: dict) -> str:
    return (
        f'data-v1-row data-area="{_e(row.get("area"))}" data-floor="{_e(row.get("floor"))}" '
        f'data-phase="{_e(row.get("phase"))}" data-trade="{_e(row.get("trade"))}" data-task_type="{_e(row.get("task_type"))}"'
    )


def _th(language: str, label_key: str, sort_key: str) -> str:
    return f'<th data-sort-key="{sort_key}" onclick="niV1Sort(this)" title="{_e(t(language, "sort"))}">{_e(t(language, label_key))}</th>'


def _table_row(row: dict, language: str, variant: str) -> str:
    location = row.get("location") or " / ".join(p for p in [row.get("area"), row.get("floor"), row.get("phase")] if p)
    resource = row.get("resource") or row.get("trade")
    dev = float(row.get("deviation") or 0)
    dev_cls = "ni-neg" if dev < 0 else "ni-pos" if dev > 0 else ""
    base = (
        f'<tr {_filter_attrs(row)} {_sort_attrs(row)}>'
        f'<td>{_e(row.get("id"))}</td>'
        f'<td class="ni-task">{_e(row.get("task_name"))}</td>'
        f'<td>{_e(row.get("phase"))}</td>'
        f'<td><span class="ni-chip">{_e(location)}</span></td>'
        f'<td><span class="ni-chip">{_e(resource)}</span></td>'
    )
    if variant == "changed":
        return (
            base
            +
            f'<td>{_e(row.get("old_start") or row.get("start_date"))}</td><td>{_e(row.get("new_start") or row.get("start_date"))}</td>'
            f'<td>{_e(row.get("old_finish") or row.get("finish_date"))}</td><td>{_e(row.get("new_finish") or row.get("finish_date"))}</td>'
            f'<td>{_e(row.get("old_duration"))}</td><td>{_e(row.get("new_duration") or row.get("duration"))}</td>'
            f'<td>{_change_type_cell(row.get("change_type"))}</td><td>{_e(row.get("old"))}</td><td>{_e(row.get("new"))}</td></tr>'
        )
    if variant == "critical_path":
        return (
            base
            +
            f'<td>{_e(row.get("start_date"))}</td><td>{_e(row.get("finish_date"))}</td>'
            f'<td>{_e(_format_float(row.get("float_days"), language))}</td><td class="{dev_cls}">{dev:+.0f}%</td></tr>'
        )
    if variant == "delayed":
        return (
            base
            +
            f'<td>{_e(row.get("start_date"))}</td><td>{_e(row.get("finish_date"))}</td>'
            f'<td>{_e(row.get("duration"))}</td><td class="ni-neg">{_e(row.get("days_overdue"))}</td>'
            f'<td>{_e(_display_status(row.get("priority") or row.get("status"), language))}</td></tr>'
        )
    return (
        base
        +
        f'<td>{_pct(row.get("actual_pct"))}</td><td>{_pct(row.get("expected_pct"))}</td>'
        f'<td class="{dev_cls}">{dev:+.0f}%</td><td>{_e(_display_status(row.get("status"), language))}</td></tr>'
    )


def _render_table(language: str, title_key: str, rows: list[dict], variant: str = "progress", count: int | None = None) -> str:
    if variant == "changed":
        headers = [
            _th(language, "id", "id"), _th(language, "task_name", "task"),
            _th(language, "phase_col", "phase"), _th(language, "area_col", "area"),
            _th(language, "resource_col", "resource"), _th(language, "old_start_col", "actual"),
            _th(language, "new_start_col", "expected"), _th(language, "old_finish_col", "deviation"),
            _th(language, "new_finish_col", "days"), _th(language, "old_duration_col", "float"),
            _th(language, "new_duration_col", "resource"), f"<th>{_e(t(language, 'change_col'))}</th>",
            f"<th>{_e(t(language, 'before_col'))}</th>", f"<th>{_e(t(language, 'after_col'))}</th>",
        ]
    elif variant == "critical_path":
        headers = [
            _th(language, "id", "id"), _th(language, "task_name", "task"),
            _th(language, "phase_col", "phase"), _th(language, "area_col", "area"),
            _th(language, "resource_col", "resource"), _th(language, "start_col", "actual"),
            _th(language, "finish_col", "expected"), _th(language, "float_col", "float"),
            _th(language, "deviation_col", "deviation"),
        ]
    elif variant == "delayed":
        headers = [
            _th(language, "id", "id"), _th(language, "task_name", "task"),
            _th(language, "phase_col", "phase"), _th(language, "area_col", "area"),
            _th(language, "resource_col", "resource"), _th(language, "start_col", "actual"),
            _th(language, "finish_col", "expected"), _th(language, "duration_col", "deviation"),
            _th(language, "days_overdue", "days"), _th(language, "priority", "resource"),
        ]
    else:
        headers = [
            _th(language, "id", "id"), _th(language, "task_name", "task"),
            _th(language, "phase_col", "phase"), _th(language, "area_col", "area"),
            _th(language, "resource_col", "resource"), _th(language, "actual_col", "actual"),
            _th(language, "expected_col", "expected"), _th(language, "deviation_col", "deviation"),
            _th(language, "status_col", "resource"),
        ]
    body = "".join(_table_row(row, language, variant) for row in rows)
    if not body:
        body = f'<tr><td colspan="{len(headers)}" style="text-align:center;color:#71828f;padding:18px">{_e(t(language, "none"))}</td></tr>'
    tone, _icon = _section_icon(title_key)
    section_cls = f"ni-section ni-table-section ni-section-{tone or 'teal'}"
    return f"""
<section class="{section_cls}">
  {_section_heading(language, title_key, len(rows) if count is None else count)}
  <div class="ni-table-wrap">
    <table class="ni-table"><thead><tr>{''.join(headers)}</tr></thead><tbody>{body}</tbody></table>
  </div>
</section>"""


def _render_actions(payload: dict, language: str) -> str:
    actions = payload.get("actions", [])
    if not actions:
        return ""
    parts = [
        '<section class="ni-section ni-actions-section">',
        _section_heading(language, "actions"),
        '<div class="ni-actions">',
    ]
    for idx, action in enumerate(actions[:3], 1):
        text = action.get("action") or action.get("issue") or action.get("activity") or ""
        responsible = action.get("responsible") or ""
        deadline = action.get("deadline") or ""
        parts.append(
            f'<div class="ni-action"><div class="ni-action-rank">{idx}</div>'
            f'<div class="ni-action-text">{_e(text)}</div>'
            f'<div class="ni-action-meta">{_e(responsible)} {_e(deadline)}</div></div>'
        )
    parts.append("</div></section>")
    return "\n".join(parts)


def _summary_value(value: Any, suffix: str = "") -> str:
    if value in (None, ""):
        return "-"
    return f"{value}{suffix}"


def _render_summary(payload: dict, language: str) -> str:
    summary = payload.get("summary") or {}
    if not summary:
        return ""
    items = [
        ("overall_progress", _summary_value(summary.get("overall_progress"), "%")),
        ("completed_activities", _summary_value(summary.get("completed_activities"))),
        ("delayed_activities", _summary_value(summary.get("delayed_activities"))),
        ("total_activities", _summary_value(summary.get("total_activities"))),
        ("added_activities", _summary_value(summary.get("added_activities"))),
        ("removed_activities", _summary_value(summary.get("removed_activities"))),
        ("reporting_period", _summary_value(summary.get("reporting_period"))),
    ]
    parts = [
        '<section class="ni-summary-dark">',
        _section_heading(language, "summary_notes", sub_key="summary_notes_sub"),
        '<div class="ni-summary-grid">',
    ]
    for key, value in items:
        parts.append(
            f'<div class="ni-summary-item"><div class="ni-summary-label">{_e(t(language, key))}</div>'
            f'<div class="ni-summary-value">{_e(value)}</div></div>'
        )
    notes = summary.get("notes") or t(language, "no_notes")
    parts.append(
        f'<div class="ni-summary-note"><strong>{_e(t(language, "notes"))}:</strong> {_e(notes)}</div>'
    )
    parts.append("</div></section>")
    return "\n".join(parts)


def _render_payload(payload: dict, language: str) -> str:
    language = lang_code(language)
    status = str(payload.get("status", "at-risk")).replace("_", "-")
    warnings = "".join(
        f'<div class="ni-warnings"><strong>{_e(t(language, "data_quality"))}:</strong> {_e(_warning_text(w, language))}</div>'
        for w in payload.get("warnings", [])
        if w
    )
    tables = payload.get("tables", {})
    table_counts = payload.get("table_counts", {})
    table_html = []
    summary_html = ""
    if payload.get("mode") == "health":
        summary_html = _render_summary(payload, language)
        table_html.extend(
            [
                _render_table(language, "behind_table", tables.get("behind", [])),
                _render_table(language, "ahead_table", tables.get("ahead", [])),
                _render_table(language, "changed_table", tables.get("changed", []), "changed", table_counts.get("changed_table")),
                _render_table(language, "stage_table", tables.get("stage", [])),
                _render_table(language, "critical_path_table", tables.get("critical_path", []), "critical_path"),
            ]
        )
    else:
        table_html.extend(
            [
                _render_actions(payload, language),
                _render_table(language, "critical_now", tables.get("critical", []), "delayed"),
                _render_table(language, "important_next", tables.get("important", []), "delayed"),
                _render_table(language, "monitor", tables.get("monitor", []), "delayed"),
                _render_table(language, "all_delayed", tables.get("all_delayed", []), "delayed"),
            ]
        )
    return f"""
<style>{CSS}</style>
<script>{JS}</script>
<script>window.__novaV1Data={_script_json(payload)};</script>
<div class="ni-v1">
  <header class="ni-header">
    <div class="ni-logo">NI</div>
    <div>
      <p class="ni-brand">{_e(t(language, "brand"))}</p>
      <h1 class="ni-title">{_e(t(language, payload.get("title_key", "health_title")))}</h1>
      <p class="ni-sub">{_e(t(language, "subtitle"))}</p>
    </div>
    <div class="ni-status {status}">{_e(_status_label(payload, language))}</div>
  </header>
  {_render_kpis(payload, language)}
  <div class="ni-body">
    {_render_sidebar(payload, language)}
    <main class="ni-main">
      {warnings}
      {summary_html}
      {_render_progress_graph(payload, language)}
      {_render_area_progress(payload, language)}
      {''.join(table_html)}
    </main>
  </div>
</div>"""


def format_health_v1_as_html(data: dict, language: str = "en") -> str:
    return _render_payload(adapt_health_dashboard(data, language), language)


def format_predictive_v1_as_html(data: dict, language: str = "en") -> str:
    return _render_payload(adapt_predictive_dashboard(data, language), language)


def localize_v1_html(html: str, language: str = "da") -> str:
    match = _PAYLOAD_SCRIPT_RE.search(html or "")
    if not match:
        raise ValueError("Version 1.0 dashboard payload was not found in the submitted HTML.")

    payload = _json.loads(match.group("payload"))
    if not isinstance(payload, dict) or payload.get("mode") not in {"health", "predictive"}:
        raise ValueError("Submitted HTML does not contain a valid Version 1.0 dashboard payload.")

    return _render_payload(payload, language)
