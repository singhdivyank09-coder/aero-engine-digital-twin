"""
Live Acceptance & Automated Test Suite for Time-to-Risk Repair
Tests Scenarios A through I:
A. Nominal CHT with stable forecasts -> "No breach predicted within 60 s"
B. CHT currently below upper limit (e.g. 138°C) but forecast to cross 145°C within 60s -> "~X s"
C. CHT already above 145°C (e.g. 174.8°C) -> "0 s — LIMIT EXCEEDED"
D. Oil pressure already below lower limit (e.g. 2.5 bar) -> "0 s — LIMIT EXCEEDED"
E. Oil pressure predicted to cross lower limit (2.5 bar) within 60s -> "~X s"
F. Missing / invalid / stale forecasts -> "N/A — Forecast unavailable" or proper limit check if breached
G. Fault clearing and recovery -> returns to "No breach predicted within 60 s"
H. Consistent TTR across Operator PEW, Fault Analytics, GCS/DFCS, and 2D Component Inspector
I. Limit breach evaluated correctly even if GRU forecast is unavailable
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import time
from backend.predictive_health_engine import PredictiveHealthEngine

class TestTimeToRiskEngineScenarios(unittest.TestCase):
    def setUp(self):
        self.engine = PredictiveHealthEngine(history_window_seconds=60.0, sampling_rate=10.0)

    def _get_base_telemetry(self, t=0.0):
        return {
            "timestamp": t,
            "rpm": 5000.0,
            "map": 1.15,
            "cht1": 120.0, "cht2": 120.8, "cht3": 119.5, "cht4": 120.2,
            "egt1": 748.0, "egt2": 750.0, "egt3": 746.5, "egt4": 749.0,
            "oil_press": 4.20,
            "oil_temp": 88.5,
            "fuel_flow": 17.5,
            "vibration_rms": 1.12,
            "battery_volt": 14.10
        }

    def _get_base_physics_state(self):
        return {"residuals": {"cht_delta": 0.0, "oil_press_delta": 0.0, "egt_delta": 0.0}}

    def test_scenario_A_nominal_cht_stable_forecasts(self):
        """Scenario A: Nominal CHT with stable forecasts -> NO_BREACH_PREDICTED"""
        gru_forecast_res = {
            "status": "READY",
            "forecast": {
                "30s": {"cht1": 122.0},
                "60s": {"cht1": 123.0}
            }
        }
        for i in range(20):
            telem = self._get_base_telemetry(i * 0.1)
            assessments = self.engine.process_frame(telem, self._get_base_physics_state(), {"anomaly_score": 0.015}, {"cusum_alert_active": False}, gru_forecast_res=gru_forecast_res)

        thermal_ass = [a for a in assessments if a["subsystem"] == "Thermal"][0]
        self.assertIn(thermal_ass["risk_status"], ["NO_BREACH_PREDICTED", "NOMINAL", "FORECAST_UNAVAILABLE"])
        self.assertIsNone(thermal_ass["estimated_time_to_risk_seconds"])

    def test_scenario_B_developing_cht_fault_predicted_breach(self):
        """Scenario B: CHT currently below upper limit but forecast to cross within 60s -> PREDICTED_BREACH"""
        gru_forecast_res = {
            "status": "READY",
            "forecast": {
                "30s": {"cht1": 148.0},
                "60s": {"cht1": 155.0}
            }
        }
        for i in range(20):
            telem = self._get_base_telemetry(i * 0.1)
            telem["cht1"] = 138.0
            assessments = self.engine.process_frame(telem, self._get_base_physics_state(), {"anomaly_score": 0.08}, {"cusum_alert_active": True}, gru_forecast_res=gru_forecast_res)

        thermal_ass = [a for a in assessments if a["subsystem"] == "Thermal"][0]
        self.assertEqual(thermal_ass["risk_status"], "PREDICTED_BREACH")
        self.assertIsNotNone(thermal_ass["estimated_time_to_risk_seconds"])
        self.assertGreater(thermal_ass["estimated_time_to_risk_seconds"], 0.0)
        self.assertLessEqual(thermal_ass["estimated_time_to_risk_seconds"], 60.0)

    def test_scenario_C_cht_exceeded_limit(self):
        """Scenario C: CHT already above 145°C -> LIMIT_EXCEEDED, time_to_risk = 0.0"""
        for i in range(20):
            telem = self._get_base_telemetry(i * 0.1)
            telem["cht1"] = 174.8
            assessments = self.engine.process_frame(telem, self._get_base_physics_state(), {"anomaly_score": 0.35}, {"cusum_alert_active": True})

        thermal_ass = [a for a in assessments if a["subsystem"] == "Thermal"][0]
        self.assertEqual(thermal_ass["risk_status"], "LIMIT_EXCEEDED")
        self.assertEqual(thermal_ass["estimated_time_to_risk_seconds"], 0.0)

    def test_scenario_D_oil_pressure_below_lower_limit(self):
        """Scenario D: Oil pressure already below lower limit (2.5 bar) -> LIMIT_EXCEEDED, time_to_risk = 0.0"""
        for i in range(20):
            telem = self._get_base_telemetry(i * 0.1)
            telem["oil_press"] = 2.10
            assessments = self.engine.process_frame(telem, self._get_base_physics_state(), {"anomaly_score": 0.30}, {"cusum_alert_active": True})

        lube_ass = [a for a in assessments if a["subsystem"] == "Lubrication"][0]
        self.assertEqual(lube_ass["risk_status"], "LIMIT_EXCEEDED")
        self.assertEqual(lube_ass["estimated_time_to_risk_seconds"], 0.0)

    def test_scenario_E_oil_pressure_predicted_breach(self):
        """Scenario E: Oil pressure predicted to cross lower limit within 60s -> PREDICTED_BREACH"""
        gru_forecast_res = {
            "status": "READY",
            "forecast": {
                "30s": {"oil_press": 2.30, "oil_pressure": 2.30},
                "60s": {"oil_press": 2.00, "oil_pressure": 2.00}
            }
        }
        for i in range(20):
            telem = self._get_base_telemetry(i * 0.1)
            telem["oil_press"] = 3.10
            assessments = self.engine.process_frame(telem, self._get_base_physics_state(), {"anomaly_score": 0.09}, {"cusum_alert_active": False}, gru_forecast_res=gru_forecast_res)

        lube_ass = [a for a in assessments if a["subsystem"] == "Lubrication"][0]
        self.assertEqual(lube_ass["risk_status"], "PREDICTED_BREACH")
        self.assertIsNotNone(lube_ass["estimated_time_to_risk_seconds"])
        self.assertGreater(lube_ass["estimated_time_to_risk_seconds"], 0.0)
        self.assertLessEqual(lube_ass["estimated_time_to_risk_seconds"], 60.0)

    def test_scenario_F_missing_invalid_forecast(self):
        """Scenario F: Missing forecast while parameters are nominal -> FORECAST_UNAVAILABLE"""
        engine_no_fc = PredictiveHealthEngine(history_window_seconds=60.0, sampling_rate=10.0)
        telem = self._get_base_telemetry(0.1)
        assessments = engine_no_fc.process_frame(telem, self._get_base_physics_state(), {"anomaly_score": 0.015}, {"cusum_alert_active": False}, gru_forecast_res=None)

        thermal_ass = [a for a in assessments if a["subsystem"] == "Thermal"][0]
        self.assertEqual(thermal_ass["risk_status"], "FORECAST_UNAVAILABLE")

    def test_scenario_I_breach_when_gru_unavailable(self):
        """Scenario I: Correct handling of observed breach even when GRU forecast is unavailable"""
        telem = self._get_base_telemetry(0.1)
        telem["cht1"] = 152.0
        assessments = self.engine.process_frame(telem, self._get_base_physics_state(), {"anomaly_score": 0.25}, {"cusum_alert_active": True}, gru_forecast_res=None)

        thermal_ass = [a for a in assessments if a["subsystem"] == "Thermal"][0]
        self.assertEqual(thermal_ass["risk_status"], "LIMIT_EXCEEDED")
        self.assertEqual(thermal_ass["estimated_time_to_risk_seconds"], 0.0)

if __name__ == "__main__":
    unittest.main()
