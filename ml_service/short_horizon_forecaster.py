"""
Short-Horizon Telemetry Forecaster — PyTorch LSTM Temporal Sequence Model
SIH 26054 — Aero-Piston Engine Digital Twin

Forecasts short-horizon (10s, 30s, 60s) future trajectories for core aero-piston parameters:
- CHT (Cylinder Head Temperature)
- EGT (Exhaust Gas Temperature)
- Oil Pressure
- Oil Temperature
- Vibration RMS

Synthetic training data is generated using SIMULATED REFERENCE AERO-PISTON TRAJECTORIES
(Not DRDO flight measurements).
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import json
import torch
import torch.nn as nn
import numpy as np
from typing import Dict, Any, List, Tuple, Optional

# Model Directory
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

MODEL_PATH = os.path.join(MODELS_DIR, "short_horizon_forecaster.pt")
SCALER_PATH = os.path.join(MODELS_DIR, "forecaster_scaler.json")
METRICS_PATH = os.path.join(MODELS_DIR, "forecaster_metrics.json")

FEATURE_KEYS = ["cht1", "egt1", "oil_press", "oil_temp", "vibration_rms"]
PARAM_NAME_MAP = {
    "cht1": "cht",
    "egt1": "egt",
    "oil_press": "oil_press",
    "oil_temp": "oil_temp",
    "vibration_rms": "vibration_rms"
}

class LstmShortHorizonNet(nn.Module):
    """
    Lightweight PyTorch 2-Layer LSTM Forecaster
    Maps 300-step (30s) input window of 5 features to 15 output targets (5 params x 3 horizons [10s, 30s, 60s]).
    """
    def __init__(self, input_dim: int = 5, hidden_dim: int = 64, num_layers: int = 2, output_dim: int = 15):
        super(LstmShortHorizonNet, self).__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.1 if num_layers > 1 else 0.0
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Linear(64, output_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch_size, sequence_length, input_dim)
        lstm_out, (h_n, c_n) = self.lstm(x)
        # Use final time-step hidden state
        last_out = lstm_out[:, -1, :]
        out = self.fc(last_out)
        return out


def generate_synthetic_training_data(num_sequences: int = 400, seq_len: int = 300) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generates synthetic training trajectories clearly labeled:
    SIMULATED REFERENCE AERO-PISTON TRAJECTORIES
    (Not DRDO flight measurements)
    """
    np.random.seed(42)
    X_list = []
    y_list = []

    # Target future offsets at 10Hz: 10s (100 steps), 30s (300 steps), 60s (600 steps)
    horizons = [100, 300, 600]

    for _ in range(num_sequences):
        total_len = seq_len + max(horizons) + 10
        t = np.linspace(0, total_len * 0.1, total_len)

        scenario = np.random.choice(["NOMINAL", "THERMAL_DEGRADATION", "OIL_DECAY", "VIB_GROWTH", "HOT_WEATHER"])

        base_cht = 120.0
        base_egt = 748.0
        base_oil_p = 4.20
        base_oil_t = 88.5
        base_vib = 1.12

        if scenario == "NOMINAL":
            cht_trend = base_cht + np.sin(t * 0.05) * 2.0
            egt_trend = base_egt + np.sin(t * 0.05) * 5.0
            oil_p_trend = base_oil_p + np.sin(t * 0.02) * 0.1
            oil_t_trend = base_oil_t + np.sin(t * 0.02) * 1.0
            vib_trend = base_vib + np.random.normal(0, 0.02, total_len)
        elif scenario == "THERMAL_DEGRADATION":
            slope = np.random.uniform(0.3, 0.8)
            cht_trend = base_cht + slope * t + np.random.normal(0, 0.3, total_len)
            egt_trend = base_egt + (slope * 0.5) * t + np.random.normal(0, 1.0, total_len)
            oil_p_trend = base_oil_p - (slope * 0.008) * t + np.random.normal(0, 0.01, total_len)
            oil_t_trend = base_oil_t + (slope * 0.2) * t + np.random.normal(0, 0.2, total_len)
            vib_trend = base_vib + np.random.normal(0, 0.02, total_len)
        elif scenario == "OIL_DECAY":
            decay = np.random.uniform(0.02, 0.05)
            oil_p_trend = np.maximum(1.2, base_oil_p - decay * t + np.random.normal(0, 0.01, total_len))
            oil_t_trend = base_oil_t + decay * 10.0 * t + np.random.normal(0, 0.2, total_len)
            cht_trend = base_cht + decay * 2.0 * t + np.random.normal(0, 0.3, total_len)
            egt_trend = base_egt + np.random.normal(0, 1.0, total_len)
            vib_trend = base_vib + decay * 0.5 * t + np.random.normal(0, 0.02, total_len)
        elif scenario == "VIB_GROWTH":
            vib_slope = np.random.uniform(0.015, 0.04)
            vib_trend = base_vib + vib_slope * t + np.random.normal(0, 0.03, total_len)
            cht_trend = base_cht + np.random.normal(0, 0.3, total_len)
            egt_trend = base_egt + np.random.normal(0, 1.0, total_len)
            oil_p_trend = base_oil_p + np.random.normal(0, 0.01, total_len)
            oil_t_trend = base_oil_t + np.random.normal(0, 0.1, total_len)
        else: # HOT_WEATHER
            cht_trend = 132.0 + np.random.normal(0, 0.3, total_len)
            egt_trend = 765.0 + np.random.normal(0, 1.0, total_len)
            oil_p_trend = 3.90 + np.random.normal(0, 0.01, total_len)
            oil_t_trend = 102.0 + np.random.normal(0, 0.2, total_len)
            vib_trend = 1.15 + np.random.normal(0, 0.02, total_len)

        traj = np.column_stack([cht_trend, egt_trend, oil_p_trend, oil_t_trend, vib_trend])

        # Extract sequence X (0 to seq_len) and targets Y at future horizons
        start_idx = np.random.randint(0, total_len - seq_len - max(horizons) - 1)
        x_win = traj[start_idx : start_idx + seq_len]

        targets = []
        for h in horizons:
            t_idx = start_idx + seq_len + h - 1
            targets.extend(traj[t_idx])

        X_list.append(x_win)
        y_list.append(targets)

    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32)


