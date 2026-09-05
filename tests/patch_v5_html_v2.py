"""Patch 2: add KPI icons, larger KPI labels, larger card titles."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

HTML = 'C:/work/gac/nova/rag-ai-azure/nova-ai-backend-bridge/test_outputs/v5_dashboard_output.html'

with open(HTML, encoding='utf-8') as f:
    h = f.read()

# ── 1. Extra CSS overrides ───────────────────────────────────────────────────
EXTRA_CSS = """
/* KPI strip with icons */
.v5-ki{padding:8px 16px!important;}
.v5-ki-row2{display:flex;align-items:center;gap:7px;margin-bottom:4px;}
.v5-ki-ico{width:22px;height:22px;border-radius:6px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
.v5-ki-num{font-size:28px!important;line-height:1;}
.v5-ki-lbl{font-size:12px!important;font-weight:700!important;letter-spacing:0.3px!important;}

/* Card titles — larger, compensate with tighter header padding */
.v5-card-title{font-size:15px!important;font-weight:800!important;}
.v5-card-sub{font-size:11px!important;color:#64748b!important;}
.v5-card-header{padding-bottom:7px!important;margin-bottom:8px!important;}
.v5-card-icon{width:28px!important;height:28px!important;}

/* Critical path card title */
#v5-cp-hdr{font-size:15px!important;}
#v5-critical-hdr{font-size:15px!important;}
#v5-behind-hdr{font-size:15px!important;}
#v5-ahead-hdr{font-size:15px!important;}
"""

# Inject before the first </style> that follows the EXTRA CSS we already added
# Find the last </style> before the data script
data_pos = h.find('<script>window.__v5Data')
last_style_close = h.rfind('</style>', 0, data_pos)
h = h[:last_style_close] + EXTRA_CSS + h[last_style_close:]

# ── 2. Replace KPI strip with icon version ────────────────────────────────────
OLD_KSTRIP = '''<div class="v5-kstrip">
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
  </div>'''

NEW_KSTRIP = '''<div class="v5-kstrip">

    <div class="v5-ki">
      <div class="v5-ki-row2">
        <div class="v5-ki-ico" style="background:rgba(239,68,68,0.12)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2.5">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
          </svg>
        </div>
        <span class="v5-ki-num red" id="v5-kpi-highrisk">5</span>
      </div>
      <span class="v5-ki-lbl" style="color:#dc2626">High Risk</span>
    </div>

    <div class="v5-ki">
      <div class="v5-ki-row2">
        <div class="v5-ki-ico" style="background:rgba(2,132,199,0.12)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#0284c7" stroke-width="2.5">
            <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
          </svg>
        </div>
        <span class="v5-ki-num blue" id="v5-kpi-analyzed">214</span>
      </div>
      <span class="v5-ki-lbl" style="color:#0284c7">Activities</span>
    </div>

    <div class="v5-ki">
      <div class="v5-ki-row2">
        <div class="v5-ki-ico" style="background:rgba(239,68,68,0.12)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2.5">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        </div>
        <span class="v5-ki-num red" id="v5-kpi-critical">8</span>
      </div>
      <span class="v5-ki-lbl" style="color:#dc2626">Critical</span>
    </div>

    <div class="v5-ki">
      <div class="v5-ki-row2">
        <div class="v5-ki-ico" style="background:rgba(124,58,237,0.12)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#7c3aed" stroke-width="2.5">
            <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
          </svg>
        </div>
        <span class="v5-ki-num purple" id="v5-kpi-cp">7</span>
      </div>
      <span class="v5-ki-lbl" style="color:#7c3aed">Critical Path</span>
    </div>

    <div class="v5-ki">
      <div class="v5-ki-row2">
        <div class="v5-ki-ico" style="background:rgba(239,68,68,0.12)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2.5">
            <polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/>
            <polyline points="16 17 22 17 22 11"/>
          </svg>
        </div>
        <span class="v5-ki-num red" id="v5-kpi-behind">11</span>
      </div>
      <span class="v5-ki-lbl" style="color:#dc2626">Behind</span>
    </div>

    <div class="v5-ki">
      <div class="v5-ki-row2">
        <div class="v5-ki-ico" style="background:rgba(5,150,105,0.12)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="2.5">
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>
            <polyline points="16 7 22 7 22 13"/>
          </svg>
        </div>
        <span class="v5-ki-num green" id="v5-kpi-ahead">7</span>
      </div>
      <span class="v5-ki-lbl" style="color:#059669">Ahead</span>
    </div>

  </div>'''

if OLD_KSTRIP in h:
    h = h.replace(OLD_KSTRIP, NEW_KSTRIP)
    print('KPI strip replaced OK')
else:
    print('WARNING: old kstrip not found exactly — trying partial match')
    s = h.find('<div class="v5-kstrip">')
    e = h.find('</div>\n</div>\n<div class="v5-page-body">')
    if s != -1 and e != -1:
        h = h[:s] + NEW_KSTRIP + h[e:]
        print('KPI strip replaced via position OK')
    else:
        print('ERROR: could not replace kstrip')

with open(HTML, 'w', encoding='utf-8') as f:
    f.write(h)

print('Written:', len(h), 'chars')
for chk in ['v5-ki-ico', 'v5-ki-row2', 'v5-ki-lbl', 'v5-kpi-behind']:
    print(' ', 'OK' if chk in h else 'MISSING', chk)
