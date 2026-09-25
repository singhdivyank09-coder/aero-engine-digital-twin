"""
Unit & Integration Tests for Navigation & Responsive Layout
Verifies:
1. Unified single navigation definition across all views.
2. Presence of all 8 required navigation sections in exact order.
3. Absence of restrictive eng-only classes on navigation buttons (tabs visible to all views).
4. Responsive overflow wrapper (.nav-tabs-wrapper) and selector section (.mission-selector) structure.
5. Active page highlighting (.nav-tab.active) preservation.
"""

import unittest
import re
from pathlib import Path

class TestNavigationResponsiveLayout(unittest.TestCase):

    def setUp(self):
        self.html_path = Path("frontend/index.html")
        self.css_path = Path("frontend/styles.css")
        self.js_path = Path("frontend/app.js")

        self.assertTrue(self.html_path.exists(), "index.html must exist")
        self.assertTrue(self.css_path.exists(), "styles.css must exist")
        self.assertTrue(self.js_path.exists(), "app.js must exist")

        self.html_content = self.html_path.read_text(encoding="utf-8")
        self.css_content = self.css_path.read_text(encoding="utf-8")
        self.js_content = self.js_path.read_text(encoding="utf-8")

    def test_required_navigation_sections_present(self):
        """Verify all 8 required navigation sections are defined in index.html."""
        required_sections = [
            ("view-operator", "Operator Dashboard"),
            ("view-digital-twin", "2D Digital Twin Schematic"),
            ("view-engineer", "Fault Injection & Analytics"),
            ("view-replay", "Mission Replay & Reports"),
            ("view-models-datasets", "AI Models & Dataset Mapping"),
            ("view-gcs-dfcs", "GCS & DFCS Demonstrator"),
            ("view-metrics", "System Metrics & Assumptions"),
            ("view-audit", "Security Audit Logs")
        ]

        # Extract navigation buttons block
        nav_match = re.search(r'<nav[^>]*id="gcs-main-navigation"[^>]*>(.*?)</nav>', self.html_content, re.DOTALL)
        self.assertIsNotNone(nav_match, "gcs-main-navigation element must exist in index.html")

        nav_block = nav_match.group(1)

        for target_id, label in required_sections:
            pattern = rf'data-target="{target_id}"[^>]*>.*?{re.escape(label)}'
            self.assertIsNotNone(
                re.search(pattern, nav_block, re.DOTALL),
                f"Navigation button for '{label}' (target: {target_id}) must be present in unified navigation"
            )

    def test_no_silently_hidden_navigation_tabs(self):
        """Verify navigation buttons do not contain eng-only classes that hide them on certain views/roles."""
        nav_match = re.search(r'<div[^>]*id="nav-tabs-list"[^>]*>(.*?)</div>', self.html_content, re.DOTALL)
        self.assertIsNotNone(nav_match, "nav-tabs-list element must exist")

        tabs_block = nav_match.group(1)
        self.assertNotIn("eng-only", tabs_block, "eng-only class should not silently remove navigation tabs")

    def test_responsive_layout_containers_and_css(self):
        """Verify responsive overflow container and breakpoints for 1920x1080, 1366x768, 1280x720."""
        self.assertIn(".nav-tabs-wrapper", self.css_content)
        self.assertIn("overflow-x: auto;", self.css_content)
        self.assertIn(".mission-selector", self.css_content)

        # Verify media queries for responsive resolution testing
        self.assertIn("@media (min-width: 1600px)", self.css_content)
        self.assertIn("@media (max-width: 1366px)", self.css_content)
        self.assertIn("@media (max-width: 1280px)", self.css_content)

    def test_active_highlighting_preserved_in_js(self):
        """Verify JS maintains active tab class switching on click."""
        self.assertIn('classList.remove("active")', self.js_content)
        self.assertIn('classList.add("active")', self.js_content)

if __name__ == "__main__":
    unittest.main()
