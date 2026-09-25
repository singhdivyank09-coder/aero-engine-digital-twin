import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import create_access_token
from backend.fault_registry import is_valid_fault_component

client = TestClient(app)

def get_auth_header():
    token = create_access_token({"sub": "engineer", "role": "engineer", "full_name": "Test Engineer"})
    return {"Authorization": f"Bearer {token}"}

def test_valid_fault_component_registry_logic():
    assert is_valid_fault_component("FUEL_INJECTOR_ABNORMALITY", "INJECTOR_CYL_2") is True
    assert is_valid_fault_component("FUEL_INJECTOR_ABNORMALITY", "OIL_SYSTEM") is False
    assert is_valid_fault_component("CYLINDER_MISFIRE", "CYLINDER_1") is True
    assert is_valid_fault_component("CYLINDER_MISFIRE", "CRANKSHAFT_BEARING_ASSEMBLY") is False
    assert is_valid_fault_component("OIL_PRESSURE_DEGRADATION", "OIL_SYSTEM") is True
    assert is_valid_fault_component("OIL_PRESSURE_DEGRADATION", "CYLINDER_3") is False

def test_backend_validation_rejects_invalid_pair():
    headers = get_auth_header()
    resp = client.post(
        "/api/fault-injection/start",
        json={"scenario": "FUEL_INJECTOR_ABNORMALITY", "component": "OIL_SYSTEM"},
        headers=headers
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data.get("error") == "INVALID_FAULT_COMPONENT_PAIR"
    assert data.get("fault") == "FUEL_INJECTOR_ABNORMALITY"
    assert data.get("component") == "OIL_SYSTEM"

def test_backend_validation_accepts_valid_pair():
    headers = get_auth_header()
    resp = client.post(
        "/api/fault-injection/start",
        json={"scenario": "FUEL_INJECTOR_ABNORMALITY", "component": "INJECTOR_CYL_2"},
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "success"
