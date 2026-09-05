import re
import json

def format_compare_v2_as_html(data: dict, language: str = "en") -> str:
    """
    Formats the structured v2 comparison data into a PM dashboard style HTML report
    that is 1-1 consistent with the premium styles of html_formatter.py.
    """
    
    html = []
    html.append('''
    <style>
        .nova-dashboard {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #1e293b;
            line-height: 1.6;
            max-width: 1100px;
            margin: 0 auto;
            padding: 16px;
        }
        
        /* Banner Header */
        .nova-header-banner {
            background: linear-gradient(135deg, #0f172a, #1e293b);
            border-radius: 16px;
            padding: 24px 32px;
            margin-bottom: 32px;
            box-shadow: 0 4px 20px rgba(15, 23, 42, 0.15);
            display: flex;
            align-items: center;
            justify-content: space-between;
            color: #ffffff;
        }
        .nova-header-info h1 {
            font-size: 24px;
            font-weight: 800;
            margin: 0;
            letter-spacing: -0.5px;
            background: linear-gradient(to right, #00D6D6, #38bdf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .nova-header-info p {
            font-size: 14px;
            color: #94a3b8;
            margin: 6px 0 0 0;
        }

        /* Card System (Matched to html_formatter.py) */
        .nova-card {
            background: #ffffff;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .nova-card:hover {
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
        }
        
        /* Header section block (Inspired by html_formatter.py) */
        .section-header-block {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 20px;
            padding-bottom: 16px;
        }
        
        .section-header-icon-box {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
        }

        /* Scope activities list styling */
        .scope-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 12px;
            padding: 0;
            list-style-type: none;
            margin: 0;
        }
        .scope-list li {
            padding: 10px 14px;
            background: #f8fafc;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            font-size: 13px;
            font-weight: 550;
            color: #334155;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .scope-list li::before {
            content: "✓";
            color: #10b981;
            font-weight: bold;
        }

        /* Section Headings for changes */
        .changes-group-title {
            font-size: 14px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 20px;
            margin-bottom: 12px;
            color: #64748b;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .changes-group-title.added { color: #10b981; }
        .changes-group-title.removed { color: #ef4444; }
        .changes-group-title.start_changes { color: #f59e0b; }
        .changes-group-title.finish_changes { color: #ef4444; }
        .changes-group-title.duration_changes { color: #0ea5e9; }

        /* List-unstyled for items */
        .list-unstyled {
            list-style-type: none;
            padding-left: 0;
            margin: 0;
        }
        .list-unstyled li {
            padding: 12px 16px;
            background: #f8fafc;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
            margin-bottom: 8px;
            font-size: 13px;
            color: #334155;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
        }
        .list-unstyled li strong {
            color: #0f172a;
            font-weight: 600;
        }
        .change-detail-badge {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            color: #475569;
            font-family: monospace;
        }

        /* Tables Premium Styling */
        .nova-table-wrapper {
            overflow-x: auto;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
        }
        .nova-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 13.5px;
        }
        .nova-table th, .nova-table td {
            text-align: left;
            padding: 12px 16px;
        }
        .nova-table th {
            background-color: #f8fafc;
            font-weight: 700;
            color: #475569;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
            border-bottom: 2px solid #e2e8f0;
        }
        .nova-table td {
            border-bottom: 1px solid #f1f5f9;
            color: #334155;
        }
        .nova-table tbody tr:last-child td {
            border-bottom: none;
        }
        .nova-table tbody tr:hover {
            background-color: #f8fafc;
        }

        /* Status Badge */
        .nova-badge {
            display: inline-flex;
            align-items: center;
            padding: 5px 12px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            border: 1px solid transparent;
        }
        .badge-ahead {
            background-color: rgba(16, 185, 129, 0.12);
            color: #059669;
            border-color: rgba(16, 185, 129, 0.2);
        }
        .badge-on {
            background-color: rgba(245, 158, 11, 0.12);
            color: #d97706;
            border-color: rgba(245, 158, 11, 0.2);
        }
        .badge-behind {
            background-color: rgba(239, 68, 68, 0.12);
            color: #dc2626;
            border-color: rgba(239, 68, 68, 0.2);
        }
        .badge-critical {
            background-color: rgba(239, 68, 68, 0.15);
            color: #b91c1c;
            font-weight: 700;
            border: 1px solid rgba(239, 68, 68, 0.3);
            box-shadow: 0 2px 4px rgba(239, 68, 68, 0.05);
        }
        
        .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
        }
        .dot-green { background-color: #10b981; }
        .dot-yellow { background-color: #f59e0b; }
        .dot-red { background-color: #ef4444; }
    </style>
    ''')

    html.append('<div class="nova-dashboard">')

    # Banner Header (Uses high-end styling with configurable title)
    title = "Nova Targeted Comparison Report"
    subtitle = "Scope alignment and progression delta tracking"
    
    html.append(f'''
    <div class="nova-header-banner">
        <div class="nova-header-info">
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        <div style="font-size: 13px; font-weight: 600; color: #38bdf8; background: rgba(56, 189, 248, 0.1); padding: 6px 14px; border-radius: 8px;">
            Target: Comparison Analysis
        </div>
    </div>
    ''')

    # Scope Summary (uses id="section-data-trust" for navbar compatibility)
    scope_acts = data.get("scope_activities", [])
    if scope_acts:
        html.append(f'''
        <div id="section-data-trust" class="nova-card" style="border-left: 5px solid #0ea5e9;">
            <div class="section-header-block" style="border-bottom: 2px solid rgba(14, 165, 233, 0.1);">
                <div class="section-header-icon-box" style="background: linear-gradient(135deg, #0ea5e9, #0284c7); box-shadow: 0 4px 14px rgba(14, 165, 233, 0.3);">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                </div>
                <div>
                    <h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0;">Included Scope Activities</h2>
                    <div style="font-size:12px;color:#64748b;margin-top:2px;">Discipline scope size: {len(scope_acts)} activities</div>
                </div>
            </div>
            <ul class="scope-list">
                {''.join(f'<li>{act}</li>' for act in scope_acts[:24])}
                {f'<li style="background: none; border: none; font-style: italic; color: #64748b;">... and {len(scope_acts) - 24} more activities.</li>' if len(scope_acts) > 24 else ''}
            </ul>
        </div>
        ''')

    # Section 1: Changed Activities (uses id="section-summary-changes" or id="section-comparison" for navbar compatibility)
    changes = data.get("changed_activities", {})
    if changes:
        has_changes = any(changes.get(k) for k in ["added", "removed", "start_changes", "finish_changes", "duration_changes"])
        if has_changes:
            html.append('''
            <div id="section-comparison" class="nova-card" style="border-left: 5px solid #f59e0b;">
                <div class="section-header-block" style="border-bottom: 2px solid rgba(245, 158, 11, 0.1);">
                    <div class="section-header-icon-box" style="background: linear-gradient(135deg, #f59e0b, #d97706); box-shadow: 0 4px 14px rgba(245, 158, 11, 0.3);">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M16 3h5v5M4 20L21 3M21 16v5h-5M4 4l5 5"/></svg>
                    </div>
                    <div>
                        <h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0;">Schedule Changes</h2>
                        <div style="font-size:12px;color:#64748b;margin-top:2px;">Deltas identified between versions</div>
                    </div>
                </div>
            ''')
            
            icon_map = {
                "added": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
                "removed": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
                "start_changes": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
                "finish_changes": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>',
                "duration_changes": '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21.21 15.89A10 10 0 1 1 8 2.83M22 12A10 10 0 0 0 12 2v10z"/></svg>'
            }

            for k, label in [("added", "Added Activities"), ("removed", "Removed Activities"), 
                             ("start_changes", "Start Date Changes"), ("finish_changes", "Finish Date Changes"), 
                             ("duration_changes", "Duration Changes")]:
                items = changes.get(k, [])
                if items:
                    html.append(f'''
                    <div class="changes-group-title {k}">
                        {icon_map.get(k, '')}
                        <span>{label}</span>
                    </div>
                    ''')
                    html.append('<ul class="list-unstyled">')
                    for item in items:
                        if isinstance(item, dict):
                            name = item.get("activity") or item.get("name", "Unknown")
                            old_val = item.get("old", "-")
                            new_val = item.get("new", "-")
                            html.append(f'<li><strong>{name}</strong> <span class="change-detail-badge">Old: {old_val} ➔ New: {new_val}</span></li>')
                        else:
                            html.append(f'<li>{item}</li>')
                    html.append('</ul>')
            html.append('</div>')

    # Section 2: Progress Status vs Schedule (uses id="section-project-health" for navbar compatibility)
    status_items = data.get("progress_status", [])
    if status_items:
        html.append('''
        <div id="section-project-health" class="nova-card" style="border-left: 5px solid #10b981;">
            <div class="section-header-block" style="border-bottom: 2px solid rgba(16, 185, 129, 0.1);">
                <div class="section-header-icon-box" style="background: linear-gradient(135deg, #10b981, #059669); box-shadow: 0 4px 14px rgba(16, 185, 129, 0.3);">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/></svg>
                </div>
                <div>
                    <h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0;">Progress Status vs Schedule</h2>
                    <div style="font-size:12px;color:#64748b;margin-top:2px;">Discipline timeline status</div>
                </div>
            </div>
            <div class="nova-table-wrapper">
                <table class="nova-table">
                    <thead>
                        <tr>
                            <th style="width: 160px;">Status</th>
                            <th>Activity</th>
                        </tr>
                    </thead>
                    <tbody>
        ''')
        for item in status_items:
            stat_raw = str(item.get("status", "")).lower()
            if "ahead" in stat_raw:
                dot = "dot-green"
                badge = "badge-ahead"
                lbl = "Ahead"
            elif "behind" in stat_raw:
                dot = "dot-red"
                badge = "badge-behind"
                lbl = "Behind"
            else:
                dot = "dot-yellow"
                badge = "badge-on"
                lbl = "On Schedule"
                
            name = item.get("activity") or item.get("name", "")
            
            html.append(f'''
                <tr>
                    <td><span class="nova-badge {badge}"><span class="status-dot {dot}"></span>{lbl}</span></td>
                    <td>{name}</td>
                </tr>
            ''')
        html.append('</tbody></table></div></div>')

    # Section 3: Variance Analysis (uses id="section-estimated-impact" for navbar compatibility)
    variance_items = data.get("variance_analysis", [])
    if variance_items:
        html.append('''
        <div id="section-estimated-impact" class="nova-card" style="border-left: 5px solid #ef4444;">
            <div class="section-header-block" style="border-bottom: 2px solid rgba(239, 68, 68, 0.1);">
                <div class="section-header-icon-box" style="background: linear-gradient(135deg, #ef4444, #dc2626); box-shadow: 0 4px 14px rgba(239, 68, 68, 0.3);">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                </div>
                <div>
                    <h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0;">Progress Variance Analysis</h2>
                    <div style="font-size:12px;color:#64748b;margin-top:2px;">Discipline variance metrics</div>
                </div>
            </div>
            <div class="nova-table-wrapper">
                <table class="nova-table">
                    <thead>
                        <tr>
                            <th>Activity</th>
                            <th>Expected %</th>
                            <th>Actual %</th>
                            <th>Variance</th>
                            <th style="width: 140px;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
        ''')
        for item in variance_items:
            name = item.get("activity") or item.get("name", "")
            exp = item.get("expected_pct", "-")
            act = item.get("actual_pct", "-")
            var = item.get("variance", "-")
            st = str(item.get("status", ""))
            
            if "critical" in st.lower():
                st_html = f'<span class="nova-badge badge-critical">{st}</span>'
            else:
                st_html = st
                
            var_style = ''
            if var.startswith('+'):
                var_style = ' style="color: #10b981; font-weight: 700;"'
            elif var.startswith('-'):
                var_style = ' style="color: #ef4444; font-weight: 700;"'
                
            html.append(f'''
                <tr>
                    <td>{name}</td>
                    <td>{exp}</td>
                    <td>{act}</td>
                    <td{var_style}>{var}</td>
                    <td>{st_html}</td>
                </tr>
            ''')
        html.append('</tbody></table></div></div>')

    html.append('</div>')
    return "\n".join(html)
