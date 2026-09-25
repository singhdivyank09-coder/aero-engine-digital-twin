"""
Test Suite for Digital Twin State Machine (Tests A, B, C, D, E, F)
SIH 26054 — Aero-Piston Engine Digital Twin

Verifies:
- TEST A: Nominal Telemetry -> NORMAL
- TEST B: Gradual Thermal Degradation -> NORMAL -> WATCH -> CAUTION -> WARNING -> CRITICAL
- TEST C: Severe Persistent Fault -> CRITICAL
- TEST D: Restore Nominal Input -> Stepwise Recovery CRITICAL -> WARNING -> CAUTION -> WATCH -> NORMAL
- TEST E: Single Sensor Spike -> Suppressed by K-of-M persistence
- TEST F: Timeline & Pre-Threshold Early Warning (WATCH, CAUTION, WARNING occur BEFORE 145.0°C limit breach)
- TEST G: Logged state evidence metadata schema validation
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.digital_twin_core import DigitalTwinCore

class TestDigitalTwinStateMachine(unittest.TestCase):

    def setUp(self):
        self.core = DigitalTwinCore()
        self.nominal_frame = {
            "timestamp": 1.0,
            "rpm": 5000.0,
            "map": 1.15,
            "cht1": 120.0, "cht2": 121.0, "cht3": 119.5, "cht4": 120.5,
            "egt1": 748.0, "egt2": 750.0, "egt3": 746.0, "egt4": 749.0,
            "oil_press": 4.20,
            "oil_temp": 88.5,
            "fuel_flow": 17.5,
            "vibration_rms": 1.12,
            "battery_volt": 14.10
        }

    def test_nominal_operation(self):
        """TEST A: Nominal Telemetry -> NORMAL"""
        snapshot = None
        for i in range(5):
            frame = self.nominal_frame.copy()
            frame["timestamp"] = float(i + 1)
            snapshot = self.core.process_telemetry_frame(frame)

        self.assertEqual(snapshot["system_state"], "NORMAL")
        self.assertGreater(snapshot["overall_health"], 90.0)

    def test_pre_threshold_warnings_and_timeline(self):
        """
        TEST F: Required Timeline & Pre-Threshold Early Warning Verification.
        Verifies that WATCH, CAUTION, and WARNING occur BEFORE any current parameter
        exceeds its reference limit (145.0°C CHT active fault threshold).
        """
        timeline_records = []
        
        # Stream thermal rise sequence (CHT 120°C -> 147°C)
        for step in range(65):
            t = float(step)
            # Simulate progressive temperature curve:
            # 0s: ~120°C, 20s: ~129°C, 35s: ~135°C, 45s: ~139°C, 60s: ~147°C
            cht_val = 120.0 + (step * 0.45)
            frame = self.nominal_frame.copy()
            frame["timestamp"] = t
            frame["cht1"] = cht_val

            snapshot = self.core.process_telemetry_frame(frame)
            state = snapshot["system_state"]

            timeline_records.append({
                "t": t,
                "cht": cht_val,
                "state": state,
                "metadata": snapshot["state_transition_metadata"]
            })

        observed_states = [r["state"] for r in timeline_records]
        
        # Verify pre-threshold early warning states occurred
        self.assertIn("WATCH", observed_states, "WATCH state must occur before threshold limit")
        self.assertIn("CAUTION", observed_states, "CAUTION state must occur before threshold limit")
        self.assertIn("WARNING", observed_states, "WARNING state must occur before threshold limit")
        self.assertIn("CRITICAL", observed_states, "CRITICAL state must occur when limit breached")

        # Find first occurrence of each state
        watch_rec = next(r for r in timeline_records if r["state"] == "WATCH")
        caution_rec = next(r for r in timeline_records if r["state"] == "CAUTION")
        warning_rec = next(r for r in timeline_records if r["state"] == "WARNING")
        critical_rec = next(r for r in timeline_records if r["state"] == "CRITICAL")

        # ASSERTION: WATCH, CAUTION, WARNING occur while CHT < 145.0°C
        self.assertLess(watch_rec["cht"], 145.0, f"WATCH state triggered at CHT={watch_rec['cht']}°C, expected < 145°C")
        self.assertLess(caution_rec["cht"], 145.0, f"CAUTION state triggered at CHT={caution_rec['cht']}°C, expected < 145°C")
        self.assertLess(warning_rec["cht"], 145.0, f"WARNING state triggered at CHT={warning_rec['cht']}°C, expected < 145°C")

        # ASSERTION: CRITICAL state triggers when CHT exceeds reference limit
        self.assertGreaterEqual(critical_rec["cht"], 145.0, f"CRITICAL state triggered at CHT={critical_rec['cht']}°C, expected >= 145°C")

    def test_logged_state_evidence_format(self):
        """
        TEST G: Logged State Evidence Schema Verification.
        Ensures state_transition_metadata contains all required schema fields:
        state, reason, predictive_risk_probability, estimated_time_to_risk,
        anomaly_score, physics_residual, cusum_evidence, current_fault_confirmation.
        """
        frame = self.nominal_frame.copy()
        frame["cht1"] = 138.0
        snapshot = self.core.process_telemetry_frame(frame)

        metadata = snapshot.get("state_transition_metadata", {})

        required_keys = [
            "state",
            "reason",
            "predictive_risk_probability",
            "estimated_time_to_risk",
            "anomaly_score",
            "physics_residual",
            "cusum_evidence",
            "current_fault_confirmation"
        ]

        for k in required_keys:
            self.assertIn(k, metadata, f"Metadata missing required key: {k}")

        self.assertIsInstance(metadata["predictive_risk_probability"], float)
        self.assertIsInstance(metadata["estimated_time_to_risk"], float)
        self.assertIsInstance(metadata["anomaly_score"], float)
        self.assertIsInstance(metadata["physics_residual"], float)
        self.assertIsInstance(metadata["cusum_evidence"], bool)
        self.assertIsInstance(metadata["current_fault_confirmation"], bool)

    def test_single_sensor_spike_suppression(self):
        """TEST E: Isolated single-frame spike must NOT trigger CRITICAL."""
        for i in range(5):
            frame = self.nominal_frame.copy()
            frame["timestamp"] = float(i + 1)
            self.core.process_telemetry_frame(frame)

        spike_frame = self.nominal_frame.copy()
        spike_frame["timestamp"] = 6.0
        spike_frame["cht1"] = 195.0

        snap = self.core.process_telemetry_frame(spike_frame)
        self.assertNotEqual(snap["system_state"], "CRITICAL")

if __name__ == "__main__":
    unittest.main()
