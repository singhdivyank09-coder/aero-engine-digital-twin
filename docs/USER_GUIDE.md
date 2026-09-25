# User Guide & Demo Walkthrough — Aero Engine Digital Twin

## 1. Overview
The Ground Control Station (GCS) UI provides real-time propulsion health monitoring, predictive degradation analytics, 2D component schematics, and simulated fault injection controls for 4-cylinder aero-piston UAV engines.

---

## 2. Interface Layout

### 2.1 Top Navigation & Header
- **System State Badge**: Displays current global state (`NORMAL`, `WATCH`, `CAUTION`, `WARNING`, `CRITICAL`).
- **Health Index Gauge**: Displays overall propulsion health percentage (0.0% – 100.0%).
- **Anomaly Score**: Real-time multi-sensor autoencoder anomaly score.
- **Prototype RUL Estimate**: Experimental prognostics estimate in sequence cycles based on NASA C-MAPSS model curves.
- **User Profile**: Displays authenticated role (`ENGINEER` or `OPERATOR`) and user display label (`Demo Prototype Operator`).

### 2.2 Navigation Tabs
1. **Operator Dashboard**: Primary telemetry gauges, RPM, CHT/EGT temperature spreads, oil pressure, battery voltage, and 10Hz live trend charts.
2. **2D Digital Twin Schematic**: Interactive 2D component diagram showing individual cylinder heads (CHT 1–4), oil pump, exhaust manifold, and electrical generator with per-component thermal degradation overlays.
3. **Predictive Analytics & Forecaster**: Real-time PyTorch GRU 60-second forward projection curves (+10s, +30s, +60s) for CHT1, Oil Pressure, and Vibration RMS.
4. **Fault Injection & Analytics**: Control panel to trigger simulated physical fault scenarios.
5. **GCS / DFCS Demonstrator**: Advisory Digital Flight Control System interface displaying pilot advisories, emergency checklist recommendations, and manual control overrides.
6. **Mission Replay & Reports**: Historical mission telemetry viewer and report exporter.

---

## 3. Running a Guided Demonstration

### Step 1: Nominal Baseline Operation
1. Log in as `engineer` / `engineer123`.
2. Observe that the **System State** is `NORMAL` and **Health Index** is `> 96%`.
3. Note that the **Predictive Early Warning** panel displays `999 s (Nominal)`.

### Step 2: Injecting Thermal Degradation (Cylinder 1 CHT Spike)
1. Navigate to the **Fault Injection & Analytics** tab.
2. Select **Cylinder 1 Thermal Degradation** (`CYLINDER_THERMAL`).
3. Set **Profile** to `GRADUAL` and **Intensity** to `1.8`.
4. Click **INJECT FAULT**.

### Step 3: Observing Predictive Early Warning & State Machine Escalation
1. Observe the **PyTorch GRU Forecaster**: the +30s and +60s curves for CHT1 start angling upwards before current CHT1 breaches the 145.0°C limit.
2. The System State transitions through progressive hysteresis: `NORMAL` $\rightarrow$ `WATCH` $\rightarrow$ `CAUTION` $\rightarrow$ `WARNING`.
3. The **Predictive Time-to-Risk** panel decreases dynamically (e.g. `45.0 s`, `20.0 s`).

### Step 4: Physical Limit Breach & Emergency Advisory
1. As CHT1 reaches **145.0°C**, the System State escalates to `CRITICAL`.
2. The **Predictive Early Warning** badge updates immediately to `0 s — LIMIT EXCEEDED`.
3. The **GCS/DFCS Demonstrator** highlights Cylinder 1 in red and generates advisory recommendations: `REDUCE THROTTLE TO 65% / INITIATE RETURN TO BASE (RTB)`.

### Step 5: Clearing Fault & Stepwise Recovery
1. Click **CLEAR ALL FAULTS**.
2. Observe telemetry returning toward baseline nominal values.
3. Note that the state machine does not instantly jump to `NORMAL`; it de-escalates step-by-step (`CRITICAL` $\rightarrow$ `WARNING` $\rightarrow$ `CAUTION` $\rightarrow$ `WATCH` $\rightarrow$ `NORMAL`) over consecutive nominal frames via hysteresis ring buffers.
