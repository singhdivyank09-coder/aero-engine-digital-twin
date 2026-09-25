"""
Test Suite for Predictive Diagnostics / Active Fault / Maintenance Advisory Module
Verifies:
1. Cylinder Head Overheating: CHT2 elevation -> Thermal subsystem evidence ONLY (no d(Oil)/dt).
2. Oil Pressure Drop: Oil pressure degradation -> Lubrication subsystem evidence ONLY.
3. Vibration Anomaly: High RMS -> Mechanical subsystem evidence ONLY.
4. Sensor Drift: Battery voltage drift -> Electrical subsystem evidence ONLY.
5. Status Differentiation: PREDICTIVE_RISK vs ACTIVE_FAULT.
6. Safe Confidence Handling: Invalid / NaN / None confidence -> None (no NaN%).
"""

import os
import sys
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.digital_twin_core import DigitalTwinCore

def run_diagnostics_tests():
    core = DigitalTwinCore()
    results = {}

    nominal_frame = {
        "timestamp": 100.0,
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

    # Prime core history window with nominal frames
    for i in range(5):
        frame = nominal_frame.copy()
        frame["timestamp"] = float(i + 1)
        core.process_telemetry_frame(frame)

    # TEST 1: Cylinder Head Overheating
    print("\n--- TEST 1: Cylinder Head Overheating ---")
    oh_core = DigitalTwinCore()
    for i in range(3):
        f = nominal_frame.copy()
        f["timestamp"] = float(i + 1)
        oh_core.process_telemetry_frame(f)

    overheat_frame = nominal_frame.copy()
    overheat_frame["timestamp"] = 4.0
    overheat_frame["cht2"] = 148.5 # Crosses fault threshold > 145°C

    snap_oh = oh_core.process_telemetry_frame(overheat_frame)
    diags_oh = snap_oh.get("predictive_diagnostics", [])

    test1_passed = False
    if len(diags_oh) > 0:
        d = diags_oh[0]
        has_correct_type = (d["event_type"] == "CYLINDER_HEAD_OVERHEATING")
        has_correct_sub = (d["affected_subsystem"] == "Thermal")
        has_correct_param = (d["observed_parameter"] == "CHT2")
        has_active_status = (d["status"] == "ACTIVE_FAULT")
        
        # Verify evidence references CHT & cylinder 2 and does NOT mention d(Oil)/dt
        evidence_text = " ".join(d["evidence_sources"])
        no_oil_mention = ("d(Oil)/dt" not in evidence_text) and ("oil_press" not in evidence_text.lower())
        has_cht_mention = ("CHT" in evidence_text) and ("Cylinder 2" in evidence_text or "CHT2" in evidence_text)

        test1_passed = has_correct_type and has_correct_sub and has_correct_param and has_active_status and no_oil_mention and has_cht_mention
        print(f"   Event: {d['event_type']} | Status: {d['status']} | Subsystem: {d['affected_subsystem']} | Param: {d['observed_parameter']}={d['observed_value']}")
        print(f"   Evidence: {d['evidence_sources']}")
        print(f"   Advisory: {d['advisory']}")

    print(f"TEST 1 Passed: {test1_passed}")
    results["TEST_1_OVERHEATING"] = test1_passed

    # TEST 2: Oil Pressure Degradation
    print("\n--- TEST 2: Oil Pressure Degradation ---")
    oil_core = DigitalTwinCore()
    for i in range(3):
        f = nominal_frame.copy()
        f["timestamp"] = float(i + 1)
        oil_core.process_telemetry_frame(f)

    oil_frame = nominal_frame.copy()
    oil_frame["timestamp"] = 4.0
    oil_frame["oil_press"] = 2.20 # Below active fault limit < 2.50 bar

    snap_oil = oil_core.process_telemetry_frame(oil_frame)
    diags_oil = snap_oil.get("predictive_diagnostics", [])

    test2_passed = False
    if len(diags_oil) > 0:
        d = diags_oil[0]
        has_correct_type = (d["event_type"] == "OIL_PRESSURE_DROP")
        has_correct_sub = (d["affected_subsystem"] == "Lubrication")
        has_correct_param = (d["observed_parameter"] == "Oil Pressure")
        has_active_status = (d["status"] == "ACTIVE_FAULT")

        evidence_text = " ".join(d["evidence_sources"])
        has_oil_mention = ("Oil Pressure" in evidence_text or "d(OilPressure)/dt" in evidence_text)

        test2_passed = has_correct_type and has_correct_sub and has_correct_param and has_active_status and has_oil_mention
        print(f"   Event: {d['event_type']} | Status: {d['status']} | Subsystem: {d['affected_subsystem']} | Param: {d['observed_parameter']}={d['observed_value']}")
        print(f"   Evidence: {d['evidence_sources']}")

    print(f"TEST 2 Passed: {test2_passed}")
    results["TEST_2_OIL_DEGRADATION"] = test2_passed

    # TEST 3: Vibration Anomaly
    print("\n--- TEST 3: Mechanical Vibration Anomaly ---")
    vib_core = DigitalTwinCore()
    for i in range(3):
        f = nominal_frame.copy()
        f["timestamp"] = float(i + 1)
        vib_core.process_telemetry_frame(f)

    vib_frame = nominal_frame.copy()
    vib_frame["timestamp"] = 4.0
    vib_frame["vibration_rms"] = 2.85 # Exceeds active fault limit > 2.50 g

    snap_vib = vib_core.process_telemetry_frame(vib_frame)
    diags_vib = snap_vib.get("predictive_diagnostics", [])

    test3_passed = False
    if len(diags_vib) > 0:
        d = diags_vib[0]
        has_correct_type = (d["event_type"] == "VIBRATION_ANOMALY")
        has_correct_sub = (d["affected_subsystem"] == "Mechanical")
        has_correct_param = (d["observed_parameter"] == "Vibration RMS")
        has_active_status = (d["status"] == "ACTIVE_FAULT")

        evidence_text = " ".join(d["evidence_sources"])
        has_vib_mention = ("Vibration RMS" in evidence_text or "d(Vib)/dt" in evidence_text)

        test3_passed = has_correct_type and has_correct_sub and has_correct_param and has_active_status and has_vib_mention
        print(f"   Event: {d['event_type']} | Status: {d['status']} | Subsystem: {d['affected_subsystem']} | Param: {d['observed_parameter']}={d['observed_value']}")
        print(f"   Evidence: {d['evidence_sources']}")

    print(f"TEST 3 Passed: {test3_passed}")
    results["TEST_3_VIBRATION"] = test3_passed

    # TEST 4: Sensor Drift (Battery Voltage)
    print("\n--- TEST 4: Sensor Drift (Electrical Bus Voltage) ---")
    batt_core = DigitalTwinCore()
    for i in range(3):
        f = nominal_frame.copy()
        f["timestamp"] = float(i + 1)
        batt_core.process_telemetry_frame(f)

    batt_frame = nominal_frame.copy()
    batt_frame["timestamp"] = 4.0
    batt_frame["battery_volt"] = 11.20 # Exceeds active fault limit < 11.50 V

    snap_batt = batt_core.process_telemetry_frame(batt_frame)
    diags_batt = snap_batt.get("predictive_diagnostics", [])

    test4_passed = False
    if len(diags_batt) > 0:
        d = diags_batt[0]
        has_correct_type = (d["event_type"] == "SENSOR_DRIFT")
        has_correct_sub = (d["affected_subsystem"] == "Electrical")
        has_correct_param = (d["observed_parameter"] == "Battery Voltage")
        has_active_status = (d["status"] == "ACTIVE_FAULT")

        evidence_text = " ".join(d["evidence_sources"])
        has_batt_mention = ("Battery Voltage" in evidence_text or "Voltage Sensor Drift" in evidence_text)

        test4_passed = has_correct_type and has_correct_sub and has_correct_param and has_active_status and has_batt_mention
        print(f"   Event: {d['event_type']} | Status: {d['status']} | Subsystem: {d['affected_subsystem']} | Param: {d['observed_parameter']}={d['observed_value']}")
        print(f"   Evidence: {d['evidence_sources']}")

    print(f"TEST 4 Passed: {test4_passed}")
    results["TEST_4_SENSOR_DRIFT"] = test4_passed

    # TEST 5: Differentiate Predictive Risk vs Active Fault
    print("\n--- TEST 5: Differentiate Predictive Risk vs Active Fault ---")
    pred_core = DigitalTwinCore()
    for i in range(3):
        f = nominal_frame.copy()
        f["timestamp"] = float(i + 1)
        pred_core.process_telemetry_frame(f)

    # Moderate CHT temperature (138.0 °C) - approaching risk, not crossed fault limit (145.0 °C)
    pred_frame = nominal_frame.copy()
    pred_frame["timestamp"] = 4.0
    pred_frame["cht3"] = 138.0

    snap_pred = pred_core.process_telemetry_frame(pred_frame)
    diags_pred = snap_pred.get("predictive_diagnostics", [])

    test5_passed = False
    if len(diags_pred) > 0:
        d = diags_pred[0]
        is_predictive_risk = (d["status"] == "PREDICTIVE_RISK")
        test5_passed = is_predictive_risk
        print(f"   Moderate Parameter CHT3=138°C -> Status: {d['status']} (Expected: PREDICTIVE_RISK)")

    print(f"TEST 5 Passed: {test5_passed}")
    results["TEST_5_PREDICTIVE_RISK_DIFF"] = test5_passed

    # TEST 6: Safe Confidence Handling (Invalid / NaN confidence -> None)
    print("\n--- TEST 6: Safe Confidence Handling ---")
    nan_conf = float('nan')
    extracted = core._extract_confidence({"confidence": nan_conf})
    test6_passed = (extracted is None)
    print(f"   Confidence NaN input -> Extracted: {extracted} (Expected: None)")
    print(f"TEST 6 Passed: {test6_passed}")
    results["TEST_6_CONFIDENCE_SAFE"] = test6_passed

    # SUMMARY
    print("\n================ DIAGNOSTICS TEST SUMMARY ================")
    all_passed = all(results.values())
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"Overall Diagnostics Test Result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return all_passed

if __name__ == "__main__":
    success = run_diagnostics_tests()
    sys.exit(0 if success else 1)
