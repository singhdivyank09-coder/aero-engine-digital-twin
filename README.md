# Aero Engine Digital Twin — Demo Prototype

> **Developed by Team Hackonauts09**  
> *MALE UAV Propulsion Reliability, Real-Time Diagnostics & Predictive Health Monitoring System*

---

## 1. Project Overview & Problem Statement

Medium-Altitude Long-Endurance (MALE) Unmanned Aerial Vehicles (UAVs) rely heavily on 4-cylinder turbocharged aero-piston engines for extended mission endurance. In-flight thermal degradation, lubrication pressure drops, combustion exhaust imbalances, and mechanical vibration anomalies can lead to catastrophic propulsion failures if not detected early.

The **Aero Engine Digital Twin — Demo Prototype** solves this challenge by providing a real-time Ground Control Station (GCS) health monitoring and predictive analytics suite. Operating under an authoritative **Single Source of Truth** paradigm at 10 Hz, the system combines first-principles physics models, PyTorch deep learning forecasters, autoencoder anomaly detectors, and a 5-state predictive health engine to deliver early warnings before physical safety thresholds are breached.

---

## 2. Key Implemented Capabilities

- **10 Hz Real-Time Telemetry Pipeline**: Ingests, validates, and monitors 15 physical propulsion parameters (RPM, MAP, CHT 1–4, EGT 1–4, Oil Pressure, Oil Temp, Fuel Flow, Vibration RMS, Battery Voltage).
- **Physics-Informed Neural Network (PINN) Residuals**: Disentangles environmental ambient variations from mechanical degradation using first-principles thermodynamic curves.
- **PyTorch GRU 60-Second Short-Horizon Forecaster**: Predicts future propulsion parameter trajectories (+10s, +30s, +60s into future) to anticipate thermal and lubrication risks.
- **5-State Predictive Health State Machine**: Manages progressive system health transitions (`NORMAL` $\leftrightarrow$ `WATCH` $\leftrightarrow$ `CAUTION` $\leftrightarrow$ `WARNING` $\leftrightarrow$ `CRITICAL`) with $K$-of-$M$ temporal persistence filtering (4 of 6 frames) and stepwise hysteresis recovery.
- **Predictive Time-to-Risk Engine**: Computes exact time remaining until threshold crossing, automatically updating to `0 s — LIMIT EXCEEDED` upon limit breach.
- **2D Component Digital Twin Inspector**: Interactive schematic rendering real-time thermal degradation overlays for individual cylinder heads, oil pumps, and exhaust manifolds.
- **Advisory Digital Flight Control System (DFCS)**: Provides real-time emergency checklist recommendations (e.g. throttle reduction, Return-to-Base advisories).
- **Interactive Fault Injection Engine**: Enables live simulation of Cylinder 1 Thermal Degradation, Oil Pressure Loss, EGT Spread Unbalance, and Mechanical Vibration Spikes.
- **Lightweight Database Storage**: Stores 0.2 Hz compact mission snapshots in SQLite to maintain a small database footprint (< 250 MB).

---

## 3. Technology Stack

- **Backend Framework**: Python 3.10+, FastAPI, Uvicorn, AsyncIO, WebSockets.
- **Machine Learning & AI**: PyTorch (GRU Forecaster & Autoencoder), XGBoost (Fault Classifier), NumPy, SciPy.
- **Database**: SQLite 3 (`data/telemetry_db.sqlite`).
- **Frontend GCS UI**: HTML5, Vanilla CSS3 (Custom Light Aerospace Design System), JavaScript (ES6+), Chart.js.
- **Automated Testing & QA**: Pytest, Playwright (End-to-End Browser Verification).

---

## 4. Repository Structure

