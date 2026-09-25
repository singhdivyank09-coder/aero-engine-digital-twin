"""
Test Suite for Physical vs Virtual Model Residuals Module
Verifies:
1. Residual Schema & Exposed Attributes:
   parameter, observed_value, observed_type, predicted_value, residual, reference_band, residual_status, timestamp, unit.
2. 5 Supported PINN Parameters: Power, Avg CHT, Avg EGT, Oil Pressure, Oil Temperature.
3. Power Labeling: "Telemetry-Derived Estimate" (NOT "Actual Power").
4. Residual Math Definition: Residual = Observed - Physics Prediction.
5. Acceptance Test: Gradual CHT thermal deviation causes CHT residual to rise and status to transition NORMAL -> WATCH -> ABNORMAL.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.digital_twin_core import DigitalTwinCore

def run_residuals_tests():
    core = DigitalTwinCore()
    results = {}

    nominal_frame = {
        "timestamp": 10.0,
        "rpm": 5000.0,
        "map": 1.15,
        "cht1": 120.0, "cht2": 121.0, "cht3": 119.5, "cht4": 120.5,
        "egt1": 748.0, "egt2": 750.0, "egt3": 746.0, "egt4": 749.0,
        "oil_press": 4.20,
        "oil_temp": 88.0,
        "fuel_flow": 17.5,
        "vibration_rms": 1.12,
        "battery_volt": 14.10
    }

    snap = core.process_telemetry_frame(nominal_frame)
    res_table = snap.get("residuals_table", {})

    # TEST 1: Schema & Parameter Availability Check
    print("\n--- TEST 1: Residual Table Schema & Supported PINN Parameters ---")
    required_params = ["power_kw", "avg_cht", "avg_egt", "oil_press", "oil_temp"]
    has_all_params = all(p in res_table for p in required_params)

    required_keys = ["parameter", "observed_value", "observed_type", "predicted_value", "residual", "reference_band", "residual_status", "timestamp", "unit"]
    has_all_keys = all(all(k in res_table[p] for k in required_keys) for p in required_params)

    test1_passed = has_all_params and has_all_keys
    print(f"   Has 5 PINN Parameters: {has_all_params} | Has Required Schema Keys: {has_all_keys}")
    print(f"TEST 1 Passed: {test1_passed}")
    results["TEST_1_SCHEMA_CHECK"] = test1_passed

    # TEST 2: Power Labeling Verification
    print("\n--- TEST 2: Power Observed Type Labeling ---")
    power_obs_type = res_table["power_kw"]["observed_type"]
    not_actual_power = "Actual Power" not in power_obs_type
    is_telemetry_derived = power_obs_type == "Telemetry-Derived Estimate"

    test2_passed = not_actual_power and is_telemetry_derived
    print(f"   Observed Type: '{power_obs_type}' | Is 'Telemetry-Derived Estimate': {is_telemetry_derived}")
    print(f"TEST 2 Passed: {test2_passed}")
    results["TEST_2_POWER_LABEL"] = test2_passed

    # TEST 3: Residual Formula Math (Residual = Observed - Predicted)
    print("\n--- TEST 3: Residual Math Definition (Observed - Predicted) ---")
    cht_item = res_table["avg_cht"]
    expected_cht_res = round(cht_item["observed_value"] - cht_item["predicted_value"], 1)
    cht_res_correct = abs(cht_item["residual"] - expected_cht_res) < 1e-3

    oil_item = res_table["oil_press"]
    expected_oil_res = round(oil_item["observed_value"] - oil_item["predicted_value"], 2)
    oil_res_correct = abs(oil_item["residual"] - expected_oil_res) < 1e-3

    test3_passed = cht_res_correct and oil_res_correct
    print(f"   CHT Residual: {cht_item['residual']} °C (Calculated: {expected_cht_res} °C) | Oil Residual: {oil_item['residual']} bar (Calculated: {expected_oil_res} bar)")
    print(f"TEST 3 Passed: {test3_passed}")
    results["TEST_3_RESIDUAL_MATH"] = test3_passed

    # TEST 4: Acceptance Test — Gradual Thermal Deviation
    print("\n--- TEST 4: Acceptance Test (Gradual CHT Thermal Deviation) ---")
    frame = nominal_frame.copy()
    
    # Baseline nominal frame
    snap_nom = core.process_telemetry_frame(frame)
    res_nom = snap_nom["residuals_table"]["avg_cht"]
    
    # Moderate thermal deviation: CHTs rising (avg CHT ~ 133.5°C -> residual ~ +9.0°C -> WATCH)
    frame["timestamp"] = 11.0
    frame["cht1"] = 140.0
    frame["cht2"] = 132.0
    frame["cht3"] = 130.0
    frame["cht4"] = 132.0
    snap_mod = core.process_telemetry_frame(frame)
    res_mod = snap_mod["residuals_table"]["avg_cht"]

    # Severe thermal deviation: CHT thermal runaway (avg CHT ~ 155°C -> residual ~ +30.5°C)
    frame["timestamp"] = 12.0
    frame["cht1"] = 168.0
    frame["cht2"] = 152.0
    frame["cht3"] = 148.0
    frame["cht4"] = 150.0
    snap_sev = core.process_telemetry_frame(frame)
    res_sev = snap_sev["residuals_table"]["avg_cht"]

    print(f"   Nominal (Avg CHT {res_nom['observed_value']}°C): Residual = {res_nom['residual']:+.1f} °C, Status = {res_nom['residual_status']}")
    print(f"   Moderate (Avg CHT {res_mod['observed_value']}°C): Residual = {res_mod['residual']:+.1f} °C, Status = {res_mod['residual_status']}")
    print(f"   Severe (Avg CHT {res_sev['observed_value']}°C): Residual = {res_sev['residual']:+.1f} °C, Status = {res_sev['residual_status']}")

    status_transition_correct = (res_nom["residual_status"] == "NORMAL") and (res_mod["residual_status"] == "WATCH") and (res_sev["residual_status"] == "ABNORMAL")
    residual_trend_rising = res_sev["residual"] > res_mod["residual"] > res_nom["residual"]

    test4_passed = status_transition_correct and residual_trend_rising
    print(f"   Residual Trend Rising: {residual_trend_rising} | Status Transition Verified: {status_transition_correct}")
    print(f"TEST 4 Passed: {test4_passed}")
    results["TEST_4_ACCEPTANCE_THERMAL_DEVIATION"] = test4_passed

    # SUMMARY
    print("\n================ RESIDUALS MODULE TEST SUMMARY ================")
    all_passed = all(results.values())
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"Overall Residuals Module Test Result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return all_passed

if __name__ == "__main__":
    success = run_residuals_tests()
    sys.exit(0 if success else 1)
