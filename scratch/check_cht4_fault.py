import requests
import time

API_BASE = "http://127.0.0.1:8000"

login_res = requests.post(f"{API_BASE}/api/auth/login", json={"username": "engineer", "password": "engineer123"})
token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

requests.post(f"{API_BASE}/api/fault-injection/clear", headers=headers)
time.sleep(1)

print("Injecting CYLINDER_HEAD_OVERHEATING on CYLINDER_4 via /api/fault-injection/start...")
res = requests.post(f"{API_BASE}/api/fault-injection/start", headers=headers, json={
    "scenario": "CYLINDER_HEAD_OVERHEATING",
    "component": "CYLINDER_4",
    "profile": "SUDDEN",
    "intensity": 1.0,
    "rate": "FAST"
})
print("Start response:", res.json())

for i in range(15):
    time.sleep(1)
    snap = requests.get(f"{API_BASE}/api/telemetry/latest").json()
    t = snap.get("telemetry") or {}
    state = snap.get("system_state", "N/A")
    sub_health = snap.get("subsystem_health") or {}
    cht4 = t.get('cht4') if t.get('cht4') is not None else 0.0
    cht1 = t.get('cht1') if t.get('cht1') is not None else 0.0
    th = sub_health.get('thermal') if sub_health.get('thermal') is not None else 0.0
    print(f"t={i+1}s | state={state} | CHT4={cht4:.1f} | CHT1={cht1:.1f} | Thermal Health={th:.1f}%")

