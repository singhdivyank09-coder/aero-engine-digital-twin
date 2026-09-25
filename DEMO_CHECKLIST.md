# DRDO iDEX MALE UAV Aero-Piston Engine Digital Twin — Demo Checklist

**SIH 26054 Live Demonstration Procedure**

---

## 1. Pre-Demo Preparation

- [ ] Confirm Python 3.10+ environment is active.
- [ ] Launch backend server: `python backend/main.py`.
- [ ] Open web browser to `http://127.0.0.1:8000`.
- [ ] Authenticate using credentials:
  - **Engineer:** `engineer` / `engineer123`
  - **Operator:** `operator` / `operator123`
- [ ] Verify `SYNCHRONIZED (10Hz)` connection status badge in header.

---

## 2. Step-by-Step Live Demo Execution

### Step 1: Nominal Cruise Baseline
- [ ] Ensure active mission scenario is set to **Cruise / Endurance**.
- [ ] Allow system to stabilize for 10-15 seconds.
- [ ] Observe HUD metrics:
  - System State: `NORMAL`
  - Health Index: ~98.0%
  - Anomaly Score: < 0.020
  - CHT1: ~120.0 °C
  - Oil Pressure: ~4.2 bar
  - Prototype RUL: ~1270 cycles

### Step 2: Scenario Physics & Environment Adaptation
- [ ] Change Scenario to **High Altitude** (4500 m).
- [ ] Observe environmental parameter changes: Altitude `4500 m`, Ambient Temp `-14.2 °C`, MAP `1.15 bar`.
- [ ] Change Scenario to **Hot Weather** (42 °C ambient).
- [ ] Return Scenario to **Cruise / Endurance**.
- [ ] Confirm single active `TwinSession` ID (`TWIN_SESSION_SIH26054`) is maintained throughout.

### Step 3: Cylinder 1 Thermal Fault Injection
- [ ] Navigate to **Fault Injection & Analytics** tab.
- [ ] Configure Fault Parameters:
  - **Scenario:** Cylinder 1 Thermal Degradation
  - **Component:** Cylinder Head 1 (CYLINDER_1)
  - **Profile:** Gradual Linear Ramp
  - **Progression Rate:** Moderate / 60s
  - **Intensity:** 1.0 (100%)
- [ ] Click **Start Fault Injection**.

### Step 4: Mandatory Predictive Early Warning Timeline Observation
- [ ] **Observe State Sequence:**
  - `NORMAL` (CHT1 ~120.0 °C) — Nominal Monitoring
  - `WATCH` (CHT1 ~121.1 °C) — Derivative & residual evidence developing
  - `CAUTION` (CHT1 ~123.8 °C) — Conservative mission advisory
  - **`WARNING` / `PREDICTED THERMAL RISK`** triggered at CHT1 ~124.3 °C.
- [ ] **Verify Core Predictive Requirement:**
  - Confirm `WARNING` state & `PREDICTED THERMAL RISK` trigger **WHILE CHT1 IS STILL INSIDE THE REFERENCE ENVELOPE** (< 135.0 °C reference, strictly safe < 145.0 °C fault limit).
- [ ] **Inspect Predictive Early Warning Panel:**
  - Observe **GRU 10s / 30s / 60s Forecast Curves** (predicting exceedance before it occurs).
  - Observe **Estimated Time-to-Risk:** `~27 seconds`.
  - Observe **Degradation Score:** `0.70 - 0.90`.
- [ ] **Continue to Active Fault / Critical:**
  - Allow CHT1 to reach > 145.0 °C.
  - Observe transition to `CRITICAL` state & `ACTIVE THERMAL FAULT` confirmation.

### Step 5: Natural Hysteresis Recovery
- [ ] Click **Clear All Faults**.
- [ ] Observe thermal trajectory improving, GRU forecast dropping, and physics residuals falling.
- [ ] Observe stepwise hysteresis state recovery: `CRITICAL` → `WARNING` → `CAUTION` → `WATCH` → `NORMAL`.
- [ ] Confirm no stale critical warnings remain after full recovery.

### Step 6: Auxiliary View Verification
- [ ] Open **2D Digital Twin Schematic** — Verify spatial cylinder thermal indicators and component isolation.
- [ ] Open **Mission Replay & Reports** — Run historical 300-frame replay, verify scrubber and cycle-based RUL summary.
- [ ] Open **GCS & DFCS Demonstrator** — Verify decision-support advisory displays and pilot warnings.
- [ ] Open **AI Models & Dataset Mapping** — Verify model artifact statuses (`TRAINED`), dataset provenance, and surrogate physics label.
- [ ] Open **System Metrics & Runtime** — Verify high-resolution execution rates, latency metrics (Physics, AE, GRU, Predictive Engine), and 100% data integrity.
