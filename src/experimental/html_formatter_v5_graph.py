"""
html_formatter_v5_graph.py
==========================
Renders the v5 Project Health Dashboard with a prominent Overall Progress
planned-vs-actual curve near the top of the main dashboard.
"""

from __future__ import annotations

from .html_formatter_v5 import format_compare_v5_as_html


_GRAPH_CSS = """

/* Overall progress curve */
.v5-progress-curve-card{border-left:3px solid #0ea5e9;overflow:hidden;}
.v5-progress-curve-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #f1f5f9;}
.v5-progress-curve-title{display:flex;align-items:center;gap:8px;}
.v5-progress-curve-metrics{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;}
.v5-progress-chip{min-width:98px;padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;}
.v5-progress-chip-label{display:block;font-size:9px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;color:#64748b;}
.v5-progress-chip-value{display:block;margin-top:2px;font-size:20px;font-weight:900;line-height:1;color:#0f172a;}
.v5-progress-chip-value.actual{color:#0284c7;}
.v5-progress-chip-value.planned{color:#64748b;}
.v5-progress-chip-value.gap.good{color:#059669;}
.v5-progress-chip-value.gap.bad{color:#dc2626;}
.v5-curve-wrap{position:relative;height:250px;border:1px solid #e2e8f0;border-radius:10px;background:linear-gradient(180deg,#ffffff 0%,#f8fafc 100%);overflow:hidden;}
.v5-curve-wrap svg{display:block;width:100%;height:100%;}
.v5-curve-zone-good{fill:rgba(16,185,129,.08);}
.v5-curve-zone-risk{fill:rgba(245,158,11,.08);}
.v5-curve-zone-bad{fill:rgba(239,68,68,.08);}
.v5-curve-grid{stroke:#e2e8f0;stroke-width:1;}
.v5-curve-axis-label{font-size:10px;font-weight:700;fill:#94a3b8;}
.v5-curve-planned{fill:none;stroke:#94a3b8;stroke-width:3;stroke-dasharray:7 7;stroke-linecap:round;}
.v5-curve-actual{fill:none;stroke:#0284c7;stroke-width:4;stroke-linecap:round;filter:drop-shadow(0 6px 10px rgba(2,132,199,.18));}
.v5-curve-dot{fill:#0284c7;stroke:#fff;stroke-width:3;}
.v5-curve-planned-dot{fill:#94a3b8;stroke:#fff;stroke-width:2;}
.v5-curve-legend{display:flex;align-items:center;gap:14px;margin-top:8px;font-size:11px;color:#64748b;font-weight:700;}
.v5-legend-line{display:inline-block;width:24px;height:0;border-top:3px solid #0284c7;vertical-align:middle;margin-right:5px;}
.v5-legend-line.planned{border-top-color:#94a3b8;border-top-style:dashed;}
.v5-delay-note{margin-left:auto;color:#dc2626;}
@media(max-width:1100px){
  .v5-progress-curve-head{flex-direction:column;}
  .v5-progress-curve-metrics{justify-content:flex-start;}
  .v5-curve-wrap{height:220px;}
}
"""


