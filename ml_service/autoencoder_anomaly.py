"""
PyTorch Deep Autoencoder for Unsupervised Anomaly Detection
Learns healthy aero engine telemetry manifold and detects anomalies via MSE reconstruction error.
"""

import os
import torch
import torch.nn as nn
import numpy as np
import pickle
from typing import Dict, Any, List

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

class TelemetryAutoencoder(nn.Module):
    def __init__(self, input_dim: int = 15):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 10),
            nn.ReLU(),
            nn.Linear(10, 5),
            nn.ReLU()
        )
        self.decoder = nn.Sequential(
            nn.Linear(5, 10),
            nn.ReLU(),
            nn.Linear(10, input_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed


class AutoencoderAnomalyDetector:
    def __init__(self, input_dim: int = 15):
        self.input_dim = input_dim
        self.model = TelemetryAutoencoder(input_dim)
        self.model_path = os.path.join(MODELS_DIR, "autoencoder_anomaly.pt")
        self.scaler_path = os.path.join(MODELS_DIR, "autoencoder_scaler.pkl")
        self.mean = None
        self.std = None
        self.max_healthy_error = 0.05
        
        self.features = [
            "rpm", "map", "cht1", "cht2", "cht3", "cht4",
            "egt1", "egt2", "egt3", "egt4", "oil_press", "oil_temp",
            "fuel_flow", "vibration_rms", "battery_volt"
        ]

    def _extract_feature_vector(self, telemetry: Dict[str, Any]) -> np.ndarray:
        defaults = {
            "rpm": 5000.0, "map": 1.15,
            "cht1": 120.0, "cht2": 121.0, "cht3": 119.5, "cht4": 120.5,
            "egt1": 748.0, "egt2": 750.0, "egt3": 746.0, "egt4": 749.0,
            "oil_press": 4.20, "oil_temp": 88.5, "fuel_flow": 17.5,
            "vibration_rms": 1.12, "battery_volt": 14.10
        }
        vec = []
        for f in self.features:
            val = float(telemetry.get(f, defaults.get(f, 0.0)))
            if f == "battery_volt" and val == 0.0:
                val = 14.10
            vec.append(val)
        return np.array(vec, dtype=np.float32)


    def train_and_save(self, healthy_telemetry_df: Any, epochs: int = 50):
        """Trains Autoencoder on healthy operational telemetry."""
        X_raw = healthy_telemetry_df[self.features].values.astype(np.float32)
        
        # Calculate mean & std for Z-score normalization
        self.mean = np.mean(X_raw, axis=0)
        self.std = np.std(X_raw, axis=0) + 1e-6

        X_norm = (X_raw - self.mean) / self.std
        tensor_x = torch.tensor(X_norm, dtype=torch.float32)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.005)
        criterion = nn.MSELoss()

        self.model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            output = self.model(tensor_x)
            loss = criterion(output, tensor_x)
            loss.backward()
            optimizer.step()

        # Compute max error on healthy dataset as reference threshold
        self.model.eval()
        with torch.no_grad():
            reconstructed = self.model(tensor_x)
            errors = torch.mean((tensor_x - reconstructed) ** 2, dim=1).numpy()
            self.max_healthy_error = float(np.percentile(errors, 98)) + 1e-4

        # Save artifacts
        torch.save(self.model.state_dict(), self.model_path)
        with open(self.scaler_path, "wb") as f:
            pickle.dump({"mean": self.mean, "std": self.std, "threshold": self.max_healthy_error}, f)
        print(f"[Autoencoder] Model trained successfully (Max Healthy MSE: {self.max_healthy_error:.5f})")

    def load_model(self) -> bool:
        if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
            self.model.load_state_dict(torch.load(self.model_path))
            with open(self.scaler_path, "rb") as f:
                data = pickle.load(f)
                self.mean = data["mean"]
                self.std = data["std"]
                self.max_healthy_error = data["threshold"]
            self.model.eval()
            return True
        return False

    def predict_anomaly(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Predicts reconstruction error and anomaly score for live telemetry frame."""
        if self.mean is None:
            if not self.load_model():
                # Auto-train if model weights absent
                from ml_service.dataset_loader import generate_multiclass_fault_dataset
                df = generate_multiclass_fault_dataset()
                healthy_df = df[df["fault_label"] == 0]
                self.train_and_save(healthy_df)

        vec = self._extract_feature_vector(telemetry)
        vec_norm = (vec - self.mean) / self.std
        tensor_vec = torch.tensor(vec_norm, dtype=torch.float32).unsqueeze(0)

        self.model.eval()
        with torch.no_grad():
            recon = self.model(tensor_vec)
            mse_loss = float(torch.mean((tensor_vec - recon) ** 2).item())

        # Anomaly score normalized between 0.00 and 1.00
        anomaly_score = float(min(1.0, max(0.0, mse_loss / (self.max_healthy_error * 3.5))))
        is_anomaly = anomaly_score > 0.45

        return {
            "reconstruction_mse": round(mse_loss, 5),
            "healthy_mse_threshold": round(self.max_healthy_error, 5),
            "anomaly_score": round(anomaly_score, 3),
            "status": "ANOMALY_DETECTED" if is_anomaly else "NORMAL"
        }
