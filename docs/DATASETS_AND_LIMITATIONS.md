# Datasets, Provenance & Limitations — Aero Engine Digital Twin

**Team Hackonauts09 · Software-only research and demonstration prototype**

[README](../README.md) · [Installation](INSTALLATION.md) · [Live demonstration](https://aero-engine-digital-twin.onrender.com)

## 1. What the data represents

The application's **primary live engine feed is simulated aero-piston telemetry**, not measurements from an operational UAV. Separate public or analogous datasets support demonstration model development, dataset-selection workflows and experimental prognostics. The browser-only Public Fault Playground uses bundled **synthetic example traces** and does not run new server-side model inference.

The scheduler targets **10 Hz** for live processing; actual rate and nominal model-update frequencies depend on available compute. The live UI reports measured scheduler performance and can display `DEGRADED` under load.

## 2. Dataset provenance and intended use

| Source or asset | Repository location / reference | Demonstration use | Important boundary |
| --- | --- | --- | --- |
| **Simulated aero-piston telemetry** | `backend/telemetry_simulator.py` | Primary shared live engine stream: RPM, manifold pressure, CHT 1–4, EGT 1–4, oil pressure/temperature, fuel flow, vibration and bus voltage. | Generated from an illustrative four-cylinder turbocharged aero-piston reference model; not real aircraft telemetry or validated engine-test measurements. |
| **NASA C-MAPSS FD001** | `datasets/raw/train_FD001.txt`; `datasets/processed/cmapss_fd001_canonical.csv` | Turbofan run-to-failure benchmark and experimental LSTM remaining-useful-life (RUL) analogue. | Turbofan sequence cycles are **not** certified remaining life, flight hours or maintenance intervals for aero-piston engines. |
| **ALFA sample** | `datasets/raw/alfa_sample_flight.csv` | Example UAV dataset and mapping/loader support. | A sample flight file is not a validated replacement for primary aero-piston engine measurements. |
| **RflyMAD and UAV-FD** | References in `datasets/mapping_doc.json` and loader modules | Dataset-mapping and optional/replay workflows. | Do not assume these projects' complete raw datasets are bundled or that their features directly measure piston-engine health. |
| **Synthetic forecast-training trajectories** | `datasets/simulated/forecast_training/simulated_aero_piston_trajectories.csv` | Artificial aero-piston trajectories used for forecasting demonstration/model-development workflows. | Synthetic generation and model behavior do not establish real-engine predictive accuracy. |
| **Public Fault Playground traces** | `frontend/playground_traces.js` | Six browser-local scenarios with play/pause/reset and timeline controls. | Illustrative synthetic traces, **not live AI predictions or recordings of an operational engine**; they cannot modify the shared TwinSession. |

The source-feature examples in `datasets/mapping_doc.json` are **mappings** for demonstration and comparison. A mapping such as a turbofan temperature channel, UAV yaw-rate measurement or actuator PWM value must not be interpreted as a directly interchangeable aero-piston engine sensor.

Third-party source names are given for provenance; **no blanket claim of redistribution rights is made**. Check the original dataset provider's terms, attribution conditions and permitted uses before republishing or using any dataset outside this demonstration.

## 3. Predictive analytics: interpretation and limitations

- **Physics-reference residuals / PINN-labeled module:** contrasts simulated measurements with reference expectations. Residuals are demonstrations of an analytics pipeline, not calibrated operational failure limits.
- **CUSUM and PyTorch autoencoder:** provide simulated change-detection and reconstruction-error evidence.
- **XGBoost:** classifies demonstration fault signatures. Its labels and confidence outputs have not been validated as real-aircraft diagnostic probabilities.
- **PyTorch GRU:** provides experimental +10 s, +30 s and +60 s projections from simulated/historical demonstration inputs. Forecasts are not guarantees of future physical measurements.
- **PyTorch LSTM RUL:** uses NASA C-MAPSS turbofan patterns as an **analogue**. Displayed RUL in sequence cycles is not a real aero-piston engine time-to-failure prediction.
- **Five-state health engine and time-to-risk:** demonstrate evidence fusion and threshold-crossing logic. States and advisories must not be treated as flight-certified operational warnings.

Some expensive models run at scheduled intervals rather than on every processed telemetry frame. Cached outputs carry frame/age information; their age and the measured rate matter when interpreting a live display.

## 4. Live simulation versus the Public Fault Playground

**Shared live session:** one authoritative backend TwinSession supplies the dashboard. An authorized Engineer may inject, pause, resume or clear simulated faults; Operators and CAPTCHA-verified Demo visitors observe changes without live mutation authority. Live mission snapshots and events are stored in temporary SQLite.

**Public Fault Playground:** each visitor plays independent browser-side synthetic scenario traces for cylinder thermal degradation, oil-pressure loss, increasing vibration, electrical sensor drift, intermittent combustion or injector disturbance. Playground selections **never mutate** the live simulator, audit trail, mission database or other viewers' sessions. Any illustrative score or classifier label in a playground trace must not be described as newly computed live inference. Metrics not represented in a trace should be shown as unavailable, not invented.

## 5. Storage, hosting and data retention

The default live recorder saves compact SQLite snapshots at a nominal **0.2 Hz** plus relevant state-transition events. It retains at most **five recent missions**, and a mission rolls over after a default **60 minutes**. Actual snapshot timing depends on the achieved scheduler rate.

The hosted Render Free instance has **no persistent disk**. Recordings, accounts provisioned into SQLite and other runtime state can reset after sleep, restart or redeployment; authorized accounts are provisioned again from the private deployment environment. Download any mission reports that need to survive these events. Bundled frontend playground traces remain part of the deployed code.

A configured 10 Hz target or successful unit test does **not** establish sustained throughput on Render Free. Consult the application's measured scheduler rate and runtime metrics; capacity can be lower with concurrent viewers or expensive inference.

## 6. Safety, affiliation and acceptable interpretation

> [!IMPORTANT]
> **Demonstration only.** The software is not connected to an operational UAV or a physical engine testbed; it has not been validated for real-world propulsion decisions or flight-certified under DO-178C / DO-254. Do not use it to control an aircraft, determine airworthiness or decide flight procedures. GCS/DFCS advisories are software demonstrations for human evaluation, not autonomous flight commands.

This is an independently developed **Team Hackonauts09** prototype. No official defense-agency employment, endorsement, operational deployment or certification is claimed.

## 7. Secrets, privacy and publication

This project is designed around public/analogous and synthetic demonstration data. **Do not add actual aircraft telemetry, institutional records, real credentials or private visitor information** to this repository.

Production Engineer and Operator passwords are configured privately through environment variables; public Demo access is guarded by server-verified Cloudflare Turnstile. There are **no public production passwords**. Example development credentials are not suitable for production, and published documentation must never imply that an old hardcoded password grants access to the hosted service.

`.gitignore` only prevents *new* tracking of matching paths; it does not hide already committed files or erase earlier Git history. Review the complete public repository and its history before sharing sensitive material. Rotate any secret that was previously committed or otherwise exposed.

The repository's original code has no open-source `LICENSE` file at the time of this documentation update. Third-party libraries, model artifacts, datasets and other assets remain subject to their own applicable terms.
