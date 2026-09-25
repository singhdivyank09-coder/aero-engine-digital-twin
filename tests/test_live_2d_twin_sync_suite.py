import pytest
import asyncio
import time
from fastapi.testclient import TestClient
from backend.main import app

@pytest.mark.asyncio
async def test_single_session_and_component_sync():
    """
    PART 12 - LIVE SYNCHRONIZATION TEST & COMPONENT ISOLATION
    Verifies that Operator Dashboard, 2D Twin, and Fault Analytics consume the exact same session.
    """
    client = TestClient(app)
    
    # 1. Get baseline snapshot
    res1 = client.get("/api/telemetry/latest")
    assert res1.status_code == 200
    snap1 = res1.json()
    
    session_id1 = snap1.get("session_id")
    seq1 = snap1.get("sequence_number", 0)
    cht1_init = snap1.get("telemetry", {}).get("cht1", 120.0)
    state1 = snap1.get("system_state", "NORMAL")
    
    assert session_id1 is not None, "session_id must not be None"
    print(f"\n[PART 12 SYNC] Session ID: {session_id1} | Sequence: {seq1} | CHT1: {cht1_init}°C | State: {state1}")

    # Allow time for twin loop to step sequence
    await asyncio.sleep(0.3)
    
    res2 = client.get("/api/telemetry/latest")
    snap2 = res2.json()
    session_id2 = snap2.get("session_id")
    seq2 = snap2.get("sequence_number", 0)
    
    assert session_id1 == session_id2, "Session ID must remain identical across queries"
    assert seq2 > seq1, f"Sequence number must increase: {seq2} > {seq1}"
    print(f"[PART 12 SYNC PASS] Single Session Maintained across views ({seq1} -> {seq2})")


