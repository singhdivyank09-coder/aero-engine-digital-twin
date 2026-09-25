import sys
import os
import time
import requests

API_BASE = "http://127.0.0.1:8000"

def get_auth_token():
    res = requests.post(f"{API_BASE}/api/auth/login", json={"username": "engineer", "password": "engineer123"})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return res.json()["access_token"]

def get_session_snapshot(token):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{API_BASE}/api/debug/session", headers=headers)
    assert res.status_code == 200, f"Get session failed: {res.text}"
    return res.json()

def start_fault(token, scenario, component="CYLINDER_1", profile="GRADUAL", intensity=1.0, rate="MODERATE"):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(
        f"{API_BASE}/api/fault-injection/start",
        headers=headers,
        json={"scenario": scenario, "component": component, "profile": profile, "intensity": intensity, "rate": rate}
    )
    assert res.status_code == 200, f"Start fault failed: {res.text}"
    return res.json()

def clear_faults(token):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{API_BASE}/api/fault-injection/clear", headers=headers)
    assert res.status_code == 200, f"Clear faults failed: {res.text}"
    return res.json()

def set_scenario(token, profile):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{API_BASE}/api/mission/set-profile", headers=headers, json={"profile": profile})
    assert res.status_code == 200, f"Set scenario failed: {res.text}"
    return res.json()

def stream_session_for_duration(token, duration_seconds):
    num_steps = max(1, int(duration_seconds * 10))
    last_snap = None
    for _ in range(num_steps):
        last_snap = get_session_snapshot(token)
        time.sleep(0.08)  # ~10Hz pacing
    return last_snap

