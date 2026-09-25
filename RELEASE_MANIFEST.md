# DRDO iDEX MALE UAV Aero-Piston Engine Digital Twin — Release Manifest

**Official Prototype Demo Release Package (SIH 26054)**  
**Release Date:** 2026-09-20  
**Version:** v2.0.0-PROTOTYPE  
**System Status:** ACCEPTED & FREEZE-LOCKED  

---

## 1. Source Code Core Modules

| Module / Component | Path | Function |
| :--- | :--- | :--- |
| **FastAPI Orchestrator** | `backend/main.py` | REST endpoints, WebSocket 10Hz stream broadcast, static asset serving |
| **Digital Twin Core** | `backend/digital_twin_core.py` | Single source of truth, atomic snapshot generator, 5-state health machine |
| **Predictive Health Engine** | `backend/predictive_health_engine.py` | Multi-source predictive evidence fusion & early warning assessment |
| **Predictive State Machine** | `backend/predictive_state_machine.py` | Hysteresis state transition logic & temporal persistence filtering |
| **GRU Forecast Service** | `backend/gru_forecast_service.py` | Sequence-to-sequence PyTorch GRU trajectory forecasting (~1Hz / 60-step) |
| **Telemetry Simulator** | `backend/telemetry_simulator.py` | Physical sensor noise, scenario physics, time-dependent fault injection |
| **Physics Engine** | `backend/physics_engine.py` | 0D/1D Thermodynamic thermodynamic surrogate reference calculations |
| **PINN Physics Model** | `ml_service/pinn_physics_model.py` | Environmental lapse rates & expected physical baseline calculations |
| **Autoencoder Model** | `ml_service/autoencoder_anomaly.py` | Deep Autoencoder multivariate anomaly score computation |
| **CUSUM Change Detector** | `ml_service/cusum_detector.py` | Cumulative sum change-point detection |
| **XGBoost Classifier** | `ml_service/xgboost_fault_classifier.py` | 7-class multi-fault condition diagnostic classifier |
| **LSTM RUL Model** | `ml_service/lstm_rul_model.py` | Sequence-based RUL prognostics estimator (C-MAPSS FD001) |
| **Replay Service** | `backend/replay_service.py` | Historical 300-frame mission replay & summary report pipeline |
| **Metrics Tracker** | `backend/metrics_tracker.py` | High-resolution performance, latency & data integrity measurement |
| **Model Registry** | `backend/model_registry.py` | Artifact verification & multi-dataset provenance mapping |
| **Frontend HMI Application** | `frontend/index.html`, `frontend/app.js`, `frontend/styles.css` | Light aerospace Ground Control Station (GCS) user interface |

---

## 2. Trained Model Artifacts

| Model Name | Artifact File Path | Framework | Artifact Size | Status |
| :--- | :--- | :--- | :--- | :---: |
| **PyTorch Autoencoder** | `models/autoencoder_anomaly.pt` | PyTorch | 5.5 KB | `VERIFIED` |
| **Autoencoder Scaler** | `models/autoencoder_scaler.pkl` | Scikit-Learn | 310 B | `VERIFIED` |
| **PyTorch GRU Forecaster** | `models/forecast/gru_forecaster.pt` | PyTorch | 190.5 KB | `VERIFIED` |
| **GRU Input Scaler** | `models/forecast/input_scaler.pkl` | Scikit-Learn | 361 B | `VERIFIED` |
| **GRU Target Scaler** | `models/forecast/target_scaler.pkl` | Scikit-Learn | 361 B | `VERIFIED` |
| **LSTM RUL Estimator** | `models/lstm_rul.pt` | PyTorch | 61.6 KB | `VERIFIED` |
| **LSTM RUL Scaler** | `models/lstm_scaler.pkl` | Scikit-Learn | 225 B | `VERIFIED` |
| **XGBoost Classifier** | `models/xgboost_fault.json` | XGBoost | 350.4 KB | `VERIFIED` |
| **XGBoost Scaler** | `models/xgboost_scaler.pkl` | Scikit-Learn | 289 B | `VERIFIED` |

---

## 3. Dataset Directories & Provenance

| Dataset Identifier | Local Directory | Original Provenance | Role in Digital Twin |
| :--- | :--- | :--- | :--- |
| **NASA C-MAPSS** | `datasets/cmapss/` | NASA Prognostics Center (FD001) | Analogue Run-to-Failure RUL Prognostics |
| **ALFA UAV** | `datasets/alfa/` | Autonomous Controls Lab | Autonomous Flight Trajectory Telemetry |
| **RFLYMAD** | `datasets/rflymad/` | Beihang University | Multi-Rotor Actuator & Sensor Anomaly |
| **UAVFD** | `datasets/uavfd/` | Public UAV Fault Collection | Fixed-Wing Engine & Control Surface Faults |

---

## 4. Evaluation Metrics Artifacts

- **Autoencoder Evaluation Metrics:** `models/anomaly_metrics.json`
- **GRU Forecaster Evaluation Metrics:** `models/forecast/metrics.json`
- **LSTM RUL Evaluation Metrics:** `models/rul_metrics.json`

---

## 5. System Acceptance & Documentation Reports

- **Final Full-System Acceptance Report:** `FINAL_ACCEPTANCE_REPORT.md`
- **Live Demo Procedure Checklist:** `DEMO_CHECKLIST.md`
- **Quick Troubleshooting Guide:** `DEMO_TROUBLESHOOTING.md`
- **System README & Startup Guide:** `README.md`

---

## 6. Project Configuration & Database Files

- **Dependencies Specification:** `requirements.txt`
- **GRU Model Config:** `models/forecast/config.json`
- **SQLite Database:** `data/telemetry_db.sqlite` (WAL Mode)

---

## 7. Prototype Limitations & Disclaimers

1. **Software Demonstrator Notice:** Developed as an aerospace digital twin software demonstrator. Not certified for operational flight control.
2. **Physics Surrogate Model:** Uses a 0D/1D thermodynamic surrogate model for a 1211cc 4-cylinder turbocharged aero-piston engine.
3. **Analogue Prognostics Source:** NASA C-MAPSS turbofan dataset is used solely as an analogous prognostics/degradation source.
4. **Validation Requirement:** Requires future engine test-rig validation, Hardware-in-the-Loop (HIL) testing, and platform-specific flight-test calibration.
