import os
import sys
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.main import app

class TestMissionReplayReportModule(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.html_path = os.path.join(self.base_dir, "frontend", "index.html")
        self.js_path = os.path.join(self.base_dir, "frontend", "app.js")

        with open(self.html_path, "r", encoding="utf-8") as f:
            self.html_content = f.read()
        with open(self.js_path, "r", encoding="utf-8") as f:
            self.js_content = f.read()

    def test_api_replay_mission_data_endpoint(self):
        response = self.client.get("/api/replay/mission-data")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("mission_id", data)
        self.assertIn("data_source", data)
        self.assertIn("duration_seconds", data)
        self.assertIn("total_frames", data)
        self.assertIn("frames", data)
        self.assertIn("summary", data)
        self.assertIn("timeline_markers", data)

        frames = data["frames"]
        self.assertGreater(len(frames), 0)

        # Ensure frames contain DigitalTwinCore authoritative snapshots
        sample_frame = frames[0]
        self.assertIn("telemetry", sample_frame)
        self.assertIn("system_state", sample_frame)

    def test_no_certified_health_summary_wording(self):
        self.assertNotIn("certified health summary", self.html_content.lower())
        self.assertIn("Prototype Mission Health Summary", self.html_content)

    def test_reconstruction_acceptance_scrubbing(self):
        response = self.client.get("/api/replay/mission-data")
        data = response.json()
        frames = data["frames"]

        if len(frames) >= 2:
            f_first = frames[0]
            f_last = frames[-1]
            self.assertIn(f_first["system_state"], ["NORMAL", "WATCH", "CAUTION", "WARNING", "CRITICAL"])
            self.assertIn(f_last["system_state"], ["NORMAL", "WATCH", "CAUTION", "WARNING", "CRITICAL"])

    def test_timeline_markers(self):
        response = self.client.get("/api/replay/mission-data")
        data = response.json()
        markers = data["timeline_markers"]
        self.assertIsInstance(markers, list)

if __name__ == "__main__":
    unittest.main()
