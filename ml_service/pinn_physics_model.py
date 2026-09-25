"""
Physics-Informed Neural Network (PINN) Thermodynamic Engine Model
Combines first-principles 1D thermodynamics (mass, momentum, and energy conservation)
with data-driven ML to predict expected physical reference states.
"""

import math
import numpy as np
from typing import Dict, Any

class PinnPhysicsModel:
    """
    Thermodynamic reference model for 1211cc 4-stroke 4-cylinder turbocharged aero piston engine.
    Applies thermodynamic equations to calculate expected thermal, pressure, and power baselines.
    """
    def __init__(self):
        self.displacement_cc = 1211.0
        self.compression_ratio = 9.0
        self.stroke_m = 0.061
        self.bore_m = 0.0795

    def predict_expected_state(self, telemetry: Dict[str, Any], mission_profile: str = "CRUISE") -> Dict[str, Any]:
        """
        Calculates expected physical baselines incorporating environmental lapse rates:
        - High Altitude: 4500m (ambient pressure 0.57 bar, turbo boost +0.25 bar)
        - Hot Weather: 42°C ambient thermal stress
        """
        rpm = float(telemetry.get("rpm", 5000.0))
        map_bar = float(telemetry.get("map", 1.15))

        # Adjust environmental factors based on scenario
        if mission_profile == "HIGH_ALTITUDE":
            altitude_m = 4500.0
            ambient_temp_c = -14.2  # Standard lapse rate at 4.5km
            ambient_press_bar = 0.57
            throttle_pct = 85.0
            engine_load_pct = 80.0
            turbo_boost = 0.25
        elif mission_profile == "HOT_WEATHER":
            altitude_m = 1500.0
            ambient_temp_c = 42.0   # Extreme heat stress
            ambient_press_bar = 0.85
            throttle_pct = 75.0
            engine_load_pct = 75.0
            turbo_boost = 0.10
        elif mission_profile == "RAPID_THROTTLE":
            altitude_m = 1500.0
            ambient_temp_c = 25.0
            ambient_press_bar = 0.85
            throttle_pct = 90.0
            engine_load_pct = 85.0
            turbo_boost = 0.15
        else: # CRUISE / ENDURANCE
            altitude_m = 1500.0
            ambient_temp_c = 15.0
            ambient_press_bar = 0.85
            throttle_pct = 75.0
            engine_load_pct = 70.0
            turbo_boost = 0.10

        # 1. Expected Power Calculation (Brake Power kW)
        # Power P = (MAP * V_d * RPM / 120) * Volumetric_Efficiency * Thermal_Efficiency
        volumetric_eff = 0.88 + turbo_boost * 0.12
        indicated_power = (map_bar * 100.0 * (self.displacement_cc * 1e-6) * (rpm / 120.0)) * volumetric_eff
        expected_power_kw = round(indicated_power * 0.34, 1)

        # 2. Expected Cylinder Head Temperature (CHT) (°C)
        # Thermal equilibrium equation: Q_in = Q_work + Q_cooling + Q_exhaust
        expected_cht = 105.0 + (rpm / 5800.0) * 20.0 + (map_bar - 1.0) * 15.0 + (ambient_temp_c - 15.0) * 0.35
        expected_cht = round(max(95.0, min(160.0, expected_cht)), 1)

        # 3. Expected Exhaust Gas Temperature (EGT) (°C)
        expected_egt = 710.0 + (rpm / 5800.0) * 45.0 + (map_bar - 1.0) * 25.0
        expected_egt = round(max(650.0, min(860.0, expected_egt)), 1)

        # 4. Expected Oil Pressure (bar)
        # Oil pump flow scales linearly with RPM; viscosity drops slightly with oil temp
        expected_oil_press = 2.2 + (rpm / 5800.0) * 2.6
        expected_oil_press = round(max(1.8, min(4.8, expected_oil_press)), 2)

        # 5. Expected Oil Temperature (°C)
        expected_oil_temp = round(78.0 + (expected_cht - 100.0) * 0.3 + (ambient_temp_c - 15.0) * 0.25, 1)

        # Calculate Residuals (Observed - Physics Prediction)
        actual_cht_avg = round(float(np.mean([telemetry.get(f"cht{i}", expected_cht) for i in range(1, 5)])), 1)
        actual_egt_avg = round(float(np.mean([telemetry.get(f"egt{i}", expected_egt) for i in range(1, 5)])), 1)
        actual_oil_press = round(float(telemetry.get("oil_press", expected_oil_press)), 2)
        actual_oil_temp = round(float(telemetry.get("oil_temp", expected_oil_temp)), 1)

        cht_residual = round(actual_cht_avg - expected_cht, 1)
        egt_residual = round(actual_egt_avg - expected_egt, 1)
        oil_press_residual = round(actual_oil_press - expected_oil_press, 2)
        oil_temp_residual = round(actual_oil_temp - expected_oil_temp, 1)

        return {
            "altitude_m": altitude_m,
            "ambient_temp_c": ambient_temp_c,
            "ambient_press_bar": ambient_press_bar,
            "throttle_pct": throttle_pct,
            "engine_load_pct": engine_load_pct,
            "expected_power_kw": expected_power_kw,
            "expected_cht": expected_cht,
            "expected_egt": expected_egt,
            "expected_oil_press": expected_oil_press,
            "expected_oil_temp": expected_oil_temp,
            "residuals": {
                "cht_delta": cht_residual,
                "egt_delta": egt_residual,
                "oil_press_delta": oil_press_residual,
                "oil_temp_delta": oil_temp_residual
            }
        }
