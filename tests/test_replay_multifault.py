import sys
import os
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.mission_recorder import MissionRecorder
from backend.replay_service import replay_service_instance

def test_replay_multi_fault_preservation():
    """Verify Mission Replay preserves multiple simultaneous active fault injections."""
    rec = MissionRecorder()
    rec.start_new_mission(initial_scenario="CRUISE")
    mission_id = rec.current_mission_id
    
    fault1 = {
        "fault_id": "FLT-001",
        "fault_scenario": "CYLINDER_THERMAL",
        "affected_component": "CYLINDER_2",
        "injection_profile": "SUDDEN",
        "intensity": 0.8
    }
    fault2 = {
        "fault_id": "FLT-002",
        "fault_scenario": "OIL_PRESSURE_DROP",
        "affected_component": "OIL_SYSTEM",
        "injection_profile": "GRADUAL",
        "intensity": 0.5
    }
    
    # Tick 1: Nominal
    rec.record_snapshot({
        "session_id": "multifault_session",
        "sequence_number": 1,
        "timestamp": 0.1,
        "scenario": "CRUISE",
        "system_state": "NORMAL",
        "overall_health_index": 98.0,
        "anomaly_score": 0.01,
        "telemetry": {"cht2": 120.0, "oil_press": 4.2},
        "active_faults": []
    })
    
    # Tick 2: Fault 1 active
    rec.record_snapshot({
        "session_id": "multifault_session",
        "sequence_number": 2,
        "timestamp": 0.2,
        "scenario": "CRUISE",
        "system_state": "CAUTION",
        "overall_health_index": 85.0,
        "anomaly_score": 0.12,
        "telemetry": {"cht2": 134.0, "oil_press": 4.2},
        "active_faults": [fault1]
    })
    
    # Tick 3: Multi-fault active (Fault 1 + Fault 2)
    rec.record_snapshot({
        "session_id": "multifault_session",
        "sequence_number": 3,
        "timestamp": 0.3,
        "scenario": "CRUISE",
        "system_state": "WARNING",
        "overall_health_index": 65.0,
        "anomaly_score": 0.45,
        "telemetry": {"cht2": 140.0, "oil_press": 2.8},
        "active_faults": [fault1, fault2]
    })
    
    replay_data = replay_service_instance.get_mission_data(mission_id)
    frames = replay_data["frames"]
    
    # Verify frame 3 contains BOTH active faults
    frame_3 = frames[2]
    assert len(frame_3["active_faults"]) == 2
    components = [f["affected_component"] for f in frame_3["active_faults"]]
    assert "CYLINDER_2" in components
    assert "OIL_SYSTEM" in components
    assert frame_3["system_state"] == "WARNING"

def test_replay_partial_fault_clear():
    """Verify clearing one fault leaves remaining active faults in historical snapshot."""
    rec = MissionRecorder()
    rec.start_new_mission(initial_scenario="CRUISE")
    mission_id = rec.current_mission_id
    
    fault2 = {
        "fault_id": "FLT-002",
        "fault_scenario": "OIL_PRESSURE_DROP",
        "affected_component": "OIL_SYSTEM",
        "injection_profile": "GRADUAL",
        "intensity": 0.5
    }
    
    # Thermal cleared, oil fault remains active
    rec.record_snapshot({
        "session_id": "multifault_session",
        "sequence_number": 4,
        "timestamp": 0.4,
        "scenario": "CRUISE",
        "system_state": "CAUTION",
        "overall_health_index": 82.0,
        "anomaly_score": 0.15,
        "telemetry": {"cht2": 122.0, "oil_press": 2.9},
        "active_faults": [fault2]
    })
    
    replay_data = replay_service_instance.get_mission_data(mission_id)
    frame_4 = replay_data["frames"][0]
    assert len(frame_4["active_faults"]) == 1
    assert frame_4["active_faults"][0]["affected_component"] == "OIL_SYSTEM"

if __name__ == "__main__":
    pytest.main(["-v", __file__])
