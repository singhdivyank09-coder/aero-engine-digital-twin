import sys
import os
import pytest
import datetime

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.mission_recorder import MissionRecorder, mission_recorder_instance
from backend.database import db_get_mission, db_get_all_missions

def test_mission_recorder_unique_id():
    """Verify that MissionRecorder generates real unique IDs matching MIS-YYYYMMDD-XXX format."""
    rec = MissionRecorder()
    assert rec.current_mission_id.startswith("MIS-")
    assert "MIS-2026-TAPAS-001" not in rec.current_mission_id
    
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    assert date_str in rec.current_mission_id

def test_recording_snapshot_pipeline():
    """Verify that snapshot recording saves snapshots and events to SQLite."""
    rec = MissionRecorder()
    rec.start_new_mission(initial_scenario="CRUISE")
    mission_id = rec.current_mission_id
    
    # Record a nominal tick
    sample_snapshot = {
        "session_id": "test_session_rec",
        "sequence_number": 1,
        "timestamp": 0.1,
        "scenario": "CRUISE",
        "system_state": "NORMAL",
        "overall_health_index": 98.5,
        "anomaly_score": 0.012,
        "telemetry": {"cht1": 120.5, "rpm": 5000, "oil_press": 4.2},
        "active_faults": [],
        "latest_forecast": {"status": "READY", "forecast_30s": {"cht1": 121.0}},
        "prototype_rul_estimate": {"display_prediction_cycles": 210.0}
    }
    
    rec.record_snapshot(sample_snapshot)
    assert rec.recorded_frames == 1
    
    # Check DB
    mission_data = db_get_mission(mission_id)
    assert mission_data is not None
    snapshots = mission_data.get("snapshots", [])
    events = mission_data.get("events", [])
    assert len(snapshots) == 1
    assert len(events) >= 1  # MISSION_START event at minimum
    
    # Verify recorded frame content matches snapshot
    snap_data = snapshots[0]
    assert snap_data["sequence_number"] == 1
    assert snap_data["telemetry"]["cht1"] == 120.5

def test_scenario_change_recording():
    """Verify scenario transitions generate explicit events in the recorded stream."""
    rec = MissionRecorder()
    rec.start_new_mission(initial_scenario="CRUISE")
    mission_id = rec.current_mission_id
    
    snap1 = {
        "session_id": "test_session_scen",
        "sequence_number": 1,
        "timestamp": 0.1,
        "scenario": "CRUISE",
        "system_state": "NORMAL",
        "overall_health_index": 98.5,
        "anomaly_score": 0.012,
        "telemetry": {"cht1": 120.0},
        "active_faults": []
    }
    rec.record_snapshot(snap1)
    
    # Change scenario to HIGH_ALTITUDE
    snap2 = {
        "session_id": "test_session_scen",
        "sequence_number": 2,
        "timestamp": 0.2,
        "scenario": "HIGH_ALTITUDE",
        "system_state": "NORMAL",
        "overall_health_index": 98.2,
        "anomaly_score": 0.014,
        "telemetry": {"cht1": 121.0},
        "active_faults": []
    }
    rec.record_snapshot(snap2)
    
    mission_data = db_get_mission(mission_id)
    events = mission_data.get("events", [])
    scenario_events = [e for e in events if e["event_type"] == "SCENARIO_CHANGE"]
    assert len(scenario_events) == 1
    assert scenario_events[0]["to_scenario"] == "HIGH_ALTITUDE"

if __name__ == "__main__":
    pytest.main(["-v", __file__])
