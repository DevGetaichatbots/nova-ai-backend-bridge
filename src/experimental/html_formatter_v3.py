def format_compare_v3_as_html(data: dict, language: str = "en") -> str:
    html = []

    html.append('''<style>
    .nv3 {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        color: #1e293b;
        line-height: 1.6;
        max-width: 1100px;
        margin: 0 auto;
        padding: 16px;
    }
    .nv3-banner {
        background: linear-gradient(135deg, #0f172a, #1e293b);
        border-radius: 16px;
        padding: 24px 32px;
        margin-bottom: 28px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        color: #fff;
        box-shadow: 0 4px 20px rgba(15,23,42,0.15);
    }
    .nv3-banner h1 {
        font-size: 22px;
        font-weight: 800;
        margin: 0;
        background: linear-gradient(to right, #00D6D6, #38bdf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .nv3-banner p { font-size: 13px; color: #94a3b8; margin: 4px 0 0; }
    .nv3-card {
        background: #fff;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    }
    .nv3-card-header {
        display: flex;
        align-items: center;
        gap: 14px;
        padding-bottom: 16px;
        margin-bottom: 20px;
        border-bottom: 2px solid #f1f5f9;
    }
    .nv3-icon {
        width: 44px; height: 44px;
        border-radius: 12px;
        display: flex; align-items: center; justify-content: center;
        color: #fff; flex-shrink: 0;
    }
    .nv3-card-header h2 { font-size: 19px; font-weight: 800; color: #0f172a; margin: 0; }
    .nv3-card-header small { font-size: 12px; color: #64748b; margin-top: 2px; display: block; }

    /* Health badge */
    .nv3-health {
        display: inline-flex; align-items: center; gap: 10px;
        padding: 10px 22px; border-radius: 50px; font-size: 18px; font-weight: 800;
        letter-spacing: 0.5px;
    }
    .health-green { background: rgba(16,185,129,0.12); color: #059669; border: 2px solid rgba(16,185,129,0.3); }
    .health-yellow { background: rgba(245,158,11,0.12); color: #b45309; border: 2px solid rgba(245,158,11,0.3); }
    .health-red { background: rgba(239,68,68,0.12); color: #dc2626; border: 2px solid rgba(239,68,68,0.3); }

    /* Stat pills row */
    .nv3-stats { display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0; }
    .nv3-stat {
        background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
        padding: 10px 18px; text-align: center; min-width: 120px;
    }
    .nv3-stat-val { font-size: 28px; font-weight: 800; color: #0f172a; line-height: 1; }
    .nv3-stat-val.red { color: #dc2626; }
    .nv3-stat-val.green { color: #059669; }
    .nv3-stat-val.amber { color: #b45309; }
    .nv3-stat-lbl { font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; margin-top: 4px; }

    /* Recommended action box */
    .nv3-action-box {
        background: #0f172a; color: #e2e8f0; border-radius: 10px;
        padding: 14px 20px; margin-top: 16px; font-size: 14px; font-weight: 500;
        display: flex; align-items: flex-start; gap: 10px;
    }
    .nv3-action-box strong { color: #38bdf8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px; }

    /* Tables */
    .nv3-table-wrap { overflow-x: auto; border-radius: 12px; border: 1px solid #e2e8f0; }
    .nv3-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13.5px; }
    .nv3-table th {
        background: #f8fafc; font-weight: 700; color: #475569;
        text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px;
        padding: 11px 14px; border-bottom: 2px solid #e2e8f0; text-align: left;
    }
    .nv3-table td { padding: 11px 14px; border-bottom: 1px solid #f1f5f9; color: #334155; }
    .nv3-table tbody tr:last-child td { border-bottom: none; }
    .nv3-table tbody tr:hover { background: #f8fafc; }
    .nv3-table tr.row-red td { background: rgba(239,68,68,0.04); }
    .nv3-table tr.row-amber td { background: rgba(245,158,11,0.04); }

    /* Badges */
    .nv3-badge {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 4px 11px; border-radius: 8px; font-size: 12px; font-weight: 600; border: 1px solid transparent;
    }
    .b-green  { background: rgba(16,185,129,0.1);  color: #059669; border-color: rgba(16,185,129,0.2); }
    .b-yellow { background: rgba(245,158,11,0.1);  color: #b45309; border-color: rgba(245,158,11,0.2); }
    .b-red    { background: rgba(239,68,68,0.1);   color: #dc2626; border-color: rgba(239,68,68,0.2); }
    .b-blue   { background: rgba(14,165,233,0.1);  color: #0369a1; border-color: rgba(14,165,233,0.2); }
    .b-gray   { background: #f1f5f9; color: #475569; border-color: #e2e8f0; }
    .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; }
    .dot-g { background: #10b981; } .dot-y { background: #f59e0b; } .dot-r { background: #ef4444; }

    /* Variance numbers */
    .var-pos { color: #059669; font-weight: 700; }
    .var-neg { color: #dc2626; font-weight: 700; }

    /* Added/removed pills */
    .nv3-pill-list { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
    .nv3-pill {
        padding: 5px 13px; border-radius: 20px; font-size: 12px; font-weight: 600;
    }
    .pill-added   { background: rgba(16,185,129,0.1); color: #059669; border: 1px solid rgba(16,185,129,0.25); }
    .pill-removed { background: rgba(239,68,68,0.1);  color: #dc2626; border: 1px solid rgba(239,68,68,0.25); }

    /* PONR card */
    .ponr-card {
        border: 2px solid #fecaca; border-radius: 12px; padding: 16px 20px; margin-bottom: 14px;
        background: rgba(239,68,68,0.03);
    }
    .ponr-card-yellow { border-color: #fde68a; background: rgba(245,158,11,0.03); }
    .ponr-title { font-size: 15px; font-weight: 700; color: #0f172a; margin-bottom: 8px; }
    .ponr-grid { display: flex; flex-wrap: wrap; gap: 12px; }
    .ponr-cell { flex: 1; min-width: 100px; }
    .ponr-cell-lbl { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.4px; font-weight: 600; }
    .ponr-cell-val { font-size: 14px; font-weight: 700; color: #0f172a; margin-top: 2px; }
    .ponr-rec { margin-top: 10px; font-size: 13px; color: #475569; border-top: 1px solid #e2e8f0; padding-top: 8px; }

    /* Action recs */
    .action-item { padding: 14px 18px; border-radius: 10px; border: 1px solid #fecaca; background: rgba(239,68,68,0.03); margin-bottom: 12px; }
    .action-item-title { font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }
    .action-item-issue { font-size: 12px; color: #64748b; margin-bottom: 10px; }
    .action-bullets { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 5px; }
    .action-bullets li { font-size: 13px; color: #334155; display: flex; align-items: flex-start; gap: 7px; }
    .action-bullets li::before { content: "→"; color: #ef4444; font-weight: 700; flex-shrink: 0; }
</style>''')

    html.append('<div class="nv3">')

    # ── Banner ──────────────────────────────────────────────────────────────────
    html.append('''
    <div class="nv3-banner">
        <div>
            <h1>Nova Insight — Decision Dashboard</h1>
            <p>v3 · Schedule comparison &amp; recovery analysis</p>
        </div>
        <div style="font-size:13px;font-weight:600;color:#38bdf8;background:rgba(56,189,248,0.1);padding:6px 14px;border-radius:8px;">
            v3 Analysis
        </div>
    </div>''')

    # ── P1: Executive Summary ───────────────────────────────────────────────────
    es = data.get("executive_summary", {})
    health = str(es.get("project_health", "Green"))
    health_cls = {"Red": "health-red", "Yellow": "health-yellow"}.get(health, "health-green")
    health_dot = {"Red": "dot-r", "Yellow": "dot-y"}.get(health, "dot-g")
    health_icon = {"Red": "⚠", "Yellow": "●"}.get(health, "✓")

    stats = [
        ("selected_activities",      "Activities",          ""),
        ("added_activities",         "Added",               "green"),
        ("behind_schedule_count",    "Behind Schedule",     "red"),
        ("ahead_of_schedule_count",  "Ahead of Schedule",   "green"),
        ("critical_count",           "Critical",            "amber"),
        ("point_of_no_return_count", "Point of No Return",  "red"),
    ]

    stat_pills = ""
    for key, label, color_cls in stats:
        val = es.get(key, 0)
        stat_pills += f'<div class="nv3-stat"><div class="nv3-stat-val {color_cls}">{val}</div><div class="nv3-stat-lbl">{label}</div></div>'

    recommended = es.get("recommended_action", "")
    recommended_html = f'<div class="nv3-action-box"><div><strong>Recommended Action</strong>{recommended}</div></div>' if recommended else ""

    html.append(f'''
    <div class="nv3-card" style="border-left:5px solid #0f172a;">
        <div class="nv3-card-header" style="border-bottom-color:rgba(15,23,42,0.08);">
            <div class="nv3-icon" style="background:linear-gradient(135deg,#0f172a,#1e3a5f);box-shadow:0 4px 14px rgba(15,23,42,0.25);">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            </div>
            <div>
                <h2>Executive Summary</h2>
                <small>Project health at a glance — understand the situation in 30 seconds</small>
            </div>
        </div>
        <div style="margin-bottom:16px;">
            <span class="nv3-health {health_cls}">
                <span class="dot {health_dot}"></span>
                Project Health: {health}
            </span>
        </div>
        <div class="nv3-stats">{stat_pills}</div>
        {recommended_html}
    </div>''')

    # ── P2: Change Summary ──────────────────────────────────────────────────────
    changes = data.get("changed_activities", {})
    added = changes.get("added", [])
    removed = changes.get("removed", [])
    flat_changes = changes.get("changes", [])

    if added or removed or flat_changes:
        html.append('''
    <div class="nv3-card" style="border-left:5px solid #f59e0b;">
        <div class="nv3-card-header" style="border-bottom-color:rgba(245,158,11,0.1);">
            <div class="nv3-icon" style="background:linear-gradient(135deg,#f59e0b,#d97706);box-shadow:0 4px 14px rgba(245,158,11,0.25);">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M16 3h5v5M4 20L21 3M21 16v5h-5M4 4l5 5"/></svg>
            </div>
            <div>
                <h2>Change Summary</h2>
                <small>Added, removed, and date/duration changes between schedules</small>
            </div>
        </div>''')

        if added:
            pills = "".join(f'<span class="nv3-pill pill-added">+ {a}</span>' for a in added)
            html.append(f'<div style="margin-bottom:8px;font-size:12px;font-weight:700;color:#059669;text-transform:uppercase;letter-spacing:0.4px;">Added ({len(added)})</div><div class="nv3-pill-list">{pills}</div>')

        if removed:
            pills = "".join(f'<span class="nv3-pill pill-removed">− {r}</span>' for r in removed)
            html.append(f'<div style="margin-bottom:8px;font-size:12px;font-weight:700;color:#dc2626;text-transform:uppercase;letter-spacing:0.4px;">Removed ({len(removed)})</div><div class="nv3-pill-list">{pills}</div>')

        if flat_changes:
            html.append(f'<div style="margin-top:16px;margin-bottom:8px;font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.4px;">Date &amp; Duration Changes ({len(flat_changes)})</div>')
            html.append('<div class="nv3-table-wrap"><table class="nv3-table"><thead><tr><th>Activity</th><th>Change Type</th><th>Old Value</th><th>New Value</th></tr></thead><tbody>')
            for ch in flat_changes:
                name = ch.get("activity", "")
                ctype = ch.get("change_type", "")
                old_v = ch.get("old", "")
                new_v = ch.get("new", "")
                html.append(f'<tr><td>{name}</td><td><span class="nv3-badge b-blue">{ctype}</span></td><td style="color:#64748b;">{old_v}</td><td style="font-weight:600;">{new_v}</td></tr>')
            html.append('</tbody></table></div>')

        html.append('</div>')

    # ── P3: Activities That Should Have Started — always render ─────────────────
    not_started = data.get("not_started_overdue", [])
    subtitle = f"0% progress — planned start date already passed ({len(not_started)} activities)" if not_started else "0% progress — planned start date already passed"
    html.append(f'''
    <div class="nv3-card" style="border-left:5px solid #ef4444;">
        <div class="nv3-card-header" style="border-bottom-color:rgba(239,68,68,0.1);">
            <div class="nv3-icon" style="background:linear-gradient(135deg,#ef4444,#dc2626);box-shadow:0 4px 14px rgba(239,68,68,0.25);">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
            <div>
                <h2>Activities That Should Have Started</h2>
                <small>{subtitle}</small>
            </div>
        </div>''')
    if not_started:
        html.append('''<div class="nv3-table-wrap"><table class="nv3-table">
            <thead><tr><th>ID</th><th>Activity</th><th>Planned Start</th><th>Planned Finish</th><th>Progress</th></tr></thead>
            <tbody>''')
        for item in not_started:
            id_ = item.get("id", "—")
            name = item.get("activity", "")
            start = item.get("start_date", "")
            finish = item.get("finish_date", "")
            html.append(f'<tr class="row-red"><td style="color:#64748b;">{id_}</td><td style="font-weight:600;">{name}</td><td>{start}</td><td>{finish}</td><td><span class="nv3-badge b-red">0%</span></td></tr>')
        html.append('</tbody></table></div>')
    else:
        html.append('<div style="padding:16px 0;color:#64748b;font-size:13px;display:flex;align-items:center;gap:8px;"><span class="nv3-badge b-green">✓</span> No activities found with 0% progress and a missed start date — all work is either underway or not yet due.</div>')
    html.append('</div>')

    # ── P4: Progress vs Expected ────────────────────────────────────────────────
    progress_items = data.get("progress_vs_expected", [])
    if progress_items:
        html.append(f'''
    <div class="nv3-card" style="border-left:5px solid #10b981;">
        <div class="nv3-card-header" style="border-bottom-color:rgba(16,185,129,0.1);">
            <div class="nv3-icon" style="background:linear-gradient(135deg,#10b981,#059669);box-shadow:0 4px 14px rgba(16,185,129,0.25);">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
            </div>
            <div>
                <h2>Progress vs Expected</h2>
                <small>Actual % compared to expected % based on elapsed calendar time ({len(progress_items)} activities)</small>
            </div>
        </div>
        <div class="nv3-table-wrap">
            <table class="nv3-table">
                <thead><tr><th>Activity</th><th>Expected %</th><th>Actual %</th><th>Variance</th><th>Status</th></tr></thead>
                <tbody>''')
        for item in progress_items:
            name = item.get("activity", "")
            exp = item.get("expected_pct", "—")
            act = item.get("actual_pct", "—")
            var = item.get("variance_pct", 0)
            status = str(item.get("status", "")).lower()

            try:
                var_f = float(var)
                var_str = f"{var_f:+.0f}%"
                var_cls = "var-pos" if var_f > 0 else "var-neg" if var_f < 0 else ""
            except (ValueError, TypeError):
                var_str = str(var)
                var_cls = ""

            if "behind" in status:
                badge = '<span class="nv3-badge b-red"><span class="dot dot-r"></span>Behind</span>'
                row_cls = "row-red"
            elif "ahead" in status:
                badge = '<span class="nv3-badge b-green"><span class="dot dot-g"></span>Ahead</span>'
                row_cls = ""
            else:
                badge = '<span class="nv3-badge b-yellow"><span class="dot dot-y"></span>On Schedule</span>'
                row_cls = ""

            try:
                exp_str = f"{float(exp):.0f}%"
            except (ValueError, TypeError):
                exp_str = str(exp)
            try:
                act_str = f"{float(act):.0f}%"
            except (ValueError, TypeError):
                act_str = str(act)

            html.append(f'<tr class="{row_cls}"><td style="font-weight:500;">{name}</td><td>{exp_str}</td><td>{act_str}</td><td class="{var_cls}">{var_str}</td><td>{badge}</td></tr>')
        html.append('</tbody></table></div></div>')

    # ── P5: Stage Mismatch ──────────────────────────────────────────────────────
    mismatch_items = data.get("stage_mismatch", [])
    non_ok = [i for i in mismatch_items if "mismatch" in str(i.get("status", "")).lower()]
    if non_ok:
        html.append(f'''
    <div class="nv3-card" style="border-left:5px solid #8b5cf6;">
        <div class="nv3-card-header" style="border-bottom-color:rgba(139,92,246,0.1);">
            <div class="nv3-icon" style="background:linear-gradient(135deg,#8b5cf6,#7c3aed);box-shadow:0 4px 14px rgba(139,92,246,0.25);">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            </div>
            <div>
                <h2>Stage Mismatch Detection</h2>
                <small>Reported progress does not match expected stage based on elapsed time ({len(non_ok)} mismatches)</small>
            </div>
        </div>
        <div class="nv3-table-wrap">
            <table class="nv3-table">
                <thead><tr><th>Activity</th><th>Actual %</th><th>Expected %</th><th>Difference</th><th>Status</th></tr></thead>
                <tbody>''')
        for item in non_ok:
            name = item.get("activity", "")
            act = item.get("actual_pct", "—")
            exp = item.get("expected_pct", "—")
            diff = item.get("difference_pct", 0)
            status = str(item.get("status", ""))

            try:
                diff_f = float(diff)
                diff_str = f"{diff_f:+.0f}%"
                diff_cls = "var-pos" if diff_f > 0 else "var-neg"
            except (ValueError, TypeError):
                diff_str = str(diff)
                diff_cls = ""

            if "critical" in status.lower():
                badge = '<span class="nv3-badge b-red">Critical Mismatch</span>'
                row_cls = "row-red"
            else:
                badge = '<span class="nv3-badge b-yellow">Mismatch</span>'
                row_cls = "row-amber"

            try:
                act_str = f"{float(act):.0f}%"
            except (ValueError, TypeError):
                act_str = str(act)
            try:
                exp_str = f"{float(exp):.0f}%"
            except (ValueError, TypeError):
                exp_str = str(exp)

            html.append(f'<tr class="{row_cls}"><td style="font-weight:500;">{name}</td><td>{act_str}</td><td>{exp_str}</td><td class="{diff_cls}">{diff_str}</td><td>{badge}</td></tr>')
        html.append('</tbody></table></div></div>')

    # ── P6: Point of No Return ──────────────────────────────────────────────────
    ponr_items = data.get("point_of_no_return", [])
    red_ponr = [i for i in ponr_items if str(i.get("classification", "")).upper() == "RED"]
    yellow_ponr = [i for i in ponr_items if str(i.get("classification", "")).upper() == "YELLOW"]

    if red_ponr or yellow_ponr:
        html.append(f'''
    <div class="nv3-card" style="border-left:5px solid #dc2626;">
        <div class="nv3-card-header" style="border-bottom-color:rgba(220,38,38,0.1);">
            <div class="nv3-icon" style="background:linear-gradient(135deg,#dc2626,#b91c1c);box-shadow:0 4px 14px rgba(220,38,38,0.25);">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            </div>
            <div>
                <h2>Point of No Return</h2>
                <small>Recovery assessment — can these activities still meet their planned finish date?</small>
            </div>
        </div>''')

        for item in red_ponr:
            name = item.get("activity", "")
            act = item.get("actual_pct", "—")
            exp = item.get("expected_pct", "—")
            var = item.get("variance_pct", "—")
            remaining = item.get("remaining_time", "—")
            assessment = item.get("assessment", "POINT OF NO RETURN")
            rec = item.get("recommendation", "")

            try:
                var_str = f"{float(var):+.0f}%"
            except (ValueError, TypeError):
                var_str = str(var)

            rec_html = f'<div class="ponr-rec">{rec}</div>' if rec else ""
            html.append(f'''<div class="ponr-card">
    <div class="ponr-title">{name} <span class="nv3-badge b-red" style="margin-left:8px;">{assessment}</span></div>
    <div class="ponr-grid">
        <div class="ponr-cell"><div class="ponr-cell-lbl">Actual %</div><div class="ponr-cell-val">{act}%</div></div>
        <div class="ponr-cell"><div class="ponr-cell-lbl">Expected %</div><div class="ponr-cell-val">{exp}%</div></div>
        <div class="ponr-cell"><div class="ponr-cell-lbl">Variance</div><div class="ponr-cell-val" style="color:#dc2626;">{var_str}</div></div>
        <div class="ponr-cell"><div class="ponr-cell-lbl">Remaining Time</div><div class="ponr-cell-val">{remaining}</div></div>
    </div>
    {rec_html}
</div>''')

        for item in yellow_ponr:
            name = item.get("activity", "")
            act = item.get("actual_pct", "—")
            exp = item.get("expected_pct", "—")
            var = item.get("variance_pct", "—")
            remaining = item.get("remaining_time", "—")
            assessment = item.get("assessment", "HIGH RISK")
            rec = item.get("recommendation", "")

            try:
                var_str = f"{float(var):+.0f}%"
            except (ValueError, TypeError):
                var_str = str(var)

            rec_html = f'<div class="ponr-rec">{rec}</div>' if rec else ""
            html.append(f'''<div class="ponr-card ponr-card-yellow">
    <div class="ponr-title">{name} <span class="nv3-badge b-yellow" style="margin-left:8px;">{assessment}</span></div>
    <div class="ponr-grid">
        <div class="ponr-cell"><div class="ponr-cell-lbl">Actual %</div><div class="ponr-cell-val">{act}%</div></div>
        <div class="ponr-cell"><div class="ponr-cell-lbl">Expected %</div><div class="ponr-cell-val">{exp}%</div></div>
        <div class="ponr-cell"><div class="ponr-cell-lbl">Variance</div><div class="ponr-cell-val" style="color:#b45309;">{var_str}</div></div>
        <div class="ponr-cell"><div class="ponr-cell-lbl">Remaining Time</div><div class="ponr-cell-val">{remaining}</div></div>
    </div>
    {rec_html}
</div>''')

        html.append('</div>')

    # ── P7: Action Recommendations ──────────────────────────────────────────────
    action_items = data.get("action_recommendations", [])
    if action_items:
        html.append(f'''
    <div class="nv3-card" style="border-left:5px solid #0ea5e9;">
        <div class="nv3-card-header" style="border-bottom-color:rgba(14,165,233,0.1);">
            <div class="nv3-icon" style="background:linear-gradient(135deg,#0ea5e9,#0284c7);box-shadow:0 4px 14px rgba(14,165,233,0.25);">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
            </div>
            <div>
                <h2>Action Recommendations</h2>
                <small>Short, operational actions — one list per critical activity</small>
            </div>
        </div>''')
        for item in action_items:
            name = item.get("activity", "")
            issue = item.get("issue", "")
            actions = item.get("actions", [])
            bullets = "".join(f"<li>{a}</li>" for a in actions)
            html.append(f'''<div class="action-item">
    <div class="action-item-title">{name}</div>
    <div class="action-item-issue">{issue}</div>
    <ul class="action-bullets">{bullets}</ul>
</div>''')
        html.append('</div>')

    html.append('</div>')
    return "\n".join(html)
