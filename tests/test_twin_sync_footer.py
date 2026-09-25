import pytest
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

def test_twin_sync_canonical_snapshot_fields():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    frame_cont = simulator_instance.get_next_frame()
    snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    # Required fields for TWIN_SYNC footer synchronization
    assert "session_id" in snapshot
    assert "sequence_number" in snapshot
    assert "timestamp" in snapshot
    assert "scenario" in snapshot or "scenario_id" in snapshot or "mission_profile" in snapshot
    assert "system_state" in snapshot or "global_state" in snapshot

    session_id = snapshot.get("session_id")
    seq = snapshot.get("sequence_number")
    ts = snapshot.get("timestamp")
    state = snapshot.get("system_state")

    assert session_id == "TWIN_SESSION_SIH26054"
    assert isinstance(seq, int)
    assert isinstance(ts, (int, float))
    assert state in ["NORMAL", "WATCH", "CAUTION", "WARNING", "CRITICAL"]

def test_twin_sync_fault_progression_and_critical_state_sync():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL_DEGRADATION",
        component="CYLINDER_4",
        profile="SUDDEN",
        intensity=2.0,
        rate="FAST"
    )

    for _ in range(20):
        frame_cont = simulator_instance.get_next_frame()
        snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    sys_state = snapshot.get("system_state")
    global_state = snapshot.get("global_state")

    # Authoritative canonical state consistency across snapshot properties
    assert sys_state == global_state
    assert sys_state in ["WARNING", "CRITICAL"]

def test_twin_sync_scenario_change():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    simulator_instance.set_mission_profile("HIGH_ALTITUDE")
    frame_cont = simulator_instance.get_next_frame()
    snapshot = digital_twin_core_instance.process_telemetry_frame(frame_cont)

    sc_id = snapshot.get("scenario_id") or snapshot.get("mission_profile") or (snapshot.get("scenario", {}).get("id") if isinstance(snapshot.get("scenario"), dict) else snapshot.get("scenario"))
    assert sc_id == "HIGH_ALTITUDE"