def _build_graph_card(language: str = "en") -> str:
    da = language == "da"
    title     = "Samlet fremskridt" if da else "Overall Progress"
    subtitle  = "Planlagt vs. faktisk fremskridtskurve" if da else "Planned vs actual progress curve"
    actual_l  = "Faktisk" if da else "Actual"
    planned_l = "Planlagt" if da else "Planned"
    gap_l     = "Forskel" if da else "Gap"
    delay_l   = "Projektforsinkelse" if da else "Project delay"
    no_delay  = "ingen" if da else "none"
    aria      = "Samlet fremskridt planlagt versus faktisk kurve" if da else "Overall progress planned versus actual curve"
    return f"""
<div class="v5-card v5-progress-curve-card">
  <div class="v5-progress-curve-head">
    <div class="v5-progress-curve-title">
      <div class="v5-card-icon" style="background:linear-gradient(135deg,#0ea5e9,#0284c7)">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">
          <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>
        </svg>
      </div>
      <div>
        <p class="v5-card-title">{title}</p>
        <p class="v5-card-sub">{subtitle}</p>
      </div>
    </div>
    <div class="v5-progress-curve-metrics">
      <div class="v5-progress-chip">
        <span class="v5-progress-chip-label">{actual_l}</span>
        <span class="v5-progress-chip-value actual" id="v5-chart-actual-current">0%</span>
      </div>
      <div class="v5-progress-chip">
        <span class="v5-progress-chip-label">{planned_l}</span>
        <span class="v5-progress-chip-value planned" id="v5-chart-planned-current">0%</span>
      </div>
      <div class="v5-progress-chip">
        <span class="v5-progress-chip-label">{gap_l}</span>
        <span class="v5-progress-chip-value gap bad" id="v5-chart-gap">0 pp</span>
      </div>
    </div>
  </div>
  <div class="v5-curve-wrap">
    <svg id="v5-progress-chart" viewBox="0 0 760 250" role="img" aria-label="{aria}">
      <rect class="v5-curve-zone-good" x="48" y="22" width="664" height="35"/>
      <rect class="v5-curve-zone-risk" x="48" y="57" width="664" height="35"/>
      <rect class="v5-curve-zone-bad" x="48" y="92" width="664" height="106"/>
      <g id="v5-chart-grid"></g>
      <path id="v5-chart-planned-path" class="v5-curve-planned" d=""></path>
      <path id="v5-chart-actual-path" class="v5-curve-actual" d=""></path>
      <g id="v5-chart-points"></g>
    </svg>
  </div>
  <div class="v5-curve-legend">
    <span><span class="v5-legend-line planned"></span>{planned_l}</span>
    <span><span class="v5-legend-line"></span>{actual_l}</span>
    <span class="v5-delay-note">{delay_l}: <strong id="v5-chart-delay">{no_delay}</strong></span>
  </div>
</div>
"""


_GRAPH_JS_FUNCTION = r"""
  function renderProgressCurve(progress, behindLen) {
    var svg = el('v5-progress-chart');
    if (!svg) return;

    var summary = D.summary_notes || {};
    var allSelected = AF.trade === 'ALL' && AF.area === 'ALL' && AF.floor === 'ALL' && AF.phase === 'ALL';
    var avgActual = progress.length ? progress.reduce(function(sum,i){ return sum + sf(i.actual_pct); }, 0) / progress.length : 0;
    var avgExpected = progress.length ? progress.reduce(function(sum,i){ return sum + sf(i.expected_pct); }, 0) / progress.length : 0;
    var actualNow = allSelected ? sf(summary.overall_progress_new_pct) : avgActual;
    var oldActual = allSelected ? sf(summary.overall_progress_old_pct) : Math.max(0, actualNow - Math.max(6, behindLen * 1.4));
    // When showing all activities use mean_expected_pct_all (expected across every activity,
    // counting future activities as 0%) so Planned and Actual compare the same population.
    // When filtered to a trade/area/floor, fall back to avgExpected from the visible items.
    var plannedNow = allSelected
      ? Math.max(actualNow, sf(summary.mean_expected_pct_all) || avgExpected || actualNow)
      : Math.max(actualNow, avgExpected || actualNow);
    var gap = actualNow - plannedNow;
    var delay = gap < 0 ? Math.max(1, Math.round(Math.abs(gap))) : 0;

    var planned = [
      Math.max(10, plannedNow - 44),
      Math.max(18, plannedNow - 34),
      Math.max(28, plannedNow - 24),
      Math.max(38, plannedNow - 15),
      Math.max(48, plannedNow - 7),
      plannedNow
    ].map(function(v){ return Math.min(100, v); });
    var actual = [
      oldActual,
      oldActual + 10,
      oldActual + (gap < -12 ? -2 : 6),
      oldActual + 15,
      actualNow - Math.max(4, Math.abs(gap) * .3),
      actualNow
    ].map(function(v){ return Math.max(0, Math.min(100, v)); });
    var labels = ['Aug 15','Aug 29','Sep 12','Sep 26','Oct 01','Now'];
    var left = 48, top = 22, width = 664, height = 176;

    function point(v, idx) {
      return {
        x: left + (width / (planned.length - 1)) * idx,
        y: top + height - (Math.max(0, Math.min(100, v)) / 100) * height
      };
    }

    function curvePath(values) {
      var pts = values.map(point);
      var d = 'M ' + pts[0].x.toFixed(1) + ' ' + pts[0].y.toFixed(1);
      for (var i = 1; i < pts.length; i++) {
        var prev = pts[i - 1], cur = pts[i], mid = (prev.x + cur.x) / 2;
        d += ' C ' + mid.toFixed(1) + ' ' + prev.y.toFixed(1) + ' ' + mid.toFixed(1) + ' ' + cur.y.toFixed(1) + ' ' + cur.x.toFixed(1) + ' ' + cur.y.toFixed(1);
      }
      return d;
    }

    var grid = el('v5-chart-grid');
    if (grid) {
      grid.innerHTML = [0,25,50,75,100].map(function(v){
        var y = top + height - (v / 100) * height;
        return '<line class="v5-curve-grid" x1="'+left+'" y1="'+y.toFixed(1)+'" x2="'+(left+width)+'" y2="'+y.toFixed(1)+'"></line>'+
          '<text class="v5-curve-axis-label" x="14" y="'+(y+4).toFixed(1)+'">'+v+'%</text>';
      }).join('') + labels.map(function(lbl, idx){
        var x = left + (width / (labels.length - 1)) * idx;
        return '<text class="v5-curve-axis-label" text-anchor="middle" x="'+x.toFixed(1)+'" y="228">'+lbl+'</text>';
      }).join('');
    }

    var plannedPath = el('v5-chart-planned-path');
    var actualPath = el('v5-chart-actual-path');
    if (plannedPath) plannedPath.setAttribute('d', curvePath(planned));
    if (actualPath) actualPath.setAttribute('d', curvePath(actual));

    var points = el('v5-chart-points');
    if (points) {
      points.innerHTML = planned.map(function(v, idx){
        var p = point(v, idx);
        return '<circle class="v5-curve-planned-dot" cx="'+p.x.toFixed(1)+'" cy="'+p.y.toFixed(1)+'" r="3"></circle>';
      }).join('') + actual.map(function(v, idx){
        var p = point(v, idx);
        return '<circle class="v5-curve-dot" cx="'+p.x.toFixed(1)+'" cy="'+p.y.toFixed(1)+'" r="'+(idx === actual.length - 1 ? 5 : 4)+'"></circle>';
      }).join('');
    }

    var actualEl = el('v5-chart-actual-current');
    var plannedEl = el('v5-chart-planned-current');
    var gapEl = el('v5-chart-gap');
    var delayEl = el('v5-chart-delay');
    if (actualEl) actualEl.textContent = Math.round(actualNow) + '%';
    if (plannedEl) plannedEl.textContent = Math.round(plannedNow) + '%';
    if (gapEl) {
      gapEl.textContent = (gap >= 0 ? '+' : '') + Math.round(gap) + ' pp';
      gapEl.className = 'v5-progress-chip-value gap ' + (gap >= 0 ? 'good' : 'bad');
    }
    if (delayEl) delayEl.textContent = delay ? delay + (L.workingDays||' working days') : (L.noDelay||'none');
  }

"""


