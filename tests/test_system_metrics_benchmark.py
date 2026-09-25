import sys
import os
import json
import asyncio
import time

# Ensure workspace root is in python path
sys.path.insert(0, os.path.abspath('.'))

from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance
from backend.metrics_tracker import metrics_tracker_instance

async def run_system_metrics_benchmark():
    print("=== STARTING SYSTEM METRICS & ASSUMPTIONS BENCHMARK SUITE ===")
    
    # 1. Reset metrics & simulation
    simulator_instance.reset()
    digital_twin_core_instance.reset()
    metrics_tracker_instance.reset()
    simulator_instance.set_mission_profile("CRUISE")
    
    print("\n--- RUNNING 30-SECOND NOMINAL CRUISE BENCHMARK (300 frames @ 10Hz target) ---")
    start_wall = time.perf_counter()
    
    for i in range(300):
        t_gen_0 = time.perf_counter()
        raw_frame = simulator_instance.get_next_frame()
        twin_frame = digital_twin_core_instance.process_telemetry_frame(raw_frame)
        
        t_pub_0 = time.perf_counter()
        msg_str = json.dumps(twin_frame)
        t_pub_1 = time.perf_counter()
        
        metrics_tracker_instance.record_ws_publish_latency((t_pub_1 - t_pub_0) * 1000.0)
        metrics_tracker_instance.record_end_to_end_latency((t_pub_1 - t_gen_0) * 1000.0)
        metrics_tracker_instance.record_ws_message()
        
        # simulate 10Hz pacing (0.1s interval)
        await asyncio.sleep(0.098)
        
    elapsed_wall = time.perf_counter() - start_wall
    print(f"Completed 300 frames in {elapsed_wall:.2f} seconds.")
    
    # Extract 30-second Nominal Metrics
    summary = metrics_tracker_instance.get_summary()
    
    telem_m = summary["telemetry"]
    lat_m = summary["latencies"]
    integ_m = summary["data_integrity"]
    ws_m = summary["websocket"]
    
    print(f"\n[30-SECOND NOMINAL BENCHMARK RESULTS]")
    print(f"Telemetry Target: {telem_m['target_hz']} Hz")
    print(f"Telemetry Measured: {telem_m['effective_hz']} Hz")
    print(f"Mean Interval: {telem_m['mean_interval_ms']} ms")
    print(f"P95 Interval: {telem_m['p95_interval_ms']} ms")
    print(f"Digital Twin Mean: {lat_m['digital_twin']['mean']} ms | P95: {lat_m['digital_twin']['p95']} ms")
    print(f"Physics Mean: {lat_m['physics']['mean']} ms | P95: {lat_m['physics']['p95']} ms")
    print(f"Autoencoder Mean: {lat_m['autoencoder']['mean']} ms | P95: {lat_m['autoencoder']['p95']} ms")
    print(f"GRU Mean: {lat_m['gru_forecast']['mean']} ms | P95: {lat_m['gru_forecast']['p95']} ms")
    print(f"Predictive Engine Mean: {lat_m['predictive_health']['mean']} ms | P95: {lat_m['predictive_health']['p95']} ms")
    print(f"WebSocket Hz: {ws_m['publish_rate_hz']} msgs/s")
    print(f"Valid Frames: {integ_m['valid_ingested_frames']}")
    print(f"Invalid Frames: {integ_m['dropped_invalid_frames']}")
    print(f"Dropped Frames: {integ_m['dropped_invalid_frames']}")
    print(f"Data Integrity: {integ_m['data_integrity_text']}")
    
    # Assert integrity
    assert integ_m["valid_ingested_frames"] == 300, f"Expected 300 valid frames, got {integ_m['valid_ingested_frames']}"
    assert integ_m["data_integrity_pct"] == 100.0, f"Expected 100% integrity, got {integ_m['data_integrity_pct']}"
    assert telem_m["effective_hz"] is not None and telem_m["effective_hz"] > 0
    
    # 2. Thermal Predictive Benchmark
    print("\n--- RUNNING THERMAL PREDICTIVE BENCHMARK (Gradual Cylinder Thermal Degradation) ---")
    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL",
        component="CYLINDER_1",
        profile="GRADUAL",
        intensity=1.0,
        rate="MODERATE"
    )
    
    warning_ts = None
    active_ts = None
    
    for step in range(1, 150):
        raw = simulator_instance.get_next_frame()
        twin = digital_twin_core_instance.process_telemetry_frame(raw)
        
        seq = twin["sequence_number"]
        state = twin["system_state"]
        ts = twin["timestamp"]
        cht1 = twin["telemetry"]["cht1"]
        
        diagnostics = twin.get("predictive_diagnostics", [])
        is_active = any(d.get("status") == "ACTIVE_FAULT" for d in diagnostics) or state == "CRITICAL"
        
        if (state in ["WARNING", "PREDICTIVE_RISK", "CAUTION"]) and not is_active and warning_ts is None:
            warning_ts = ts
            print(f"First Predictive Warning detected at t={warning_ts:.1f}s (CHT1={cht1:.1f}°C, State={state})")
            
        if is_active and active_ts is None and warning_ts is not None:
            active_ts = ts
            print(f"Active Fault confirmed at t={active_ts:.1f}s (CHT1={cht1:.1f}°C, State={state})")
            break
            
        await asyncio.sleep(0.01)
        
    lead_time = round(active_ts - warning_ts, 1) if (warning_ts and active_ts) else None
    print(f"\n[THERMAL PREDICTIVE BENCHMARK RESULTS]")
    print(f"First Predictive Warning Time: t = {warning_ts:.1f} s")
    print(f"Active Fault Time: t = {active_ts:.1f} s")
    print(f"Measured Predictive Lead Time: {lead_time} seconds")
    
    assert warning_ts is not None, "Predictive Warning was not triggered during thermal test!"
    assert active_ts is not None, "Active Fault was not confirmed during thermal test!"
    assert lead_time > 0.0, f"Expected positive lead time, got {lead_time}"
    
    print("\n=== SYSTEM METRICS BENCHMARK COMPLETED SUCCESSFULLY ===")
    return {
        "summary": summary,
        "warning_ts": warning_ts,
        "active_ts": active_ts,
        "lead_time": lead_time
    }

if __name__ == "__main__":
    asyncio.run(run_system_metrics_benchmark())
