import pytest
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

def test_predictive_early_warning_before_hard_limit_breach():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL_DEGRADATION",
        component="CYLINDER_2",
        profile="GRADUAL",
        intensity=1.0,
        rate="SLOW"
    )

    predictive_warning_issued = False

    for _ in range(30):
        frame_cont = simulator_instance.get_next_frame()
        snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

        telem = snapshot.get("telemetry", {})
        cht2 = float(telem.get("cht2", 120.0))
        sys_state = snapshot.get("system_state")
        dfcs_adv = snapshot.get("gcs_dfcs_advisory", {})

        # If CHT is still below hard limit (145°C), check if early warning / PRECAUTIONARY advisory triggers
        if cht2 < 145.0:
            if sys_state in ["WATCH", "CAUTION"] or dfcs_adv.get("level") in ["ENHANCED_MONITORING", "PRECAUTIONARY"]:
                predictive_warning_issued = True
                break

    assert predictive_warning_issued is True, "Predictive early warning was not issued before hard limit breach"
