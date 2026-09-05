import time
import uuid
import threading
import requests
import os

BASE_URL = "http://localhost:5000"
SESSION_ID = f"test_v3_session_{uuid.uuid4().hex[:6]}"
OLD_SESSION_ID = f"{SESSION_ID}_old"
NEW_SESSION_ID = f"{SESSION_ID}_new"
ANALYSIS_ID = uuid.uuid4().hex[:12]

OLD_CSV = r"c:\work\gac\nova\sample inputs\Katrinetorvet_Arbejdstidsplan_rev_G.csv"
NEW_CSV = r"c:\work\gac\nova\sample inputs\Katrinetorvet_Arbejdstidsplan_rev_H.csv"

SCOPE_FILTER = "Electrical"
REFERENCE_DATE = "12-03-2026"
OUTPUT_FILE = "v3_dashboard_output.html"


def upload_schedules():
    print("=" * 60)
    print(" STEP 1: UPLOADING SCHEDULES")
    print("=" * 60)

    url = f"{BASE_URL}/upload"
    data = {
        "session_id": SESSION_ID,
        "old_session_id": OLD_SESSION_ID,
        "new_session_id": NEW_SESSION_ID,
    }
    files = {
        "old_schedule": open(OLD_CSV, "rb"),
        "new_schedule": open(NEW_CSV, "rb"),
    }

    response = requests.post(url, data=data, files=files)
    response.raise_for_status()
    upload_id = response.json()["upload_id"]
    print(f"Upload started — ID: {upload_id}")

    while True:
        prog = requests.get(f"{BASE_URL}/upload/progress/{upload_id}").json()
        status = prog.get("status")
        old_detail = prog.get("old_schedule", {}).get("detail", "")
        new_detail = prog.get("new_schedule", {}).get("detail", "")
        print(f"  [Upload] old={old_detail} | new={new_detail}")
        if status == "complete":
            print("Upload complete.\n")
            return True
        if status == "error":
            print(f"Upload error: {prog.get('error')}")
            return False
        time.sleep(1)


# REMOVED: /v3/compare endpoint deleted in route cleanup
def run_v3_compare():
    print("SKIPPED: /v3/compare endpoint was removed during route cleanup.")
    return

    t = threading.Thread(target=fire_request)
    t.start()
    time.sleep(0.5)

    last_msg = ""
    while t.is_alive():
        try:
            r = requests.get(f"{BASE_URL}/predictive/progress/{ANALYSIS_ID}")
            if r.status_code == 200:
                prog = r.json()
                msg = prog.get("message", "")
                step = prog.get("step", "")
                total = prog.get("total_steps", "")
                if msg and msg != last_msg:
                    print(f"  [{step}/{total}] {msg}")
                    last_msg = msg
        except Exception:
            pass
        time.sleep(1)

    t.join()

    if "error" in result_container:
        print(f"\nRequest failed: {result_container['error']}")
        return

    final = result_container.get("response", {})
    if not final:
        print("Empty response.")
        return

    html_out = final.get("response", "")
    json_data = final.get("json_data", {})

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nova Insight v3 — Test Output</title>
<style>body {{ margin: 0; background: #f1f5f9; padding: 24px; }}</style>
</head>
<body>
{html_out}
</body>
</html>""")

    print("\n" + "=" * 60)
    print(" DONE — V3 DASHBOARD GENERATED")
    print("=" * 60)
    print(f"  Context chunks : {final.get('context_chunks')}")
    print(f"  Analysis ID    : {final.get('analysis_id')}")

    es = json_data.get("executive_summary", {})
    print(f"\n  Project Health : {es.get('project_health')}")
    print(f"  Activities     : {es.get('selected_activities')}")
    print(f"  Behind Schedule: {es.get('behind_schedule_count')}")
    print(f"  Ahead Schedule : {es.get('ahead_of_schedule_count')}")
    print(f"  Critical       : {es.get('critical_count')}")
    print(f"  PONR           : {es.get('point_of_no_return_count')}")
    print(f"  Recommended    : {es.get('recommended_action')}")

    changes = json_data.get("changed_activities", {})
    print(f"\n  Added          : {len(changes.get('added', []))}")
    print(f"  Removed        : {len(changes.get('removed', []))}")
    print(f"  Changes        : {len(changes.get('changes', []))}")
    print(f"  Not Started    : {len(json_data.get('not_started_overdue', []))}")
    print(f"  Stage Mismatch : {len(json_data.get('stage_mismatch', []))}")
    print(f"  PONR items     : {len(json_data.get('point_of_no_return', []))}")
    print(f"  Actions        : {len(json_data.get('action_recommendations', []))}")

    print(f"\n  HTML saved to  : {os.path.abspath(OUTPUT_FILE)}")
    print("  Open that file in a browser to review the dashboard.\n")


if __name__ == "__main__":
    if upload_schedules():
        run_v3_compare()