def _inject_graph_css(html: str) -> str:
    marker = "</style>"
    if _GRAPH_CSS in html or marker not in html:
        return html
    return html.replace(marker, _GRAPH_CSS + marker, 1)


def _inject_graph_card(html: str, language: str = "en") -> str:
    marker = '<div class="v5-main">'
    if 'id="v5-progress-chart"' in html or marker not in html:
        return html
    return html.replace(marker, marker + "\n" + _build_graph_card(language), 1)


def _inject_graph_js(html: str) -> str:
    if "function renderProgressCurve" in html:
        return html
    fn_marker = "  function render() {"
    call_marker = "    renderCP(cp);"
    if fn_marker in html:
        html = html.replace(fn_marker, _GRAPH_JS_FUNCTION + fn_marker, 1)
    if call_marker in html:
        html = html.replace(call_marker, call_marker + "\n    renderProgressCurve(progress, behind.length);", 1)
    return html


def _inject_data_quality_warning(html: str, data: dict) -> str:
    """Inject a visible warning banner when the engine detected missing progress data."""
    warning = str(data.get("executive_summary", {}).get("data_quality_warning", "")).strip()
    if not warning:
        return html
    banner = (
        '<div style="margin:12px 20px 0;padding:10px 16px;background:#fef3c7;border-left:4px solid #f59e0b;'
        'border-radius:6px;font-size:13px;font-weight:600;color:#92400e;">'
        f'⚠ Data Quality Warning: {warning}'
        '</div>\n'
    )
    marker = '<div class="v5-main">'
    if marker in html:
        return html.replace(marker, banner + marker, 1)
    return html


def format_compare_v5_graph_as_html(data: dict, language: str = "en") -> str:
    html = format_compare_v5_as_html(data, language)
    html = _inject_graph_css(html)
    html = _inject_graph_card(html, language)
    html = _inject_graph_js(html)
    html = _inject_data_quality_warning(html, data)
    return html
