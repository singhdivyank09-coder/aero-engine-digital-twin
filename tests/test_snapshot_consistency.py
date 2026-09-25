import pytest
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

def test_single_snapshot_session_and_sequence_number_consistency():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    frame_cont = simulator_instance.get_next_frame()
    snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    session_id = snapshot.get("session_id")
    sequence_number = snapshot.get("sequence_number")
    system_state = snapshot.get("system_state")

    assert session_id is not None
    assert sequence_number is not None
    assert system_state is not None

    assert snapshot.get("global_state") == system_state
    assert snapshot.get("state_machine", {}).get("current_state") == system_state
    assert snapshot.get("gcs_dfcs_advisory") is not None
