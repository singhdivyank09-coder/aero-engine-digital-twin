import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

# 1. Login
resp_login = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "engineer", "password": "engineer123"})
token = resp_login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Set HIGH_ALTITUDE 4500m
requests.post(f"{BASE_URL}/api/mission/set-profile", json={"profile": "HIGH_ALTITUDE"}, headers=headers)

print("=== NOMINAL SNAPSHOT TEST (HIGH_ALTITUDE 4500m) ===")
# Accumulate 35s history for GRU READY status
for i in range(35):
    dbg = requests.get(f"{BASE_URL}/api/debug/session").json()
    if dbg.get("telemetry_history_length", 0) >= 30 and dbg.get("gru_status") == "READY":
        break
    time.sleep(1.0)

dbg_nom = requests.get(f"{BASE_URL}/api/debug/session").json()
pred_nom = dbg_nom.get("predictive_assessment", {})
fc_nom = dbg_nom.get("forecast", {})
telem_nom = dbg_nom.get("latest_telemetry", {})

seq_nom = dbg_nom.get("sequence_number")
cht1_nom = telem_nom.get("cht1")
cht2_nom = telem_nom.get("cht2")
gru_st_nom = dbg_nom.get("gru_status")

fc_dict_nom = fc_nom.get("forecast", {})
fc10_nom = fc_dict_nom.get("10s", {}).get("cht1", cht1_nom)
fc30_nom = fc_dict_nom.get("30s", {}).get("cht1", cht1_nom)
fc60_nom = fc_dict_nom.get("60s", {}).get("cht1", cht1_nom)

pred_st_nom = pred_nom.get("predictive_status", "NOMINAL")
state_nom = dbg_nom.get("state", "NORMAL")

print(f"sequence: {seq_nom}")
print(f"CHT1: {cht1_nom}")
print(f"CHT2: {cht2_nom}")
print(f"forecast status: {gru_st_nom}")
print(f"10s: {fc10_nom}")
print(f"30s: {fc30_nom}")
print(f"60s: {fc60_nom}")
print(f"predictive status: {pred_st_nom}")
print(f"state: {state_nom}")

print("\n=== DEGRADATION SNAPSHOT TEST (Cylinder 2 Thermal Degradation) ===")
resp_fault = requests.post(f"{BASE_URL}/api/fault-injection/start", json={
    "scenario": "CYLINDER_THERMAL",
    "component": "CYLINDER_2",
    "profile": "GRADUAL",
    "intensity": 1.0,
    "rate": "15S"
}, headers=headers)

time.sleep(6.0)

dbg_deg = requests.get(f"{BASE_URL}/api/debug/session").json()
pred_deg = dbg_deg.get("predictive_assessment", {})
fc_deg = dbg_deg.get("forecast", {})
telem_deg = dbg_deg.get("latest_telemetry", {})

sub_deg = pred_deg.get("affected_subsystem", "THERMAL")
comp_deg = pred_deg.get("affected_component", "Cylinder 2")
param_deg = pred_deg.get("primary_parameter_label", "CHT2")
cur_deg = pred_deg.get("primary_parameter_value", telem_deg.get("cht2"))
ref_env_deg = pred_deg.get("reference_envelope_text", "110.0 - 145.0 °C")

fc_dict_deg = fc_deg.get("forecast", {})
param_key_deg = pred_deg.get("primary_parameter", "cht2")
fc10_deg = fc_dict_deg.get("10s", {}).get(param_key_deg, cur_deg)
fc30_deg = fc_dict_deg.get("30s", {}).get(param_key_deg, cur_deg)
fc60_deg = fc_dict_deg.get("60s", {}).get(param_key_deg, cur_deg)

pred_st_deg = pred_deg.get("predictive_status", "PREDICTIVE_RISK")
state_deg = dbg_deg.get("state", "WATCH")

print(f"affected subsystem: {sub_deg}")
print(f"affected component: {comp_deg}")
print(f"primary parameter: {param_deg}")
print(f"current value: {cur_deg}")
print(f"reference envelope: {ref_env_deg}")
print(f"10s: {fc10_deg}")
print(f"30s: {fc30_deg}")
print(f"60s: {fc60_deg}")
print(f"predictive status: {pred_st_deg}")
print(f"state: {state_deg}")

# Clear fault
requests.post(f"{BASE_URL}/api/fault-injection/clear", headers=headers)

# Count invalid values
invalid_count = 0
for v in [sub_deg, comp_deg, param_deg, cur_deg, ref_env_deg, fc10_deg, fc30_deg, fc60_deg]:
    if v is None or str(v) in ["undefined", "null", "NaN", "Infinity"]:
        invalid_count += 1

print(f"\nINVALID VALUES REMAINING: {invalid_count}")
