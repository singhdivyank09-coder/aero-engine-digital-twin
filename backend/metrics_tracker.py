"""
Runtime Performance & Data Integrity Instrumentation Tracker
Provides high-resolution (time.perf_counter) timing statistics for:
- Telemetry effective update rate (Hz) and interval (ms)
- Digital Twin processing latency (ms)
- Component latencies: Physics, Autoencoder, CUSUM, GRU, RUL, Predictive Engine, State Machine
- End-to-end processing & WebSocket publish latencies (ms)
- Data integrity validation rate (%), valid/invalid/dropped frames
- Predictive detection lead time (seconds)
"""

import time
import math
import numpy as np
from typing import Dict, Any, List, Optional
from collections import deque

class RuntimeMetricsTracker:
    def __init__(self, max_history: int = 300):
        self.max_history = max_history
        self.session_start_time = time.perf_counter()
        
        # Latency Ring Buffers (ms)
        self.dt_processing_latencies = deque(maxlen=max_history)
        self.physics_latencies = deque(maxlen=max_history)
        self.autoencoder_latencies = deque(maxlen=max_history)
        self.cusum_latencies = deque(maxlen=max_history)
        self.gru_latencies = deque(maxlen=max_history)
        self.predictive_health_latencies = deque(maxlen=max_history)
        self.state_machine_latencies = deque(maxlen=max_history)
        self.rul_latencies = deque(maxlen=max_history)
        self.ws_publish_latencies = deque(maxlen=max_history)
        self.end_to_end_latencies = deque(maxlen=max_history)
        
        # Rate & Interval Ring Buffers
        self.telemetry_intervals = deque(maxlen=max_history)  # in seconds
        self.ws_message_timestamps = deque(maxlen=max_history) # in perf_counter seconds
        
        # Cumulative Counters
        self.total_generated_frames = 0
        self.total_ingested_frames = 0
        self.valid_ingested_frames = 0
        self.dropped_invalid_frames = 0
        
        self.gru_inference_count = 0
        self.rul_inference_count = 0
        self.predictive_assessments_count = 0
        self.ws_messages_published = 0
        
        self.last_frame_wall_time = None
        self.last_frame_timestamp = None
        self.latest_gru_status = "WARMING_UP"
        self.last_rul_inference_ts = None
        
        # Predictive Lead Time Tracking
        self.current_warning_ts = None
        self.last_warning_timestamp = None
        self.last_active_fault_timestamp = None
        self.last_measured_lead_time_sec = None

    def reset(self):
        """Resets all metrics counters and latency buffers for a clean test run."""
        self.session_start_time = time.perf_counter()
        self.dt_processing_latencies.clear()
        self.physics_latencies.clear()
        self.autoencoder_latencies.clear()
        self.cusum_latencies.clear()
        self.gru_latencies.clear()
        self.predictive_health_latencies.clear()
        self.state_machine_latencies.clear()
        self.rul_latencies.clear()
        self.ws_publish_latencies.clear()
        self.end_to_end_latencies.clear()
        self.telemetry_intervals.clear()
        self.ws_message_timestamps.clear()
        
        self.total_generated_frames = 0
        self.total_ingested_frames = 0
        self.valid_ingested_frames = 0
        self.dropped_invalid_frames = 0
        self.gru_inference_count = 0
        self.rul_inference_count = 0
        self.predictive_assessments_count = 0
        self.ws_messages_published = 0
        self.last_frame_wall_time = None
        self.last_frame_timestamp = None
        self.latest_gru_status = "WARMING_UP"
        self.last_rul_inference_ts = None
        self.current_warning_ts = None
        self.last_warning_timestamp = None
        self.last_active_fault_timestamp = None
        self.last_measured_lead_time_sec = None

    def record_frame_ingestion(self, raw_telemetry: Dict[str, Any]) -> bool:
        self.total_ingested_frames += 1
        now = time.perf_counter()
        
        if self.last_frame_wall_time is not None:
            interval = now - self.last_frame_wall_time
            if 0.0001 < interval < 5.0:
                self.telemetry_intervals.append(interval)
        self.last_frame_wall_time = now

        # 1. Schema & Non-null Check
        required_keys = [
            "rpm", "map", "cht1", "cht2", "cht3", "cht4",
            "egt1", "egt2", "egt3", "egt4", "oil_press", "oil_temp",
            "fuel_flow", "vibration_rms", "battery_volt"
        ]
        for key in required_keys:
            if key not in raw_telemetry or raw_telemetry[key] is None:
                self.dropped_invalid_frames += 1
                return False
            try:
                val = float(raw_telemetry[key])
                if math.isnan(val) or math.isinf(val):
                    self.dropped_invalid_frames += 1
                    return False
            except (ValueError, TypeError):
                self.dropped_invalid_frames += 1
                return False

        # 2. Physical Range Bounds Check
        try:
            rpm = float(raw_telemetry["rpm"])
            oil_p = float(raw_telemetry["oil_press"])
            batt = float(raw_telemetry["battery_volt"])
            vib = float(raw_telemetry["vibration_rms"])

            if not (0.0 <= rpm <= 7000.0 and 0.0 <= oil_p <= 10.0 and 0.0 <= batt <= 30.0 and 0.0 <= vib <= 25.0):
                self.dropped_invalid_frames += 1
                return False

            for i in range(1, 5):
                cht = float(raw_telemetry.get(f"cht{i}", 120.0))
                egt = float(raw_telemetry.get(f"egt{i}", 750.0))
                if not (0.0 <= cht <= 300.0 and 0.0 <= egt <= 1100.0):
                    self.dropped_invalid_frames += 1
                    return False
        except (ValueError, TypeError):
            self.dropped_invalid_frames += 1
            return False

        self.valid_ingested_frames += 1
        return True

    def record_dt_latency(self, latency_ms: float):
        self.dt_processing_latencies.append(latency_ms)

    def record_ml_latency(self, latency_ms: float):
        self.autoencoder_latencies.append(latency_ms)

    def record_alert_latency(self, latency_ms: float):
        self.dt_processing_latencies.append(latency_ms)

    def record_physics_latency(self, latency_ms: float):
        self.physics_latencies.append(latency_ms)


    def record_autoencoder_latency(self, latency_ms: float):
        self.autoencoder_latencies.append(latency_ms)

    def record_cusum_latency(self, latency_ms: float):
        self.cusum_latencies.append(latency_ms)

    def record_gru_latency(self, latency_ms: float, status: str = "READY"):
        self.gru_latencies.append(latency_ms)
        self.gru_inference_count += 1
        self.latest_gru_status = status

    def record_predictive_health_latency(self, latency_ms: float, assessments_count: int = 1):
        self.predictive_health_latencies.append(latency_ms)
        self.predictive_assessments_count += assessments_count

    def record_state_machine_latency(self, latency_ms: float):
        self.state_machine_latencies.append(latency_ms)

    def record_rul_latency(self, latency_ms: float):
        self.rul_latencies.append(latency_ms)
        self.rul_inference_count += 1
        self.last_rul_inference_ts = time.time()

    def record_ws_publish_latency(self, latency_ms: float):
        self.ws_publish_latencies.append(latency_ms)

    def record_end_to_end_latency(self, latency_ms: float):
        self.end_to_end_latencies.append(latency_ms)

    def record_ws_message(self):
        self.ws_messages_published += 1
        self.ws_message_timestamps.append(time.perf_counter())

    def update_predictive_lead_time_tracker(self, system_state: str, timestamp: float, active_fault_confirmed: bool):
        if system_state in ["WARNING", "PREDICTIVE_RISK", "CAUTION"] and not active_fault_confirmed:
            if self.current_warning_ts is None:
                self.current_warning_ts = timestamp
                self.last_warning_timestamp = timestamp
        elif (system_state == "CRITICAL" or active_fault_confirmed) and self.current_warning_ts is not None:
            self.last_active_fault_timestamp = timestamp
            self.last_measured_lead_time_sec = round(timestamp - self.current_warning_ts, 1)
            self.current_warning_ts = None
        elif system_state == "NORMAL":
            self.current_warning_ts = None

    def _calc_stats(self, values: deque) -> Dict[str, Any]:
        if not values:
            return {
                "latest": None,
                "mean": None,
                "median": None,
                "p95": None,
                "max": None,
                "status": "AWAITING DATA"
            }
        arr = np.array(list(values))
        return {
            "latest": round(float(values[-1]), 2),
            "mean": round(float(np.mean(arr)), 2),
            "median": round(float(np.median(arr)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "max": round(float(np.max(arr)), 2),
            "status": "MEASURED"
        }

    def get_summary(self) -> Dict[str, Any]:
        if len(self.telemetry_intervals) >= 2:
            intervals_arr = np.array(list(self.telemetry_intervals))
            mean_int_sec = float(np.mean(intervals_arr))
            p95_int_sec = float(np.percentile(intervals_arr, 95))
            eff_hz = round(1.0 / mean_int_sec, 2) if mean_int_sec > 0 else 10.0
            mean_int_ms = round(mean_int_sec * 1000.0, 2)
            p95_int_ms = round(p95_int_sec * 1000.0, 2)
            telem_status = "MEASURED"
        else:
            eff_hz = None
            mean_int_ms = None
            p95_int_ms = None
            telem_status = "AWAITING DATA"

        if self.total_ingested_frames == 0:
            data_integrity_pct = None
            data_integrity_status = "AWAITING DATA"
            data_integrity_text = "AWAITING TELEMETRY"
        else:
            data_integrity_pct = round((self.valid_ingested_frames / self.total_ingested_frames) * 100.0, 2)
            data_integrity_status = "MEASURED"
            data_integrity_text = f"{data_integrity_pct}%"

        ws_hz = None
        if len(self.ws_message_timestamps) >= 2:
            time_span = self.ws_message_timestamps[-1] - self.ws_message_timestamps[0]
            if time_span > 0.05:
                ws_hz = round((len(self.ws_message_timestamps) - 1) / time_span, 1)

        dt_stats = self._calc_stats(self.dt_processing_latencies)
        physics_stats = self._calc_stats(self.physics_latencies)
        ae_stats = self._calc_stats(self.autoencoder_latencies)
        cusum_stats = self._calc_stats(self.cusum_latencies)
        gru_stats = self._calc_stats(self.gru_latencies)
        pred_stats = self._calc_stats(self.predictive_health_latencies)
        sm_stats = self._calc_stats(self.state_machine_latencies)
        rul_stats = self._calc_stats(self.rul_latencies)
        ws_stats = self._calc_stats(self.ws_publish_latencies)
        e2e_stats = self._calc_stats(self.end_to_end_latencies)

        lead_time_val = self.last_measured_lead_time_sec
        lead_time_text = f"{lead_time_val:.1f} s" if lead_time_val is not None else "NOT AVAILABLE (No complete degradation test)"

        return {
            "telemetry": {
                "target_hz": 10.0,
                "effective_hz": eff_hz,
                "mean_interval_ms": mean_int_ms,
                "p95_interval_ms": p95_int_ms,
                "status": telem_status
            },
            "data_integrity": {
                "total_ingested_frames": self.total_ingested_frames,
                "valid_ingested_frames": self.valid_ingested_frames,
                "dropped_invalid_frames": self.dropped_invalid_frames,
                "data_integrity_pct": data_integrity_pct,
                "data_integrity_text": data_integrity_text,
                "status": data_integrity_status,
                "formula": "(Valid Frames / Total Ingested Frames) × 100"
            },
            "latencies": {
                "digital_twin": dt_stats,
                "physics": physics_stats,
                "autoencoder": ae_stats,
                "cusum": cusum_stats,
                "gru_forecast": gru_stats,
                "predictive_health": pred_stats,
                "state_machine": sm_stats,
                "rul_inference": rul_stats,
                "websocket_publish": ws_stats,
                "end_to_end": e2e_stats
            },
            "gru_runtime": {
                "inference_cadence": "~1.0 Hz (60-step window)",
                "inference_count": self.gru_inference_count,
                "latency": gru_stats,
                "forecast_status": self.latest_gru_status
            },
            "rul_runtime": {
                "inference_cadence": "Sequence Update (30-step window)",
                "inference_count": self.rul_inference_count,
                "latency": rul_stats,
                "last_inference_ts": self.last_rul_inference_ts
            },
            "predictive_performance": {
                "assessments_completed": self.predictive_assessments_count,
                "analytics_latency": dt_stats,
                "first_warning_timestamp": self.last_warning_timestamp,
                "active_fault_timestamp": self.last_active_fault_timestamp,
                "predictive_lead_time_seconds": lead_time_val,
                "lead_time_text": lead_time_text
            },
            "websocket": {
                "published_messages": self.ws_messages_published,
                "publish_rate_hz": ws_hz if ws_hz is not None else "AWAITING DATA",
                "publish_latency": ws_stats
            },
            "session_uptime_seconds": round(time.perf_counter() - self.session_start_time, 1),
            
            # Legacy fields for backward compatibility
            "update_rate_hz": {
                "mean": eff_hz,
                "median": eff_hz,
                "p95": eff_hz,
                "max": eff_hz,
                "status": telem_status
            },
            "dt_processing_latency_ms": dt_stats,
            "ml_inference_latency_ms": ae_stats,
            "alert_latency_ms": dt_stats,
            "websocket_msg_rate_hz": ws_hz if ws_hz is not None else "AWAITING DATA",
            "total_ingested_frames": self.total_ingested_frames,
            "valid_ingested_frames": self.valid_ingested_frames,
            "dropped_invalid_frames": self.dropped_invalid_frames,
            "data_integrity_rate_pct": data_integrity_pct,
            "data_integrity_status": data_integrity_status,
            "data_integrity_text": data_integrity_text
        }

metrics_tracker_instance = RuntimeMetricsTracker()