```
aero_engine_digital_twin/
├── backend/                        # FastAPI Backend & Core Engine
│   ├── main.py                     # Web API Routes, WebSockets & App Entry
│   ├── digital_twin_core.py        # Authoritative Single Source of Truth Core
│   ├── predictive_state_machine.py # 5-State Machine & Evidence Fusion
│   ├── predictive_health_engine.py # Time-to-Risk Calculation Engine
│   ├── gru_forecast_service.py     # PyTorch GRU Forecaster Inference
│   ├── telemetry_simulator.py      # 10Hz Physics Telemetry Generator
│   ├── metrics_tracker.py          # Data Integrity & Latency Instrumentation
│   └── database.py                 # SQLite Initialization & 0.2Hz Snapshots
├── docs/                           # Comprehensive Technical Documentation
│   ├── ARCHITECTURE.md             # System Architecture & Flow Diagrams
│   ├── INSTALLATION.md             # Detailed Setup & Configuration Guide
│   ├── USER_GUIDE.md               # Feature Walkthrough & Operating Guide
│   ├── AI_MODELS.md                # Machine Learning Model Specifications
│   ├── DATASETS_AND_LIMITATIONS.md # Provenance, Disclaimers & Limitations
│   └── TESTING.md                  # Test Suite & Acceptance Procedures
├── frontend/                       # Ground Control Station HMI UI
│   ├── index.html                  # GCS Dashboard HTML Structure
│   ├── app.js                      # Real-time Telemetry & Charting Logic
│   └── static/styles.css           # Aerospace Glassmorphism Styling
├── ml_service/                     # ML Model Architecture Classes
│   ├── autoencoder_anomaly.py      # Autoencoder Anomaly Detector
│   ├── cusum_detector.py           # CUSUM Change-Point Detector
│   ├── lstm_rul_model.py           # NASA C-MAPSS RUL Model Class
│   ├── pinn_physics_model.py       # PINN Physics Residual Model
│   └── xgboost_fault_classifier.py # XGBoost Multi-Class Fault Classifier
├── models/                         # Pre-trained Model Weights (.pt, .json)
├── tests/                          # Automated Pytest Test Suite
├── requirements.txt                # Python Dependencies
└── README.md                       # Project Master Readme
```

---

## 5. Local Installation & Startup Instructions

### 5.1 Clone & Setup Environment
```bash
git clone https://github.com/singhdivyank09-coder/aero-engine-digital-twin.git
cd aero-engine-digital-twin

# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Activate virtual environment (Linux/macOS)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 5.2 Start the Backend Application Server
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 5.3 Access the Ground Control Station Dashboard
Open your web browser and navigate to:
```
http://127.0.0.1:8000
```

#### Demo Login Credentials:
- **Engineer Role**: Username `engineer` / Password `engineer123` *(Full access including Fault Injection)*
- **Operator Role**: Username `operator` / Password `operator123` *(Dashboard & Telemetry view)*

---

## 6. How to Run a Live Demonstration

1. **Log In**: Access `http://127.0.0.1:8000` and log in as `engineer` / `engineer123`.
2. **Observe Baseline**: Verify that the **System State** is `NORMAL` and **Health Index** is `> 96%`.
3. **Inject Fault**: Navigate to **Fault Injection & Analytics**, select **Cylinder 1 Thermal Degradation** (`CYLINDER_THERMAL`), set Profile to `GRADUAL`, and click **INJECT FAULT**.
4. **Observe GRU Predictive Forecaster**: Watch the +30s and +60s projected curves rise on the **Predictive Analytics** tab before the 145°C limit is reached.
5. **Observe State Escalation**: Note the state transitioning (`NORMAL` $\rightarrow$ `WATCH` $\rightarrow$ `CAUTION` $\rightarrow$ `WARNING` $\rightarrow$ `CRITICAL`).
6. **Observe Time-to-Risk & DFCS Advisories**: When CHT1 exceeds 145.0°C, observe the **Time-to-Risk** updating to `0 s — LIMIT EXCEEDED` and emergency advisories appearing on the **GCS/DFCS Demonstrator**.
7. **Clear Fault & Stepwise Recovery**: Click **CLEAR ALL FAULTS** and observe the stepwise hysteresis de-escalation back to `NORMAL`.

---

## 7. Automated Testing Suite

To run the complete automated unit and integration test suite:

```bash
python -m pytest tests/
```

To run the time-to-risk boundary acceptance test:
```bash
python scratch/test_time_to_risk_acceptance.py
```

---

## 8. Dataset Provenance & Operational Disclaimers

> [!IMPORTANT]
> **DEMONSTRATOR DISCLAIMER**:
> This software is a **functional software prototype** created by Team **Hackonauts09** for research, evaluation, and demonstration purposes.
> - **Simulated Telemetry**: Uses simulated 10 Hz propulsion telemetry feeds. It is **not connected to an operational UAV or physical aircraft**.
> - **Experimental RUL**: Remaining Useful Life estimates use NASA C-MAPSS turbofan degradation curves as an **experimental analogue metric in sequence cycles**, not a certified remaining useful life figure for aero-piston engines.
> - **No Flight Certification**: This software is not flight-certified (DO-178C / DO-254) and must not be used for actual flight navigation or real-world aircraft operation.
> - **No Institutional Endorsement**: This prototype does not claim DRDO employment, official defense endorsement, or military flight certification.
