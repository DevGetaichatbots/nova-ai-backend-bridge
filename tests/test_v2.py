import time
import uuid
import threading
import requests
import os

# Configuration
BASE_URL = "http://localhost:5000"
SESSION_ID = f"test_v2_session_{uuid.uuid4().hex[:6]}"
OLD_SESSION_ID = f"{SESSION_ID}_old"
NEW_SESSION_ID = f"{SESSION_ID}_new"
ANALYSIS_ID = uuid.uuid4().hex[:12]

def create_mock_schedules():
    """Returns the actual CSV schedules from the sample inputs directory."""
    old_csv = r"c:\work\gac\nova\sample inputs\Katrinetorvet_Arbejdstidsplan_rev_G.csv"
    new_csv = r"c:\work\gac\nova\sample inputs\Katrinetorvet_Arbejdstidsplan_rev_H.csv"
    return old_csv, new_csv

def upload_schedules(old_csv, new_csv):
    print("=" * 50)
    print(" STEP 1: UPLOADING SCHEDULES")
    print("=" * 50)
    
    url = f"{BASE_URL}/upload"
    data = {
        "session_id": SESSION_ID,
        "old_session_id": OLD_SESSION_ID,
        "new_session_id": NEW_SESSION_ID
    }
    files = {
        "old_schedule": open(old_csv, "rb"),
        "new_schedule": open(new_csv, "rb")
    }
    
    response = requests.post(url, data=data, files=files)
    response.raise_for_status()
    res_data = response.json()
    upload_id = res_data["upload_id"]
    
    # Poll Upload Progress
    while True:
        prog_r = requests.get(f"{BASE_URL}/upload/progress/{upload_id}")
        if prog_r.status_code == 200:
            prog = prog_r.json()
            status = prog.get("status")
            old_step = prog.get("old_schedule", {}).get("detail", "")
            new_step = prog.get("new_schedule", {}).get("detail", "")
            print(f"[Upload Progress] Old: {old_step} | New: {new_step}")
            if status == "complete":
                print("Files uploaded and vectorized successfully!")
                break
            elif status == "error":
                print(f"Upload Error: {prog.get('error')}")
                return False
        time.sleep(1)
        
    return True

# REMOVED: /v2/compare endpoint deleted in route cleanup
def run_v2_compare():
    print("SKIPPED: /v2/compare endpoint was removed during route cleanup.")
    return
            
    # Start request in background so we can poll progress
    t = threading.Thread(target=fire_request)
    t.start()
    
    # Give the server a moment to register the analysis_id
    time.sleep(0.5) 
    
    # Poll V2 Compare Progress
    last_msg = ""
    while t.is_alive():
        try:
            r = requests.get(f"{BASE_URL}/predictive/progress/{ANALYSIS_ID}")
            if r.status_code == 200:
                prog = r.json()
                msg = prog.get("message", "")
                if msg and msg != last_msg:
                    print(f"[V2 Agent Status]: {msg}")
                    last_msg = msg
        except Exception:
            pass # Server might slightly lag registering the ID
        time.sleep(1)
        
    t.join()
    
    if "error" in result_container:
        print(f"\nFailed to get comparison: {result_container['error']}")
        return
        
    final_res = result_container["response"]
    if final_res:
        html_out = final_res.get("response", "")
        # Save HTML so user can review the dashboard UI
        out_file = "v2_dashboard_output.html"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html_out)
        
        print("\n" + "=" * 50)
        print(" DONE! V2 DASHBOARD GENERATED")
        print("=" * 50)
        print(f"Context chunks used: {final_res.get('context_chunks')}")
        print(f"\nWe have saved the UI output to: {os.path.abspath(out_file)}")
        print("Please double-click that file in your file explorer to see Emil's layout.")

if __name__ == "__main__":
    print("Starting Setup...")
    old_f, new_f = create_mock_schedules()
    if upload_schedules(old_f, new_f):
        run_v2_compare()
