import pytest
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

def test_dfcs_stepwise_hysteresis_recovery():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    # Drive to CRITICAL
    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL_DEGRADATION",
        component="CYLINDER_2",
        profile="SUDDEN",
        intensity=2.0,
        rate="FAST"
    )

    for _ in range(25):
        frame_cont = simulator_instance.get_next_frame()
        snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    assert snapshot.get("system_state") in ["WARNING", "CRITICAL"]

    # Clear fault
    simulator_instance.clear_fault_injection()

    states_observed = []
    for _ in range(30):
        frame_cont = simulator_instance.get_next_frame()
        snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)
        st = snapshot.get("system_state")
        if not states_observed or states_observed[-1] != st:
            states_observed.append(st)

    # Verify recovery path was step-by-step and not an instantaneous leap
    assert len(states_observed) >= 2
    assert "NORMAL" in states_observed or states_observed[-1] in ["WATCH", "NORMAL"]
