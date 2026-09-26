import pytest
import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.auth import get_password_hash, verify_password
from backend.main import app, verify_turnstile_captcha

client = TestClient(app)

def test_random_per_user_password_salting():
    pwd = "SecretPassword123!"
    hash1 = get_password_hash(pwd, username="operator")
    hash2 = get_password_hash(pwd, username="operator")

    # Hash format must be salt$hash
    assert "$" in hash1
    assert "$" in hash2

    # Random salts must produce distinct hash outputs for the same password
    assert hash1 != hash2

    # Both hashes must verify correctly
    assert verify_password(pwd, hash1, username="operator") is True
    assert verify_password(pwd, hash2, username="operator") is True
    assert verify_password("WrongPassword", hash1, username="operator") is False

def test_legacy_password_salting_backwards_compatibility():
    import hashlib
    # Test legacy hash without $ delimiter
    legacy_salt = "operator:AERO_DIGITAL_TWIN_SALT_2026"
    legacy_hash = hashlib.pbkdf2_hmac('sha256', "operator123".encode('utf-8'), legacy_salt.encode('utf-8'), 100000).hex()
    
    assert verify_password("operator123", legacy_hash, username="operator") is True
    assert verify_password("wrongpass", legacy_hash, username="operator") is False

def test_captcha_action_and_hostname_validation(monkeypatch):
    # Mock Turnstile siteverify response
    fake_response = {
        "success": True,
        "action": "demo_login",
        "hostname": "aero-engine-digital-twin.onrender.com"
    }

    class MockUrlOpen:
        def __init__(self, resp_dict):
            self.resp_dict = resp_dict
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            import json
            return json.dumps(self.resp_dict).encode("utf-8")

    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "real_secret_key_123")
    monkeypatch.setattr("backend.main.TURNSTILE_SECRET_KEY", "real_secret_key_123")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://aero-engine-digital-twin.onrender.com")

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=8: MockUrlOpen(fake_response))

    # Matching action and matching hostname -> True
    assert verify_turnstile_captcha("token_123", client_ip="1.2.3.4", expected_action="demo_login") is True

    # Action mismatch -> False
    assert verify_turnstile_captcha("token_456", client_ip="1.2.3.4", expected_action="other_action") is False

    # Hostname mismatch -> False
    fake_response_bad_host = {
        "success": True,
        "action": "demo_login",
        "hostname": "malicious-site.com"
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=8: MockUrlOpen(fake_response_bad_host))
    assert verify_turnstile_captcha("token_789", client_ip="1.2.3.4", expected_action="demo_login") is False

    # Production mode: Missing action or missing hostname must be rejected
    monkeypatch.setenv("ENVIRONMENT", "production")
    fake_response_missing_action = {
        "success": True,
        "action": "",
        "hostname": "aero-engine-digital-twin.onrender.com"
    }
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=8: MockUrlOpen(fake_response_missing_action))
    assert verify_turnstile_captcha("token_missing_act", client_ip="1.2.3.4", expected_action="demo_login") is False

def test_per_ip_rate_limiting():
    from backend.main import rate_limit_tracker
    rate_limit_tracker.clear()
    try:
        # Make multiple demo logins from IP A until rate limited
        headers_ip_a = {"X-Forwarded-For": "203.0.113.195"}
        headers_ip_b = {"X-Forwarded-For": "198.51.100.42"}

        # IP B should succeed even if IP A gets rate limited
        res_b = client.post("/api/auth/demo-login", json={"captcha_token": "valid_captcha_token"}, headers=headers_ip_b)
        assert res_b.status_code == 200

        # Flood IP A
        for _ in range(12):
            client.post("/api/auth/demo-login", json={"captcha_token": "valid_captcha_token"}, headers=headers_ip_a)

        # IP A should now be rate limited (429)
        res_a_blocked = client.post("/api/auth/demo-login", json={"captcha_token": "valid_captcha_token"}, headers=headers_ip_a)
        assert res_a_blocked.status_code == 429
        assert "Too many login attempts from your IP" in res_a_blocked.json()["detail"]

        # IP B should STILL be allowed
        res_b_ok = client.post("/api/auth/demo-login", json={"captcha_token": "valid_captcha_token"}, headers=headers_ip_b)
        assert res_b_ok.status_code in [200, 400]  # Not 429!
    finally:
        rate_limit_tracker.clear()
