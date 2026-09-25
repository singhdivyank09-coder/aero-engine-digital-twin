"""
PyTorch GRU Short-Horizon Model Training & Evaluation Pipeline
SIH 26054 — Aero-Piston Engine Digital Twin

Performs:
1. Loads 2 Hz trajectory dataset from datasets/simulated/forecast_training/simulated_aero_piston_trajectories.csv
2. Trajectory-level split: 70% Train, 15% Validation, 15% Test (prevents temporal data leakage)
3. Fits StandardScaler on TRAIN trajectories only
4. Builds 30s input windows (60 time steps at 2 Hz) mapped to +10s, +30s, +60s multi-horizon targets
5. Trains GruShortHorizonNet with Early Stopping and validation loss tracking
6. Evaluates test set MAE and RMSE per parameter and horizon
7. Saves artifacts into models/forecast/:
   - gru_forecaster.pt
   - input_scaler.pkl
   - target_scaler.pkl
   - config.json
   - metrics.json
   - actual_vs_predicted_plot.png
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
import json
import pickle
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml_service.gru_model import GruShortHorizonNet, CustomScaler

MODELS_FORECAST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "forecast")
os.makedirs(MODELS_FORECAST_DIR, exist_ok=True)

DATASET_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets", "simulated", "forecast_training", "simulated_aero_piston_trajectories.csv")

FEATURE_COLUMNS = [
    "rpm", "map", "cht1", "cht2", "cht3", "cht4",
    "egt1", "egt2", "egt3", "egt4", "oil_pressure", "oil_temperature",
    "fuel_flow", "vibration_rms", "bus_voltage", "altitude", "ambient_temperature", "throttle"
]

TARGET_COLUMNS = ["cht1", "oil_pressure", "oil_temperature", "vibration_rms", "egt1", "map"]
TARGET_HORIZONS = [10, 30, 60]  # in seconds (at 2 Hz: +20, +60, +120 steps)
HORIZON_STEPS = [h * 2 for h in TARGET_HORIZONS]  # [20, 60, 120] steps at 2 Hz


def build_window_dataset_fast(grouped_dict: Dict[str, pd.DataFrame], trajectory_ids: List[str], seq_len: int = 60, stride: int = 2):
    X_samples = []
    y_samples = []

    max_target_offset = max(HORIZON_STEPS)

    for traj_id in trajectory_ids:
        if traj_id not in grouped_dict:
            continue
        traj_df = grouped_dict[traj_id]
        feature_vals = traj_df[FEATURE_COLUMNS].values
        target_vals = traj_df[TARGET_COLUMNS].values
        n_points = len(traj_df)

        if n_points < seq_len + max_target_offset:
            continue

        for i in range(0, n_points - seq_len - max_target_offset, stride):
            x_win = feature_vals[i : i + seq_len]
            
            y_win = []
            for offset in HORIZON_STEPS:
                target_at_horizon = target_vals[i + seq_len + offset - 1]
                y_win.extend(target_at_horizon)

            X_samples.append(x_win)
            y_samples.append(y_win)

    return np.array(X_samples, dtype=np.float32), np.array(y_samples, dtype=np.float32)


def train_gru_model():
    print(f"Loading trajectory dataset from {DATASET_CSV}...")
    df = pd.read_csv(DATASET_CSV)
    
    unique_trajectories = list(df["trajectory_id"].unique())
    np.random.seed(42)
    np.random.shuffle(unique_trajectories)

    n_total = len(unique_trajectories)
    n_train = int(0.70 * n_total)
    n_val = int(0.15 * n_total)
    
    train_trajs = unique_trajectories[:n_train]
    val_trajs = unique_trajectories[n_train : n_train + n_val]
    test_trajs = unique_trajectories[n_train + n_val :]

    print(f"Trajectory Split — Train: {len(train_trajs)}, Val: {len(val_trajs)}, Test: {len(test_trajs)}")

    # Pre-group dataframe by trajectory_id for fast extraction
    grouped_dict = {name: group.sort_values("timestamp") for name, group in df.groupby("trajectory_id")}

    # Extract Raw Windows
    X_train_raw, y_train_raw = build_window_dataset_fast(grouped_dict, train_trajs, stride=2)
    X_val_raw, y_val_raw = build_window_dataset_fast(grouped_dict, val_trajs, stride=2)
    X_test_raw, y_test_raw = build_window_dataset_fast(grouped_dict, test_trajs, stride=2)

    print(f"Dataset Window Shapes — Train: {X_train_raw.shape}, Val: {X_val_raw.shape}, Test: {X_test_raw.shape}")

    # Fit Scalers on TRAIN split only
    input_scaler = CustomScaler()
    input_scaler.fit(X_train_raw)

    target_scaler = CustomScaler()
    target_scaler.fit(y_train_raw.reshape(-1, y_train_raw.shape[-1]))

    # Transform Datasets
    X_train_norm = input_scaler.transform(X_train_raw)
    y_train_norm = target_scaler.transform(y_train_raw)

    X_val_norm = input_scaler.transform(X_val_raw)
    y_val_norm = target_scaler.transform(y_val_raw)

    X_test_norm = input_scaler.transform(X_test_raw)
    y_test_norm = target_scaler.transform(y_test_raw)

    # PyTorch DataLoaders
    train_ds = TensorDataset(torch.tensor(X_train_norm), torch.tensor(y_train_norm))
    val_ds = TensorDataset(torch.tensor(X_val_norm), torch.tensor(y_val_norm))
    
    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=64, shuffle=False)

    input_dim = len(FEATURE_COLUMNS)
    output_dim = len(TARGET_COLUMNS) * len(TARGET_HORIZONS) # 6 * 3 = 18

    model = GruShortHorizonNet(input_dim=input_dim, hidden_dim=64, num_layers=2, output_dim=output_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.002, weight_decay=1e-5)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_model_weights = None
    patience = 5
    patience_counter = 0
    epochs = 25

    print("Training PyTorch GruShortHorizonNet (25 epochs max)...")

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for bx, by in train_loader:
            optimizer.zero_grad()
            out = model(bx)
            loss = criterion(out, by)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * len(bx)
        train_loss /= len(train_ds)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for bx, by in val_loader:
                out = model(bx)
                loss = criterion(out, by)
                val_loss += loss.item() * len(bx)
        val_loss /= len(val_ds)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_weights = model.state_dict().copy()
            patience_counter = 0
        else:
            patience_counter += 1

        if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
            print(f"Epoch {epoch+1:02d}/{epochs} | Train Loss: {train_loss:.5f} | Val Loss: {val_loss:.5f} (Best Val: {best_val_loss:.5f})")

        if patience_counter >= patience:
            print(f"Early stopping triggered at epoch {epoch+1}")
            break

    # Load best weights for evaluation
    model.load_state_dict(best_model_weights)
    model.eval()

    # Save Model Weights
    pt_path = os.path.join(MODELS_FORECAST_DIR, "gru_forecaster.pt")
    torch.save(model.state_dict(), pt_path)

    # Save Scalers
    input_scaler_path = os.path.join(MODELS_FORECAST_DIR, "input_scaler.pkl")
    target_scaler_path = os.path.join(MODELS_FORECAST_DIR, "target_scaler.pkl")

    with open(input_scaler_path, "wb") as f:
        pickle.dump(input_scaler, f)
    with open(target_scaler_path, "wb") as f:
        pickle.dump(target_scaler, f)

    # Held-Out Test Evaluation
    with torch.no_grad():
        test_preds_norm = model(torch.tensor(X_test_norm)).numpy()

    test_preds = target_scaler.inverse_transform(test_preds_norm)
    y_test_actual = y_test_raw

    metrics = {
        "model": "GRU",
        "model_version": "v1.0",
        "training_dataset": "SIMULATED REFERENCE AERO-PISTON TRAJECTORY",
        "input_window_seconds": 30,
        "input_features": FEATURE_COLUMNS,
        "target_parameters": TARGET_COLUMNS,
        "horizons_seconds": TARGET_HORIZONS,
        "train_trajectories": len(train_trajs),
        "val_trajectories": len(val_trajs),
        "test_trajectories": len(test_trajs),
        "train_windows": len(X_train_raw),
        "val_windows": len(X_val_raw),
        "test_windows": len(X_test_raw),
        "best_val_loss": round(float(best_val_loss), 6),
        "metrics_by_parameter_horizon": {}
    }

    print("\n--- HELD-OUT TEST EVALUATION METRICS ---")
    for p_idx, param in enumerate(TARGET_COLUMNS):
        metrics["metrics_by_parameter_horizon"][param] = {}
        for h_idx, h_sec in enumerate(TARGET_HORIZONS):
            col_idx = h_idx * len(TARGET_COLUMNS) + p_idx
            pred_col = test_preds[:, col_idx]
            actual_col = y_test_actual[:, col_idx]

            mae = float(np.mean(np.abs(pred_col - actual_col)))
            rmse = float(np.sqrt(np.mean((pred_col - actual_col) ** 2)))

            metrics["metrics_by_parameter_horizon"][param][f"{h_sec}s"] = {
                "mae": round(mae, 4),
                "rmse": round(rmse, 4)
            }
            print(f"Parameter: {param:15s} | Horizon: +{h_sec:02d}s | MAE: {mae:7.4f} | RMSE: {rmse:7.4f}")

    metrics_json_path = os.path.join(MODELS_FORECAST_DIR, "metrics.json")
    with open(metrics_json_path, "w") as f:
        json.dump(metrics, f, indent=2)

    config_json_path = os.path.join(MODELS_FORECAST_DIR, "config.json")
    config = {
        "model_type": "GRU",
        "input_dim": input_dim,
        "hidden_dim": 64,
        "num_layers": 2,
        "output_dim": output_dim,
        "sequence_length": 60,
        "sampling_rate_hz": 2.0,
        "feature_columns": FEATURE_COLUMNS,
        "target_columns": TARGET_COLUMNS,
        "horizons_seconds": TARGET_HORIZONS
    }
    with open(config_json_path, "w") as f:
        json.dump(config, f, indent=2)

    # Plot Actual vs Predicted for held-out test trajectory
    plt.figure(figsize=(10, 6))
    sample_indices = np.arange(min(100, len(y_test_actual)))
    plt.plot(sample_indices, y_test_actual[:100, 0], label="Actual CHT1 (+10s)", color="blue", linewidth=2)
    plt.plot(sample_indices, test_preds[:100, 0], label="GRU Forecast CHT1 (+10s)", color="red", linestyle="--", linewidth=2)
    plt.plot(sample_indices, y_test_actual[:100, 6], label="Actual CHT1 (+30s)", color="teal", linewidth=1.5)
    plt.plot(sample_indices, test_preds[:100, 6], label="GRU Forecast CHT1 (+30s)", color="orange", linestyle="--", linewidth=1.5)
    plt.title("GRU Short-Horizon Forecast: Actual vs Predicted CHT1 Trajectory")
    plt.xlabel("Test Sequence Index")
    plt.ylabel("CHT1 (°C)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plot_path = os.path.join(MODELS_FORECAST_DIR, "actual_vs_predicted_plot.png")
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"\n[MODEL TRAINING SUCCESS] Artifacts saved to {MODELS_FORECAST_DIR}")
    return metrics

if __name__ == "__main__":
    train_gru_model()
