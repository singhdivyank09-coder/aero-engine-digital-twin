import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.metrics_tracker import RuntimeMetricsTracker, metrics_tracker_instance
from backend.digital_twin_core import DigitalTwinCore
from backend.telemetry_simulator import TelemetrySimulator

class TestDataIntegrityInstrumentation(unittest.TestCase):
    def setUp(self):
        # Reset metrics tracker state for test isolation
        metrics_tracker_instance.reset()

        self.twin_core = DigitalTwinCore()
        self.simulator = TelemetrySimulator()

        self.valid_telemetry = {
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

    def test_zero_ingested_frames_returns_null_and_not_available(self):
        """When total_ingested_frames == 0, data_integrity_rate_pct is None (null) and status is NOT AVAILABLE."""
        summary = metrics_tracker_instance.get_summary()
        self.assertEqual(summary["total_ingested_frames"], 0)
        self.assertEqual(summary["dropped_invalid_frames"], 0)
        self.assertIsNone(summary["data_integrity_rate_pct"])
        self.assertIn(summary["data_integrity_status"], ["AWAITING DATA", "NOT AVAILABLE"])
        self.assertIn(summary["data_integrity_text"].upper(), ["AWAITING TELEMETRY", "AWAITING DATA"])

    def test_canonical_ingestion_path_increments_counter(self):
        """Each frame processed by DigitalTwinCore increments total_ingested_frames."""
        for i in range(10):
            frame = dict(self.valid_telemetry, timestamp=1000.0 + i * 0.1)
            self.twin_core.process_telemetry_frame({"telemetry": frame})

        summary = metrics_tracker_instance.get_summary()
        self.assertEqual(summary["total_ingested_frames"], 10)
        self.assertEqual(summary["valid_ingested_frames"], 10)
        self.assertEqual(summary["dropped_invalid_frames"], 0)
        self.assertEqual(summary["data_integrity_rate_pct"], 100.0)
        self.assertEqual(summary["data_integrity_status"], "MEASURED")

    def test_simulator_telemetry_goes_through_same_counter_path(self):
        """Simulator-generated frames processed by DigitalTwinCore update the exact same ingestion counters."""
        # Simulate 10 seconds of 10 Hz telemetry (100 frames)
        for i in range(100):
            raw_frame = self.simulator.get_next_frame()
            self.twin_core.process_telemetry_frame(raw_frame)

        summary = metrics_tracker_instance.get_summary()
        self.assertEqual(summary["total_ingested_frames"], 100)
        self.assertGreaterEqual(summary["valid_ingested_frames"], 98) # All or nearly all valid
        self.assertEqual(summary["data_integrity_status"], "MEASURED")
        self.assertIsNotNone(summary["data_integrity_rate_pct"])

    def test_invalid_frame_increments_invalid_counter_and_calculates_integrity_rate(self):
        """Invalid frame increments dropped_invalid_frames and correctly calculates integrity rate."""
        # 3 valid frames
        for i in range(3):
            frame = dict(self.valid_telemetry, timestamp=1000.0 + i * 0.1)
            self.twin_core.process_telemetry_frame({"telemetry": frame})

        # 1 invalid frame (corrupted RPM out of range)
        bad_frame = dict(self.valid_telemetry, timestamp=1000.3, rpm=99999.0)
        self.twin_core.process_telemetry_frame({"telemetry": bad_frame})

        summary = metrics_tracker_instance.get_summary()
        self.assertEqual(summary["total_ingested_frames"], 4)
        self.assertEqual(summary["valid_ingested_frames"], 3)
        self.assertEqual(summary["dropped_invalid_frames"], 1)
        self.assertEqual(summary["data_integrity_rate_pct"], 75.0) # (3 / 4) * 100

if __name__ == "__main__":
    unittest.main()
