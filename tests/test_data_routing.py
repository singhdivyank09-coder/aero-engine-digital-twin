"""
Test Suite for Data-Source Routing & Signal Provenance Metadata
Verifies:
1. Separation of Twin Telemetry Source (SIMULATOR / REPLAY) from Analytics Dataset (CMAPSS / ALFA / RFLYMAD / UAVFD).
2. Primary telemetry signals (CHT, EGT, Oil Press, Vibration) remain driven by the primary telemetry source.
3. Signal Provenance metadata structure (source_type, source_dataset, source_feature, transformation, timestamp).
4. Acceptance test: Selecting NASA C-MAPSS leaves primary telemetry as SIMULATED aero-piston data.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.telemetry_simulator import TelemetrySimulator
from backend.digital_twin_core import DigitalTwinCore

def run_data_routing_tests():
    sim = TelemetrySimulator()
    core = DigitalTwinCore()
    results = {}

    # TEST 1: Default Data Sources
    print("\n--- TEST 1: Default Data Sources Initial State ---")
    frame1 = sim.get_next_frame()
    snap1 = core.process_telemetry_frame(frame1)

    t_src1 = snap1.get("telemetry_source")
    a_ds1 = snap1.get("analytics_dataset")

    test1_passed = (t_src1 == "SIMULATOR") and (a_ds1 == "CMAPSS") and ("signal_provenance" in snap1)
    print(f"   Telemetry Source: {t_src1} | Analytics Dataset: {a_ds1} | Has Signal Provenance: {'signal_provenance' in snap1}")
    print(f"TEST 1 Passed: {test1_passed}")
    results["TEST_1_DEFAULT_SOURCES"] = test1_passed

    # TEST 2: Select NASA C-MAPSS as Analytics Dataset
    print("\n--- TEST 2: Select NASA C-MAPSS as Analytics Dataset ---")
    sim.set_telemetry_source("SIMULATOR")
    sim.set_analytics_dataset("CMAPSS")

    frame2 = sim.get_next_frame()
    snap2 = core.process_telemetry_frame(frame2)

    prov2 = snap2.get("signal_provenance", {})
    cht_prov = prov2.get("cht1", {})
    oil_prov = prov2.get("oil_press", {})
    rul_prov = prov2.get("rul", {})

    cht_is_simulated = (cht_prov.get("source_type") == "SIMULATED") and ("Reference Aero-Piston" in cht_prov.get("source_dataset", ""))
    oil_is_simulated = (oil_prov.get("source_type") == "SIMULATED") and ("Reference Aero-Piston" in oil_prov.get("source_dataset", ""))
    rul_is_analogue = (rul_prov.get("source_type") == "ANALOGUE") and ("C-MAPSS" in rul_prov.get("source_dataset", ""))

    test2_passed = cht_is_simulated and oil_is_simulated and rul_is_analogue
    print(f"   CHT1 Source: {cht_prov.get('source_dataset')} ({cht_prov.get('source_type')})")
    print(f"   OilPress Source: {oil_prov.get('source_dataset')} ({oil_prov.get('source_type')})")
    print(f"   RUL Source: {rul_prov.get('source_dataset')} ({rul_prov.get('source_type')})")
    print(f"TEST 2 Passed: {test2_passed}")
    results["TEST_2_CMAPSS_SEPARATION"] = test2_passed

    # TEST 3: Switch Analytics Dataset to ALFA UAV Dataset
    print("\n--- TEST 3: Switch Analytics Dataset to ALFA ---")
    sim.set_analytics_dataset("ALFA")
    frame3 = sim.get_next_frame()
    snap3 = core.process_telemetry_frame(frame3)

    prov3 = snap3.get("signal_provenance", {})
    rul_prov3 = prov3.get("rul", {})

    test3_passed = (snap3.get("analytics_dataset") == "ALFA") and ("ALFA" in rul_prov3.get("source_dataset", ""))
    print(f"   Analytics Dataset Label: {snap3.get('analytics_dataset_label')}")
    print(f"TEST 3 Passed: {test3_passed}")
    results["TEST_3_ALFA_SWITCH"] = test3_passed

    # TEST 4: Complete Signal Provenance Key Verification
    print("\n--- TEST 4: Complete Signal Provenance Structure Verification ---")
    required_keys = ["primary_telemetry", "analytics_dataset", "cht1", "oil_press", "vibration_rms", "rul"]
    has_all_keys = all(k in prov2 for k in required_keys)
    
    sample_entry = prov2.get("cht1", {})
    required_meta_fields = ["source_type", "source_dataset", "source_feature", "transformation", "timestamp"]
    has_all_fields = all(f in sample_entry for f in required_meta_fields)

    test4_passed = has_all_keys and has_all_fields
    print(f"   Has All Required Provenance Signals: {has_all_keys} | Has All Metadata Fields: {has_all_fields}")
    print(f"TEST 4 Passed: {test4_passed}")
    results["TEST_4_PROVENANCE_SCHEMA"] = test4_passed

    # SUMMARY
    print("\n================ DATA ROUTING TEST SUMMARY ================")
    all_passed = all(results.values())
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"Overall Data Routing Test Result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    return all_passed

if __name__ == "__main__":
    success = run_data_routing_tests()
    sys.exit(0 if success else 1)
