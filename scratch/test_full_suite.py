import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

resp_login = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "engineer", "password": "engineer123"})
token = resp_login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 1. Test GRU warmup progression
print("--- GRU WARMUP TEST ---")
gru_status = "WARMING_UP"
hist_len = 0
for i in range(40):
    dbg = requests.get(f"{BASE_URL}/api/debug/session").json()
    hist_len = dbg.get("telemetry_history_length", 0)
    gru_status = dbg.get("gru_status", "WARMING_UP")
    if hist_len >= 30 and gru_status == "READY":
        break
    time.sleep(1.0)
print(f"Final History Length: {hist_len}, GRU Status: {gru_status}")

# 2. Test State Flicker during Nominal Operation (60 seconds)
print("--- STATE FLICKER TEST (20s check) ---")
state_history = []
transitions = 0
prev_state = None
for i in range(20):
    dbg = requests.get(f"{BASE_URL}/api/debug/session").json()
    st = dbg.get("state", "NORMAL")
    if prev_state is not None and st != prev_state:
        transitions += 1
    prev_state = st
    state_history.append(st)
    time.sleep(0.5)
print(f"State Transitions in 10s: {transitions}, States seen: {set(state_history)}")

# 3. Test Predictive Exceedance logic
print("--- PREDICTIVE EXCEEDANCE LOGIC TEST ---")
dbg = requests.get(f"{BASE_URL}/api/debug/session").json()
pred = dbg.get("predictive_assessment", {})
print("Predictive Assessment Keys & Values:", json.dumps(pred, indent=2))
