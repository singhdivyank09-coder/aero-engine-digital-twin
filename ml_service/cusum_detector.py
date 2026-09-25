"""
Statistical CUSUM Change-Point Detector
Tracks cumulative deviations from nominal mean for early statistical fault detection.
"""

import numpy as np
from typing import Dict, Any, List

class CusumDetector:
    def __init__(self, target_params: List[str] = None, k: float = 0.5, h: float = 4.5):
        """
        k: allowance (slack) parameter in standard deviation units
        h: decision threshold limit in standard deviation units
        """
        if target_params is None:
            self.target_params = ["cht1", "egt1", "oil_press", "vibration_rms", "battery_volt"]
        else:
            self.target_params = target_params

        self.k = k
        self.h = h
        
        # Baselines (Mean & Std) per parameter
        self.baselines = {
            "cht1": {"mean": 120.0, "std": 3.0},
            "egt1": {"mean": 748.0, "std": 8.0},
            "oil_press": {"mean": 4.20, "std": 0.15},
            "vibration_rms": {"mean": 1.10, "std": 0.10},
            "battery_volt": {"mean": 14.10, "std": 0.10}
        }

        # High (S_pos) and Low (S_neg) cumulative sum states
        self.pos_sums = {p: 0.0 for p in self.target_params}
        self.neg_sums = {p: 0.0 for p in self.target_params}

    def reset(self):
        self.pos_sums = {p: 0.0 for p in self.target_params}
        self.neg_sums = {p: 0.0 for p in self.target_params}

    def update(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Updates CUSUM statistics with live telemetry frame."""
        triggered_channels = []
        param_states = {}

        for p in self.target_params:
            if p not in telemetry:
                continue
            
            val = float(telemetry[p])
            mean = self.baselines[p]["mean"]
            std = self.baselines[p]["std"]

            # Z-score normalization
            z = (val - mean) / std

            # CUSUM positive and negative accumulators with rapid decay on signal normalization
            if z <= 0.0:
                self.pos_sums[p] = max(0.0, self.pos_sums[p] * 0.70 - self.k)
            else:
                self.pos_sums[p] = max(0.0, self.pos_sums[p] + z - self.k)

            if -z <= 0.0:
                self.neg_sums[p] = max(0.0, self.neg_sums[p] * 0.70 - self.k)
            else:
                self.neg_sums[p] = max(0.0, self.neg_sums[p] - z - self.k)

            max_cusum = max(self.pos_sums[p], self.neg_sums[p])
            is_alert = max_cusum > self.h

            if is_alert:
                triggered_channels.append(p)

            param_states[p] = {
                "cusum_pos": round(self.pos_sums[p], 2),
                "cusum_neg": round(self.neg_sums[p], 2),
                "max_score": round(max_cusum, 2),
                "triggered": is_alert
            }

        return {
            "cusum_alert_active": len(triggered_channels) > 0,
            "triggered_channels": triggered_channels,
            "channel_details": param_states
        }
