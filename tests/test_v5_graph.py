import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.experimental.html_formatter_v5_graph import format_compare_v5_graph_as_html


fixture = {
    "executive_summary": {
        "project_health": "Red",
        "selected_activities": 3,
        "added_activities": 1,
        "behind_schedule_count": 2,
        "ahead_of_schedule_count": 1,
        "critical_count": 2,
        "point_of_no_return_count": 1,
        "critical_path_count": 1,
        "overall_progress_pct": 54.2,
        "recommended_action": "Escalate EL works.",
        "trade_counts": {"EL": 2, "VVS": 1, "VENT": 0, "ARK": 0, "BYGH": 0, "ALL": 3},
    },
    "summary_notes": {
        "overall_progress_old_pct": 49.1,
        "overall_progress_new_pct": 54.2,
        "overall_progress_delta": 5.1,
        "finished_activities": 1,
        "delayed_activities": 2,
        "total_activities": 3,
        "added_count": 1,
        "removed_count": 0,
        "reporting_period_old": "2025-08-15",
        "reporting_period_new": "2025-10-01",
    },
    "filter_options": {
        "areas": ["Building A"],
        "floors": ["Ground Floor", "Basement"],
        "phases": ["Phase 3"],
    },
    "changed_activities": {
        "added": ["EL - New distribution board"],
        "removed": [],
        "changes": [{"activity": "EL - Main board", "change_type": "Finish Date", "old": "01-09-2025", "new": "01-11-2025"}],
    },
    "progress_vs_expected": [
        {
            "activity": "EL - Main board",
            "actual_pct": 22,
            "expected_pct": 100,
            "variance_pct": -78,
            "status": "behind",
            "location": {"area": "Building A", "floor": "Ground Floor", "phase": "Phase 3"},
        },
        {
            "activity": "EL - Cable install",
            "actual_pct": 55,
            "expected_pct": 85,
            "variance_pct": -30,
            "status": "behind",
            "location": {"area": "Building A", "floor": "Ground Floor", "phase": "Phase 3"},
        },
        {
            "activity": "VVS - Basement drain",
            "actual_pct": 92,
            "expected_pct": 80,
            "variance_pct": 12,
            "status": "ahead",
            "location": {"area": "Building A", "floor": "Basement", "phase": "Phase 3"},
        },
    ],
    "not_started_overdue": [],
    "point_of_no_return": [
        {
            "activity": "EL - Main board",
            "actual_pct": 22,
            "expected_pct": 100,
            "variance_pct": -78,
            "remaining_time": "-22 days",
            "classification": "Red",
            "assessment": "POINT OF NO RETURN",
            "recommendation": "Add crew now.",
            "location": {"area": "Building A", "floor": "Ground Floor", "phase": "Phase 3"},
        }
    ],
    "critical_path_activities": [
        {
            "activity": "EL - Main board",
            "start_date": "01-07-2025",
            "finish_date": "01-11-2025",
            "actual_pct": 22,
            "float_days": 0,
            "location": {"area": "Building A", "floor": "Ground Floor", "phase": "Phase 3"},
        }
    ],
    "delay_drivers": [{"driver": "EL labour", "description": "EL crew is short.", "affected_count": 2}],
    "stage_mismatch": [],
    "action_recommendations": [{"activity": "EL - Main board", "issue": "Behind plan.", "actions": ["Add crew", "Notify PM"]}],
}


html = format_compare_v5_graph_as_html(fixture)
agent_source = Path("src/experimental/compare_v5_graph_agent.py").read_text(encoding="utf-8")

assert "class CompareV5GraphAgent" in agent_source
assert "compare_v5_graph_agent = CompareV5GraphAgent()" in agent_source
assert "v5-progress-curve-card" in html
assert "Overall Progress" in html
assert "id=\"v5-progress-chart\"" in html
assert "id=\"v5-chart-actual-path\"" in html
assert "id=\"v5-chart-planned-path\"" in html
assert "function renderProgressCurve" in html
assert "renderProgressCurve(progress, behind.length)" in html
assert "window.__v5Data" in html

output = Path("test_outputs/v5_graph_dashboard_output.html")
output.parent.mkdir(exist_ok=True)
output.write_text(
    f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nova Insight v5 Graph Dashboard Test</title>
<style>body {{ margin: 0; background: #f1f5f9; }}</style>
</head>
<body>
{html}
</body>
</html>""",
    encoding="utf-8",
)

print(f"SUCCESS: generated {output}")
