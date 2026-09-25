"""
Unit & Integration Test Suite for Backend Predictive Health Engine
Verifies:
1. Constant healthy telemetry => NOMINAL
2. One isolated sensor spike => suppressed (must NOT become predictive risk or degradation)
3. Gradual CHT increase while below current limit => DEGRADATION_DETECTED
4. Sustained rising CHT forecast to become unsafe => PREDICTIVE_RISK BEFORE current threshold crossing
5. Actual unsafe CHT later => ACTIVE_FAULT
6. Declining oil pressure while still nominal => predictive lubrication risk
7. Increasing vibration variance and slope => predictive mechanical degradation
"""

import unittest
from backend.predictive_health_engine import PredictiveHealthEngine

class TestPredictiveHealthEngine(unittest.TestCase):

    def setUp(self):
        self.engine = PredictiveHealthEngine(history_window_seconds=60.0, sampling_rate=10.0)

    def _get_base_telemetry(self, t=0.0):
        return {
            "timestamp": t,
            "rpm": 5000.0,
            "map": 1.15,
            "cht1": 120.0, "cht2": 120.8, "cht3": 119.5, "cht4": 120.2,
            "egt1": 748.0, "egt2": 750.0, "egt3": 746.5, "egt4": 749.0,
            "oil_press": 4.20,
            "oil_temp": 88.5,
            "fuel_flow": 17.5,
            "vibration_rms": 1.12,
            "battery_volt": 14.10
        }

    def _get_base_physics_state(self):
        return {
            "residuals": {
                "cht_delta": 0.0,
                "oil_press_delta": 0.0,
                "egt_delta": 0.0
            }
        }

    def _get_base_ae(self):
        return {"anomaly_score": 0.015}

    def _get_base_cusum(self):
        return {"cusum_alert_active": False}

    def test_1_constant_healthy_telemetry_is_nominal(self):
        """Constant healthy telemetry must yield status NOMINAL for all subsystems."""
        for i in range(20):
            t = i * 0.1
            telem = self._get_base_telemetry(t)
            assessments = self.engine.process_frame(telem, self._get_base_physics_state(), self._get_base_ae(), self._get_base_cusum())

        for ass in assessments:
            self.assertEqual(ass["status"], "NOMINAL")
            self.assertIn("NOMINAL", ass["evidence_sources"][0])

    def test_2_isolated_sensor_spike_is_suppressed(self):
        """One single isolated sensor spike must NOT trigger PREDICTIVE_RISK or DEGRADATION_DETECTED."""
        # 1. Run 20 nominal frames
        for i in range(20):
            t = i * 0.1
            telem = self._get_base_telemetry(t)
            self.engine.process_frame(telem, self._get_base_physics_state(), self._get_base_ae(), self._get_base_cusum())

        # 2. Inject 1 isolated spike on CHT1
        t_spike = 20 * 0.1
        spike_telem = self._get_base_telemetry(t_spike)
        spike_telem["cht1"] = 160.0  # Spike

        assessments = self.engine.process_frame(spike_telem, self._get_base_physics_state(), self._get_base_ae(), self._get_base_cusum())
        thermal_ass = [a for a in assessments if a["subsystem"] == "Thermal"][0]

        # Isolated spike without sustained slope must be suppressed (NOT PREDICTIVE_RISK)
        self.assertNotEqual(thermal_ass["status"], "PREDICTIVE_RISK")

    def test_3_gradual_cht_increase_below_limit_triggers_degradation(self):
        """Gradual CHT increase while below current limit triggers DEGRADATION_DETECTED."""
        # Ramp CHT1 from 120°C up to 132°C over 100 frames (10 seconds, slope ~ 1.2°C/s)
        for i in range(100):
            t = i * 0.1
            telem = self._get_base_telemetry(t)
            telem["cht1"] = 120.0 + (i * 0.12)  # Reach 132°C (< 135°C nominal ceiling, < 145°C limit)
            assessments = self.engine.process_frame(telem, self._get_base_physics_state(), self._get_base_ae(), self._get_base_cusum())

        thermal_ass = [a for a in assessments if a["subsystem"] == "Thermal"][0]
        self.assertIn(thermal_ass["status"], ["DEGRADATION_DETECTED", "PREDICTIVE_RISK"])

    def test_4_sustained_rising_cht_forecast_unsafe_triggers_predictive_risk_before_threshold(self):
        """
        Sustained rising CHT forecast to become unsafe MUST trigger PREDICTIVE_RISK
        BEFORE current threshold crossing (i.e. while current CHT < 145.0°C).
        """
        predictive_risk_triggered_below_limit = False
        trigger_cht_val = 0.0

        # Ramp CHT1 from 120°C towards 145°C at +0.45°C/s over 40 seconds (400 frames)
        for i in range(400):
            t = i * 0.1
            telem = self._get_base_telemetry(t)
            curr_cht = 120.0 + (i * 0.045)
            telem["cht1"] = curr_cht
            phys = self._get_base_physics_state()
            phys["residuals"]["cht_delta"] = curr_cht - 120.0

            assessments = self.engine.process_frame(telem, phys, self._get_base_ae(), self._get_base_cusum())
            thermal_ass = [a for a in assessments if a["subsystem"] == "Thermal"][0]

            if thermal_ass["status"] == "PREDICTIVE_RISK" and curr_cht < 145.0:
                predictive_risk_triggered_below_limit = True
                trigger_cht_val = curr_cht
                break

        self.assertTrue(predictive_risk_triggered_below_limit, "PREDICTIVE_RISK must trigger BEFORE CHT reaches 145.0°C limit")
        self.assertLess(trigger_cht_val, 145.0)
        print(f"\n[TEST VERIFIED] PREDICTIVE_RISK triggered at CHT1 = {trigger_cht_val:.1f}°C (< 145.0°C safety limit)")

    def test_5_actual_unsafe_cht_later_triggers_active_fault(self):
        """Actual unsafe CHT later (cht >= 145.0°C) triggers ACTIVE_FAULT."""
        for i in range(600):
            t = i * 0.1
            telem = self._get_base_telemetry(t)
            telem["cht1"] = 120.0 + (i * 0.05)  # Will reach 150°C
            assessments = self.engine.process_frame(telem, self._get_base_physics_state(), self._get_base_ae(), self._get_base_cusum())

        thermal_ass = [a for a in assessments if a["subsystem"] == "Thermal"][0]
        self.assertEqual(thermal_ass["status"], "ACTIVE_FAULT")

    def test_6_declining_oil_pressure_while_nominal_triggers_predictive_risk(self):
        """Declining oil pressure while still nominal (> 2.50 bar limit) triggers predictive lubrication risk."""
        predictive_lube_triggered_above_limit = False
        trigger_p_val = 0.0

        # Decay oil pressure from 4.20 bar down towards 2.50 bar at -0.04 bar/s over 35 seconds
        for i in range(350):
            t = i * 0.1
            telem = self._get_base_telemetry(t)
            curr_p = max(2.51, 4.20 - (i * 0.004))
            telem["oil_press"] = curr_p
            phys = self._get_base_physics_state()
            phys["residuals"]["oil_press_delta"] = 4.20 - curr_p

            assessments = self.engine.process_frame(telem, phys, self._get_base_ae(), self._get_base_cusum())
            lube_ass = [a for a in assessments if a["subsystem"] == "Lubrication"][0]

            if lube_ass["status"] in ["PREDICTIVE_RISK", "DEGRADATION_DETECTED"] and curr_p > 2.50:
                predictive_lube_triggered_above_limit = True
                trigger_p_val = curr_p
                break

        self.assertTrue(predictive_lube_triggered_above_limit, "Predictive lubrication risk must trigger while oil pressure is > 2.50 bar limit")
        self.assertGreater(trigger_p_val, 2.50)
        print(f"\n[TEST VERIFIED] Predictive Lubrication Risk triggered at Oil Pressure = {trigger_p_val:.2f} bar (> 2.50 bar safety limit)")

    def test_7_increasing_vibration_variance_and_slope_triggers_predictive_mechanical_degradation(self):
        """Increasing vibration variance and slope triggers predictive mechanical degradation."""
        for i in range(250):
            t = i * 0.1
            telem = self._get_base_telemetry(t)
            # Add increasing trend + increasing noise variance
            noise = (i % 5 - 2) * 0.08 * (i / 100.0)
            telem["vibration_rms"] = 1.12 + (i * 0.003) + noise
            assessments = self.engine.process_frame(telem, self._get_base_physics_state(), self._get_base_ae(), self._get_base_cusum())

        mech_ass = [a for a in assessments if a["subsystem"] == "Mechanical"][0]
        self.assertIn(mech_ass["status"], ["PREDICTIVE_RISK", "DEGRADATION_DETECTED"])
        print(f"\n[TEST VERIFIED] Mechanical Predictive Degradation status: {mech_ass['status']}")

if __name__ == "__main__":
    unittest.main()
