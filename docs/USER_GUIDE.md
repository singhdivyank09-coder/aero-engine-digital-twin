# User Guide & Demo Walkthrough — Aero Engine Digital Twin

**Team Hackonauts09 · Simulated engine health-monitoring demonstration**

[Open live demo](https://aero-engine-digital-twin.onrender.com) · [README](../README.md) · [Installation and account setup](INSTALLATION.md)

> This software is not connected to a physical engine or operational UAV. All fault injection affects only simulated telemetry; GCS/DFCS advisories are demonstrative and not certified flight guidance.

## 1. Choose an access role

| Role | Sign-in | Available experience |
| --- | --- | --- |
| **Public Demo** | Complete the Cloudflare Turnstile challenge; no password required. | Read-only shared dashboard, 2D twin, selected analytics, available mission replay and an independent Public Fault Playground. |
| **Operator** | Use the private Operator username and password provided by the project administrator. | Shared live monitoring, analytics, GCS/DFCS advisory views and replay. |
| **Engineer** | Use the private Engineer username and password provided by the project administrator. | Monitoring plus authorized live simulated fault controls, scenario/dataset changes, mission controls and audit logs. |

**No production passwords are published in this repository.** Only Engineers can change the **shared live simulation**. Other visitors can experiment with faults in their **own browser** using the Public Fault Playground.

## 2. Understand the dashboard

The header shows the current health state, health index, anomaly score, experimental RUL and the **measured scheduler rate**. The telemetry pipeline targets 10 Hz, but a host under load may show `DEGRADED` with a lower measured rate.

- **Operator Dashboard:** telemetry, trends, predictive early warnings and the shared simulated-fault status.
- **2D Digital Twin Schematic:** component-level visualization of the current simulated state.
- **Fault Injection & Analytics:** live control buttons for Engineers and an Engineer-only permission notice for other roles; viewers can inspect available diagnostics.
- **Simulated Fault Playground:** separate browser-side synthetic scenario playback that does not change the shared engine.
- **Mission Replay & Reports:** recent temporary recordings and report export.
- **AI Models & Dataset Mapping:** model descriptions and the distinction between simulated live data and analogous prognostics datasets.
- **GCS & DFCS Demonstrator:** advisory-only software checklists and status indicators.
- **System Metrics & Assumptions:** measured application and data-integrity metrics.
- **Security Audit Logs:** restricted to authorized Engineer accounts.

The **SHARED DEMONSTRATION SESSION** label means an Engineer's live fault can appear for all connected viewers. It does not make a Demo visitor an Engineer.

## 3. Public visitor: try a fault without Engineer access

1. Open the live website, complete Turnstile and choose **Explore Public Demo**.
2. Select **Simulated Fault Playground**.
3. Choose one of six synthetic scenarios: thermal degradation, oil-pressure loss, increased vibration, sensor drift, intermittent combustion or injector disturbance.
4. Use **Play**, **Pause**, **Reset** or the timeline slider to explore the illustrative recorded-style trace.
5. Read the **RECORDED DEMONSTRATION RESULTS** label. Trace scores are synthetic illustrations, not freshly executed model inference. Unavailable metrics should be marked accordingly.

Playground actions stay in your browser. They never inject a fault into TwinSession or affect other viewers.

## 4. Engineer: guided shared-session demonstration

Use only your **configured private Engineer credentials**. If other people are watching, tell them that the following actions change the shared simulation.

### Step 1 — Establish a nominal starting point

Clear any previously injected simulated fault if one is active. Allow the simulator and prediction windows time to settle; do not assume the session is nominal immediately after another visitor's demonstration. Check the measured scheduler rate and current system state.

### Step 2 — Inject a simulated fault

Open **Fault Injection & Analytics**, select a compatible scenario and component, choose a profile such as `GRADUAL` and start the simulated injection. For example, **Cylinder 1 Thermal Degradation** (`CYLINDER_THERMAL`) can illustrate rising CHT and subsequent changes in diagnostic evidence.

Only authorized Engineers can start, pause, resume or clear a **live** injection. Operator and Demo requests to restricted backend endpoints receive HTTP 403.

### Step 3 — Observe diagnostics and recovery

Watch telemetry, the physics residual, anomaly and classifier outputs, GRU projections, time-to-risk and the five-state health indicator. The precise timing and state transitions depend on the selected profile, model warm-up and achieved processing rate; they are not guaranteed to follow a fixed countdown.

Use **Clear All Faults** when finished, then observe the simulator returning toward its baseline and the health-state machine recovering step by step where the evidence allows.

### Step 4 — Inspect mission replay

Open **Mission Replay & Reports** to inspect recent snapshots and events. The recorder retains at most five missions and uses a one-hour default rollover. Render Free storage is temporary: export reports you want to keep before inactivity, restart or redeployment resets the server.

## 5. Operator: monitor without live control

Log in with the Operator credentials configured by the administrator. Observe the shared dashboard, current simulated faults, diagnostic indicators and advisory views. Use mission replay to examine available prior segments. The Public Fault Playground offers an independent way to explore scenarios without requiring Engineer permissions.

## 6. Logout and connection status

Use the power button in the top-right header to log out. If the Free host has been inactive, the first request may take longer while the service starts. A connected backend does not imply that a login attempt succeeded; credential errors and CAPTCHA status are separate.

This is **research and demonstration software**. RUL cycles come from an experimental NASA C-MAPSS turbofan analogue, not a certified aero-piston maintenance estimate. See [Datasets, Provenance & Limitations](DATASETS_AND_LIMITATIONS.md).