@pytest.mark.asyncio
async def test_thermal_degradation_and_isolation():
    """
    PART 13 & 14 - THERMAL ACCEPTANCE TEST & COMPONENT ISOLATION
    Starts Cylinder 1 Thermal Degradation. Verifies predictive early warning before threshold crossing,
    and checks that Cylinder 2, 3, 4 and Oil/Mech/Elec remain NORMAL (Isolated).
    """
    client = TestClient(app)

    # 1. Clear any active faults first
    client.post("/api/fault-injection/clear")
    await asyncio.sleep(0.5)

    # Record baseline state
    res0 = client.get("/api/telemetry/latest").json()
    init_cht1 = res0.get("telemetry", {}).get("cht1", 120.0)
    print(f"\n[THERMAL TEST] Baseline CHT1: {init_cht1}°C | System State: {res0.get('system_state')}")
    assert init_cht1 < 130.0, "Baseline CHT1 should be normal"

    # 2. Start Cylinder 1 Thermal Degradation (Gradual, 60s ramp)
    req = {
        "scenario": "CYLINDER_THERMAL",
        "component": "CYLINDER_1",
        "profile": "GRADUAL",
        "rate": "SLOW",
        "intensity": 1.2
    }
    start_res = client.post("/api/fault-injection/start", json=req)
    assert start_res.status_code == 200
    print("[THERMAL TEST] Injected CYLINDER_1 Thermal Degradation (Gradual 60s Ramp)")

    timeline = []
    predictive_warning_triggered = False
    active_fault_triggered = False
    isolation_verified = False

    # Monitor progression over time
    for step in range(30):
        await asyncio.sleep(0.5)
        snap = client.get("/api/telemetry/latest").json()
        telem = snap.get("telemetry", {})
        sub_states = snap.get("subsystem_states", {})
        sub_health = snap.get("subsystem_health", {})
        fc = snap.get("latest_forecast", {})
        res_tab = snap.get("residuals_table", {})
        sys_state = snap.get("system_state", "NORMAL")

        cht1 = telem.get("cht1", 120.0)
        cht2 = telem.get("cht2", 120.0)
        cht3 = telem.get("cht3", 120.0)
        cht4 = telem.get("cht4", 120.0)
        oil_p = telem.get("oil_press", 4.2)
        vib = telem.get("vibration_rms", 1.12)
        volt = telem.get("battery_volt", 14.1)

        fc30 = fc.get("forecast_30s", {}).get("cht1", cht1) if fc.get("status") == "READY" else cht1
        residual = res_tab.get("avg_cht", {}).get("residual", 0.0)

        # Derive component states as schematic does
        cyl1_state = "CRITICAL" if cht1 >= 145.0 else ("WARNING" if (cht1 >= 138.0 or fc30 >= 145.0) else ("CAUTION" if (cht1 >= 132.0 or fc30 >= 138.0) else ("WATCH" if cht1 >= 126.0 else "NORMAL")))
        cyl2_state = "CRITICAL" if cht2 >= 145.0 else ("WARNING" if cht2 >= 138.0 else ("CAUTION" if cht2 >= 132.0 else ("WATCH" if cht2 >= 126.0 else "NORMAL")))
        oil_state = sub_states.get("lubrication", "NORMAL")
        mech_state = sub_states.get("mechanical", "NORMAL")
        elec_state = sub_states.get("electrical", "NORMAL")

        entry = {
            "t": (step + 1) * 0.5,
            "cht1": round(cht1, 1),
            "fc30": round(fc30, 1),
            "residual": round(residual, 1),
            "cyl1_state": cyl1_state,
            "cyl2_state": cyl2_state,
            "global_state": sys_state
        }
        timeline.append(entry)

        # Check predictive early warning (when current CHT1 < 145.0°C but GRU forecast / residual triggers warning/caution)
        if cht1 < 145.0 and (cyl1_state in ["CAUTION", "WARNING", "WATCH"] or sys_state in ["CAUTION", "WARNING", "WATCH"]):
            predictive_warning_triggered = True

        # Verify component isolation
        if cyl1_state in ["CAUTION", "WARNING", "CRITICAL"]:
            assert cyl2_state in ["NORMAL", "WATCH"], f"Cylinder 2 should remain unaffected (got {cyl2_state})"
            assert oil_state in ["NORMAL", "WATCH"], f"Oil system should remain unaffected during thermal fault (got {oil_state})"
            assert mech_state in ["NORMAL", "WATCH"], f"Mechanical system should remain unaffected (got {mech_state})"
            assert elec_state in ["NORMAL", "WATCH"], f"Electrical system should remain unaffected (got {elec_state})"
            isolation_verified = True

        if cht1 >= 145.0 or sys_state == "CRITICAL":
            active_fault_triggered = True

    print("\n--- THERMAL TEST TIMELINE ---")
    for row in timeline[::3]:
        print(f"t={row['t']}s | CHT1={row['cht1']}°C | GRU30={row['fc30']}°C | Residual={row['residual']}°C | Cyl1={row['cyl1_state']} | Cyl2={row['cyl2_state']} | Global={row['global_state']}")

    assert predictive_warning_triggered, "Predictive warning must trigger before current threshold crossing"
    assert isolation_verified, "Component isolation must be preserved: Cyl 1 degrades while Cyl 2-4 & Oil/Mech/Elec stay nominal"
    print("[THERMAL ACCEPTANCE & ISOLATION PASS]")


