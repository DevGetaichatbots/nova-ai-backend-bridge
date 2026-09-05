import requests
import sys

BASE_URL = "http://localhost:5000"

# Use the session ID from the last upload in the logs: test_v2_session_a2a7b1
SESSION_ID = "test_v2_session_a2a7b1"
OLD_SESSION_ID = f"{SESSION_ID}_old"
NEW_SESSION_ID = f"{SESSION_ID}_new"

def test_query():
    print(f"Testing /query endpoint with session {SESSION_ID}...")
    url = f"{BASE_URL}/query"
    data = {
        "query": "Compare the electrical tasks between the two schedules and list the delayed ones.",
        "vs_table": SESSION_ID,
        "old_session_id": OLD_SESSION_ID,
        "new_session_id": NEW_SESSION_ID,
        "language": "en",
        "format": "html"
    }
    
    try:
        response = requests.post(url, data=data)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("Success!")
            print(f"Response length: {len(response.json().get('response', ''))}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    test_query()
