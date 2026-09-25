import sys
import os
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.mission_recorder import MissionRecorder
from backend.replay_service import ReplayService, replay_service_instance

def test_replay_dynamic_frame_count():
    """Verify that ReplayService uses real recorded frame count and NOT a fixed 300-frame demo array."""
    rec = MissionRecorder()
    rec.start_new_mission(initial_scenario="CRUISE")
    mission_id = rec.current_mission_id
    
    # Record exactly 42 frames
    for i in range(42):
        rec.record_snapshot({
            "session_id": "session_test_dynamic",
            "sequence_number": i + 1,
            "timestamp": i * 0.1,
            "scenario": "CRUISE",
            "system_state": "NORMAL",
            "overall_health_index": 98.0 - i * 0.1,
            "anomaly_score": 0.01 + i * 0.001,
            "telemetry": {"cht1": 120.0 + i * 0.2, "rpm": 5000, "oil_press": 4.2},
            "active_faults": [],
            "latest_forecast": {"status": "READY", "forecast_30s": {"cht1": 125.0}},
            "prototype_rul_estimate": {"display_prediction_cycles": 200.0 - i}
        })
    
    replay_data = replay_service_instance.get_mission_data(mission_id)
    assert replay_data["summary"]["mission_id"] == mission_id
    assert len(replay_data["frames"]) == 42
    assert replay_data["summary"]["frame_count"] == 42
    assert replay_data["summary"]["duration"] == pytest.approx(4.1, 0.1)

def test_replay_frame_reconstruction_integrity():
    """Verify frame N in ReplayService reproduces recorded snapshot N exactly."""
    rec = MissionRecorder()
    rec.start_new_mission(initial_scenario="HOT_WEATHER")
    mission_id = rec.current_mission_id
    
    target_snapshot = {
        "session_id": "session_test_integrity",
        "sequence_number": 15,
        "timestamp": 1.5,
        "scenario": "HOT_WEATHER",
        "system_state": "CAUTION",
        "overall_health_index": 82.5,
        "anomaly_score": 0.125,
        "telemetry": {"cht1": 134.5, "rpm": 5200, "oil_press": 3.8},
        "active_faults": [{"fault_scenario": "CYLINDER_THERMAL", "affected_component": "CYLINDER_1"}],
        "latest_forecast": {"status": "READY", "forecast_30s": {"cht1": 139.0}},
        "prototype_rul_estimate": {"display_prediction_cycles": 185.2}
    }
    
    for i in range(1, 20):
        if i == 15:
            rec.record_snapshot(target_snapshot)
        else:
            rec.record_snapshot({
                "session_id": "session_test_integrity",
                "sequence_number": i,
                "timestamp": i * 0.1,
                "scenario": "HOT_WEATHER",
                "system_state": "NORMAL",
                "overall_health_index": 95.0,
                "anomaly_score": 0.02,
                "telemetry": {"cht1": 120.0},
                "active_faults": []
            })
            
    replay_data = replay_service_instance.get_mission_data(mission_id)
    frame_15 = replay_data["frames"][14] # 0-indexed frame 14 corresponds to sequence #15
    
    assert frame_15["sequence_number"] == 15
    assert frame_15["system_state"] == "CAUTION"
    assert frame_15["telemetry"]["cht1"] == 134.5
    assert frame_15["overall_health_index"] == 82.5
    assert len(frame_15["active_faults"]) == 1

if __name__ == "__main__":
    pytest.main(["-v", __file__])
