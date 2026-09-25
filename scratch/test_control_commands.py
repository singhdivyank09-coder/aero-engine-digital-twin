import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

# 1. Login
resp_login = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "engineer", "password": "engineer123"})
print(f"Login Status: {resp_login.status_code}")
token = resp_login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Security Audit Endpoint test
resp_audit = requests.get(f"{BASE_URL}/api/audit-logs", headers=headers)
print(f"Security Audit Status: {resp_audit.status_code} (Expected: 200)")

# 3. Session Before Scenario Change
resp_sess_before = requests.get(f"{BASE_URL}/api/debug/session")
sess_before = resp_sess_before.json()
print("SESSION BEFORE SCENARIO CHANGE:", json.dumps(sess_before["scenario_parameters"]))

# 4. Change Scenario to HIGH_ALTITUDE
resp_scen = requests.post(f"{BASE_URL}/api/mission/set-profile", json={"profile": "HIGH_ALTITUDE"}, headers=headers)
print(f"Scenario API Status: {resp_scen.status_code}")

time.sleep(0.5)

# 5. Session After Scenario Change
resp_sess_after = requests.get(f"{BASE_URL}/api/debug/session")
sess_after = resp_sess_after.json()
print("SESSION AFTER HIGH_ALTITUDE:", json.dumps(sess_after["scenario_parameters"]))

# 6. Start Cylinder 2 Thermal Degradation Fault
resp_fault = requests.post(f"{BASE_URL}/api/fault-injection/start", json={
    "scenario": "CYLINDER_THERMAL",
    "component": "CYLINDER_2",
    "profile": "GRADUAL",
    "intensity": 1.0,
    "rate": "15S"
}, headers=headers)

fault_res = resp_fault.json()
print(f"FAULT API STATUS: {resp_fault.status_code}")
print(f"FAULT ID: {fault_res.get('fault_id')}")

# Record CHT2 time series over 10 seconds
cht2_series = []
for i in range(5):
    time.sleep(2.0)
    dbg = requests.get(f"{BASE_URL}/api/debug/session").json()
    cht2 = dbg["latest_telemetry"].get("cht2")
    cht1 = dbg["latest_telemetry"].get("cht1")
    act_faults = len(dbg.get("active_faults", []))
    cht2_series.append((round(i*2.0, 1), cht2, cht1, act_faults))
    print(f"t={i*2}s | CHT2={cht2}°C | CHT1={cht1}°C | Active Faults={act_faults} | GRU History Len={dbg.get('telemetry_history_length')}")

# Clear Fault
resp_clear = requests.post(f"{BASE_URL}/api/fault-injection/clear", headers=headers)
print(f"Clear Fault API Status: {resp_clear.status_code}")

# Return scenario to CRUISE
requests.post(f"{BASE_URL}/api/mission/set-profile", json={"profile": "CRUISE"}, headers=headers)
