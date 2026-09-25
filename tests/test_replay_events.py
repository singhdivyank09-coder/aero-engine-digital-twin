import sys
import os
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.mission_recorder import MissionRecorder
from backend.replay_service import replay_service_instance

def test_event_lifecycle_recording():
    """Verify event lifecycle (START, FAULT_INJECTED, STATE_TRANSITION, FAULT_CLEARED)."""
    rec = MissionRecorder()
    rec.start_new_mission(initial_scenario="CRUISE")
    mission_id = rec.current_mission_id
    
    # 1. Nominal Frame
    rec.record_snapshot({
        "session_id": "event_session",
        "sequence_number": 1,
        "timestamp": 0.1,
        "scenario": "CRUISE",
        "system_state": "NORMAL",
        "overall_health_index": 98.0,
        "anomaly_score": 0.01,
        "telemetry": {"cht1": 120.0},
        "active_faults": []
    })
    
    # 2. Inject Fault & State Change to WATCH
    rec.record_snapshot({
        "session_id": "event_session",
        "sequence_number": 2,
        "timestamp": 0.2,
        "scenario": "CRUISE",
        "system_state": "WATCH",
        "overall_health_index": 91.0,
        "anomaly_score": 0.08,
        "telemetry": {"cht1": 128.5},
        "active_faults": [{"fault_scenario": "CYLINDER_THERMAL", "affected_component": "CYLINDER_1"}]
    })
    
    # 3. State transition to WARNING
    rec.record_snapshot({
        "session_id": "event_session",
        "sequence_number": 3,
        "timestamp": 0.3,
        "scenario": "CRUISE",
        "system_state": "WARNING",
        "overall_health_index": 72.0,
        "anomaly_score": 0.25,
        "telemetry": {"cht1": 139.0},
        "active_faults": [{"fault_scenario": "CYLINDER_THERMAL", "affected_component": "CYLINDER_1"}]
    })
    
    # 4. Clear Fault
    rec.record_snapshot({
        "session_id": "event_session",
        "sequence_number": 4,
        "timestamp": 0.4,
        "scenario": "CRUISE",
        "system_state": "NORMAL",
        "overall_health_index": 97.5,
        "anomaly_score": 0.02,
        "telemetry": {"cht1": 121.0},
        "active_faults": []
    })
    
    replay_data = replay_service_instance.get_mission_data(mission_id)
    events = replay_data["events"]
    markers = replay_data["timeline_markers"]
    
    event_types = [e["event_type"] for e in events]
    assert "MISSION_START" in event_types
    assert "FAULT_INJECTION_STARTED" in event_types
    assert "WATCH_ENTERED" in event_types
    assert "WARNING_ENTERED" in event_types
    assert "ALL_FAULTS_CLEARED" in event_types
    
    # Markers verify seeking capability
    assert len(markers) == len(events)
    marker_labels = [m["label"] for m in markers]
    assert any("Fault Injection Started" in l for l in marker_labels)

if __name__ == "__main__":
    pytest.main(["-v", __file__])