def train_and_save_short_horizon_forecaster():
    """
    Trains the PyTorch LstmShortHorizonNet on SIMULATED REFERENCE AERO-PISTON TRAJECTORIES,
    evaluates MAE/RMSE on test split, and saves model & preprocessor artifacts.
    """
    print("Generating SIMULATED REFERENCE AERO-PISTON TRAJECTORIES for training...")
    X_raw, y_raw = generate_synthetic_training_data(num_sequences=500, seq_len=300)

    num_samples, seq_len, num_features = X_raw.shape

    # Fit Normalization Scalers
    means = np.mean(X_raw.reshape(-1, num_features), axis=0)
    stds = np.std(X_raw.reshape(-1, num_features), axis=0)
    stds[stds < 1e-6] = 1.0

    X_norm = (X_raw - means) / stds

    # Target scaling (flattened targets repeat the 5 features 3 times)
    target_means = np.tile(means, 3)
    target_stds = np.tile(stds, 3)
    y_norm = (y_raw - target_means) / target_stds

    # Split 80% train, 20% test
    split = int(0.8 * num_samples)
    X_train, X_test = X_norm[:split], X_norm[split:]
    y_train, y_test = y_norm[:split], y_norm[split:]

    train_ds = torch.utils.data.TensorDataset(torch.tensor(X_train), torch.tensor(y_train))
    train_loader = torch.utils.data.DataLoader(train_ds, batch_size=32, shuffle=True)

    model = LstmShortHorizonNet(input_dim=5, hidden_dim=64, num_layers=2, output_dim=15)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.002, weight_decay=1e-5)
    criterion = nn.MSELoss()

    print("Training PyTorch LstmShortHorizonNet (30 epochs)...")
    model.train()
    for epoch in range(30):
        total_loss = 0.0
        for bx, by in train_loader:
            optimizer.zero_grad()
            out = model(bx)
            loss = criterion(out, by)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

    # Evaluation on Held-Out Test Set
    model.eval()
    with torch.no_grad():
        test_preds_norm = model(torch.tensor(X_test)).numpy()

    # Unscale predictions & targets to calculate physical MAE & RMSE
    test_preds = test_preds_norm * target_stds + target_means
    y_test_unscaled = y_test * target_stds + target_means

    mae = float(np.mean(np.abs(test_preds - y_test_unscaled)))
    rmse = float(np.sqrt(np.mean((test_preds - y_test_unscaled) ** 2)))

    print(f"Evaluation Complete — Test MAE: {mae:.3f} | Test RMSE: {rmse:.3f}")

    # Save Model Weights
    torch.save(model.state_dict(), MODEL_PATH)

    # Save Scaler Artifact
    scaler_data = {
        "dataset_provenance": "SIMULATED REFERENCE AERO-PISTON TRAJECTORIES",
        "disclaimer": "Synthetic training dataset. Not DRDO flight measurements.",
        "feature_keys": FEATURE_KEYS,
        "means": means.tolist(),
        "stds": stds.tolist(),
        "target_means": target_means.tolist(),
        "target_stds": target_stds.tolist()
    }
    with open(SCALER_PATH, "w") as f:
        json.dump(scaler_data, f, indent=2)

    # Save Metrics Artifact
    metrics_data = {
        "model_version": "PyTorch-LSTM-ShortHorizonForecaster-v1.0",
        "training_dataset": "SIMULATED REFERENCE AERO-PISTON TRAJECTORIES",
        "provenance": "Synthetic simulator trajectories (Not DRDO flight measurements)",
        "sequence_window_length_sec": 30.0,
        "forecast_horizons_sec": [10.0, 30.0, 60.0],
        "test_mae": round(mae, 4),
        "test_rmse": round(rmse, 4),
        "feature_count": 5
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics_data, f, indent=2)

    print(f"Saved artifacts to {MODELS_DIR}")


