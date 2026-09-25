import sys
import os
import hashlib
import json
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.mission_recorder import MissionRecorder
from backend.replay_service import replay_service_instance
from backend.digital_twin_core import digital_twin_core_instance

def compute_canonical_frame_hash(frame):
    """Computes a deterministic MD5 hash of canonical snapshot attributes."""
    canonical_dict = {
        "scenario": frame.get("scenario"),
        "system_state": frame.get("system_state"),
        "overall_health_index": round(frame.get("overall_health_index", 0.0), 2),
        "anomaly_score": round(frame.get("anomaly_score", 0.0), 4),
        "telemetry": {k: round(v, 2) for k, v in frame.get("telemetry", {}).items() if isinstance(v, (int, float))},
        "active_faults_count": len(frame.get("active_faults", [])),
    }
    raw_str = json.dumps(canonical_dict, sort_keys=True)
    return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

def test_replay_session_isolation_from_live_twin():
    """Verify that accessing ReplaySession never modifies live Digital Twin state or live sequence number."""
    # Capture live state
    live_counter_before = digital_twin_core_instance.cycle_counter
    live_state_before = digital_twin_core_instance.current_system_state
    
    # Create and fetch a recorded replay mission
    rec = MissionRecorder()
    rec.start_new_mission(initial_scenario="HIGH_ALTITUDE")
    mission_id = rec.current_mission_id
    
    rec.record_snapshot({
        "session_id": "historical_session",
        "sequence_number": 99,
        "timestamp": 99.0,
        "scenario": "HIGH_ALTITUDE",
        "system_state": "CRITICAL",
        "overall_health_index": 30.0,
        "anomaly_score": 0.95,
        "telemetry": {"cht1": 155.0, "rpm": 4000},
        "active_faults": [{"fault_scenario": "CYLINDER_THERMAL"}]
    })
    
    replay_data = replay_service_instance.get_mission_data(mission_id)
    assert len(replay_data["frames"]) == 1
    
    # Verify live Digital Twin core was completely unaffected by replay fetch
    assert digital_twin_core_instance.cycle_counter == live_counter_before
    assert digital_twin_core_instance.current_system_state == live_state_before

def test_snapshot_hash_consistency():
    """Verify reconstructed replay frame hash matches stored frame hash exactly."""
    rec = MissionRecorder()
    rec.start_new_mission(initial_scenario="CRUISE")
    mission_id = rec.current_mission_id
    
    original_frame = {
        "session_id": "hash_test_session",
        "sequence_number": 10,
        "timestamp": 1.0,
        "scenario": "CRUISE",
        "system_state": "CAUTION",
        "overall_health_index": 84.2,
        "anomaly_score": 0.145,
        "telemetry": {"cht1": 133.4, "rpm": 5100, "oil_press": 3.9},
        "active_faults": [{"fault_scenario": "CYLINDER_THERMAL"}]
    }
    
    rec.record_snapshot(original_frame)
    original_hash = compute_canonical_frame_hash(original_frame)
    
    # Retrieve from ReplayService
    replay_data = replay_service_instance.get_mission_data(mission_id)
    reconstructed_frame = replay_data["frames"][0]
    reconstructed_hash = compute_canonical_frame_hash(reconstructed_frame)
    
    assert reconstructed_hash == original_hash, f"Frame hash mismatch! Stored: {original_hash}, Reconstructed: {reconstructed_hash}"

if __name__ == "__main__":
    pytest.main(["-v", __file__])
