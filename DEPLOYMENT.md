# Production Deployment Guide — SIH 26054 Aero Engine Digital Twin

## 1. System Requirements & Overview

- **Operating System**: Linux (Ubuntu 20.04+), macOS, or Windows 10/11
- **Runtime**: Docker Desktop / Engine 20.10+ & Docker Compose v2+ **OR** Python 3.10+
- **Host RAM**: Minimum 4 GB (8 GB recommended)
- **Disk Storage**: ~1.2 GB for container image

---

## 2. Option A: Single-Command Docker Deployment (Recommended)

### Build and Launch Application
Run from project root:
```bash
docker compose up --build -d
```

### Access Application
- **Ground Control Station HMI**: `http://localhost:8000`
- **REST API Health Check**: `http://localhost:8000/api/health`
- **Real-Time WebSocket Stream**: `ws://localhost:8000/ws/telemetry`

### Execute Automated Test Suite Inside Container
```bash
docker exec -it aero_engine_digital_twin pytest tests/ -v
```

### Container Lifecycle Commands
- **Check Status**: `docker compose ps`
- **View Live Stream Logs**: `docker compose logs -f`
- **Stop Application**: `docker compose down`

---

## 3. Option B: Direct Python Execution (Non-Docker Method)

If running without Docker:

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch Digital Twin Backend
```bash
python backend/main.py
```
Or using Uvicorn directly:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
```

### 3. Run Test Suite
```bash
python -m pytest tests/ -v
```

---

## 4. Database & Memory Architecture Safeguards

1. **Memory Buffers**:
   - Live Telemetry RAM Buffer: `deque(maxlen=1200)` (120 seconds at 10 Hz).
   - GRU Input Window: `sample_window` (30 seconds at 2 Hz / 60 frames).
2. **Database Footprint**:
   - Initial database size: **~0.04 MB** (40 KB).
   - Downsampled 0.2 Hz recording: **< 1.0 MB** growth after 15+ minutes of continuous run.