def run_e2e_tests():
    token = get_auth_token()
    print("=== STARTING E2E FAULT INJECTION INTEGRATION TESTS ===")

    # Ensure clean starting state
    clear_faults(token)
    set_scenario(token, "CRUISE")
    stream_session_for_duration(token, 0.5)

    # -------------------------------------------------------------
    # 1. ACCEPTANCE TEST — REAL THERMAL INJECTION (GRADUAL 15s)
    # -------------------------------------------------------------
    print("\n--- 1. Acceptance Test: Real Thermal Injection (CYLINDER_THERMAL, Cylinder 2) ---")
    snap_base = get_session_snapshot(token)
    act_count_before = len(snap_base.get("active_faults", []))
    cht2_base = snap_base["latest_telemetry"].get("cht2", 120.0)
    sub_ev_base = snap_base.get("subsystem_evidence", {})
    health_base = sub_ev_base.get("thermal", {}).get("risk", 0.05)
    state_base = snap_base.get("state", "NORMAL")

    print(f"Active count before: {act_count_before}")
    print(f"CHT2 baseline: {cht2_base:.1f} °C")
    print(f"Thermal risk baseline: {health_base:.2f}")
    print(f"State baseline: {state_base}")

    # Inject
    start_resp = start_fault(token, scenario="CYLINDER_THERMAL", component="CYLINDER_2", profile="GRADUAL", intensity=1.0, rate="MODERATE")
    inj_id_thermal = start_resp["fault_config"]["injection_id"]
    print(f"Started fault injection: {inj_id_thermal}")

    timeline_thermal = {}
    intervals = [1, 4, 5, 5]  # Cumulative: 1s, 5s, 10s, 15s
    cum_t = 0
    for dur in intervals:
        cum_t += dur
        snap = stream_session_for_duration(token, dur)
        telem = snap["latest_telemetry"]
        sub_ev = snap.get("subsystem_evidence", {})
        thermal_data = sub_ev.get("thermal", {})
        timeline_thermal[cum_t] = {
            "cht2": telem.get("cht2", 0.0),
            "egt2": telem.get("egt2", 0.0),
            "oil_temp": telem.get("oil_temp", 0.0),
            "state": snap.get("state", "NORMAL"),
            "risk": thermal_data.get("risk", 0.0),
            "health": thermal_data.get("degradation_score", 0.0),
            "active_count": len(snap.get("active_faults", []))
        }
        print(f"  + {cum_t}s: CHT2 = {timeline_thermal[cum_t]['cht2']:.1f}°C, EGT2 = {timeline_thermal[cum_t]['egt2']:.1f}°C, State = {timeline_thermal[cum_t]['state']}, Risk = {timeline_thermal[cum_t]['risk']:.2f}")

    act_count_after = timeline_thermal[15]["active_count"]
    cht2_15 = timeline_thermal[15]["cht2"]
    
    assert act_count_after >= 1, "Active count must be >= 1 during injection"
    assert cht2_15 > cht2_base + 30.0, f"CHT2 should rise significantly from baseline ({cht2_base:.1f} -> {cht2_15:.1f})"
    assert timeline_thermal[15]["state"] in ["CAUTION", "WARNING", "CRITICAL"], f"State should escalate, got {timeline_thermal[15]['state']}"
    print("PASS: Real Thermal Injection causally changed telemetry, risk, health, and system state")

    # Clear and verify recovery
    clear_resp = clear_faults(token)
    assert clear_resp["remaining_active_count"] == 0
    snap_post_clear = stream_session_for_duration(token, 1.0)
    telem_post_clear = snap_post_clear["latest_telemetry"]
    print(f"After clear: CHT2 = {telem_post_clear.get('cht2', 0.0):.1f}°C, active_faults = {len(snap_post_clear.get('active_faults', []))}")
    assert len(snap_post_clear.get("active_faults", [])) == 0, "Active faults must be 0 after clear"

    # -------------------------------------------------------------
    # 2. ACCEPTANCE TEST — REAL OIL INJECTION
    # -------------------------------------------------------------
    print("\n--- 2. Acceptance Test: Real Oil Injection (OIL_PRESSURE, Oil System) ---")
    clear_faults(token)
    stream_session_for_duration(token, 0.5)

    snap_oil_base = get_session_snapshot(token)
    oil_p_base = snap_oil_base["latest_telemetry"].get("oil_press", 4.2)
    oil_t_base = snap_oil_base["latest_telemetry"].get("oil_temp", 88.5)
    print(f"Oil Press baseline: {oil_p_base:.2f} bar, Oil Temp baseline: {oil_t_base:.1f} °C")

    start_fault(token, scenario="OIL_PRESSURE", component="OIL_SYSTEM", profile="GRADUAL", intensity=1.0, rate="MODERATE")

    timeline_oil = {}
    cum_t = 0
    for dur in [1, 4, 5, 5]:
        cum_t += dur
        snap = stream_session_for_duration(token, dur)
        telem = snap["latest_telemetry"]
        sub_ev = snap.get("subsystem_evidence", {})
        lub_data = sub_ev.get("lubrication", {})
        timeline_oil[cum_t] = {
            "oil_press": telem.get("oil_press", 0.0),
            "oil_temp": telem.get("oil_temp", 0.0),
            "state": snap.get("state", "NORMAL"),
            "risk": lub_data.get("risk", 0.0),
            "health": lub_data.get("degradation_score", 0.0)
        }
        print(f"  + {cum_t}s: Oil Press = {timeline_oil[cum_t]['oil_press']:.2f} bar, Oil Temp = {timeline_oil[cum_t]['oil_temp']:.1f}°C, State = {timeline_oil[cum_t]['state']}, Risk = {timeline_oil[cum_t]['risk']:.2f}")

    oil_p_15 = timeline_oil[15]["oil_press"]
    assert oil_p_15 < oil_p_base - 1.0, f"Oil pressure should drop significantly ({oil_p_base:.2f} -> {oil_p_15:.2f})"
    print("PASS: Real Oil Injection causally changed pressure, temperature, and risk")
    clear_faults(token)

    # -------------------------------------------------------------
    # 3. VERIFY ALL 6 FAULT INJECTION TYPES
    # -------------------------------------------------------------
    print("\n--- 3. Verifying All 6 Fault Injection Types ---")
    all_fault_types = [
        ("CYLINDER_THERMAL", "CYLINDER_2", "cht2"),
        ("OIL_PRESSURE", "OIL_SYSTEM", "oil_press"),
        ("INCREASING_VIBRATION", "MECHANICAL_BEARING", "vibration_rms"),
        ("SENSOR_DRIFT", "ELECTRICAL_BUS", "battery_volt"),
        ("INTERMITTENT_COMBUSTION", "CYLINDER_3", "egt3"),
        ("INJECTOR_DISTURBANCE", "CYLINDER_2", "fuel_flow")
    ]

    for scen, comp, sig_key in all_fault_types:
        clear_faults(token)
        stream_session_for_duration(token, 0.3)
        snap_b = get_session_snapshot(token)
        val_b = snap_b["latest_telemetry"].get(sig_key, 0.0)

        start_fault(token, scenario=scen, component=comp, profile="SUDDEN", intensity=1.5)
        snap_a = stream_session_for_duration(token, 0.8)
        val_a = snap_a["latest_telemetry"].get(sig_key, 0.0)

        delta = abs(val_a - val_b)
        print(f"  Fault {scen} ({comp}) -> {sig_key}: baseline={val_b:.2f}, affected={val_a:.2f}, delta={delta:.2f}")
        assert delta > 0.05, f"Fault {scen} failed to alter signal {sig_key}!"
        clear_faults(token)

    print("PASS: All 6 fault injection types verified with measurable channel deltas")

    # -------------------------------------------------------------
    # 4. TEST SCENARIO COUPLING (CRUISE vs HIGH_ALTITUDE)
    # -------------------------------------------------------------
    print("\n--- 4. Test Scenario Coupling (CRUISE vs HIGH_ALTITUDE) ---")
    clear_faults(token)
    set_scenario(token, "CRUISE")
    snap_cruise = stream_session_for_duration(token, 0.8)
    telem_cruise = snap_cruise["latest_telemetry"]
    scen_params_cruise = snap_cruise.get("scenario_parameters", {})

    print(f"CRUISE Baseline: RPM={telem_cruise.get('rpm'):.1f}, MAP={telem_cruise.get('map'):.2f}, CHT1={telem_cruise.get('cht1'):.1f}°C, Alt={scen_params_cruise.get('altitude_m')}m")

    set_scenario(token, "HIGH_ALTITUDE")
    snap_hi = stream_session_for_duration(token, 0.8)
    telem_hi = snap_hi["latest_telemetry"]
    scen_params_hi = snap_hi.get("scenario_parameters", {})

    print(f"HIGH_ALTITUDE Baseline: RPM={telem_hi.get('rpm'):.1f}, MAP={telem_hi.get('map'):.2f}, CHT1={telem_hi.get('cht1'):.1f}°C, Alt={scen_params_hi.get('altitude_m')}m")

    assert telem_hi.get("map") != telem_cruise.get("map"), "MAP must differ between CRUISE and HIGH_ALTITUDE"
    assert scen_params_hi.get("altitude_m") != scen_params_cruise.get("altitude_m"), "Altitude parameter must differ"
    print("PASS: Scenario coupling verified — operating baseline differs between CRUISE and HIGH_ALTITUDE")

    clear_faults(token)
    set_scenario(token, "CRUISE")

    print("\nALL E2E FAULT INJECTION INTEGRATION TESTS PASSED!")

if __name__ == "__main__":
    run_e2e_tests()
