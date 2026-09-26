# Installation, Authentication & Deployment — Aero Engine Digital Twin

**Team Hackonauts09 · Software-only demonstration**

[Live public demo](https://aero-engine-digital-twin.onrender.com) · [README](../README.md) · [Dataset provenance and limitations](DATASETS_AND_LIMITATIONS.md)

This guide describes the current three-role application. **There are no published production passwords.** Engineer and Operator credentials are supplied privately through environment variables; public visitors can instead use Cloudflare Turnstile to enter the read-only Demo.

## 1. Prerequisites

- **Recommended:** Docker for a setup matching the Python 3.11 production container. The first build downloads CPU-only PyTorch and other dependencies and may take several minutes.
- **Alternative:** Python 3.11, a virtual environment, and the packages in `requirements.txt`.
- A modern browser. FastAPI serves the existing HTML, CSS and JavaScript frontend; a Node.js frontend build is not required for the documented workflow.

The dashboard's telemetry scheduler **targets 10 Hz**, but actual throughput depends on host CPU and memory. Use the measured scheduler rate displayed in the application rather than assuming that every deployment sustains 10 Hz.

## 2. Clone and run locally with Docker

~~~bash
git clone https://github.com/singhdivyank09-coder/aero-engine-digital-twin.git
cd aero-engine-digital-twin
~~~

Create `.env.local` in the repository root. This filename is excluded by the existing `.gitignore`. Replace the example placeholders with **your own** strong, different local credentials:

~~~dotenv
ENVIRONMENT=development
JWT_SECRET_KEY=replace-with-your-own-long-random-local-secret
DEMO_ENGINEER_USERNAME=engineer
DEMO_ENGINEER_PASSWORD=choose-a-strong-local-engineer-password
DEMO_OPERATOR_USERNAME=operator
DEMO_OPERATOR_PASSWORD=choose-a-different-strong-local-operator-password
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
~~~

The values above are placeholders, **not working public accounts**. Never copy actual passwords or private keys into committed files.

~~~bash
docker build -t aero-engine-digital-twin .
docker run --rm --name aero-engine-digital-twin \
  -p 8000:8000 --env-file .env.local aero-engine-digital-twin
~~~

For Windows PowerShell, run the same `docker run` arguments **on one line**, without the Bash line-continuation backslashes.

Open **http://localhost:8000** and check **http://localhost:8000/api/health**. A healthy response contains `"status": "ok"`.

### Local Demo login and CAPTCHA

With `ENVIRONMENT=development` and no Turnstile secret configured, the backend supports a **development-only test-token flow**. It is not equivalent to Cloudflare verification and must not be used to operate a public deployment. To exercise genuine CAPTCHA verification, configure a Turnstile widget whose allowed hostname matches the site where you are testing, plus its site and secret keys.

## 3. Alternative: run in a Python virtual environment

~~~bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
~~~

Activate the virtual environment before installing packages and set the environment variables from Section 2 in your shell before starting Uvicorn. The backend does **not** automatically load `.env.local`; `docker run --env-file` handles that only in the Docker workflow.

If installing PyTorch manually, prefer the CPU build for machines without a supported GPU. The production [Dockerfile](../Dockerfile) already installs CPU-only PyTorch.

## 4. Authentication and permissions

| Role | Sign-in method | Permissions |
| --- | --- | --- |
| **Engineer** | Configured username and private password | Shared-session monitoring, live simulated fault controls, permitted scenario/dataset changes, mission controls and authorized audit access. |
| **Operator** | Configured username and private password | Read-only live telemetry, analytics, 2D twin, GCS/DFCS advisory views and available mission replay. |
| **Public Demo** | Server-verified Cloudflare Turnstile, no password | Read-only shared monitoring, available replay and the independent Public Fault Playground. Restricted audit/control endpoints are unavailable. |

Engineer-only restrictions are enforced on the backend, not merely hidden in the interface. **Never share an Engineer password to give public users access to simulated faults.** Visitors can explore the six independent scenarios in the Public Fault Playground without altering the live shared session.

## 5. Deploy on Render Free

The checked-in [render.yaml](../render.yaml) configures one Docker web service using `plan: free`, with **no persistent disk**. Connect the repository's `main` branch to a Render Blueprint and supply the private values when Render asks for them.

| Variable | Production setting |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `JWT_SECRET_KEY` | Strong private signing secret; generated by the checked-in Blueprint. |
| `DEMO_ENGINEER_USERNAME` / `DEMO_ENGINEER_PASSWORD` | Authorized Engineer username and strong private password. |
| `DEMO_OPERATOR_USERNAME` / `DEMO_OPERATOR_PASSWORD` | Authorized Operator username and a different strong private password. |
| `TURNSTILE_SITE_KEY` | Public Cloudflare Turnstile widget key. |
| `TURNSTILE_SECRET_KEY` | **Private** Cloudflare verification secret; configure in Render, never in the frontend or Git. |
| `ALLOWED_ORIGINS` | Exact public HTTPS origin, e.g. `https://aero-engine-digital-twin.onrender.com`. |
| `DB_PATH` | Ephemeral SQLite file path, set in the Blueprint. |

The backend **refuses production startup** if the JWT secret or required Engineer/Operator passwords are missing, and it rejects the old development password defaults. Turnstile's production verification checks successful validation, the configured hostname and the `demo_login` action.

If Render assigns a different hostname, update both `ALLOWED_ORIGINS` and the allowed hostname in your Cloudflare Turnstile widget. Keep service credentials in Render environment settings, not in the repository.

**Render Free caveats:** the service can sleep during inactivity, and SQLite data can disappear on sleep, restart or redeployment. The application retains at most five recent missions during the running server session, with a default one-hour recording rollover. Download reports you want to preserve. All visitors observe the same live TwinSession; the browser-only Public Fault Playground is independent.

## 6. Verify the installation

~~~bash
curl http://localhost:8000/api/health
python -m pip install pytest httpx
python -m pytest tests/
~~~

The health endpoint only confirms that FastAPI is responding; it does not prove that every UI tab works or that the service sustains 10 Hz. For browser verification, review `scratch/verify_demo_deployment.py` and the test guidance in [TESTING.md](TESTING.md). Test Engineer, Operator and Demo permissions separately, confirm all tabs and logout work, and check measured telemetry rate under realistic load.

## 7. Security and distribution

- Do not commit local `.env.local`, production secrets, JWTs, SQLite recordings or downloaded reports containing private information.
- `.gitignore` does not erase previously committed material from Git history. Audit history and rotate any credential that was ever exposed.
- This repository contains public/analogous and synthetic demonstration material. Review third-party dataset and asset terms before redistribution.
- This software is **not flight-certified**, is not connected to an operational aircraft and must not be used for flight or engine-control decisions. GCS/DFCS output is demonstrative advisory information only.
