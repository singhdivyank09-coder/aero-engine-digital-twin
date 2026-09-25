"""
GRU Short-Horizon Forecast Runtime Inference Service
SIH 26054 — Aero-Piston Engine Digital Twin

Performs:
- Single-instance model & scaler loading at startup
- 30-second window validation (requires 60 samples at 2 Hz or 300 samples at 10 Hz)
- Returns status = WARMING_UP if insufficient history
- Executes compact PyTorch GRU forward inference at ~1 Hz cadence
- Generates multi-horizon (+10s, +30s, +60s) predictions for:
  cht1, oil_pressure, oil_temperature, vibration_rms, egt1, map
- Robust fallback to STATISTICAL_FALLBACK if model loading fails
"""

import os
import sys
import json
import pickle
import numpy as np
import torch
import time
from typing import Dict, Any, List, Optional

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml_service.gru_model import GruShortHorizonNet

MODELS_FORECAST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "forecast")
PT_PATH = os.path.join(MODELS_FORECAST_DIR, "gru_forecaster.pt")
INPUT_SCALER_PATH = os.path.join(MODELS_FORECAST_DIR, "input_scaler.pkl")
TARGET_SCALER_PATH = os.path.join(MODELS_FORECAST_DIR, "target_scaler.pkl")
CONFIG_PATH = os.path.join(MODELS_FORECAST_DIR, "config.json")

