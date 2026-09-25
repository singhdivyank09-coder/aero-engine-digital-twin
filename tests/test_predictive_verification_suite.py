"""
Comprehensive Predictive Health Engine Verification Test Suite (Tests A-E)
Validates early degradation detection before reference threshold crossing.
"""

import unittest
import time
from backend.telemetry_simulator import TelemetrySimulator
from backend.digital_twin_core import DigitalTwinCore
from backend.predictive_health_engine import PredictiveHealthEngine

class TestPredictiveVerificationSuite(unittest.TestCase):

    def setUp(self):
        self.simulator = TelemetrySimulator()
        self.core = DigitalTwinCore()
        self.simulator.reset()
        self.core.reset()

    def test_A_healthy_nominal(self):
        """TEST A — HEALTHY NOMINAL: Cruise scenario, no fault."""
        self.simulator.set_mission_profile("CRUISE")
        
        assessments = []
        for i in range(100):
            frame = self.simulator.get_next_frame()
            snapshot = self.core.process_telemetry_frame(frame)
            assessments = snapshot["predictive_health_assessments"]

        for ass in assessments:
            self.assertEqual(ass["predictive_status"], "NOMINAL")
            self.assertLess(ass["degradation_score"], 0.25)
            self.assertGreaterEqual(ass["estimated_time_to_risk"], 100.0)

    def test_B_single_sensor_spike(self):
        """TEST B — SINGLE SENSOR SPIKE: Inject 1 temporary spike, verify NO persistent predictive risk."""
        self.simulator.set_mission_profile("CRUISE")
        for i in range(30):
            frame = self.simulator.get_next_frame()
            self.core.process_telemetry_frame(frame)

        # Inject single isolated spike
        spike_frame = self.simulator.get_next_frame()
        spike_frame["telemetry"]["cht1"] = 165.0
        spike_frame["raw_telemetry"]["cht1"] = 165.0

        snapshot = self.core.process_telemetry_frame(spike_frame)
        thermal_ass = [a for a in snapshot["predictive_health_assessments"] if a["subsystem"] == "Thermal"][0]
        
        self.assertNotEqual(thermal_ass["predictive_status"], "PREDICTIVE_RISK", 
                            "Single sensor spike must not trigger PREDICTIVE_RISK")

    def test_C_gradual_thermal_degradation(self):
        """
        TEST C — GRADUAL THERMAL DEGRADATION:
        Cylinder 1 thermal degradation with 60-second ramp.
        Records telemetry every 5 seconds.
        Validates MANDATORY sequence: NOMINAL -> DEGRADATION_DETECTED -> PREDICTIVE_RISK (< 145.0°C) -> ACTIVE_FAULT.
        """
        self.simulator.set_mission_profile("CRUISE")
        
        # Initial 20 frames nominal baseline
        for _ in range(20):
            frame = self.simulator.get_next_frame()
            self.core.process_telemetry_frame(frame)

        # Start 60-second gradual thermal fault injection
        self.simulator.start_fault_injection(
            scenario="CYLINDER_THERMAL",
            component="CYLINDER_1",
            profile="GRADUAL",
            intensity=1.0,
            rate="SLOW",
            ramp_duration=60.0
        )

        timeline_log = []
        first_degradation_time = None
        first_predictive_risk_time = None
        first_predictive_risk_cht = None
        active_fault_time = None

        total_seconds = 70
        for step in range(total_seconds * 10):
            t_sec = step * 0.1
            frame = self.simulator.get_next_frame()
            snapshot = self.core.process_telemetry_frame(frame)
            
            thermal_ass = [a for a in snapshot["predictive_health_assessments"] if a["subsystem"] == "Thermal"][0]
            status = thermal_ass["predictive_status"]
            cht1_val = thermal_ass["current_value"]

            if status in ["DEGRADATION_DETECTED", "PREDICTIVE_RISK"] and first_degradation_time is None:
                first_degradation_time = t_sec
            if status == "PREDICTIVE_RISK" and first_predictive_risk_time is None:
                first_predictive_risk_time = t_sec
                first_predictive_risk_cht = cht1_val
            if status == "ACTIVE_FAULT" and active_fault_time is None:
                active_fault_time = t_sec

            # Record log every 5 seconds (every 50 steps)
            if step % 50 == 0:
                timeline_log.append({
                    "t": f"t={int(t_sec)}s",
                    "cht1": f"{cht1_val:.1f}°C",
                    "slope": f"{thermal_ass['short_slope']:+.2f}°C/s",
                    "anomaly": f"{thermal_ass['anomaly_score']:.3f}",
                    "cusum": str(thermal_ass['cusum_detected']),
                    "residual": f"{thermal_ass['physics_residual']:+.1f}°C",
                    "degradation_score": f"{thermal_ass['degradation_score']:.3f}",
                    "time_to_risk": f"{thermal_ass['estimated_time_to_risk']:.1f}s",
                    "status": status
                })

        # MANDATORY ASSERTIONS:
        self.assertIsNotNone(first_degradation_time, "DEGRADATION_DETECTED must occur")
        self.assertIsNotNone(first_predictive_risk_time, "PREDICTIVE_RISK must occur")
        self.assertLess(first_predictive_risk_cht, 145.0, "PREDICTIVE_RISK must occur BEFORE CHT1 crosses safety limit (145.0°C)")
        self.assertIsNotNone(active_fault_time, "ACTIVE_FAULT must occur after actual limit breach")
        self.assertLess(first_predictive_risk_time, active_fault_time, "PREDICTIVE_RISK time must be earlier than ACTIVE_FAULT time")

        print("\n--- THERMAL TEST TIMELINE ---")
        for entry in timeline_log:
            print(f"{entry['t']} | CHT1={entry['cht1']} | Slope={entry['slope']} | Anomaly={entry['anomaly']} | CUSUM={entry['cusum']} | Residual={entry['residual']} | DegScore={entry['degradation_score']} | TTR={entry['time_to_risk']} | Status={entry['status']}")

        print(f"\nFIRST DEGRADATION_DETECTED TIME: t={first_degradation_time:.1f}s")
        print(f"FIRST PREDICTIVE_RISK TIME: t={first_predictive_risk_time:.1f}s (CHT1 = {first_predictive_risk_cht:.1f}°C)")
        print(f"ACTIVE_FAULT TIME: t={active_fault_time:.1f}s")
        print(f"PROOF THAT PREDICTIVE_RISK OCCURRED BEFORE ACTIVE_FAULT: {first_predictive_risk_time:.1f}s < {active_fault_time:.1f}s (CHT1 at risk = {first_predictive_risk_cht:.1f}°C < 145.0°C)")

    def test_D_oil_pressure_degradation(self):
        """TEST D — OIL PRESSURE DEGRADATION: Predictive lubrication risk appears BEFORE active-fault (<= 2.50 bar)."""
        self.simulator.set_mission_profile("CRUISE")
        for _ in range(20):
            frame = self.simulator.get_next_frame()
            self.core.process_telemetry_frame(frame)

        self.simulator.start_fault_injection(
            scenario="OIL_PRESSURE",
            component="OIL_SYSTEM",
            profile="GRADUAL",
            intensity=1.0,
            rate="SLOW",
            ramp_duration=40.0
        )

        risk_triggered_above_limit = False
        trigger_press = 0.0

        for step in range(500):
            frame = self.simulator.get_next_frame()
            snapshot = self.core.process_telemetry_frame(frame)
            lube_ass = [a for a in snapshot["predictive_health_assessments"] if a["subsystem"] == "Lubrication"][0]
            st = lube_ass["predictive_status"]
            val = lube_ass["current_value"]

            if st in ["PREDICTIVE_RISK", "DEGRADATION_DETECTED"] and val > 2.50:
                risk_triggered_above_limit = True
                trigger_press = val
                break

        self.assertTrue(risk_triggered_above_limit, "Predictive lubrication risk must trigger while oil pressure is > 2.50 bar")
        print(f"OIL TEST RESULT: PASS (Predictive risk detected at Oil Pressure = {trigger_press:.2f} bar > 2.50 bar limit)")

    def test_E_vibration_degradation(self):
        """TEST E — VIBRATION DEGRADATION: Predictive mechanical degradation detected through trend/variance."""
        self.simulator.set_mission_profile("CRUISE")
        for _ in range(20):
            frame = self.simulator.get_next_frame()
            self.core.process_telemetry_frame(frame)

        self.simulator.start_fault_injection(
            scenario="INCREASING_VIBRATION",
            component="MECHANICAL_BEARING",
            profile="GRADUAL",
            intensity=1.0,
            rate="SLOW",
            ramp_duration=40.0
        )

        risk_detected = False
        trigger_vib = 0.0

        for step in range(500):
            frame = self.simulator.get_next_frame()
            snapshot = self.core.process_telemetry_frame(frame)
            mech_ass = [a for a in snapshot["predictive_health_assessments"] if a["subsystem"] == "Mechanical"][0]
            st = mech_ass["predictive_status"]
            val = mech_ass["current_value"]

            if st in ["PREDICTIVE_RISK", "DEGRADATION_DETECTED"] and val < 2.50:
                risk_detected = True
                trigger_vib = val
                break

        self.assertTrue(risk_detected, "Predictive mechanical degradation must trigger before 2.50g fault limit")
        print(f"VIBRATION TEST RESULT: PASS (Predictive mechanical degradation detected at Vibration RMS = {trigger_vib:.2f}g < 2.50g limit)")

if __name__ == "__main__":
    unittest.main()
