"""Patches v5_dashboard_output.html with compact top + larger body fonts."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

HTML = 'C:/work/gac/nova/rag-ai-azure/nova-ai-backend-bridge/test_outputs/v5_dashboard_output.html'

with open(HTML, encoding='utf-8') as f:
    h = f.read()

# ── 1. CSS overrides ─────────────────────────────────────────────────────────
CSS_OVERRIDE = """
/* ===== COMPACT TOP ===== */
.v5-header{padding:5px 16px!important;gap:8px!important;}
.v5-logo{width:26px!important;height:26px!important;border-radius:7px!important;}
.v5-header-text{flex-direction:row!important;align-items:center!important;gap:6px!important;}
.v5-header-brand{font-size:9px!important;letter-spacing:1.5px!important;}
.v5-header-title{font-size:14px!important;line-height:1!important;}
.v5-header-sub{font-size:10px!important;margin-left:2px!important;}
.v5-badge{font-size:12px!important;padding:4px 10px!important;}
/* Hide old hero children */
.v5-hero{padding:0!important;}
.v5-hero-label,.v5-progress-hero,.v5-kpi-row{display:none!important;}
/* Topbar */
.v5-topbar{display:flex;align-items:stretch;background:#fff;border-bottom:2px solid #e2e8f0;}
.v5-prog-zone{display:flex;align-items:center;padding:10px 20px;border-right:2px solid #e2e8f0;gap:2px;flex-shrink:0;}
.v5-prog-blk{display:flex;flex-direction:column;padding:0 10px;}
.v5-prog-lbl2{font-size:9px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;color:#94a3b8;margin-bottom:1px;}
.v5-prog-big{font-size:42px;font-weight:900;line-height:1;letter-spacing:-2px;}
.v5-prog-big.red{color:#dc2626;}.v5-prog-big.amber{color:#b45309;}.v5-prog-big.green{color:#059669;}
.v5-prog-meta2{font-size:10px;color:#64748b;margin-top:4px;}
.v5-prog-arr2{font-size:18px;color:#cbd5e1;padding:0 6px;flex-shrink:0;}
.v5-dchip{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:8px 12px;border-radius:10px;margin-left:8px;flex-shrink:0;}
.v5-dchip.pos{background:rgba(5,150,105,0.08);border:1px solid rgba(5,150,105,0.2);}
.v5-dchip.neg{background:rgba(220,38,38,0.08);border:1px solid rgba(220,38,38,0.2);}
.v5-dnum{font-size:22px;font-weight:900;line-height:1;}
.v5-dchip.pos .v5-dnum{color:#059669;}.v5-dchip.neg .v5-dnum{color:#dc2626;}
.v5-dlbl{font-size:8px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;margin-top:2px;}
.v5-dchip.pos .v5-dlbl{color:#059669;}.v5-dchip.neg .v5-dlbl{color:#dc2626;}
/* KPI strip */
.v5-kstrip{display:flex;flex:1;}
.v5-ki{flex:1;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;padding:10px 14px;border-left:1px solid #f0f2f5;}
.v5-ki-num{font-size:32px;font-weight:900;line-height:1;}
.v5-ki-num.red{color:#dc2626;}.v5-ki-num.blue{color:#0284c7;}.v5-ki-num.purple{color:#7c3aed;}.v5-ki-num.green{color:#059669;}
.v5-ki-lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px;color:#64748b;margin-top:3px;white-space:nowrap;}
/* ===== LARGER BODY FONTS ===== */
.v5-card-title{font-size:13px!important;}
.v5-card-sub{font-size:11px!important;}
.v5-table thead th{font-size:11px!important;padding:8px 10px!important;}
.v5-table tbody td{font-size:12px!important;padding:8px 10px!important;}
.v5-act-name{font-size:12px!important;}
.v5-loc-badge{font-size:10px!important;padding:2px 6px!important;}
.v5-filter-group-title{font-size:10px!important;letter-spacing:1px!important;}
.v5-filter-opt{font-size:12px!important;padding:6px 10px!important;}
.v5-filter-count{font-size:10px!important;}
.v5-ponr-name{font-size:12px!important;}
.v5-ponr-rec{font-size:11px!important;}
.v5-driver-name{font-size:13px!important;}
.v5-driver-desc{font-size:12px!important;}
.v5-driver-count{font-size:11px!important;}
.v5-summary-row{font-size:13px!important;padding:7px 0!important;}
.v5-wsid-activity{font-size:14px!important;}
.v5-wsid-issue{font-size:12px!important;}
.v5-actions-list li{font-size:12px!important;padding:4px 0!important;}
.v5-imp{font-size:10px!important;padding:2px 7px!important;}
.v5-change-kpi-num{font-size:22px!important;}
.v5-change-kpi-lbl{font-size:10px!important;}
.v5-change-section-lbl{font-size:11px!important;}
"""

# Inject before </style> of v5 CSS block (the one after @import)
import_pos   = h.find('@import')
style_close  = h.find('</style>', import_pos)
h = h[:style_close] + CSS_OVERRIDE + h[style_close:]

# ── 2. Replace header ────────────────────────────────────────────────────────
OLD_HEADER = (
    '<div class="v5-header">\n'
    '  <div class="v5-logo">\n'
    '    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">\n'
    '      <path d="M2 20h20M6 20V10M12 20V4M18 20v-6"/>\n'
    '    </svg>\n'
    '  </div>\n'
    '  <div class="v5-header-text">\n'
    '    <p class="v5-header-brand">Nova Insight</p>\n'
    '    <h1 class="v5-header-title">PROJECT HEALTH DASHBOARD</h1>\n'
    '    <p class="v5-header-sub">Are we on track? Where is the problem? What should I do?</p>\n'
    '  </div>\n'
    '  <div style="margin-left:auto" id="v5-status-badge-wrap">'
)

NEW_HEADER = (
    '<div class="v5-header">\n'
    '  <div class="v5-logo">\n'
    '    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5">'
    '<path d="M2 20h20M6 20V10M12 20V4M18 20v-6"/></svg>\n'
    '  </div>\n'
    '  <div class="v5-header-text">\n'
    '    <span class="v5-header-brand">Nova Insight</span>\n'
    '    <span style="color:#e2e8f0;margin:0 4px;">|</span>\n'
    '    <span class="v5-header-title">PROJECT HEALTH DASHBOARD</span>\n'
    '    <span class="v5-header-sub">&nbsp;&middot; Are we on track? Where is the problem? What should I do?</span>\n'
    '  </div>\n'
    '  <div style="margin-left:auto" id="v5-status-badge-wrap">'
)

if OLD_HEADER in h:
    h = h.replace(OLD_HEADER, NEW_HEADER)
    print('Header replaced OK')
else:
    print('WARNING: old header not found, skipping')

# ── 3. Replace hero section ──────────────────────────────────────────────────
hero_start = h.find('<div class="v5-hero">')
hero_end   = h.find('<div class="v5-page-body">')
old_hero   = h[hero_start:hero_end]

NEW_HERO = '''<div class="v5-hero">
<div class="v5-topbar">
  <div class="v5-prog-zone">
    <div class="v5-prog-blk">
      <span class="v5-prog-lbl2">Previous &middot; 2025-08-15</span>
      <span class="v5-prog-big red">49.1%</span>
    </div>
    <span class="v5-prog-arr2">&rarr;</span>
    <div class="v5-prog-blk">
      <span class="v5-prog-lbl2">Current &middot; 2025-10-01</span>
      <span class="v5-prog-big amber">54.2%</span>
      <span class="v5-prog-meta2">
        <strong style="color:#0f172a">214</strong> total &nbsp;&middot;&nbsp;
        <strong style="color:#dc2626">11</strong> late &nbsp;&middot;&nbsp;
        <strong style="color:#059669">18</strong> done
      </span>
    </div>
    <div class="v5-dchip pos">
      <span class="v5-dnum">+5.1</span>
      <span class="v5-dlbl">pp change</span>
    </div>
  </div>
  <div class="v5-kstrip">
    <div class="v5-ki">
      <span class="v5-ki-num red" id="v5-kpi-highrisk">5</span>
      <span class="v5-ki-lbl">High Risk</span>
    </div>
    <div class="v5-ki">
      <span class="v5-ki-num blue" id="v5-kpi-analyzed">214</span>
      <span class="v5-ki-lbl">Activities</span>
    </div>
    <div class="v5-ki">
      <span class="v5-ki-num red" id="v5-kpi-critical">8</span>
      <span class="v5-ki-lbl">Critical</span>
    </div>
    <div class="v5-ki">
      <span class="v5-ki-num purple" id="v5-kpi-cp">7</span>
      <span class="v5-ki-lbl">Critical Path</span>
    </div>
    <div class="v5-ki">
      <span class="v5-ki-num red" id="v5-kpi-behind">11</span>
      <span class="v5-ki-lbl">Behind</span>
    </div>
    <div class="v5-ki">
      <span class="v5-ki-num green" id="v5-kpi-ahead">7</span>
      <span class="v5-ki-lbl">Ahead</span>
    </div>
  </div>
</div>
</div>
'''

h = h[:hero_start] + NEW_HERO + h[hero_end:]
print('Hero replaced OK')

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(h)

print('Written:', len(h), 'chars')
for chk in ['v5-topbar','v5-prog-zone','v5-kstrip','v5-ki-num','v5-kpi-highrisk','v5-kpi-behind','v5-dchip']:
    print(' ', 'OK' if chk in h else 'MISSING', chk)
