import time
import math
import random
from datetime import datetime
from typing import Dict, Any

class TelemetryGenerator:
    def __init__(self):
        self.sequence_no = 0
        self.active_mission_profile = "CRUISE"
        self.injected_fault = "NONE" # Options: NONE, MISFIRE, INJECTOR_ABNORMALITY, OIL_PRESSURE_DROP, OVERHEATING, VIBRATION_SPIKE, SENSOR_DRIFT
        self.fault_intensity = 1.0

    def set_mission_profile(self, profile_name: str):
        valid_profiles = ["CRUISE", "HIGH_ALTITUDE", "HOT_WEATHER", "ENDURANCE", "RAPID_THROTTLE"]
        if profile_name.upper() in valid_profiles:
            self.active_mission_profile = profile_name.upper()

    def inject_fault(self, fault_type: str, intensity: float = 1.0):
        self.injected_fault = fault_type.upper()
        self.fault_intensity = max(0.1, min(2.0, intensity))

    def clear_faults(self):
        self.injected_fault = "NONE"

    def generate_next_frame(self) -> Dict[str, Any]:
        self.sequence_no += 1
        now_iso = datetime.now().isoformat()

        # Baseline parameters per mission profile
        if self.active_mission_profile == "HIGH_ALTITUDE":
            base_rpm = 5200
            map_kpa = 95.0
            ambient_temp = -5.0
            altitude_m = 4500.0
        elif self.active_mission_profile == "HOT_WEATHER":
            base_rpm = 5100
            map_kpa = 115.0
            ambient_temp = 42.0
            altitude_m = 500.0
        elif self.active_mission_profile == "ENDURANCE":
            base_rpm = 4800
            map_kpa = 105.0
            ambient_temp = 20.0
            altitude_m = 2500.0
        elif self.active_mission_profile == "RAPID_THROTTLE":
            # Transient sine throttle wave
            t = time.time()
            base_rpm = 4500 + 1000 * math.sin(t * 0.8)
            map_kpa = 100 + 25 * math.sin(t * 0.8)
            ambient_temp = 25.0
            altitude_m = 1500.0
        else: # CRUISE
            base_rpm = 5000
            map_kpa = 110.0
            ambient_temp = 25.0
            altitude_m = 1500.0

        # Add physical noise
        noise_rpm = random.uniform(-15, 15)
        rpm = max(1000, base_rpm + noise_rpm)

        # Baseline temps & pressures
        cht1 = 122.0 + random.uniform(-2, 2)
        cht2 = 124.0 + random.uniform(-2, 2)
        cht3 = 121.0 + random.uniform(-2, 2)
        cht4 = 123.0 + random.uniform(-2, 2)

        egt1 = 745.0 + random.uniform(-5, 5)
        egt2 = 750.0 + random.uniform(-5, 5)
        egt3 = 742.0 + random.uniform(-5, 5)
        egt4 = 748.0 + random.uniform(-5, 5)

        oil_press = 4.2 + random.uniform(-0.1, 0.1)
        oil_temp = 88.0 + random.uniform(-1, 1)
        fuel_flow = 17.5 + (rpm / 5000.0) * 2.0 + random.uniform(-0.3, 0.3)
        vibration_rms = 1.1 + random.uniform(-0.1, 0.1)
        battery_volt = 14.1 + random.uniform(-0.05, 0.05)

        # ----------------------------------------------------
        # FAULT INJECTION LOGIC
        # ----------------------------------------------------
        if self.injected_fault == "MISFIRE":
            # Cylinder 3 EGT drops significantly, RPM fluctuates
            egt3 -= 150.0 * self.fault_intensity
            rpm += random.uniform(-70, 70)
            vibration_rms += 1.8 * self.fault_intensity

        elif self.injected_fault == "INJECTOR_ABNORMALITY":
            # Cylinder 2 lean burn (EGT spikes +90°C)
            egt2 += 110.0 * self.fault_intensity
            cht2 += 18.0 * self.fault_intensity

        elif self.injected_fault == "OIL_PRESSURE_DROP":
            # Oil pressure drops to dangerous low
            oil_press = max(0.8, oil_press - 2.6 * self.fault_intensity)
            oil_temp += 22.0 * self.fault_intensity

        elif self.injected_fault == "OVERHEATING":
            # CHT thermal runaway across all cylinders
            thermal_boost = 42.0 * self.fault_intensity
            cht1 += thermal_boost
            cht2 += thermal_boost + 5
            cht3 += thermal_boost - 2
            cht4 += thermal_boost + 3
            oil_temp += 18.0 * self.fault_intensity

        elif self.injected_fault == "VIBRATION_SPIKE":
            # Mechanical bearing wear / unbalance
            vibration_rms += 3.4 * self.fault_intensity

        elif self.injected_fault == "SENSOR_DRIFT":
            # True gradual sensor drift: bias b(t) increases progressively with sequence ticks
            drift_bias = min(4.5, 0.05 * (self.sequence_no % 100)) # Gradual drift from 0V to +4.5V
            battery_volt += drift_bias

        return {
            "timestamp": now_iso,
            "sequence_no": self.sequence_no,
            "mission_profile": self.active_mission_profile,
            "ambient_temp": round(ambient_temp, 1),
            "altitude_m": round(altitude_m, 1),
            "rpm": round(rpm, 1),
            "map_kpa": round(map_kpa, 1),
            "cht1": round(cht1, 1),
            "cht2": round(cht2, 1),
            "cht3": round(cht3, 1),
            "cht4": round(cht4, 1),
            "egt1": round(egt1, 1),
            "egt2": round(egt2, 1),
            "egt3": round(egt3, 1),
            "egt4": round(egt4, 1),
            "oil_press": round(oil_press, 2),
            "oil_temp": round(oil_temp, 1),
            "fuel_flow": round(fuel_flow, 2),
            "vibration_rms": round(vibration_rms, 2),
            "battery_volt": round(battery_volt, 2),
            "injected_fault": self.injected_fault
        }

telemetry_gen_instance = TelemetryGenerator()
