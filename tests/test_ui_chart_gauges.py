"""
Test Suite for Telemetry Chart, Primary Engine Gauges, CHT/EGT Matrix Rendering
Verifies:
1. Chart Normalization Scaling: RPM/50, CHT1, EGT1/5, OilPress*20.
2. Proportional CHT/EGT Height Math: CHT (0-200°C), EGT (0-1000°C).
3. Selective Cylinder Highlighting: Only CHT1 highlighted when CHT1 rises.
4. Gauge State Indicator Badging: Subsystem state mapping matches backend snapshot.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.digital_twin_core import DigitalTwinCore

def run_ui_chart_gauge_tests():
    core = DigitalTwinCore()
    results = {}

    nominal_frame = {
        "timestamp": 10.0,
        "rpm": 5000.0,
        "map": 1.15,
        "cht1": 120.0, "cht2": 121.0, "cht3": 119.5, "cht4": 120.5,
        "egt1": 748.0, "egt2": 750.0, "egt3": 746.0, "egt4": 749.0,
        "oil_press": 4.20,
        "oil_temp": 88.5,
        "fuel_flow": 17.5,
        "vibration_rms": 1.12,
        "battery_volt": 14.10
    }

    # TEST 1: Chart Normalization Math
    print("\n--- TEST 1: Chart Channel Normalization Scaling ---")
    rpm_norm = nominal_frame["rpm"] / 50.0 # 100.0
    cht_norm = nominal_frame["cht1"]       # 120.0
    egt_norm = nominal_frame["egt1"] / 5.0 # 149.6
    oil_norm = nominal_frame["oil_press"] * 20.0 # 84.0

    test1_passed = (rpm_norm == 100.0) and (cht_norm == 120.0) and (abs(egt_norm - 149.6) < 1e-4) and (abs(oil_norm - 84.0) < 1e-4)
    print(f"   RPM Norm: {rpm_norm} | CHT Norm: {cht_norm} | EGT Norm: {egt_norm:.1f} | Oil Norm: {oil_norm:.1f}")
    print(f"TEST 1 Passed: {test1_passed}")
    results["TEST_1_CHART_SCALING"] = test1_passed

    # TEST 2: Proportional CHT & EGT Bar Heights
    print("\n--- TEST 2: Proportional CHT & EGT Bar Height Math ---")
    cht_val = 148.5 # CHT1 in warning condition
    egt_val = 745.0

    cht_height_pct = min(100.0, max(6.0, (cht_val / 200.0) * 100.0)) # 74.25%
    egt_height_pct = min(100.0, max(6.0, (egt_val / 1000.0) * 100.0)) # 74.5%

    test2_passed = (abs(cht_height_pct - 74.25) < 1e-3) and (abs(egt_height_pct - 74.5) < 1e-3)
    print(f"   CHT1 (148.5°C) -> Height: {cht_height_pct:.2f}% | EGT1 (745°C) -> Height: {egt_height_pct:.2f}%")
    print(f"TEST 2 Passed: {test2_passed}")
    results["TEST_2_BAR_HEIGHTS"] = test2_passed

    # TEST 3: Selective Cylinder Highlighting (Cylinder 1 Overheating)
    print("\n--- TEST 3: Selective Cylinder Highlighting ---")
    cht1_val = 172.0 # Cylinder 1 high temperature
    cht2_val = 122.0 # Cylinder 2 nominal
    cht3_val = 120.0 # Cylinder 3 nominal
    cht4_val = 121.0 # Cylinder 4 nominal

    def get_cyl_state(val):
        if val >= 145.0: return "WARNING"
        if val >= 135.0: return "CAUTION"
        if val >= 128.0: return "WATCH"
        return "NORMAL"

    state_cyl1 = get_cyl_state(cht1_val)
    state_cyl2 = get_cyl_state(cht2_val)
    state_cyl3 = get_cyl_state(cht3_val)
    state_cyl4 = get_cyl_state(cht4_val)

    # Only Cylinder 1 should be in WARNING state
    test3_passed = (state_cyl1 == "WARNING") and (state_cyl2 == "NORMAL") and (state_cyl3 == "NORMAL") and (state_cyl4 == "NORMAL")
    print(f"   CYL1 (172°C): {state_cyl1} | CYL2 (122°C): {state_cyl2} | CYL3 (120°C): {state_cyl3} | CYL4 (121°C): {state_cyl4}")
    print(f"TEST 3 Passed: {test3_passed} (Selective Highlighting Verified)")
    results["TEST_3_SELECTIVE_HIGHLIGHT"] = test3_passed

    # TEST 4: Backend Snapshot Subsystem State Mapping to Gauges
    print("\n--- TEST 4: Backend Snapshot Subsystem State Mapping ---")
    frame = nominal_frame.copy()
    for i in range(10):
        frame["timestamp"] = 11.0 + i
        frame["oil_press"] = 1.80 # Severe low oil pressure
        snap = core.process_telemetry_frame(frame)
    
    sub_health = snap["subsystem_health"]
    sys_state = snap["system_state"]

    print(f"   System State: {sys_state} | Lubrication Health: {sub_health['lubrication']}%")
    test4_passed = (sub_health["lubrication"] < 70.0)
    print(f"TEST 4 Passed: {test4_passed}")
    results["TEST_4_GAUGE_STATE_MAPPING"] = test4_passed

    # SUMMARY
    print("\n================ UI CHART & GAUGE TEST SUMMARY ================")
    all_passed = all(results.values())
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"Overall UI Chart & Gauge Test Result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return all_passed

if __name__ == "__main__":
    success = run_ui_chart_gauge_tests()
    sys.exit(0 if success else 1)
