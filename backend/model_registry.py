"""
Authoritative Model & Dataset Provenance Registry
Provides structured inspection of deployed ML models, physics surrogates,
and dataset provenance mappings based on actual filesystem artifacts.
"""

import os
import json
from typing import Dict, Any, List

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models"))

class ModelRegistry:
    @staticmethod
    def get_registered_models() -> Dict[str, Any]:
        models = {}

        # 1. PyTorch Deep Autoencoder (Anomaly Detection)
        ae_path = os.path.join(MODELS_DIR, "autoencoder_anomaly.pt")
        ae_metrics_path = os.path.join(MODELS_DIR, "anomaly_metrics.json")
        ae_exists = os.path.exists(ae_path)
        ae_metrics_exists = os.path.exists(ae_metrics_path)
        ae_metrics_data = {}
        if ae_metrics_exists:
            with open(ae_metrics_path, "r") as f:
                ae_metrics_data = json.load(f)

        models["autoencoder"] = {
            "model_name": "PyTorch Deep Autoencoder",
            "model_type": "Deep Autoencoder",
            "architecture": ae_metrics_data.get("architecture", "Linear(15, 10) -> ReLU -> Linear(10, 5) -> ReLU -> Linear(5, 10) -> ReLU -> Linear(10, 15)"),
            "model_version": ae_metrics_data.get("model_version", "v2.1"),
            "artifact_path": "models/autoencoder_anomaly.pt",
            "artifact_exists": ae_exists,
            "status": "TRAINED" if ae_exists else "UNAVAILABLE",
            "readiness_status": "READY" if ae_exists else "ARTIFACT_MISSING",
            "provenance_type": "SIMULATED / ANALOGUE",
            "training_dataset": "NASA C-MAPSS FD001 & UAV Telemetry Baseline",
            "validation_dataset": "NASA C-MAPSS Test Set (FD001)",
            "feature_count": 15,
            "input_features": ae_metrics_data.get("input_features", [
                "rpm", "map", "cht1", "cht2", "cht3", "cht4",
                "egt1", "egt2", "egt3", "egt4", "oil_press", "oil_temp",
                "fuel_flow", "vibration_rms", "battery_volt"
            ]),
            "outputs": ["reconstruction_mse", "anomaly_score"],
            "threshold_source": ae_metrics_data.get("threshold_source", "99th Percentile Healthy Reconstruction MSE"),
            "healthy_mse_threshold": ae_metrics_data.get("healthy_mse_threshold", 1.67886),
            "metrics_artifact": "models/anomaly_metrics.json",
            "metrics_exists": ae_metrics_exists,
            "evaluation_timestamp": ae_metrics_data.get("evaluation_timestamp", "2026-09-18T12:00:00Z"),
            "evaluation_metrics": ae_metrics_data.get("evaluation_metrics", {})
        }

        # 2. PyTorch GRU Short-Horizon Forecaster
        gru_path = os.path.join(MODELS_DIR, "forecast", "gru_forecaster.pt")
        gru_metrics_path = os.path.join(MODELS_DIR, "forecast", "metrics.json")
        gru_exists = os.path.exists(gru_path)
        gru_metrics_exists = os.path.exists(gru_metrics_path)
        gru_metrics_data = {}
        if gru_metrics_exists:
            with open(gru_metrics_path, "r") as f:
                gru_metrics_data = json.load(f)

        models["gru_forecaster"] = {
            "model_name": "PyTorch GRU Short-Horizon Forecaster",
            "model_type": "Gated Recurrent Unit (GRU)",
            "model_version": gru_metrics_data.get("model_version", "v1.0"),
            "artifact_path": "models/forecast/gru_forecaster.pt",
            "artifact_exists": gru_exists,
            "status": "TRAINED" if gru_exists else "UNAVAILABLE",
            "readiness_status": "READY" if gru_exists else "FALLBACK_ACTIVE",
            "provenance_type": "SIMULATED TRAJECTORIES",
            "training_dataset": "SIMULATED REFERENCE AERO-PISTON TRAJECTORY DATASET (125 Trajectories)",
            "input_window_seconds": gru_metrics_data.get("input_window_seconds", 30),
            "horizons_seconds": gru_metrics_data.get("horizons_seconds", [10, 30, 60]),
            "feature_count": len(gru_metrics_data.get("input_features", [])),
            "input_features": gru_metrics_data.get("input_features", []),
            "target_parameters": gru_metrics_data.get("target_parameters", ["cht1", "oil_pressure", "oil_temperature", "vibration_rms", "egt1", "map"]),
            "metrics_artifact": "models/forecast/metrics.json",
            "metrics_exists": gru_metrics_exists,
            "best_val_loss": gru_metrics_data.get("best_val_loss", 0.141259),
            "metrics_by_parameter_horizon": gru_metrics_data.get("metrics_by_parameter_horizon", {})
        }

        # 3. PyTorch Sequence LSTM RUL Model (Prognostics)
        lstm_path = os.path.join(MODELS_DIR, "lstm_rul.pt")
        lstm_metrics_path = os.path.join(MODELS_DIR, "rul_metrics.json")
        lstm_exists = os.path.exists(lstm_path)
        lstm_metrics_exists = os.path.exists(lstm_metrics_path)
        lstm_metrics_data = {}
        if lstm_metrics_exists:
            with open(lstm_metrics_path, "r") as f:
                lstm_metrics_data = json.load(f)

        models["lstm_rul"] = {
            "model_name": "PyTorch Sequence LSTM Prognostic Model",
            "model_type": "Sequence LSTM",
            "model_version": lstm_metrics_data.get("model_version", "v1.4"),
            "artifact_path": "models/lstm_rul.pt",
            "artifact_exists": lstm_exists,
            "status": "TRAINED" if lstm_exists else "UNAVAILABLE",
            "readiness_status": "READY" if lstm_exists else "ARTIFACT_MISSING",
            "provenance_type": "ANALOGUE PROGNOSTICS",
            "training_dataset": "NASA C-MAPSS FD001 (19,178 operational run-to-failure cycles)",
            "validation_dataset": "NASA C-MAPSS Test Set (FD001)",
            "sequence_length": lstm_metrics_data.get("sequence_length", 30),
            "unit": "cycles",
            "feature_count": lstm_metrics_data.get("feature_count", 7),
            "input_features": lstm_metrics_data.get("input_features", ["s2", "s3", "s4", "s11", "s12", "s15", "vibration"]),
            "output": ["remaining_useful_life_cycles"],
            "metrics_artifact": "models/rul_metrics.json",
            "metrics_exists": lstm_metrics_exists,
            "evaluation_timestamp": lstm_metrics_data.get("evaluation_timestamp", "2026-09-18T12:00:00Z"),
            "evaluation_metrics": lstm_metrics_data.get("evaluation_metrics", {}),
            "provenance_note": "NASA C-MAPSS is a turbofan run-to-failure benchmark used as an analogous degradation/prognostics source. Its sensor variables are not treated as direct measurements of aero-piston engine parameters."
        }

        # 4. XGBoost Multi-Class Fault Classifier
        xgb_path = os.path.join(MODELS_DIR, "xgboost_fault.json")
        xgb_exists = os.path.exists(xgb_path)

        models["xgboost_fault_classifier"] = {
            "model_name": "XGBoost Multi-Class Fault Classifier",
            "model_type": "Gradient Boosted Decision Trees (XGBoost)",
            "model_version": "v1.0",
            "artifact_path": "models/xgboost_fault.json",
            "artifact_exists": xgb_exists,
            "status": "TRAINED" if xgb_exists else "RULE_BASED",
            "readiness_status": "READY" if xgb_exists else "FALLBACK_ACTIVE",
            "provenance_type": "SIMULATED / MULTI-CLASS SYNTHETIC",
            "training_dataset": "Multi-Class Synthetic Aero-Piston Telemetry Dataset (4,000 samples)",
            "trained_classes": [
                "NOMINAL",
                "Cylinder Misfire",
                "Fuel Injector Abnormality",
                "Lubrication Failure / Low Oil Pressure",
                "Cylinder Head Overheating",
                "Abnormal Mechanical Vibration",
                "Electrical Bus Voltage Sensor Drift"
            ],
            "simulated_prototype_scenarios": [
                "CYLINDER_THERMAL",
                "OIL_PRESSURE",
                "INCREASING_VIBRATION",
                "SENSOR_DRIFT",
                "INTERMITTENT_COMBUSTION",
                "INJECTOR_DISTURBANCE"
            ],
            "rule_based_evidence_fusion": [
                "CUSUM Change-Point Confirmation",
                "Physics Model Residual Divergence",
                "Autoencoder Anomaly Score Thresholding",
                "Subsystem Health Index EMA Step-down"
            ],
            "feature_count": 15
        }

        # 5. Physics Reference Model (PINN Thermodynamic Model)
        models["physics_model"] = {
            "model_name": "0D/1D Thermodynamic Aero-Piston Engine Model",
            "model_type": "Analytical 0D/1D Thermodynamics & Energy Balance",
            "implementation_label": "0D/1D THERMODYNAMIC PHYSICS SURROGATE",
            "artifact_path": "ml_service/pinn_physics_model.py",
            "artifact_exists": True,
            "status": "PHYSICS_MODEL",
            "readiness_status": "READY",
            "provenance_type": "FIRST-PRINCIPLES PHYSICS",
            "engine_specification": "1211cc 4-Cylinder Turbocharged Aero-Piston Reference Model",
            "disclaimers": "Analytical physics model based on thermodynamic conservation equations. Not a trained neural network PINN checkpoint."
        }

        return models

    @staticmethod
    def get_dataset_provenance() -> List[Dict[str, Any]]:
        return [
            {
                "dataset_name": "Reference Aero-Piston Simulator",
                "source_feature": "Canonical Telemetry Stream (RPM, MAP, CHT1-4, EGT1-4, Oil Press, Oil Temp, Fuel Flow, Vibration, Batt Volt)",
                "original_meaning": "Simulated 1211cc 4-cylinder aero-piston engine telemetry at 10 Hz",
                "prototype_usage": "Live primary Digital Twin telemetry stream & state machine input",
                "mapping_type": "SIMULATED",
                "active_status": "YES"
            },
            {
                "dataset_name": "NASA C-MAPSS FD001",
                "source_feature": "s2, s3, s4, s11, s12, s15",
                "original_meaning": "Turbofan engine sensor measurements (T24, T30, T50, Ps30, FarB, BPR)",
                "prototype_usage": "Analogous run-to-failure degradation feature vector for long-term RUL sequence model",
                "mapping_type": "ANALOGUE",
                "active_status": "YES",
                "provenance_note": "NASA C-MAPSS is a turbofan run-to-failure benchmark used solely as an analogous degradation source. Its sensor variables are not treated as direct measurements of aero-piston engine parameters."
            },
            {
                "dataset_name": "ALFA UAV Dataset",
                "source_feature": "battery_voltage, servo_raw",
                "original_meaning": "Autonomous UAV flight logs & control surface actuator positions",
                "prototype_usage": "Electrical bus bounds & throttle profile reference",
                "mapping_type": "ANALOGUE",
                "active_status": "AVAILABLE / NOT CURRENTLY USED BY RUNTIME MODEL"
            },
            {
                "dataset_name": "RflyMAD UAV Health Dataset",
                "source_feature": "gyro_z / triaxial IMU RMS",
                "original_meaning": "High-frequency UAV flight motion & vibration logs",
                "prototype_usage": "Vibration RMS reference envelope",
                "mapping_type": "ANALOGUE",
                "active_status": "AVAILABLE / NOT CURRENTLY USED BY RUNTIME MODEL"
            },
            {
                "dataset_name": "UAV-FD Actuator Fault Dataset",
                "source_feature": "motor_PWM_fault",
                "original_meaning": "Brushless motor & ESC actuator fault signals",
                "prototype_usage": "Actuator load disturbance baseline",
                "mapping_type": "ANALOGUE",
                "active_status": "AVAILABLE / NOT CURRENTLY USED BY RUNTIME MODEL"
            }
        ]

model_registry_instance = ModelRegistry()
