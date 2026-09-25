import unittest
import os
import sys
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.main import app
from backend.database import get_db_connection, init_db, log_audit_event, get_recent_audit_logs

class TestSecurityAuditLogs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def setUp(self):
        # Clean audit_logs table before each test
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_logs;")
        conn.commit()
        conn.close()

    def test_database_schema_has_role_column(self):
        """Verify role column exists in audit_logs table."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(audit_logs);")
        columns = [col[1] for col in cursor.fetchall()]
        conn.close()

        self.assertIn("role", columns)
        self.assertIn("username", columns)
        self.assertIn("action", columns)
        self.assertIn("details", columns)
        self.assertIn("timestamp", columns)

    def test_log_audit_event_and_get_recent_audit_logs(self):
        """Test inserting and retrieving audit events with user & role fields."""
        log_audit_event("operator", "login", "User logged in with role operator", role="operator")
        log_audit_event("engineer", "fault injection started", "Started CYLINDER_THERMAL fault", role="engineer")

        logs = get_recent_audit_logs(limit=50)
        self.assertEqual(len(logs), 2)
        
        # Most recent first
        latest = logs[0]
        self.assertEqual(latest["username"], "engineer")
        self.assertEqual(latest["user"], "engineer")
        self.assertEqual(latest["role"], "engineer")
        self.assertEqual(latest["action"], "fault injection started")

        earlier = logs[1]
        self.assertEqual(earlier["username"], "operator")
        self.assertEqual(earlier["user"], "operator")
        self.assertEqual(earlier["role"], "operator")
        self.assertEqual(earlier["action"], "login")

    def test_api_audit_logs_unauthenticated(self):
        """Unauthenticated GET /api/audit-logs must return HTTP 401."""
        response = self.client.get("/api/audit-logs")
        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.json())

    def test_api_audit_logs_authenticated_and_empty_state(self):
        """Authenticated GET /api/audit-logs with empty database returns empty array."""
        # Login to get token
        login_res = self.client.post("/api/auth/login", json={"username": "engineer", "password": "engineer123"})
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json()["access_token"]

        # Clear audit log created by login for clean testing of empty response
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_logs;")
        conn.commit()
        conn.close()

        response = self.client.get("/api/audit-logs", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("audit_logs", data)
        self.assertEqual(data["audit_logs"], [])

    def test_real_application_events_logging(self):
        """Test real events: login, failed login, fault injection, scenario, dataset mode, client post."""
        # 1. Failed login
        fail_res = self.client.post("/api/auth/login", json={"username": "baduser", "password": "wrongpassword"})
        self.assertEqual(fail_res.status_code, 401)

        # 2. Successful login
        eng_login = self.client.post("/api/auth/login", json={"username": "engineer", "password": "engineer123"})
        self.assertEqual(eng_login.status_code, 200)
        eng_token = eng_login.json()["access_token"]

        # 3. Fault injection started
        fault_res = self.client.post(
            "/api/fault-injection/start",
            json={"scenario": "CYLINDER_THERMAL", "component": "CYLINDER_1", "profile": "GRADUAL", "intensity": 1.0},
            headers={"Authorization": f"Bearer {eng_token}"}
        )
        self.assertEqual(fault_res.status_code, 200)

        # 4. Fault injection cleared
        clear_res = self.client.post(
            "/api/fault-injection/clear",
            headers={"Authorization": f"Bearer {eng_token}"}
        )
        self.assertEqual(clear_res.status_code, 200)

        # 5. Scenario changed
        scen_res = self.client.post(
            "/api/mission/set-profile",
            json={"profile": "HIGH_ALTITUDE"},
            headers={"Authorization": f"Bearer {eng_token}"}
        )
        self.assertEqual(scen_res.status_code, 200)

        # 6. Analytics dataset changed
        ds_res = self.client.post(
            "/api/telemetry/data-sources",
            json={"telemetry_source": "SIMULATOR", "analytics_dataset": "ALFA"},
            headers={"Authorization": f"Bearer {eng_token}"}
        )
        self.assertEqual(ds_res.status_code, 200)

        # 7. Client POST endpoint (mission replay started, mission report exported, logout)
        replay_res = self.client.post(
            "/api/audit-logs/log",
            json={"action": "mission replay started", "details": "Started playback"},
            headers={"Authorization": f"Bearer {eng_token}"}
        )
        self.assertEqual(replay_res.status_code, 200)

        report_res = self.client.post(
            "/api/audit-logs/log",
            json={"action": "mission report exported", "details": "Exported JSON report"},
            headers={"Authorization": f"Bearer {eng_token}"}
        )
        self.assertEqual(report_res.status_code, 200)

        logout_res = self.client.post(
            "/api/audit-logs/log",
            json={"action": "logout", "details": "User logged out"},
            headers={"Authorization": f"Bearer {eng_token}"}
        )
        self.assertEqual(logout_res.status_code, 200)

        # Retrieve audit logs
        logs_res = self.client.get("/api/audit-logs", headers={"Authorization": f"Bearer {eng_token}"})
        self.assertEqual(logs_res.status_code, 200)
        logs = logs_res.json()["audit_logs"]

        actions = [l["action"] for l in logs]
        self.assertIn("failed login", actions)
        self.assertIn("login", actions)
        self.assertIn("fault injection started", actions)
        self.assertIn("fault injection cleared", actions)
        self.assertIn("scenario changed", actions)
        self.assertIn("analytics dataset changed", actions)
        self.assertIn("mission replay started", actions)
        self.assertIn("mission report exported", actions)
        self.assertIn("logout", actions)

if __name__ == "__main__":
    unittest.main()
