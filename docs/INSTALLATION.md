# Installation & Startup Guide — Aero Engine Digital Twin

## 1. Prerequisites

Before installing, ensure your environment meets the following requirements:
- **Operating System**: Windows 10/11, macOS, or Linux.
- **Python**: Version **3.10** or higher (Python 3.10 - 3.12 recommended).
- **Node.js** (Optional): Version 18+ if using Vite frontend dev server (Vanilla HTML/JS is served directly by FastAPI backend by default).

---

## 2. Environment Setup

### 2.1 Clone Repository
```bash
git clone https://github.com/singhdivyank09-coder/aero-engine-digital-twin.git
cd aero-engine-digital-twin
```

### 2.2 Create Virtual Environment
```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 2.3 Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Running the Application

### 3.1 Start the FastAPI Backend Server
Run the backend server using `uvicorn`:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 3.2 Access the Ground Control Station (GCS) UI
Open your web browser and navigate to:
```
http://127.0.0.1:8000
```

---

## 4. Default Demo Authentication Credentials

The Ground Control Station interface includes role-based access control. You can log in using either pre-configured demo user:

| Role | Username | Password | Access Privileges |
| :--- | :--- | :--- | :--- |
| **Operator** | `operator` | `operator123` | Operational GCS Dashboard, 2D Twin View, Telemetry Readouts |
| **Engineer** | `engineer` | `engineer123` | Full Access: Fault Injection Controls, Analytics, PyTorch GRU Projections, DFCS Override Controls |

---

## 5. Environment & Configuration Verification

To verify backend server API health programmatically:

```bash
# System status check
curl http://127.0.0.1:8000/api/system/metrics
```

Expected JSON response includes `"data_integrity_status": "MEASURED"` and `"session_uptime_seconds"`.
