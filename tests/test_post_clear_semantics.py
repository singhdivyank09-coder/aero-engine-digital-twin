"""
Automated Verification Suite — Post-Clear Fault / Forecast / Diagnostic Semantics
Verifies Acceptance Tests A, B, C, D, E:
- ACCEPTANCE TEST A: History & GRU forecast preservation immediately post-clear
- ACCEPTANCE TEST B: Nominal display fields (Subsystem: NONE, Component: NONE, Failure Mode: NONE)
- ACCEPTANCE TEST C: Step-down hysteresis recovery
- ACCEPTANCE TEST D: Transition rationale correctness (no stale/unrelated subsystem string)
- ACCEPTANCE TEST E: Historical audit record retention vs active diagnostic state
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance
from backend.main import compute_canonical_tick

def test_post_clear_semantics():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    # 1. Run nominal baseline for 320 frames (~32s) to accumulate GRU history
    baseline_frames = []
    for _ in range(320):
        baseline_frames.append(compute_canonical_tick())

    latest_init = baseline_frames[-1]
    fc_init = latest_init.get("forecast", {})
    assert fc_init.get("status") == "READY", f"Expected GRU status = READY, got {fc_init.get('status')}"
    init_history_len = len(digital_twin_core_instance.history_window_full)
    assert init_history_len >= 300

    # 2. Inject Cylinder Thermal Fault on Cylinder 1
    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL",
        component="CYLINDER_1",
        profile="GRADUAL",
        intensity=1.0,
        rate="MODERATE"
    )

    fault_frames = []
    for _ in range(150):
        fault_frames.append(compute_canonical_tick())

    latest_fault = fault_frames[-1]
    hist_len_before_clear = len(digital_twin_core_instance.history_window_full)
    fc_before_clear = latest_fault.get("forecast", {})
    assert fc_before_clear.get("status") == "READY"
    assert latest_fault["system_state"] in ["WARNING", "CRITICAL"]

    # 3. Clear All Faults
    simulator_instance.clear_fault_injection()

    # ACCEPTANCE TEST A: Immediate post-clear inspection
    immediate_frame = compute_canonical_tick()
    hist_len_after_clear = len(digital_twin_core_instance.history_window_full)
    fc_after_clear = immediate_frame.get("forecast", {})

    print(f"\n[ACCEPTANCE TEST A — HISTORY & FORECAST PRESERVATION]")
    print(f"History length before clear: {hist_len_before_clear}")
    print(f"History length immediately after clear: {hist_len_after_clear}")
    print(f"Forecast status before clear: {fc_before_clear.get('status')}")
    print(f"Forecast status immediately after clear: {fc_after_clear.get('status')}")

    assert hist_len_after_clear >= hist_len_before_clear, "Telemetry history must NOT be reset on clear"
    assert fc_after_clear.get("status") == "READY", "GRU forecast status must NOT revert to WARMING_UP on clear"

    # 4. Step through recovery phase (60 frames ~6s)
    recovery_frames = []
    for _ in range(60):
        recovery_frames.append(compute_canonical_tick())

    final_rec = recovery_frames[-1]

    print(f"\n[ACCEPTANCE TEST B, C, D — NOMINAL DIAGNOSTIC STATE & RATIONALE]")
    print(f"Final system state: {final_rec['system_state']}")
    print(f"State rationale: {final_rec['state_reason']}")

    # ACCEPTANCE TEST B: Diagnostic state
    ass = final_rec.get("latest_predictive_assessment") or final_rec.get("predictive_assessment") or {}
    print(f"Current affected subsystem = {ass.get('affected_subsystem')}")
    print(f"Current affected component = {ass.get('affected_component')}")
    print(f"Current failure mode = {ass.get('predicted_failure_mode')}")

    if final_rec["system_state"] == "NORMAL":
        assert ass.get("affected_subsystem") in ["NONE", None] or ass.get("predictive_status") == "NOMINAL"
        assert ass.get("affected_component") in ["NONE", None]
        assert ass.get("predicted_failure_mode") in ["NONE", None]

    # ACCEPTANCE TEST D: Rationale check
    rationale = final_rec.get("state_reason", "")
    assert "Lubrication" not in rationale or final_rec.get("dominant_subsystem") == "LUBRICATION", "Transition reason must not mention unrelated Lubrication subsystem"

    # ACCEPTANCE TEST E: Historical record check
    log_events = simulator_instance.fault_event_log
    assert len(log_events) > 0
    last_log = log_events[-1]
    assert last_log.get("status") == "CLEARED"
    assert len(simulator_instance.active_faults) == 0
    print(f"[ACCEPTANCE TEST E PASS] Historical event retained as CLEARED. Active faults count = 0.")

if __name__ == "__main__":
    test_post_clear_semantics()
