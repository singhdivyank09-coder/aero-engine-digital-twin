"""
Canonical Engine Telemetry Schema
Provides standardized data models, validation, and dataset transformer mappings
converting raw aerospace datasets (NASA C-MAPSS, RflyMAD, ALFA/UAV-FD) into
the standardized Aero Piston Engine Digital Twin format.
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

@dataclass
class CanonicalEngineState:
    timestamp: float
    engine_id: str = "TAPAS-ROTAX914-01"
    rpm: float = 5000.0
    map: float = 1.15               # Manifold Absolute Pressure (bar)
    cht1: float = 120.0             # Cylinder Head Temp 1 (°C)
    cht2: float = 121.0             # Cylinder Head Temp 2 (°C)
    cht3: float = 119.5             # Cylinder Head Temp 3 (°C)
    cht4: float = 120.5             # Cylinder Head Temp 4 (°C)
    egt1: float = 748.0             # Exhaust Gas Temp 1 (°C)
    egt2: float = 752.0             # Exhaust Gas Temp 2 (°C)
    egt3: float = 745.0             # Exhaust Gas Temp 3 (°C)
    egt4: float = 749.0             # Exhaust Gas Temp 4 (°C)
    oil_press: float = 4.20         # Oil Pressure (bar)
    oil_temp: float = 88.5          # Oil Temperature (°C)
    fuel_flow: float = 17.5         # Fuel Flow Rate (L/hr)
    vibration_rms: float = 1.12     # Mechanical Vibration (g)
    battery_volt: float = 14.10     # Bus Voltage (V)
    injection_timing: float = 26.0  # Injection Timing (° BTDC)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanonicalEngineState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DatasetCanonicalMapper:
    """
    Scientific mapping layer converting raw dataset features into Canonical Engine State.
    Maintains rigorous justification for analogue mappings.
    """

    @staticmethod
    def map_cmapss_row(row: Dict[str, float], engine_id: str, cycle: int) -> CanonicalEngineState:
        """
        Maps NASA C-MAPSS turbofan sensor parameters to Aero Piston Engine Digital Twin analogues:
        - s2 (Total Temp at LPC outlet) -> CHT Avg (scaled 110-175 °C)
        - s3 (Total Temp at HPC outlet) -> EGT Avg (scaled 700-880 °C)
        - s4 (Physical fan speed) -> Engine Speed RPM (scaled 4000-5800 RPM)
        - s7 (HPC outlet pressure) -> Manifold Absolute Pressure MAP (scaled 0.9-1.4 bar)
        - s11 (Static press at HPC outlet) -> Oil Pressure (scaled 1.5-4.8 bar)
        - s12 (Ratio of fuel flow to Ps30) -> Fuel Flow (scaled 12-25 L/hr)
        - s15 (Bypass ratio) -> Vibration RMS (scaled 0.8-4.5 g)
        """
        # Baseline extraction with fallback defaults
        s2 = row.get("s2", 642.0)
        s3 = row.get("s3", 1580.0)
        s4 = row.get("s4", 1400.0)
        s7 = row.get("s7", 553.0)
        s11 = row.get("s11", 47.0)
        s12 = row.get("s12", 521.0)
        s15 = row.get("s15", 8.4)

        # Scientific linear normalization to IC engine operational limits
        rpm = 4000.0 + (s4 - 1380.0) * (1800.0 / 60.0)
        rpm = float(max(3000.0, min(5800.0, rpm)))

        avg_cht = 115.0 + (s2 - 641.0) * 1.8
        cht1 = float(max(90.0, min(180.0, avg_cht + 0.5)))
        cht2 = float(max(90.0, min(180.0, avg_cht + 1.2)))
        cht3 = float(max(90.0, min(180.0, avg_cht - 0.8)))
        cht4 = float(max(90.0, min(180.0, avg_cht - 0.2)))

        avg_egt = 730.0 + (s3 - 1575.0) * 2.5
        egt1 = float(max(600.0, min(920.0, avg_egt - 3.0)))
        egt2 = float(max(600.0, min(920.0, avg_egt + 2.0)))
        egt3 = float(max(600.0, min(920.0, avg_egt - 4.0)))
        egt4 = float(max(600.0, min(920.0, avg_egt + 1.0)))

        map_val = 1.0 + (s7 - 550.0) * (0.4 / 15.0)
        map_val = float(max(0.7, min(1.45, map_val)))

        oil_p = 4.5 - (s11 - 46.8) * 0.4
        oil_p = float(max(1.2, min(5.0, oil_p)))

        fuel_f = 16.0 + (s12 - 520.0) * 0.15
        fuel_f = float(max(10.0, min(28.0, fuel_f)))

        vib = 1.0 + max(0.0, (s15 - 8.3) * 1.2)
        vib = float(max(0.5, min(5.0, vib)))

        return CanonicalEngineState(
            timestamp=float(cycle),
            engine_id=engine_id,
            rpm=round(rpm, 1),
            map=round(map_val, 3),
            cht1=round(cht1, 1),
            cht2=round(cht2, 1),
            cht3=round(cht3, 1),
            cht4=round(cht4, 1),
            egt1=round(egt1, 1),
            egt2=round(egt2, 1),
            egt3=round(egt3, 1),
            egt4=round(egt4, 1),
            oil_press=round(oil_p, 2),
            oil_temp=round(85.0 + (avg_cht - 115.0) * 0.4, 1),
            fuel_flow=round(fuel_f, 2),
            vibration_rms=round(vib, 2),
            battery_volt=14.10,
            injection_timing=26.0
        )
