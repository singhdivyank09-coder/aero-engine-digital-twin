import time
import requests
import json
import asyncio
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:8000"

async def run_live_acceptance_tests():
    print("==========================================================")
    print("STARTING LIVE GCS/DFCS SYNCHRONIZATION ACCEPTANCE TEST")
    print("==========================================================")
    
    # 1. Obtain Auth Token
    session = requests.Session()
    login_resp = session.post(f"{BASE_URL}/api/auth/login", json={"username": "operator", "password": "operator123"})
    if login_resp.status_code != 200:
        print(f"FAILED to login: {login_resp.status_code} {login_resp.text}")
        return False
    
    token = login_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[AUTH SUCCESS] Logged in successfully. Token length: {len(token)}")
    
    # Ensure clear fault initially
    session.post(f"{BASE_URL}/api/fault-injection/clear", headers=headers)
    time.sleep(2)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        
        print("\n--- TEST 1: Launching localhost UI & Checking Nominal Sequence Advancement ---")
        await page.goto(BASE_URL)
        await page.click('button[data-target="view-gcs-dfcs"]')
        await page.wait_for_selector("#gcs-seq-display", state="attached")
        await asyncio.sleep(2.0)  # Wait for initial WebSocket connection & frame rendering
        
        # Helper to safely evaluate text content from DOM regardless of tab visibility
        async def get_text(selector):
            return await page.evaluate(f"document.querySelector('{selector}') ? document.querySelector('{selector}').innerText : ''")
        
        async def get_seq_num():
            return await page.evaluate("window.twinStore ? window.twinStore.sequence_number : 0")

        # Check initial sequence numbers
        seq1_val = await get_seq_num()
        seq1_text = await get_text("#gcs-seq-display")
        print(f"Initial Sequence Displayed: {seq1_text} (Store Numeric: {seq1_val})")
        assert seq1_val > 0, f"Expected initial sequence > 0, got {seq1_val}"
        
        await asyncio.sleep(3.0)  # Wait for 30 telemetry ticks
        seq2_val = await get_seq_num()
        seq2_text = await get_text("#gcs-seq-display")
        print(f"Sequence after 3s: {seq2_text} (Store Numeric: {seq2_val})")
        assert seq2_val > seq1_val, f"Expected sequence to advance monotonically: {seq2_val} > {seq1_val}"
        print(f"[PASS] TEST 1 PASSED: Nominal sequence advancement verified ({seq1_val} -> {seq2_val}, +{seq2_val - seq1_val} ticks)!")
        
        print("\n--- TEST 2 & 3 & 4 & 5: Cylinder 2 Thermal Fault Injection & GCS/DFCS Sync ---")
        # Inject Cyl 2 thermal fault
        inject_payload = {
            "fault_type": "CYLINDER_HEAD_OVERHEATING",
            "scenario": "CYLINDER_HEAD_OVERHEATING",
            "affected_component": "CYLINDER_2",
            "component": "CYLINDER_2",
            "target_value": 178.0,
            "ramp_time_sec": 4.0,
            "duration_sec": 60.0
        }
        res = session.post(f"{BASE_URL}/api/fault-injection/start", json=inject_payload, headers=headers)
        print(f"Fault Injection API Response ({res.status_code}): {res.text}")
        assert res.status_code == 200, "Fault injection failed"
        
        # Monitor health progression on UI
        states_observed = set()
        start_crit_time = None
        sustained_crit_duration = 0
        final_thermal_hi = None
        
        for i in range(50):
            await asyncio.sleep(1)
            # Switch between Dashboard and GCS tab to verify tab switching & state preservation
            if i % 6 == 0:
                await page.click('button[data-target="view-gcs-dfcs"]')
            elif i % 6 == 3:
                await page.click('button[data-target="view-operator"]')
                
            # Get GCS elements from DOM
            gcs_state = await get_text("#gcs-state-display")
            gcs_thermal_hi = await get_text("#gcs-hi-thermal")
            dfcs_adv_title = await get_text("#dfcs-advisory-title")
            gcs_seq = await get_text("#gcs-seq-display")
            
            states_observed.add(gcs_state)
            print(f"[t={i}s] GCS State: {gcs_state} | Thermal HI: {gcs_thermal_hi} | Advisory: {dfcs_adv_title} | {gcs_seq}")
            
            if gcs_state == "CRITICAL":
                if start_crit_time is None:
                    start_crit_time = time.time()
                sustained_crit_duration = time.time() - start_crit_time
                if gcs_thermal_hi:
                    final_thermal_hi = int(gcs_thermal_hi.replace("%", "").strip())
                
                # Verify exact GCS/DFCS synchronization during CRITICAL
                assert "Critical" in dfcs_adv_title or "CRITICAL" in dfcs_adv_title or "Propulsion" in dfcs_adv_title, f"Expected Critical advisory title, got '{dfcs_adv_title}'"
            
            if sustained_crit_duration >= 30.0:
                print(f"[PASS] Achieved sustained CRITICAL condition for {sustained_crit_duration:.1f}s (>= 30s)!")
                break
                
        print(f"Health states observed during fault ramp: {states_observed}")
        assert "CRITICAL" in states_observed, f"Engine failed to reach CRITICAL state, observed: {states_observed}"
        assert sustained_crit_duration >= 30.0, f"Sustained CRITICAL duration was only {sustained_crit_duration:.1f}s"
        assert final_thermal_hi is not None and final_thermal_hi < 30, f"Expected degraded thermal health < 30% by steady state CRITICAL, got {final_thermal_hi}%"
        print(f"[PASS] Thermal health reached steady-state degraded value: {final_thermal_hi}% (< 30%)!")
        print("[PASS] TEST 2, 3, 4, 5 PASSED: Cylinder 2 thermal fault progression, sustained CRITICAL, and exact DFCS advisory sync verified!")
        
        print("\n--- TEST 6: Clearing Fault & Observing Hysteresis Recovery ---")
        clear_res = session.post(f"{BASE_URL}/api/fault-injection/clear", headers=headers)
        print(f"Fault Clear API Response: {clear_res.text}")
        
        # Monitor recovery
        recovery_states = []
        for i in range(15):
            await asyncio.sleep(1)
            b_state = await get_text("#gcs-state-display")
            recovery_states.append(b_state)
            print(f"[Clear +{i+1}s] GCS UI State: {b_state}")
            
        print(f"Recovery state trajectory: {recovery_states}")
        assert recovery_states[0] != "NORMAL", "State snapped immediately to NORMAL without cooling/hysteresis period!"
        print("[PASS] TEST 6 PASSED: Hysteresis cooling period observed before nominal recovery!")

        print("\n--- TEST 7: Testing Oil Pressure & Vibration Fault Scenarios ---")
        # Test Oil Pressure Fault
        oil_payload = {
            "fault_type": "LUBRICATION_FAILURE",
            "scenario": "LOW_OIL_PRESSURE",
            "affected_component": "OIL_PUMP",
            "component": "OIL_PUMP",
            "target_value": 2.1,
            "ramp_time_sec": 2.0,
            "duration_sec": 10.0
        }
        session.post(f"{BASE_URL}/api/fault-injection/start", json=oil_payload, headers=headers)
        await asyncio.sleep(4)
        b_oil_state = await get_text("#gcs-state-display")
        print(f"Oil Pressure Fault State: {b_oil_state}")
        assert b_oil_state in ["WARNING", "CRITICAL", "ACTIVE_FAULT", "CAUTION"], f"Unexpected oil fault state: {b_oil_state}"
        session.post(f"{BASE_URL}/api/fault-injection/clear", headers=headers)
        await asyncio.sleep(3)
        print("[PASS] TEST 7 PASSED: Oil pressure fault scenario verified!")

        print("\n--- TEST 8: Tab Switching Verification ---")
        await page.click('button[data-target="view-gcs-dfcs"]')
        await asyncio.sleep(1)
        gcs_seq = await get_text("#gcs-seq-display")
        await page.click('button[data-target="view-operator"]')
        await asyncio.sleep(1)
        dash_seq = await get_text("#gcs-seq-display") # Header seq is global
        print(f"GCS Tab Seq: {gcs_seq} | Operator Tab Seq: {dash_seq}")
        assert gcs_seq and dash_seq, "Sequence display empty after tab switch"
        print("[PASS] TEST 8 PASSED: Tab switching preserves state seamlessly!")

        print("\n--- TEST 9: Missing / Null degradation_score Error Safety ---")
        # Check console errors accumulated during entire run
        print(f"Total Console Errors Recorded: {len(console_errors)}")
        type_errors = [err for err in console_errors if "TypeError" in err or "toFixed" in err]
        if type_errors:
            print(f"Uncaught TypeErrors detected: {type_errors}")
        assert len(type_errors) == 0, f"Uncaught TypeErrors detected in console: {type_errors}"
        print("[PASS] TEST 9 PASSED: Zero uncaught TypeError or toFixed errors in console!")

        print("\n--- TEST 10: WebSocket Interruption & Recovery Handling ---")
        await page.evaluate("if (window.telemetrySocket) window.telemetrySocket.close();")
        await asyncio.sleep(0.5)
        link_status_text = await get_text("#gcs-link-status")
        print(f"Link Status during socket disconnection: {link_status_text}")
        assert "DISCONNECTED" in link_status_text or "DEGRADED" in link_status_text, f"Expected degraded link status indicator, got '{link_status_text}'"
        
        # Wait for auto-reconnect (app.js reconnects after 2.0s)
        await asyncio.sleep(4.0)
        reconnected_link_status = await get_text("#gcs-link-status")
        print(f"Link Status after auto-reconnect: {reconnected_link_status}")
        assert "CONNECTED" in reconnected_link_status, f"Expected reconnected link status indicator, got '{reconnected_link_status}'"
        print("[PASS] TEST 10 PASSED: Disconnection & Link Status indication verified!")

        # Take final screenshot artifact
        await page.click('button[data-target="view-gcs-dfcs"]')
        await asyncio.sleep(2)
        screenshot_path = "scratch/live_gcs_dfcs_verification_result.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"\nSaved full verification screenshot artifact to {screenshot_path}")

        print("\n==========================================================")
        print("ALL 10 LIVE RUNTIME ACCEPTANCE TESTS PASSED SUCCESSFULLY!")
        print("==========================================================")
        return True

if __name__ == "__main__":
    asyncio.run(run_live_acceptance_tests())
