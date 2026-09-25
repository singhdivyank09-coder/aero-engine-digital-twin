import os
import sys
import json
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.main import app

class TestModelsDatasetsPage(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.html_path = os.path.join(self.base_dir, "frontend", "index.html")
        self.css_path = os.path.join(self.base_dir, "frontend", "styles.css")
        self.js_path = os.path.join(self.base_dir, "frontend", "app.js")

        with open(self.html_path, "r", encoding="utf-8") as f:
            self.html_content = f.read()
        with open(self.css_path, "r", encoding="utf-8") as f:
            self.css_content = f.read()
        with open(self.js_path, "r", encoding="utf-8") as f:
            self.js_content = f.read()

    def test_api_ml_metrics_endpoint(self):
        response = self.client.get("/api/ml/metrics")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("autoencoder", data)
        self.assertIn("lstm_rul", data)

        ae = data["autoencoder"]
        self.assertIn("artifact_path", ae)
        self.assertIn("model_version", ae)
        self.assertIn("training_dataset", ae)
        self.assertIn("validation_dataset", ae)
        self.assertIn("feature_count", ae)
        self.assertIn("threshold_source", ae)
        self.assertIn("evaluation_timestamp", ae)
        self.assertIn("evaluation_metrics", ae)

        lstm = data["lstm_rul"]
        self.assertIn("artifact_path", lstm)
        self.assertIn("model_version", lstm)
        self.assertIn("training_dataset", lstm)
        self.assertIn("sequence_length", lstm)
        self.assertIn("feature_count", lstm)
        self.assertIn("evaluation_timestamp", lstm)
        self.assertIn("evaluation_metrics", lstm)

    def test_dataset_provenance_table_columns(self):
        expected_columns = [
            "<th>Dataset</th>",
            "<th>Source Feature</th>",
            "<th>Original Physical Meaning</th>",
            "<th>Prototype Usage</th>",
            "<th>Mapping Type</th>"
        ]
        for col in expected_columns:
            self.assertIn(col, self.html_content)

    def test_cmapss_prototype_usage_no_aeropiston_signals(self):
        view_start = self.html_content.find('id="view-models-datasets"')
        table_start = self.html_content.find('<table', view_start)
        table_end = self.html_content.find('</table>', table_start)
        table_section = self.html_content[table_start:table_end]

        
        # Ensure aero-piston signal names are NOT in Prototype Usage for C-MAPSS rows
        self.assertNotIn("<td>CHT (Cylinder Head Temp)</td>", table_section)
        self.assertNotIn("<td>EGT (Exhaust Gas Temp)</td>", table_section)
        self.assertNotIn("<td>Engine Speed RPM</td>", table_section)
        self.assertNotIn("<td>Oil Pressure (bar)</td>", table_section)
        self.assertNotIn("<td>Fuel Flow Rate (L/hr)</td>", table_section)
        self.assertNotIn("<td>Vibration RMS (g)</td>", table_section)

        # Ensure correct degradation feature descriptions ARE present
        self.assertIn("Thermal degradation feature", table_section)
        self.assertIn("Pressure-related degradation feature", table_section)
        self.assertIn("Flow-related degradation feature", table_section)
        self.assertIn("Generic degradation feature", table_section)
        self.assertIn("Sequence prognostic input", table_section)


    def test_cmapss_original_physical_meanings(self):
        self.assertIn("Total temperature at LPC outlet (T24)", self.html_content)
        self.assertIn("Total temperature at HPC outlet (T30)", self.html_content)
        self.assertIn("Total temperature at LPT outlet (T50)", self.html_content)
        self.assertIn("Static pressure at HPC outlet (Ps30)", self.html_content)
        self.assertIn("Ratio of fuel flow to Ps30 (FarB)", self.html_content)
        self.assertIn("Bypass ratio (BPR)", self.html_content)

    def test_cmapss_provenance_disclaimer_note(self):
        required_note = (
            "NASA C-MAPSS is a turbofan run-to-failure dataset used solely as an "
            "analogous prognostics/degradation source. Its sensor variables are not "
            "presented as direct measurements of aero-piston engine parameters."
        )
        self.assertIn(required_note, self.html_content)

    def test_xgboost_class_separation(self):
        self.assertIn("TRAINED DATASET-SUPPORTED CLASSES", self.html_content)
        self.assertIn("SIMULATED PROTOTYPE FAULT SCENARIOS", self.html_content)

    def test_badge_tags_css_and_html(self):
        badge_types = ["trained", "analogue", "rule-based", "simulated", "not-evaluated"]
        for btype in badge_types:
            self.assertIn(f".badge-tag.{btype}", self.css_content)

if __name__ == "__main__":
    unittest.main()
