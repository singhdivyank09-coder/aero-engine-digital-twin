import pytest
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

def test_clear_all_faults_lifecycle():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL_DEGRADATION",
        component="CYLINDER_2",
        profile="GRADUAL",
        intensity=1.0,
        rate="FAST"
    )
    simulator_instance.start_fault_injection(
        scenario="OIL_PRESSURE_DEGRADATION",
        component="OIL_SYSTEM",
        profile="GRADUAL",
        intensity=1.0,
        rate="FAST"
    )

    for _ in range(15):
        frame_cont = simulator_instance.get_next_frame()
        snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    assert len(snapshot.get("active_injections", [])) >= 2

    # Perform Clear All
    res = simulator_instance.clear_fault_injection()
    assert res.get("status") == "success" or res.get("active_count") == 0

    frame_cont = simulator_instance.get_next_frame()
    snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    assert len(snapshot.get("active_injections", [])) == 0
