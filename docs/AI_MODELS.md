# AI & Physics Models Specification — Aero Engine Digital Twin

## 1. Overview of Integrated Machine Learning & Physics Models

The Digital Twin Core combines first-principles physics models with deep learning and statistical machine learning models to perform anomaly detection, fault classification, short-horizon forecasting, and long-term remaining useful life estimation.

---

## 2. Model Specifications

### 2.1 PyTorch GRU Short-Horizon Forecaster
- **File**: `ml_service/lstm_rul_model.py` / `models/forecast/gru_forecaster.pt`
- **Architecture**: 2-layer Gated Recurrent Unit (GRU) + Dense Linear Output.
- **Input Dimension**: $(60 \times 15)$ tensor (60 sequence steps across 15 telemetry channels).
- **Output Targets**: Multi-step predictions (+10s, +30s, +60s into future) for:
  - Cylinder 1 CHT (`cht1`)
  - Oil Pressure (`oil_press`)
  - Vibration RMS (`vibration_rms`)
  - EGT Temperature Spread (`egt_spread`)
- **Inference Cadence**: ~1.0 Hz (evaluated every 10 telemetry frames).

### 2.2 Autoencoder Anomaly Detector
- **File**: `ml_service/autoencoder_anomaly.py`
- **Architecture**: PyTorch Multi-Layer Perceptron Autoencoder (Encoder: 15 $\rightarrow$ 8 $\rightarrow$ 4; Decoder: 4 $\rightarrow$ 8 $\rightarrow$ 15).
- **Loss Metric**: Mean Squared Error (MSE) reconstruction loss across normalized sensor vector.
- **Anomaly Score**: $S_{\text{AE}} = \frac{1}{N} \sum_{i=1}^{N} (x_i - \hat{x}_i)^2$. Normalized to $[0.0, 1.0]$ against nominal baseline threshold ($0.75$).

### 2.3 CUSUM Change-Point Detector
- **File**: `ml_service/cusum_detector.py`
- **Algorithm**: Cumulative Sum (CUSUM) drift detection algorithm.
- **Purpose**: Detects subtle step-changes or gradual parameter drifts in CHT, Oil Pressure, and Vibration RMS before absolute safety thresholds are breached.

### 2.4 XGBoost Fault Classifier
- **File**: `ml_service/xgboost_fault_classifier.py`
- **Algorithm**: Gradient-boosted decision tree ensemble trained on synthetic fault signatures.
- **Classes**: `NOMINAL`, `CYLINDER_THERMAL`, `OIL_PRESSURE_LOSS`, `EGT_UNBALANCE`, `MECHANICAL_VIBRATION`.

### 2.5 PINN Physics Residual Model
- **File**: `ml_service/pinn_physics_model.py`
- **Formulation**:
  - Expected CHT: $T_{\text{expected}} = T_{\text{ambient}} + k_1 \cdot \text{RPM} + k_2 \cdot \text{MAP} \cdot \text{FuelFlow}$
  - Residual: $R_{\text{CHT}} = |T_{\text{observed}} - T_{\text{expected}}|$
- **Role**: Disentangles environmental ambient temperature variations from true mechanical/thermal engine degradation.

### 2.6 Experimental NASA C-MAPSS RUL Estimator
- **File**: `ml_service/lstm_rul_model.py`
- **Methodology**: LSTM Deep Prognostics model trained on NASA C-MAPSS FD001 turbofan degradation dataset.
- **Important Disclaimer**: RUL estimates are provided as an **experimental analogue in sequence cycles** to demonstrate prognostics UI workflows. RUL estimates are **not validated remaining useful life figures for operational aero-piston engines**.
