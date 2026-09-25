"""
Mission Recorder Module — Automatic Real-Time Live Twin Session Recorder
Subscribes to the canonical TwinSession snapshot stream, tracks state transitions and fault events,
and persists snapshots and events to SQLite storage.
"""

import os
import time
import json
from collections import deque
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.database import (
    save_mission_record,
    save_mission_snapshot_record,
    save_mission_event_record,
    db_get_all_missions,
    db_get_mission
)

def sanitize_snapshot_for_persistence(snap: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strips heavy cumulative histories (unbounded state_history, forecast_history, predictive_history,
    fault_event_log, duplicate metrics objects) right at the mission persistence boundary to keep
    SQLite snapshot records bounded at < 10 KB while preserving full mission replay fidelity.
    """
    if not snap or not isinstance(snap, dict):
        return {}

    ass = snap.get("latest_predictive_assessment") or snap.get("predictive_assessment") or {}
    fc = snap.get("latest_forecast") or snap.get("forecast") or {}

    compact_ass = {
        "affected_subsystem": ass.get("affected_subsystem"),
        "affected_component": ass.get("affected_component"),
        "primary_parameter": ass.get("primary_parameter"),
        "primary_parameter_label": ass.get("primary_parameter_label"),
        "unit": ass.get("unit"),
        "reference_envelope_text": ass.get("reference_envelope_text"),
        "estimated_time_to_risk_seconds": ass.get("estimated_time_to_risk_seconds"),
        "degradation_score": ass.get("degradation_score"),
        "predictive_status": ass.get("predictive_status")
    } if ass else {}

    compact = {
        "sequence_number": snap.get("sequence_number"),
        "timestamp": snap.get("timestamp"),
        "session_id": snap.get("session_id"),
        "system_state": snap.get("system_state") or snap.get("global_state"),
        "overall_health_index": snap.get("overall_health_index"),
        "anomaly_score": snap.get("anomaly_score"),
        "scenario": snap.get("scenario"),
        "scenario_parameters": snap.get("scenario_parameters"),
        "telemetry": snap.get("telemetry"),
        "prototype_rul_estimate": snap.get("prototype_rul_estimate"),
        "latest_predictive_assessment": {k: v for k, v in compact_ass.items() if v is not None},
        "latest_forecast": {
            "status": fc.get("status"),
            "forecast_10s": fc.get("forecast_10s") or (fc.get("forecast", {}) if isinstance(fc.get("forecast"), dict) else {}).get("10s"),
            "forecast_30s": fc.get("forecast_30s") or (fc.get("forecast", {}) if isinstance(fc.get("forecast"), dict) else {}).get("30s"),
            "forecast_60s": fc.get("forecast_60s") or (fc.get("forecast", {}) if isinstance(fc.get("forecast"), dict) else {}).get("60s")
        } if fc else {},
        "active_faults": snap.get("active_faults") or snap.get("active_injections"),
        "predictive_diagnostics": snap.get("predictive_diagnostics") or snap.get("diagnostics"),
        "residuals_table": snap.get("residuals_table"),
        "subsystem_health": snap.get("subsystem_health"),
        "subsystem_states": snap.get("subsystem_states"),
        "parameter_statuses": snap.get("parameter_statuses"),
        "state_transition_metadata": snap.get("state_transition_metadata"),
        "state_history": snap.get("state_history", [])[-5:] if snap.get("state_history") else []
    }
    return {k: v for k, v in compact.items() if v is not None and v != {} and v != []}


class MissionRecorder:
    _mission_counter = 1

    def __init__(self):
        self.is_recording = True
        self.session_id = "TWIN_SESSION_SIH26054"
        self.current_mission_id = self._generate_mission_id()
        self.start_wall_time = datetime.now().isoformat()
        self.start_ts = time.time()
        
        self.recorded_snapshots = deque(maxlen=1200)
        self.recorded_events: List[Dict[str, Any]] = []
        
        self.prev_scenario: Optional[str] = None
        self.prev_state: Optional[str] = None
        self.prev_fault_count: int = 0
        self.prev_diagnostics_set = set()
        
        # Internal aggregates
        self.min_health: float = 100.0
        self.max_anomaly: float = 0.0
        self.max_predictive_risk: float = 0.0
        self.rul_start: Optional[float] = None
        self.rul_end: Optional[float] = None
        self.initial_scenario: str = "CRUISE"
        self.telemetry_source: str = "SIMULATOR"
        self.analytics_dataset: str = "CMAPSS"
        
        self._init_mission_record()

    @property
    def recorded_frames(self) -> int:
        return len(self.recorded_snapshots)

    def _generate_mission_id(self) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        millis = int(time.time() * 1000) % 1000
        mid = f"MIS-{date_str}-{MissionRecorder._mission_counter:03d}-{millis:03d}"
        MissionRecorder._mission_counter += 1
        return mid

    def _init_mission_record(self):
        meta = {
            "mission_id": self.current_mission_id,
            "session_id": self.session_id,
            "start_time": self.start_wall_time,
            "duration": 0.0,
            "telemetry_source": self.telemetry_source,
            "analytics_dataset": self.analytics_dataset,
            "initial_scenario": self.initial_scenario,
            "final_state": "NORMAL",
            "min_health": 100.0,
            "max_anomaly": 0.0,
            "rul_start": None,
            "rul_end": None,
            "frame_count": 0,
            "summary_json": {}
        }
        try:
            save_mission_record(meta)
            # Record MISSION_START event
            start_evt = {
                "event_id": f"EVT_{self.current_mission_id}_START",
                "mission_id": self.current_mission_id,
                "sequence_number": 0,
                "twin_timestamp": 0.0,
                "event_type": "MISSION_START",
                "subsystem": "GLOBAL_SYSTEM",
                "component": "ENGINE",
                "details": f"Mission {self.current_mission_id} started recording"
            }
            self.recorded_events.append(start_evt)
            save_mission_event_record(self.current_mission_id, start_evt)
        except Exception as e:
            print(f"[MISSION RECORDER INIT ERROR] {e}")

    def start_new_mission(self, scenario: str = "CRUISE", initial_scenario: Optional[str] = None, telemetry_source: str = "SIMULATOR", analytics_dataset: str = "CMAPSS") -> str:
        """Finalizes the current mission recording and begins a new one."""
        if initial_scenario:
            scenario = initial_scenario
            
        self.finalize_current_mission()
        
        self.current_mission_id = self._generate_mission_id()
        self.start_wall_time = datetime.now().isoformat()
        self.start_ts = time.time()
        self.recorded_snapshots.clear()
        self.recorded_events.clear()
        
        self.prev_scenario = None
        self.prev_state = None
        self.prev_fault_count = 0
        self.prev_diagnostics_set.clear()
        
        self.min_health = 100.0
        self.max_anomaly = 0.0
        self.max_predictive_risk = 0.0
        self.rul_start = None
        self.rul_end = None
        self.initial_scenario = scenario
        self.telemetry_source = telemetry_source
        self.analytics_dataset = analytics_dataset
        
        self._init_mission_record()
        print(f"[MISSION RECORDER] Started new mission: {self.current_mission_id}")
        return self.current_mission_id

    def record_snapshot(self, snapshot: Dict[str, Any]):
        """Records a live canonical TwinSnapshot into memory and SQLite database."""
        if not self.is_recording or not snapshot:
            return

        seq = snapshot.get("sequence_number", 0)
        ts = snapshot.get("timestamp", 0.0)
        state = snapshot.get("system_state") or snapshot.get("global_state") or "NORMAL"
        
        sc_obj = snapshot.get("scenario")
        sc_id = sc_obj.get("id") if isinstance(sc_obj, dict) else str(sc_obj or "CRUISE")
        
        health_val = float(snapshot.get("health", {}).get("overall", snapshot.get("overall_health_index", 100.0)))
        anom_val = float(snapshot.get("anomaly", {}).get("score", snapshot.get("anomaly_score", 0.0)))
        risk_val = float(snapshot.get("predictive_risk", 0.0))
        
        rul_obj = snapshot.get("rul", {}) or snapshot.get("prototype_rul_estimate", {})
        rul_cycles = rul_obj.get("display_prediction_cycles")
        
        # Track aggregates
        if health_val < self.min_health:
            self.min_health = health_val
        if anom_val > self.max_anomaly:
            self.max_anomaly = anom_val
        if risk_val > self.max_predictive_risk:
            self.max_predictive_risk = risk_val
        if rul_cycles is not None and isinstance(rul_cycles, (int, float)):
            if self.rul_start is None:
                self.rul_start = float(rul_cycles)
            self.rul_end = float(rul_cycles)
            
        self.recorded_snapshots.append(snapshot)
        
        # Persist downsampled snapshot record to DB (0.2 Hz or state transitions) to prevent database growth
        if seq % 50 == 0 or (self.prev_state is not None and state != self.prev_state):
            try:
                compact_snap = sanitize_snapshot_for_persistence(snapshot)
                save_mission_snapshot_record(self.current_mission_id, seq, ts, compact_snap)
            except Exception as e:
                print(f"[RECORDER SNAPSHOT SAVE ERROR] {e}")

        # ----------------------------------------------------
        # EVENT DETECTION & STREAMING
        # ----------------------------------------------------
        
        # 1. Scenario Change Event
        if self.prev_scenario is not None and sc_id != self.prev_scenario:
            sc_evt = {
                "event_id": f"EVT_SCENARIO_{seq}",
                "mission_id": self.current_mission_id,
                "session_id": self.session_id,
                "sequence_number": seq,
                "twin_timestamp": ts,
                "event_type": "SCENARIO_CHANGE",
                "subsystem": "ENVIRONMENT",
                "component": "FLIGHT_PROFILE",
                "details": f"Scenario changed from {self.prev_scenario} to {sc_id}",
                "from_scenario": self.prev_scenario,
                "to_scenario": sc_id
            }
            self.recorded_events.append(sc_evt)
            try: save_mission_event_record(self.current_mission_id, sc_evt)
            except Exception: pass
        self.prev_scenario = sc_id

        # 2. System State Transition Event
        if self.prev_state is not None and state != self.prev_state:
            state_rank = {"NORMAL": 0, "WATCH": 1, "CAUTION": 2, "WARNING": 3, "CRITICAL": 4}
            is_escalation = state_rank.get(state, 0) > state_rank.get(self.prev_state, 0)
            
            if is_escalation:
                evt_type = f"{state}_ENTERED"
            else:
                evt_type = "STATE_RECOVERY"
                
            st_evt = {
                "event_id": f"EVT_STATE_{seq}",
                "mission_id": self.current_mission_id,
                "session_id": self.session_id,
                "sequence_number": seq,
                "twin_timestamp": ts,
                "event_type": evt_type,
                "subsystem": "GLOBAL_SYSTEM",
                "component": "ENGINE",
                "details": f"System state transitioned from {self.prev_state} to {state}",
                "from_state": self.prev_state,
                "to_state": state,
                "reason": snapshot.get("state_reasoning", snapshot.get("state_reason", ""))
            }
            self.recorded_events.append(st_evt)
            try: save_mission_event_record(self.current_mission_id, st_evt)
            except Exception: pass
        self.prev_state = state

        # 3. Fault Injection Events
        injections = snapshot.get("active_injections") or snapshot.get("active_faults") or []
        curr_fault_count = len(injections)
        
        if curr_fault_count > self.prev_fault_count:
            # Fault Injected
            latest_fault = injections[0] if injections else {}
            flt_evt = {
                "event_id": f"EVT_FAULT_START_{seq}",
                "mission_id": self.current_mission_id,
                "session_id": self.session_id,
                "sequence_number": seq,
                "twin_timestamp": ts,
                "event_type": "FAULT_INJECTION_STARTED",
                "subsystem": latest_fault.get("subsystem", "PROPULSION"),
                "component": latest_fault.get("affected_component", latest_fault.get("component", "CYLINDER_1")),
                "details": f"Injected fault {latest_fault.get('scenario', 'FAULT')} on {latest_fault.get('affected_component', 'CYLINDER_1')}",
                "fault_config": latest_fault
            }
            self.recorded_events.append(flt_evt)
            try: save_mission_event_record(self.current_mission_id, flt_evt)
            except Exception: pass
        elif curr_fault_count == 0 and self.prev_fault_count > 0:
            # Fault Cleared
            clr_evt = {
                "event_id": f"EVT_FAULT_CLEAR_{seq}",
                "mission_id": self.current_mission_id,
                "session_id": self.session_id,
                "sequence_number": seq,
                "twin_timestamp": ts,
                "event_type": "ALL_FAULTS_CLEARED",
                "subsystem": "GLOBAL_SYSTEM",
                "component": "ENGINE",
                "details": "All active fault injections cleared by operator"
            }
            self.recorded_events.append(clr_evt)
            try: save_mission_event_record(self.current_mission_id, clr_evt)
            except Exception: pass
        self.prev_fault_count = curr_fault_count

        # 4. Diagnostic Warnings
        diags = snapshot.get("diagnostics", snapshot.get("predictive_diagnostics", []))
        curr_diag_set = { (d.get("affected_subsystem"), d.get("classifier_label")) for d in diags if isinstance(d, dict) }
        
        new_diags = curr_diag_set - self.prev_diagnostics_set
        for sub, label in new_diags:
            diag_evt = {
                "event_id": f"EVT_DIAG_{seq}_{sub}",
                "mission_id": self.current_mission_id,
                "session_id": self.session_id,
                "sequence_number": seq,
                "twin_timestamp": ts,
                "event_type": "PREDICTIVE_WARNING",
                "subsystem": sub,
                "component": label,
                "details": f"AI Diagnostic Warning: {label} on {sub}"
            }
            self.recorded_events.append(diag_evt)
            try: save_mission_event_record(self.current_mission_id, diag_evt)
            except Exception: pass
        self.prev_diagnostics_set = curr_diag_set

        # Periodically update mission metadata summary
        if len(self.recorded_snapshots) % 10 == 0:
            self._update_mission_summary()

    def _update_mission_summary(self):
        duration = round(time.time() - self.start_ts, 1)
        summary = self.build_mission_summary()
        meta = {
            "mission_id": self.current_mission_id,
            "session_id": self.session_id,
            "start_time": self.start_wall_time,
            "end_time": datetime.now().isoformat(),
            "duration": duration,
            "telemetry_source": self.telemetry_source,
            "analytics_dataset": self.analytics_dataset,
            "initial_scenario": self.initial_scenario,
            "final_state": self.prev_state or "NORMAL",
            "min_health": round(self.min_health, 1),
            "max_anomaly": round(self.max_anomaly, 3),
            "rul_start": self.rul_start,
            "rul_end": self.rul_end,
            "frame_count": len(self.recorded_snapshots),
            "summary_json": summary
        }
        try:
            save_mission_record(meta)
        except Exception as e:
            print(f"[UPDATE MISSION RECORD ERROR] {e}")

    def finalize_current_mission(self):
        """Finalizes current mission recording with MISSION_END event."""
        if not self.recorded_snapshots:
            return
            
        end_seq = self.recorded_snapshots[-1].get("sequence_number", 0)
        end_ts = self.recorded_snapshots[-1].get("timestamp", 0.0)
        
        end_evt = {
            "event_id": f"EVT_{self.current_mission_id}_END",
            "mission_id": self.current_mission_id,
            "sequence_number": end_seq,
            "twin_timestamp": end_ts,
            "event_type": "MISSION_END",
            "subsystem": "GLOBAL_SYSTEM",
            "component": "ENGINE",
            "details": f"Mission {self.current_mission_id} completed with {len(self.recorded_snapshots)} recorded frames"
        }
        self.recorded_events.append(end_evt)
        try: save_mission_event_record(self.current_mission_id, end_evt)
        except Exception: pass
        
        self._update_mission_summary()
        print(f"[MISSION RECORDER] Finalized mission {self.current_mission_id}")

    def build_mission_summary(self, snapshots: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Calculates exact summary report metrics strictly from recorded frames and events."""
        duration = round(time.time() - self.start_ts, 1)
        target_snapshots = snapshots if snapshots is not None else list(self.recorded_snapshots)
        frames_count = len(target_snapshots)
        
        scenarios_seen = []
        for f in target_snapshots:
            sc = f.get("scenario")
            sc_id = sc.get("id") if isinstance(sc, dict) else str(sc or "CRUISE")
            if not scenarios_seen or scenarios_seen[-1] != sc_id:
                scenarios_seen.append(sc_id)
                
        warning_count = sum(1 for e in self.recorded_events if "WARNING" in e.get("event_type", "") or e.get("event_type") == "PREDICTIVE_WARNING")
        fault_count = sum(1 for e in self.recorded_events if "FAULT" in e.get("event_type", ""))
        critical_count = sum(1 for e in self.recorded_events if "CRITICAL" in e.get("event_type", ""))
        recovery_count = sum(1 for e in self.recorded_events if e.get("event_type") == "STATE_RECOVERY" or e.get("event_type") == "ALL_FAULTS_CLEARED")
        
        timeline_markers = []
        for idx, evt in enumerate(self.recorded_events):
            color = "#059669"
            etype = evt.get("event_type", "GENERIC")
            if "CRITICAL" in etype or "FAULT_INJECTION_STARTED" in etype:
                color = "#dc2626"
            elif "WARNING" in etype or "CAUTION" in etype:
                color = "#ea580c"
            elif "WATCH" in etype or "SCENARIO" in etype:
                color = "#0284c7"
                
            timeline_markers.append({
                "event_id": evt.get("event_id", f"EVT_{idx}"),
                "frame_index": evt.get("sequence_number", idx),
                "sequence_number": evt.get("sequence_number", idx),
                "timestamp": evt.get("twin_timestamp", 0.0),
                "event_type": etype,
                "subsystem": evt.get("subsystem", "SYSTEM"),
                "component": evt.get("component", "ENGINE"),
                "label": f"{etype.replace('_', ' ').title()} ({evt.get('component', 'ENGINE')})",
                "color": color,
                "description": evt.get("details", "")
            })
            
        telem_source_label = "Reference Aero-Piston Physics Simulator" if self.telemetry_source == "SIMULATOR" else str(self.telemetry_source)
        analytics_label = "NASA C-MAPSS FD001 — analogue prognostics" if self.analytics_dataset == "CMAPSS" else f"{self.analytics_dataset} Dataset"

        return {
            "title": f"Recorded Mission Summary — {self.current_mission_id}",
            "mission_id": self.current_mission_id,
            "session_id": self.session_id,
            "aircraft_callsign": "MALE-UAV-REF-01",
            "telemetry_source": self.telemetry_source,
            "analytics_dataset": self.analytics_dataset,
            "telemetry_source_label": telem_source_label,
            "analytics_dataset_label": analytics_label,
            "data_source": f"{telem_source_label} & {analytics_label}",
            "duration_seconds": duration,
            "frame_count": frames_count,
            "total_frames": frames_count,
            "scenario_history": scenarios_seen,
            "minimum_health_index_pct": round(self.min_health, 1),
            "maximum_anomaly_score": round(self.max_anomaly, 3),
            "maximum_predictive_risk": round(self.max_predictive_risk, 2),
            "rul_start_cycles": self.rul_start,
            "rul_end_cycles": self.rul_end,
            "predictive_warnings_count": warning_count,
            "diagnosed_faults_count": fault_count,
            "critical_events_count": critical_count,
            "fault_injection_count": fault_count,
            "recovery_count": recovery_count,
            "timeline_markers": timeline_markers,
            "recorded_events": self.recorded_events,
            "disclaimer_notice": "PROTOTYPE / DECISION-SUPPORT ONLY. NOT FLIGHT-CERTIFIED. NOT CONNECTED TO OPERATIONAL UAV."
        }

mission_recorder_instance = MissionRecorder()
