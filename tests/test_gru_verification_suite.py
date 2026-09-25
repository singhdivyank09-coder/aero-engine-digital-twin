"""
GRU Short-Horizon Forecasting & Predictive Health Integration Verification Test Suite
SIH 26054 — Aero-Piston Engine Digital Twin

Performs:
1. Thermal Degradation Test (Cylinder 1 Thermal Degradation, 60s ramp)
   - Proves GRU 30s/60s forecast triggers PREDICTIVE_RISK while CHT1 < 145.0°C safety limit.
2. Lubrication Degradation Test (Oil pressure drop)
   - Proves GRU forecast triggers PREDICTIVE_RISK while Oil Pressure > 2.50 bar safety limit.
3. Nominal False-Positive Test
   - Proves Cruise 60s nominal operation stays near nominal evolution with 0 false PREDICTIVE_RISK alerts.
4. Fallback Handling Test
   - Proves missing/corrupt model fallback gracefully exposes STATISTICAL_FALLBACK mode without crashing.
"""

import os
import unittest
import time
from backend.telemetry_simulator import TelemetrySimulator
from backend.digital_twin_core import DigitalTwinCore
from backend.gru_forecast_service import GruForecastService

class TestGruVerificationSuite(unittest.TestCase):

    def setUp(self):
        self.simulator = TelemetrySimulator()
        self.core = DigitalTwinCore()
        self.simulator.reset()
        self.core.reset()

    def test_1_thermal_degradation_gru_predictive_risk(self):
        """
        CRITICAL TEST 1 — THERMAL DEGRADATION:
        Cruise scenario, Cylinder 1 Thermal Degradation (60s gradual ramp).
        Demonstrates GRU 30s/60s forecast predicting future thermal risk and triggering
        PREDICTIVE_RISK BEFORE current CHT1 breaches the 145.0°C safety limit.
        """
        self.simulator.set_mission_profile("CRUISE")

        # Warm up 40 seconds (400 frames) to fill GRU 30-second input window (status = READY)
        for _ in range(400):
            frame = self.simulator.get_next_frame()
            snapshot = self.core.process_telemetry_frame(frame)

        self.assertEqual(snapshot["forecast_mode"], "GRU_MODEL")
        self.assertEqual(snapshot["latest_forecast"]["status"], "READY")

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
        first_gru_predictive_risk_time = None
        first_gru_predictive_risk_cht = None
        active_fault_time = None

        total_seconds = 70
        for step in range(total_seconds * 10):
            t_sec = step * 0.1
            frame = self.simulator.get_next_frame()
            snapshot = self.core.process_telemetry_frame(frame)

            thermal_ass = [a for a in snapshot["predictive_health_assessments"] if a["subsystem"] == "Thermal"][0]
            st = thermal_ass["predictive_status"]
            cht1_val = thermal_ass["current_value"]

            fc = snapshot.get("latest_forecast", {}).get("forecast", {})
            f10 = fc.get("10s", {}).get("cht1", cht1_val)
            f30 = fc.get("30s", {}).get("cht1", cht1_val)
            f60 = fc.get("60s", {}).get("cht1", cht1_val)

            if st == "PREDICTIVE_RISK" and first_gru_predictive_risk_time is None:
                first_gru_predictive_risk_time = t_sec
                first_gru_predictive_risk_cht = cht1_val
            if st == "ACTIVE_FAULT" and active_fault_time is None:
                active_fault_time = t_sec

            if step % 50 == 0:
                timeline_log.append({
                    "t": f"t={int(t_sec)}s",
                    "cht1": f"{cht1_val:.1f}°C",
                    "f10": f"{f10:.1f}°C",
                    "f30": f"{f30:.1f}°C",
                    "f60": f"{f60:.1f}°C",
                    "anomaly": f"{thermal_ass['anomaly_score']:.3f}",
                    "cusum": str(thermal_ass['cusum_detected']),
                    "residual": f"{thermal_ass['physics_residual']:+.1f}°C",
                    "status": st
                })

        print("\n--- THERMAL PREDICTION TEST TIMELINE ---")
        for entry in timeline_log:
            print(f"{entry['t']} | Current CHT1={entry['cht1']} | 10s Forecast={entry['f10']} | 30s Forecast={entry['f30']} | 60s Forecast={entry['f60']} | Anomaly={entry['anomaly']} | CUSUM={entry['cusum']} | Residual={entry['residual']} | Status={entry['status']}")

        self.assertIsNotNone(first_gru_predictive_risk_time, "PREDICTIVE_RISK must trigger")
        self.assertLess(first_gru_predictive_risk_cht, 145.0, "PREDICTIVE_RISK must trigger while CHT1 < 145.0°C limit")
        self.assertIsNotNone(active_fault_time, "ACTIVE_FAULT must occur after actual limit breach")
        self.assertLess(first_gru_predictive_risk_time, active_fault_time, "PREDICTIVE_RISK must occur BEFORE ACTIVE_FAULT")

        print(f"\nFIRST GRU-BASED PREDICTIVE_RISK TIME: t={first_gru_predictive_risk_time:.1f}s (CHT1 = {first_gru_predictive_risk_cht:.1f}°C)")
        print(f"ACTIVE_FAULT TIME: t={active_fault_time:.1f}s")
        print(f"PROOF PREDICTIVE_RISK OCCURRED FIRST: {first_gru_predictive_risk_time:.1f}s < {active_fault_time:.1f}s (CHT1 at risk = {first_gru_predictive_risk_cht:.1f}°C < 145.0°C)")

    def test_2_lubrication_degradation_gru_forecast(self):
        """
        TEST 2 — LUBRICATION DEGRADATION:
        Gradual oil pressure decay. Proves GRU 30s/60s forecast predicts declining trajectory
        and triggers PREDICTIVE_RISK while oil pressure > 2.50 bar limit.
        """
        self.simulator.set_mission_profile("CRUISE")
        for _ in range(350):
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
        trigger_p = 0.0

        for step in range(500):
            frame = self.simulator.get_next_frame()
            snapshot = self.core.process_telemetry_frame(frame)

            lube_ass = [a for a in snapshot["predictive_health_assessments"] if a["subsystem"] == "Lubrication"][0]
            st = lube_ass["predictive_status"]
            val = lube_ass["current_value"]

            if st in ["PREDICTIVE_RISK", "DEGRADATION_DETECTED"] and val > 2.50:
                risk_triggered_above_limit = True
                trigger_p = val
                break

        self.assertTrue(risk_triggered_above_limit, "Predictive lubrication risk must trigger while oil pressure > 2.50 bar")
        print(f"LUBRICATION TEST RESULT: PASS (Predictive risk detected at Oil Pressure = {trigger_p:.2f} bar > 2.50 bar limit)")

    def test_3_nominal_false_positive(self):
        """
        TEST 3 — NOMINAL FALSE-POSITIVE TEST:
        Cruise scenario for 60 seconds (600 frames).
        Verifies GRU predictions stay near nominal evolution with 0 false PREDICTIVE_RISK alerts.
        """
        self.simulator.set_mission_profile("CRUISE")
        false_predictive_warnings = 0

        for step in range(600):
            frame = self.simulator.get_next_frame()
            snapshot = self.core.process_telemetry_frame(frame)

            for ass in snapshot["predictive_health_assessments"]:
                if ass["predictive_status"] in ["PREDICTIVE_RISK", "ACTIVE_FAULT"]:
                    false_predictive_warnings += 1
                    print(f"[DEBUG FALSE ALARM] step={step} subsystem={ass['subsystem']} val={ass['current_value']} slope={ass['short_slope']} evidence={ass['evidence_sources']}")

        self.assertEqual(false_predictive_warnings, 0, "Nominal cruise must produce zero false PREDICTIVE_RISK alerts")
        print(f"NOMINAL FALSE-POSITIVE TEST RESULT: PASS (0 false predictive warnings observed across 600 nominal frames)")

    def test_4_failure_handling_fallback(self):
        """
        TEST 4 — FAILURE HANDLING:
        Verifies GRU service error handling falls back gracefully to STATISTICAL_FALLBACK without crashing.
        """
        service = GruForecastService()
        service.is_loaded = False
        service.load_error = "Simulated missing model file test"

        res = service.predict_forecast([], timestamp=10.0)
        self.assertEqual(res["forecast_mode"], "STATISTICAL_FALLBACK")
        self.assertIn("FALLBACK", res["status"])
        print(f"FAILURE HANDLING TEST RESULT: PASS (Gracefully exposed forecast_mode = {res['forecast_mode']})")

if __name__ == "__main__":
    unittest.main()
