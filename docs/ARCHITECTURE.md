# System Architecture — Aero Engine Digital Twin

## 1. Executive Summary & Core Paradigm
The **Aero Engine Digital Twin — Demo Prototype** (developed by Team **Hackonauts09**) is a high-fidelity Ground Control Station (GCS) flight reliability and health monitoring system designed for 4-cylinder turbocharged MALE UAV aero-piston propulsion units.

The system enforces a **Single Source of Truth** paradigm: all physical telemetry processing, physics residual checks, machine learning inference, evidence fusion, state transitions, and advisory flight control system (DFCS) interventions occur within a unified atomic pipeline executed at **10 Hz**.

---

## 2. System Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                            GROUND CONTROL STATION (GCS)                           |
|                      HTML5 / CSS3 / JavaScript (Vanilla) UI                       |
+-----------------------------------------------------------------------------------+
                                        ^
                                        | (WebSocket @ 10Hz / REST API)
                                        v
+-----------------------------------------------------------------------------------+
|                             FASTAPI BACKEND SERVICE                               |
|                               (backend/main.py)                                   |
+-----------------------------------------------------------------------------------+
                                        |
                                        v
+-----------------------------------------------------------------------------------+
|                            DIGITAL TWIN CORE ENGINE                               |
|                       (backend/digital_twin_core.py)                              |
|                                                                                   |
|  +-----------------------+  +------------------------+  +----------------------+  |
|  | Telemetry Simulator   |  | PINN Physics Model     |  | Autoencoder Anomaly |  |
|  | (10Hz Real-Time Feed) |  | (First-Principles Delta|  | (Multi-Sensor Norm)  |  |
|  +-----------------------+  +------------------------+  +----------------------+  |
|              |                          |                          |              |
|              +--------------------------+--------------------------+              |
|                                         |                                         |
|                                         v                                         |
|  +-----------------------------------------------------------------------------+  |
|  |             Multi-Source Evidence Fusion Engine & Risk Engine               |  |
|  |      - CUSUM Change-Point Detector    - XGBoost Fault Classifier            |  |
|  |      - PyTorch GRU 60s Forecaster       - Predictive Time-to-Risk Engine    |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|                                         v                                         |
|  +-----------------------------------------------------------------------------+  |
|  |               5-State Predictive Health System Machine                      |  |
|  |      NORMAL  <-->  WATCH  <-->  CAUTION  <-->  WARNING  <-->  CRITICAL        |  |
|  |      (K-of-M Persistence: 4/6 frames | Progressive Hysteresis Recovery)    |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
                                        |
                         (0.2 Hz Compact Snapshots)
                                        v
+-----------------------------------------------------------------------------------+
|                           SQLITE TELEMETRY DATABASE                               |
|                          (data/telemetry_db.sqlite)                               |
+-----------------------------------------------------------------------------------+
```

---

## 3. Core Engine Components

### 3.1 Telemetry Processing & Ingestion (`backend/telemetry_simulator.py`)
- **Sampling Frequency**: 10 Hz (100ms interval).
- **Monitored Channels**:
  - Engine Speed (`rpm`), Manifold Absolute Pressure (`map`), Fuel Flow (`fuel_flow`), Battery Voltage (`battery_volt`), Vibration RMS (`vibration_rms`).
  - Cylinder Head Temperatures (`cht1`, `cht2`, `cht3`, `cht4`).
  - Exhaust Gas Temperatures (`egt1`, `egt2`, `egt3`, `egt4`).
  - Lubrication Metrics (`oil_press`, `oil_temp`).
- **Data Integrity Validation**: Rejects non-numeric, null, infinite, or out-of-physical-range sensor values (0–7000 RPM, 0–300°C CHT, 0–10 bar Oil Pressure).

### 3.2 Physics-Informed Neural Network (PINN) Residuals (`ml_service/pinn_physics_model.py`)
Calculates first-principles thermodynamic and fluid dynamics expected values based on Rotax 914 reference operating curves:
- **Thermodynamic Expectation**: Expected CHT derived as a function of RPM, Manifold Pressure, and Fuel Flow.
- **Residual Delta**: $\Delta \text{CHT} = \text{Observed CHT} - \text{Expected CHT}$.
- **Lubrication Expectation**: Expected Oil Pressure derived as a function of RPM and Oil Temperature.

### 3.3 PyTorch GRU 60-Second Short-Horizon Forecaster (`backend/gru_forecast_service.py`)
- **Architecture**: 2-layer Gated Recurrent Unit (GRU) with Linear Projection Head.
- **Input Window**: 60 consecutive telemetry frames (6 seconds of history at 10 Hz).
- **Forecast Horizons**: Predicts future values at **+10s**, **+30s**, and **+60s** into the future.
- **Output Channels**: `cht1`, `oil_press`, `vibration_rms`, `egt_spread`.

### 3.4 Predictive Health & Time-to-Risk Engine (`backend/predictive_health_engine.py`)
- **Threshold Crossing Projection**: Evaluates observed measurements and GRU forecasts against channel safety limits:
  - CHT Upper Limit: **145.0 °C**
  - Oil Pressure Lower Limit: **2.50 bar**
  - Vibration RMS Upper Limit: **2.50 g**
  - EGT Spread Upper Limit: **90.0 °C**
- **Boundary Logic**:
  - If limit is **already breached**: `time_to_risk = 0.0 s`, `risk_status = LIMIT_EXCEEDED`.
  - If limit is **approached on GRU forecast**: `time_to_risk = t_cross`, `risk_status = PREDICTIVE_RISK`.
  - If parameters are **nominal**: `time_to_risk = 999.0 s`, `risk_status = NOMINAL`.

### 3.5 5-State Predictive Health State Machine (`backend/predictive_state_machine.py`)
Evaluates multi-source evidence scores $E_{\text{sub}} \in [0.0, 1.0]$ across 5 subsystems: **Thermal**, **Lubrication**, **Combustion**, **Mechanical**, and **Electrical**.
- **States**: `NORMAL` $\leftrightarrow$ `WATCH` $\leftrightarrow$ `CAUTION` $\leftrightarrow$ `WARNING` $\leftrightarrow$ `CRITICAL`.
- **Persistence Filter**: Requires **4 out of 6 consecutive frames** ($K$-of-$M$) to trigger an escalation.
- **Stepwise Hysteresis Recovery**: De-escalates state stepwise (e.g. `CRITICAL` $\rightarrow$ `WARNING` $\rightarrow$ `CAUTION` $\rightarrow$ `WATCH` $\rightarrow$ `NORMAL`) requiring **4 consecutive nominal frames** per step, preventing alert chatter.

---

## 4. Database & Storage Architecture
- **Engine**: SQLite 3 (`data/telemetry_db.sqlite`).
- **Telemetry Recording Cadence**: **0.2 Hz** (1 frame every 5 seconds) to maintain lightweight database size (< 250 MB) during long continuous operations.
- **In-Memory Buffer**: Sliding 600-frame circular buffer for real-time GCS rendering and GRU inference.
