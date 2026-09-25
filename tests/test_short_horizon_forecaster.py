"""
Unit Tests for Short-Horizon Telemetry Forecaster & PredictiveHealthEngine Integration
SIH 26054 — Aero-Piston Engine Digital Twin

Verifies:
1. PyTorch LSTM ShortHorizonForecaster inference format & schema compliance.
2. Saved metrics artifact contains valid MAE and RMSE evaluations.
3. Key requirement scenario: Current CHT remains normal (e.g. 132.5°C < 145.0°C limit),
   but 30-second forecast CHT crosses the 145.0°C reference safety envelope.
4. PredictiveHealthEngine correctly receives forecast and triggers PREDICTIVE_RISK.
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import json
import unittest
import numpy as np
from ml_service.short_horizon_forecaster import ShortHorizonForecaster, MODEL_PATH, SCALER_PATH, METRICS_PATH
from backend.predictive_health_engine import PredictiveHealthEngine

class TestShortHorizonForecaster(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.forecaster = ShortHorizonForecaster()
        cls.engine = PredictiveHealthEngine()

    def test_artifacts_exist(self):
        """Verify model, scaler, and metrics artifacts exist."""
        self.assertTrue(os.path.exists(MODEL_PATH), "Model checkpoint artifact missing.")
        self.assertTrue(os.path.exists(SCALER_PATH), "Scaler artifact missing.")
        self.assertTrue(os.path.exists(METRICS_PATH), "Metrics artifact missing.")

    def test_metrics_evaluation_quality(self):
        """Verify evaluation metrics artifact contains test_mae and test_rmse."""
        with open(METRICS_PATH, "r") as f:
            metrics = json.load(f)

        self.assertIn("test_mae", metrics)
        self.assertIn("test_rmse", metrics)
        self.assertIsInstance(metrics["test_mae"], float)
        self.assertIsInstance(metrics["test_rmse"], float)
        self.assertGreater(metrics["test_mae"], 0.0)
        self.assertGreater(metrics["test_rmse"], 0.0)
        self.assertEqual(metrics["training_dataset"], "SIMULATED REFERENCE AERO-PISTON TRAJECTORIES")

    def test_forecast_output_schema(self):
        """Verify forecast return schema matches exact user specifications."""
        # Generate dummy 30-sample history window
        history_window = []
        for i in range(30):
            history_window.append({
                "cht1": 120.0 + i * 0.2,
                "egt1": 748.0,
                "oil_press": 4.20,
                "oil_temp": 88.5,
                "vibration_rms": 1.12
            })

        timestamp = 100.0
        res = self.forecaster.forecast(history_window, timestamp)

        self.assertIn("horizon_seconds", res)
        self.assertIn("predicted_values", res)
        self.assertIn("prediction_timestamp", res)
        self.assertIn("model_version", res)
        self.assertIn("confidence_or_error_band_if_available", res)

        self.assertEqual(res["prediction_timestamp"], timestamp)
        self.assertIsNone(res["confidence_or_error_band_if_available"])

        predicted_values = res["predicted_values"]
        self.assertIn("10s", predicted_values)
        self.assertIn("30s", predicted_values)
        self.assertIn("60s", predicted_values)

        for horizon_key in ["10s", "30s", "60s"]:
            horizon_dict = predicted_values[horizon_key]
            self.assertIn("cht", horizon_dict)
            self.assertIn("egt", horizon_dict)
            self.assertIn("oil_press", horizon_dict)
            self.assertIn("oil_temp", horizon_dict)
            self.assertIn("vibration_rms", horizon_dict)

    def test_current_cht_normal_but_forecast_breaches_limit(self):
        """
        CRITICAL TEST REQUIREMENT:
        Current CHT remains normal (e.g. 132.5°C < 145.0°C limit),
        but thermal trajectory forecast crosses the reference envelope in 30 seconds.
        PredictiveHealthEngine must receive this forecast and flag PREDICTIVE_RISK.
        """
        engine = PredictiveHealthEngine()
        fault_limit = engine.SAFETY_ENVELOPES["cht"]["fault_limit"] # 145.0 °C

        # Simulate progressive thermal rise sequence where current CHT is ~132.5°C
        # but rapid slope (0.50 °C/s) projects 30s CHT to 132.5 + (0.50 * 30) = 147.5°C (> 145.0°C)
        t_base = 1000.0
        for i in range(50):
            t = t_base + i * 0.1
            cht_val = 115.0 + i * 0.35 # Rising temperature curve
            telemetry = {
                "timestamp": t,
                "rpm": 2450.0,
                "map": 28.5,
                "cht1": cht_val,
                "cht2": 120.0,
                "cht3": 121.0,
                "cht4": 119.0,
                "egt1": 750.0,
                "egt2": 752.0,
                "egt3": 748.0,
                "egt4": 751.0,
                "oil_press": 4.10,
                "oil_temp": 89.0,
                "fuel_flow": 28.0,
                "vibration_rms": 1.15,
                "battery_volt": 13.8
            }
            physics_state = {"residuals": {"cht_delta": 2.5, "oil_press_delta": 0.05, "egt_delta": 3.0}}
            ae_res = {"anomaly_score": 0.45}
            cusum_res = {"cusum_alert_active": False}

            assessments = engine.process_frame(telemetry, physics_state, ae_res, cusum_res)

        thermal_assessment = next(a for a in assessments if a["subsystem"] == "Thermal")

        current_cht = thermal_assessment["current_values"]["max_cht"]
        forecasted_val = thermal_assessment["future_forecast"]["forecasted_value"]
        status = thermal_assessment["status"]

        # Assert current CHT is strictly below the physical active fault limit (145.0°C)
        self.assertLess(current_cht, fault_limit, f"Current CHT ({current_cht}°C) must be normal (< {fault_limit}°C)")
        
        # Assert 30-second forecast crosses reference safety envelope (>= 145.0°C)
        self.assertGreaterEqual(forecasted_val, fault_limit, f"30s forecast CHT ({forecasted_val}°C) must cross reference limit ({fault_limit}°C)")

        # Assert PredictiveHealthEngine evaluated state to PREDICTIVE_RISK (not ACTIVE_FAULT, not NOMINAL)
        self.assertEqual(status, "PREDICTIVE_RISK", f"Engine status should be PREDICTIVE_RISK, got {status}")

        # Assert short_horizon_telemetry_forecast is attached in the assessment object
        self.assertIn("short_horizon_telemetry_forecast", thermal_assessment["future_forecast"])

if __name__ == "__main__":
    unittest.main()
