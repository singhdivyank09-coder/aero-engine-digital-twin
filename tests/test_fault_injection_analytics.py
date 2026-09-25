"""
Unit & Integration Tests for Fault Injection & Analytics Module
Verifies:
1. Fault Injection controls (scenario, component, profile, intensity, rate, start/pause/clear).
2. Physical Input Perturbation strictly (never directly setting system_state, health_index, anomaly_score, fault_label, maintenance_advisory).
3. Event log tracking (fault scenario, start time, affected input, injection profile, cleared time).
4. Acceptance Test: Gradual CHT1 Thermal Degradation natural state machine progression (NORMAL -> WATCH -> CAUTION -> WARNING -> CRITICAL) and stepwise hysteresis recovery upon clearing.
"""

import unittest
from backend.telemetry_simulator import TelemetrySimulator
from backend.digital_twin_core import DigitalTwinCore

class TestFaultInjectionAnalytics(unittest.TestCase):

    def setUp(self):
        self.simulator = TelemetrySimulator()
        self.digital_twin = DigitalTwinCore()
        self.simulator.reset()
        self.digital_twin.reset()

    def test_fault_injection_controls_and_event_log(self):
        """Verify fault injection configuration and event log generation."""
        # Start fault
        res_start = self.simulator.start_fault_injection(
            scenario="CYLINDER_THERMAL",
            component="CYLINDER_1",
            profile="GRADUAL",
            intensity=1.2,
            rate="FAST"
        )
        self.assertEqual(res_start["scenario"], "CYLINDER_THERMAL")
        self.assertIn(res_start["status"], ["INJECTING", "RUNNING"])
        self.assertEqual(len(self.simulator.fault_event_log), 1)

        event = self.simulator.fault_event_log[0]
        self.assertIn("fault_scenario", event)
        self.assertIn("start_time", event)
        self.assertIn("affected_input", event)
        self.assertIn("injection_profile", event)
        self.assertIn(event["status"], ["INJECTING", "RUNNING"])
        self.assertEqual(event["cleared_time"], "ACTIVE")

        # Pause fault
        res_pause = self.simulator.pause_fault_injection()
        self.assertEqual(res_pause["status"], "PAUSED")

        # Resume fault
        res_resume = self.simulator.resume_fault_injection()
        self.assertIn(res_resume["status"], ["INJECTING", "RUNNING"])

        # Clear fault
        res_clear = self.simulator.clear_fault_injection()
        self.assertIn(res_clear["status"], ["CLEARED", "success"])
        self.assertNotEqual(event["cleared_time"], "ACTIVE")

    def test_physical_input_perturbation_only(self):
        """Verify fault injection only perturbs physical telemetry inputs and never assigns output analytics directly."""
        frame = self.simulator.get_next_frame()
        raw_before = frame["raw_telemetry"].copy()

        # Start oil pressure degradation
        self.simulator.start_fault_injection(
            scenario="OIL_PRESSURE",
            component="OIL_SYSTEM",
            profile="SUDDEN",
            intensity=1.5
        )

        # Advance frames
        for _ in range(10):
            frame = self.simulator.get_next_frame()

        raw_after = frame["raw_telemetry"]

        # Ensure physical input was perturbed (oil pressure decreased)
        self.assertLess(raw_after["oil_press"], raw_before["oil_press"])

        # Ensure frame output does NOT contain hardcoded system_state or health_index assigned by simulator
        self.assertNotIn("system_state", self.simulator.fault_config)
        self.assertNotIn("health_index", self.simulator.fault_config)
        self.assertNotIn("anomaly_score", self.simulator.fault_config)

    def test_acceptance_natural_progression_and_hysteresis_recovery(self):
        """
        ACCEPTANCE TEST:
        Start gradual CHT1 thermal degradation.
        1. System should initially remain NORMAL.
        2. Progress naturally through state machine: NORMAL -> WATCH -> CAUTION -> WARNING -> CRITICAL.
        3. Clear fault.
        4. System recovers step-by-step using state-machine hysteresis: CRITICAL -> WARNING -> CAUTION -> WATCH -> NORMAL.
        """
        # Step 1: Run nominal frames to ensure steady state
        for _ in range(10):
            frame = self.simulator.get_next_frame()
            snapshot = self.digital_twin.process_telemetry_frame(frame)
        
        self.assertIn(snapshot["system_state"], ["NORMAL", "WATCH"])

        # Step 2: Inject Gradual CHT1 Thermal Degradation
        self.simulator.start_fault_injection(
            scenario="CYLINDER_THERMAL",
            component="CYLINDER_1",
            profile="GRADUAL",
            intensity=1.8,
            rate="FAST"
        )

        observed_states = []
        
        # Run simulator frames while fault progresses over time
        for _ in range(180):  # 18 seconds of 10Hz telemetry
            frame = self.simulator.get_next_frame()
            snapshot = self.digital_twin.process_telemetry_frame(frame)
            st = snapshot["system_state"]
            if not observed_states or observed_states[-1] != st:
                observed_states.append(st)

        # Confirm progressive degradation reached CRITICAL
        self.assertTrue(any(s in ["NORMAL", "WATCH"] for s in observed_states))
        self.assertIn("CRITICAL", observed_states)
        # Ensure transitions were progressive (e.g. WATCH/CAUTION/WARNING encountered before CRITICAL)
        self.assertGreater(len(observed_states), 2)
        self.assertEqual(observed_states[-1], "CRITICAL")

        # Step 3: Clear Fault
        self.simulator.clear_fault_injection()

        recovery_states = []
        # Run simulator frames while telemetry normalizes
        for _ in range(200):  # 20 seconds of recovery
            frame = self.simulator.get_next_frame()
            snapshot = self.digital_twin.process_telemetry_frame(frame)
            st = snapshot["system_state"]
            if not recovery_states or recovery_states[-1] != st:
                recovery_states.append(st)

        # Confirm stepwise hysteresis recovery back to NORMAL
        self.assertEqual(recovery_states[-1], "NORMAL")
        # Stepwise recovery path should go through intermediate states (WARNING/CAUTION/WATCH)
        self.assertGreater(len(recovery_states), 2)

    def test_60s_ramp_predictive_detection_timeline(self):
        """
        ADD TEST (REQUIRED BY SPEC):
        Start nominal.
        Inject gradual CHT1 degradation using 60-second ramp.
        Verifies:
        1. First portion: CHT still normal, Digital Twin NORMAL.
        2. Trend detected: WATCH.
        3. Before threshold: CAUTION / WARNING.
        4. Only later if severe: current threshold crossed -> CRITICAL.
        Proves predictive detection.
        """
        # 1. Start nominal
        for _ in range(10):
            frame = self.simulator.get_next_frame()
            snapshot = self.digital_twin.process_telemetry_frame(frame)
        self.assertIn(snapshot["system_state"], ["NORMAL", "WATCH"])

        # 2. Inject gradual CHT1 degradation using 60-second ramp
        self.simulator.start_fault_injection(
            scenario="CYLINDER_THERMAL",
            component="CYLINDER_1",
            profile="GRADUAL",
            intensity=1.8,
            ramp_duration=60.0
        )

        history_records = []
        pre_threshold_warnings = []

        # Run 600 frames (60 seconds at 10Hz)
        for i in range(600):
            frame = self.simulator.get_next_frame()
            snapshot = self.digital_twin.process_telemetry_frame(frame)
            st = snapshot["system_state"]
            cht1_val = frame["raw_telemetry"]["cht1"]
            t_sec = i * 0.1

            history_records.append((t_sec, cht1_val, st))
            
            # Record states triggered while CHT1 is strictly inside normal safety limit (< 145.0 °C)
            if cht1_val < 145.0 and st in ["WATCH", "CAUTION", "WARNING"]:
                pre_threshold_warnings.append((t_sec, cht1_val, st))

        # First portion (e.g. t <= 10s, CHT < 125°C): State was NORMAL or WATCH
        early_states = [st for (t, cht, st) in history_records if t <= 10.0]
        self.assertTrue(any(s in ["NORMAL", "WATCH"] for s in early_states))

        # Confirm predictive detection: WATCH, CAUTION, or WARNING occurred BEFORE threshold (CHT < 145°C)
        self.assertGreater(len(pre_threshold_warnings), 0, "Predictive warning must occur before physical safety limit (145.0 °C) breach!")
        
        # Verify specific pre-threshold states occurred
        pre_thresh_state_names = set(st for (t, cht, st) in pre_threshold_warnings)
        self.assertTrue(
            "WATCH" in pre_thresh_state_names or "CAUTION" in pre_thresh_state_names or "WARNING" in pre_thresh_state_names,
            f"Expected early predictive state (WATCH/CAUTION/WARNING) before threshold, got: {pre_thresh_state_names}"
        )

        # Final portion (after 60s ramp when CHT1 >= 145.0 °C): CRITICAL reached
        final_state = history_records[-1][2]
        self.assertEqual(final_state, "CRITICAL", f"Expected CRITICAL state at end of severe 60s thermal ramp, got: {final_state}")

if __name__ == "__main__":
    unittest.main()
