import pytest
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

def test_operator_diagnostics_never_nominal_when_state_abnormal():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL_DEGRADATION",
        component="CYLINDER_2",
        profile="SUDDEN",
        intensity=1.5,
        rate="FAST"
    )

    for _ in range(15):
        frame_cont = simulator_instance.get_next_frame()
        snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    sys_state = snapshot.get("system_state")
    diagnostics = snapshot.get("diagnostics", [])

    if sys_state != "NORMAL":
        assert len(diagnostics) > 0, f"Diagnostics list empty despite system state being {sys_state}"
        for diag in diagnostics:
            assert diag.get("status") in ["ACTIVE_FAULT", "PREDICTIVE_RISK"]
            assert diag.get("affected_subsystem") is not None
