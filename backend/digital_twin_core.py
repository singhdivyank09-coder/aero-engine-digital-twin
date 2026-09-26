"""
Digital Twin Core Engine — Single Source of Truth & 5-State Machine
Performs:
- Authoritative atomic snapshot generation (same logical processing frame)
- 5-State System Health Machine (NORMAL -> WATCH -> CAUTION -> WARNING -> CRITICAL)
- Stepwise progressive recovery path (CRITICAL -> WARNING -> CAUTION -> WATCH -> NORMAL)
- Hysteresis trigger/clear thresholds & K-of-M temporal persistence
- Transition metadata tracking (previous_state, new_state, timestamp, reason, trigger_metric, trigger_value, recovery_reason)
"""

import math
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from collections import deque

from ml_service.autoencoder_anomaly import AutoencoderAnomalyDetector
from ml_service.cusum_detector import CusumDetector
from ml_service.xgboost_fault_classifier import XGBoostFaultClassifier
from ml_service.lstm_rul_model import LstmRulEstimator
from ml_service.pinn_physics_model import PinnPhysicsModel
from backend.predictive_health_engine import PredictiveHealthEngine
from backend.gru_forecast_service import gru_forecast_service_instance
from backend.predictive_state_machine import predictive_state_machine_instance
from backend.metrics_tracker import metrics_tracker_instance
from backend.telemetry_simulator import simulator_instance
import time

