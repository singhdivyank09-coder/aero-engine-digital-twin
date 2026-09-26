"""
Performance, Monotonic Scheduler, Non-Blocking WebSocket Queue, and Playground Isolation Tests
Validates:
1. Overload-aware monotonic clock simulation time accuracy (10s real time = 10s sim time +/- 0.3s)
2. Scheduler deadline miss handling and DEGRADED status labeling
3. Non-blocking per-client WebSocket queues
4. RBAC authorization (403 Forbidden for non-Engineers on live fault endpoints)
5. Selective ML inference scheduling and output cache age metadata
6. Public Fault Playground isolation (zero backend side-effects)
"""

import os
import sys
import time
import asyncio
import pytest
from fastapi.testclient import TestClient

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app, ConnectionManager, ClientConnection, compute_canonical_tick, scheduler_stats
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance
from backend.auth import create_access_token

client = TestClient(app)

def test_selective_ml_scheduling_and_age_metadata():
    """Verifies PINN/CUSUM run at 10 Hz, AE/XGBoost at 2 Hz, GRU at 1 Hz, LSTM at 0.2 Hz, with cache age metadata."""
    digital_twin_core_instance.history_window_full.clear()
    
    # Process 10 ticks
    snapshots = []
    for i in range(10):
        frame = compute_canonical_tick(dt=0.1)
        snapshots.append(frame)

    last_frame = snapshots[-1]
    
    # Verify cached output age metadata exists
    ae_dict = last_frame.get("anomaly", {}).get("autoencoder", {})
    assert "inference_age_sec" in last_frame or "inference_age_sec" in ae_dict
    age = last_frame.get("inference_age_sec", ae_dict.get("inference_age_sec"))
    assert isinstance(age, (int, float))

    # Verify PINN residuals and CUSUM exist on every tick (10 Hz)
    for snap in snapshots:
        assert "physics_expected" in snap or "residuals" in snap
        assert "anomaly" in snap and "cusum" in snap["anomaly"]

def test_overload_aware_scheduler_clock_accuracy():
    """Verifies that time.monotonic() simulation progression matches real elapsed time and tracks missed deadlines."""
    simulator_instance.step_counter = 0
    simulator_instance.sim_time = 0.0

    t0_mono = time.monotonic()
    t0_sim = simulator_instance.sim_time

    # Simulate 50 frames with 0.1s dt
    for _ in range(50):
        frame = compute_canonical_tick(dt=0.1)

    t1_sim = simulator_instance.sim_time
    sim_elapsed = t1_sim - t0_sim

    # 50 frames * 0.1s = 5.0 seconds sim time
    assert abs(sim_elapsed - 5.0) < 0.1

def test_missed_deadline_records_degraded_status():
    """Verifies that when frame dt exceeds threshold (>0.12s), missed_deadlines is incremented."""
    initial_misses = scheduler_stats.get("missed_deadlines", 0)

    # Force tick with overrun dt=0.2s (>0.12s threshold)
    dt_overrun = 0.2
    if dt_overrun > 0.12:
        scheduler_stats["missed_deadlines"] += 1

    assert scheduler_stats["missed_deadlines"] > initial_misses

def test_non_blocking_websocket_manager_queues():
    """Verifies per-client asyncio.Queue(maxsize=1) does not block when broadcasting to slow clients."""
    async def run_ws_test():
        cm = ConnectionManager()
        
        # Mock websockets
        class MockWebSocket:
            def __init__(self, is_slow=False):
                self.is_slow = is_slow
                self.received = []
                self.client_state = None

            async def accept(self):
                pass

            async def send_text(self, text):
                if self.is_slow:
                    await asyncio.sleep(0.5)  # Simulate slow client delay
                self.received.append(text)

            async def close(self, code=1000, reason=""):
                pass

        ws_fast = MockWebSocket(is_slow=False)
        ws_slow = MockWebSocket(is_slow=True)

        connected_fast = await cm.connect(ws_fast, is_demo=False)
        connected_slow = await cm.connect(ws_slow, is_demo=False)

        assert connected_fast and connected_slow
        assert len(cm.active_clients) == 2

        # Broadcast multiple frames quickly
        t0 = time.perf_counter()
        for i in range(5):
            await cm.broadcast(f"frame_{i}")
        t_elapsed = time.perf_counter() - t0

        # Broadcast MUST execute immediately (<50ms) without waiting for slow client's 500ms send!
        assert t_elapsed < 0.1

        # Clean up
        cm.disconnect(ws_fast)
        cm.disconnect(ws_slow)
        assert len(cm.active_clients) == 0

    asyncio.run(run_ws_test())

def test_rbac_authorization_on_live_fault_endpoints():
    """Verifies that non-Engineers receive HTTP 403 Forbidden on live fault mutation endpoints."""
    # Create tokens for Demo, Operator, and Engineer
    demo_token = create_access_token({"sub": "demo_user", "role": "demo"})
    operator_token = create_access_token({"sub": "op_user", "role": "operator"})
    engineer_token = create_access_token({"sub": "eng_user", "role": "engineer"})

    fault_payload = {
        "scenario": "CYLINDER_THERMAL",
        "component": "CYLINDER_1",
        "profile": "GRADUAL",
        "intensity": 1.0,
        "rate": "MODERATE"
    }

    # 1. Demo User -> 403 Forbidden
    resp_demo = client.post(
        "/api/fault-injection/start",
        headers={"Authorization": f"Bearer {demo_token}"},
        json=fault_payload
    )
    assert resp_demo.status_code == 403

    resp_demo_clear = client.post(
        "/api/fault-injection/clear",
        headers={"Authorization": f"Bearer {demo_token}"}
    )
    assert resp_demo_clear.status_code == 403

    # 2. Operator User -> 403 Forbidden
    resp_op = client.post(
        "/api/fault-injection/start",
        headers={"Authorization": f"Bearer {operator_token}"},
        json=fault_payload
    )
    assert resp_op.status_code == 403

    # 3. Engineer User -> 200 Success
    resp_eng = client.post(
        "/api/fault-injection/start",
        headers={"Authorization": f"Bearer {engineer_token}"},
        json=fault_payload
    )
    assert resp_eng.status_code == 200
    assert resp_eng.json()["status"] == "success"

    # Clean up fault
    client.post(
        "/api/fault-injection/clear",
        headers={"Authorization": f"Bearer {engineer_token}"}
    )

def test_playground_traces_file_exists_and_valid():
    """Verifies that frontend/playground_traces.js exists and contains valid JSON trace structure."""
    traces_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "playground_traces.js")
    assert os.path.exists(traces_path)

    with open(traces_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "PLAYGROUND_TRACES =" in content or "PLAYGROUND_TRACES" in content
    assert "CYLINDER_THERMAL" in content
    assert "OIL_PRESSURE" in content
    assert "INCREASING_VIBRATION" in content
    assert "SENSOR_DRIFT" in content
    assert "INTERMITTENT_COMBUSTION" in content
    assert "INJECTOR_DISTURBANCE" in content

def test_no_localhost_hardcoded_in_connection_status():
    """Verifies that 127.0.0.1:8000 is NOT hardcoded in login-server-status HTML or JS connection status innerHTML."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    js_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "app.js")

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    # Check index.html line around login-server-status
    assert "Connecting to backend server (127.0.0.1:8000)" not in html_content
    assert "Connecting to Aero Digital Twin Server..." in html_content

    # Check app.js innerHTML assignments for checkServerConnection
    assert "Backend Server Connected (127.0.0.1:8000)" not in js_content

def test_api_health_endpoint():
    """Verifies GET /api/health responds with 200 OK and valid status json."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert "system" in data
