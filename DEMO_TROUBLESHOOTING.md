# DRDO iDEX MALE UAV Aero-Piston Engine Digital Twin — Demo Troubleshooting Guide

**Quick Recovery Instructions for SIH 26054 Demonstrator**

---

## 1. Backend Server Not Starting

### Symptoms
- Command `python backend/main.py` fails with `ModuleNotFoundError` or `[WinError 10048] address already in use`.

### Quick Recovery
1. **Check Python Environment:** Ensure Anaconda Python or virtual environment with PyTorch & FastAPI installed is active. Use full path if necessary:
   ```bash
   C:\Users\divya\anaconda3\python.exe backend/main.py
   ```
2. **Kill Existing Server Processes on Port 8000:**
   - **Windows PowerShell:**
     ```powershell
     Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
     ```
   - **Windows Command Prompt:**
     ```cmd
     taskkill /F /IM python.exe
     ```
3. **Restart Backend:**
   ```bash
   python backend/main.py
   ```

---

## 2. Frontend Not Connecting / Site Cannot Be Reached

### Symptoms
- Browser displays `ERR_CONNECTION_REFUSED` or "Site cannot be reached" at `http://127.0.0.1:8000`.

### Quick Recovery
1. Verify backend server is running and displaying `Uvicorn running on http://0.0.0.0:8000`.
2. Test health endpoint in browser: `http://127.0.0.1:8000/api/health`.
3. Try binding host `http://localhost:8000` or `http://127.0.0.1:8000`.
4. Hard refresh browser cache: **Ctrl + F5**.

---

## 3. WebSocket Disconnected (`DISCONNECTED` Badge)

### Symptoms
- Header status badge shows `DISCONNECTED` in red; live charts stop updating.

### Quick Recovery
1. **Auto-Reconnect:** The frontend will attempt auto-reconnect every 2 seconds.
2. **Hard Refresh:** Press **Ctrl + F5** to reload the WebSocket client instance.
3. **Verify Backend Status:** Check backend terminal for WebSocket exception logs. If backend crashed, restart `python backend/main.py`.

---

## 4. PyTorch GRU Forecaster Artifact Unavailable

### Symptoms
- Header status shows `Statistical Fallback` instead of `GRU Short-Horizon Model`.

### Quick Recovery
1. **Verify Artifact Existence:** Check `models/forecast/gru_forecaster.pt` exists (~190 KB).
2. **Check PyTorch Import:** Verify `torch` is installed in current Python environment (`python -c "import torch; print(torch.__version__)"`).
3. **Re-initialize Model:** Restart backend server; `gru_forecast_service` automatically loads `.pt` file upon startup.

---

## 5. Authentication Expired / HTTP 401 Unauthorized

### Symptoms
- API calls return HTTP 401 Unauthorized; red error text displayed on login modal.

### Quick Recovery
1. Click **Power Off / Logout** button in top-right header.
2. Clear browser LocalStorage: `localStorage.clear()` in Browser Developer Console (F12).
3. Log in again with default credentials:
   - **Engineer:** `engineer` / `engineer123`
   - **Operator:** `operator` / `operator123`

---

## 6. Real-Time Telemetry Charts Empty

### Symptoms
- Live telemetry line chart or residual chart displays no data points.

### Quick Recovery
1. Switch navigation tabs (e.g. from Operator Dashboard to 2D Digital Twin and back). Chart instances auto-resize on tab focus.
2. Check browser console for Chart.js rendering warnings.
3. Verify WebSocket status shows `SYNCHRONIZED (10Hz)`.

---

## 7. Fault Injection Not Active / Buttons Disabled

### Symptoms
- Clicking "Start Fault Injection" displays HTTP 403 Forbidden or has no physical effect.

### Quick Recovery
1. **Check Role:** Fault injection requires **Engineer** role (`engineer`). Ensure logged-in user badge displays `PROTOTYPE PROPULSION ENGINEER`.
2. **Reset Fault Controller:** Click **Clear All Faults**, wait 3 seconds, then re-select scenario and click **Start Fault Injection**.

---

## 8. Scenario Not Changing Physical Outputs

### Symptoms
- Switching to `HIGH_ALTITUDE` or `HOT_WEATHER` does not update altitude or temperature gauges.

### Quick Recovery
1. Ensure WebSocket connection is `SYNCHRONIZED`.
2. Verify `scenario_parameters` object is present in backend frame snapshot (`/api/telemetry/latest`).
3. Refresh page (**Ctrl + F5**) to re-sync scenario dropdown controls.
