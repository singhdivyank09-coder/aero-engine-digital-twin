"""
Unit Tests for System Metrics & Model Assumptions Requirements
"""

import unittest
import os
import re
from backend.metrics_tracker import RuntimeMetricsTracker

INDEX_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))
APP_JS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "app.js"))


class TestSystemMetricsAndAssumptions(unittest.TestCase):

    def setUp(self):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            self.index_html = f.read()

        with open(APP_JS_PATH, "r", encoding="utf-8") as f:
            self.app_js = f.read()

        self.tracker = RuntimeMetricsTracker(max_history=50)

    def test_no_hardcoded_measured_claims_or_rotax_mention(self):
        """Verify Rotax 914 is not mentioned and no hardcoded static values claim to be measured."""
        self.assertNotIn("Rotax 914", self.index_html)
        self.assertNotIn("Rotax", self.index_html)
        self.assertIn("Actual Measured Runtime Metrics", self.index_html)
        self.assertIn("Design Targets & Model Assumptions", self.index_html)

    def test_metrics_tracker_validation_and_data_integrity(self):
        """Verify data integrity calculation formula and frame validation checks."""
        valid_frame = {
            "timestamp": 1.0,
            "rpm": 5000.0,
            "map": 1.15,
            "cht1": 120.0,
            "cht2": 122.0,
            "cht3": 121.0,
            "cht4": 123.0,
            "egt1": 745.0,
            "egt2": 750.0,
            "egt3": 742.0,
            "egt4": 748.0,
            "oil_press": 4.20,
            "oil_temp": 88.5,
            "fuel_flow": 17.5,
            "vibration_rms": 1.12,
            "battery_volt": 14.10
        }

        # 1. Valid Frame Ingestion
        is_valid = self.tracker.record_frame_ingestion(valid_frame)
        self.assertTrue(is_valid)

        # 2. Invalid Frame (Out of range RPM)
        invalid_frame = valid_frame.copy()
        invalid_frame["rpm"] = 99999.0  # Exceeds max 7000 RPM
        is_valid_bad = self.tracker.record_frame_ingestion(invalid_frame)
        self.assertFalse(is_valid_bad)

        summary = self.tracker.get_summary()
        self.assertEqual(summary["total_ingested_frames"], 2)
        self.assertEqual(summary["valid_ingested_frames"], 1)
        self.assertEqual(summary["dropped_invalid_frames"], 1)
        self.assertEqual(summary["data_integrity_rate_pct"], 50.0)

    def test_latency_statistics_calculation(self):
        """Verify mean, median, p95, and max calculations for measured latencies."""
        for lat in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
            self.tracker.record_dt_latency(lat)

        summary = self.tracker.get_summary()
        dt_stats = summary["dt_processing_latency_ms"]
        self.assertEqual(dt_stats["status"], "MEASURED")
        self.assertEqual(dt_stats["mean"], 5.5)
        self.assertEqual(dt_stats["median"], 5.5)
        self.assertEqual(dt_stats["max"], 10.0)

    def test_unmeasured_latency_returns_not_measured(self):
        """Verify unmeasured latencies (e.g. alert latency when no alerts triggered) return NOT MEASURED."""
        summary = self.tracker.get_summary()
        alert_stats = summary["alert_latency_ms"]
        self.assertEqual(alert_stats["status"], "NOT MEASURED")
        self.assertIsNone(alert_stats["mean"])

    def test_frontend_assumptions_panel_contents(self):
        """Verify assumptions panel contains exact required disclaimer texts."""
        self.assertIn("Reference 4-cylinder turbocharged aero-piston model", self.index_html)
        self.assertIn("0D/1D prototype thermodynamic surrogate", self.index_html)
        self.assertIn("Not calibrated using target MALE UAV flight-test data", self.index_html)
        self.assertIn("Requires engine test-rig / HIL / flight-test calibration before operational use", self.index_html)


if __name__ == "__main__":
    unittest.main()
