"""
XGBoost Multi-Class Fault Classifier
Classifies specific propulsion fault modes and outputs confidence probability distributions.
"""

import os
import xgboost as xgb
import numpy as np
import pandas as pd
import pickle
from typing import Dict, Any, List

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

class XGBoostFaultClassifier:
    FAULT_NAMES = {
        0: "NOMINAL",
        1: "Cylinder Misfire",
        2: "Fuel Injector Abnormality",
        3: "Lubrication Failure / Low Oil Pressure",
        4: "Cylinder Head Overheating",
        5: "Abnormal Mechanical Vibration",
        6: "Electrical Bus Voltage Sensor Drift"
    }

    FAULT_SUBSYSTEMS = {
        0: "Nominal",
        1: "Combustion",
        2: "Fuel System",
        3: "Lubrication",
        4: "Thermal",
        5: "Mechanical",
        6: "Electrical"
    }

    def __init__(self):
        self.model_path = os.path.join(MODELS_DIR, "xgboost_fault.json")
        self.scaler_path = os.path.join(MODELS_DIR, "xgboost_scaler.pkl")
        self.model = None
        self.mean = None
        self.std = None
        
        self.features = [
            "rpm", "map", "cht1", "cht2", "cht3", "cht4",
            "egt1", "egt2", "egt3", "egt4", "oil_press", "oil_temp",
            "fuel_flow", "vibration_rms", "battery_volt"
        ]

    def train_and_save(self, df: pd.DataFrame):
        """Trains XGBoost Classifier on multi-class telemetry dataset."""
        X = df[self.features].values.astype(np.float32)
        y = df["fault_label"].values.astype(int)

        self.mean = np.mean(X, axis=0)
        self.std = np.std(X, axis=0) + 1e-6
        X_norm = (X - self.mean) / self.std

        self.model = xgb.XGBClassifier(
            n_estimators=60,
            max_depth=5,
            learning_rate=0.1,
            objective="multi:softprob",
            num_class=7,
            random_state=42
        )
        self.model.fit(X_norm, y)

        # Save model & scaler
        self.model.save_model(self.model_path)
        with open(self.scaler_path, "wb") as f:
            pickle.dump({"mean": self.mean, "std": self.std}, f)
        print("[XGBoost] Fault Classifier model trained & saved successfully.")

    def load_model(self) -> bool:
        if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
            self.model = xgb.XGBClassifier()
            self.model.load_model(self.model_path)
            with open(self.scaler_path, "rb") as f:
                data = pickle.load(f)
                self.mean = data["mean"]
                self.std = data["std"]
            return True
        return False

    def predict_fault(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Predicts fault class and confidence for live telemetry frame."""
        if self.model is None:
            if not self.load_model():
                from ml_service.dataset_loader import generate_multiclass_fault_dataset
                df = generate_multiclass_fault_dataset(4000)
                self.train_and_save(df)

        vec = np.array([[float(telemetry.get(f, 0.0)) for f in self.features]], dtype=np.float32)
        vec_norm = (vec - self.mean) / self.std

        probs = self.model.predict_proba(vec_norm)[0]
        class_idx = int(np.argmax(probs))
        confidence = float(probs[class_idx])

        return {
            "fault_code": class_idx,
            "fault_type": self.FAULT_NAMES.get(class_idx, "Unknown"),
            "subsystem": self.FAULT_SUBSYSTEMS.get(class_idx, "General"),
            "confidence_pct": round(confidence * 100, 1),
            "confidence_tier": f"{'HIGH' if confidence >= 0.85 else 'MEDIUM'} ({round(confidence, 2)})",
            "probabilities": {self.FAULT_NAMES[i]: round(float(p), 3) for i, p in enumerate(probs)}
        }
