"""
Automated Test Suite for Aero Engine Digital Twin Security, Authentication & RBAC Enforcements
Tests:
- Configurable credentials & JWT token authentication
- Rejection of unauthenticated access to debug, telemetry, audit logs, and WebSockets
- RBAC enforcement (403 Forbidden for operator role on fault injection & control endpoints)
- Successful authorization for engineer role on control endpoints
- Public availability of safe read-only endpoints
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_public_readonly_endpoints():
    """Verify safe public read-only endpoints are accessible without authentication."""
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"

    r_ml = client.get("/api/ml/metrics")
    assert r_ml.status_code == 200

    r_faults = client.get("/api/faults/registry")
    assert r_faults.status_code == 200

    r_metrics = client.get("/api/system/metrics")
    assert r_metrics.status_code == 200


def test_authentication_workflow():
    """Verify login authentication success and failure handling."""
    # Invalid password
    r_bad = client.post("/api/auth/login", json={"username": "operator", "password": "wrongpassword"})
    assert r_bad.status_code == 401

    # Valid operator login
    r_op = client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
    assert r_op.status_code == 200
    op_data = r_op.json()
    assert "access_token" in op_data
    assert op_data["role"] == "operator"

    # Valid engineer login
    r_eng = client.post("/api/auth/login", json={"username": "engineer", "password": "engineer123"})
    assert r_eng.status_code == 200
    eng_data = r_eng.json()
    assert "access_token" in eng_data
    assert eng_data["role"] == "engineer"


def test_unauthenticated_endpoint_rejection():
    """Verify unauthenticated requests to protected endpoints return 401 Unauthorized."""
    endpoints = [
        ("GET", "/api/debug/session", None),
        ("GET", "/api/telemetry/latest", None),
        ("GET", "/api/audit-logs", None),
        ("POST", "/api/mission/set-profile", {"profile": "CRUISE"}),
        ("POST", "/api/fault-injection/start", {"scenario": "CYLINDER_THERMAL", "component": "CYLINDER_1"}),
        ("POST", "/api/fault-injection/pause", {}),
        ("POST", "/api/fault-injection/clear", {}),
        ("POST", "/api/fault-injection/inject", {"fault_type": "OVERHEAT"}),
        ("POST", "/api/telemetry/dataset-mode", {"mode": "NOMINAL_CRUISE"}),
        ("POST", "/api/telemetry/data-sources", {"telemetry_source": "SIMULATOR"}),
        ("POST", "/api/replay/start-new-mission", {}),
    ]
    for method, path, payload in endpoints:
        if method == "GET":
            res = client.get(path)
        else:
            res = client.post(path, json=payload or {})
        assert res.status_code == 401, f"Expected 401 for unauthenticated {method} {path}, got {res.status_code}"


def test_websocket_unauthenticated_rejection():
    """Verify WebSocket connection requires valid authentication token."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/telemetry") as ws:
            pass


def test_operator_rbac_restrictions():
    """Verify operators are denied permission (403 Forbidden) on simulation control & fault endpoints."""
    # Login as operator
    r_op = client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
    token = r_op.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    control_endpoints = [
        ("/api/mission/set-profile", {"profile": "HOT_WEATHER"}),
        ("/api/fault-injection/start", {"scenario": "CYLINDER_THERMAL", "component": "CYLINDER_1"}),
        ("/api/fault-injection/pause", {}),
        ("/api/fault-injection/clear", {}),
        ("/api/fault-injection/inject", {"fault_type": "OVERHEAT"}),
        ("/api/telemetry/dataset-mode", {"mode": "NOMINAL_CRUISE"}),
        ("/api/telemetry/data-sources", {"telemetry_source": "SIMULATOR"}),
        ("/api/replay/start-new-mission", {}),
    ]

    for path, body in control_endpoints:
        res = client.post(path, json=body, headers=headers)
        assert res.status_code == 403, f"Expected 403 for operator on {path}, got {res.status_code}"


def test_engineer_rbac_permissions():
    """Verify engineers are allowed to execute simulation control & fault endpoints."""
    # Login as engineer
    r_eng = client.post("/api/auth/login", json={"username": "engineer", "password": "engineer123"})
    token = r_eng.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r_start = client.post("/api/fault-injection/start", json={"scenario": "CYLINDER_THERMAL", "component": "CYLINDER_1"}, headers=headers)
    assert r_start.status_code == 200

    r_clear = client.post("/api/fault-injection/clear", headers=headers)
    assert r_clear.status_code == 200
