import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance
from backend.main import compute_canonical_tick

def test_chart_sync_acceptance_all():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    # 1. ACCEPTANCE TEST 1 — NOMINAL CYLINDER 1
    nominal_frame = None
    for _ in range(320): # Warmup for GRU
        nominal_frame = compute_canonical_tick()

    telem = nominal_frame.get("telemetry", {})
    fc = nominal_frame.get("forecast", {})
    
    assert abs(telem.get("cht1", 0) - 120.0) < 5.0, f"Nominal CHT1 expected ~120C, got {telem.get('cht1')}"
    assert fc.get("status") == "READY"
    assert "cht1" in fc.get("forecast_10s", {})
    assert abs(fc["forecast_10s"]["cht1"] - telem["cht1"]) < 10.0

    # 2. ACCEPTANCE TEST 2 & 4 — CYLINDER 3 THERMAL FAULT
    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL",
        component="CYLINDER_3",
        profile="GRADUAL",
        intensity=1.0,
        rate="FAST"
    )

    critical_frame = None
    for _ in range(150):
        f = compute_canonical_tick()
        if f["system_state"] in ["WARNING", "CRITICAL"]:
            critical_frame = f

    assert critical_frame is not None
    crit_telem = critical_frame.get("telemetry", {})
    crit_fc = critical_frame.get("forecast", {})
    ass = critical_frame.get("latest_predictive_assessment") or critical_frame.get("predictive_assessment") or {}

    assert ass.get("affected_component") == "CYLINDER_3" or critical_frame.get("dominant_component") in ["CYLINDER_3", "Cylinder 3"]
    assert crit_telem.get("cht3", 0) > 145.0, f"CHT3 expected > 145C under critical thermal fault, got {crit_telem.get('cht3')}"
    
    # ACCEPTANCE TEST 3 — FORECAST CONSISTENCY
    f10_3 = crit_fc.get("forecast_10s", {}).get("cht3")
    assert f10_3 is not None, "Forecast for CHT3 must exist when status is READY"
    assert abs(f10_3 - crit_telem["cht3"]) < 30.0

    # 3. ACCEPTANCE TEST 5 — CLEAR FAULT RECOVERY & HISTORY PRESERVATION
    simulator_instance.clear_fault_injection()
    
    history_len_before = len(digital_twin_core_instance.history_window_full)
    
    recovery_frame = None
    for _ in range(60):
        recovery_frame = compute_canonical_tick()

    history_len_after = len(digital_twin_core_instance.history_window_full)
    assert history_len_after >= history_len_before, "History must NOT be reset on Clear"
    assert recovery_frame.get("forecast", {}).get("status") == "READY"
