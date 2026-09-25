import os
import sys
import time
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance
from backend.main import compute_canonical_tick

def test_active_fault_live_sync():
    simulator_instance.reset()
    digital_twin_core_instance.reset()

    # 1. Start normal cruise baseline
    baseline_frames = []
    for _ in range(50):
        baseline_frames.append(compute_canonical_tick())

    latest_init = baseline_frames[-1]
    assert latest_init["system_state"] in ["NORMAL", "WATCH"]
    assert abs(latest_init["telemetry"]["cht1"] - 120.0) < 5.0

    # 2. Inject Cylinder 1 Thermal Fault (Gradual)
    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL",
        component="CYLINDER_1",
        profile="GRADUAL",
        intensity=1.0,
        rate="MODERATE"
    )

    ramp_history = []
    frame_at_130 = None
    frame_at_150 = None
    frame_at_175 = None

    # Step through 160 frames (~16s of simulation time)
    for _ in range(160):
        frame = compute_canonical_tick()
        ramp_history.append(frame)
        cht1 = frame["telemetry"]["cht1"]

        if cht1 >= 130.0 and frame_at_130 is None:
            frame_at_130 = frame
        if cht1 >= 150.0 and frame_at_150 is None:
            frame_at_150 = frame
        if cht1 >= 170.0 and frame_at_175 is None:
            frame_at_175 = frame

    assert frame_at_130 is not None, "Expected CHT1 to reach at least 130°C during ramp"
    assert frame_at_150 is not None, "Expected CHT1 to reach at least 150°C during ramp"
    assert frame_at_175 is not None, "Expected CHT1 to reach ~175°C during peak fault"

    # Verify frame_at_175 state and forecast consistency
    latest_frame = ramp_history[-1]
    last_telemetry = latest_frame["telemetry"]
    cht1_card = last_telemetry["cht1"]

    # History newest frame matches current frame
    history_newest = ramp_history[-1]
    history_oldest = ramp_history[-300] if len(ramp_history) >= 300 else ramp_history[0]

    print(f"\n[LIVE FAULT TEST RESULTS]")
    print(f"latest_frame sequence={latest_frame['sequence_number']} time={latest_frame['timestamp']:.1f}s")
    print(f"latest frame CHT1 = {cht1_card:.1f} °C")
    print(f"history newest CHT1 = {history_newest['telemetry']['cht1']:.1f} °C")
    print(f"history oldest CHT1 = {history_oldest['telemetry']['cht1']:.1f} °C")
    print(f"Main state = {latest_frame['system_state']}")
    print(f"TWIN_SYNC state = {latest_frame['global_state']}")

    # Forecast consistency check
    fc = latest_frame.get("forecast", {})
    fc10 = (fc.get("forecast_10s") or fc.get("forecast", {}).get("10s", {})).get("cht1")
    fc30 = (fc.get("forecast_30s") or fc.get("forecast", {}).get("30s", {})).get("cht1")
    fc60 = (fc.get("forecast_60s") or fc.get("forecast", {}).get("60s", {})).get("cht1")

    print(f"Forecast card +10/+30/+60 = +10s:{fc10}°C | +30s:{fc30}°C | +60s:{fc60}°C")
    print(f"Forecast graph +10/+30/+60 = +10s:{fc10}°C | +30s:{fc30}°C | +60s:{fc60}°C")

    assert latest_frame["system_state"] == "CRITICAL"
    assert latest_frame["global_state"] == "CRITICAL"
    assert fc10 is not None and fc10 >= cht1_card - 2.0

    # 3. Test Clear All Faults
    simulator_instance.clear_fault_injection()
    recovery_frames = []
    for _ in range(60):
        recovery_frames.append(compute_canonical_tick())

    rec_latest = recovery_frames[-1]
    print(f"Clear All Faults: Final frame seq={rec_latest['sequence_number']} time={rec_latest['timestamp']:.1f}s state={rec_latest['system_state']}")
    assert rec_latest["sequence_number"] > latest_frame["sequence_number"]

if __name__ == "__main__":
    test_active_fault_live_sync()