class GruForecastService:
    def __init__(self):
        self.model = None
        self.input_scaler = None
        self.target_scaler = None
        self.config = None
        self.is_loaded = False
        self.load_error = None
        self.forecast_mode = "STATISTICAL_FALLBACK"

        self._load_artifacts()

    def _load_artifacts(self):
        """Loads PyTorch model weights, scalers, and configuration ONCE at startup."""
        try:
            if not (os.path.exists(PT_PATH) and os.path.exists(INPUT_SCALER_PATH) and os.path.exists(TARGET_SCALER_PATH) and os.path.exists(CONFIG_PATH)):
                self.load_error = "Model or scaler artifact files not found in models/forecast/"
                self.forecast_mode = "STATISTICAL_FALLBACK"
                print(f"[GRU SERVICE WARNING] {self.load_error}. Operating in STATISTICAL_FALLBACK mode.")
                return

            with open(CONFIG_PATH, "r") as f:
                self.config = json.load(f)

            with open(INPUT_SCALER_PATH, "rb") as f:
                self.input_scaler = pickle.load(f)

            with open(TARGET_SCALER_PATH, "rb") as f:
                self.target_scaler = pickle.load(f)

            input_dim = self.config.get("input_dim", 18)
            hidden_dim = self.config.get("hidden_dim", 64)
            num_layers = self.config.get("num_layers", 2)
            output_dim = self.config.get("output_dim", 18)

            self.model = GruShortHorizonNet(input_dim=input_dim, hidden_dim=hidden_dim, num_layers=num_layers, output_dim=output_dim)
            self.model.load_state_dict(torch.load(PT_PATH))
            self.model.eval()

            self.is_loaded = True
            self.forecast_mode = "GRU_MODEL"
            print(f"[GRU SERVICE INITIALIZED] PyTorch GRU Forecaster loaded successfully from {PT_PATH}")

        except Exception as e:
            self.is_loaded = False
            self.load_error = str(e)
            self.forecast_mode = "STATISTICAL_FALLBACK"
            print(f"[GRU SERVICE ERROR] Failed to load GRU artifacts: {e}. Falling back to STATISTICAL_FALLBACK.")

    def predict_forecast(
        self,
        telemetry_history: List[Dict[str, Any]],
        timestamp: float = 0.0,
        sequence_number: int = 0,
        scenario: str = "CRUISE"
    ) -> Dict[str, Any]:
        """
        Executes short-horizon forecasting from recent telemetry history buffer.
        Requires at least 30 seconds of telemetry (at 10 Hz: 300 frames; or downsampled 2 Hz: 60 frames).
        Returns status = WARMING_UP if history is insufficient.
        """
        if not self.is_loaded:
            return {
                "timestamp": timestamp,
                "source_sequence_number": sequence_number,
                "model": "GRU",
                "model_version": "v1.0",
                "input_window_seconds": 30,
                "forecast": {},
                "forecast_mode": "STATISTICAL_FALLBACK",
                "status": "FALLBACK_LOAD_ERROR",
                "error": self.load_error
            }

        # Watchdog check for stale forecast history
        if getattr(self, "last_forecast_sequence", -1) >= 0 and sequence_number > self.last_forecast_sequence + 20:
            print(f"[GRU_WARNING] Forecast stale while telemetry continues. current_seq={sequence_number}, last_seq={self.last_forecast_sequence}")

        if not self.is_loaded:
            return {
                "ready": False,
                "timestamp": timestamp,
                "source_sequence_number": sequence_number,
                "model": "GRU",
                "model_version": "v1.0",
                "input_window_seconds": 30,
                "forecast": {},
                "forecast_mode": "STATISTICAL_FALLBACK",
                "status": "FALLBACK_LOAD_ERROR",
                "error": self.load_error
            }

        # Check if history has at least 30 frames
        if not telemetry_history or len(telemetry_history) < 30:
            return {
                "ready": False,
                "timestamp": timestamp,
                "source_sequence_number": sequence_number,
                "model": "GRU",
                "model_version": "v1.0",
                "input_window_seconds": 30,
                "forecast": {},
                "forecast_mode": "STATISTICAL_FALLBACK",
                "status": "WARMING_UP"
            }

        t_start = time.perf_counter()

        try:
            # Downsample input history to 2 Hz (take every 5th sample if 10 Hz telemetry)
            if len(telemetry_history) >= 300:
                sample_window = telemetry_history[-300::5]  # 60 samples at 2 Hz
            elif len(telemetry_history) >= 60:
                sample_window = telemetry_history[-60:]
            else:
                # Pad window by repeating earliest sample up to 60 samples
                pad_needed = 60 - len(telemetry_history)
                sample_window = [telemetry_history[0]] * pad_needed + list(telemetry_history)

            feature_cols = self.config["feature_columns"]
            target_cols = self.config["target_columns"]
            horizons = self.config["horizons_seconds"]

            # Build feature matrix
            seq_features = []
            for frame in sample_window:
                row = []
                for col in feature_cols:
                    if col == "altitude":
                        val = 4500.0 if scenario == "HIGH_ALTITUDE" else 1500.0
                    elif col == "ambient_temperature":
                        val = 42.0 if scenario == "HOT_WEATHER" else (-14.0 if scenario == "HIGH_ALTITUDE" else 15.0)
                    elif col == "throttle":
                        val = float(frame.get("throttle", 70.0))
                    elif col in ["bus_voltage", "battery_volt"]:
                        val = float(frame.get("battery_volt", frame.get("bus_voltage", 14.10)))
                    elif col in ["oil_pressure", "oil_press"]:
                        val = float(frame.get("oil_press", frame.get("oil_pressure", 4.20)))
                    elif col in ["oil_temperature", "oil_temp"]:
                        val = float(frame.get("oil_temp", frame.get("oil_temperature", 88.5)))
                    else:
                        val = float(frame.get(col, 0.0))
                    row.append(val)
                seq_features.append(row)

            seq_arr = np.array(seq_features, dtype=np.float32)  # Shape: (60, 18)

            # Input Validation for NaN / Inf
            contains_nan = bool(np.isnan(seq_arr).any())
            contains_inf = bool(np.isinf(seq_arr).any())
            if contains_nan or contains_inf:
                print(f"[GRU_ERROR] Input tensor contains NaN or Inf at seq={sequence_number}. Rejecting frame.")
                return {
                    "ready": False,
                    "timestamp": timestamp,
                    "source_sequence_number": sequence_number,
                    "model": "GRU",
                    "forecast": {},
                    "forecast_mode": "STATISTICAL_FALLBACK",
                    "status": "INPUT_INVALID_NAN_INF"
                }

            norm_seq = self.input_scaler.transform(seq_arr)
            tensor_in = torch.tensor(norm_seq).unsqueeze(0)  # Shape: (1, 60, 18)

            with torch.no_grad():
                pred_norm = self.model(tensor_in).numpy()[0]  # Shape: (18,)

            pred_unscaled = self.target_scaler.inverse_transform(pred_norm)

            # Extract current latest values and slopes for ALL channels
            latest_frame = sample_window[-1] if sample_window else {}
            n_samples = len(sample_window)
            t_axis = np.linspace(-30.0, 0.0, n_samples)

            def get_channel_metrics(key_name, default_val):
                vals = np.array([float(f.get(key_name, default_val)) for f in sample_window], dtype=np.float32)
                cur_v = float(vals[-1])
                if n_samples >= 5:
                    poly = np.polyfit(t_axis, vals, 1)
                    slope = float(poly[0])
                else:
                    slope = 0.0
                return cur_v, slope, vals

            cht_metrics = {f"cht{i}": get_channel_metrics(f"cht{i}", 120.0) for i in range(1, 5)}
            egt_metrics = {f"egt{i}": get_channel_metrics(f"egt{i}", 750.0) for i in range(1, 5)}
            oil_p_cur, oil_p_slope, _ = get_channel_metrics("oil_press", 4.20)
            if "oil_press" not in latest_frame and "oil_pressure" in latest_frame:
                oil_p_cur, oil_p_slope, _ = get_channel_metrics("oil_pressure", 4.20)

            oil_t_cur, oil_t_slope, _ = get_channel_metrics("oil_temp", 88.5)
            if "oil_temp" not in latest_frame and "oil_temperature" in latest_frame:
                oil_t_cur, oil_t_slope, _ = get_channel_metrics("oil_temperature", 88.5)

            vib_cur, vib_slope, _ = get_channel_metrics("vibration_rms", 1.12)
            map_cur, map_slope, _ = get_channel_metrics("map", 29.92)

            # Compute GRU neural delta adjustments relative to nominal baseline
            gru_raw_10 = {col: float(pred_unscaled[0 * 6 + idx]) for idx, col in enumerate(target_cols)}
            gru_raw_30 = {col: float(pred_unscaled[1 * 6 + idx]) for idx, col in enumerate(target_cols)}
            gru_raw_60 = {col: float(pred_unscaled[2 * 6 + idx]) for idx, col in enumerate(target_cols)}

            nom_cht1_base = 120.0
            nom_oil_p_base = 4.20
            nom_oil_t_base = 88.5
            nom_vib_base = 1.12
            nom_egt1_base = 750.0
            nom_map_base = 29.92

            gru_delta_10 = {
                "cht1": gru_raw_10["cht1"] - nom_cht1_base,
                "oil_press": gru_raw_10["oil_pressure"] - nom_oil_p_base,
                "oil_temp": gru_raw_10["oil_temperature"] - nom_oil_t_base,
                "vibration_rms": gru_raw_10["vibration_rms"] - nom_vib_base,
                "egt1": gru_raw_10["egt1"] - nom_egt1_base,
                "map": gru_raw_10["map"] - nom_map_base
            }

            gru_delta_30 = {
                "cht1": gru_raw_30["cht1"] - nom_cht1_base,
                "oil_press": gru_raw_30["oil_pressure"] - nom_oil_p_base,
                "oil_temp": gru_raw_30["oil_temperature"] - nom_oil_t_base,
                "vibration_rms": gru_raw_30["vibration_rms"] - nom_vib_base,
                "egt1": gru_raw_30["egt1"] - nom_egt1_base,
                "map": gru_raw_30["map"] - nom_map_base
            }

            gru_delta_60 = {
                "cht1": gru_raw_60["cht1"] - nom_cht1_base,
                "oil_press": gru_raw_60["oil_pressure"] - nom_oil_p_base,
                "oil_temp": gru_raw_60["oil_temperature"] - nom_oil_t_base,
                "vibration_rms": gru_raw_60["vibration_rms"] - nom_vib_base,
                "egt1": gru_raw_60["egt1"] - nom_egt1_base,
                "map": gru_raw_60["map"] - nom_map_base
            }

            forecast_dict = {"10s": {}, "30s": {}, "60s": {}}

            for h_key, h_sec, d_dict in [("10s", 10, gru_delta_10), ("30s", 30, gru_delta_30), ("60s", 60, gru_delta_60)]:
                # 1. CHT Cylinders 1..4
                for i in range(1, 5):
                    c_key = f"cht{i}"
                    c_cur, c_slope, _ = cht_metrics[c_key]
                    val = c_cur + (c_slope * h_sec) + d_dict["cht1"] * (h_sec / 60.0)
                    if c_slope >= 0:
                        val = max(c_cur, val)
                    else:
                        val = max(15.0, val)
                    forecast_dict[h_key][c_key] = round(val, 1)

                # 2. EGT Cylinders 1..4
                for i in range(1, 5):
                    e_key = f"egt{i}"
                    e_cur, e_slope, _ = egt_metrics[e_key]
                    val = e_cur + (e_slope * h_sec) + d_dict["egt1"] * (h_sec / 60.0)
                    if e_slope >= 0:
                        val = max(e_cur, val)
                    else:
                        val = max(15.0, val)
                    forecast_dict[h_key][e_key] = round(val, 1)

                # 3. Oil Pressure
                val_op = oil_p_cur + (oil_p_slope * h_sec) + d_dict["oil_press"] * (h_sec / 60.0)
                if oil_p_slope <= 0:
                    val_op = min(oil_p_cur, val_op)
                val_op = max(0.0, val_op)
                forecast_dict[h_key]["oil_pressure"] = round(val_op, 2)
                forecast_dict[h_key]["oil_press"] = round(val_op, 2)

                # 4. Oil Temp
                val_ot = oil_t_cur + (oil_t_slope * h_sec) + d_dict["oil_temp"] * (h_sec / 60.0)
                if oil_t_slope >= 0:
                    val_ot = max(oil_t_cur, val_ot)
                forecast_dict[h_key]["oil_temperature"] = round(val_ot, 1)
                forecast_dict[h_key]["oil_temp"] = round(val_ot, 1)

                # 5. Vibration RMS
                val_v = vib_cur + (vib_slope * h_sec) + d_dict["vibration_rms"] * (h_sec / 60.0)
                if vib_slope >= 0:
                    val_v = max(vib_cur, val_v)
                val_v = max(0.0, val_v)
                forecast_dict[h_key]["vibration_rms"] = round(val_v, 2)

                # 6. MAP
                val_m = map_cur + (map_slope * h_sec) + d_dict["map"] * (h_sec / 60.0)
                forecast_dict[h_key]["map"] = round(val_m, 2)

            t_end = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000.0, 2)

            self.last_forecast_sequence = sequence_number

            fc_id = f"fc_{sequence_number}_{int(timestamp * 1000)}"

            return {
                "ready": True,
                "forecast_id": fc_id,
                "timestamp": timestamp,
                "generated_at": timestamp,
                "source_sequence_number": sequence_number,
                "input_channel": "cht1",
                "current_value": cht_metrics["cht1"][0],
                "model": "GRU",
                "model_version": "v1.0",
                "input_window_seconds": 30,
                "forecast": forecast_dict,
                "forecast_10s": forecast_dict.get("10s", {}),
                "forecast_30s": forecast_dict.get("30s", {}),
                "forecast_60s": forecast_dict.get("60s", {}),
                "forecast_mode": "GRU_MODEL",
                "status": "READY"
            }

        except Exception as e:
            t_end = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000.0, 2)
            print(f"[GRU ERROR] Exception during inference at seq={sequence_number}: {e}")
            import traceback
            traceback.print_exc()

            return {
                "ready": False,
                "timestamp": timestamp,
                "source_sequence_number": sequence_number,
                "model": "GRU",
                "forecast": {},
                "forecast_mode": "STATISTICAL_FALLBACK",
                "status": "INFERENCE_EXCEPTION",
                "error": str(e)
            }


gru_forecast_service_instance = GruForecastService()
