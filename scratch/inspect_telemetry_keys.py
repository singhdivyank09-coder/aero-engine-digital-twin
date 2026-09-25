import requests
import json

API_BASE = "http://127.0.0.1:8000"
snap = requests.get(f"{API_BASE}/api/telemetry/latest").json()
print("KEYS:", snap.keys())
print("SAMPLE SNAPSHOT:")
print(json.dumps(snap, indent=2)[:500])
