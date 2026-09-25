"""
Test Suite: GRU Forecast Continuity During Active Fault Injection & System Degradation
SIH 26054 — Aero-Piston Engine Digital Twin
"""

import sys
import os
import time
import pytest

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.digital_twin_core import DigitalTwinCore, simulator_instance
from backend.gru_forecast_service import GruForecastService, gru_forecast_service_instance

def create_synthetic_telemetry(seq_num: int, timestamp: float, cht1: float = 120.0, oil_p: float = 4.2, vib: float = 1.12) -> dict:
    return {
        "sequence_number": seq_num,
        "timestamp": timestamp,
        "rpm": 2400.0,
        "map": 29.92,
        "cht1": cht1,
        "cht2": 120.0,
        "cht3": 120.0,
        "cht4": 120.0,
        "egt1": 750.0,
        "egt2": 750.0,
        "egt3": 750.0,
        "egt4": 750.0,
        "oil_press": oil_p,
        "oil_pressure": oil_p,
        "oil_temp": 88.5,
        "oil_temperature": 88.5,
        "fuel_flow": 10.5,
        "vibration_rms": vib,
        "battery_volt": 14.10,
        "bus_voltage": 14.10,
        "altitude": 1500.0,
        "ambient_temperature": 15.0,
        "throttle": 70.0
    }

def test_gru_thermal_fault_continuity():
    """Verify GRU forecast continues updating continuously during rising CHT1 thermal fault."""
    core = DigitalTwinCore()
    
    # Pre-fill history to ensure READY status (60 frames)
    history = []
    for seq in range(1, 61):
        t = seq * 0.1
        frame = create_synthetic_telemetry(seq, t, cht1=120.0)
        history.append(frame)
        core.process_telemetry_frame({"telemetry": frame, "mission_profile": "CRUISE"})

    # Check nominal forecast
    res_nom = core.latest_forecast
    assert res_nom is not None
    assert res_nom.get("status") == "READY"
    assert "forecast_10s" in res_nom

    # Simulate rising CHT1 fault progression: 120 -> 135 -> 150 -> 165 -> 175 C
    cht_steps = [125.0, 135.0, 145.0, 160.0, 175.0]
    prev_fc_10 = None
    prev_fc_id = None
    prev_seq = None

    for idx, cht_val in enumerate(cht_steps):
        # Push 10 frames of rising telemetry
        for i in range(10):
            seq = 60 + idx * 10 + i + 1
            t = seq * 0.1
            frame = create_synthetic_telemetry(seq, t, cht1=cht_val + (i * 0.5))
            snap = core.process_telemetry_frame({"telemetry": frame, "mission_profile": "CRUISE"})

        fc = snap.get("latest_forecast") or snap.get("forecast")
        assert fc is not None, f"Forecast missing at step {idx}"
        assert fc.get("status") == "READY", f"Forecast status not READY at step {idx}"
        assert fc.get("ready") is True, f"Forecast ready field is False at step {idx}"
        
        fc_id = fc.get("forecast_id")
        src_seq = fc.get("source_sequence_number")
        fc10_cht1 = fc.get("forecast_10s", {}).get("cht1")

        assert fc_id != prev_fc_id, f"Forecast ID failed to advance at CHT1={cht_val}"
        assert src_seq > (prev_seq or 0), f"Source sequence number did not advance at CHT1={cht_val}"
        assert fc10_cht1 != prev_fc_10, f"Forecast 10s value did not update at CHT1={cht_val}"

        prev_fc_id = fc_id
        prev_seq = src_seq
        prev_fc_10 = fc10_cht1
        print(f"[TEST_THERMAL_PROGRESSION] CHT1={cht_val:.1f}C -> Forecast ID={fc_id}, Seq={src_seq}, +10s={fc10_cht1}C, +30s={fc.get('forecast_30s', {}).get('cht1')}C, +60s={fc.get('forecast_60s', {}).get('cht1')}C")

