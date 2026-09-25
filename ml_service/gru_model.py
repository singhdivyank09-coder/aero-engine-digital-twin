"""
PyTorch GRU Short-Horizon Telemetry Forecaster Module
SIH 26054 — Aero-Piston Engine Digital Twin

Provides:
- Compact multi-horizon PyTorch GRU network (GruShortHorizonNet)
- CustomScaler for input and target standardization
"""

import os
import torch
import torch.nn as nn
import numpy as np
from typing import Dict, Any, List, Tuple

class CustomScaler:
    def __init__(self):
        self.mean_ = None
        self.scale_ = None

    def fit(self, X: np.ndarray):
        flat_X = X.reshape(-1, X.shape[-1])
        self.mean_ = np.mean(flat_X, axis=0)
        self.scale_ = np.std(flat_X, axis=0)
        self.scale_[self.scale_ < 1e-6] = 1.0
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mean_) / self.scale_

    def inverse_transform(self, X: np.ndarray) -> np.ndarray:
        return X * self.scale_ + self.mean_


class GruShortHorizonNet(nn.Module):
    """
    Multi-Output Compact PyTorch GRU Forecaster
    Input shape: (batch_size, seq_len=60, input_dim=18)
    Output shape: (batch_size, output_dim=18)  # 6 parameters x 3 horizons [10s, 30s, 60s]
    """
    def __init__(self, input_dim: int = 18, hidden_dim: int = 64, num_layers: int = 2, output_dim: int = 18):
        super(GruShortHorizonNet, self).__init__()
        self.gru = nn.GRU(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.1 if num_layers > 1 else 0.0
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.05),
            nn.Linear(64, output_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch_size, sequence_length, input_dim)
        gru_out, h_n = self.gru(x)
        # Use final time-step hidden state
        last_out = gru_out[:, -1, :]
        out = self.fc(last_out)
        return out
