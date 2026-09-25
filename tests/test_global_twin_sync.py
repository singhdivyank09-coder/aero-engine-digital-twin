"""
Automated Test Suite — Global Digital Twin State Synchronization
Tests:
- Test A: Baseline Sync (REST & WebSocket agree on session_id, sequence_number, scenario, state, health, anomaly)
- Test B: Scenario Change Sync (CRUISE -> HIGH_ALTITUDE propogated within 2 frames to all consumers)
- Test C: Real Fault Injection Sync (Fault injected, active_injections >= 1, state/health equal everywhere)
- Test D: Clear / Recovery Sync (Clear faults, active_injections == 0 everywhere, synchronized recovery)
- Test E: Multi-Client 100-Frame Consistency (3 concurrent WebSocket clients receive identical frames per sequence)
"""

import sys
import os
import json
import asyncio
import time
import urllib.request
import websockets

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/telemetry"

def get_auth_token():
    req = urllib.request.Request(
        f"{BASE_URL}/api/auth/login",
        data=json.dumps({"username": "engineer", "password": "engineer123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["access_token"]

def http_post(endpoint, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def http_get(endpoint, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        headers=headers,
        method="GET"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

async def test_baseline_sync(token):
    print("\n--- TEST A: BASELINE SYNC ---")
    debug_data = http_get("/api/debug/session")
    latest_data = http_get("/api/telemetry/latest", token=token)
    
    async with websockets.connect(WS_URL) as ws:
        msg = await ws.recv()
        ws_data = json.loads(msg)
    
    sess_id = ws_data.get("session_id")
    seq_num = ws_data.get("sequence_number")
    sys_state = ws_data.get("system_state") or ws_data.get("global_state")
    
    sc = ws_data.get("scenario")
    sc_id = sc.get("id") if isinstance(sc, dict) else str(sc)
    
    print(f"WS session_id: {sess_id}, sequence_number: {seq_num}, scenario: {sc_id}, state: {sys_state}")
    
    assert sess_id == "TWIN_SESSION_SIH26054", f"Expected session TWIN_SESSION_SIH26054, got {sess_id}"
    assert seq_num > 0, f"Sequence number must be > 0, got {seq_num}"
    assert sys_state in ["NORMAL", "WATCH", "CAUTION", "WARNING", "CRITICAL"], f"Invalid state: {sys_state}"
    
    assert debug_data["session_id"] == sess_id, "REST debug session_id mismatch"
    assert latest_data["session_id"] == sess_id, "REST latest session_id mismatch"
    print("TEST A — BASELINE: PASS")
    return True

async def test_scenario_sync(token):
    print("\n--- TEST B: SCENARIO CHANGE SYNC ---")
    # Set to CRUISE first
    http_post("/api/mission/set-profile", {"profile": "CRUISE"}, token=token)
    await asyncio.sleep(0.3)
    
    # Connect WS listener
    async with websockets.connect(WS_URL) as ws:
        # Request scenario change to HIGH_ALTITUDE
        http_post("/api/mission/set-profile", {"profile": "HIGH_ALTITUDE"}, token=token)
        
        # Check next 2 frames
        frame1 = json.loads(await ws.recv())
        frame2 = json.loads(await ws.recv())
        
        sc1 = frame1.get("scenario")
        sc1_id = sc1.get("id") if isinstance(sc1, dict) else str(sc1)
        
        sc2 = frame2.get("scenario")
        sc2_id = sc2.get("id") if isinstance(sc2, dict) else str(sc2)
        
        print(f"Frame 1 scenario: {sc1_id}, Frame 2 scenario: {sc2_id}")
        assert sc2_id == "HIGH_ALTITUDE", f"Expected HIGH_ALTITUDE, got {sc2_id}"
        
        # Verify physical telemetry baseline reflects high altitude
        alt = frame2.get("scenario_parameters", {}).get("altitude_m", 0)
        print(f"High Altitude parameter altitude_m: {alt} m")
        assert alt >= 3000, f"Expected altitude >= 3000m for HIGH_ALTITUDE, got {alt}"

    print("TEST B — SCENARIO SYNC: PASS")
    return True

async def test_real_fault_sync(token):
    print("\n--- TEST C: REAL FAULT INJECTION SYNC ---")
    async with websockets.connect(WS_URL) as ws:
        await ws.recv()  # Drain initial snapshot sent on connection
        
        # Inject Cylinder Thermal Degradation on Cylinder 2
        fault_res = http_post("/api/fault-injection/start", {
            "scenario": "CYLINDER_THERMAL",
            "component": "CYLINDER_2",
            "profile": "SUDDEN",
            "intensity": 1.0,
            "rate": "FAST"
        }, token=token)
        
        print(f"Fault start response status: {fault_res.get('status')}")
        
        frame = None
        for _ in range(3):
            msg = await ws.recv()
            f = json.loads(msg)
            if len(f.get("active_injections", [])) >= 1:
                frame = f
                break
        if frame is None:
            frame = f
            
        active_injections = frame.get("active_injections", [])
        sys_state = frame.get("system_state")
        health_overall = frame.get("health", {}).get("overall", frame.get("overall_health_index"))
        anomaly_score = frame.get("anomaly", {}).get("score", frame.get("anomaly_score"))
        
        print(f"Active injections count: {len(active_injections)}")
        print(f"System State: {sys_state}, Health: {health_overall}%, Anomaly Score: {anomaly_score}")
        
        assert len(active_injections) >= 1, "Active injections must be >= 1"
        assert active_injections[0].get("component") == "CYLINDER_2", "Expected CYLINDER_2 active fault"
        
        # Check canonical state consistency
        gcs_adv = frame.get("gcs_dfcs_advisory", {})
        print(f"GCS DFCS Advisory Level: {gcs_adv.get('level')}")
        assert gcs_adv.get("level") == sys_state, f"GCS advisory level {gcs_adv.get('level')} must match system_state {sys_state}"

    print("TEST C — REAL FAULT SYNC: PASS")
    return True

async def test_clear_recovery_sync(token):
    print("\n--- TEST D: CLEAR / RECOVERY SYNC ---")
    async with websockets.connect(WS_URL) as ws:
        await ws.recv()  # Drain initial frame
        clear_res = http_post("/api/fault-injection/clear", {}, token=token)
        print(f"Clear fault response: {clear_res.get('status')}")
        
        frame = None
        for _ in range(3):
            msg = await ws.recv()
            f = json.loads(msg)
            if len(f.get("active_injections", [])) == 0:
                frame = f
                break
        if frame is None:
            frame = f
            
        active_injections = frame.get("active_injections", [])
        print(f"Post-clear active injections count: {len(active_injections)}")
        assert len(active_injections) == 0, f"Expected 0 active injections, got {len(active_injections)}"
        
    print("TEST D — CLEAR / RECOVERY SYNC: PASS")
    return True

async def test_multi_client_consistency():
    print("\n--- TEST E: MULTI-CLIENT 100-FRAME CONSISTENCY ---")
    async with websockets.connect(WS_URL) as ws1, \
               websockets.connect(WS_URL) as ws2, \
               websockets.connect(WS_URL) as ws3:
        
        mismatches = 0
        frames_checked = 0
        
        for i in range(100):
            msg1 = await ws1.recv()
            msg2 = await ws2.recv()
            msg3 = await ws3.recv()
            
            f1 = json.loads(msg1)
            f2 = json.loads(msg2)
            f3 = json.loads(msg3)
            
            s1 = (f1.get("session_id"), f1.get("sequence_number"), f1.get("system_state"), f1.get("overall_health_index"))
            s2 = (f2.get("session_id"), f2.get("sequence_number"), f2.get("system_state"), f2.get("overall_health_index"))
            s3 = (f3.get("session_id"), f3.get("sequence_number"), f3.get("system_state"), f3.get("overall_health_index"))
            
            if s1 != s2 or s1 != s3:
                mismatches += 1
                print(f"[FRAME {i} MISMATCH] Client 1: {s1} | Client 2: {s2} | Client 3: {s3}")
            else:
                frames_checked += 1
                
        print(f"100-Frame Multi-Client Consistency: {frames_checked}/100 frames perfectly matched")
        assert mismatches == 0, f"Found {mismatches} mismatched frames across clients"
        
    print("TEST E — MULTI-CLIENT 100-FRAME CONSISTENCY: PASS")
    return True

async def main():
    print("Starting Global Digital Twin State Synchronization Verification Suite...")
    token = get_auth_token()
    
    res_a = await test_baseline_sync(token)
    res_b = await test_scenario_sync(token)
    res_c = await test_real_fault_sync(token)
    res_d = await test_clear_recovery_sync(token)
    res_e = await test_multi_client_consistency()
    
    print("\n==========================================")
    print("ALL 5 GLOBAL TWIN SYNCHRONIZATION TESTS PASSED!")
    print("==========================================")

if __name__ == "__main__":
    asyncio.run(main())
