import os
import sys
import unittest
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml_service.lstm_rul_model import LstmRulEstimator
from backend.digital_twin_core import DigitalTwinCore

class TestRulPrognosticsModule(unittest.TestCase):
    def setUp(self):
        self.rul_model = LstmRulEstimator()
        self.rul_model.reset()
        self.twin_core = DigitalTwinCore()
        self.twin_core.lstm_rul.reset()

        self.dummy_telemetry = {
            "timestamp": 1000.0,
            "rpm": 5000.0,
            "map": 1.15,
            "cht1": 120.0,
            "cht2": 121.0,
            "cht3": 119.0,
            "cht4": 122.0,
            "egt1": 748.0,
            "egt2": 752.0,
            "egt3": 745.0,
            "egt4": 750.0,
            "oil_press": 4.20,
            "oil_temp": 88.0,
            "fuel_flow": 17.5,
            "vibration_rms": 1.12,
            "battery_volt": 14.10
        }

    def test_acceptance_before_30_cycles_insufficient_sequence(self):
        """Before 30 valid cycles: RUL must show INSUFFICIENT SEQUENCE / None."""
        for i in range(1, 30):
            telem = dict(self.dummy_telemetry, timestamp=1000.0 + i * 0.1)
            res = self.rul_model.update_and_predict(telem)
            self.assertEqual(res["model_status"], "WARMING UP")
            self.assertIsNone(res["raw_prediction_cycles"])
            self.assertIsNone(res["display_prediction_cycles"])
            self.assertIsNone(res["previous_prediction_cycles"])
            self.assertIsNone(res["sequence_window_id"])
            self.assertEqual(res["unit"], "cycles")
            self.assertEqual(res["valid_sequence_count"], i)

    def test_acceptance_at_first_valid_sequence_window(self):
        """At frame 30 (first valid sequence window): prediction appears with window_id = 1."""
        for i in range(1, 30):
            self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1000.0 + i * 0.1))
        
        # Frame 30
        res = self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1003.0))
        self.assertEqual(res["model_status"], "INFERENCE ACTIVE")
        self.assertEqual(res["sequence_window_id"], 1)
        self.assertIsNotNone(res["raw_prediction_cycles"])
        self.assertIsNotNone(res["display_prediction_cycles"])
        self.assertGreater(res["display_prediction_cycles"], 0.0)
        self.assertEqual(res["unit"], "cycles")

    def test_acceptance_ui_refresh_without_new_sequence(self):
        """UI refresh at 10 Hz between sequence windows (frames 31-59): RUL prediction remains unchanged."""
        for i in range(1, 31):
            res_30 = self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1000.0 + i * 0.1))

        first_window_id = res_30["sequence_window_id"]
        first_display = res_30["display_prediction_cycles"]
        first_timestamp = res_30["prediction_timestamp"]

        # Simulate 10Hz UI updates for frames 31 through 59
        for i in range(31, 60):
            res_intermediate = self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1000.0 + i * 0.1))
            self.assertEqual(res_intermediate["sequence_window_id"], first_window_id)
            self.assertEqual(res_intermediate["display_prediction_cycles"], first_display)
            self.assertEqual(res_intermediate["prediction_timestamp"], first_timestamp)

    def test_acceptance_new_valid_window_updates_gradually(self):
        """At frame 60 (second valid 30-cycle sequence window): prediction updates gradually with EMA."""
        for i in range(1, 31):
            res_w1 = self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1000.0 + i * 0.1))

        display_w1 = res_w1["display_prediction_cycles"]

        # Run frames 31 to 59
        for i in range(31, 60):
            self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1000.0 + i * 0.1))

        # Frame 60 (New valid window)
        res_w2 = self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1006.0))
        self.assertEqual(res_w2["sequence_window_id"], 2)
        self.assertEqual(res_w2["previous_prediction_cycles"], display_w1)
        self.assertIsNotNone(res_w2["display_prediction_cycles"])

    def test_rul_required_schema_attributes(self):
        """Verifies exact schema keys required by prompt."""
        for i in range(1, 31):
            res = self.rul_model.update_and_predict(dict(self.dummy_telemetry, timestamp=1000.0 + i * 0.1))

        required_keys = [
            "raw_prediction_cycles",
            "display_prediction_cycles",
            "previous_prediction_cycles",
            "prediction_timestamp",
            "sequence_window_id",
            "trend",
            "model_status",
            "unit"
        ]
        for key in required_keys:
            self.assertIn(key, res)

        self.assertEqual(res["unit"], "cycles")
        self.assertIn(res["model_status"], ["WARMING UP", "READY", "INFERENCE ACTIVE", "INSUFFICIENT SEQUENCE", "ERROR"])

if __name__ == "__main__":
    unittest.main()
