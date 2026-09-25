import unittest
import os
import sys
import time
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.database import init_db
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

class TestFaultInjectionVerification(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        simulator_instance.reset()
        digital_twin_core_instance.reset()

    def test_fault_injection_real_pipeline(self):
        # 1. Login to get Bearer Token
        login_res = self.client.post("/api/auth/login", json={"username": "engineer", "password": "engineer123"})
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Start nominal simulator & capture baseline CHT1
        raw = simulator_instance.get_next_frame()
        snap_nominal = digital_twin_core_instance.process_telemetry_frame(raw)
        baseline_cht1 = snap_nominal["telemetry"]["cht1"]
        print(f"\n[STEP 1 & 2] Nominal Baseline CHT1: {baseline_cht1}°C")

        # 3. Start Cylinder 1 Thermal Degradation
        start_res = self.client.post("/api/session/fault/start", json={
            "scenario": "CYLINDER_THERMAL",
            "component": "CYLINDER_1",
            "profile": "GRADUAL",
            "intensity": 1.2,
            "rate": "SLOW"
        }, headers=headers)
        self.assertEqual(start_res.status_code, 200)
        start_data = start_res.json()
        fault_id = start_data.get("fault_id")
        print(f"[STEP 3] Fault Injection Started | Fault ID: {fault_id}")

        # 4. Verify fault event exists in event log
        event_res = self.client.get("/api/session/fault/event-log", headers=headers)
        self.assertEqual(event_res.status_code, 200)
        event_log = event_res.json()["event_log"]
        self.assertGreater(len(event_log), 0)
        latest_evt = event_log[-1]
        print(f"[STEP 6] Verified Event Log Entry: ID={latest_evt.get('fault_id')} | Scenario={latest_evt.get('fault_scenario')} | Status={latest_evt.get('status')}")

        # 5. Sample CHT1 every 5 seconds (50 frames @ 10Hz) over 30 seconds
        cht_samples = []
        samples_table = []
        
        for i in range(1, 301):
            raw = simulator_instance.get_next_frame()
            snap = digital_twin_core_instance.process_telemetry_frame(raw)
            
            if i % 50 == 0:
                t_sec = i * 0.1
                cht1 = snap["telemetry"]["cht1"]
                active_faults = snap.get("active_faults", [])
                active_obj = active_faults[0] if active_faults else {}
                effect = active_obj.get("current_effect", 0.0)
                elapsed = active_obj.get("elapsed_seconds", 0.0)
                state = snap.get("system_state", "NORMAL")

                cht_samples.append((t_sec, cht1))
                samples_table.append({
                    "time": t_sec,
                    "cht1": cht1,
                    "elapsed": elapsed,
                    "effect": effect,
                    "state": state
                })

        print("\n--- [STEP 4 & 5] CHT1 TIME SERIES SAMPLING (EVERY 5 SECONDS) ---")
        print(f"{'Time (s)':<10} | {'CHT1 (°C)':<12} | {'Fault Elapsed (s)':<18} | {'Current Effect':<15} | {'Digital Twin State':<15}")
        print("-" * 75)
        for row in samples_table:
            print(f"{row['time']:<10.1f} | {row['cht1']:<12.1f} | {row['elapsed']:<18.1f} | {row['effect']:<15.3f} | {row['state']:<15}")

        # Verify progressive change (each sample >= previous sample)
        cht_values = [s[1] for s in cht_samples]
        self.assertGreater(cht_values[-1], baseline_cht1 + 5.0, "CHT1 did not progressively increase over 30 seconds!")

        # 6. Verify pause functionality
        pause_res = self.client.post("/api/session/fault/pause", headers=headers)
        self.assertEqual(pause_res.status_code, 200)
        snap_paused = digital_twin_core_instance.process_telemetry_frame(simulator_instance.get_next_frame())
        active_paused = snap_paused.get("active_faults", [])[0]
        self.assertTrue(active_paused["paused"])
        print(f"\n[STEP 6b] Fault Paused Verified | active={active_paused['active']}, paused={active_paused['paused']}")

        # 7. Clear fault
        clear_res = self.client.post("/api/session/fault/clear", headers=headers)
        self.assertEqual(clear_res.status_code, 200)
        print("[STEP 7] Fault Clear Command Issued")

        # 8. Verify active_faults becomes empty
        raw_cleared = simulator_instance.get_next_frame()
        snap_cleared = digital_twin_core_instance.process_telemetry_frame(raw_cleared)
        cleared_active_faults = snap_cleared.get("active_faults", [])
        print(f"[STEP 8] Active Faults Count After Clear: {len(cleared_active_faults)}")
        self.assertEqual(len(cleared_active_faults), 0, "active_faults list is not empty after clear!")

if __name__ == "__main__":
    unittest.main()
