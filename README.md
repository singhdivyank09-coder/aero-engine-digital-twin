# Aero Engine Digital Twin

**A software-only aero-piston engine health-monitoring demonstrator by Team Hackonauts09**

[**Launch the live demo**](https://aero-engine-digital-twin.onrender.com) · [Source code](https://github.com/singhdivyank09-coder/aero-engine-digital-twin) · [Dataset provenance and limitations](docs/DATASETS_AND_LIMITATIONS.md)

> **Research and demonstration only.** This prototype uses simulated engine telemetry and analogous public datasets. It is not connected to an aircraft or operational UAV, has not been flight-certified, and must not be used to control an engine or make real-world flight decisions. GCS/DFCS outputs are advisory demonstrations for human review.

## Overview

The Hackonauts09 Aero Engine Digital Twin brings together simulated four-cylinder turbocharged aero-piston telemetry, physics-reference residuals, anomaly detection, fault classification, short-horizon forecasting, experimental remaining-useful-life (RUL) estimates, and a browser-based ground-control-style dashboard.

A single authoritative **shared TwinSession** supplies the live dashboard to all signed-in viewers. Engineers can change simulated faults; Operators and public Demo visitors can observe the resulting telemetry and diagnostics. For independent experimentation, the **Public Fault Playground** runs separate synthetic scenario traces entirely in each visitor's browser, without changing the live session.

**Live service:** https://aero-engine-digital-twin.onrender.com

The hosted service uses Render Free. It may take time to wake after inactivity, and its live recordings are temporary.

## Explore the demo

| Access | How to enter | What you can do |
| --- | --- | --- |
| **Public Demo** | Complete Cloudflare Turnstile and select **Explore Public Demo** | Watch the shared session, inspect telemetry and the 2D twin, view available recordings, and explore the independent Public Fault Playground. |
| **Operator** | Sign in with an individually configured Operator account | Monitor telemetry, analytics, GCS/DFCS advisories, and mission replay. Live fault controls remain read-only. |
| **Engineer** | Sign in with an authorized Engineer account | Use monitoring features plus live simulated fault injection, scenario and dataset controls, mission controls, and authorized audit views. |

**Only Engineers may start, pause, resume, or clear faults in the shared live simulation.** All connected viewers observe the same live state. Do not share Engineer credentials with public visitors.

### Public Fault Playground

Visitors can select six independent **synthetic demonstration traces**: cylinder thermal degradation, oil-pressure loss, increasing vibration, electrical sensor drift, intermittent combustion, and fuel-injector abnormality. Play, pause, reset, and timeline-scrubbing controls run locally in the browser. These illustrative traces are **not new model inference**, do not modify TwinSession, and do not write mission recordings.

### Live monitoring

The dashboard includes telemetry readouts and charts, a 2D engine schematic, physics residuals, predictive-health and fault diagnostics, short-horizon projections, mission replay, a GCS/DFCS advisory demonstrator, and runtime metrics.

The telemetry scheduler **targets 10 Hz**, but the actual rate depends on server load. The interface reports measured rate and a **DEGRADED** status when the host cannot sustain its target. A configured rate is not a performance guarantee.

## Architecture

~~~mermaid
flowchart TD
    UI["Browser: GCS dashboard"] <-->|"JWT-authenticated REST and WebSocket"| API["FastAPI · single-worker server"]
    API --> CORE["Shared authoritative TwinSession"]
    CORE --> TEL["Simulated aero-piston telemetry"]
    CORE --> PHYS["Physics-reference residuals + CUSUM"]
    CORE --> AI["Cached anomaly, classification and prognostic inference"]
    PHYS --> HEALTH["Five-state predictive-health engine"]
    AI --> HEALTH
    CORE --> DB["SQLite: compact mission snapshots + events"]
    CORE --> WS["Bounded per-client WebSocket queues"]
    WS --> UI
    UI --> PLAY["Isolated client-side Public Fault Playground"]
    PLAY --> TRACES["Six bundled synthetic scenario traces"]
~~~

### Processing and model components

| Component | Demonstration role | Nominal scheduling |
| --- | --- | --- |
| Telemetry simulator | RPM, manifold pressure, CHT/EGT, oil, fuel, vibration and voltage | 10 Hz **target** |
| Physics-reference/PINN module and CUSUM | Expected-state residuals and change detection | Each processed telemetry tick |
| PyTorch autoencoder | Multichannel anomaly score | Every 5 processed ticks |
| XGBoost | Simulated fault-signature classification | Every 5 processed ticks |
| PyTorch GRU | Experimental +10 s, +30 s and +60 s trajectories | Every 10 processed ticks |
| PyTorch LSTM | Experimental RUL expressed in analogue sequence cycles | Every 50 processed ticks |
| Predictive state machine | NORMAL → WATCH → CAUTION → WARNING → CRITICAL, with persistence and stepwise recovery | Updated with processed evidence |

Cached inference carries source-frame and age metadata. Nominal inference frequencies assume the scheduler meets its target; under overload, actual inference frequency may be lower.

## Simulated faults and mission replay

Engineer-controlled live scenarios include thermal degradation, oil-pressure degradation, vibration increase, sensor drift, intermittent combustion and fuel-injector disturbance. Fault injection perturbs simulator inputs; diagnostics and state transitions are evaluated separately.

Mission replay stores downsampled SQLite snapshots (nominally **0.2 Hz**, plus relevant state transitions) and event records. The application retains **up to five recent missions**, automatically rolling recordings over after a configured default of **60 minutes**.

**Render Free data is ephemeral.** Recordings can disappear when the free service becomes inactive, restarts or redeploys. Download reports you wish to keep. The public playground's bundled scenarios are independent of this temporary database.

## Run locally

**Prerequisites:** Docker, or Python 3.11 with the packages in `requirements.txt`.

~~~bash
git clone https://github.com/singhdivyank09-coder/aero-engine-digital-twin.git
cd aero-engine-digital-twin
docker build -t aero-engine-digital-twin .
~~~

Create a local `.env.local` file **outside Git tracking**. Choose your own distinct, strong local passwords; the values below are placeholders, not actual credentials:

~~~dotenv
ENVIRONMENT=development
JWT_SECRET_KEY=replace-with-a-long-random-local-value
DEMO_ENGINEER_USERNAME=engineer
DEMO_ENGINEER_PASSWORD=choose-a-strong-local-engineer-password
DEMO_OPERATOR_USERNAME=operator
DEMO_OPERATOR_PASSWORD=choose-a-different-strong-local-operator-password
ALLOWED_ORIGINS=http://localhost:8000
~~~

~~~bash
docker run --rm -p 8000:8000 --env-file .env.local aero-engine-digital-twin
~~~

Open **http://localhost:8000**. You can also run the backend in a configured Python environment with:

~~~bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
~~~

For the Python command, export your local environment variables in your shell first; the app does not automatically read an `.env.local` file. For real Turnstile verification, configure a site key and secret key for the hostname you use.

### Production configuration

The committed [Render Blueprint](render.yaml) specifies a **Free Docker web service with no persistent disk**. It generates `JWT_SECRET_KEY` and requests Engineer/Operator passwords and Turnstile keys as private deployment variables (`sync: false`). Production requires configured credentials and a valid signing secret.

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | Set to `production` on the public service. |
| `JWT_SECRET_KEY` | Private JWT signing secret; Render Blueprint generates one. |
| `DEMO_ENGINEER_USERNAME` / `DEMO_ENGINEER_PASSWORD` | Provision the Engineer account. |
| `DEMO_OPERATOR_USERNAME` / `DEMO_OPERATOR_PASSWORD` | Provision the Operator account. |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | Public widget key and private server-side CAPTCHA verification key. |
| `ALLOWED_ORIGINS` | Exact permitted website origin, including HTTPS. |
| `DB_PATH` | SQLite file path; ephemeral on Render Free. |
| `MAX_MISSION_DURATION_SECONDS` | Optional mission rollover limit (default: 3600). |
| `MAX_DEMO_WS_CONNECTIONS` | Optional concurrent Demo WebSocket limit (default: 20). |

**Never commit passwords, JWT secrets, Turnstile secret keys, local databases or production environment files.** Public Demo users do not need an Engineer or Operator password.

## Tests

The repository includes unit, integration, authorization, mission-retention, performance/scheduler and browser-verification tests.

~~~bash
python -m pip install -r requirements.txt
python -m pip install pytest httpx
python -m pytest tests/
~~~

Useful targeted suites include `tests/test_rbac_3roles.py`, `tests/test_captcha_turnstile.py`, `tests/test_mission_retention_isolation.py`, `tests/test_password_salting.py` and `tests/test_performance_and_playground.py`. Browser checks are in `scratch/verify_demo_deployment.py` and related scripts. A passing unit test or successful cloud build alone does **not** establish sustained 10 Hz performance or validate every browser interaction; measure those separately.

## Repository guide

~~~text
backend/                  FastAPI, authentication, shared TwinSession, simulator and replay
ml_service/               Anomaly, CUSUM, fault, forecasting and physics-reference modules
models/                   Trained demonstration model artifacts and scalers
frontend/                 GCS dashboard, styling and client-side playground traces
datasets/                 Public/analogous and synthetic dataset inputs
data/                     Local example and temporary mission data
tests/                    Unit, integration and security tests
scratch/                  Development and browser-verification scripts
docs/                     Additional technical and provenance notes
Dockerfile                Single-worker container definition
render.yaml               Render Free Blueprint
~~~

## Dataset provenance and limitations

- **Primary live feed:** simulated aero-piston telemetry, not real aircraft sensor measurements.
- **NASA C-MAPSS FD001:** an *analogous turbofan degradation benchmark* for experimental LSTM prognostics. Displayed RUL is in **analogue sequence cycles**, not validated aero-piston service life or remaining flight time.
- **Other dataset references:** ALFA, RflyMAD and UAV-FD integrations are represented in the project's dataset and mapping modules; their use is distinct from the primary simulated live telemetry.
- **Safety:** no physical engine or flight-control integration; the GCS/DFCS interface is a software-only, advisory demonstrator, not certified flight software.
- **Affiliation:** independently developed by **Team Hackonauts09**; no official defense-agency affiliation, endorsement or operational deployment is claimed.

See [dataset provenance and limitations](docs/DATASETS_AND_LIMITATIONS.md) for background. Verify applicable third-party dataset and asset redistribution terms before reusing material from this repository.

## Copyright and reuse

**© 2026 Team Hackonauts09.** No open-source `LICENSE` file is currently provided for the project's original code. Public visibility does not itself grant a general permission to redistribute or modify that code. Third-party software, models and datasets remain subject to their respective terms.

**Project:** Team Hackonauts09 · [Source repository](https://github.com/singhdivyank09-coder/aero-engine-digital-twin) · [Live demonstration](https://aero-engine-digital-twin.onrender.com)
