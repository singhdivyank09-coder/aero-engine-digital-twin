"""
Predictive State Machine & Multi-Source Evidence Fusion Engine
SIH 26054 — Aero-Piston Engine Digital Twin

Performs:
- Transparent multi-source evidence fusion score computation [0.0, 1.0]
- Independent 5-subsystem state tracking (Thermal, Lubrication, Combustion, Mechanical, Electrical)
- Derived global system state (NORMAL -> WATCH -> CAUTION -> WARNING -> CRITICAL)
- Stepwise progressive hysteresis recovery (CRITICAL -> WARNING -> CAUTION -> WATCH -> NORMAL)
- K-of-M temporal persistence ring buffers (5-frame activation, 4-frame recovery)
- Full state-decision explanation objects with transition metadata
- TwinSession transition event logging (state_history)
"""

import math
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from collections import deque

from backend.predictive_state_config import (
    EVIDENCE_WEIGHTS,
    STATE_THRESHOLDS,
    ACTIVATION_PERSISTENCE_DEPTH,
    ACTIVATION_K_OF_M,
    RECOVERY_PERSISTENCE_DEPTH,
    RECOVERY_K_OF_M,
    SAFETY_ENVELOPES
)

class PredictiveStateMachine:
    STATES = ["NORMAL", "WATCH", "CAUTION", "WARNING", "CRITICAL"]
    SUBSYSTEMS = ["Thermal", "Lubrication", "Combustion", "Mechanical", "Electrical"]

    def __init__(self):
        self.sequence_number = 0
        self.global_state = "NORMAL"
        self.dominant_subsystem = "Thermal"

        # Per-Subsystem State Tracking
        self.subsystem_states = {s: "NORMAL" for s in self.SUBSYSTEMS}
        self.subsystem_evidence_scores = {s: 0.0 for s in self.SUBSYSTEMS}
        self.subsystem_activation_buffers = {s: deque(maxlen=ACTIVATION_PERSISTENCE_DEPTH) for s in self.SUBSYSTEMS}
        self.subsystem_recovery_buffers = {s: deque(maxlen=RECOVERY_PERSISTENCE_DEPTH) for s in self.SUBSYSTEMS}

        # Global State Persistence Buffers
        self.global_activation_buffer = deque(maxlen=ACTIVATION_PERSISTENCE_DEPTH)
        self.global_recovery_buffer = deque(maxlen=RECOVERY_PERSISTENCE_DEPTH)

        # Transition Event Log History (TwinSession.state_history)
        self.state_history = []
        self.latest_explanation = None

    def reset(self):
        """Resets state machine buffers, active states, and transition history."""
        self.sequence_number = 0
        self.global_state = "NORMAL"
        self.dominant_subsystem = "Thermal"
        self.subsystem_states = {s: "NORMAL" for s in self.SUBSYSTEMS}
        self.subsystem_evidence_scores = {s: 0.0 for s in self.SUBSYSTEMS}
        self.subsystem_activation_buffers = {s: deque(maxlen=ACTIVATION_PERSISTENCE_DEPTH) for s in self.SUBSYSTEMS}
        self.subsystem_recovery_buffers = {s: deque(maxlen=RECOVERY_PERSISTENCE_DEPTH) for s in self.SUBSYSTEMS}
        self.global_activation_buffer.clear()
        self.global_recovery_buffer.clear()
        self.state_history.clear()
        self.latest_explanation = None

    def _state_idx(self, state_str: str) -> int:
        return self.STATES.index(state_str) if state_str in self.STATES else 0

    def _check_subsystem_fault_confirmation(self, subsystem: str, telemetry: Dict[str, Any]) -> bool:
        """Determines if a PHYSICAL SAFETY LIMIT BREACH exists on CURRENT frame for a subsystem."""
        if subsystem == "Thermal":
            cht_vals = [float(telemetry.get(f"cht{i}", 120.0)) for i in range(1, 5)]
            return max(cht_vals) >= SAFETY_ENVELOPES["cht"]["fault_limit"] # >= 145.0 °C
        elif subsystem == "Lubrication":
            oil_press = float(telemetry.get("oil_press", 4.2))
            return oil_press <= SAFETY_ENVELOPES["oil_press"]["fault_limit"] # <= 2.50 bar
        elif subsystem == "Mechanical":
            vib_rms = float(telemetry.get("vibration_rms", 1.12))
            return vib_rms >= SAFETY_ENVELOPES["vibration_rms"]["fault_limit"] # >= 2.50 g
        elif subsystem == "Combustion":
            egt_vals = [float(telemetry.get(f"egt{i}", 750.0)) for i in range(1, 5)]
            egt_spread = max(egt_vals) - min(egt_vals)
            return egt_spread >= SAFETY_ENVELOPES["egt_spread"]["fault_limit"] # >= 90.0 °C
        elif subsystem == "Electrical":
            batt_volt = float(telemetry.get("battery_volt", 14.10))
            return (batt_volt <= SAFETY_ENVELOPES["battery_volt"]["fault_min"] or
                    batt_volt >= SAFETY_ENVELOPES["battery_volt"]["fault_max"])
        return False

    def _compute_evidence_fusion_score(
        self,
        subsystem: str,
        pa: Dict[str, Any],
        telemetry: Dict[str, Any],
        physics_state: Dict[str, Any],
        ae_res: Dict[str, Any],
        cusum_res: Dict[str, Any],
        gru_forecast_res: Optional[Dict[str, Any]],
        subsystem_health: float
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculates transparent weighted evidence fusion score E_sub in [0.0, 1.0].
        Weights are configured strictly in backend/predictive_state_config.py.
        """
        curr_val = float(pa.get("current_value", 0.0))
        slope = float(pa.get("short_slope", 0.0))
        t_risk_raw = pa.get("estimated_time_to_risk")
        t_risk = float(t_risk_raw) if (t_risk_raw is not None and t_risk_raw != "N/A") else 999.0
        deg_score = float(pa.get("degradation_score", 0.0))
        ae_score = float(ae_res.get("anomaly_score", 0.0))
        ae_slope = float(pa.get("anomaly_score_slope", 0.0))
        cusum_active = bool(cusum_res.get("cusum_alert_active", False))

        # 1. GRU Neural Short-Horizon Forecast Risk Norm
        forecast_mode = pa.get("forecast_mode", "STATISTICAL_FALLBACK")
        forecast_risk_norm = 0.0
        
        if gru_forecast_res and gru_forecast_res.get("status") == "READY":
            fc = gru_forecast_res.get("forecast", {})
            f30 = fc.get("30s", {})
            f60 = fc.get("60s", {})

            if subsystem == "Thermal":
                v30 = float(f30.get("cht1", curr_val))
                v60 = float(f60.get("cht1", curr_val))
                max_v = max(v30, v60)
                if max_v >= 145.0: forecast_risk_norm = 1.0
                elif max_v >= 138.0: forecast_risk_norm = 0.70
                elif max_v >= 134.0: forecast_risk_norm = 0.40
            elif subsystem == "Lubrication":
                v30 = float(f30.get("oil_pressure", curr_val))
                v60 = float(f60.get("oil_pressure", curr_val))
                min_v = min(v30, v60)
                if min_v <= 2.50: forecast_risk_norm = 1.0
                elif min_v <= 3.20: forecast_risk_norm = 0.70
                elif min_v <= 3.50: forecast_risk_norm = 0.40
            elif subsystem == "Mechanical":
                v30 = float(f30.get("vibration_rms", curr_val))
                v60 = float(f60.get("vibration_rms", curr_val))
                max_v = max(v30, v60)
                if max_v >= 2.50: forecast_risk_norm = 1.0
                elif max_v >= 1.80: forecast_risk_norm = 0.70
                elif max_v >= 1.50: forecast_risk_norm = 0.40

        if forecast_risk_norm == 0.0:
            fut = pa.get("future_forecast", {})
            f_val = float(fut.get("forecasted_value", curr_val))
            if subsystem == "Thermal" and f_val >= 145.0: forecast_risk_norm = 0.80
            elif subsystem == "Lubrication" and f_val <= 2.50: forecast_risk_norm = 0.80
            elif subsystem == "Mechanical" and f_val >= 2.50: forecast_risk_norm = 0.80

        # 2. Time-to-Risk Urgency Norm
        if t_risk <= 20.0: time_to_risk_norm = 1.0
        elif t_risk <= 45.0: time_to_risk_norm = 0.75
        elif t_risk <= 60.0: time_to_risk_norm = 0.45
        elif t_risk <= 90.0: time_to_risk_norm = 0.20
        else: time_to_risk_norm = 0.0

        # 3. Degradation Score Norm
        deg_norm = min(1.0, max(0.0, deg_score))

        # 4. Autoencoder Anomaly Score Norm
        ae_norm = min(1.0, max(0.0, ae_score / 0.75))

        # 5. Autoencoder Slope Norm
        ae_slope_norm = min(1.0, max(0.0, ae_slope / 0.04))

        # 6. CUSUM Norm
        cusum_norm = 1.0 if cusum_active else 0.0

        # 7. Physics Residual Severity Norm
        res = physics_state.get("residuals", {})
        if subsystem == "Thermal": res_val = abs(float(res.get("cht_delta", 0.0))) / 12.0
        elif subsystem == "Lubrication": res_val = abs(float(res.get("oil_press_delta", 0.0))) / 0.60
        elif subsystem == "Combustion": res_val = abs(float(res.get("egt_delta", 0.0))) / 35.0
        else: res_val = 0.0
        residual_norm = min(1.0, max(0.0, res_val))

        # 8. Subsystem Health Index Degradation Norm
        health_deg_norm = min(1.0, max(0.0, (100.0 - subsystem_health) / 45.0))

        terms = {
            "forecast_risk": forecast_risk_norm,
            "time_to_risk": time_to_risk_norm,
            "degradation_score": deg_norm,
            "autoencoder_score": ae_norm,
            "autoencoder_slope": ae_slope_norm,
            "cusum_detected": cusum_norm,
            "physics_residual": residual_norm,
            "subsystem_health": health_deg_norm
        }

        score = sum(terms[k] * EVIDENCE_WEIGHTS[k] for k in terms)
        return round(float(score), 3), terms

    def _determine_target_subsystem_state(
        self,
        subsystem: str,
        evidence_score: float,
        is_fault_confirmed: bool,
        pa: Dict[str, Any],
        subsystem_health: float
    ) -> Tuple[str, str]:
        """
        Determines target subsystem state BEFORE temporal persistence filters are applied.
        CRITICAL is strictly reserved for confirmed severe CURRENT physical fault conditions.
        """
        st_config = STATE_THRESHOLDS
        pred_st = pa.get("status", pa.get("current_state", "NOMINAL"))
        t_risk_raw = pa.get("estimated_time_to_risk")
        t_risk = float(t_risk_raw) if (t_risk_raw is not None and t_risk_raw != "N/A") else 999.0
        slope = float(pa.get("short_slope", 0.0))

        if is_fault_confirmed or subsystem_health < st_config["CRITICAL"]["health_activation"]:
            return "CRITICAL", f"Physical fault confirmed on {subsystem} (Current limit breached or Health < {st_config['CRITICAL']['health_activation']}%)."

        if (evidence_score >= st_config["WARNING"]["activation_score"] or
            pred_st == "PREDICTIVE_RISK" and (t_risk <= 45.0 or abs(slope) >= 0.25) or
            subsystem_health < st_config["WARNING"]["health_activation"]):
            return "WARNING", f"Strong predictive risk on {subsystem} (Evidence score={evidence_score:.3f}, Time to risk={t_risk:.1f}s)."

        if (evidence_score >= st_config["CAUTION"]["activation_score"] or
            pred_st == "PREDICTIVE_RISK" or
            subsystem_health < st_config["CAUTION"]["health_activation"]):
            return "CAUTION", f"Predictive trajectory risk detected on {subsystem} (Evidence score={evidence_score:.3f})."

        if (evidence_score >= st_config["WATCH"]["activation_score"] or
            pred_st == "DEGRADATION_DETECTED" or
            subsystem_health < st_config["WATCH"]["health_activation"]):
            return "WATCH", f"Early degradation/trend evidence detected on {subsystem} (Evidence score={evidence_score:.3f})."

        return "NORMAL", f"{subsystem} subsystem operating nominally."

    def evaluate_frame(
        self,
        telemetry: Dict[str, Any],
        health_ema: Dict[str, float],
        predictive_assessments: List[Dict[str, Any]],
        physics_state: Dict[str, Any],
        ae_res: Dict[str, Any],
        cusum_res: Dict[str, Any],
        gru_forecast_res: Optional[Dict[str, Any]],
        timestamp: float
    ) -> Dict[str, Any]:
        """
        Evaluates frame predictive evidence across all 5 subsystems and global system state.
        Applies K-of-M persistence ring buffers and progressive step-down hysteresis recovery.
        Logs transitions to TwinSession state_history.
        """
        self.sequence_number += 1
        pa_map = {pa.get("subsystem", "Thermal"): pa for pa in predictive_assessments}

        sub_target_states = {}
        sub_reasons = {}

        for sub in self.SUBSYSTEMS:
            pa = pa_map.get(sub, {})
            sub_hi = float(health_ema.get(sub.lower(), 98.0))
            is_fault = self._check_subsystem_fault_confirmation(sub, telemetry)
            
            score, _ = self._compute_evidence_fusion_score(
                sub, pa, telemetry, physics_state, ae_res, cusum_res, gru_forecast_res, sub_hi
            )
            self.subsystem_evidence_scores[sub] = score
            
            target_st, reason = self._determine_target_subsystem_state(sub, score, is_fault, pa, sub_hi)
            sub_target_states[sub] = target_st
            sub_reasons[sub] = reason

        # 1. Per-Subsystem Persistence & Hysteresis Processing
        for sub in self.SUBSYSTEMS:
            target_st = sub_target_states[sub]
            curr_st = self.subsystem_states[sub]
            curr_idx = self._state_idx(curr_st)
            target_idx = self._state_idx(target_st)
            score = self.subsystem_evidence_scores[sub]

            # Activation buffer
            self.subsystem_activation_buffers[sub].append(target_idx >= curr_idx + 1)
            # Recovery buffer
            is_recovery_candidate = (target_idx < curr_idx) and (score <= STATE_THRESHOLDS.get(curr_st, {}).get("recovery_score", 0.50))
            self.subsystem_recovery_buffers[sub].append(is_recovery_candidate)

            is_activated = sum(self.subsystem_activation_buffers[sub]) >= ACTIVATION_K_OF_M
            is_recovered = sum(self.subsystem_recovery_buffers[sub]) >= RECOVERY_K_OF_M

            if target_idx > curr_idx:
                if is_activated:
                    new_sub_st = self.STATES[curr_idx + 1]
                else:
                    new_sub_st = curr_st
            elif target_idx < curr_idx:
                if is_recovered:
                    # Progressive step-down recovery (CRITICAL -> WARNING -> CAUTION -> WATCH -> NORMAL)
                    new_sub_st = self.STATES[curr_idx - 1]
                    self.subsystem_recovery_buffers[sub].clear()
                else:
                    new_sub_st = curr_st
            else:
                new_sub_st = curr_st

            if new_sub_st != curr_st:
                # Log Subsystem Transition to State History
                self.state_history.append({
                    "timestamp": timestamp,
                    "sequence_number": self.sequence_number,
                    "subsystem": sub,
                    "previous_state": curr_st,
                    "new_state": new_sub_st,
                    "reason": sub_reasons[sub],
                    "evidence": {
                        "evidence_score": self.subsystem_evidence_scores[sub],
                        "current_value": pa_map.get(sub, {}).get("current_value", 0.0),
                        "time_to_risk": float(pa_map.get(sub, {}).get("estimated_time_to_risk")) if (pa_map.get(sub, {}).get("estimated_time_to_risk") is not None and pa_map.get(sub, {}).get("estimated_time_to_risk") != "N/A") else 999.0
                    }
                })
                self.subsystem_states[sub] = new_sub_st

        # 2. Derive Global System State & Dominant Subsystem
        worst_subsystem = max(self.SUBSYSTEMS, key=lambda s: (self._state_idx(self.subsystem_states[s]), self.subsystem_evidence_scores[s]))
        target_global_st = self.subsystem_states[worst_subsystem]
        target_global_idx = self._state_idx(target_global_st)
        curr_global_idx = self._state_idx(self.global_state)
        dominant_score = self.subsystem_evidence_scores[worst_subsystem]

        self.global_activation_buffer.append(target_global_idx > curr_global_idx)
        is_global_rec = (target_global_idx < curr_global_idx) and (dominant_score <= STATE_THRESHOLDS.get(self.global_state, {}).get("recovery_score", 0.50))
        self.global_recovery_buffer.append(is_global_rec)

        if target_global_idx > curr_global_idx:
            if target_global_st == "CRITICAL" and self._check_subsystem_fault_confirmation(worst_subsystem, telemetry):
                new_global_st = "CRITICAL"
            elif sum(self.global_activation_buffer) >= ACTIVATION_K_OF_M:
                new_global_st = self.STATES[curr_global_idx + 1]
            else:
                new_global_st = self.global_state
        elif target_global_idx < curr_global_idx:
            if sum(self.global_recovery_buffer) >= RECOVERY_K_OF_M:
                new_global_st = self.STATES[curr_global_idx - 1]
                self.global_recovery_buffer.clear()
            else:
                new_global_st = self.global_state
        else:
            new_global_st = self.global_state

        prev_global_st = self.global_state
        if new_global_st != prev_global_st:
            if self._state_idx(new_global_st) < self._state_idx(prev_global_st):
                transition_reason = f"Monitored parameters recovering within reference envelopes ({prev_global_st} → {new_global_st})."
            else:
                transition_reason = f"Global state transition from {prev_global_st} to {new_global_st} driven by {worst_subsystem} subsystem."
            self.state_history.append({
                "timestamp": timestamp,
                "sequence_number": self.sequence_number,
                "subsystem": "GLOBAL",
                "previous_state": prev_global_st,
                "new_state": new_global_st,
                "reason": transition_reason,
                "evidence": {
                    "dominant_subsystem": worst_subsystem,
                    "evidence_score": dominant_score,
                    "subsystem_states": self.subsystem_states.copy()
                }
            })
            self.global_state = new_global_st
        else:
            if new_global_st == "NORMAL":
                transition_reason = "All monitored propulsion parameters are operating within nominal reference envelopes."
            else:
                transition_reason = f"State unchanged — system remains {new_global_st}."

        self.dominant_subsystem = worst_subsystem

        # 3. Build Full Transparent State Decision Explanation Object
        worst_pa = pa_map.get(worst_subsystem, {})
        current_fault_confirmed = any(self._check_subsystem_fault_confirmation(s, telemetry) for s in self.SUBSYSTEMS)
        forecast_mode = gru_forecast_res.get("forecast_mode", "STATISTICAL_FALLBACK") if gru_forecast_res else "STATISTICAL_FALLBACK"

        t_risk_worst_raw = worst_pa.get("estimated_time_to_risk")
        t_risk_worst = float(t_risk_worst_raw) if (t_risk_worst_raw is not None and t_risk_worst_raw != "N/A") else 999.0

        explanation = {
            "timestamp": timestamp,
            "sequence_number": self.sequence_number,
            "previous_state": prev_global_st,
            "new_state": self.global_state,
            "state": self.global_state,
            "dominant_subsystem": self.dominant_subsystem,
            "predictive_status": worst_pa.get("status", "NOMINAL"),
            "evidence_score": dominant_score,
            "gru_forecast_risk": round(float(self.subsystem_evidence_scores[worst_subsystem]), 3),
            "estimated_time_to_risk": t_risk_worst,
            "anomaly_score": round(float(ae_res.get("anomaly_score", 0.0)), 3),
            "anomaly_trend": round(float(worst_pa.get("anomaly_score_slope", 0.0)), 4),
            "cusum_evidence": bool(cusum_res.get("cusum_alert_active", False)),
            "physics_residual_evidence": round(float(worst_pa.get("physics_residual", 0.0)), 2),
            "subsystem_health": health_ema,
            "current_fault_confirmed": current_fault_confirmed,
            "transition_reason": transition_reason,
            "forecast_mode": forecast_mode,
            "subsystem_states": self.subsystem_states.copy(),
            "subsystem_evidence_scores": self.subsystem_evidence_scores.copy()
        }

        self.latest_explanation = explanation
        return explanation

predictive_state_machine_instance = PredictiveStateMachine()
