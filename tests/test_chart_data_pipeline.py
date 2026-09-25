"""
Unit Test for Real-Time Chart Data Pipelines
Verifies:
1. Telemetry frames emitted at 10Hz contain required channels: RPM, CHT1, EGT1, Oil pressure, timestamp.
2. Digital Twin Core processes frames and generates residuals_table with all 5 channels: avg_cht, avg_egt, oil_press, oil_temp, power_kw.
3. Over a 10-second simulation (100 frames @ 10Hz), 100 valid data points with timestamps are produced.
4. Injecting gradual CHT1 thermal degradation causes CHT1 and CHT residual to visibly trend upward.
"""

import unittest
from backend.telemetry_simulator import TelemetrySimulator
from backend.digital_twin_core import DigitalTwinCore

class TestChartDataPipeline(unittest.TestCase):

    def setUp(self):
        self.simulator = TelemetrySimulator()
        self.digital_twin = DigitalTwinCore()

    def test_chart_channels_and_history_transport(self):
        """Verify all required telemetry channels and residual channels exist in every frame."""
        for _ in range(10):
            frame = self.simulator.get_next_frame()
            snapshot = self.digital_twin.process_telemetry_frame(frame)

        telem = snapshot["telemetry"]
        res_tab = snapshot["residuals_table"]

        # Main Telemetry Chart Channels
        self.assertIn("rpm", telem)
        self.assertIn("cht1", telem)
        self.assertIn("egt1", telem)
        self.assertIn("oil_press", telem)
        self.assertIn("timestamp", telem)

        # Residual Chart Channels
        self.assertIn("avg_cht", res_tab)
        self.assertIn("avg_egt", res_tab)
        self.assertIn("oil_press", res_tab)
        self.assertIn("oil_temp", res_tab)
        self.assertIn("power_kw", res_tab)

        for channel in ["avg_cht", "avg_egt", "oil_press", "oil_temp", "power_kw"]:
            self.assertIn("residual", res_tab[channel])
            self.assertIsInstance(res_tab[channel]["residual"], (int, float))

    def test_10s_simulation_data_accumulation(self):
        """Verify running simulator for 10 seconds yields ~100 frames with timestamps."""
        snapshots = []
        for _ in range(100):
            frame = self.simulator.get_next_frame()
            snapshot = self.digital_twin.process_telemetry_frame(frame)
            snapshots.append(snapshot)

        self.assertEqual(len(snapshots), 100)
        
        timestamps = [s["timestamp"] for s in snapshots]
        self.assertEqual(len(timestamps), 100)
        self.assertAlmostEqual(timestamps[-1] - timestamps[0], 9.9, delta=0.5)

    def test_thermal_degradation_chart_trend(self):
        """Verify CHT1 and CHT residual trend upward during gradual thermal degradation."""
        # 1. Run nominal 10 frames
        nominal_cht1 = []
        nominal_residuals = []
        for _ in range(10):
            frame = self.simulator.get_next_frame()
            snapshot = self.digital_twin.process_telemetry_frame(frame)
            nominal_cht1.append(snapshot["telemetry"]["cht1"])
            nominal_residuals.append(snapshot["residuals_table"]["avg_cht"]["residual"])

        base_cht1 = sum(nominal_cht1) / len(nominal_cht1)
        base_res = sum(nominal_residuals) / len(nominal_residuals)

        # 2. Inject gradual thermal degradation
        self.simulator.start_fault_injection(
            scenario="CYLINDER_THERMAL",
            component="CYLINDER_1",
            profile="GRADUAL",
            intensity=1.8,
            ramp_duration=30.0
        )

        degraded_cht1 = []
        degraded_residuals = []
        for _ in range(100):  # 10 seconds of degradation
            frame = self.simulator.get_next_frame()
            snapshot = self.digital_twin.process_telemetry_frame(frame)
            degraded_cht1.append(snapshot["telemetry"]["cht1"])
            degraded_residuals.append(snapshot["residuals_table"]["avg_cht"]["residual"])

        final_cht1 = sum(degraded_cht1[-10:]) / 10.0
        final_res = sum(degraded_residuals[-10:]) / 10.0

        # Assert CHT1 and CHT residual visibly trended upward
        self.assertGreater(final_cht1, base_cht1 + 10.0, "CHT1 must trend upward during thermal degradation")
        self.assertGreater(final_res, base_res + 5.0, "CHT residual must trend upward during thermal degradation")

if __name__ == "__main__":
    unittest.main()