class ShortHorizonForecaster:
    """
    Inference service for short-horizon telemetry forecasting.
    Loads trained LstmShortHorizonNet model and scaler artifacts.
    """
    def __init__(self):
        self.model_version = "PyTorch-LSTM-ShortHorizonForecaster-v1.0"
        self.feature_keys = FEATURE_KEYS

        if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
            train_and_save_short_horizon_forecaster()

        # Load Scaler
        with open(SCALER_PATH, "r") as f:
            scaler_data = json.load(f)

        self.means = np.array(scaler_data["means"], dtype=np.float32)
        self.stds = np.array(scaler_data["stds"], dtype=np.float32)
        self.target_means = np.array(scaler_data["target_means"], dtype=np.float32)
        self.target_stds = np.array(scaler_data["target_stds"], dtype=np.float32)

        # Load PyTorch Model
        self.model = LstmShortHorizonNet(input_dim=5, hidden_dim=64, num_layers=2, output_dim=15)
        self.model.load_state_dict(torch.load(MODEL_PATH))
        self.model.eval()

    def forecast(self, history_window: List[Dict[str, float]], timestamp: float) -> Dict[str, Any]:
        """
        Forecasts future 10s, 30s, and 60s parameter trajectories from past telemetry sequence.
        Input history_window: list of telemetry frame dictionaries (requires at least 30 samples).
        """
        if not history_window or len(history_window) < 10:
            # Fallback for warming up window
            last_frame = history_window[-1] if history_window else {}
            curr_cht = float(last_frame.get("cht1", 120.0))
            curr_egt = float(last_frame.get("egt1", 748.0))
            curr_oil_p = float(last_frame.get("oil_press", 4.20))
            curr_oil_t = float(last_frame.get("oil_temp", 88.5))
            curr_vib = float(last_frame.get("vibration_rms", 1.12))

            baseline_pred = {
                "cht": round(curr_cht, 1),
                "egt": round(curr_egt, 1),
                "oil_press": round(curr_oil_p, 2),
                "oil_temp": round(curr_oil_t, 1),
                "vibration_rms": round(curr_vib, 2)
            }
            return {
                "horizon_seconds": 30.0,
                "predicted_values": {
                    "10s": baseline_pred,
                    "30s": baseline_pred,
                    "60s": baseline_pred
                },
                "prediction_timestamp": timestamp,
                "model_version": self.model_version,
                "confidence_or_error_band_if_available": None
            }

        # Build feature sequence array (take up to 300 samples)
        seq_data = []
        for frame in history_window[-300:]:
            seq_data.append([
                float(frame.get("cht1", 120.0)),
                float(frame.get("egt1", 748.0)),
                float(frame.get("oil_press", 4.20)),
                float(frame.get("oil_temp", 88.5)),
                float(frame.get("vibration_rms", 1.12))
            ])

        # If window is shorter than 300 samples, pad by repeating first sample
        if len(seq_data) < 300:
            pad_len = 300 - len(seq_data)
            seq_data = [seq_data[0]] * pad_len + seq_data

        seq_arr = np.array(seq_data, dtype=np.float32)
        norm_seq = (seq_arr - self.means) / self.stds
        tensor_seq = torch.tensor(norm_seq).unsqueeze(0)  # Shape: (1, 300, 5)

        with torch.no_grad():
            pred_norm = self.model(tensor_seq).numpy()[0]  # Shape: (15,)

        pred_unscaled = pred_norm * self.target_stds + self.target_means

        # Map 15 values to 3 horizons x 5 params
        # Index 0-4: 10s forecast, 5-9: 30s forecast, 10-14: 60s forecast
        p10 = pred_unscaled[0:5]
        p30 = pred_unscaled[5:10]
        p60 = pred_unscaled[10:15]

        def format_pred_dict(arr):
            return {
                "cht": round(float(arr[0]), 1),
                "egt": round(float(arr[1]), 1),
                "oil_press": round(float(arr[2]), 2),
                "oil_temp": round(float(arr[3]), 1),
                "vibration_rms": round(float(arr[4]), 2)
            }

        return {
            "horizon_seconds": 30.0,
            "predicted_values": {
                "10s": format_pred_dict(p10),
                "30s": format_pred_dict(p30),
                "60s": format_pred_dict(p60)
            },
            "prediction_timestamp": timestamp,
            "model_version": self.model_version,
            "confidence_or_error_band_if_available": None
        }

if __name__ == "__main__":
    train_and_save_short_horizon_forecaster()
