"""
Tests for GCS & DFCS Demonstrator Requirements
"""

import unittest
import os
import re

INDEX_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))
APP_JS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "app.js"))


class TestGCSDFCSDemonstrator(unittest.TestCase):

    def setUp(self):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            self.index_html = f.read()

        with open(APP_JS_PATH, "r", encoding="utf-8") as f:
            self.app_js = f.read()

    def test_platform_identifier_is_neutral(self):
        """Verify TAPAS BH-201 is replaced with MALE-UAV-REF-01 in GCS section."""
        self.assertNotIn("TAPAS BH-201 (UAV-001)", self.index_html)
        self.assertIn("MALE-UAV-REF-01", self.index_html)

    def test_simulated_link_label(self):
        """Verify SATCOM connectivity claim is replaced with SIMULATED GCS LINK."""
        self.assertNotIn("SATCOM / LOS SYNCHRONIZED", self.index_html)
        self.assertIn("SIMULATED GCS LINK", self.index_html)

    def test_dfcs_title_and_disclaimer_banner(self):
        """Verify DFCS title is DFCS Advisory Demonstrator and includes non-flight-certified disclaimer."""
        self.assertIn("DFCS Advisory Demonstrator", self.index_html)
        self.assertIn("Prototype Advisory Logic — Not Flight-Certified", self.index_html)
        self.assertIn("PROTOTYPE DEMONSTRATOR ONLY — NO REAL FLIGHT CONTROL COMMAND ISSUED.", self.index_html)

    def test_display_elements_present_in_gcs_dfcs_html(self):
        """Verify all 7 required display elements are present in HTML structure."""
        self.assertIn('id="gcs-state-display"', self.index_html)
        self.assertIn('id="gcs-hi-display"', self.index_html)
        self.assertIn('id="gcs-anomaly-display"', self.index_html)
        self.assertIn('id="gcs-rul-display"', self.index_html)
        self.assertIn('id="gcs-timestamp-display"', self.index_html)
        self.assertIn('id="dfcs-throttle-limit"', self.index_html)
        self.assertIn('id="dfcs-advisory-rationale"', self.index_html)

    def test_app_js_state_advisory_mapping_and_no_contradiction(self):
        """Verify app.js maps states cleanly and avoids contradictory text in CRITICAL state."""
        self.assertIn('sysState === "CRITICAL"', self.app_js)
        self.assertIn('Prototype emergency-envelope advisory active', self.app_js)
        self.assertIn('Prototype Assumption: 30% Throttle Limit', self.app_js)
        self.assertIn('Prototype Assumption: 60% Throttle Limit', self.app_js)
        self.assertIn('Prototype Assumption: 85% Throttle Limit', self.app_js)

        # Ensure CRITICAL block does NOT assign "Standard climb/cruise"
        critical_match = re.search(r'if\s*\(\s*sysState\s*===\s*"CRITICAL"\s*\)\s*\{([^}]+)\}', self.app_js)
        self.assertIsNotNone(critical_match)
        critical_code = critical_match.group(1)
        self.assertNotIn("Standard climb/cruise", critical_code)
        self.assertIn("Emergency derated thrust requested", critical_code)


if __name__ == "__main__":
    unittest.main()
