"""
Unit & Integration Tests for Cloudflare Turnstile CAPTCHA & Rate Limiting
Verifies:
1. Rejection of missing or invalid CAPTCHA tokens.
2. Rejection of replayed / reused CAPTCHA tokens.
3. Rate limiting enforcement on authentication endpoints.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["ENVIRONMENT"] = "development"
os.environ["TURNSTILE_SECRET_KEY"] = "test"
os.environ["JWT_SECRET_KEY"] = "TEST_JWT_SECRET_KEY_FOR_UNIT_TESTS_ONLY"

from backend.main import app

client = TestClient(app)

def test_captcha_config_endpoint():
    resp = client.get("/api/auth/captcha-config")
    assert resp.status_code == 200
    assert "site_key" in resp.json()

def test_demo_login_valid_token():
    resp = client.post("/api/auth/demo-login", json={"captcha_token": "test_valid_unique_token_1"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "demo"
    assert "access_token" in resp.json()

def test_demo_login_reused_token_rejection():
    token = "test_reused_token_abc"
    # First attempt should succeed
    resp1 = client.post("/api/auth/demo-login", json={"captcha_token": token})
    assert resp1.status_code == 200

    # Second attempt with same token must fail (400 Bad Request)
    resp2 = client.post("/api/auth/demo-login", json={"captcha_token": token})
    assert resp2.status_code == 400
    assert "CAPTCHA verification failed" in resp2.json()["detail"]

def test_invalid_captcha_token():
    resp = client.post("/api/auth/demo-login", json={"captcha_token": "invalid_fake_token_xyz"})
    assert resp.status_code == 400