def test_gru_critical_state_sustained_inference():
    """Verify GRU forecast continues updating while system is sustained in CRITICAL state."""
    core = DigitalTwinCore()
    
    # Warmup
    for seq in range(1, 61):
        frame = create_synthetic_telemetry(seq, seq * 0.1, cht1=120.0)
        core.process_telemetry_frame({"telemetry": frame})

    # Push sustained CRITICAL telemetry (CHT1 = 175.0 C for 30 seconds = 300 frames)
    fc_ids = set()
    for seq in range(61, 361):
        t = seq * 0.1
        frame = create_synthetic_telemetry(seq, t, cht1=175.0 + (seq % 5) * 0.2)
        snap = core.process_telemetry_frame({"telemetry": frame})
        
        fc = snap.get("latest_forecast")
        assert fc is not None
        assert fc.get("status") == "READY"
        fc_ids.add(fc.get("forecast_id"))

    # Verify we got unique fresh forecast IDs throughout CRITICAL state
    assert len(fc_ids) >= 290, f"Expected ~300 unique forecast IDs in CRITICAL state, got {len(fc_ids)}"
    print(f"[TEST_CRITICAL_SUSTAINED] Successfully generated {len(fc_ids)} fresh forecasts during 30s of CRITICAL state operation.")

def test_gru_post_clear_recovery_inference():
    """Verify GRU forecast adapts continuously during fault recovery after clearing."""
    core = DigitalTwinCore()
    
    # Warmup
    for seq in range(1, 61):
        frame = create_synthetic_telemetry(seq, seq * 0.1, cht1=120.0)
        core.process_telemetry_frame({"telemetry": frame})

    # Active fault phase
    for seq in range(61, 100):
        frame = create_synthetic_telemetry(seq, seq * 0.1, cht1=170.0)
        core.process_telemetry_frame({"telemetry": frame})

    # Recovery phase: CHT1 drops from 170 -> 120 C
    recovery_chts = [160.0, 150.0, 140.0, 130.0, 120.0]
    for idx, cht_val in enumerate(recovery_chts):
        seq = 100 + idx * 10
        frame = create_synthetic_telemetry(seq, seq * 0.1, cht1=cht_val)
        snap = core.process_telemetry_frame({"telemetry": frame})
        fc = snap.get("latest_forecast")
        
        assert fc.get("status") == "READY"
        fc10_cht1 = fc.get("forecast_10s", {}).get("cht1")
        print(f"[TEST_RECOVERY] Recovery CHT1={cht_val}C -> +10s forecast={fc10_cht1}C")

def test_gru_oil_pressure_fault_continuity():
    """Verify GRU forecasting continues while oil pressure drops below safety limit."""
    core = DigitalTwinCore()
    for seq in range(1, 61):
        frame = create_synthetic_telemetry(seq, seq * 0.1, oil_p=4.2)
        core.process_telemetry_frame({"telemetry": frame})

    # Degrade oil pressure to 1.5 bar (below 2.5 bar envelope)
    oil_pressures = [4.0, 3.5, 3.0, 2.5, 2.0, 1.5]
    for idx, p_val in enumerate(oil_pressures):
        seq = 60 + idx * 10
        frame = create_synthetic_telemetry(seq, seq * 0.1, oil_p=p_val)
        snap = core.process_telemetry_frame({"telemetry": frame})
        fc = snap.get("latest_forecast")

        assert fc.get("status") == "READY"
        fc30_oil = fc.get("forecast_30s", {}).get("oil_press")
        assert fc30_oil is not None
        print(f"[TEST_OIL_PRESSURE] Oil Pressure={p_val} bar -> +30s forecast={fc30_oil} bar")

def test_gru_vibration_fault_continuity():
    """Verify GRU forecasting continues while mechanical vibration rises."""
    core = DigitalTwinCore()
    for seq in range(1, 61):
        frame = create_synthetic_telemetry(seq, seq * 0.1, vib=1.12)
        core.process_telemetry_frame({"telemetry": frame})

    vibrations = [1.5, 2.0, 2.5, 3.0, 3.5]
    for idx, v_val in enumerate(vibrations):
        seq = 60 + idx * 10
        frame = create_synthetic_telemetry(seq, seq * 0.1, vib=v_val)
        snap = core.process_telemetry_frame({"telemetry": frame})
        fc = snap.get("latest_forecast")

        assert fc.get("status") == "READY"
        fc30_vib = fc.get("forecast_30s", {}).get("vibration_rms")
        assert fc30_vib is not None
        print(f"[TEST_VIBRATION] Vibration RMS={v_val} g -> +30s forecast={fc30_vib} g")

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
