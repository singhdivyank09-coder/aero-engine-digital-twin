import pytest
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

def test_sensor_drift_does_not_modify_true_physics_state():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    simulator_instance.start_fault_injection(
        scenario="SENSOR_DRIFT",
        component="OIL_PRESSURE_SENSOR",
        profile="GRADUAL",
        intensity=1.0,
        rate="FAST"
    )

    for _ in range(30):
        frame_cont = simulator_instance.get_next_frame()
        snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    phys_exp = snapshot.get("physics_expected", {})
    telem = snapshot.get("telemetry", {})

    # True physics expected oil pressure remains in nominal band (~4.2 bar)
    assert abs(phys_exp.get("expected_oil_press", 4.2) - 4.2) < 0.5

    # Observed telemetry oil pressure was drifted
    obs_oil = float(telem.get("oil_press", 4.2))
    assert obs_oil < 3.5

    # Residual observed != expected grows
    residuals = snapshot.get("residuals", {})
    assert abs(residuals.get("oil_press_delta", 0.0)) > 0.5
