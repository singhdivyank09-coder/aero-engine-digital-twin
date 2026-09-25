import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.replay_service import ReplayService

class TestEventDeduplicationTimeline(unittest.TestCase):
    def setUp(self):
        self.replay_service = ReplayService()

    def test_timeline_marker_identity_and_schema(self):
        """Each timeline marker must contain required identity keys."""
        data = self.replay_service.generate_historical_mission()
        markers = data.get("timeline_markers", [])
        self.assertIsInstance(markers, list)

        required_keys = [
            "event_id",
            "frame_index",
            "timestamp",
            "event_type",
            "subsystem",
            "component",
            "label",
            "color",
            "description"
        ]

        for m in markers:
            for k in required_keys:
                self.assertIn(k, m, f"Missing key {k} in timeline marker {m}")

if __name__ == "__main__":
    unittest.main()
