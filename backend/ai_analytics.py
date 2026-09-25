import math
import numpy as np
from typing import Dict, List, Any

class AeroEngineAIAnalytics:
    def __init__(self):
        self.nominal_rul_hours = 1200.0 # TBO (Time Between Overhaul) baseline for Rotax aero piston engine

    def analyze_engine_state(self, telemetry: Dict[str, Any], physics_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes AI diagnostics comparing telemetry to physics predictions,
        calculating 5 subsystem health indices, anomaly score, prototype RUL, and XAI advisory.
        """
        rpm = telemetry.get("rpm", 5000)
        cht_vals = [telemetry.get(f"cht{i}", 120.0) for i in range(1, 5)]
        egt_vals = [telemetry.get(f"egt{i}", 750.0) for i in range(1, 5)]
        oil_press = telemetry.get("oil_press", 4.0)
        oil_temp = telemetry.get("oil_temp", 90.0)
        fuel_flow = telemetry.get("fuel_flow", 18.0)
        vib_rms = telemetry.get("vibration_rms", 1.2)
        batt_volt = telemetry.get("battery_volt", 14.1)

        # 1. Physics Deltas (Residuals)
        exp_cht = physics_state.get("expected_cht", 120.0)
        exp_egt = physics_state.get("expected_egt", 750.0)
        exp_oil_press = physics_state.get("expected_oil_press", 4.0)
        exp_oil_temp = physics_state.get("expected_oil_temp", 90.0)

        cht_max_delta = max(abs(c - exp_cht) for c in cht_vals)
        egt_max_delta = max(abs(e - exp_egt) for e in egt_vals)
        egt_spread = max(egt_vals) - min(egt_vals)
        cht_spread = max(cht_vals) - min(cht_vals)
        oil_press_delta = max(0.0, exp_oil_press - oil_press)

        # 2. Subsystem Health Indices (0 to 100%)
        # A. Thermal Health Index
        thermal_penalty = (cht_max_delta / 45.0)*30.0 + (max(0, max(cht_vals) - 155.0)/20.0)*50.0
        thermal_hi = max(0.0, min(100.0, 100.0 - thermal_penalty))

        # B. Lubrication Health Index
        lubrication_penalty = (oil_press_delta / 2.5)*60.0 + (max(0, oil_temp - 120.0)/20.0)*40.0
        lubrication_hi = max(0.0, min(100.0, 100.0 - lubrication_penalty))

        # C. Combustion & Fuel Health Index
        combustion_penalty = (egt_spread / 120.0)*50.0 + (egt_max_delta / 80.0)*30.0
        combustion_hi = max(0.0, min(100.0, 100.0 - combustion_penalty))

        # D. Electrical & Ignition Health Index
        elec_dev = abs(batt_volt - 14.1)
        electrical_hi = max(0.0, min(100.0, 100.0 - (elec_dev / 2.5)*80.0))

        # E. Mechanical & Structural Health Index
        vib_penalty = (max(0.0, vib_rms - 1.5) / 3.5)*100.0
        mechanical_hi = max(0.0, min(100.0, 100.0 - vib_penalty))

        # 3. Subsystem Health Matrix & Critical-Fault Override Logic
        weights = {"thermal": 0.25, "lubrication": 0.25, "combustion": 0.25, "electrical": 0.10, "mechanical": 0.15}
        weighted_hi = (
            thermal_hi * weights["thermal"] +
            lubrication_hi * weights["lubrication"] +
            combustion_hi * weights["combustion"] +
            electrical_hi * weights["electrical"] +
            mechanical_hi * weights["mechanical"]
        )

        # Critical-Fault Override Rule: If any single subsystem HI drops below 45% or oil press < 1.8 bar, cap overall HI
        min_sub_hi = min([thermal_hi, lubrication_hi, combustion_hi, electrical_hi, mechanical_hi])
        if min_sub_hi < 45.0 or oil_press < 1.8 or max(cht_vals) > 165.0:
            overall_hi = round(min(45.0, weighted_hi), 1)
            hi_status_override = True
        else:
            overall_hi = round(weighted_hi, 1)
            hi_status_override = False

        # 4. Anomaly Score (0.00 to 1.00)
        anomaly_score = round(min(1.0, max(0.0, (100.0 - overall_hi) / 100.0)), 3)

        # Data Quality Assessment (Drift / Noise / Integrity)
        data_quality_pct = 98.5
        if abs(batt_volt - 14.1) > 1.2:
            data_quality_pct = 75.0 # Sensor drift reduces confidence in electrical channels

        # 5. Active Fault Classification & LLM Propulsion Advisory Engine
        active_faults = []
        advisories = []

        # Check Misfire
        min_egt_cyl = int(np.argmin(egt_vals) + 1)
        if egt_spread > 90.0 and egt_vals[min_egt_cyl - 1] < (exp_egt - 80.0):
            fault_obj = {
                "subsystem": "Combustion",
                "severity": "CRITICAL",
                "type": "Cylinder Misfire",
                "confidence_tier": "HIGH (0.94)",
                "confidence_pct": 94,
                "evidence": f"EGT drop of {int(exp_egt - egt_vals[min_egt_cyl-1])}°C on Cylinder #{min_egt_cyl} ({int(egt_vals[min_egt_cyl-1])}°C vs {int(exp_egt)}°C model baseline).",
                "description": f"Cylinder #{min_egt_cyl} misfire detected.",
                "temporary_fix": f"⚡ Quick Field Action: Trim throttle position, switch ECU ignition module to Channel B backup, and plan immediate recovery at nearest UAV runway.",
                "permanent_fix": f"🛠️ Depot Repair: Remove cylinder head #{min_egt_cyl}, replace dual spark plugs (NGK DCPR7E), inspect fuel injector flow rate, and check ignition coil resistance."
            }
            active_faults.append(fault_obj)
            advisories.append(f"[CONFIDENCE: HIGH (0.94)*] Combustion Fault on Cylinder #{min_egt_cyl}: {fault_obj['evidence']}\n\n• {fault_obj['temporary_fix']}\n• {fault_obj['permanent_fix']}")

        # Check Overheating / Cooling Degradation
        max_cht_cyl = int(np.argmax(cht_vals) + 1)
        if max(cht_vals) > 155.0 or (cht_vals[max_cht_cyl - 1] - exp_cht) > 35.0:
            fault_obj = {
                "subsystem": "Thermal",
                "severity": "WARNING" if max(cht_vals) < 165 else "CRITICAL",
                "type": "Cylinder Head Overheating",
                "confidence_tier": "HIGH (0.91)",
                "confidence_pct": 91,
                "evidence": f"CHT on Cylinder #{max_cht_cyl} reached {int(cht_vals[max_cht_cyl-1])}°C ({int(cht_vals[max_cht_cyl-1] - exp_cht)}°C above baseline).",
                "description": f"CHT thermal runaway on Cylinder #{max_cht_cyl} ({int(cht_vals[max_cht_cyl-1])}°C).",
                "temporary_fix": "⚡ Quick Field Action: Enrich air-fuel mixture by +5%, reduce airspeed climb angle, and open cowl flap air intake to increase ram air cooling.",
                "permanent_fix": f"🛠️ Depot Repair: Flush coolant loop, inspect mechanical water pump impeller seal, adjust cylinder ram air cooling baffle seals on Cylinder #{max_cht_cyl}, and test thermostat operation."
            }
            active_faults.append(fault_obj)
            advisories.append(f"[CONFIDENCE: HIGH (0.91)*] Cooling Degradation: {fault_obj['evidence']}\n\n• {fault_obj['temporary_fix']}\n• {fault_obj['permanent_fix']}")

        # Check Lubrication Issues
        if oil_press < 2.2:
            fault_obj = {
                "subsystem": "Lubrication",
                "severity": "CRITICAL" if oil_press < 1.6 else "WARNING",
                "type": "Low Oil Pressure / Lubrication Issue",
                "confidence_tier": "HIGH (0.96)",
                "confidence_pct": 96,
                "evidence": f"Oil pressure is {round(((exp_oil_press - oil_press)/exp_oil_press)*100, 1)}% below physics baseline ({round(oil_press, 2)} bar vs {exp_oil_press} bar expected) with rising oil temp ({round(oil_temp, 1)}°C).",
                "description": f"Oil pressure dropped to {round(oil_press, 2)} bar (expected ~{exp_oil_press} bar).",
                "temporary_fix": "⚡ Quick Field Action: Limit engine speed to 4,200 RPM cruise ceiling, initiate immediate RTB (Return-To-Base). Ground crew: check dipstick oil level and top up 0.5L 15W-50 aero oil.",
                "permanent_fix": "🛠️ Depot Repair: Disassemble oil pump assembly, replace oil pressure relief valve spring (Rotax Part #841210), replace oil filter element, and perform 1-hour ground test rig calibration."
            }
            active_faults.append(fault_obj)
            advisories.append(f"[CONFIDENCE: HIGH (0.96)*] Lubrication Fault: {fault_obj['evidence']}\n\n• {fault_obj['temporary_fix']}\n• {fault_obj['permanent_fix']}")

        # Check Sensor Drift / Failure
        if abs(batt_volt - 14.1) > 1.2:
            fault_obj = {
                "subsystem": "Electrical",
                "severity": "WARNING",
                "type": "Bus Voltage Sensor Drift",
                "confidence_tier": "MEDIUM (0.78)",
                "confidence_pct": 78,
                "evidence": f"Bus voltage reading drifted to {round(batt_volt, 2)}V (nominal baseline 14.10V ±0.20V).",
                "description": f"Bus voltage anomaly detected: {round(batt_volt, 2)}V.",
                "temporary_fix": "⚡ Quick Field Action: Switch GCS telemetry stream source to secondary redundant sensor bus, verify alternator output reading on analog multimeter.",
                "permanent_fix": "🛠️ Depot Repair: Replace voltage regulator module, inspect main engine ground strap bond resistance (< 0.05 ohms), and recalibrate ADC transducer."
            }
            active_faults.append(fault_obj)
            advisories.append(f"[CONFIDENCE: MEDIUM (0.78)*] Sensor Drift: {fault_obj['evidence']}\n\n• {fault_obj['temporary_fix']}\n• {fault_obj['permanent_fix']}")

        # Check Vibration Spike
        if vib_rms > 2.8:
            fault_obj = {
                "subsystem": "Mechanical",
                "severity": "WARNING" if vib_rms < 4.0 else "CRITICAL",
                "type": "Abnormal Mechanical Vibration Spike",
                "confidence_tier": "HIGH (0.92)",
                "confidence_pct": 92,
                "evidence": f"Engine vibration RMS rose to {round(vib_rms, 2)}g (baseline < 1.50g).",
                "description": f"High engine vibration RMS: {round(vib_rms, 2)} g.",
                "temporary_fix": "⚡ Quick Field Action: Avoid resonant RPM bands (4,400 - 4,700 RPM sweep), maintain smooth throttle inputs, and prepare for priority recovery.",
                "permanent_fix": "🛠️ Depot Repair: Re-balance propeller dynamically on digital optical balancer, replace rubber engine mount isolation dampers, and measure crankshaft main bearing play."
            }
            active_faults.append(fault_obj)
            advisories.append(f"[CONFIDENCE: HIGH (0.92)*] Mechanical Imbalance: {fault_obj['evidence']}\n\n• {fault_obj['temporary_fix']}\n• {fault_obj['permanent_fix']}")

        # 6. Prototype Degradation-Based RUL Estimate
        if overall_hi >= 85.0:
            rul_status = "HEALTHY"
            rul_factor = 1.0
        elif overall_hi >= 60.0:
            rul_status = "DEGRADATION DETECTED"
            rul_factor = 0.65
        else:
            rul_status = "CRITICAL FAULT"
            rul_factor = 0.20

        estimated_rul_hours = round(self.nominal_rul_hours * (overall_hi / 100.0)**1.5 * rul_factor, 1)
        estimated_mission_remaining_mins = round(max(0, (overall_hi / 100.0) * 360.0), 0)

        return {
            "overall_health_index": overall_hi,
            "critical_override_active": hi_status_override,
            "data_quality_pct": data_quality_pct,
            "subsystem_health": {
                "thermal": round(thermal_hi, 1),
                "lubrication": round(lubrication_hi, 1),
                "combustion": round(combustion_hi, 1),
                "electrical": round(electrical_hi, 1),
                "mechanical": round(mechanical_hi, 1)
            },
            "anomaly_score": anomaly_score,
            "prototype_rul_estimate": {
                "status": rul_status,
                "remaining_tbo_hours": estimated_rul_hours,
                "estimated_mission_remaining_mins": estimated_mission_remaining_mins,
                "disclaimer": "Experimental Prototype Estimate — Not for Operational Flight Decisions (Synthetic degradation profile; uncalibrated dataset)"
            },
            "active_faults": active_faults,
            "maintenance_advisories": advisories if advisories else ["System operating within nominal physics baselines. No degradation detected."],
            "confidence_note": "*Model score based on current simulated evidence; not statistically calibrated on flight datasets."
        }

ai_analytics_instance = AeroEngineAIAnalytics()
