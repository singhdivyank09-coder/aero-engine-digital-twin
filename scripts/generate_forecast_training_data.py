"""
Simulated Aero-Piston Telemetry Trajectory Generator for GRU Forecast Training
SIH 26054 — MALE UAV Aero Engine Digital Twin

LABEL: SIMULATED REFERENCE AERO-PISTON TRAJECTORY
(Not DRDO flight measurements)

Generates 180 diverse simulated trajectories across 5 mission scenarios and 7 fault profiles.
Downsamples training output to 2 Hz (dt = 0.5s) while using the reference simulator physics.
Saves dataset to datasets/simulated/forecast_training/simulated_aero_piston_trajectories.csv
"""

import os
import sys
import random
import csv
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.telemetry_simulator import TelemetrySimulator
from ml_service.pinn_physics_model import PinnPhysicsModel

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "datasets", "simulated", "forecast_training")
os.makedirs(DATASET_DIR, exist_ok=True)
OUTPUT_CSV = os.path.join(DATASET_DIR, "simulated_aero_piston_trajectories.csv")

SCENARIOS = ["CRUISE", "HIGH_ALTITUDE", "HOT_WEATHER", "ENDURANCE", "RAPID_THROTTLE"]
FAULT_TYPES = [
    "NONE",
    "CYLINDER_THERMAL",
    "OIL_PRESSURE",
    "INCREASING_VIBRATION",
    "SENSOR_DRIFT",
    "INTERMITTENT_COMBUSTION",
    "INJECTOR_DISTURBANCE"
]
FAULT_PROFILES = ["GRADUAL", "GRADUAL_EXP", "INTERMITTENT", "SUDDEN"]
COMPONENTS = ["CYLINDER_1", "CYLINDER_2", "CYLINDER_3", "CYLINDER_4", "OIL_SYSTEM", "MECHANICAL_BEARING", "ELECTRICAL_BUS"]

def generate_trajectories(num_trajectories: int = 180):
    simulator = TelemetrySimulator()
    physics_model = PinnPhysicsModel()
    
    fieldnames = [
        "timestamp", "trajectory_id", "scenario", "active_fault_type", "fault_component",
        "fault_profile", "fault_intensity", "fault_ramp_duration", "altitude", "ambient_temperature",
        "throttle", "engine_load", "rpm", "map", "cht1", "cht2", "cht3", "cht4",
        "egt1", "egt2", "egt3", "egt4", "oil_pressure", "oil_temperature", "fuel_flow",
        "vibration_rms", "bus_voltage", "fault_effect", "physics_residual_cht",
        "physics_residual_oil_press", "physics_residual_egt"
    ]

    print(f"Generating {num_trajectories} SIMULATED REFERENCE AERO-PISTON TRAJECTORIES at 2 Hz...")
    
    total_rows = 0

    with open(OUTPUT_CSV, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for traj_idx in range(num_trajectories):
            simulator.reset()
            trajectory_id = f"TRAJ_{traj_idx+1:03d}"
            
            scenario = random.choice(SCENARIOS)
            simulator.set_mission_profile(scenario)

            altitude = random.uniform(500, 4500) if scenario == "HIGH_ALTITUDE" else random.uniform(500, 2000)
            amb_temp = random.uniform(35, 45) if scenario == "HOT_WEATHER" else random.uniform(-15, 25)
            throttle = random.uniform(60, 90)
            engine_load = throttle * random.uniform(0.9, 1.05)

            fault_type = random.choice(FAULT_TYPES)
            fault_profile = random.choice(FAULT_PROFILES)
            component = random.choice(COMPONENTS)
            intensity = random.uniform(0.5, 1.5)
            ramp_duration = random.uniform(20.0, 60.0)

            if fault_type != "NONE":
                simulator.start_fault_injection(
                    scenario=fault_type,
                    component=component,
                    profile=fault_profile if fault_profile != "GRADUAL_EXP" else "GRADUAL",
                    intensity=intensity,
                    rate="SLOW" if ramp_duration >= 40 else "MODERATE",
                    ramp_duration=ramp_duration
                )

            # Trajectory duration: 60s to 120s at 2 Hz sampling (120 to 240 steps at 2Hz)
            duration_sec = random.randint(60, 120)
            num_2hz_steps = duration_sec * 2

            for step_2hz in range(num_2hz_steps):
                simulator.step_counter += 4  # Jump 4 steps forward so get_next_frame adds +1 step = 5 steps (0.5s at 10Hz)
                frame = simulator.get_next_frame()

                telem = frame["telemetry"]
                t = step_2hz * 0.5

                physics_state = physics_model.predict_expected_state(telem, mission_profile=scenario)
                res = physics_state.get("residuals", {})

                cht_res = res.get("cht_delta", 0.0)
                oil_p_res = res.get("oil_press_delta", 0.0)
                egt_res = res.get("egt_delta", 0.0)

                active_faults = frame.get("active_faults", [])
                fault_effect = active_faults[0].get("current_effect", 0.0) if active_faults else 0.0

                row = {
                    "timestamp": round(t, 2),
                    "trajectory_id": trajectory_id,
                    "scenario": scenario,
                    "active_fault_type": fault_type,
                    "fault_component": component if fault_type != "NONE" else "NONE",
                    "fault_profile": fault_profile,
                    "fault_intensity": round(intensity, 2),
                    "fault_ramp_duration": round(ramp_duration, 1),
                    "altitude": round(altitude, 1),
                    "ambient_temperature": round(amb_temp, 1),
                    "throttle": round(throttle, 1),
                    "engine_load": round(engine_load, 1),
                    "rpm": round(float(telem.get("rpm", 5000)), 1),
                    "map": round(float(telem.get("map", 1.15)), 3),
                    "cht1": round(float(telem.get("cht1", 120)), 2),
                    "cht2": round(float(telem.get("cht2", 120)), 2),
                    "cht3": round(float(telem.get("cht3", 120)), 2),
                    "cht4": round(float(telem.get("cht4", 120)), 2),
                    "egt1": round(float(telem.get("egt1", 748)), 2),
                    "egt2": round(float(telem.get("egt2", 748)), 2),
                    "egt3": round(float(telem.get("egt3", 748)), 2),
                    "egt4": round(float(telem.get("egt4", 748)), 2),
                    "oil_pressure": round(float(telem.get("oil_press", 4.2)), 3),
                    "oil_temperature": round(float(telem.get("oil_temp", 88.5)), 2),
                    "fuel_flow": round(float(telem.get("fuel_flow", 17.5)), 2),
                    "vibration_rms": round(float(telem.get("vibration_rms", 1.12)), 3),
                    "bus_voltage": round(float(telem.get("battery_volt", 14.1)), 2),
                    "fault_effect": round(float(fault_effect), 3),
                    "physics_residual_cht": round(float(cht_res), 2),
                    "physics_residual_oil_press": round(float(oil_p_res), 3),
                    "physics_residual_egt": round(float(egt_res), 2)
                }
                writer.writerow(row)
                total_rows += 1

    print(f"\n[DATASET CREATED SUCCESS] Saved {num_trajectories} trajectories ({total_rows} rows at 2 Hz) to:")
    print(f"Path: {OUTPUT_CSV}")
    return OUTPUT_CSV, num_trajectories, total_rows

if __name__ == "__main__":
    generate_trajectories(num_trajectories=180)
