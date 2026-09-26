"""
PyTorch Sequence LSTM Model for Remaining Useful Life (RUL) Prognostics
Trained on NASA C-MAPSS run-to-failure sequences to predict remaining operational cycles.
"""

import os
import time
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
import pickle
from typing import Dict, Any, List, Tuple
from collections import deque

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

class RulLstmNet(nn.Module):
    def __init__(self, input_size: int = 7, hidden_size: int = 32, num_layers: int = 2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        # Take output of last time step
        last_step = out[:, -1, :]
        rul_pred = self.fc(last_step)
        return rul_pred


class LstmRulEstimator:
    FEATURES = ["rpm", "map", "cht1", "egt1", "oil_press", "fuel_flow", "vibration_rms"]

    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self.model = RulLstmNet(input_size=len(self.FEATURES))
        self.model_path = os.path.join(MODELS_DIR, "lstm_rul.pt")
        self.scaler_path = os.path.join(MODELS_DIR, "lstm_scaler.pkl")
        self.sequence_buffer = deque(maxlen=window_size)
        self.mean = None
        self.std = None

        # RUL State Tracking
        self.valid_sequence_count = 0
        self.sequence_window_id = None
        self.window_step_counter = 0
        self.raw_prediction_cycles = None
        self.display_prediction_cycles = None
        self.previous_prediction_cycles = None
        self.prediction_timestamp = None
        self.trend = "N/A"
        self.model_status = "WARMING UP"

    def reset(self):
        """Resets sequence buffer and sequence window counters for a clean state."""
        self.sequence_buffer.clear()
        self.valid_sequence_count = 0
        self.sequence_window_id = None
        self.window_step_counter = 0
        self.raw_prediction_cycles = None
        self.display_prediction_cycles = None
        self.previous_prediction_cycles = None
        self.prediction_timestamp = None
        self.trend = "N/A"
        self.model_status = "WARMING UP"

    def prepare_dataset(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Converts raw C-MAPSS DataFrame into canonical sliding window sequences (W=30)."""
        from ml_service.canonical_schema import DatasetCanonicalMapper
        
        canonical_rows = []
        for _, row in df.iterrows():
            st = DatasetCanonicalMapper.map_cmapss_row(row.to_dict(), f"U{int(row['unit_id'])}", int(row["cycle"]))
            d = st.to_dict()
            d["unit_id"] = row["unit_id"]
            d["RUL"] = row["RUL"]
            canonical_rows.append(d)

        cdf = pd.DataFrame(canonical_rows)
        X_seqs = []
        y_ruls = []

        X_raw = cdf[self.FEATURES].values.astype(np.float32)
        if self.mean is None:
            self.mean = np.mean(X_raw, axis=0)
            self.std = np.std(X_raw, axis=0) + 1e-6

        cdf_norm = cdf.copy()
        cdf_norm[self.FEATURES] = (X_raw - self.mean) / self.std

        for uid, ugroup in cdf_norm.groupby("unit_id"):
            u_feats = ugroup[self.FEATURES].values
            u_ruls = ugroup["RUL"].values
            
            if len(u_feats) >= self.window_size:
                for i in range(len(u_feats) - self.window_size + 1):
                    X_seqs.append(u_feats[i : i + self.window_size])
                    y_ruls.append(u_ruls[i + self.window_size - 1])

        return np.array(X_seqs, dtype=np.float32), np.array(y_ruls, dtype=np.float32).reshape(-1, 1)

    def train_and_save(self, epochs: int = 25):
        """Trains PyTorch LSTM on NASA C-MAPSS degradation sequences."""
        from ml_service.dataset_loader import CMapssDatasetLoader
        print("[LSTMRUL] Loading NASA C-MAPSS dataset for RUL training...")
        loader = CMapssDatasetLoader()
        df = loader.load_df()

        X_train, y_train = self.prepare_dataset(df)
        print(f"[LSTMRUL] Training on {X_train.shape[0]} sequences (Window W={self.window_size})...")

        tensor_x = torch.tensor(X_train, dtype=torch.float32)
        tensor_y = torch.tensor(y_train, dtype=torch.float32)

        dataset = torch.utils.data.TensorDataset(tensor_x, tensor_y)
        dataloader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=True)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.003)
        criterion = nn.MSELoss()

        self.model.train()
        for epoch in range(epochs):
            total_loss = 0.0
            for bx, by in dataloader:
                optimizer.zero_grad()
                pred = self.model(bx)
                loss = criterion(pred, by)
                loss.backward()
                optimizer.step()
                total_loss += loss.item() * len(bx)
            
            rmse = np.sqrt(total_loss / len(X_train))
            if (epoch + 1) % 5 == 0:
                print(f"[LSTMRUL] Epoch {epoch+1}/{epochs} - Train RMSE: {rmse:.2f} cycles")

        torch.save(self.model.state_dict(), self.model_path)
        with open(self.scaler_path, "wb") as f:
            pickle.dump({"mean": self.mean, "std": self.std}, f)
        print(f"[LSTMRUL] Model trained & saved to {self.model_path}")

    def update_history_only(self, telemetry: Dict[str, Any]):
        """Updates internal sequence buffer without running PyTorch LSTM neural net inference."""
        feat_vals = [float(telemetry.get(f, 0.0)) for f in self.FEATURES]
        if self.mean is not None and self.std is not None:
            feat_norm = (np.array(feat_vals, dtype=np.float32) - self.mean) / self.std
        else:
            feat_norm = np.array(feat_vals, dtype=np.float32)
        self.sequence_buffer.append(feat_norm)
        self.valid_sequence_count += 1

    def load_model(self) -> bool:
        if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
            try:
                self.model.load_state_dict(torch.load(self.model_path))
                with open(self.scaler_path, "rb") as f:
                    data = pickle.load(f)
                    self.mean = data["mean"]
                    self.std = data["std"]
                self.model.eval()
                return True
            except Exception as e:
                print(f"[LSTMRUL] Failed loading model: {e}")
                return False
        return False

    def update_and_predict(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates internal sequence buffer at 10 Hz telemetry rate.
        RUL inference occurs ONLY when a new valid 30-cycle sequence window becomes available.
        Between window completions, returns cached prediction snapshot without refreshing.
        """
        if self.mean is None:
            if not self.load_model():
                self.train_and_save(epochs=20)

        ts = float(telemetry.get("timestamp", time.time()))
        
        # Extract features and append to sequence buffer
        feat_vals = [float(telemetry.get(f, 0.0)) for f in self.FEATURES]
        if self.mean is not None and self.std is not None:
            feat_norm = (np.array(feat_vals, dtype=np.float32) - self.mean) / self.std
        else:
            feat_norm = np.array(feat_vals, dtype=np.float32)

        self.sequence_buffer.append(feat_norm)
        self.valid_sequence_count += 1

        # Check if sequence buffer has reached minimum required sequence length (30 cycles)
        if len(self.sequence_buffer) < self.window_size:
            self.model_status = "WARMING UP"
            return {
                "raw_prediction_cycles": None,
                "display_prediction_cycles": None,
                "previous_prediction_cycles": None,
                "prediction_timestamp": None,
                "sequence_window_id": None,
                "trend": "N/A",
                "model_status": "WARMING UP",
                "unit": "cycles",
                "uncertainty_cycles": None,
                "sequence_length": self.window_size,
                "valid_sequence_count": len(self.sequence_buffer),
                "label": "NASA C-MAPSS FD001 LSTM Prognostics"
            }

        # Sequence buffer has reached 30 items. Determine if a new valid sequence window is available.
        should_run_inference = False

        if self.sequence_window_id is None:
            # First valid sequence window!
            self.sequence_window_id = 1
            self.window_step_counter = 0
            should_run_inference = True
        else:
            self.window_step_counter += 1
            if self.window_step_counter >= self.window_size:
                # New valid 30-cycle sequence window completed!
                self.sequence_window_id += 1
                self.window_step_counter = 0
                should_run_inference = True

        if should_run_inference:
            try:
                seq_array = np.array(self.sequence_buffer, dtype=np.float32).reshape(1, self.window_size, len(self.FEATURES))
                tensor_seq = torch.tensor(seq_array, dtype=torch.float32)

                self.model.eval()
                with torch.no_grad():
                    pred_cycles_raw = float(self.model(tensor_seq).item())

                raw_cycles = max(0.0, round(pred_cycles_raw, 1))

                if self.display_prediction_cycles is None:
                    # First window prediction: initial display equals raw
                    self.previous_prediction_cycles = raw_cycles
                    self.raw_prediction_cycles = raw_cycles
                    self.display_prediction_cycles = raw_cycles
                    self.trend = "STABLE"
                else:
                    self.previous_prediction_cycles = self.display_prediction_cycles
                    self.raw_prediction_cycles = raw_cycles
                    # EMA display smoothing: alpha = 0.3
                    alpha = 0.3
                    self.display_prediction_cycles = round(alpha * raw_cycles + (1 - alpha) * self.previous_prediction_cycles, 1)

                    if self.display_prediction_cycles < self.previous_prediction_cycles:
                        self.trend = "DEGRADING"
                    elif self.display_prediction_cycles > self.previous_prediction_cycles:
                        self.trend = "IMPROVING"
                    else:
                        self.trend = "STABLE"

                self.prediction_timestamp = ts
                self.model_status = "INFERENCE ACTIVE"
            except Exception as e:
                print(f"[LSTMRUL] Model inference error: {e}")
                self.model_status = "ERROR"

        return {
            "raw_prediction_cycles": self.raw_prediction_cycles,
            "display_prediction_cycles": self.display_prediction_cycles,
            "previous_prediction_cycles": self.previous_prediction_cycles,
            "prediction_timestamp": self.prediction_timestamp,
            "sequence_window_id": self.sequence_window_id,
            "trend": self.trend,
            "model_status": self.model_status,
            "unit": "cycles",
            "uncertainty_cycles": None,
            "sequence_length": self.window_size,
            "valid_sequence_count": self.valid_sequence_count,
            "label": "NASA C-MAPSS FD001 LSTM Prognostics"
        }
