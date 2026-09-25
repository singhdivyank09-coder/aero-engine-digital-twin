import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

# 1. Login
resp_login = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "engineer", "password": "engineer123"})
token = resp_login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Clear any previous faults
requests.post(f"{BASE_URL}/api/fault-injection/clear", headers=headers)
requests.post(f"{BASE_URL}/api/mission/set-profile", json={"profile": "CRUISE"}, headers=headers)
time.sleep(1.0)

print("=== STARTING COMPOUND-FAULT VERIFICATION TEST ===")

# 2. Inject Fault A: Oil Pressure Degradation
print("\n--- INJECTING FAULT A: Oil Pressure Degradation ---")
res_a = requests.post(f"{BASE_URL}/api/fault-injection/start", json={
    "scenario": "OIL_PRESSURE",
    "component": "OIL_SYSTEM",
    "profile": "GRADUAL",
    "intensity": 1.0,
    "rate": "15S"
}, headers=headers).json()

print(f"Fault A HTTP Status: 200 | Fault ID: {res_a.get('fault_id')} | Active Count: {res_a.get('active_faults_count')}")

time.sleep(3.0)
dbg_a = requests.get(f"{BASE_URL}/api/debug/session").json()
telem_a = dbg_a.get("latest_telemetry", {})
print(f"t=3s after Fault A | Oil Press={telem_a.get('oil_press')} bar | Vib RMS={telem_a.get('vibration_rms')} g")

# 3. Inject Fault B: Increasing Mechanical Vibration (while Fault A is active)
print("\n--- INJECTING FAULT B: Increasing Mechanical Vibration (COMPOUND) ---")
res_b = requests.post(f"{BASE_URL}/api/fault-injection/start", json={
    "scenario": "INCREASING_VIBRATION",
    "component": "MECHANICAL_BEARING",
    "profile": "GRADUAL",
    "intensity": 1.0,
    "rate": "15S"
}, headers=headers).json()

print(f"Fault B HTTP Status: 200 | Fault ID: {res_b.get('fault_id')} | Active Count: {res_b.get('active_faults_count')}")

time.sleep(4.0)

# 4. Verify Compound Telemetry & Evidence Fusion
dbg_c = requests.get(f"{BASE_URL}/api/debug/session").json()
telem_c = dbg_c.get("latest_telemetry", {})
sub_ev = dbg_c.get("subsystem_evidence", {})
dom_sub = dbg_c.get("dominant_subsystem")
dom_comp = dbg_c.get("dominant_component")
sec_deg = dbg_c.get("secondary_degradations", [])
inj_faults = dbg_c.get("injected_faults", [])
det_cond = dbg_c.get("detected_conditions", [])
global_st = dbg_c.get("state")

print("\n=== COMPOUND FAULT RUNTIME EVIDENCE RESULTS ===")
print(f"Active Faults Count: {len(inj_faults)}")
print(f"Injected Fault Scenarios: {[f.get('scenario') for f in inj_faults]}")
print(f"Telemetry Readouts: Oil Press = {telem_c.get('oil_press')} bar | Vib RMS = {telem_c.get('vibration_rms')} g | CHT1 = {telem_c.get('cht1')} °C")
print(f"Lubrication Subsystem State: {sub_ev.get('lubrication', {}).get('state')} (Risk Score: {sub_ev.get('lubrication', {}).get('risk')})")
print(f"Mechanical Subsystem State: {sub_ev.get('mechanical', {}).get('state')} (Risk Score: {sub_ev.get('mechanical', {}).get('risk')})")
print(f"Global Engine State: {global_st}")
print(f"Dominant Subsystem: {dom_sub}")
print(f"Dominant Component: {dom_comp}")
print(f"Secondary Degradations: {sec_deg}")
print(f"Detected AI Conditions: {json.dumps(det_cond)}")

# Cleanup
requests.post(f"{BASE_URL}/api/fault-injection/clear", headers=headers)
print("\nTest completed & faults cleared.")
