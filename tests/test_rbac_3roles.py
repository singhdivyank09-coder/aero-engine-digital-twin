"""
Unit & Integration Tests for 3-Role Access Control (ENGINEER, OPERATOR, DEMO)
Verifies:
1. Engineer login and 200 OK access on fault control and scenario modification endpoints.
2. Operator login and 403 Forbidden access on fault control and scenario modification endpoints.
3. Demo login via CAPTCHA verification and 403 Forbidden access on fault control, scenario, and audit log endpoints.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure test mode environment
os.environ["ENVIRONMENT"] = "development"
os.environ["TURNSTILE_SECRET_KEY"] = "test"
os.environ["JWT_SECRET_KEY"] = "TEST_JWT_SECRET_KEY_FOR_UNIT_TESTS_ONLY"

from backend.main import app
from backend.auth import create_access_token

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_engineer_permissions():
    # Login as Engineer
    resp = client.post("/api/auth/login", json={"username": "engineer", "password": "engineer123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Fault injection start
    resp_fault = client.post(
        "/api/fault-injection/start",
        json={"scenario": "CYLINDER_THERMAL_DEGRADATION", "component": "CYLINDER_1", "intensity": 1.0},
        headers=headers
    )
    assert resp_fault.status_code == 200, resp_fault.text
    assert resp_fault.json()["status"] == "success"

    # 2. Scenario change
    resp_sc = client.post("/api/session/scenario", json={"profile": "CLIMB"}, headers=headers)
    assert resp_sc.status_code == 200, resp_sc.text

    # 3. Clear fault
    resp_clr = client.post("/api/fault-injection/clear", headers=headers)
    assert resp_clr.status_code == 200, resp_clr.text

    # 4. Audit logs access
    resp_audit = client.get("/api/audit-logs", headers=headers)
    assert resp_audit.status_code == 200, resp_audit.text


def test_operator_permissions_and_403_enforcement():
    # Login as Operator
    resp = client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Telemetry read-only access (200 OK)
    resp_telem = client.get("/api/telemetry/latest", headers=headers)
    assert resp_telem.status_code == 200

    # 2. Fault injection start MUST FAIL (403 Forbidden)
    resp_fault = client.post(
        "/api/fault-injection/start",
        json={"scenario": "CYLINDER_THERMAL_DEGRADATION", "component": "CYLINDER_1"},
        headers=headers
    )
    assert resp_fault.status_code == 403, f"Expected 403, got {resp_fault.status_code}"

    # 3. Scenario modification MUST FAIL (403 Forbidden)
    resp_sc = client.post("/api/session/scenario", json={"profile": "CLIMB"}, headers=headers)
    assert resp_sc.status_code == 403

    # 4. Clear fault MUST FAIL (403 Forbidden)
    resp_clr = client.post("/api/fault-injection/clear", headers=headers)
    assert resp_clr.status_code == 403


def test_demo_permissions_and_403_enforcement():
    # Demo login with mock CAPTCHA token
    resp_demo = client.post("/api/auth/demo-login", json={"captcha_token": "test_captcha_token"})
    assert resp_demo.status_code == 200, resp_demo.text
    demo_data = resp_demo.json()
    assert demo_data["role"] == "demo"
    token = demo_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Read-only replay & metrics (200 OK)
    resp_replay = client.get("/api/replay/missions", headers=headers)
    assert resp_replay.status_code == 200

    # 2. Fault injection MUST FAIL (403 Forbidden)
    resp_fault = client.post(
        "/api/fault-injection/start",
        json={"scenario": "CYLINDER_THERMAL_DEGRADATION", "component": "CYLINDER_1"},
        headers=headers
    )
    assert resp_fault.status_code == 403


    # 3. Audit logs access MUST FAIL (403 Forbidden)
    resp_audit = client.get("/api/audit-logs", headers=headers)
    assert resp_audit.status_code == 403

    # 4. Debug session diagnostic endpoint MUST FAIL (403 Forbidden)
    resp_debug = client.get("/api/debug/session", headers=headers)
    assert resp_debug.status_code == 403
