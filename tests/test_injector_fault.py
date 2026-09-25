import pytest
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

def test_fuel_injector_2_fault_propagation():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    simulator_instance.start_fault_injection(
        scenario="FUEL_INJECTOR_ABNORMALITY",
        component="INJECTOR_CYL_2",
        profile="GRADUAL",
        intensity=1.0,
        rate="FAST"
    )

    for _ in range(30):
        frame_cont = simulator_instance.get_next_frame()
        snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    active_injections = snapshot.get("active_injections", [])
    assert len(active_injections) >= 1
    target_inj = active_injections[0]
    assert target_inj.get("resolved_component") == "INJECTOR_CYL_2" or "2" in str(target_inj.get("resolved_component"))

    # Verify combustion subsystem evidence responded
    sub_ev = snapshot.get("subsystem_evidence", {}).get("combustion", {})
    assert sub_ev.get("subsystem") == "COMBUSTION"
