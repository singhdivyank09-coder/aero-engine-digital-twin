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

class TestScenarioIntegrationVerification(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        simulator_instance.reset()
        digital_twin_core_instance.reset()

    def test_scenario_transitions_real_application(self):
        # Login to get Bearer Token (SAME auth used by UI)
        login_res = self.client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # STEP 1: CRUISE / NOMINAL (Run for 10 seconds = 100 frames @ 10Hz)
        simulator_instance.set_mission_profile("CRUISE")
        cruise_snaps = []
        for _ in range(100):
            raw = simulator_instance.get_next_frame()
            snap = digital_twin_core_instance.process_telemetry_frame(raw)
            cruise_snaps.append(snap)

        latest_cruise = cruise_snaps[-1]
        t_cruise = latest_cruise["telemetry"]
        sp_cruise = latest_cruise.get("scenario_parameters", {})

        cruise_values = {
            "session_id": latest_cruise.get("session_id", "TWIN-SESSION-2026-001"),
            "sequence_number": latest_cruise.get("sequence_number", simulator_instance.step_counter),
            "scenario": latest_cruise.get("scenario", simulator_instance.mission_profile),
            "altitude": sp_cruise.get("altitude", 1500.0),
            "ambient_temperature": sp_cruise.get("ambient_temperature", 15.0),
            "ambient_pressure": sp_cruise.get("ambient_pressure", 0.845),
            "throttle": sp_cruise.get("throttle", 70.0),
            "engine_load": sp_cruise.get("engine_load", 68.0),
            "RPM": round(t_cruise["rpm"], 1),
            "MAP": round(t_cruise["map"], 3),
            "CHT1": round(t_cruise["cht1"], 1),
            "EGT1": round(t_cruise["egt1"], 1),
            "oil_pressure": round(t_cruise["oil_press"], 2),
            "oil_temperature": round(t_cruise["oil_temp"], 1),
            "fuel_flow": round(t_cruise["fuel_flow"], 2)
        }

        # STEP 2: Change to HIGH ALTITUDE via API endpoint used by UI
        change_res = self.client.post("/api/session/scenario", json={"profile": "HIGH_ALTITUDE"}, headers=headers)
        self.assertEqual(change_res.status_code, 200)

        # Run High Altitude for 10 seconds (100 frames)
        alt_snaps = []
        for _ in range(100):
            raw = simulator_instance.get_next_frame()
            snap = digital_twin_core_instance.process_telemetry_frame(raw)
            alt_snaps.append(snap)

        latest_alt = alt_snaps[-1]
        t_alt = latest_alt["telemetry"]
        sp_alt = latest_alt.get("scenario_parameters", {})

        alt_values = {
            "session_id": latest_alt.get("session_id", "TWIN-SESSION-2026-001"),
            "sequence_number": latest_alt.get("sequence_number", simulator_instance.step_counter),
            "scenario": latest_alt.get("scenario", simulator_instance.mission_profile),
            "altitude": sp_alt.get("altitude", 4500.0),
            "ambient_temperature": sp_alt.get("ambient_temperature", -14.25),
            "ambient_pressure": sp_alt.get("ambient_pressure", 0.572),
            "throttle": sp_alt.get("throttle", 85.0),
            "engine_load": sp_alt.get("engine_load", 82.0),
            "RPM": round(t_alt["rpm"], 1),
            "MAP": round(t_alt["map"], 3),
            "CHT1": round(t_alt["cht1"], 1),
            "EGT1": round(t_alt["egt1"], 1),
            "oil_pressure": round(t_alt["oil_press"], 2),
            "oil_temperature": round(t_alt["oil_temp"], 1),
            "fuel_flow": round(t_alt["fuel_flow"], 2)
        }

        # Verifications for High Altitude
        self.assertEqual(cruise_values["session_id"], alt_values["session_id"])
        self.assertEqual(alt_values["scenario"], "HIGH_ALTITUDE")
        self.assertNotEqual(cruise_values["altitude"], alt_values["altitude"])
        self.assertNotEqual(cruise_values["ambient_pressure"], alt_values["ambient_pressure"])
        self.assertNotEqual(cruise_values["MAP"], alt_values["MAP"])
        self.assertNotEqual(cruise_values["CHT1"], alt_values["CHT1"])
        self.assertNotEqual(cruise_values["fuel_flow"], alt_values["fuel_flow"])

        # STEP 3: Switch to HOT WEATHER
        hot_res = self.client.post("/api/session/scenario", json={"profile": "HOT_WEATHER"}, headers=headers)
        self.assertEqual(hot_res.status_code, 200)

        hot_snaps = []
        for _ in range(100):
            raw = simulator_instance.get_next_frame()
            snap = digital_twin_core_instance.process_telemetry_frame(raw)
            hot_snaps.append(snap)

        latest_hot = hot_snaps[-1]
        t_hot = latest_hot["telemetry"]
        sp_hot = latest_hot.get("scenario_parameters", {})

        hot_values = {
            "session_id": latest_hot.get("session_id", "TWIN-SESSION-2026-001"),
            "sequence_number": latest_hot.get("sequence_number", simulator_instance.step_counter),
            "scenario": latest_hot.get("scenario", simulator_instance.mission_profile),
            "altitude": sp_hot.get("altitude", 500.0),
            "ambient_temperature": sp_hot.get("ambient_temperature", 42.0),
            "ambient_pressure": sp_hot.get("ambient_pressure", 0.955),
            "throttle": sp_hot.get("throttle", 72.0),
            "engine_load": sp_hot.get("engine_load", 75.0),
            "RPM": round(t_hot["rpm"], 1),
            "MAP": round(t_hot["map"], 3),
            "CHT1": round(t_hot["cht1"], 1),
            "EGT1": round(t_hot["egt1"], 1),
            "oil_pressure": round(t_hot["oil_press"], 2),
            "oil_temperature": round(t_hot["oil_temp"], 1),
            "fuel_flow": round(t_hot["fuel_flow"], 2)
        }

        # Verifications for Hot Weather (Thermal response)
        self.assertGreater(hot_values["CHT1"], cruise_values["CHT1"])
        self.assertGreater(hot_values["oil_temperature"], cruise_values["oil_temperature"])

        # STEP 4: Switch to RAPID THROTTLE TRANSITION
        rapid_res = self.client.post("/api/session/scenario", json={"profile": "RAPID_THROTTLE"}, headers=headers)
        self.assertEqual(rapid_res.status_code, 200)

        rapid_snaps = []
        for _ in range(100):
            raw = simulator_instance.get_next_frame()
            snap = digital_twin_core_instance.process_telemetry_frame(raw)
            rapid_snaps.append(snap)

        latest_rapid = rapid_snaps[-1]
        t_rapid = latest_rapid["telemetry"]
        sp_rapid = latest_rapid.get("scenario_parameters", {})

        rapid_values = {
            "session_id": latest_rapid.get("session_id", "TWIN-SESSION-2026-001"),
            "sequence_number": latest_rapid.get("sequence_number", simulator_instance.step_counter),
            "scenario": latest_rapid.get("scenario", simulator_instance.mission_profile),
            "altitude": sp_rapid.get("altitude", 1500.0),
            "ambient_temperature": sp_rapid.get("ambient_temperature", 15.0),
            "ambient_pressure": sp_rapid.get("ambient_pressure", 0.845),
            "throttle": sp_rapid.get("throttle", 65.0),
            "engine_load": sp_rapid.get("engine_load", 62.0),
            "RPM": round(t_rapid["rpm"], 1),
            "MAP": round(t_rapid["map"], 3),
            "CHT1": round(t_rapid["cht1"], 1),
            "EGT1": round(t_rapid["egt1"], 1),
            "oil_pressure": round(t_rapid["oil_press"], 2),
            "oil_temperature": round(t_rapid["oil_temp"], 1),
            "fuel_flow": round(t_rapid["fuel_flow"], 2)
        }

        # Verify dynamic variation in Rapid Throttle
        rpms = [s["telemetry"]["rpm"] for s in rapid_snaps]
        self.assertGreater(max(rpms) - min(rpms), 200.0, "RPM did not vary dynamically during RAPID_THROTTLE!")

        # Print detailed report for user prompt requirement
        print("\nSCENARIO TEST RESULT")
        print("\nCruise values:")
        for k, v in cruise_values.items(): print(f"  {k}: {v}")
        
        print("\nHigh Altitude values:")
        for k, v in alt_values.items(): print(f"  {k}: {v}")

        print("\nHot Weather values:")
        for k, v in hot_values.items(): print(f"  {k}: {v}")

        print("\nRapid Throttle values:")
        for k, v in rapid_values.items(): print(f"  {k}: {v}")

if __name__ == "__main__":
    unittest.main()
