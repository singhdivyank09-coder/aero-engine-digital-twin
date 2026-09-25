import pytest
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

def test_multifault_preservation_and_dfcs_dominant_advisory():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    # Inject Fault 1: Cylinder Thermal
    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL_DEGRADATION",
        component="CYLINDER_2",
        profile="GRADUAL",
        intensity=1.0,
        rate="FAST"
    )

    for _ in range(10):
        simulator_instance.get_next_frame()

    # Inject Fault 2: Oil Pressure Drop
    simulator_instance.start_fault_injection(
        scenario="OIL_PRESSURE_DEGRADATION",
        component="OIL_SYSTEM",
        profile="GRADUAL",
        intensity=1.2,
        rate="FAST"
    )

    for _ in range(20):
        frame_cont = simulator_instance.get_next_frame()
        snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    active_injections = snapshot.get("active_injections", [])
    assert len(active_injections) >= 2

    dfcs_adv = snapshot.get("gcs_dfcs_advisory", {})
    assert dfcs_adv.get("active_diagnostic_count", 0) >= 1
    assert dfcs_adv.get("dominant_subsystem") in ["THERMAL", "LUBRICATION"]
