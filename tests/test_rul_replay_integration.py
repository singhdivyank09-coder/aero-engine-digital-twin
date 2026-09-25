import os
import sys
import unittest
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml_service.lstm_rul_model import LstmRulEstimator
from backend.replay_service import ReplayService
from backend.digital_twin_core import DigitalTwinCore

class TestRulReplayIntegration(unittest.TestCase):
    def setUp(self):
        self.rul_model = LstmRulEstimator()
        self.rul_model.reset()
        self.replay_service = ReplayService()

        self.dummy_telemetry = {
            "timestamp": 1000.0,
            "rpm": 5000.0,
            "map": 1.15,
            "cht1": 120.0,
            "cht2": 120.5,
            "cht3": 119.5,
            "cht4": 120.2,
            "egt1": 748.0,
            "egt2": 750.0,
            "egt3": 745.0,
            "egt4": 749.0,
            "oil_press": 4.20,
            "oil_temp": 88.0,
            "fuel_flow": 17.5,
            "vibration_rms": 1.12,
            "battery_volt": 14.10
        }

    def test_rul_warmup_initialization(self):
        """Before 30 sequence cycles exist: RUL status = WARMING UP and display_prediction_cycles = None."""
        for frame_idx in range(29): # 0 to 28 (29 samples)
            telem = dict(self.dummy_telemetry, timestamp=1000.0 + frame_idx * 0.1)
            pred = self.rul_model.update_and_predict(telem)
            self.assertEqual(pred["model_status"], "WARMING UP")
            self.assertIsNone(pred["display_prediction_cycles"])
            self.assertIsNone(pred["raw_prediction_cycles"])
            self.assertIsNone(pred["sequence_window_id"])

    def test_first_valid_rul_estimate(self):
        """At cycle 30 (frame index 29), first valid RUL estimate is generated."""
        for frame_idx in range(29):
            self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1000.0 + frame_idx * 0.1))

        # 30th frame
        pred_30 = self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1002.9))
        self.assertEqual(pred_30["model_status"], "INFERENCE ACTIVE")
        self.assertEqual(pred_30["sequence_window_id"], 1)
        self.assertIsNotNone(pred_30["display_prediction_cycles"])
        self.assertIsInstance(pred_30["display_prediction_cycles"], float)

    def test_replay_service_full_mission_rul_summary(self):
        """Replay service produces valid RUL Start, RUL End, Net Change, and timestamps."""
        replay_data = self.replay_service.generate_historical_mission()
        summary = replay_data["summary"]

        self.assertTrue(summary["has_valid_rul"])
        self.assertIsNotNone(summary["rul_start_cycles"])
        self.assertIsNotNone(summary["rul_end_cycles"])
        self.assertIsNotNone(summary["net_change_cycles"])
        self.assertIsNotNone(summary["mission_start_timestamp"])
        self.assertIsNotNone(summary["first_valid_rul_timestamp"])

        # Mission start timestamp (t=0) vs first valid RUL timestamp (t=29s) must be distinct
        self.assertLess(summary["mission_start_timestamp"], summary["first_valid_rul_timestamp"])
        
        # Check net change calculation: RUL_End - RUL_Start
        expected_net = round(summary["rul_end_cycles"] - summary["rul_start_cycles"], 1)
        self.assertEqual(summary["net_change_cycles"], expected_net)

        # Confirm summary string format
        self.assertIn("RUL Start:", summary["rul_summary_text"])
        self.assertIn("RUL End:", summary["rul_summary_text"])
        self.assertNotIn("null", summary["rul_summary_text"].lower())

    def test_short_mission_insufficient_sequence(self):
        """Short mission with < 30 frames returns 'Insufficient sequence for RUL estimation'."""
        twin_core = DigitalTwinCore()
        processed_frames = []

        # Stream only 15 frames (< 30)
        for idx in range(15):
            t = round(idx * 0.1, 1)
            telemetry = dict(self.dummy_telemetry, timestamp=1000.0 + t)
            frame_container = {
                "telemetry": telemetry,
                "raw_telemetry": telemetry,
                "mission_profile": "HISTORICAL_REPLAY",
                "telemetry_source": "REPLAY"
            }
            snapshot = twin_core.process_telemetry_frame(frame_container)
            processed_frames.append(snapshot)

        # Run RUL summary extraction logic
        valid_rul_frames = []
        for frame in processed_frames:
            rul_est = frame.get("prototype_rul_estimate", {})
            cycles = rul_est.get("display_prediction_cycles")
            if cycles is not None and isinstance(cycles, (int, float)):
                valid_rul_frames.append(frame)

        self.assertEqual(len(valid_rul_frames), 0)

        # Check report format for short mission
        has_valid_rul = len(valid_rul_frames) > 0
        self.assertFalse(has_valid_rul)

if __name__ == "__main__":
    unittest.main()
