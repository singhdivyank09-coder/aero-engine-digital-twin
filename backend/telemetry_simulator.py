"""
Real-Time Telemetry Simulator & Signal Processing Pipeline
Provides:
- Raw telemetry ingestion (Dataset or Physics-based 10Hz stream)
- Signal validation & 3-sample median filtering for isolated single-spike noise
- Exponential Moving Average (EMA) display smoothing (alpha = 0.25)
- Preservation of original raw telemetry alongside smoothed display values
- Time-dependent fault profiles (sudden, gradual ramp, intermittent, sensor drift, thermal rise, pressure decay)
  Modifying physics inputs ONLY (never hardcoding health or anomaly output scores)
"""

import math
import time
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from collections import deque
from ml_service.canonical_schema import CanonicalEngineState
from ml_service.dataset_loader import CMapssDatasetLoader, AlfaDatasetLoader, RflyMadDatasetLoader, UavFdDatasetLoader
from backend.metrics_tracker import metrics_tracker_instance

class TelemetrySimulator:
    SIGNAL_KEYS = [
        "rpm", "map", "cht1", "cht2", "cht3", "cht4",
        "egt1", "egt2", "egt3", "egt4", "oil_press", "oil_temp",
        "fuel_flow", "vibration_rms", "battery_volt"
    ]

    def __init__(self):
        self.mode = "NOMINAL_CRUISE"
        self.mission_profile = "CRUISE"
        self.telemetry_source = "SIMULATOR"  # SIMULATOR or REPLAY
        self.analytics_dataset = "CMAPSS"    # CMAPSS, ALFA, RFLYMAD, UAVFD

        self.raw_history = {k: deque(maxlen=5) for k in self.SIGNAL_KEYS}
        self.smoothed_state = {k: None for k in self.SIGNAL_KEYS}

        self.cmapss_loader = CMapssDatasetLoader()
        self.alfa_loader = AlfaDatasetLoader()
        self.rflymad_loader = RflyMadDatasetLoader()
        self.uavfd_loader = UavFdDatasetLoader()

        self.dataset_generator = None
        self.step_counter = 0
        self.active_fault_profile = "NONE"
        self.current_fault_id = "FLT_NONE"
        # Fault Injection Controller State & Event Log
        self.fault_config = {
            "scenario": "NONE",        # CYLINDER_THERMAL, OIL_PRESSURE, INCREASING_VIBRATION, SENSOR_DRIFT, INTERMITTENT_COMBUSTION, INJECTOR_DISTURBANCE
            "component": "CYLINDER_1",  # CYLINDER_1, CYLINDER_2, CYLINDER_3, CYLINDER_4, OIL_SYSTEM, MECHANICAL_BEARING, ELECTRICAL_BUS
            "profile": "GRADUAL",       # SUDDEN, GRADUAL, INTERMITTENT
            "intensity": 1.0,           # 0.1 to 2.0
            "rate": "MODERATE",         # FAST (5s), MODERATE (15s), SLOW (30s)
            "status": "IDLE"            # IDLE, RUNNING, PAUSED, CLEARED
        }
        self.fault_start_time = 0.0
        self.fault_paused_time = 0.0
        self.total_paused_duration = 0.0
        self.fault_event_log = []

    def reset(self):
        """Resets all simulator buffers, smoothed states, step counters, and fault configurations."""
        self.mode = "NOMINAL_CRUISE"
        self.mission_profile = "CRUISE"
        self.telemetry_source = "SIMULATOR"
        self.analytics_dataset = "CMAPSS"
        self.step_counter = 0
        self.active_fault_profile = "NONE"
        self.current_fault_id = "FLT_NONE"
        self.fault_config = {
            "scenario": "NONE",
            "component": "CYLINDER_1",
            "profile": "GRADUAL",
            "intensity": 1.0,
            "rate": "MODERATE",
            "status": "IDLE"
        }
        self.fault_start_time = 0.0
        self.fault_paused_time = 0.0
        self.total_paused_duration = 0.0
        self.fault_event_log = []
        self.raw_history = {k: deque(maxlen=5) for k in self.SIGNAL_KEYS}
        self.smoothed_state = {k: None for k in self.SIGNAL_KEYS}

    def set_telemetry_source(self, source: str):
        if source in ["SIMULATOR", "REPLAY"]:
            self.telemetry_source = source

    def set_analytics_dataset(self, dataset: str):
        if dataset in ["CMAPSS", "ALFA", "RFLYMAD", "UAVFD"]:
            self.analytics_dataset = dataset

    def set_mode(self, mode: str):
        self.mode = mode
        if mode in ["SIMULATOR", "NOMINAL_CRUISE"]:
            self.telemetry_source = "SIMULATOR"
        elif mode in ["REPLAY", "HISTORICAL"]:
            self.telemetry_source = "REPLAY"
        elif mode.startswith("DATASET_CMAPSS") or mode == "CMAPSS":
            self.analytics_dataset = "CMAPSS"
        elif mode == "DATASET_ALFA_1" or mode == "ALFA":
            self.analytics_dataset = "ALFA"
        elif mode == "DATASET_RFLYMAD_1" or mode == "RFLYMAD":
            self.analytics_dataset = "RFLYMAD"
        elif mode == "DATASET_UAVFD_1" or mode == "UAVFD":
            self.analytics_dataset = "UAVFD"

    def start_fault_injection(
        self,
        scenario: str,
        component: str = "CYLINDER_1",
        profile: str = "GRADUAL",
        intensity: float = 1.0,
        rate: str = "MODERATE",
        ramp_duration: Optional[float] = None
    ) -> Dict[str, Any]:
        curr_time = self.step_counter * 0.1
        
        if ramp_duration is not None:
            actual_ramp_duration = float(ramp_duration)
        elif isinstance(rate, (int, float)):
            actual_ramp_duration = float(rate)
        elif str(rate).upper() in ["SLOW", "60S", "60"]:
            actual_ramp_duration = 60.0
        elif str(rate).upper() in ["FAST", "5S", "5"]:
            actual_ramp_duration = 5.0
        else:  # MODERATE
            actual_ramp_duration = 15.0

        if not hasattr(self, "active_faults"):
            self.active_faults = []

        from backend.fault_registry import get_fault_spec, resolve_fault_id
        canon_scenario = resolve_fault_id(scenario)
        spec = get_fault_spec(canon_scenario)
        aff_sub = spec.get("subsystem", "COMBUSTION") if spec else "THERMAL"

        comp_str = str(component).upper()
        cyl_num = "1"
        if "2" in comp_str: cyl_num = "2"
        elif "3" in comp_str: cyl_num = "3"
        elif "4" in comp_str: cyl_num = "4"
        elif "1" in comp_str: cyl_num = "1"

        resolved_idx = int(cyl_num) - 1

        if canon_scenario in ["CYLINDER_THERMAL_DEGRADATION"]:
            res_comp = f"CYLINDER_{cyl_num}"
            mutated = [f"cht{cyl_num}", f"egt{cyl_num}", "oil_temp"]
        elif canon_scenario in ["OIL_PRESSURE_DEGRADATION"]:
            res_comp = "OIL_SYSTEM"
            resolved_idx = 0
            mutated = ["oil_press", "oil_temp"]
        elif canon_scenario in ["INCREASING_VIBRATION"]:
            res_comp = "CRANKSHAFT_BEARING_ASSEMBLY"
            resolved_idx = 0
            mutated = ["vibration_rms"]
        elif canon_scenario in ["SENSOR_DRIFT"]:
            res_comp = component.upper()
            resolved_idx = 0
            mutated = ["sensor_signal"]
        elif canon_scenario in ["INTERMITTENT_COMBUSTION", "CYLINDER_MISFIRE"]:
            res_comp = f"CYLINDER_{cyl_num}"
            mutated = [f"egt{cyl_num}", "vibration_rms"]
        elif canon_scenario in ["FUEL_INJECTOR_ABNORMALITY"]:
            res_comp = f"INJECTOR_CYL_{cyl_num}"
            mutated = ["fuel_flow", f"egt{cyl_num}", f"cht{cyl_num}"]
        elif canon_scenario in ["ELECTRICAL_BUS_VOLTAGE_DEGRADATION"]:
            res_comp = "ELECTRICAL_BUS"
            resolved_idx = 0
            mutated = ["battery_volt"]
        else:
            res_comp = component
            mutated = ["telemetry"]


        injection_id = f"INJ_{int(curr_time * 10)}_{len(self.fault_event_log) + 1}"
        self.current_fault_id = injection_id

        print(f"[FAULT_START_REQUEST] injection_id={injection_id} scenario={scenario} component={component} profile={profile} intensity={intensity} rate={rate}")

        wall_now = time.time()
        fault_entry = {
            "injection_id": injection_id,
            "fault_id": injection_id,
            "scenario": scenario,
            "fault_type": scenario,
            "affected_subsystem": aff_sub,
            "component": component,
            "affected_component": component,
            "requested_component": component,
            "resolved_component": res_comp,
            "resolved_index": resolved_idx,
            "mutated_signal_names": mutated,
            "start_time": curr_time,
            "start_timestamp": curr_time,
            "start_wall_time": wall_now,
            "profile": profile,
            "progression_rate": str(rate),
            "intensity": float(intensity),
            "ramp_duration": actual_ramp_duration,
            "current_effect": 0.0,
            "current_effect_pct": 0.0,
            "elapsed_seconds": 0.0,
            "status": "RUNNING",
            "fault_paused_time": 0.0,
            "total_paused_duration": 0.0,
            "fault_paused_wall_time": 0.0,
            "total_paused_wall_duration": 0.0
        }

        self.active_faults.append(fault_entry)
        self.fault_config = fault_entry
        self.active_fault_profile = scenario
        self.fault_start_time = curr_time

        target_input = self._determine_target_signal(scenario, component)
        
        event_entry = {
            "injection_id": injection_id,
            "fault_id": injection_id,
            "event_id": injection_id,
            "timestamp": f"{round(curr_time, 1)}s",
            "start_time": f"{round(curr_time, 1)}s",
            "start_timestamp": curr_time,
            "fault_scenario": scenario.replace("_", " ").title(),
            "fault_type": scenario,
            "scenario": scenario,
            "affected_component": component,
            "affected_input": target_input,
            "profile": profile.title(),
            "injection_profile": profile.title(),
            "configured_intensity": float(intensity),
            "intensity": f"{int(float(intensity) * 100)}%",
            "ramp_duration": f"{round(actual_ramp_duration, 1)}s",
            "progression_rate": str(rate).title(),
            "status": "RUNNING",
            "cleared_time": "ACTIVE"
        }
        self.fault_event_log.append(event_entry)

        print(f"[FAULT_REGISTERED] injection_id={injection_id} scenario={scenario} component={component} target_input={target_input}")
        return fault_entry

    def pause_fault_injection(self) -> Dict[str, Any]:
        curr_time = self.step_counter * 0.1
        if hasattr(self, "active_faults"):
            for f in self.active_faults:
                f_id = f.get("injection_id") or f.get("fault_id")
                if f.get("status") in ["RUNNING", "INJECTING"]:
                    f["status"] = "PAUSED"
                    f["fault_paused_time"] = curr_time
                    for ev in self.fault_event_log:
                        if (ev.get("injection_id") == f_id or ev.get("fault_id") == f_id) and ev.get("status") != "CLEARED":
                            ev["status"] = "PAUSED"
                elif f.get("status") == "PAUSED":
                    f["status"] = "INJECTING"
                    f["total_paused_duration"] += (curr_time - f.get("fault_paused_time", curr_time))
                    for ev in self.fault_event_log:
                        if (ev.get("injection_id") == f_id or ev.get("fault_id") == f_id) and ev.get("status") != "CLEARED":
                            ev["status"] = "RUNNING"
        return self.fault_config

    def resume_fault_injection(self) -> Dict[str, Any]:
        curr_time = self.step_counter * 0.1
        if hasattr(self, "active_faults"):
            for f in self.active_faults:
                f_id = f.get("injection_id") or f.get("fault_id")
                if f.get("status") == "PAUSED":
                    f["status"] = "INJECTING"
                    f["total_paused_duration"] += (curr_time - f.get("fault_paused_time", curr_time))
                    for ev in self.fault_event_log:
                        if (ev.get("injection_id") == f_id or ev.get("fault_id") == f_id) and ev.get("status") != "CLEARED":
                            ev["status"] = "RUNNING"
        return self.fault_config

    def clear_fault_injection(self, injection_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Clears fault injections from authoritative active registry and synchronizes historical log.
        If injection_id is specified, clears that specific active injection.
        If injection_id is None, clears ALL active fault injections atomically.
        """
        curr_time = self.step_counter * 0.1
        if not hasattr(self, "active_faults"):
            self.active_faults = []

        cleared_ids = []

        if injection_id:
            to_clear = [f for f in self.active_faults if f.get("injection_id") == injection_id or f.get("fault_id") == injection_id]
            for f in to_clear:
                f_id = f.get("injection_id") or f.get("fault_id")
                cleared_ids.append(f_id)
                f["status"] = "CLEARED"
                f["clear_time"] = curr_time
            self.active_faults = [f for f in self.active_faults if f not in to_clear]
        else:
            for f in self.active_faults:
                f_id = f.get("injection_id") or f.get("fault_id")
                cleared_ids.append(f_id)
                f["status"] = "CLEARED"
                f["clear_time"] = curr_time
            self.active_faults.clear()

        # Update matching historical records in self.fault_event_log
        for event in self.fault_event_log:
            ev_id = event.get("injection_id") or event.get("fault_id")
            if (not injection_id and event.get("status") in ["RUNNING", "PAUSED", "INJECTING"]) or (injection_id and ev_id in cleared_ids):
                event["status"] = "CLEARED"
                event["cleared_time"] = f"{round(curr_time, 1)}s"
                event["clear_timestamp"] = curr_time
                if "start_timestamp" in event:
                    event["duration_seconds"] = round(curr_time - event["start_timestamp"], 1)

        # Invariant Check: Reconcile any orphan RUNNING/PAUSED historical rows
        active_ids = {f.get("injection_id") or f.get("fault_id") for f in self.active_faults}
        for event in self.fault_event_log:
            ev_id = event.get("injection_id") or event.get("fault_id")
            if event.get("status") in ["RUNNING", "PAUSED", "INJECTING"] and ev_id not in active_ids:
                print(f"[FAULT_REGISTRY_INCONSISTENCY] Reconciling orphan running status for event {ev_id}")
                event["status"] = "CLEARED"
                event["cleared_time"] = f"{round(curr_time, 1)}s"

        self.fault_config = {
            "fault_id": "NONE",
            "injection_id": "NONE",
            "scenario": "NONE",
            "component": "NONE",
            "profile": "NONE",
            "intensity": 0.0,
            "status": "CLEARED"
        }
        self.active_fault_profile = "NONE"

        print(f"[FAULT_CLEARED] injection_ids={cleared_ids} session_time={round(curr_time, 1)}s")

        return {
            "status": "success",
            "success": True,
            "cleared_count": len(cleared_ids),
            "cleared_injection_ids": cleared_ids,
            "remaining_active_count": len(self.active_faults),
            "session_time": round(curr_time, 1),
            "fault_config": self.fault_config
        }

    def set_fault_profile(self, profile: str):
        self.start_fault_injection(scenario=profile, component="CYLINDER_1", profile="GRADUAL", intensity=1.0, rate="MODERATE")

    def set_fault(self, fault_type: str):
        if fault_type in ["NONE", "CLEAR"]:
            self.clear_fault_injection()
            return
        mapping = {
            "MISFIRE": ("INTERMITTENT_COMBUSTION", "CYLINDER_3"),
            "INJECTOR_ABNORMALITY": ("INJECTOR_DISTURBANCE", "CYLINDER_2"),
            "OIL_PRESSURE_DROP": ("OIL_PRESSURE", "OIL_SYSTEM"),
            "OVERHEATING": ("CYLINDER_THERMAL", "CYLINDER_1"),
            "VIBRATION_SPIKE": ("INCREASING_VIBRATION", "MECHANICAL_BEARING"),
            "SENSOR_DRIFT": ("SENSOR_DRIFT", "ELECTRICAL_BUS")
        }
        scen, comp = mapping.get(fault_type, (fault_type, "CYLINDER_1"))
        self.start_fault_injection(scenario=scen, component=comp, profile="GRADUAL", intensity=1.0, rate="MODERATE")

    def set_mission_profile(self, profile: str):
        self.mission_profile = profile

    def _determine_target_signal(self, scenario: str, component: str) -> str:
        comp_map = {
            "CYLINDER_1": "CHT1", "CYLINDER_2": "CHT2", "CYLINDER_3": "CHT3", "CYLINDER_4": "CHT4",
            "OIL_SYSTEM": "Oil Pressure", "MECHANICAL_BEARING": "Vibration RMS", "ELECTRICAL_BUS": "Battery Voltage"
        }
        if scenario in ["CYLINDER_THERMAL", "OVERHEATING"]:
            return comp_map.get(component, "CHT1")
        elif scenario in ["OIL_PRESSURE", "OIL_PRESSURE_DROP"]:
            return "Oil Pressure"
        elif scenario in ["INCREASING_VIBRATION", "VIBRATION_SPIKE"]:
            return "Vibration RMS"
        elif scenario in ["SENSOR_DRIFT"]:
            return "Battery Voltage"
        elif scenario in ["INTERMITTENT_COMBUSTION", "MISFIRE"]:
            return f"EGT ({comp_map.get(component, 'Cylinder 3')}) & Vibration"
        elif scenario in ["INJECTOR_DISTURBANCE", "INJECTOR_ABNORMALITY"]:
            return f"Fuel Flow & EGT ({comp_map.get(component, 'Cylinder 2')})"
        return "Input Telemetry Signal"

    def _apply_time_dependent_fault(self, raw_telemetry: Dict[str, Any], t: float) -> Dict[str, Any]:
        """
        Applies time-dependent physical bias profiles to raw input telemetry for ALL active faults concurrently.
        Modifies simulator physics input ONLY (never hardcodes health, state, or anomaly scores).
        """
        if not hasattr(self, "active_faults") or not self.active_faults:
            scenario = self.fault_config.get("scenario", "NONE")
            status = self.fault_config.get("status", "IDLE")
            if scenario == "NONE" or status in ["IDLE", "CLEARED"]:
                return raw_telemetry
            fault_list = [self.fault_config]
        else:
            fault_list = [f for f in self.active_faults if f.get("status") in ["RUNNING", "INJECTING", "PAUSED"]]

        if not fault_list:
            return raw_telemetry

        telem = raw_telemetry.copy()

        for fault in fault_list:
            scenario = fault.get("scenario", "NONE")
            status = fault.get("status", "RUNNING")
            if scenario == "NONE" or status in ["IDLE", "CLEARED"]:
                continue

            f_start = float(fault.get("start_time", t))
            f_paused_time = float(fault.get("fault_paused_time", 0.0))
            f_total_paused = float(fault.get("total_paused_duration", 0.0))

            f_start_wall = fault.get("start_wall_time")
            f_paused_wall = fault.get("fault_paused_wall_time", 0.0)
            f_total_paused_wall = fault.get("total_paused_wall_duration", 0.0)

            if status == "PAUSED":
                t_elapsed_sim = max(0.0, f_paused_time - f_start - f_total_paused)
                t_elapsed_wall = max(0.0, f_paused_wall - f_start_wall - f_total_paused_wall) if f_start_wall else t_elapsed_sim
            else:
                t_elapsed_sim = max(0.0, t - f_start - f_total_paused)
                t_elapsed_wall = max(0.0, time.time() - f_start_wall - f_total_paused_wall) if f_start_wall else t_elapsed_sim

            t_elapsed = max(t_elapsed_sim, t_elapsed_wall)

            profile = fault.get("profile", "GRADUAL")
            intensity = float(fault.get("intensity", 1.0))
            component = fault.get("component") or fault.get("affected_component") or "CYLINDER_1"
            ramp_duration = float(fault.get("ramp_duration", 15.0))

            if profile.upper() == "SUDDEN":
                progress = 1.0
            elif profile.upper() == "INTERMITTENT":
                pulse = math.sin(t_elapsed * 1.5) > 0.3
                progress = 1.0 if pulse else 0.0
            else:  # GRADUAL
                progress = min(1.0, t_elapsed / max(0.1, ramp_duration))

            current_effect = round(progress * 100.0, 1)
            fault["current_effect"] = current_effect
            fault["current_effect_pct"] = current_effect
            fault["elapsed_seconds"] = round(t_elapsed, 1)

            # Helper for explicit cylinder index resolution
            comp_str = str(component).upper()
            cyl_num = "1"
            if "CYLINDER_2" in comp_str or comp_str == "CYLINDER 2" or comp_str == "2":
                cyl_num = "2"
            elif "CYLINDER_3" in comp_str or comp_str == "CYLINDER 3" or comp_str == "3":
                cyl_num = "3"
            elif "CYLINDER_4" in comp_str or comp_str == "CYLINDER 4" or comp_str == "4":
                cyl_num = "4"
            elif "CYLINDER_1" in comp_str or comp_str == "CYLINDER 1" or comp_str == "1":
                cyl_num = "1"
            elif "2" in comp_str:
                cyl_num = "2"
            elif "3" in comp_str:
                cyl_num = "3"
            elif "4" in comp_str:
                cyl_num = "4"

            resolved_index = int(cyl_num) - 1

            from backend.fault_registry import resolve_fault_id
            canon_scenario = resolve_fault_id(scenario)

            # 1. CYLINDER THERMAL DEGRADATION
            if canon_scenario in ["CYLINDER_THERMAL_DEGRADATION"]:
                target_key = f"cht{cyl_num}"
                egt_key = f"egt{cyl_num}"
                fault["requested_component"] = component
                fault["resolved_component"] = f"CYLINDER_{cyl_num}"
                fault["resolved_index"] = resolved_index
                fault["mutated_signal_names"] = [target_key, egt_key, "oil_temp"]

                cht_offset = intensity * 55.0 * progress
                telem[target_key] = float(telem.get(target_key, 120.0)) + cht_offset
                egt_coupling = (cht_offset * 1.5) * (t_elapsed / (t_elapsed + 5.0))
                telem[egt_key] = float(telem.get(egt_key, 748.0)) + egt_coupling
                telem["oil_temp"] = float(telem.get("oil_temp", 88.5)) + (cht_offset * 0.20)

            # 2. LUBRICATION DEGRADATION
            elif canon_scenario in ["OIL_PRESSURE_DEGRADATION"]:
                fault["requested_component"] = component
                fault["resolved_component"] = "OIL_SYSTEM"
                fault["resolved_index"] = 0
                fault["mutated_signal_names"] = ["oil_press", "oil_temp"]

                p_drop = intensity * 2.2 * progress
                telem["oil_press"] = max(1.1, float(telem.get("oil_press", 4.2)) - p_drop)
                telem["oil_temp"] = float(telem.get("oil_temp", 88.5)) + (p_drop * 10.0) * (t_elapsed / max(1.0, ramp_duration))

            # 3. INCREASING VIBRATION
            elif canon_scenario in ["INCREASING_VIBRATION"]:
                fault["requested_component"] = component
                fault["resolved_component"] = "CRANKSHAFT_BEARING_ASSEMBLY"
                fault["resolved_index"] = 0
                fault["mutated_signal_names"] = ["vibration_rms"]

                vib_bias = intensity * 1.8 * progress
                vib_variance = intensity * 0.12 * progress * np.random.normal(0, 1.0)
                vib_periodic = intensity * 0.35 * progress * math.sin(t_elapsed * 8.0)
                telem["vibration_rms"] = float(telem.get("vibration_rms", 1.12)) + vib_bias + vib_variance + vib_periodic

            # 4. SENSOR DRIFT (Instrumentation Bias - DOES NOT MODIFY REAL PHYSICAL ENGINE STATE)
            elif canon_scenario in ["SENSOR_DRIFT"]:
                fault["requested_component"] = component
                comp_u = str(component).upper()
                if "OIL" in comp_u: target_sig = "oil_press"
                elif "CHT1" in comp_u: target_sig = "cht1"
                elif "CHT2" in comp_u: target_sig = "cht2"
                elif "CHT3" in comp_u: target_sig = "cht3"
                elif "CHT4" in comp_u: target_sig = "cht4"
                elif "EGT1" in comp_u: target_sig = "egt1"
                elif "EGT2" in comp_u: target_sig = "egt2"
                elif "EGT3" in comp_u: target_sig = "egt3"
                elif "EGT4" in comp_u: target_sig = "egt4"
                elif "RPM" in comp_u: target_sig = "rpm"
                elif "MAP" in comp_u: target_sig = "map"
                elif "FUEL" in comp_u: target_sig = "fuel_flow"
                elif "VIBRATION" in comp_u: target_sig = "vibration_rms"
                else: target_sig = "battery_volt"

                fault["resolved_component"] = f"{target_sig.upper()}_SENSOR"
                fault["resolved_index"] = 0
                fault["mutated_signal_names"] = [target_sig]

                drift_mag = intensity * (1.8 if target_sig == "oil_press" else (2.8 if target_sig == "battery_volt" else 35.0)) * progress
                telem[target_sig] = float(telem.get(target_sig, 14.1)) - drift_mag

            # 5. INTERMITTENT COMBUSTION DISTURBANCE / MISFIRE
            elif canon_scenario in ["INTERMITTENT_COMBUSTION", "CYLINDER_MISFIRE"]:
                egt_key = f"egt{cyl_num}"
                cht_key = f"cht{cyl_num}"
                fault["requested_component"] = component
                fault["resolved_component"] = f"CYLINDER_{cyl_num}"
                fault["resolved_index"] = resolved_index
                fault["mutated_signal_names"] = [egt_key, cht_key, "vibration_rms"]

                pulse_active = (math.sin(t_elapsed * 1.5) > 0.3) if profile == "INTERMITTENT" else (progress > 0.1)
                if pulse_active:
                    egt_drop = intensity * 130.0 * (progress if profile != "INTERMITTENT" else 1.0)
                    vib_add = intensity * 1.5 * (progress if profile != "INTERMITTENT" else 1.0)
                    telem[egt_key] = max(550.0, float(telem.get(egt_key, 745.0)) - egt_drop)
                    telem["vibration_rms"] = float(telem.get("vibration_rms", 1.12)) + vib_add

            # 6. FUEL INJECTOR ABNORMALITY
            elif canon_scenario in ["FUEL_INJECTOR_ABNORMALITY"]:
                egt_key = f"egt{cyl_num}"
                cht_key = f"cht{cyl_num}"
                fault["requested_component"] = component
                fault["resolved_component"] = f"INJECTOR_CYL_{cyl_num}"
                fault["resolved_index"] = resolved_index
                fault["mutated_signal_names"] = ["fuel_flow", egt_key, cht_key]

                ff_delta = intensity * 4.5 * progress
                egt_delta = intensity * 85.0 * progress
                cht_delta = intensity * 25.0 * progress
                telem["fuel_flow"] = max(8.0, float(telem.get("fuel_flow", 17.5)) - ff_delta)
                telem[egt_key] = float(telem.get(egt_key, 748.0)) + egt_delta
                telem[cht_key] = float(telem.get(cht_key, 120.0)) + cht_delta

            # 7. ELECTRICAL BUS VOLTAGE DEGRADATION
            elif canon_scenario in ["ELECTRICAL_BUS_VOLTAGE_DEGRADATION"]:
                fault["requested_component"] = component
                fault["resolved_component"] = "ELECTRICAL_BUS"
                fault["resolved_index"] = 0
                fault["mutated_signal_names"] = ["battery_volt"]

                v_drop = intensity * 2.8 * progress
                telem["battery_volt"] = round(float(telem.get("battery_volt", 14.10)) - v_drop, 2)

            else:
                print(f"[RUNNING_FAULT_WITHOUT_PHYSICAL_EFFECT] Injection ID {fault.get('injection_id')} has unrecognized scenario {scenario}!")

            # Periodic Structured Trace Logs (t_elapsed milestones)
            last_logged = fault.get("_last_logged_milestone", -1.0)
            rounded_sec = int(round(t_elapsed))
            if rounded_sec in [1, 5, 10, 15, 20] and abs(t_elapsed - rounded_sec) < 0.15 and last_logged != rounded_sec:
                fault["_last_logged_milestone"] = float(rounded_sec)
                print(f"[FAULT_APPLIED_TO_SIMULATOR] injection_id={fault.get('injection_id')} scenario={scenario} effect={current_effect}% elapsed={t_elapsed:.1f}s")
                print(f"[FAULT_EFFECT_OBSERVED] injection_id={fault.get('injection_id')} mutated={fault.get('mutated_signal_names')}")

        # Apply Physical Plausible Model Bounds Clamping (Simulator Level)
        for i in range(1, 5):
            telem[f"cht{i}"] = max(80.0, min(220.0, float(telem.get(f"cht{i}", 120.0))))
            telem[f"egt{i}"] = max(400.0, min(950.0, float(telem.get(f"egt{i}", 750.0))))
        telem["oil_temp"] = max(50.0, min(150.0, float(telem.get("oil_temp", 88.5))))
        telem["oil_press"] = max(0.5, min(6.5, float(telem.get("oil_press", 4.2))))
        telem["vibration_rms"] = max(0.1, min(5.0, float(telem.get("vibration_rms", 1.12))))
        telem["battery_volt"] = max(9.0, min(18.0, float(telem.get("battery_volt", 14.10))))

        return telem

    def _process_signal_stability(self, raw_telemetry: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Applies:
        - 3-sample Median Filter to eliminate single isolated sensor noise spikes
        - EMA display smoothing (alpha = 0.25)
        - Preserves raw_telemetry vs display_telemetry separately
        """
        raw_copy = raw_telemetry.copy()
        display_copy = raw_telemetry.copy()

        alpha = 0.25  # EMA smoothing factor

        for k in self.SIGNAL_KEYS:
            if k not in raw_telemetry:
                continue

            val = float(raw_telemetry[k])
            self.raw_history[k].append(val)

            # 1. Median Filter (3 to 5 sample window)
            median_val = float(np.median(list(self.raw_history[k])))

            # 2. EMA Display Smoothing
            if self.smoothed_state[k] is None:
                self.smoothed_state[k] = median_val
            else:
                self.smoothed_state[k] = alpha * median_val + (1.0 - alpha) * self.smoothed_state[k]

            display_copy[k] = round(float(self.smoothed_state[k]), 2 if "press" in k or "volt" in k or "vib" in k or "map" in k else 1)

        return raw_copy, display_copy

    def get_next_frame(self) -> Dict[str, Any]:
        """Generates next 10Hz frame with raw and smoothed telemetry streams."""
        self.step_counter += 1
        t = self.step_counter * 0.1

        # Base Raw Telemetry Generation
        if self.mode.startswith("DATASET_") and self.dataset_generator:
            try:
                state = next(self.dataset_generator)
                base_raw = state.to_dict()
            except StopIteration:
                self.set_mode(self.mode)
                state = next(self.dataset_generator)
                base_raw = state.to_dict()
        else:
            # Baseline Physics Telemetry Generator
            if self.mission_profile == "HIGH_ALTITUDE":
                base_rpm, base_map, base_cht, base_egt, base_oil_p, base_oil_t, base_fuel = 5300.0, 1.32, 132.0, 780.0, 4.40, 94.0, 21.0
            elif self.mission_profile == "HOT_WEATHER":
                base_rpm, base_map, base_cht, base_egt, base_oil_p, base_oil_t, base_fuel = 4950.0, 1.15, 142.0, 765.0, 3.90, 105.0, 18.2
            elif self.mission_profile == "RAPID_THROTTLE":
                base_rpm = 4200.0 + (math.sin(t * 0.5) + 1.0) * 750.0
                base_map = 0.95 + (math.sin(t * 0.5) + 1.0) * 0.20
                base_cht, base_egt, base_oil_p, base_oil_t, base_fuel = 125.0 + math.sin(t * 0.2) * 8.0, 740.0 + math.sin(t * 0.2) * 35.0, 4.10, 90.0, 14.0
            else: # CRUISE / ENDURANCE
                base_rpm, base_map, base_cht, base_egt, base_oil_p, base_oil_t, base_fuel = 5000.0 + math.sin(t * 0.1) * 30.0, 1.15, 120.0, 748.0, 4.20, 88.5, 17.5

            base_raw = {
                "timestamp": round(t, 1),
                "sequence_no": self.step_counter,
                "sequence_number": self.step_counter,
                "engine_id": "ENG-001",
                "rpm": round(base_rpm + np.random.normal(0, 15), 1),
                "map": round(base_map + np.random.normal(0, 0.005), 3),
                "cht1": round(base_cht + np.random.normal(0, 0.4), 1),
                "cht2": round(base_cht + 0.8 + np.random.normal(0, 0.4), 1),
                "cht3": round(base_cht - 0.5 + np.random.normal(0, 0.4), 1),
                "cht4": round(base_cht + 0.2 + np.random.normal(0, 0.4), 1),
                "egt1": round(base_egt + np.random.normal(0, 1.5), 1),
                "egt2": round(base_egt + 2.0 + np.random.normal(0, 1.5), 1),
                "egt3": round(base_egt - 1.5 + np.random.normal(0, 1.5), 1),
                "egt4": round(base_egt + 1.0 + np.random.normal(0, 1.5), 1),
                "oil_press": round(base_oil_p + np.random.normal(0, 0.02), 2),
                "oil_temp": round(base_oil_t + np.random.normal(0, 0.1), 1),
                "fuel_flow": round(base_fuel + np.random.normal(0, 0.1), 2),
                "vibration_rms": round(1.12 + np.random.normal(0, 0.03), 2),
                "battery_volt": round(14.10 + np.random.normal(0, 0.02), 2),
                "injection_timing": 26.0
            }

        # Apply Time-Dependent Fault Injection to raw telemetry input
        faulted_raw = self._apply_time_dependent_fault(base_raw, t)

        # Apply Median Filtering & EMA Display Smoothing
        raw_telemetry, display_telemetry = self._process_signal_stability(faulted_raw)

        # Compute active_faults object array for active TwinSession from authoritative active registry
        if hasattr(self, "active_faults"):
            active_faults = [f for f in self.active_faults if f.get("status") in ["RUNNING", "INJECTING", "PAUSED"]]
        else:
            active_faults = []

        return {
            "sequence_no": self.step_counter,
            "sequence_number": self.step_counter,
            "raw_telemetry": raw_telemetry,
            "display_telemetry": display_telemetry,
            "telemetry": display_telemetry, # Default display stream
            "mission_profile": self.mission_profile,
            "active_fault_profile": self.active_fault_profile,
            "fault_config": self.fault_config,
            "active_faults": active_faults,
            "fault_event_log": self.fault_event_log,
            "telemetry_source": self.telemetry_source,
            "analytics_dataset": self.analytics_dataset
        }

simulator_instance = TelemetrySimulator()
