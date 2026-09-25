import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

# 1. Login
resp_login = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "engineer", "password": "engineer123"})
token = resp_login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Clear any previous faults & set baseline
requests.post(f"{BASE_URL}/api/fault-injection/clear", headers=headers)
requests.post(f"{BASE_URL}/api/mission/set-profile", json={"profile": "CRUISE"}, headers=headers)
time.sleep(1.0)

# Capture BEFORE baseline
dbg_before = requests.get(f"{BASE_URL}/api/debug/session").json()
telem_b = dbg_before.get("latest_telemetry", {})

print("=== BEFORE FAULT INJECTION (BASELINE) ===")
print(f"CHT1: {telem_b.get('cht1')} °C")
print(f"CHT2: {telem_b.get('cht2')} °C")
print(f"CHT3: {telem_b.get('cht3')} °C")
print(f"CHT4: {telem_b.get('cht4')} °C")
print(f"EGT1: {telem_b.get('egt1')} °C")
print(f"EGT2: {telem_b.get('egt2')} °C")
print(f"EGT3: {telem_b.get('egt3')} °C")
print(f"EGT4: {telem_b.get('egt4')} °C")

# Inject Cylinder 2 Thermal Degradation (SUDDEN profile)
print("\n--- INJECTING FAULT: CYLINDER_THERMAL on CYLINDER_2 (SUDDEN) ---")
res_inj = requests.post(f"{BASE_URL}/api/fault-injection/start", json={
    "scenario": "CYLINDER_THERMAL",
    "component": "CYLINDER_2",
    "profile": "SUDDEN",
    "intensity": 1.0,
    "rate": "5S"
}, headers=headers).json()

cfg = res_inj.get("fault_config", {})
print(f"requested component: {cfg.get('requested_component')}")
print(f"resolved index: {cfg.get('resolved_index')}")
print(f"mutated signals: {cfg.get('mutated_signal_names')}")

# Allow simulation to step
time.sleep(3.0)

# Capture AFTER snapshot
dbg_after = requests.get(f"{BASE_URL}/api/debug/session").json()
telem_a = dbg_after.get("latest_telemetry", {})
sub_ev = dbg_after.get("subsystem_evidence", {})
dom_sub = dbg_after.get("dominant_subsystem")
dom_comp = dbg_after.get("dominant_component")
sec_deg = dbg_after.get("secondary_degradations", [])
det_cond = dbg_after.get("detected_conditions", [])
global_st = dbg_after.get("state")
p_stats = dbg_after.get("parameter_statuses", {})
oil_t_st = p_stats.get("oil_temp", {}).get("status", "NORMAL")

print("\n=== AFTER FAULT INJECTION (SUDDEN) ===")
print(f"CHT1: {telem_a.get('cht1')} °C")
print(f"CHT2: {telem_a.get('cht2')} °C")
print(f"CHT3: {telem_a.get('cht3')} °C")
print(f"CHT4: {telem_a.get('cht4')} °C")
print(f"EGT1: {telem_a.get('egt1')} °C")
print(f"EGT2: {telem_a.get('egt2')} °C")
print(f"EGT3: {telem_a.get('egt3')} °C")
print(f"EGT4: {telem_a.get('egt4')} °C")

print(f"\nPRIMARY DETECTED CONDITION: Thermal degradation — {dom_comp}")
print(f"SECONDARY CONDITIONS: {sec_deg}")

# EGT Spread Breakdown
egt_vals = [float(telem_a.get('egt1')), float(telem_a.get('egt2')), float(telem_a.get('egt3')), float(telem_a.get('egt4'))]
max_egt = max(egt_vals)
min_egt = min(egt_vals)
max_c = egt_vals.index(max_egt) + 1
min_c = egt_vals.index(min_egt) + 1
spread = round(max_egt - min_egt, 1)

print("\n=== EGT SPREAD BREAKDOWN ===")
print(f"high cylinder: Cylinder {max_c}")
print(f"low cylinder: Cylinder {min_c}")
print(f"spread: {spread} °C")
print(f"limit: 90.0 °C")

print(f"\nGLOBAL STATE: {global_st}")
print(f"DIAGNOSTICS CONSOLE STATE: {global_st} (Dominant: {dom_sub} / {dom_comp})")
print(f"OIL TEMP STATUS TEST: Oil Temp = {telem_a.get('oil_temp')} °C | Status = {oil_t_st}")

# Cleanup
requests.post(f"{BASE_URL}/api/fault-injection/clear", headers=headers)
print("\nTest completed & cleared.")