class DigitalTwinCore:
    STATES = ["NORMAL", "WATCH", "CAUTION", "WARNING", "CRITICAL"]

    def __init__(self):
        self.autoencoder = AutoencoderAnomalyDetector()
        self.cusum = CusumDetector()
        self.xgboost = XGBoostFaultClassifier()
        self.lstm_rul = LstmRulEstimator()
        self.pinn_physics = PinnPhysicsModel()
        self.predictive_engine = PredictiveHealthEngine()
        self.state_machine = predictive_state_machine_instance
        self.latest_predictive_assessment = None
        self.predictive_history = deque(maxlen=600)

        # GRU Short-Horizon Forecaster Service
        self.gru_service = gru_forecast_service_instance
        self.latest_forecast = None
        self.forecast_history = deque(maxlen=600)
        self.history_window_full = deque(maxlen=600)

        # Sliding History Buffer for Derivatives
        self.history_window = deque(maxlen=20)

        # Hysteresis & Persistence Ring Buffers (K-of-M = 4 of 6 frames)
        self.anomaly_persistence = deque(maxlen=6)
        self.recovery_persistence = deque(maxlen=3)
        self.current_system_state = "NORMAL"
        self.last_transition_metadata = {
            "previous_state": "NORMAL",
            "new_state": "NORMAL",
            "timestamp": 0.0,
            "reason": "System initialized in nominal state",
            "trigger_metric": "initialization",
            "trigger_value": 0.0,
            "recovery_reason": "N/A"
        }

        # RUL Sequence Stabilization State
        self.cycle_counter = 0
        self.last_rul_cycles = 210.0
        self.smoothed_rul_cycles = 210.0
        self.previous_rul_cycles = 210.0

        # Subsystem Health EMA Smoothing States
        self.health_ema = {
            "thermal": 98.0,
            "lubrication": 99.0,
            "combustion": 97.0,
            "electrical": 100.0,
            "mechanical": 96.0,
            "overall": 98.0
        }

        # Selective ML Model Inference Caches & Frame Sequence Counters
        self._cached_ae_res = None
        self._cached_xgb_res = None
        self._cached_rul_output = None
        self._cached_gru_res = None

        self._ae_last_seq = 0
        self._xgb_last_seq = 0
        self._rul_last_seq = 0
        self._gru_last_seq = 0

    def reset(self):
        """Resets sliding windows, state machine persistent deques, and ML models to clean initial baseline."""
        self.history_window.clear()
        self.anomaly_persistence.clear()
        self.recovery_persistence.clear()
        self.current_system_state = "NORMAL"
        self.last_transition_metadata = {
            "previous_state": "NORMAL",
            "new_state": "NORMAL",
            "timestamp": 0.0,
            "reason": "System initialized in nominal state",
            "trigger_metric": "initialization",
            "trigger_value": 0.0,
            "recovery_reason": "N/A"
        }
        self.cycle_counter = 0
        self.last_rul_cycles = 210.0
        self.smoothed_rul_cycles = 210.0
        self.previous_rul_cycles = 210.0
        self.health_ema = {
            "thermal": 98.0,
            "lubrication": 99.0,
            "combustion": 97.0,
            "electrical": 100.0,
            "mechanical": 96.0,
            "overall": 98.0
        }
        self.predictive_engine = PredictiveHealthEngine()
        self.state_machine.reset()
        self.latest_predictive_assessment = None
        self.predictive_history.clear()
        self.latest_forecast = None
        self.forecast_history.clear()
        self.history_window_full.clear()
        self.cusum = CusumDetector()
        self.autoencoder = AutoencoderAnomalyDetector()

    def _compute_derivatives(self) -> Dict[str, float]:
        if len(self.history_window) < 3:
            return {"d_cht": 0.0, "d_oil_p": 0.0, "d_egt_spread": 0.0, "d_vib": 0.0, "d_batt": 0.0}

        t_first = self.history_window[0]
        t_last = self.history_window[-1]
        dt = max(0.1, float(t_last.get("timestamp", 0)) - float(t_first.get("timestamp", 0)))

        max_cht_first = max([t_first.get(f"cht{i}", 120.0) for i in range(1, 5)])
        max_cht_last = max([t_last.get(f"cht{i}", 120.0) for i in range(1, 5)])
        
        oil_p_first = float(t_first.get("oil_press", 4.2))
        oil_p_last = float(t_last.get("oil_press", 4.2))

        egt_spread_first = max([t_first.get(f"egt{i}", 750.0) for i in range(1, 5)]) - min([t_first.get(f"egt{i}", 750.0) for i in range(1, 5)])
        egt_spread_last = max([t_last.get(f"egt{i}", 750.0) for i in range(1, 5)]) - min([t_last.get(f"egt{i}", 750.0) for i in range(1, 5)])

        vib_first = float(t_first.get("vibration_rms", 1.12))
        vib_last = float(t_last.get("vibration_rms", 1.12))

        batt_first = float(t_first.get("battery_volt", 14.10))
        batt_last = float(t_last.get("battery_volt", 14.10))

        return {
            "d_cht": round((max_cht_last - max_cht_first) / dt, 2),
            "d_oil_p": round((oil_p_last - oil_p_first) / dt, 3),
            "d_egt_spread": round((egt_spread_last - egt_spread_first) / dt, 2),
            "d_vib": round((vib_last - vib_first) / dt, 3),
            "d_batt": round((batt_last - batt_first) / dt, 3)
        }

    def _extract_confidence(self, xgb_res: Dict[str, Any]) -> float:
        """Safely extract classification confidence as float in [0.0, 1.0] or None if NaN/inf/invalid."""
        if not xgb_res or not isinstance(xgb_res, dict):
            return None
        conf = xgb_res.get("confidence")
        if conf is None:
            conf = xgb_res.get("confidence_pct")
            if conf is not None:
                conf = conf / 100.0
        if conf is None:
            return None
        try:
            val = float(conf)
            if math.isnan(val) or math.isinf(val) or val < 0.0:
                return None
            if val > 1.0:
                val = val / 100.0
            return round(val, 3)
        except (ValueError, TypeError):
            return None

    def _build_structured_diagnostics(
        self,
        telemetry: Dict[str, Any],
        derivatives: Dict[str, Any],
        physics_state: Dict[str, Any],
        ae_res: Dict[str, Any],
        cusum_res: Dict[str, Any],
        xgb_res: Dict[str, Any],
        system_state: str,
        health_ema: Dict[str, float],
        timestamp: float
    ) -> List[Dict[str, Any]]:
        """
        Builds targeted, structured diagnostic output objects matching exact schema:
        event_id, timestamp, event_type, status, affected_subsystem, affected_component,
        observed_parameter, observed_value, threshold_or_expected_range, trend, anomaly_score,
        classifier_label, classifier_confidence, physics_residual, evidence_sources, advisory, priority.
        Differentiates PREDICTIVE_RISK vs ACTIVE_FAULT.
        """
        diagnostics = []
        conf = self._extract_confidence(xgb_res)
        anomaly_score = round(float(ae_res.get("anomaly_score", 0.0)), 3)
        fault_type = str(xgb_res.get("fault_type", "NONE"))

        cht_vals = [float(telemetry.get(f"cht{i}", 120.0)) for i in range(1, 5)]
        max_cht = max(cht_vals)
        max_cyl_idx = cht_vals.index(max_cht) + 1

        oil_press = float(telemetry.get("oil_press", 4.2))
        vib_rms = float(telemetry.get("vibration_rms", 1.12))
        batt_volt = float(telemetry.get("battery_volt", 14.10))

        # 1. CYLINDER HEAD OVERHEATING DIAGNOSTIC
        is_active_overheat = (max_cht >= 145.0) or (fault_type in ["Cylinder Head Overheating", "4"] and max_cht >= 140.0)
        is_predictive_overheat = not is_active_overheat and (
            (135.0 <= max_cht < 145.0) or
            (derivatives.get("d_cht", 0.0) > 0.5 and max_cht >= 128.0) or
            (fault_type in ["Cylinder Head Overheating", "4"] and max_cht < 140.0)
        )

        if is_active_overheat or is_predictive_overheat:
            status = "ACTIVE_FAULT" if is_active_overheat else "PREDICTIVE_RISK"
            priority = "Critical" if (is_active_overheat or system_state == "CRITICAL") else ("High" if is_predictive_overheat else "Medium")
            cht_residual = round(float(physics_state.get("residuals", {}).get("cht_delta", 0.0)), 2)
            diagnostics.append({
                "event_id": f"EVT_THERMAL_{int(timestamp)}",
                "timestamp": timestamp,
                "event_type": "CYLINDER_HEAD_OVERHEATING",
                "status": status,
                "affected_subsystem": "Thermal",
                "affected_component": f"Cylinder Head {max_cyl_idx} (CHT{max_cyl_idx})",
                "observed_parameter": f"CHT{max_cyl_idx}",
                "observed_value": round(max_cht, 1),
                "threshold_or_expected_range": "110.0 - 135.0 °C (Fault limit: > 145.0 °C)",
                "trend": f"{derivatives.get('d_cht', 0.0):+.2f} °C/s",
                "anomaly_score": anomaly_score,
                "classifier_label": "Cylinder Head Overheating",
                "classifier_confidence": conf,
                "physics_residual": cht_residual,
                "evidence_sources": [
                    f"Affected Cylinder: Cylinder {max_cyl_idx} (CHT{max_cyl_idx} = {max_cht:.1f}°C)",
                    "CHT Threshold / Expected Range: 110.0 - 135.0 °C (Fault limit: > 145.0 °C)",
                    f"Thermal Derivative d(CHT)/dt: {derivatives.get('d_cht', 0.0):+.2f} °C/s",
                    f"Physics Model CHT Residual: {cht_residual:+.1f} °C",
                    f"Deep Autoencoder Anomaly Score: {anomaly_score:.3f}"
                ],
                "advisory": "Inspect thermal subsystem and verify temperature-sensor validity.",
                "priority": priority
            })

        # 2. OIL PRESSURE DROP / LUBRICATION DEGRADATION
        is_active_oil = (oil_press <= 2.50) or (fault_type in ["Lubrication Failure / Low Oil Pressure", "3"] and oil_press <= 2.80)
        is_predictive_oil = not is_active_oil and (
            (2.50 < oil_press <= 3.20) or
            (derivatives.get("d_oil_p", 0.0) < -0.04 and oil_press <= 3.60) or
            (fault_type in ["Lubrication Failure / Low Oil Pressure", "3"] and oil_press > 2.80)
        )

        if is_active_oil or is_predictive_oil:
            status = "ACTIVE_FAULT" if is_active_oil else "PREDICTIVE_RISK"
            priority = "Critical" if (is_active_oil or system_state == "CRITICAL") else "High"
            oil_residual = round(float(physics_state.get("residuals", {}).get("oil_press_delta", 0.0)), 2)
            diagnostics.append({
                "event_id": f"EVT_LUBRICATION_{int(timestamp)}",
                "timestamp": timestamp,
                "event_type": "OIL_PRESSURE_DROP",
                "status": status,
                "affected_subsystem": "Lubrication",
                "affected_component": "Oil Pump / Sump Assembly",
                "observed_parameter": "Oil Pressure",
                "observed_value": round(oil_press, 2),
                "threshold_or_expected_range": "3.50 - 4.50 bar (Fault limit: < 2.50 bar)",
                "trend": f"{derivatives.get('d_oil_p', 0.0):+.3f} bar/s",
                "anomaly_score": anomaly_score,
                "classifier_label": "Lubrication Failure / Low Oil Pressure",
                "classifier_confidence": conf,
                "physics_residual": oil_residual,
                "evidence_sources": [
                    f"Observed Oil Pressure: {oil_press:.2f} bar",
                    "Expected Pressure Range: 3.50 - 4.50 bar (Fault limit: < 2.50 bar)",
                    f"Pressure Rate of Change d(OilPressure)/dt: {derivatives.get('d_oil_p', 0.0):+.3f} bar/s",
                    f"Lubrication Subsystem Health Index: {health_ema.get('lubrication', 100.0):.1f}%",
                    f"Physics Model Oil Pressure Residual: {oil_residual:+.2f} bar"
                ],
                "advisory": "Engineering inspection recommended for lubrication subsystem.",
                "priority": priority
            })

        # 3. ABNORMAL MECHANICAL VIBRATION
        is_active_vib = (vib_rms >= 2.50) or (fault_type in ["Abnormal Mechanical Vibration", "5"] and vib_rms >= 2.20)
        is_predictive_vib = not is_active_vib and (
            (1.50 <= vib_rms < 2.50) or
            (derivatives.get("d_vib", 0.0) > 0.04 and vib_rms >= 1.30) or
            (fault_type in ["Abnormal Mechanical Vibration", "5"] and vib_rms < 2.20)
        )

        if is_active_vib or is_predictive_vib:
            status = "ACTIVE_FAULT" if is_active_vib else "PREDICTIVE_RISK"
            priority = "Critical" if (is_active_vib or system_state == "CRITICAL") else "High"
            diagnostics.append({
                "event_id": f"EVT_MECHANICAL_{int(timestamp)}",
                "timestamp": timestamp,
                "event_type": "VIBRATION_ANOMALY",
                "status": status,
                "affected_subsystem": "Mechanical",
                "affected_component": "Crankshaft / Bearing Assembly",
                "observed_parameter": "Vibration RMS",
                "observed_value": round(vib_rms, 2),
                "threshold_or_expected_range": "0.50 - 1.50 g (Fault limit: > 2.50 g)",
                "trend": f"{derivatives.get('d_vib', 0.0):+.3f} g/s",
                "anomaly_score": anomaly_score,
                "classifier_label": "Abnormal Mechanical Vibration",
                "classifier_confidence": conf,
                "physics_residual": 0.0,
                "evidence_sources": [
                    f"Vibration RMS: {vib_rms:.2f} g",
                    "Nominal Limit: 1.50 g (Fault limit: > 2.50 g)",
                    f"Vibration Trend d(Vib)/dt: {derivatives.get('d_vib', 0.0):+.3f} g/s",
                    f"Mechanical Subsystem Health Index: {health_ema.get('mechanical', 100.0):.1f}%",
                    f"Deep Autoencoder Anomaly Score: {anomaly_score:.3f}"
                ],
                "advisory": "Monitor vibration trend and inspect mechanical subsystem during the next authorized maintenance opportunity.",
                "priority": priority
            })

        # 4. ELECTRICAL BUS VOLTAGE SENSOR DRIFT
        is_active_batt = (batt_volt <= 11.50 or batt_volt >= 15.50) or (fault_type in ["Electrical Bus Voltage Sensor Drift", "6"] and (batt_volt < 12.0 or batt_volt > 15.0))
        is_predictive_batt = not is_active_batt and (
            (11.50 < batt_volt <= 12.80) or
            (14.80 <= batt_volt < 15.50) or
            (abs(derivatives.get("d_batt", 0.0)) > 0.02 and abs(batt_volt - 14.10) > 0.6) or
            (fault_type in ["Electrical Bus Voltage Sensor Drift", "6"])
        )

        if is_active_batt or is_predictive_batt:
            status = "ACTIVE_FAULT" if is_active_batt else "PREDICTIVE_RISK"
            priority = "High" if is_active_batt else "Medium"
            batt_residual = round(abs(batt_volt - 14.10), 2)
            diagnostics.append({
                "event_id": f"EVT_ELECTRICAL_{int(timestamp)}",
                "timestamp": timestamp,
                "event_type": "SENSOR_DRIFT",
                "status": status,
                "affected_subsystem": "Electrical",
                "affected_component": "Electrical Bus / Voltage Sensor",
                "observed_parameter": "Battery Voltage",
                "observed_value": round(batt_volt, 2),
                "threshold_or_expected_range": "13.50 - 14.50 V (Nominal baseline: 14.10 V)",
                "trend": f"{derivatives.get('d_batt', 0.0):+.3f} V/s",
                "anomaly_score": anomaly_score,
                "classifier_label": "Electrical Bus Voltage Sensor Drift",
                "classifier_confidence": conf,
                "physics_residual": batt_residual,
                "evidence_sources": [
                    f"Observed Battery Voltage: {batt_volt:.2f} V",
                    "Expected Range: 13.50 - 14.50 V (Nominal baseline: 14.10 V)",
                    f"Voltage Sensor Drift Delta: {batt_residual:.2f} V",
                    f"Electrical Subsystem Health Index: {health_ema.get('electrical', 100.0):.1f}%",
                    f"Deep Autoencoder Anomaly Score: {anomaly_score:.3f}"
                ],
                "advisory": "Inspect electrical subsystem and verify voltage-sensor calibration.",
                "priority": priority
            })

        # 5. OTHER FAULT MODES (e.g. Cylinder Misfire, Fuel Injector Abnormality)
        if not diagnostics and fault_type not in ["NONE", "NOMINAL"]:
            status = "ACTIVE_FAULT" if system_state in ["WARNING", "CRITICAL"] else "PREDICTIVE_RISK"
            subsystem = str(xgb_res.get("subsystem", "General"))
            diagnostics.append({
                "event_id": f"EVT_GENERIC_{int(timestamp)}",
                "timestamp": timestamp,
                "event_type": fault_type.upper().replace(" ", "_"),
                "status": status,
                "affected_subsystem": subsystem,
                "affected_component": f"{subsystem} Subsystem Component",
                "observed_parameter": "Telemetry Anomaly Vector",
                "observed_value": round(anomaly_score, 3),
                "threshold_or_expected_range": "Nominal Baseline Vector",
                "trend": "Non-linear telemetry deviation",
                "anomaly_score": anomaly_score,
                "classifier_label": fault_type,
                "classifier_confidence": conf,
                "physics_residual": 0.0,
                "evidence_sources": [
                    f"Classifier Label: {fault_type}",
                    f"Subsystem: {subsystem}",
                    f"Deep Autoencoder Anomaly Score: {anomaly_score:.3f}",
                    f"CUSUM Change-point Alert: {cusum_res.get('cusum_alert_active', False)}"
                ],
                "advisory": f"Engineering inspection recommended for {subsystem.lower()} subsystem.",
                "priority": "High" if status == "ACTIVE_FAULT" else "Medium"
            })

        return diagnostics

    def _update_5state_machine(
        self,
        raw_score: float,
        cusum_active: bool,
        min_sub_hi: float,
        timestamp: float,
        predictive_assessments: Optional[List[Dict[str, Any]]] = None,
        physics_state: Optional[Dict[str, Any]] = None,
        telemetry: Optional[Dict[str, Any]] = None,
        gru_forecast_res: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Delegates state machine evaluation to PredictiveStateMachine:
        Multi-source evidence fusion, per-subsystem state tracking, persistence buffers,
        and progressive step-down hysteresis recovery.
        """
        telemetry = telemetry or {}
        predictive_assessments = predictive_assessments or []
        physics_state = physics_state or {}

        explanation = self.state_machine.evaluate_frame(
            telemetry=telemetry,
            health_ema=self.health_ema,
            predictive_assessments=predictive_assessments,
            physics_state=physics_state,
            ae_res={"anomaly_score": raw_score},
            cusum_res={"cusum_alert_active": cusum_active},
            gru_forecast_res=gru_forecast_res,
            timestamp=timestamp
        )

        self.current_system_state = explanation["new_state"]
        self.last_transition_metadata = explanation

        return explanation["new_state"], explanation["transition_reason"], explanation


    def process_telemetry_frame(self, frame_container: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes telemetry frame and generates an authoritative atomic snapshot.
        All metrics inside the returned snapshot belong strictly to the SAME processing frame.
        """
        dt_start = time.perf_counter()
        telemetry = frame_container.get("telemetry", frame_container)
        raw_telemetry = frame_container.get("raw_telemetry", telemetry)
        
        # Canonical Telemetry Ingestion Instrumentation Point
        metrics_tracker_instance.record_frame_ingestion(raw_telemetry)

        mission_profile = frame_container.get("mission_profile", "CRUISE")
        telemetry_source = frame_container.get("telemetry_source", "SIMULATOR")
        analytics_dataset = frame_container.get("analytics_dataset", "CMAPSS")
        timestamp = float(telemetry.get("timestamp", 0.0))

        telemetry_source_label = "Reference Aero-Piston Physics Simulator" if telemetry_source == "SIMULATOR" else "Historical Aero-Piston Replay Log"

        dataset_labels = {
            "CMAPSS": "NASA C-MAPSS FD001 Dataset (Turbofan Run-to-Failure)",
            "ALFA": "ALFA Autonomous UAV Flight Dataset",
            "RFLYMAD": "RflyMAD Multi-Sensor UAV Health Dataset",
            "UAVFD": "UAV-FD Actuator Fault Dataset"
        }
        analytics_dataset_label = dataset_labels.get(analytics_dataset, "NASA C-MAPSS FD001 Dataset")

        signal_provenance = {
            "primary_telemetry": {
                "source_type": "SIMULATED" if telemetry_source == "SIMULATOR" else "HISTORICAL",
                "source_dataset": telemetry_source_label,
                "source_feature": "Canonical Aero-Piston Telemetry Stream (10Hz)",
                "transformation": "3-Sample Median Filter + EMA Display Smoothing (alpha=0.25)",
                "timestamp": timestamp
            },
            "analytics_dataset": {
                "source_type": "ANALOGUE",
                "source_dataset": analytics_dataset_label,
                "source_feature": "Prognostics / Fault Training Feature Matrix",
                "transformation": "PyTorch / XGBoost Model Feature Extraction",
                "timestamp": timestamp
            },
            "cht1": {
                "source_type": "SIMULATED" if telemetry_source == "SIMULATOR" else "HISTORICAL",
                "source_dataset": telemetry_source_label,
                "source_feature": "Cylinder Head Temp 1",
                "transformation": "3-Sample Median Filter + EMA Smoothing",
                "timestamp": timestamp
            },
            "oil_press": {
                "source_type": "SIMULATED" if telemetry_source == "SIMULATOR" else "HISTORICAL",
                "source_dataset": telemetry_source_label,
                "source_feature": "Engine Lubrication Pressure",
                "transformation": "3-Sample Median Filter + EMA Smoothing",
                "timestamp": timestamp
            },
            "vibration_rms": {
                "source_type": "SIMULATED" if telemetry_source == "SIMULATOR" else "HISTORICAL",
                "source_dataset": telemetry_source_label,
                "source_feature": "Crankshaft Mechanical Vibration RMS",
                "transformation": "3-Sample Median Filter + EMA Smoothing",
                "timestamp": timestamp
            },
            "rul": {
                "source_type": "ANALOGUE",
                "source_dataset": analytics_dataset_label,
                "source_feature": "Turbofan Engine Degradation Curves",
                "transformation": "PyTorch LSTM Sequence Model",
                "timestamp": timestamp
            }
        }

        # 1. Store frame in history for derivative calculation and GRU forecasting
        seq_val = (
            frame_container.get("sequence_number") or
            frame_container.get("sequence_no") or
            telemetry.get("sequence_no") or
            telemetry.get("sequence_number") or
            raw_telemetry.get("sequence_no") or
            raw_telemetry.get("sequence_number")
        )
        if seq_val is not None:
            self.predictive_engine.sequence_number = int(seq_val)
        else:
            self.predictive_engine.sequence_number += 1

        self.history_window.append(telemetry)
        self.history_window_full.append(telemetry)
        derivatives = self._compute_derivatives()

        # 2. Compute Physics Model Baseline & Residuals for THIS frame
        t_phys_0 = time.perf_counter()
        physics_state = self.pinn_physics.predict_expected_state(telemetry, mission_profile=mission_profile)
        t_phys_1 = time.perf_counter()
        metrics_tracker_instance.record_physics_latency((t_phys_1 - t_phys_0) * 1000.0)

        curr_seq = self.predictive_engine.sequence_number

        # 3. CUSUM Change-Point Detector (10 Hz — Light / Fast)
        t_cusum_0 = time.perf_counter()
        cusum_res = self.cusum.update(telemetry)
        t_cusum_1 = time.perf_counter()
        metrics_tracker_instance.record_cusum_latency((t_cusum_1 - t_cusum_0) * 1000.0)

        # 4. PyTorch Autoencoder Anomaly Detector (2 Hz — Every 5 frames / 500 ms)
        if self._cached_ae_res is None or curr_seq % 5 == 0:
            t_ae_0 = time.perf_counter()
            self._cached_ae_res = self.autoencoder.predict_anomaly(telemetry)
            t_ae_1 = time.perf_counter()
            metrics_tracker_instance.record_autoencoder_latency((t_ae_1 - t_ae_0) * 1000.0)
            self._ae_last_seq = curr_seq

        ae_res = self._cached_ae_res.copy() if isinstance(self._cached_ae_res, dict) else {"anomaly_score": 0.0, "is_anomaly": False}
        ae_res["inference_frame_seq"] = self._ae_last_seq
        ae_res["inference_age_sec"] = round(max(0.0, (curr_seq - self._ae_last_seq) * 0.1), 2)

        # 5. XGBoost Fault Classifier (2 Hz — Every 5 frames / 500 ms)
        if self._cached_xgb_res is None or curr_seq % 5 == 0:
            self._cached_xgb_res = self.xgboost.predict_fault(telemetry)
            self._xgb_last_seq = curr_seq

        xgb_res = self._cached_xgb_res.copy() if isinstance(self._cached_xgb_res, dict) else {"fault_type": "NONE", "confidence": 0.99}
        xgb_res["inference_frame_seq"] = self._xgb_last_seq
        xgb_res["inference_age_sec"] = round(max(0.0, (curr_seq - self._xgb_last_seq) * 0.1), 2)

        # 6. PyTorch LSTM RUL Estimator (0.2 Hz — Every 50 frames / 5.0 s while maintaining full sequence history)
        if self._cached_rul_output is None or curr_seq % 50 == 0:
            t_rul_0 = time.perf_counter()
            self._cached_rul_output = self.lstm_rul.update_and_predict(telemetry)
            t_rul_1 = time.perf_counter()
            metrics_tracker_instance.record_rul_latency((t_rul_1 - t_rul_0) * 1000.0)
            self._rul_last_seq = curr_seq
        else:
            self.lstm_rul.update_history_only(telemetry)

        rul_output = self._cached_rul_output.copy() if isinstance(self._cached_rul_output, dict) else {"display_prediction_cycles": 210.0}
        rul_output["inference_frame_seq"] = self._rul_last_seq
        rul_output["inference_age_sec"] = round(max(0.0, (curr_seq - self._rul_last_seq) * 0.1), 2)

        # 7. PyTorch GRU Short-Horizon Forecaster (1 Hz — Every 10 frames / 1.0 s)
        if self._cached_gru_res is None or curr_seq % 10 == 0:
            t_gru_0 = time.perf_counter()
            self._cached_gru_res = self.gru_service.predict_forecast(
                telemetry_history=list(self.history_window_full),
                timestamp=timestamp,
                sequence_number=curr_seq,
                scenario=mission_profile
            )
            t_gru_1 = time.perf_counter()
            gru_status = self._cached_gru_res.get("status", "READY") if self._cached_gru_res else "WARMING_UP"
            metrics_tracker_instance.record_gru_latency((t_gru_1 - t_gru_0) * 1000.0, status=gru_status)
            self._gru_last_seq = curr_seq

        gru_forecast_res = self._cached_gru_res
        self.latest_forecast = gru_forecast_res
        if gru_forecast_res:
            self.forecast_history.append(gru_forecast_res)

        t_pred_0 = time.perf_counter()
        predictive_assessments = self.predictive_engine.process_frame(telemetry, physics_state, ae_res, cusum_res, gru_forecast_res)
        t_pred_1 = time.perf_counter()
        metrics_tracker_instance.record_predictive_health_latency((t_pred_1 - t_pred_0) * 1000.0, len(predictive_assessments))

        # Store latest primary/worst assessment and append to history buffer
        status_rank = {"ACTIVE_FAULT": 4, "PREDICTIVE_RISK": 3, "DEGRADATION_DETECTED": 2, "NOMINAL": 1}
        worst_ass = max(predictive_assessments, key=lambda a: (
            status_rank.get(a.get("status", "NOMINAL"), 0),
            a.get("degradation_score", 0.0)
        )) if predictive_assessments else None

        self.latest_predictive_assessment = worst_ass
        if worst_ass:
            if worst_ass.get("status") == "NOMINAL":
                worst_ass = worst_ass.copy()
                worst_ass["affected_subsystem"] = "NONE"
                worst_ass["affected_component"] = "NONE"
                worst_ass["predicted_failure_mode"] = "NONE"
                worst_ass["primary_parameter"] = "NONE"
            self.predictive_history.append(worst_ass)

        # Multi-Subsystem Evidence Fusion
        subsystem_map = {a.get("subsystem", "").lower(): a for a in predictive_assessments}
        subsystem_evidence = {}
        for sub_name in ["thermal", "lubrication", "mechanical", "combustion", "electrical"]:
            ass_obj = subsystem_map.get(sub_name, {})
            subsystem_evidence[sub_name] = {
                "subsystem": sub_name.upper(),
                "state": ass_obj.get("predictive_status", self.state_machine.subsystem_states.get(sub_name, "NOMINAL")),
                "risk": ass_obj.get("predictive_risk_score", 0.05),
                "degradation_score": ass_obj.get("degradation_score", 0.0),
                "component": ass_obj.get("affected_component", "Subsystem Normal"),
                "parameter": ass_obj.get("primary_parameter_label", "Signal"),
                "current_value": ass_obj.get("current_value"),
                "evidence": ass_obj.get("evidence_sources", [])
            }

        state_severity_rank = {
            "CRITICAL": 5, "ACTIVE_FAULT": 4, "WARNING": 4,
            "PREDICTIVE_RISK": 3, "CAUTION": 3,
            "DEGRADATION_DETECTED": 2, "WATCH": 2,
            "NOMINAL": 1, "NORMAL": 1
        }

        sorted_subsystems = sorted(
            subsystem_evidence.items(),
            key=lambda item: (
                state_severity_rank.get(item[1]["state"], 1),
                item[1]["degradation_score"]
            ),
            reverse=True
        )

        dominant_key, dominant_data = sorted_subsystems[0]
        dominant_subsystem = dominant_data["subsystem"]
        dominant_component = dominant_data["component"]

        secondary_degradations = [
            data["subsystem"] for sub_key, data in sorted_subsystems[1:]
            if state_severity_rank.get(data["state"], 1) > 1
        ]

        # Injected Faults (Simulator Ground Truth) vs Detected Conditions (AI Evidence Fusion)
        injected_faults = list(getattr(simulator_instance, "active_faults", []))
        detected_conditions = [
            {
                "subsystem": data["subsystem"],
                "component": data["component"],
                "state": data["state"],
                "risk": data["risk"]
            }
            for sub_key, data in sorted_subsystems if state_severity_rank.get(data["state"], 1) > 1
        ]

        # 6. Compute Subsystem Health Indices & EMA Smoothing for THIS frame
        cht_vals = [float(telemetry.get(f"cht{i}", 120.0)) for i in range(1, 5)]
        egt_vals = [float(telemetry.get(f"egt{i}", 750.0)) for i in range(1, 5)]
        oil_press = float(telemetry.get("oil_press", 4.2))
        oil_temp = float(telemetry.get("oil_temp", 88.5))
        vib_rms = float(telemetry.get("vibration_rms", 1.12))
        batt_volt = float(telemetry.get("battery_volt", 14.10))

        raw_thermal = max(0.0, min(100.0, 100.0 - (max(0.0, max(cht_vals) - 140.0) / 25.0) * 60.0))
        raw_lubrication = max(0.0, min(100.0, 100.0 - (max(0.0, physics_state["expected_oil_press"] - oil_press) / 2.5) * 70.0))
        raw_combustion = max(0.0, min(100.0, 100.0 - (max(0.0, max(egt_vals) - min(egt_vals) - 25.0) / 80.0) * 70.0))
        raw_electrical = max(0.0, min(100.0, 100.0 - (abs(batt_volt - 14.10) / 2.2) * 85.0))
        raw_mechanical = max(0.0, min(100.0, 100.0 - (max(0.0, vib_rms - 1.5) / 3.0) * 100.0))

        alpha = 0.20
        self.health_ema["thermal"] = round(alpha * raw_thermal + (1 - alpha) * self.health_ema["thermal"], 1)
        self.health_ema["lubrication"] = round(alpha * raw_lubrication + (1 - alpha) * self.health_ema["lubrication"], 1)
        self.health_ema["combustion"] = round(alpha * raw_combustion + (1 - alpha) * self.health_ema["combustion"], 1)
        self.health_ema["electrical"] = round(alpha * raw_electrical + (1 - alpha) * self.health_ema["electrical"], 1)
        self.health_ema["mechanical"] = round(alpha * raw_mechanical + (1 - alpha) * self.health_ema["mechanical"], 1)

        weights = {"thermal": 0.25, "lubrication": 0.25, "combustion": 0.25, "electrical": 0.10, "mechanical": 0.15}
        weighted_hi = sum(self.health_ema[k] * weights[k] for k in weights)
        self.health_ema["overall"] = round(weighted_hi, 1)

        min_sub_hi = min(self.health_ema[k] for k in ["thermal", "lubrication", "combustion", "electrical", "mechanical"])

        # 7. Update 5-State Machine with Multi-Source Predictive Evidence Integration & Hysteresis
        t_sm_0 = time.perf_counter()
        system_state, state_reason, transition_metadata = self._update_5state_machine(
            ae_res["anomaly_score"],
            cusum_res["cusum_alert_active"],
            min_sub_hi,
            timestamp,
            predictive_assessments,
            physics_state,
            telemetry,
            gru_forecast_res
        )
        t_sm_1 = time.perf_counter()
        metrics_tracker_instance.record_state_machine_latency((t_sm_1 - t_sm_0) * 1000.0)

        # Update predictive lead time tracker
        is_active_fault_confirmed = any(d.get("status") == "ACTIVE_FAULT" for d in structured_diagnostics) if 'structured_diagnostics' in locals() else False
        metrics_tracker_instance.update_predictive_lead_time_tracker(system_state, timestamp, is_active_fault_confirmed)



        # 8. Physics Residuals Table for THIS frame (Residual = Observed - Physics Prediction)
        rpm_val = float(telemetry.get("rpm", 5000.0))
        map_val = float(telemetry.get("map", 1.15))
        derived_power = round((map_val * 100.0 * 0.001211 * (rpm_val / 120.0)) * 0.88 * 0.34, 1)

        avg_cht_obs = round(float(np.mean(cht_vals)), 1)
        avg_egt_obs = round(float(np.mean(egt_vals)), 1)

        pow_res = round(derived_power - physics_state["expected_power_kw"], 1)
        cht_res = physics_state["residuals"]["cht_delta"]
        egt_res = physics_state["residuals"]["egt_delta"]
        oil_p_res = physics_state["residuals"]["oil_press_delta"]
        oil_t_res = physics_state["residuals"]["oil_temp_delta"]

        def get_res_status(res_val, watch_thresh, abn_thresh):
            abs_val = abs(res_val)
            if abs_val >= abn_thresh:
                return "ABNORMAL"
            if abs_val >= watch_thresh:
                return "WATCH"
            return "NORMAL"

        residuals_table = {
            "power_kw": {
                "parameter": "Power (kW)",
                "observed": derived_power,
                "observed_value": derived_power,
                "observed_type": "Telemetry-Derived Estimate",
                "expected": physics_state["expected_power_kw"],
                "predicted_value": physics_state["expected_power_kw"],
                "residual": pow_res,
                "normal_band": "± 5.0 kW",
                "reference_band": "± 5.0 kW",
                "status": get_res_status(pow_res, 5.0, 7.5),
                "residual_status": get_res_status(pow_res, 5.0, 7.5),
                "timestamp": timestamp,
                "unit": "kW"
            },
            "avg_cht": {
                "parameter": "Avg CHT (°C)",
                "observed": avg_cht_obs,
                "observed_value": avg_cht_obs,
                "observed_type": "Direct Telemetry",
                "expected": physics_state["expected_cht"],
                "predicted_value": physics_state["expected_cht"],
                "residual": cht_res,
                "normal_band": "± 8.0 °C",
                "reference_band": "± 8.0 °C",
                "status": get_res_status(cht_res, 8.0, 12.0),
                "residual_status": get_res_status(cht_res, 8.0, 12.0),
                "timestamp": timestamp,
                "unit": "°C"
            },
            "avg_egt": {
                "parameter": "Avg EGT (°C)",
                "observed": avg_egt_obs,
                "observed_value": avg_egt_obs,
                "observed_type": "Direct Telemetry",
                "expected": physics_state["expected_egt"],
                "predicted_value": physics_state["expected_egt"],
                "residual": egt_res,
                "normal_band": "± 25.0 °C",
                "reference_band": "± 25.0 °C",
                "status": get_res_status(egt_res, 25.0, 40.0),
                "residual_status": get_res_status(egt_res, 25.0, 40.0),
                "timestamp": timestamp,
                "unit": "°C"
            },
            "oil_press": {
                "parameter": "Oil Pressure (bar)",
                "observed": round(oil_press, 2),
                "observed_value": round(oil_press, 2),
                "observed_type": "Direct Telemetry",
                "expected": physics_state["expected_oil_press"],
                "predicted_value": physics_state["expected_oil_press"],
                "residual": oil_p_res,
                "normal_band": "± 0.40 bar",
                "reference_band": "± 0.40 bar",
                "status": get_res_status(oil_p_res, 0.40, 0.60),
                "residual_status": get_res_status(oil_p_res, 0.40, 0.60),
                "timestamp": timestamp,
                "unit": "bar"
            },
            "oil_temp": {
                "parameter": "Oil Temperature (°C)",
                "observed": round(oil_temp, 1),
                "observed_value": round(oil_temp, 1),
                "observed_type": "Direct Telemetry",
                "expected": physics_state["expected_oil_temp"],
                "predicted_value": physics_state["expected_oil_temp"],
                "residual": oil_t_res,
                "normal_band": "± 5.0 °C",
                "reference_band": "± 5.0 °C",
                "status": get_res_status(oil_t_res, 5.0, 8.0),
                "residual_status": get_res_status(oil_t_res, 5.0, 8.0),
                "timestamp": timestamp,
                "unit": "°C"
            }
        }

        # 9. Health Explanation Formula
        health_explanation = (
            f"Overall HI ({self.health_ema['overall']}%) = Thermal ({self.health_ema['thermal']}% × 25%) + "
            f"Lubrication ({self.health_ema['lubrication']}% × 25%) + Combustion ({self.health_ema['combustion']}% × 25%) + "
            f"Electrical ({self.health_ema['electrical']}% × 10%) + Mechanical ({self.health_ema['mechanical']}% × 15%)."
        )

        # 10. Build Structured Targeted Diagnostics & Decision-Support Maintenance Advisories
        structured_diagnostics = self._build_structured_diagnostics(
            telemetry=telemetry,
            derivatives=derivatives,
            physics_state=physics_state,
            ae_res=ae_res,
            cusum_res=cusum_res,
            xgb_res=xgb_res,
            system_state=system_state,
            health_ema=self.health_ema,
            timestamp=timestamp
        )

        # Fallback: Guarantee structured_diagnostics is never empty when system_state or detected_conditions is non-nominal
        if not structured_diagnostics and (system_state != "NORMAL" or detected_conditions):
            for cond in detected_conditions:
                structured_diagnostics.append({
                    "event_id": f"EVT_{cond['subsystem']}_{int(timestamp)}",
                    "timestamp": timestamp,
                    "event_type": f"{cond['subsystem']}_DEGRADATION",
                    "status": "ACTIVE_FAULT" if system_state in ["WARNING", "CRITICAL"] else "PREDICTIVE_RISK",
                    "affected_subsystem": cond["subsystem"].title(),
                    "affected_component": cond["component"],
                    "observed_parameter": f"{cond['subsystem']} Metric",
                    "observed_value": round(cond.get("risk", 0.5), 2),
                    "threshold_or_expected_range": "Nominal Baseline Envelope",
                    "trend": "Degradation trend active",
                    "anomaly_score": ae_res["anomaly_score"],
                    "classifier_label": f"{cond['subsystem'].title()} Degradation",
                    "classifier_confidence": 0.90,
                    "physics_residual": 0.0,
                    "evidence_sources": [
                        f"Subsystem: {cond['subsystem']}",
                        f"Affected Component: {cond['component']}",
                        f"State: {cond['state']}",
                        f"Risk Score: {cond.get('risk', 0.5)}"
                    ],
                    "advisory": f"Engineering inspection recommended for {cond['subsystem'].lower()} subsystem.",
                    "priority": "Critical" if system_state == "CRITICAL" else "High"
                })

        # Explicit Parameter Statuses for all Gauges and Cards
        def get_p_status_high(v, w, c, f):
            if v >= f: return "CRITICAL"
            if v >= c: return "WARNING"
            if v >= w: return "WATCH"
            return "NORMAL"

        def get_p_status_low(v, w, c, f):
            if v <= f: return "CRITICAL"
            if v <= c: return "WARNING"
            if v <= w: return "WATCH"
            return "NORMAL"

        parameter_statuses = {
            "rpm": {"value": rpm_val, "status": get_p_status_high(rpm_val, 5500.0, 5700.0, 5800.0), "unit": "RPM", "envelope": "4000 - 5600 RPM"},
            "oil_press": {"value": round(oil_press, 2), "status": get_p_status_low(oil_press, 3.50, 2.80, 2.50), "unit": "bar", "envelope": "3.50 - 6.00 bar"},
            "oil_temp": {"value": round(oil_temp, 1), "status": get_p_status_high(oil_temp, 105.0, 115.0, 125.0), "unit": "°C", "envelope": "70.0 - 105.0 °C"},
            "vibration_rms": {"value": round(vib_rms, 2), "status": get_p_status_high(vib_rms, 1.50, 2.00, 2.50), "unit": "g", "envelope": "0.00 - 1.50 g"},
            "battery_volt": {"value": round(batt_volt, 2), "status": ("CRITICAL" if batt_volt <= 11.50 or batt_volt >= 15.50 else ("WARNING" if batt_volt <= 12.0 or batt_volt >= 15.0 else ("WATCH" if batt_volt < 12.8 or batt_volt > 14.8 else "NORMAL"))), "unit": "V", "envelope": "12.80 - 14.80 V"},
            "fuel_flow": {"value": round(float(telemetry.get("fuel_flow", 17.5)), 2), "status": get_p_status_high(float(telemetry.get("fuel_flow", 17.5)), 22.0, 25.0, 28.0), "unit": "L/hr", "envelope": "10.0 - 22.0 L/hr"},
            "cht1": {"value": round(cht_vals[0], 1), "status": get_p_status_high(cht_vals[0], 128.0, 135.0, 145.0), "unit": "°C", "envelope": "110.0 - 145.0 °C"},
            "cht2": {"value": round(cht_vals[1], 1), "status": get_p_status_high(cht_vals[1], 128.0, 135.0, 145.0), "unit": "°C", "envelope": "110.0 - 145.0 °C"},
            "cht3": {"value": round(cht_vals[2], 1), "status": get_p_status_high(cht_vals[2], 128.0, 135.0, 145.0), "unit": "°C", "envelope": "110.0 - 145.0 °C"},
            "cht4": {"value": round(cht_vals[3], 1), "status": get_p_status_high(cht_vals[3], 128.0, 135.0, 145.0), "unit": "°C", "envelope": "110.0 - 145.0 °C"},
            "egt1": {"value": round(egt_vals[0], 1), "status": get_p_status_high(egt_vals[0], 775.0, 800.0, 850.0), "unit": "°C", "envelope": "650.0 - 800.0 °C"},
            "egt2": {"value": round(egt_vals[1], 1), "status": get_p_status_high(egt_vals[1], 775.0, 800.0, 850.0), "unit": "°C", "envelope": "650.0 - 800.0 °C"},
            "egt3": {"value": round(egt_vals[2], 1), "status": get_p_status_high(egt_vals[2], 775.0, 800.0, 850.0), "unit": "°C", "envelope": "650.0 - 800.0 °C"},
            "egt4": {"value": round(egt_vals[3], 1), "status": get_p_status_high(egt_vals[3], 775.0, 800.0, 850.0), "unit": "°C", "envelope": "650.0 - 800.0 °C"},
            "egt_spread": {"value": round(max(egt_vals) - min(egt_vals), 1), "status": get_p_status_high(max(egt_vals) - min(egt_vals), 45.0, 65.0, 90.0), "unit": "°C", "envelope": "0.0 - 45.0 °C"}
        }

        detected_primary_condition = {
            "subsystem": dominant_subsystem,
            "component": dominant_component,
            "state": dominant_data["state"],
            "risk": dominant_data["risk"],
            "evidence": dominant_data.get("evidence", [])
        }
        secondary_detected_conditions = [
            {
                "subsystem": data["subsystem"],
                "component": data["component"],
                "state": data["state"],
                "risk": data["risk"],
                "evidence": data.get("evidence", [])
            }
            for sub_key, data in sorted_subsystems[1:] if state_severity_rank.get(data["state"], 1) > 1
        ]
        injected_condition = injected_faults[0] if injected_faults else {"status": "NONE", "fault_type": "NONE", "scenario": "NONE"}

        maintenance_advisories = []
        if structured_diagnostics:
            for diag in structured_diagnostics:
                maintenance_advisories.append(f"{diag['advisory']} (Priority: {diag['priority']})")
        elif system_state in ["CRITICAL", "WARNING"]:
            if self.health_ema["lubrication"] < 75.0:
                maintenance_advisories.append("Engineering inspection recommended for lubrication subsystem. Priority: High.")
            if self.health_ema["thermal"] < 75.0:
                maintenance_advisories.append("Inspect thermal subsystem and verify temperature-sensor validity. Priority: High.")
            if self.health_ema["combustion"] < 75.0:
                maintenance_advisories.append("Engineering inspection recommended for combustion subsystem. Priority: High.")
            if self.health_ema["mechanical"] < 75.0:
                maintenance_advisories.append("Monitor vibration trend and inspect mechanical subsystem during next authorized opportunity. Priority: High.")
            if self.health_ema["electrical"] < 75.0:
                maintenance_advisories.append("Inspect electrical subsystem and verify voltage-sensor calibration. Priority: Medium.")
        elif system_state in ["CAUTION", "WATCH"]:
            maintenance_advisories.append("Minor telemetry parameter variation detected. Continuous monitoring recommended. Priority: Low.")
        else:
            maintenance_advisories.append("Propulsion system operating within nominal parameters. Scheduled maintenance interval intact. Priority: Normal.")

        active_events = []
        if system_state != "NORMAL":
            active_events.append({
                "type": f"SYSTEM_STATE_{system_state}",
                "severity": system_state,
                "timestamp": timestamp,
                "description": state_reason
            })

        if structured_diagnostics:
            alert_latency_ms = (time.perf_counter() - dt_start) * 1000.0
            metrics_tracker_instance.record_alert_latency(alert_latency_ms)

        dt_end = time.perf_counter()
        metrics_tracker_instance.record_dt_latency((dt_end - dt_start) * 1000.0)

        runtime_metrics = metrics_tracker_instance.get_summary()

        # 10. DFCS Advisory States matching requirement P, Q, R, T and Authoritative 5-State Machine
        predictive_risk_val = worst_ass.get("degradation_score", 0.0) if worst_ass else 0.0
        primary_diag = structured_diagnostics[0] if structured_diagnostics else None
        primary_diag_label = primary_diag["classifier_label"] if primary_diag else "Nominal"

        active_diag_count = len(structured_diagnostics)
        comp_str = f"{dominant_subsystem} ({dominant_component})" if (dominant_subsystem != "NONE" and dominant_component != "NONE") else (dominant_subsystem if dominant_subsystem != "NONE" else "")

        if system_state == "CRITICAL":
            gcs_dfcs_advisory = {
                "level": "CRITICAL",
                "title": "Critical Propulsion Advisory",
                "description": f"Confirmed safety-envelope violation or critical subsystem condition detected in {comp_str}." if comp_str else "Confirmed safety-envelope violation or critical subsystem condition detected.",
                "operator_action": "Reduce propulsion demand where operationally appropriate and perform immediate operator/engineering assessment.",
                "demand_recommendation": "MINIMUM SAFE / EMERGENCY",
                "dominant_subsystem": dominant_subsystem,
                "dominant_component": dominant_component,
                "active_diagnostic_count": active_diag_count,
                "is_predictive_escalation": False
            }
        elif system_state == "WARNING":
            gcs_dfcs_advisory = {
                "level": "WARNING",
                "title": "Reduced Demand Advisory",
                "description": f"Significant propulsion degradation detected in {comp_str}." if comp_str else "Significant propulsion degradation detected.",
                "operator_action": "Reduce propulsion demand where operationally appropriate and perform operator assessment.",
                "demand_recommendation": "REDUCED",
                "dominant_subsystem": dominant_subsystem,
                "dominant_component": dominant_component,
                "active_diagnostic_count": active_diag_count,
                "is_predictive_escalation": False
            }
        elif system_state == "CAUTION":
            gcs_dfcs_advisory = {
                "level": "CAUTION",
                "title": "Operational Caution Advisory",
                "description": f"Persistent degradation evidence detected in {comp_str}." if comp_str else "Persistent degradation evidence detected.",
                "operator_action": "Prepare for flight envelope adjustment if trend continues.",
                "demand_recommendation": "CONSERVATIVE",
                "dominant_subsystem": dominant_subsystem,
                "dominant_component": dominant_component,
                "active_diagnostic_count": active_diag_count,
                "is_predictive_escalation": False
            }
        elif system_state == "WATCH":
            gcs_dfcs_advisory = {
                "level": "WATCH",
                "title": "Enhanced Monitoring Advisory",
                "description": f"Early diagnostic evidence detected in {comp_str}. Continue enhanced monitoring." if comp_str else "Early diagnostic evidence detected. Continue enhanced monitoring.",
                "operator_action": "Monitor trend indicators.",
                "demand_recommendation": "MONITOR",
                "dominant_subsystem": dominant_subsystem,
                "dominant_component": dominant_component,
                "active_diagnostic_count": active_diag_count,
                "is_predictive_escalation": False
            }
        else:
            gcs_dfcs_advisory = {
                "level": "NORMAL",
                "title": "Nominal System Monitoring",
                "description": "All monitored propulsion parameters are within nominal reference envelopes.",
                "operator_action": "Maintain standard flight profile.",
                "demand_recommendation": "NOMINAL",
                "dominant_subsystem": "NONE",
                "dominant_component": "NONE",
                "active_diagnostic_count": 0,
                "is_predictive_escalation": False
            }


        # 11. Authoritative Canonical Atomic Snapshot Object
        return {
            "session_id": "TWIN_SESSION_SIH26054",
            "sequence_number": self.predictive_engine.sequence_number,
            "timestamp": timestamp,
            "scenario": {
                "id": mission_profile,
                "altitude_m": physics_state.get("altitude_m", 1500.0),
                "ambient_temp_c": physics_state.get("ambient_temp_c", 15.0),
                "throttle_pct": physics_state.get("throttle_pct", 75.0),
                "engine_load_pct": physics_state.get("engine_load_pct", 70.0)
            },
            "scenario_id": mission_profile,
            "mission_profile": mission_profile,
            "global_state": system_state,
            "system_state": system_state,
            "dominant_subsystem": dominant_subsystem,
            "dominant_component": dominant_component,
            "dominant_evidence": dominant_data.get("evidence", []),
            "secondary_degradations": secondary_degradations,
            "subsystem_evidence": subsystem_evidence,
            "injected_faults": injected_faults,
            "injected_condition": injected_condition,
            "detected_conditions": detected_conditions,
            "detected_primary_condition": detected_primary_condition,
            "secondary_detected_conditions": secondary_detected_conditions,
            "parameter_statuses": parameter_statuses,
            "provenance_notes": {
                "xgboost": "XGBoost: Single-Class Classification Evidence",
                "evidence_fusion": "Evidence Fusion: Multi-Subsystem Multi-Fault Diagnosis"
            },
            "scenario_parameters": {
                "altitude_m": physics_state.get("altitude_m", 1500.0),
                "ambient_temp_c": physics_state.get("ambient_temp_c", 15.0),
                "ambient_press_bar": physics_state.get("ambient_press_bar", 0.85),
                "throttle_pct": physics_state.get("throttle_pct", 75.0),
                "engine_load_pct": physics_state.get("engine_load_pct", 70.0)
            },
            "telemetry": telemetry,
            "raw_telemetry": raw_telemetry,
            "physics_expected": physics_state,
            "residuals": physics_state["residuals"],
            "subsystem_health": self.health_ema,
            "overall_health": self.health_ema["overall"],
            "overall_health_index": self.health_ema["overall"],
            "health": {
                "overall": self.health_ema["overall"],
                "thermal": self.health_ema["thermal"],
                "lubrication": self.health_ema["lubrication"],
                "combustion": self.health_ema["combustion"],
                "mechanical": self.health_ema["mechanical"],
                "electrical": self.health_ema["electrical"]
            },
            "health_explanation": health_explanation,
            "anomaly": {
                "score": ae_res["anomaly_score"],
                "raw_score": ae_res["anomaly_score"],
                "autoencoder_score": ae_res["anomaly_score"],
                "classifier_label": primary_diag_label,
                "classifier_confidence": xgb_res.get("confidence", 0.95),
                "trend": "STABLE" if ae_res["anomaly_score"] < 0.2 else "ELEVATED",
                "predictive_risk": predictive_risk_val,
                "cusum_active": cusum_res["cusum_alert_active"],
                "autoencoder": ae_res,
                "cusum": cusum_res
            },
            "anomaly_score": ae_res["anomaly_score"],
            "inference_frame_seq": ae_res.get("inference_frame_seq", self.predictive_engine.sequence_number),
            "inference_age_sec": ae_res.get("inference_age_sec", 0.0),
            "fault_evidence": {
                "xgboost": xgb_res,
                "active_faults": injected_faults
            },
            "physics_residuals": physics_state["residuals"],
            "residuals_table": residuals_table,
            "predictive_risk": predictive_risk_val,
            "rul": rul_output,
            "prototype_rul_estimate": rul_output,
            "state_reason": state_reason,
            "state_reasoning": transition_metadata.get("transition_reason", state_reason),
            "state_machine": {
                "previous_state": transition_metadata.get("previous_state", "NORMAL"),
                "current_state": system_state,
                "transition_reason": transition_metadata.get("transition_reason", state_reason),
                "last_transition_time": transition_metadata.get("timestamp", 0.0)
            },
            "active_events": active_events,
            "active_faults": injected_faults,
            "active_injections": injected_faults,
            "fault_event_log": frame_container.get("fault_event_log", []),
            "fault_injection": {
                "active_count": len(injected_faults),
                "active_injections": injected_faults,
                "history": frame_container.get("fault_event_log", [])
            },
            "predictive_diagnostics": structured_diagnostics,
            "predictive_health_assessments": predictive_assessments,
            "latest_predictive_assessment": worst_ass,
            "predictive_assessment": worst_ass,
            "predictive_history": list(self.predictive_history)[-10:],
            "latest_forecast": gru_forecast_res,
            "forecast": gru_forecast_res,
            "forecast_history": list(self.forecast_history)[-10:],
            "forecast_mode": gru_forecast_res.get("forecast_mode", "STATISTICAL_FALLBACK"),
            "diagnostics": structured_diagnostics,
            "maintenance_advisory": maintenance_advisories[0] if maintenance_advisories else {},
            "maintenance_advisories": maintenance_advisories,
            "gcs_dfcs_advisory": gcs_dfcs_advisory,
            "state_transition_metadata": transition_metadata,
            "state_decision_explanation": transition_metadata,
            "state_explanation": transition_metadata,
            "state_history": list(self.state_machine.state_history)[-10:],
            "subsystem_states": self.state_machine.subsystem_states,
            "runtime_metrics": runtime_metrics,
            "metrics": runtime_metrics,

            # System Branding & Disclaimers
            "system_title": "MALE UAV Aero-Piston Engine Digital Twin — Demo Prototype",
            "engine_reference": "4-Cylinder Turbocharged Aero-Piston Reference Model",
            "user_role_display": "Demo Prototype Operator",
            "disclaimer_notice": "Software demonstrator using public/analogous datasets. Not connected to an operational UAV.",
            "derivatives": derivatives,
            "physics_baseline": physics_state,
            "autoencoder": ae_res,
            "cusum": cusum_res,
            "xgboost": xgb_res,
            "telemetry_source": telemetry_source,
            "telemetry_source_label": telemetry_source_label,
            "analytics_dataset": analytics_dataset,
            "analytics_dataset_label": analytics_dataset_label,
            "signal_provenance": signal_provenance,
            "provenance": signal_provenance
        }
        
        dt_end = time.perf_counter()
        metrics_tracker_instance.record_dt_latency((dt_end - dt_start) * 1000.0)
        return snapshot

digital_twin_core_instance = DigitalTwinCore()
