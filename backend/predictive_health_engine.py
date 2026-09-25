"""
Predictive Health & Prognostic Engine — SIH 26054
Trajectory-Based Early Warning & Predictive Risk Forecasting

Performs:
- 60-second rolling history buffer (600 samples @ 10Hz) for canonical telemetry signals
- Temporal feature extraction (Current Value, Short/Long Mean, Short/Long Std Dev, EWMA, First/Second Derivatives, Short/Long Slopes, Variance Trend)
- Physics residual slope & Deep Autoencoder anomaly score slope tracking
- Normalized Degradation Score & Physically Transparent Time-to-Risk estimation
- Persistence spike filter to eliminate isolated single-frame sensor spikes
- 4-Tier Assessment Status: NOMINAL -> DEGRADATION_DETECTED -> PREDICTIVE_RISK -> ACTIVE_FAULT
"""

import math
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from collections import deque

from ml_service.short_horizon_forecaster import ShortHorizonForecaster

class PredictiveHealthEngine:
    SIGNAL_KEYS = [
        "rpm", "map", "cht1", "cht2", "cht3", "cht4",
        "egt1", "egt2", "egt3", "egt4", "oil_press", "oil_temp",
        "fuel_flow", "vibration_rms", "battery_volt"
    ]

    SAFETY_ENVELOPES = {
        "cht": {"nominal_max": 135.0, "fault_limit": 145.0, "unit": "°C", "subsystem": "Thermal"},
        "oil_press": {"nominal_min": 3.50, "fault_limit": 2.50, "unit": "bar", "subsystem": "Lubrication"},
        "vibration_rms": {"nominal_max": 1.50, "fault_limit": 2.50, "unit": "g", "subsystem": "Mechanical"},
        "battery_volt": {"nominal_min": 12.80, "nominal_max": 14.80, "fault_min": 11.50, "fault_max": 15.50, "unit": "V", "subsystem": "Electrical"},
        "egt_spread": {"nominal_max": 45.0, "fault_limit": 90.0, "unit": "°C", "subsystem": "Combustion"}
    }

    def __init__(self, history_window_seconds: float = 60.0, sampling_rate: float = 10.0):
        self.history_window_seconds = history_window_seconds
        self.sampling_rate = sampling_rate
        self.max_buffer_samples = int(history_window_seconds * sampling_rate) # 600 samples
        self.sequence_number = 0

        # Rolling History Buffers (60s @ 10Hz = 600 samples)
        self.timestamps = deque(maxlen=self.max_buffer_samples)
        self.signal_history = {k: deque(maxlen=self.max_buffer_samples) for k in self.SIGNAL_KEYS}
        self.raw_telemetry_history = deque(maxlen=self.max_buffer_samples)
        self.ewma_state = {k: None for k in self.SIGNAL_KEYS}
        
        self.physics_residual_history = {
            "cht": deque(maxlen=self.max_buffer_samples),
            "oil_press": deque(maxlen=self.max_buffer_samples),
            "egt": deque(maxlen=self.max_buffer_samples)
        }
        self.anomaly_score_history = deque(maxlen=self.max_buffer_samples)

        # Neural Short-Horizon Forecaster (PyTorch LSTM)
        self.forecaster = ShortHorizonForecaster()

    def _compute_slope(self, times: List[float], values: List[float]) -> Tuple[float, float]:
        """Calculates linear slope (dx/dt) and curvature/second derivative over window."""
        n = len(values)
        if n < 5:
            return 0.0, 0.0

        t = np.array(times) - times[0]
        v = np.array(values)
        dt = t[-1] - t[0]
        if dt < 0.3:
            return 0.0, 0.0

        slope, intercept = np.polyfit(t, v, 1)

        if n >= 8:
            poly2 = np.polyfit(t, v, 2)
            curvature = 2.0 * poly2[0]
        else:
            curvature = 0.0

        return float(slope), float(curvature)

    def extract_temporal_features(self, key: str, window_samples: Optional[int] = None) -> Dict[str, float]:
        """Extracts temporal features for a parameter over specified buffer depth."""
        history = list(self.signal_history[key])
        times = list(self.timestamps)

        if window_samples and len(history) > window_samples:
            history = history[-window_samples:]
            times = times[-window_samples:]

        n = len(history)
        if n == 0:
            return {
                "current": 0.0, "moving_mean": 0.0, "moving_std": 0.0, "ewma": 0.0,
                "first_derivative": 0.0, "second_derivative": 0.0, "short_slope": 0.0,
                "long_slope": 0.0, "rate_of_change": 0.0, "variance_trend": 0.0,
                "short_mean": 0.0, "long_mean": 0.0, "short_std": 0.0, "long_std": 0.0
            }

        curr_val = history[-1]
        mean_val = float(np.mean(history))
        std_val = float(np.std(history))

        # EWMA calculation (alpha = 0.20)
        alpha = 0.20
        ewma_val = self.ewma_state[key]
        if ewma_val is None:
            ewma_val = curr_val
        else:
            ewma_val = alpha * curr_val + (1.0 - alpha) * ewma_val
        self.ewma_state[key] = ewma_val

        # Multi-scale windows: short (3s / 30 samples) vs long (15s / 150 samples)
        short_samples = min(30, n)
        long_samples = min(150, n)

        short_hist = history[-short_samples:]
        long_hist = history[-long_samples:]
        short_times = times[-short_samples:]
        long_times = times[-long_samples:]

        short_mean = float(np.mean(short_hist))
        long_mean = float(np.mean(long_hist))
        short_std = float(np.std(short_hist))
        long_std = float(np.std(long_hist))

        short_slope, short_curv = self._compute_slope(short_times, short_hist)
        long_slope, _ = self._compute_slope(long_times, long_hist)

        # Variance trend: slope of rolling variance
        if n >= 20:
            half = n // 2
            first_half_var = float(np.var(history[:half]))
            second_half_var = float(np.var(history[half:]))
            dt_half = max(0.1, times[-1] - times[half])
            var_trend = (second_half_var - first_half_var) / dt_half
        else:
            var_trend = 0.0

        return {
            "current": float(curr_val),
            "moving_mean": round(mean_val, 3),
            "moving_std": round(std_val, 3),
            "short_mean": round(short_mean, 3),
            "long_mean": round(long_mean, 3),
            "short_std": round(short_std, 3),
            "long_std": round(long_std, 3),
            "ewma": round(float(ewma_val), 3),
            "first_derivative": round(short_slope, 4),
            "second_derivative": round(short_curv, 4),
            "short_slope": round(short_slope, 4),
            "long_slope": round(long_slope, 4),
            "rate_of_change": round(short_slope, 4),
            "variance_trend": round(var_trend, 4)
        }

    def process_frame(
        self,
        telemetry: Dict[str, Any],
        physics_state: Dict[str, Any],
        ae_res: Dict[str, Any],
        cusum_res: Dict[str, Any],
        gru_forecast_res: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Processes analytical frame and generates PredictiveHealthAssessment objects
        for each engine subsystem (Thermal, Lubrication, Mechanical, Combustion, Electrical).
        """
        seq_val = telemetry.get("sequence_no", telemetry.get("sequence_number"))
        if seq_val is not None:
            self.sequence_number = int(seq_val)
        else:
            self.sequence_number += 1
        t = float(telemetry.get("timestamp", 0.0))
        self.timestamps.append(t)
        self.raw_telemetry_history.append(telemetry)

        for k in self.SIGNAL_KEYS:
            val = float(telemetry.get(k, 0.0))
            if k == "battery_volt" and val == 0.0:
                val = 14.10
            self.signal_history[k].append(val)

        # Store residual and anomaly score history
        residuals = physics_state.get("residuals", {})
        self.physics_residual_history["cht"].append(float(residuals.get("cht_delta", 0.0)))
        self.physics_residual_history["oil_press"].append(float(residuals.get("oil_press_delta", 0.0)))
        self.physics_residual_history["egt"].append(float(residuals.get("egt_delta", 0.0)))
        self.anomaly_score_history.append(float(ae_res.get("anomaly_score", 0.0)))

        # Short-Horizon Trajectory Forecast via Neural LSTM
        neural_forecast = self.forecaster.forecast(list(self.raw_telemetry_history), t)

        assessments = []

        # 1. THERMAL SUBSYSTEM PREDICTIVE ASSESSMENT
        assessments.append(self._assess_thermal_subsystem(t, telemetry, physics_state, ae_res, cusum_res, neural_forecast, gru_forecast_res))

        # 2. LUBRICATION SUBSYSTEM PREDICTIVE ASSESSMENT
        assessments.append(self._assess_lubrication_subsystem(t, telemetry, physics_state, ae_res, cusum_res, gru_forecast_res))

        # 3. MECHANICAL SUBSYSTEM PREDICTIVE ASSESSMENT
        assessments.append(self._assess_mechanical_subsystem(t, telemetry, physics_state, ae_res, cusum_res, gru_forecast_res))

        # 4. COMBUSTION SUBSYSTEM PREDICTIVE ASSESSMENT
        assessments.append(self._assess_combustion_subsystem(t, telemetry, physics_state, ae_res, cusum_res))

        # 5. ELECTRICAL SUBSYSTEM PREDICTIVE ASSESSMENT
        assessments.append(self._assess_electrical_subsystem(t, telemetry, physics_state, ae_res, cusum_res))

        return assessments

    def _assess_thermal_subsystem(
        self, t: float, telemetry: Dict[str, Any], physics_state: Dict[str, Any], ae_res: Dict[str, Any], cusum_res: Dict[str, Any], neural_forecast: Optional[Dict[str, Any]] = None, gru_forecast_res: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        cht_vals = [float(telemetry.get(f"cht{i}", 120.0)) for i in range(1, 5)]
        max_cht = max(cht_vals)
        cyl_idx = cht_vals.index(max_cht) + 1
        key = f"cht{cyl_idx}"

        feat = self.extract_temporal_features(key)
        cht_res_history = list(self.physics_residual_history["cht"])
        ae_history = list(self.anomaly_score_history)

        res_slope, _ = self._compute_slope(list(self.timestamps), cht_res_history) if len(cht_res_history) >= 5 else (0.0, 0.0)
        ae_slope, _ = self._compute_slope(list(self.timestamps), ae_history) if len(ae_history) >= 5 else (0.0, 0.0)

        curr_cht = feat["current"]
        slope = feat["short_slope"]
        curv = feat["second_derivative"]
        std_dev = feat["short_std"]
        long_std = feat["long_std"]

        fault_limit = self.SAFETY_ENVELOPES["cht"]["fault_limit"] # 145.0 °C
        nominal_max = self.SAFETY_ENVELOPES["cht"]["nominal_max"] # 135.0 °C

        # Persistence Filter for Isolated Single-Frame Spikes:
        # High std dev with zero sustained long slope and EWMA well below nominal max
        is_isolated_spike = (std_dev > 5.0 and feat["long_slope"] < 0.10 and feat["ewma"] < nominal_max and len(self.signal_history[key]) > 10)

        # 30-Second Trajectory Forecast
        forecast_horizon = 30.0
        curv_term = (0.5 * curv * (forecast_horizon ** 2)) if (len(self.signal_history[key]) >= 30 and slope >= 0.15 and abs(curv) >= 0.01) else 0.0
        poly_forecasted_val = curr_cht + (slope * forecast_horizon) + curv_term

        forecast_mode = "STATISTICAL_FALLBACK"
        gru_30s_val = None
        gru_60s_val = None

        if gru_forecast_res and gru_forecast_res.get("status") == "READY":
            forecast_mode = "GRU_MODEL"
            fc = gru_forecast_res.get("forecast", {})
            param_key = f"cht{cyl_idx}" if f"cht{cyl_idx}" in fc.get("30s", {}) else "cht1"
            gru_30s_val = float(fc.get("30s", {}).get(param_key, curr_cht))
            gru_60s_val = float(fc.get("60s", {}).get(param_key, curr_cht))
            forecasted_val = max(gru_30s_val, gru_60s_val, poly_forecasted_val if slope >= 0.35 else 0.0)
        else:
            if slope >= 0.10 or curr_cht >= 128.0:
                neural_30s_cht = neural_forecast.get("predicted_values", {}).get("30s", {}).get("cht", curr_cht) if neural_forecast else curr_cht
            else:
                neural_30s_cht = curr_cht
            forecasted_val = max(poly_forecasted_val, neural_30s_cht)

        # Time-To-Risk Estimation: Immediate limit check -> GRU trajectory intercept -> Linear fallback -> No breach predicted
        risk_status = "NO_BREACH_PREDICTED"
        time_to_risk = None

        if curr_cht >= fault_limit:
            time_to_risk = 0.0
            risk_status = "LIMIT_EXCEEDED"
        elif forecast_mode == "GRU_MODEL" and gru_30s_val is not None and gru_30s_val >= fault_limit:
            time_to_risk = round(max(1.0, 30.0 * (fault_limit - curr_cht) / max(0.01, gru_30s_val - curr_cht)), 1)
            risk_status = "PREDICTED_BREACH"
        elif forecast_mode == "GRU_MODEL" and gru_60s_val is not None and gru_60s_val >= fault_limit:
            time_to_risk = round(max(30.0, 30.0 + 30.0 * (fault_limit - (gru_30s_val or curr_cht)) / max(0.01, gru_60s_val - (gru_30s_val or curr_cht))), 1)
            risk_status = "PREDICTED_BREACH"
        elif slope >= 0.10:
            delta_to_limit = fault_limit - curr_cht
            ttr_est = delta_to_limit / slope
            if ttr_est <= 60.0:
                time_to_risk = round(ttr_est, 1)
                risk_status = "PREDICTED_BREACH"
            else:
                time_to_risk = None
                risk_status = "NO_BREACH_PREDICTED"
        else:
            time_to_risk = None
            risk_status = "NO_BREACH_PREDICTED" if forecast_mode == "GRU_MODEL" else "FORECAST_UNAVAILABLE"

        # Normalized Degradation Score Calculation [0.0, 1.0]
        raw_ae = float(ae_res.get("anomaly_score", 0.0))
        cusum_active = bool(cusum_res.get("cusum_alert_active", False))
        res_val = float(physics_state.get("residuals", {}).get("cht_delta", 0.0))

        if curr_cht >= fault_limit:
            deg_score = 1.0
        else:
            deg_score = min(0.99, max(0.0,
                (min(1.0, max(0.0, (curr_cht - 120.0) / 25.0)) * 0.40) +
                (min(1.0, max(0.0, slope / 1.5)) * 0.30) +
                (raw_ae * 0.15) +
                (0.05 if cusum_active else 0.0) +
                (min(1.0, max(0.0, abs(res_val) / 10.0)) * 0.10)
            ))
        deg_score = round(float(deg_score), 3)

        # Status Determination
        status = "NOMINAL"
        risk_prob = 0.05
        evidence = []

        is_gru_risk = (forecast_mode == "GRU_MODEL" and ((gru_30s_val and gru_30s_val >= fault_limit) or (gru_60s_val and gru_60s_val >= fault_limit)))
        has_history = len(self.signal_history[key]) >= 30

        if curr_cht >= fault_limit:
            status = "ACTIVE_FAULT"
            risk_prob = 1.0
            evidence.append(f"CRITICAL: CHT{cyl_idx} observed at {curr_cht:.1f}°C, exceeding safety limit of {fault_limit}°C (LIMIT EXCEEDED).")
        elif (is_gru_risk or (has_history and ((forecasted_val >= fault_limit and slope >= 0.35) or (curr_cht >= 135.0 and slope >= 0.25) or ((time_to_risk is not None and time_to_risk <= 45.0) and slope >= 0.25)))) and not is_isolated_spike:
            status = "PREDICTIVE_RISK"
            risk_prob = min(0.95, round(0.50 + (slope * 0.4) + (raw_ae * 0.3), 2))
            ttr_str = f"{time_to_risk:.1f}s" if time_to_risk is not None else "predictive forecast"
            evidence.append(f"PREDICTIVE RISK: CHT{cyl_idx} currently {curr_cht:.1f}°C (< limit {fault_limit}°C).")
            if forecast_mode == "GRU_MODEL":
                evidence.append(f"GRU 30-second forecast projects CHT{cyl_idx} at {forecasted_val:.1f}°C (Limit breach in {ttr_str}).")
            else:
                evidence.append(f"Trajectory slope = {slope:+.2f}°C/s | Statistical projected CHT = {forecasted_val:.1f}°C (Limit breach in {ttr_str}).")
            evidence.append(f"PINN physics residual slope = {res_slope:+.2f}°C/s | AE score slope = {ae_slope:+.3f}/s.")
        elif (slope >= 0.12 or curr_cht > nominal_max or feat["long_slope"] >= 0.10 or cusum_active) and not is_isolated_spike:
            status = "DEGRADATION_DETECTED"
            risk_prob = 0.40
            evidence.append(f"DEGRADATION DETECTED: CHT{cyl_idx} thermal drift detected ({slope:+.2f}°C/s).")
            evidence.append(f"Moving EWMA temperature = {feat['ewma']:.1f}°C (Nominal ceiling {nominal_max}°C).")
        else:
            status = "NOMINAL"
            evidence.append(f"NOMINAL: Thermal subsystem operating within nominal bounds (CHT{cyl_idx} = {curr_cht:.1f}°C).")

        return {
            "timestamp": t,
            "source_sequence_number": self.sequence_number,
            "sequence_number": self.sequence_number,
            "subsystem": "Thermal",
            "affected_subsystem": "THERMAL",
            "component": f"CYLINDER_{cyl_idx}",
            "affected_component": f"Cylinder {cyl_idx}",
            "primary_parameter": f"cht{cyl_idx}",
            "primary_parameter_label": f"CHT{cyl_idx}",
            "primary_parameter_value": round(curr_cht, 1),
            "unit": "°C",
            "reference_envelope": {
                "lower": 110.0,
                "upper": fault_limit,
                "unit": "°C"
            },
            "reference_envelope_text": f"110.0 - {fault_limit} °C",
            "current_value": round(curr_cht, 1),
            "short_slope": round(slope, 4),
            "long_slope": round(feat["long_slope"], 4),
            "variance_trend": round(feat["variance_trend"], 4),
            "anomaly_score": round(raw_ae, 3),
            "anomaly_score_slope": round(ae_slope, 4),
            "cusum_detected": cusum_active,
            "physics_residual": round(res_val, 2),
            "residual_slope": round(res_slope, 4),
            "degradation_score": deg_score,
            "predictive_risk_score": risk_prob,
            "estimated_time_to_risk": time_to_risk,
            "estimated_time_to_risk_seconds": time_to_risk,
            "risk_status": risk_status,
            "predicted_failure_mode": "THERMAL_DEGRADATION",
            "evidence_sources": evidence,
            "predictive_status": status,
            "status": status,
            "current_state": status,
            "forecast_mode": forecast_mode,
            "predicted_risk_probability": risk_prob,
            "trends": feat,
            "future_forecast": {
                "forecast_horizon_seconds": forecast_horizon,
                "forecasted_value": round(forecasted_val, 1),
                "target_threshold": fault_limit
            }
        }

    def _assess_lubrication_subsystem(
        self, t: float, telemetry: Dict[str, Any], physics_state: Dict[str, Any], ae_res: Dict[str, Any], cusum_res: Dict[str, Any], gru_forecast_res: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        feat = self.extract_temporal_features("oil_press")
        oil_res_history = list(self.physics_residual_history["oil_press"])

        res_slope, _ = self._compute_slope(list(self.timestamps), oil_res_history) if len(oil_res_history) >= 5 else (0.0, 0.0)

        curr_p = feat["current"]
        slope = feat["short_slope"]
        curv = feat["second_derivative"]
        std_dev = feat["short_std"]

        fault_limit = self.SAFETY_ENVELOPES["oil_press"]["fault_limit"] # 2.50 bar
        nominal_min = self.SAFETY_ENVELOPES["oil_press"]["nominal_min"] # 3.50 bar

        is_isolated_spike = (std_dev > 0.40 and abs(slope) < 0.01 and feat["ewma"] > nominal_min and len(self.signal_history["oil_press"]) > 10)

        forecast_horizon = 30.0
        curv_term = (0.5 * curv * (forecast_horizon ** 2)) if (len(self.signal_history["oil_press"]) >= 30 and slope <= -0.015 and abs(curv) >= 0.01) else 0.0
        poly_forecasted_val = curr_p + (slope * forecast_horizon) + curv_term

        forecast_mode = "STATISTICAL_FALLBACK"
        gru_30s_val = None
        gru_60s_val = None

        if gru_forecast_res and gru_forecast_res.get("status") == "READY":
            forecast_mode = "GRU_MODEL"
            fc = gru_forecast_res.get("forecast", {})
            gru_30s_val = float(fc.get("30s", {}).get("oil_pressure", curr_p))
            gru_60s_val = float(fc.get("60s", {}).get("oil_pressure", curr_p))
            forecasted_val = min(gru_30s_val, gru_60s_val)
        else:
            forecasted_val = poly_forecasted_val

        # Time-To-Risk Estimation: Lower limit check -> GRU trajectory -> Linear fallback -> No breach predicted
        risk_status = "NO_BREACH_PREDICTED"
        time_to_risk = None

        if curr_p <= fault_limit:
            time_to_risk = 0.0
            risk_status = "LIMIT_EXCEEDED"
        elif forecast_mode == "GRU_MODEL" and gru_30s_val is not None and gru_30s_val <= fault_limit:
            time_to_risk = round(max(1.0, 30.0 * (curr_p - fault_limit) / max(0.01, curr_p - gru_30s_val)), 1)
            risk_status = "PREDICTED_BREACH"
        elif forecast_mode == "GRU_MODEL" and gru_60s_val is not None and gru_60s_val <= fault_limit:
            time_to_risk = round(max(30.0, 30.0 + 30.0 * ((gru_30s_val or curr_p) - fault_limit) / max(0.01, (gru_30s_val or curr_p) - gru_60s_val)), 1)
            risk_status = "PREDICTED_BREACH"
        elif slope <= -0.010:
            delta_to_limit = curr_p - fault_limit
            ttr_est = delta_to_limit / abs(slope)
            if ttr_est <= 60.0:
                time_to_risk = round(ttr_est, 1)
                risk_status = "PREDICTED_BREACH"
            else:
                time_to_risk = None
                risk_status = "NO_BREACH_PREDICTED"
        else:
            time_to_risk = None
            risk_status = "NO_BREACH_PREDICTED" if forecast_mode == "GRU_MODEL" else "FORECAST_UNAVAILABLE"

        raw_ae = float(ae_res.get("anomaly_score", 0.0))
        cusum_active = bool(cusum_res.get("cusum_alert_active", False))
        res_val = float(physics_state.get("residuals", {}).get("oil_press_delta", 0.0))

        deg_score = min(1.0, max(0.0,
            (min(1.0, max(0.0, (4.20 - curr_p) / 1.70)) * 0.35) +
            (min(1.0, max(0.0, abs(slope) / 0.08)) * 0.30) +
            (raw_ae * 0.15) +
            (0.10 if cusum_active else 0.0) +
            (min(1.0, max(0.0, abs(res_val) / 0.60)) * 0.10)
        ))
        deg_score = round(float(deg_score), 3)

        status = "NOMINAL"
        risk_prob = 0.05
        evidence = []

        is_gru_risk = (forecast_mode == "GRU_MODEL" and ((gru_30s_val and gru_30s_val <= fault_limit) or (gru_60s_val and gru_60s_val <= fault_limit)))
        has_history = len(self.signal_history["oil_press"]) >= 30

        if curr_p <= fault_limit:
            status = "ACTIVE_FAULT"
            risk_prob = 1.0
            evidence.append(f"CRITICAL: Oil pressure observed at {curr_p:.2f} bar, below safety limit of {fault_limit} bar (LIMIT EXCEEDED).")
        elif (is_gru_risk or (forecast_mode == "STATISTICAL_FALLBACK" and has_history and ((forecasted_val <= fault_limit and slope <= -0.015) or (slope <= -0.025 and curr_p <= 3.80) or ((time_to_risk is not None and time_to_risk <= 45.0) and slope <= -0.015)))) and not is_isolated_spike:
            status = "PREDICTIVE_RISK"
            risk_prob = min(0.95, round(0.50 + (abs(slope) * 8.0), 2))
            ttr_str = f"{time_to_risk:.1f}s" if time_to_risk is not None else "predictive forecast"
            evidence.append(f"PREDICTIVE RISK: Oil pressure currently {curr_p:.2f} bar (> limit {fault_limit} bar).")
            evidence.append(f"Forecast Mode = {forecast_mode} | Pressure decay slope = {slope:+.3f} bar/s.")
            evidence.append(f"Projected pressure forecast = {forecasted_val:.2f} bar (Limit breach in {ttr_str}).")
        elif (slope <= -0.008 or curr_p < nominal_min or feat["long_slope"] <= -0.006 or cusum_active) and not is_isolated_spike:
            status = "DEGRADATION_DETECTED"
            risk_prob = 0.40
            evidence.append(f"DEGRADATION DETECTED: Oil pressure decay trend detected ({slope:+.3f} bar/s).")
        else:
            status = "NOMINAL"
            evidence.append(f"NOMINAL: Lubrication subsystem operating within nominal bounds (Oil Pressure = {curr_p:.2f} bar).")

        return {
            "timestamp": t,
            "source_sequence_number": self.sequence_number,
            "sequence_number": self.sequence_number,
            "subsystem": "Lubrication",
            "affected_subsystem": "LUBRICATION",
            "component": "OIL_SYSTEM",
            "affected_component": "Oil System",
            "primary_parameter": "oil_pressure",
            "primary_parameter_label": "Oil Pressure",
            "primary_parameter_value": round(curr_p, 2),
            "unit": "bar",
            "reference_envelope": {
                "lower": fault_limit,
                "upper": 6.00,
                "unit": "bar"
            },
            "reference_envelope_text": f"{fault_limit} - 6.00 bar",
            "current_value": round(curr_p, 2),
            "short_slope": round(slope, 4),
            "long_slope": round(feat["long_slope"], 4),
            "variance_trend": round(feat["variance_trend"], 4),
            "anomaly_score": round(raw_ae, 3),
            "anomaly_score_slope": 0.0,
            "cusum_detected": cusum_active,
            "physics_residual": round(res_val, 2),
            "residual_slope": round(res_slope, 4),
            "degradation_score": deg_score,
            "predictive_risk_score": risk_prob,
            "estimated_time_to_risk": time_to_risk,
            "estimated_time_to_risk_seconds": time_to_risk,
            "risk_status": risk_status,
            "predicted_failure_mode": "LUBRICATION_DEGRADATION",
            "evidence_sources": evidence,
            "predictive_status": status,
            "status": status,
            "current_state": status,
            "forecast_mode": forecast_mode,
            "predicted_risk_probability": risk_prob,
            "trends": feat,
            "future_forecast": {
                "forecast_horizon_seconds": forecast_horizon,
                "forecasted_value": round(forecasted_val, 2),
                "target_threshold": fault_limit
            }
        }

    def _assess_mechanical_subsystem(
        self, t: float, telemetry: Dict[str, Any], physics_state: Dict[str, Any], ae_res: Dict[str, Any], cusum_res: Dict[str, Any], gru_forecast_res: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        feat = self.extract_temporal_features("vibration_rms")

        curr_vib = feat["current"]
        slope = feat["short_slope"]
        curv = feat["second_derivative"]
        std_dev = feat["short_std"]
        var_trend = feat["variance_trend"]

        fault_limit = self.SAFETY_ENVELOPES["vibration_rms"]["fault_limit"] # 2.50 g
        nominal_max = self.SAFETY_ENVELOPES["vibration_rms"]["nominal_max"] # 1.50 g

        is_isolated_spike = (std_dev > 0.50 and slope < 0.01 and feat["ewma"] < nominal_max and len(self.signal_history["vibration_rms"]) > 10)

        forecast_horizon = 30.0
        curv_term = (0.5 * curv * (forecast_horizon ** 2)) if (len(self.signal_history["vibration_rms"]) >= 30 and slope >= 0.015 and abs(curv) >= 0.01) else 0.0
        poly_forecasted_val = curr_vib + (slope * forecast_horizon) + curv_term

        forecast_mode = "STATISTICAL_FALLBACK"
        gru_30s_val = None
        gru_60s_val = None

        if gru_forecast_res and gru_forecast_res.get("status") == "READY":
            forecast_mode = "GRU_MODEL"
            fc = gru_forecast_res.get("forecast", {})
            gru_30s_val = float(fc.get("30s", {}).get("vibration_rms", curr_vib))
            gru_60s_val = float(fc.get("60s", {}).get("vibration_rms", curr_vib))
            forecasted_val = max(gru_30s_val, gru_60s_val)
        else:
            forecasted_val = poly_forecasted_val

        # Time-To-Risk Estimation: Upper limit check -> GRU trajectory -> Linear fallback -> No breach predicted
        risk_status = "NO_BREACH_PREDICTED"
        time_to_risk = None

        if curr_vib >= fault_limit:
            time_to_risk = 0.0
            risk_status = "LIMIT_EXCEEDED"
        elif forecast_mode == "GRU_MODEL" and gru_30s_val is not None and gru_30s_val >= fault_limit:
            time_to_risk = round(max(1.0, 30.0 * (fault_limit - curr_vib) / max(0.01, gru_30s_val - curr_vib)), 1)
            risk_status = "PREDICTED_BREACH"
        elif forecast_mode == "GRU_MODEL" and gru_60s_val is not None and gru_60s_val >= fault_limit:
            time_to_risk = round(max(30.0, 30.0 + 30.0 * (fault_limit - (gru_30s_val or curr_vib)) / max(0.01, gru_60s_val - (gru_30s_val or curr_vib))), 1)
            risk_status = "PREDICTED_BREACH"
        elif slope >= 0.010:
            delta_to_limit = fault_limit - curr_vib
            ttr_est = delta_to_limit / slope
            if ttr_est <= 60.0:
                time_to_risk = round(ttr_est, 1)
                risk_status = "PREDICTED_BREACH"
            else:
                time_to_risk = None
                risk_status = "NO_BREACH_PREDICTED"
        else:
            time_to_risk = None
            risk_status = "NO_BREACH_PREDICTED" if forecast_mode == "GRU_MODEL" else "FORECAST_UNAVAILABLE"

        raw_ae = float(ae_res.get("anomaly_score", 0.0))
        cusum_active = bool(cusum_res.get("cusum_alert_active", False))

        deg_score = min(1.0, max(0.0,
            (min(1.0, max(0.0, (curr_vib - 1.12) / 1.38)) * 0.35) +
            (min(1.0, max(0.0, slope / 0.05)) * 0.30) +
            (raw_ae * 0.15) +
            (0.10 if cusum_active else 0.0) +
            (min(1.0, max(0.0, var_trend / 0.02)) * 0.10)
        ))
        deg_score = round(float(deg_score), 3)

        status = "NOMINAL"
        risk_prob = 0.05
        evidence = []

        is_gru_risk = (forecast_mode == "GRU_MODEL" and ((gru_30s_val and gru_30s_val >= fault_limit) or (gru_60s_val and gru_60s_val >= fault_limit)))
        has_history = len(self.signal_history["vibration_rms"]) >= 30

        if curr_vib >= fault_limit:
            status = "ACTIVE_FAULT"
            risk_prob = 1.0
            evidence.append(f"CRITICAL: Vibration RMS observed at {curr_vib:.2f}g, exceeding safety limit of {fault_limit}g (LIMIT EXCEEDED).")
        elif (is_gru_risk or (forecast_mode == "STATISTICAL_FALLBACK" and has_history and ((forecasted_val >= fault_limit and slope >= 0.020) or (slope >= 0.035 and curr_vib >= 1.25) or (var_trend >= 0.012 and slope >= 0.015) or ((time_to_risk is not None and time_to_risk <= 45.0) and slope >= 0.018)))) and not is_isolated_spike:
            status = "PREDICTIVE_RISK"
            risk_prob = min(0.95, round(0.50 + (slope * 8.0) + (var_trend * 10.0), 2))
            ttr_str = f"{time_to_risk:.1f}s" if time_to_risk is not None else "predictive forecast"
            evidence.append(f"PREDICTIVE RISK: Vibration RMS currently {curr_vib:.2f}g (< limit {fault_limit}g).")
            evidence.append(f"Forecast Mode = {forecast_mode} | Vibration RMS slope = {slope:+.3f}g/s.")
            evidence.append(f"Projected vibration forecast = {forecasted_val:.2f}g (Limit breach in {ttr_str}).")
        elif (slope >= 0.008 or curr_vib > nominal_max or var_trend >= 0.004 or cusum_active) and not is_isolated_spike:
            status = "DEGRADATION_DETECTED"
            risk_prob = 0.40
            evidence.append(f"DEGRADATION DETECTED: Mechanical vibration growth detected ({slope:+.3f}g/s).")
        else:
            status = "NOMINAL"
            evidence.append(f"NOMINAL: Mechanical subsystem operating within nominal bounds (Vibration RMS = {curr_vib:.2f}g).")

        return {
            "timestamp": t,
            "source_sequence_number": self.sequence_number,
            "sequence_number": self.sequence_number,
            "subsystem": "Mechanical",
            "affected_subsystem": "MECHANICAL",
            "component": "MECHANICAL_BEARING",
            "affected_component": "Crankshaft Bearing",
            "primary_parameter": "vibration_rms",
            "primary_parameter_label": "Vibration RMS",
            "primary_parameter_value": round(curr_vib, 2),
            "unit": "g",
            "reference_envelope": {
                "lower": 0.0,
                "upper": fault_limit,
                "unit": "g"
            },
            "reference_envelope_text": f"0.00 - {fault_limit} g",
            "current_value": round(curr_vib, 2),
            "short_slope": round(slope, 4),
            "long_slope": round(feat["long_slope"], 4),
            "variance_trend": round(var_trend, 4),
            "anomaly_score": round(raw_ae, 3),
            "anomaly_score_slope": 0.0,
            "cusum_detected": cusum_active,
            "physics_residual": 0.0,
            "residual_slope": 0.0,
            "degradation_score": deg_score,
            "predictive_risk_score": risk_prob,
            "estimated_time_to_risk": time_to_risk,
            "estimated_time_to_risk_seconds": time_to_risk,
            "predicted_failure_mode": "MECHANICAL_VIBRATION_DEGRADATION",
            "evidence_sources": evidence,
            "predictive_status": status,
            "status": status,
            "current_state": status,
            "forecast_mode": forecast_mode,
            "predicted_risk_probability": risk_prob,
            "trends": feat,
            "predicted_failure_mode": "MECHANICAL_VIBRATION_DEGRADATION",
            "evidence_sources": evidence,
            "predictive_status": status,
            "status": status,
            "current_state": status,
            "forecast_mode": forecast_mode,
            "status": status,
            "current_state": status,
            "predicted_risk_probability": risk_prob,
            "trends": feat,
            "future_forecast": {
                "forecast_horizon_seconds": forecast_horizon,
                "forecasted_value": round(forecasted_val, 2),
                "target_threshold": fault_limit
            }
        }

    def _assess_combustion_subsystem(
        self, t: float, telemetry: Dict[str, Any], physics_state: Dict[str, Any], ae_res: Dict[str, Any], cusum_res: Dict[str, Any]
    ) -> Dict[str, Any]:
        egt_vals = [float(telemetry.get(f"egt{i}", 750.0)) for i in range(1, 5)]
        max_egt = max(egt_vals)
        max_cyl = egt_vals.index(max_egt) + 1
        min_egt = min(egt_vals)
        min_cyl = egt_vals.index(min_egt) + 1
        egt_spread = max_egt - min_egt

        # Check if high EGT is coupled with a high CHT thermal fault on max_cyl
        max_cht_val = float(telemetry.get(f"cht{max_cyl}", 120.0))
        is_thermal_coupled = (max_cht_val >= 135.0)

        key = f"egt{max_cyl}" if is_thermal_coupled else f"egt{min_cyl}"
        feat = self.extract_temporal_features(key)
        curr_egt = feat["current"]
        slope = feat["short_slope"]

        fault_limit = self.SAFETY_ENVELOPES["egt_spread"]["fault_limit"] # 90.0 °C
        nominal_max = self.SAFETY_ENVELOPES["egt_spread"]["nominal_max"] # 45.0 °C

        raw_ae = float(ae_res.get("anomaly_score", 0.0))
        cusum_active = bool(cusum_res.get("cusum_alert_active", False))

        raw_deg = (
            (min(1.0, max(0.0, (egt_spread - 10.0) / 80.0)) * 0.40) +
            (min(1.0, max(0.0, abs(slope) / 2.0)) * 0.30) +
            (raw_ae * 0.20) +
            (0.10 if cusum_active else 0.0)
        )
        if is_thermal_coupled:
            # Cap combustion degradation score below Thermal so Thermal remains primary root cause
            deg_score = min(0.65, max(0.0, raw_deg))
        else:
            deg_score = min(1.0, max(0.0, raw_deg))
        deg_score = round(float(deg_score), 3)

        status = "NOMINAL"
        risk_prob = 0.05
        evidence = []

        comb_risk_status = "NO_BREACH_PREDICTED"
        comb_ttr = None

        if egt_spread >= fault_limit:
            comb_ttr = 0.0
            comb_risk_status = "LIMIT_EXCEEDED"
        elif slope >= 0.50:
            delta_to_limit = fault_limit - egt_spread
            ttr_est = delta_to_limit / slope
            if ttr_est <= 60.0:
                comb_ttr = round(ttr_est, 1)
                comb_risk_status = "PREDICTED_BREACH"
            else:
                comb_ttr = None
                comb_risk_status = "NO_BREACH_PREDICTED"

        if egt_spread >= fault_limit:
            status = "ACTIVE_FAULT"
            risk_prob = 1.0
            evidence.append(f"CRITICAL: EGT spread reached {egt_spread:.1f}°C (Cylinder {max_cyl} high at {max_egt:.1f}°C, Cylinder {min_cyl} low at {min_egt:.1f}°C) (LIMIT EXCEEDED).")
        elif (egt_spread >= 65.0 or (slope <= -1.20 and egt_spread >= 35.0)):
            status = "PREDICTIVE_RISK"
            risk_prob = 0.85
            evidence.append(f"PREDICTIVE RISK: Combustion EGT spread variation ({egt_spread:.1f}°C, Limit: {fault_limit}°C).")
        elif egt_spread > nominal_max or slope <= -0.40 or cusum_active:
            status = "DEGRADATION_DETECTED"
            risk_prob = 0.40
            evidence.append(f"DEGRADATION DETECTED: EGT spread variation ({egt_spread:.1f}°C) across cylinders.")
        else:
            status = "NOMINAL"
            evidence.append(f"NOMINAL: Combustion subsystem nominal (EGT spread = {egt_spread:.1f}°C).")

        affected_comp = f"Cylinder {max_cyl} (High EGT)" if is_thermal_coupled else f"Cylinder {min_cyl} (Low EGT)"

        return {
            "timestamp": t,
            "source_sequence_number": self.sequence_number,
            "sequence_number": self.sequence_number,
            "subsystem": "Combustion",
            "affected_subsystem": "COMBUSTION",
            "component": f"CYLINDER_{max_cyl if is_thermal_coupled else min_cyl}",
            "affected_component": affected_comp,
            "primary_parameter": "egt_spread",
            "primary_parameter_label": "EGT Spread",
            "primary_parameter_value": round(egt_spread, 1),
            "egt_max_value": round(max_egt, 1),
            "egt_max_cylinder": f"Cylinder {max_cyl}",
            "egt_min_value": round(min_egt, 1),
            "egt_min_cylinder": f"Cylinder {min_cyl}",
            "egt_spread": round(egt_spread, 1),
            "egt_spread_limit": fault_limit,
            "unit": "°C",
            "reference_envelope": {
                "lower": 0.0,
                "upper": fault_limit,
                "unit": "°C"
            },
            "reference_envelope_text": f"0.0 - {fault_limit} °C",
            "current_value": round(egt_spread, 1),
            "short_slope": round(slope, 4),
            "long_slope": round(feat["long_slope"], 4),
            "variance_trend": round(feat["variance_trend"], 4),
            "anomaly_score": round(raw_ae, 3),
            "anomaly_score_slope": 0.0,
            "cusum_detected": cusum_active,
            "physics_residual": round(float(physics_state.get("residuals", {}).get("egt_delta", 0.0)), 2),
            "residual_slope": 0.0,
            "degradation_score": deg_score,
            "predictive_risk_score": risk_prob,
            "estimated_time_to_risk": comb_ttr,
            "estimated_time_to_risk_seconds": comb_ttr,
            "risk_status": comb_risk_status,
            "predicted_failure_mode": "COMBUSTION_DEGRADATION",
            "evidence_sources": evidence,
            "predictive_status": status,
            "status": status,
            "current_state": status,
            "predicted_risk_probability": risk_prob,
            "trends": feat,
            "future_forecast": {
                "forecast_horizon_seconds": 30.0,
                "forecasted_value": round(egt_spread, 1),
                "target_threshold": fault_limit
            }
        }

    def _assess_electrical_subsystem(
        self, t: float, telemetry: Dict[str, Any], physics_state: Dict[str, Any], ae_res: Dict[str, Any], cusum_res: Dict[str, Any]
    ) -> Dict[str, Any]:
        feat = self.extract_temporal_features("battery_volt")

        curr_v = feat["current"]
        slope = feat["short_slope"]

        fault_min = self.SAFETY_ENVELOPES["battery_volt"]["fault_min"] # 11.50 V
        fault_max = self.SAFETY_ENVELOPES["battery_volt"]["fault_max"] # 15.50 V
        nominal_min = self.SAFETY_ENVELOPES["battery_volt"]["nominal_min"] # 12.80 V
        nominal_max = self.SAFETY_ENVELOPES["battery_volt"]["nominal_max"] # 14.80 V

        raw_ae = float(ae_res.get("anomaly_score", 0.0))
        cusum_active = bool(cusum_res.get("cusum_alert_active", False))

        deg_score = min(1.0, max(0.0,
            (min(1.0, max(0.0, abs(curr_v - 14.10) / 2.60)) * 0.40) +
            (min(1.0, max(0.0, abs(slope) / 0.30)) * 0.40) +
            (raw_ae * 0.20)
        ))
        deg_score = round(float(deg_score), 3)

        elec_risk_status = "NO_BREACH_PREDICTED"
        elec_ttr = None

        if curr_v <= fault_min or curr_v >= fault_max:
            elec_ttr = 0.0
            elec_risk_status = "LIMIT_EXCEEDED"
        elif abs(slope) >= 0.05:
            delta_to_limit = (curr_v - fault_min) if slope < 0 else (fault_max - curr_v)
            ttr_est = delta_to_limit / abs(slope)
            if ttr_est <= 60.0:
                elec_ttr = round(ttr_est, 1)
                elec_risk_status = "PREDICTED_BREACH"

        status = "NOMINAL"
        risk_prob = 0.05
        evidence = []

        if curr_v <= fault_min or curr_v >= fault_max:
            status = "ACTIVE_FAULT"
            risk_prob = 1.0
            evidence.append(f"CRITICAL: Battery bus voltage observed at {curr_v:.2f}V, outside safety bounds (LIMIT EXCEEDED).")
        elif (abs(slope) >= 0.150 and (curr_v <= 12.5 or curr_v >= 15.0)):
            status = "PREDICTIVE_RISK"
            risk_prob = 0.80
            evidence.append(f"PREDICTIVE RISK: Bus voltage drift detected ({curr_v:.2f}V, slope {slope:+.3f}V/s).")
        elif abs(slope) >= 0.060 or cusum_active:
            status = "DEGRADATION_DETECTED"
            risk_prob = 0.35
            evidence.append(f"DEGRADATION DETECTED: Bus voltage variation ({slope:+.3f}V/s).")
        else:
            status = "NOMINAL"
            evidence.append(f"NOMINAL: Electrical subsystem nominal (Voltage = {curr_v:.2f}V).")

        return {
            "timestamp": t,
            "source_sequence_number": self.sequence_number,
            "sequence_number": self.sequence_number,
            "subsystem": "Electrical",
            "affected_subsystem": "ELECTRICAL",
            "component": "ELECTRICAL_BUS",
            "affected_component": "Battery Bus",
            "primary_parameter": "battery_volt",
            "primary_parameter_label": "Battery Voltage",
            "primary_parameter_value": round(curr_v, 2),
            "unit": "V",
            "reference_envelope": {
                "lower": fault_min,
                "upper": fault_max,
                "unit": "V"
            },
            "reference_envelope_text": f"{fault_min} - {fault_max} V",
            "current_value": round(curr_v, 2),
            "short_slope": round(slope, 4),
            "long_slope": round(feat["long_slope"], 4),
            "variance_trend": round(feat["variance_trend"], 4),
            "anomaly_score": round(raw_ae, 3),
            "anomaly_score_slope": 0.0,
            "cusum_detected": cusum_active,
            "physics_residual": 0.0,
            "residual_slope": 0.0,
            "degradation_score": deg_score,
            "predictive_risk_score": risk_prob,
            "estimated_time_to_risk": elec_ttr,
            "estimated_time_to_risk_seconds": elec_ttr,
            "risk_status": elec_risk_status,
            "predicted_failure_mode": "SENSOR_DRIFT",
            "evidence_sources": evidence,
            "predictive_status": status,
            "status": status,
            "current_state": status,
            "predicted_risk_probability": risk_prob,
            "trends": feat,
            "future_forecast": {
                "forecast_horizon_seconds": 30.0,
                "forecasted_value": round(curr_v + (slope * 30.0), 2),
                "target_threshold": fault_min if slope < 0 else fault_max
            }
        }
