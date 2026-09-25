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

class TestFaultPhysicsVerification(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        simulator_instance.reset()
        digital_twin_core_instance.reset()

    def test_fault_physics_pipeline_acceptance(self):
        # Authenticate
        login_res = self.client.post("/api/auth/login", json={"username": "engineer", "password": "engineer123"})
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Start Cruise Nominal Mode
        simulator_instance.set_mission_profile("CRUISE")

        # 2. Capture baseline values
        raw = simulator_instance.get_next_frame()
        snap = digital_twin_core_instance.process_telemetry_frame(raw)
        base_t = snap["telemetry"]
        
        base_cht1 = base_t["cht1"]
        base_cht2 = base_t["cht2"]
        base_cht3 = base_t["cht3"]
        base_cht4 = base_t["cht4"]
        base_thermal_health = snap["subsystem_health"]["thermal"]
        base_anomaly = snap["anomaly_score"]

        # 3. Start Cylinder Thermal Degradation (Cylinder 1, Gradual, 60s ramp, 100% intensity)
        start_res = self.client.post("/api/fault-injection/start", json={
            "scenario": "CYLINDER_THERMAL",
            "component": "CYLINDER_1",
            "profile": "GRADUAL",
            "intensity": 1.0,
            "rate": "SLOW"
        }, headers=headers)
        self.assertEqual(start_res.status_code, 200)

        # Immediate verification: active_faults becomes non-empty
        raw_first = simulator_instance.get_next_frame()
        snap_first = digital_twin_core_instance.process_telemetry_frame(raw_first)
        active_faults_start = snap_first.get("active_faults", [])
        self.assertGreater(len(active_faults_start), 0)
        self.assertEqual(active_faults_start[0]["component"], "CYLINDER_1")

        # Immediate verification: event log shows started fault
        log_res = self.client.get("/api/fault-injection/event-log", headers=headers)
        self.assertEqual(log_res.status_code, 200)
        event_log = log_res.json()["event_log"]
        self.assertGreater(len(event_log), 0)

        # 4. Sample every 5 seconds for 30 seconds (300 frames @ 10Hz)
        samples = []
        for i in range(1, 301):
            raw_f = simulator_instance.get_next_frame()
            snap_f = digital_twin_core_instance.process_telemetry_frame(raw_f)

            if i % 50 == 0: # Every 5.0 seconds
                t_sec = i * 0.1
                telem = snap_f["telemetry"]
                af = snap_f.get("active_faults", [])[0] if snap_f.get("active_faults") else {}
                effect = af.get("current_effect", 0.0)
                cht1 = telem["cht1"]
                cht2 = telem["cht2"]
                cht_res = snap_f["residuals_table"]["avg_cht"]["residual"]
                t_health = snap_f["subsystem_health"]["thermal"]
                a_score = snap_f["anomaly_score"]

                samples.append({
                    "time": t_sec,
                    "effect": effect,
                    "cht1": cht1,
                    "cht2": cht2,
                    "cht_res": cht_res,
                    "t_health": t_health,
                    "a_score": a_score
                })

        print("\n--- TIME SERIES SAMPLING ---")
        print(f"{'Time (s)':<8} | {'Current Effect':<15} | {'CHT1 (°C)':<10} | {'CHT2 (°C)':<10} | {'Physics Residual CHT1 (°C)':<26} | {'Thermal Health (%)':<20} | {'Anomaly Score':<15}")
        print("-" * 120)
        for s in samples:
            print(f"{s['time']:<8.1f} | {s['effect']:<15.3f} | {s['cht1']:<10.1f} | {s['cht2']:<10.1f} | {s['cht_res']:<26.1f} | {s['t_health']:<20.1f} | {s['a_score']:<15.3f}")

        # Assert CHT1 changes progressively
        self.assertGreater(samples[-1]["cht1"], samples[0]["cht1"] + 15.0)
        # Assert CHT2 does NOT receive identical degradation
        self.assertLess(abs(samples[-1]["cht2"] - base_cht2), 3.0)

        # 5. Pause test
        pause_res = self.client.post("/api/fault-injection/pause", headers=headers)
        self.assertEqual(pause_res.status_code, 200)
        
        # Step 20 frames while paused
        for _ in range(20):
            raw_p = simulator_instance.get_next_frame()
            snap_p = digital_twin_core_instance.process_telemetry_frame(raw_p)
            
        active_paused = snap_p.get("active_faults", [])[0]
        paused_effect = active_paused["current_effect"]
        self.assertTrue(active_paused["paused"])

        # Step another 20 frames and verify effect stopped progressing
        for _ in range(20):
            raw_p2 = simulator_instance.get_next_frame()
            snap_p2 = digital_twin_core_instance.process_telemetry_frame(raw_p2)

        active_paused_2 = snap_p2.get("active_faults", [])[0]
        self.assertEqual(active_paused_2["current_effect"], paused_effect)

        # 6. Resume test
        resume_res = self.client.post("/api/fault-injection/pause", headers=headers) # toggles back to running
        self.assertEqual(resume_res.status_code, 200)
        
        # Step 50 frames while resumed (t_elapsed goes from 30s to 35s out of 60s ramp)
        for _ in range(50):
            raw_r = simulator_instance.get_next_frame()
            snap_r = digital_twin_core_instance.process_telemetry_frame(raw_r)

        active_resumed = snap_r.get("active_faults", [])[0]
        self.assertGreater(active_resumed["current_effect"], paused_effect)

        # 7. Clear test
        clear_res = self.client.post("/api/fault-injection/clear", headers=headers)
        self.assertEqual(clear_res.status_code, 200)

        raw_c = simulator_instance.get_next_frame()
        snap_c = digital_twin_core_instance.process_telemetry_frame(raw_c)
        self.assertEqual(len(snap_c.get("active_faults", [])), 0)

if __name__ == "__main__":
    unittest.main()