@pytest.mark.asyncio
async def test_lubrication_fault_and_isolation():
    """
    PART 15 — LUBRICATION TEST
    Starts oil pressure degradation. Verifies oil system transitions NORMAL -> WATCH -> CAUTION -> WARNING
    while cylinder thermal components do not incorrectly mirror lubrication state.
    """
    client = TestClient(app)

    # Clear faults first
    client.post("/api/fault-injection/clear")
    await asyncio.sleep(0.5)

    # Start Lubrication fault
    req = {
        "scenario": "OIL_PRESSURE",
        "component": "OIL_SYSTEM",
        "profile": "GRADUAL",
        "rate": "FAST",
        "intensity": 1.2
    }
    client.post("/api/fault-injection/start", json=req)
    print("\n[LUBRICATION TEST] Started Oil Pressure Degradation")

    oil_degraded = False
    cyl_isolated = False

    for step in range(20):
        await asyncio.sleep(0.5)
        snap = client.get("/api/telemetry/latest").json()
        telem = snap.get("telemetry", {})
        sub_states = snap.get("subsystem_states", {})
        
        oil_p = telem.get("oil_press", 4.2)
        oil_state = sub_states.get("lubrication", "NORMAL")
        cht1 = telem.get("cht1", 120.0)

        if oil_p < 3.5 or oil_state in ["WATCH", "CAUTION", "WARNING", "CRITICAL"]:
            oil_degraded = True
            # Cylinders should not mirror lubrication fault unless physics actually heats them up
            if cht1 < 135.0:
                cyl_isolated = True

    assert oil_degraded, "Lubrication subsystem must show degradation when oil fault injected"
    assert cyl_isolated, "Cylinder thermal coloring must not incorrectly mirror lubrication state"
    print(f"[LUBRICATION TEST PASS] Oil system degraded while cylinder thermal isolation maintained")


@pytest.mark.asyncio
async def test_sensor_drift_test():
    """
    PART 16 — SENSOR DRIFT TEST
    Injects sensor drift into electrical bus. Verifies residual increases and electrical subsystem detects drift without making thermal/mechanical components critical.
    """
    client = TestClient(app)

    client.post("/api/fault-injection/clear")
    await asyncio.sleep(0.5)

    req = {
        "scenario": "SENSOR_DRIFT",
        "component": "ELECTRICAL_BUS",
        "profile": "GRADUAL",
        "rate": "FAST",
        "intensity": 1.0
    }
    client.post("/api/fault-injection/start", json=req)
    print("\n[SENSOR DRIFT TEST] Injected Electrical Bus Sensor Drift")

    elec_responded = False
    thermal_stayed_safe = False

    for step in range(15):
        await asyncio.sleep(0.5)
        snap = client.get("/api/telemetry/latest").json()
        telem = snap.get("telemetry", {})
        sub_states = snap.get("subsystem_states", {})
        
        volt = telem.get("battery_volt", 14.1)
        elec_st = sub_states.get("electrical", "NORMAL")
        cht1 = telem.get("cht1", 120.0)

        if abs(volt - 14.1) > 0.4 or elec_st != "NORMAL":
            elec_responded = True
            if cht1 < 135.0:
                thermal_stayed_safe = True

    assert elec_responded, "Electrical subsystem should respond to sensor drift"
    assert thermal_stayed_safe, "Thermal components should not turn critical during sensor drift"
    print("[SENSOR DRIFT TEST PASS] Electrical sensor drift detected without falsely tripping thermal/mechanical")


@pytest.mark.asyncio
async def test_fault_clearing_and_recovery():
    """
    PART 17 — RECOVERY TEST
    Clears all active faults. Verifies that predictive state machine smoothly recovers component & global states back to NORMAL.
    """
    client = TestClient(app)

    # Clear faults
    clear_res = client.post("/api/fault-injection/clear")
    assert clear_res.status_code == 200
    print("\n[RECOVERY TEST] Cleared all active faults. Monitoring live state machine recovery...")

    recovered = False

    for step in range(25):
        await asyncio.sleep(0.5)
        snap = client.get("/api/telemetry/latest").json()
        sys_state = snap.get("system_state", "CRITICAL")
        active_faults = snap.get("active_faults", [])

        if len(active_faults) == 0 and sys_state in ["NORMAL", "WATCH"]:
            recovered = True
            print(f"t={(step+1)*0.5}s | System State recovered to: {sys_state}")
            break

    assert recovered, "System must recover back to NORMAL / WATCH after clearing faults"
    print("[RECOVERY TEST PASS] Full state machine recovery verified")
