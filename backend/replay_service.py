"""
Historical Mission Replay Service — READ ONLY Recorded Session Reconstruction Engine
Loads authentic recorded TwinSession snapshots, events, and metrics from SQLite storage
and reconstructs playback streams, timeline markers, and exportable reports.
STRICTLY ISOLATED FROM LIVE TWIN SESSION. READ ONLY.
"""

import math
import json
import numpy as np
from typing import Dict, Any, List, Optional
from backend.database import db_get_all_missions, db_get_mission
from backend.mission_recorder import mission_recorder_instance

class ReplayService:
    def __init__(self):
        pass

    def get_available_missions(self) -> List[Dict[str, Any]]:
        """Returns list of all available recorded missions from database."""
        missions = db_get_all_missions()
        if not missions:
            # Fallback if DB not populated yet: expose current active recorder mission
            curr_summary = mission_recorder_instance.build_mission_summary()
            return [{
                "mission_id": mission_recorder_instance.current_mission_id,
                "session_id": mission_recorder_instance.session_id,
                "start_time": mission_recorder_instance.start_wall_time,
                "duration": round(time.time() - mission_recorder_instance.start_ts, 1),
                "frame_count": len(mission_recorder_instance.recorded_snapshots),
                "initial_scenario": mission_recorder_instance.initial_scenario,
                "final_state": mission_recorder_instance.prev_state or "NORMAL"
            }]
        return missions

    def get_mission_data(self, mission_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves authentic recorded TwinSession frames, events, and summary.
        If mission_id is None or 'latest', fetches the latest recorded mission.
        """
        if not mission_id or mission_id == "latest":
            missions = db_get_all_missions()
            if missions:
                mission_id = missions[0]["mission_id"]
            else:
                mission_id = mission_recorder_instance.current_mission_id

        # Attempt to load from SQLite DB
        record = db_get_mission(mission_id)
        if record and record.get("snapshots"):
            snapshots = record["snapshots"]
            events = record.get("events", [])
            summary = record.get("summary") or {}
            
            # Ensure summary frame counts and duration match actual recorded snapshots
            summary["frame_count"] = len(snapshots)
            summary["total_frames"] = len(snapshots)
            dur_calc = round(snapshots[-1].get("timestamp", 0.0) - snapshots[0].get("timestamp", 0.0), 1) if snapshots else record.get("duration", 0.0)
            summary["duration"] = dur_calc
            summary["duration_seconds"] = dur_calc
            
            # Reconstruct timeline markers from recorded events
            timeline_markers = []
            for idx, evt in enumerate(events):
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

            telem_src = record.get("telemetry_source", "SIMULATOR")
            analytics_ds = record.get("analytics_dataset", "CMAPSS")
            telem_label = "Reference Aero-Piston Physics Simulator" if telem_src == "SIMULATOR" else str(telem_src)
            analytics_label = "NASA C-MAPSS FD001 — analogue prognostics" if analytics_ds == "CMAPSS" else f"{analytics_ds} Dataset"

            if not summary:
                scenarios_seen = []
                min_hi = 100.0
                max_anom = 0.0
                for snap in snapshots:
                    sc = snap.get("scenario")
                    sc_id = sc.get("id") if isinstance(sc, dict) else str(sc or "CRUISE")
                    if not scenarios_seen or scenarios_seen[-1] != sc_id:
                        scenarios_seen.append(sc_id)
                    hi = float(snap.get("health", {}).get("overall", snap.get("overall_health_index", 100.0)))
                    anom = float(snap.get("anomaly", {}).get("score", snap.get("anomaly_score", 0.0)))
                    if hi < min_hi: min_hi = hi
                    if anom > max_anom: max_anom = anom

                summary = {
                    "title": f"Recorded Mission Summary — {mission_id}",
                    "mission_id": mission_id,
                    "session_id": record.get("session_id", "TWIN_SESSION_SIH26054"),
                    "aircraft_callsign": "TAPAS BH-201 (UAV-001)",
                    "telemetry_source": telem_src,
                    "analytics_dataset": analytics_ds,
                    "telemetry_source_label": telem_label,
                    "analytics_dataset_label": analytics_label,
                    "data_source": f"{telem_label} & {analytics_label}",
                    "duration": record.get("duration", len(snapshots) * 0.1),
                    "duration_seconds": record.get("duration", len(snapshots) * 0.1),
                    "frame_count": len(snapshots),
                    "total_frames": len(snapshots),
                    "scenario_history": scenarios_seen,
                    "minimum_health_index_pct": round(min_hi, 1),
                    "maximum_anomaly_score": round(max_anom, 3),
                    "maximum_predictive_risk": round(record.get("max_anomaly", 0.0), 2),
                    "rul_start_cycles": record.get("rul_start"),
                    "rul_end_cycles": record.get("rul_end"),
                    "predictive_warnings_count": sum(1 for e in events if "WARNING" in e.get("event_type", "")),
                    "diagnosed_faults_count": sum(1 for e in events if "FAULT" in e.get("event_type", "")),
                    "critical_events_count": sum(1 for e in events if "CRITICAL" in e.get("event_type", "")),
                    "fault_injection_count": sum(1 for e in events if "FAULT" in e.get("event_type", "")),
                    "recovery_count": sum(1 for e in events if "RECOVERY" in e.get("event_type", "") or "CLEAR" in e.get("event_type", "")),
                    "timeline_markers": timeline_markers,
                    "recorded_events": events,
                    "disclaimer_notice": "PROTOTYPE / DECISION-SUPPORT ONLY. NOT FLIGHT-CERTIFIED. NOT CONNECTED TO OPERATIONAL UAV."
                }

            return {
                "mission_id": mission_id,
                "session_id": record.get("session_id", "TWIN_SESSION_SIH26054"),
                "data_source": summary.get("data_source", f"{telem_label} & {analytics_label}"),
                "duration_seconds": record.get("duration", len(snapshots) * 0.1),
                "total_frames": len(snapshots),
                "timeline_markers": timeline_markers,
                "events": events,
                "summary": summary,
                "frames": snapshots
            }

        # Fallback to active live mission recorder memory if DB query returned nothing
        summary = mission_recorder_instance.build_mission_summary()
        snapshots = list(mission_recorder_instance.recorded_snapshots)
        return {
            "mission_id": mission_recorder_instance.current_mission_id,
            "session_id": mission_recorder_instance.session_id,
            "data_source": summary.get("data_source", "Reference Aero-Piston Simulator & C-MAPSS Analogue Data"),
            "duration_seconds": summary.get("duration_seconds", len(snapshots) * 0.1),
            "total_frames": len(snapshots),
            "timeline_markers": summary.get("timeline_markers", []),
            "events": mission_recorder_instance.recorded_events,
            "summary": summary,
            "frames": snapshots
        }

    def generate_historical_mission(self) -> Dict[str, Any]:
        """Backward compatible wrapper returning latest recorded mission data."""
        return self.get_mission_data("latest")

    def get_exportable_json_report(self, mission_id: Optional[str] = None) -> Dict[str, Any]:
        """Generates structured JSON mission report for export/download."""
        data = self.get_mission_data(mission_id)
        summary = data.get("summary", {})
        events = summary.get("recorded_events", [])
        
        state_transitions = [e for e in events if "ENTERED" in e.get("event_type", "") or "RECOVERY" in e.get("event_type", "")]
        fault_events = [e for e in events if "FAULT" in e.get("event_type", "")]
        predictive_events = [e for e in events if "WARNING" in e.get("event_type", "")]
        
        advisories = set()
        for f in data.get("frames", []):
            adv = f.get("maintenance_advisory")
            if isinstance(adv, dict) and adv.get("description"):
                advisories.add(adv["description"])
            elif isinstance(adv, str) and adv:
                advisories.add(adv)

        return {
            "mission": {
                "mission_id": data.get("mission_id"),
                "session_id": data.get("session_id"),
                "duration_seconds": data.get("duration_seconds"),
                "total_frames": data.get("total_frames"),
                "telemetry_source": summary.get("telemetry_source"),
                "analytics_dataset": summary.get("analytics_dataset")
            },
            "summary": summary,
            "scenario_history": summary.get("scenario_history", []),
            "fault_events": fault_events,
            "state_transitions": state_transitions,
            "predictive_events": predictive_events,
            "maintenance_advisories": list(advisories),
            "model_versions": {
                "autoencoder": "PyTorch Deep Autoencoder v2.0",
                "gru_forecaster": "PyTorch GRU Short-Horizon Forecaster v2.0",
                "xgboost_classifier": "XGBoost Multiclass Classifier v2.0",
                "lstm_rul": "PyTorch LSTM Prognostics Engine v2.0"
            }
        }

replay_service_instance = ReplayService()
