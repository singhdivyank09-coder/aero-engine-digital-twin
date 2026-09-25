"""
Single Authoritative Fault Specification Registry
Centralized backend source of truth for all fault/component relationships,
affected signals, allowed profiles, and classifier mappings.
"""

from typing import Dict, Any, List, Optional

FAULT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "CYLINDER_MISFIRE": {
        "fault_id": "CYLINDER_MISFIRE",
        "display_name": "Cylinder Misfire",
        "subsystem": "COMBUSTION",
        "valid_components": [
            "CYLINDER_1",
            "CYLINDER_2",
            "CYLINDER_3",
            "CYLINDER_4"
        ],
        "component_labels": {
            "CYLINDER_1": "Cylinder 1",
            "CYLINDER_2": "Cylinder 2",
            "CYLINDER_3": "Cylinder 3",
            "CYLINDER_4": "Cylinder 4"
        },
        "affected_signals": ["rpm", "egt1", "egt2", "egt3", "egt4", "cht1", "cht2", "cht3", "cht4"],
        "secondary_signals": ["vibration_rms", "fuel_flow", "engine_power_estimate"],
        "allowed_profiles": ["SUDDEN", "GRADUAL", "INTERMITTENT"],
        "supported_detection_sources": ["physics_residual", "cusum", "xgboost"],
        "classifier_label": "Cylinder Misfire",
        "forecast_channels": ["egt1", "egt2", "egt3", "egt4", "vibration_rms"],
        "description": "Intermittent or continuous misfire in a single combustion cylinder."
    },
    "FUEL_INJECTOR_ABNORMALITY": {
        "fault_id": "FUEL_INJECTOR_ABNORMALITY",
        "display_name": "Fuel Injector Abnormality",
        "subsystem": "COMBUSTION",
        "valid_components": [
            "INJECTOR_CYL_1",
            "INJECTOR_CYL_2",
            "INJECTOR_CYL_3",
            "INJECTOR_CYL_4",
            "FUEL_INJECTION_SYSTEM"
        ],
        "component_labels": {
            "INJECTOR_CYL_1": "Injector — Cylinder 1",
            "INJECTOR_CYL_2": "Injector — Cylinder 2",
            "INJECTOR_CYL_3": "Injector — Cylinder 3",
            "INJECTOR_CYL_4": "Injector — Cylinder 4",
            "FUEL_INJECTION_SYSTEM": "Fuel Injection System"
        },
        "affected_signals": ["fuel_flow", "egt1", "egt2", "egt3", "egt4", "cht1", "cht2", "cht3", "cht4"],
        "secondary_signals": ["rpm", "vibration_rms", "engine_power_estimate"],
        "allowed_profiles": ["SUDDEN", "GRADUAL", "INTERMITTENT"],
        "supported_detection_sources": ["physics_residual", "cusum", "xgboost"],
        "classifier_label": "Fuel Injector Abnormality",
        "forecast_channels": ["fuel_flow", "egt1", "egt2", "egt3", "egt4"],
        "description": "Fuel injector flow restriction or valve timing abnormality."
    },
    "CYLINDER_THERMAL_DEGRADATION": {
        "fault_id": "CYLINDER_THERMAL_DEGRADATION",
        "display_name": "Cylinder Thermal Degradation",
        "subsystem": "THERMAL",
        "valid_components": [
            "CYLINDER_1",
            "CYLINDER_2",
            "CYLINDER_3",
            "CYLINDER_4"
        ],
        "component_labels": {
            "CYLINDER_1": "Cylinder 1",
            "CYLINDER_2": "Cylinder 2",
            "CYLINDER_3": "Cylinder 3",
            "CYLINDER_4": "Cylinder 4"
        },
        "affected_signals": ["cht1", "cht2", "cht3", "cht4", "egt1", "egt2", "egt3", "egt4"],
        "secondary_signals": ["oil_temp", "engine_power_estimate"],
        "allowed_profiles": ["SUDDEN", "GRADUAL", "INTERMITTENT"],
        "supported_detection_sources": ["physics_residual", "autoencoder", "gru_forecast"],
        "classifier_label": "Cylinder Head Overheating",
        "forecast_channels": ["cht1", "cht2", "cht3", "cht4", "oil_temp"],
        "description": "Thermal degradation or cooling blockage affecting individual cylinder head."
    },
    "OIL_PRESSURE_DEGRADATION": {
        "fault_id": "OIL_PRESSURE_DEGRADATION",
        "display_name": "Oil Pressure Degradation",
        "subsystem": "LUBRICATION",
        "valid_components": [
            "OIL_SYSTEM",
            "OIL_PUMP",
            "OIL_PRESSURE_CIRCUIT"
        ],
        "component_labels": {
            "OIL_SYSTEM": "Lubrication System",
            "OIL_PUMP": "Oil Pump Assembly",
            "OIL_PRESSURE_CIRCUIT": "Oil Pressure Circuit"
        },
        "affected_signals": ["oil_press", "oil_temp"],
        "secondary_signals": ["cht1", "cht2", "cht3", "cht4", "vibration_rms"],
        "allowed_profiles": ["SUDDEN", "GRADUAL", "INTERMITTENT"],
        "supported_detection_sources": ["physics_residual", "cusum", "xgboost"],
        "classifier_label": "Lubrication Failure / Low Oil Pressure",
        "forecast_channels": ["oil_press", "oil_temp"],
        "description": "Pressure decay or loss of viscosity in primary engine lubrication system."
    },
    "INCREASING_VIBRATION": {
        "fault_id": "INCREASING_VIBRATION",
        "display_name": "Increasing Mechanical Vibration",
        "subsystem": "MECHANICAL",
        "valid_components": [
            "CRANKSHAFT_BEARING_ASSEMBLY",
            "ENGINE_MOUNT",
            "PROPELLER_COUPLING"
        ],
        "component_labels": {
            "CRANKSHAFT_BEARING_ASSEMBLY": "Crankshaft / Bearing Assembly",
            "ENGINE_MOUNT": "Engine Mount Assembly",
            "PROPELLER_COUPLING": "Propeller Drive Coupling"
        },
        "affected_signals": ["vibration_rms"],
        "secondary_signals": ["rpm", "engine_power_estimate", "oil_temp"],
        "allowed_profiles": ["SUDDEN", "GRADUAL", "INTERMITTENT"],
        "supported_detection_sources": ["autoencoder", "cusum", "xgboost"],
        "classifier_label": "Abnormal Mechanical Vibration",
        "forecast_channels": ["vibration_rms", "rpm"],
        "description": "Mechanical imbalance or bearing wear producing abnormal vibration."
    },
    "SENSOR_DRIFT": {
        "fault_id": "SENSOR_DRIFT",
        "display_name": "Sensor Measurement Drift",
        "subsystem": "SENSOR",
        "valid_components": [
            "RPM_SENSOR",
            "MAP_SENSOR",
            "CHT1_SENSOR",
            "CHT2_SENSOR",
            "CHT3_SENSOR",
            "CHT4_SENSOR",
            "EGT1_SENSOR",
            "EGT2_SENSOR",
            "EGT3_SENSOR",
            "EGT4_SENSOR",
            "OIL_PRESSURE_SENSOR",
            "OIL_TEMP_SENSOR",
            "FUEL_FLOW_SENSOR",
            "VIBRATION_SENSOR",
            "BUS_VOLTAGE_SENSOR"
        ],
        "component_labels": {
            "RPM_SENSOR": "RPM Sensor",
            "MAP_SENSOR": "Manifold Absolute Pressure Sensor",
            "CHT1_SENSOR": "CHT 1 Sensor",
            "CHT2_SENSOR": "CHT 2 Sensor",
            "CHT3_SENSOR": "CHT 3 Sensor",
            "CHT4_SENSOR": "CHT 4 Sensor",
            "EGT1_SENSOR": "EGT 1 Sensor",
            "EGT2_SENSOR": "EGT 2 Sensor",
            "EGT3_SENSOR": "EGT 3 Sensor",
            "EGT4_SENSOR": "EGT 4 Sensor",
            "OIL_PRESSURE_SENSOR": "Oil Pressure Sensor",
            "OIL_TEMP_SENSOR": "Oil Temperature Sensor",
            "FUEL_FLOW_SENSOR": "Fuel Flow Sensor",
            "VIBRATION_SENSOR": "Vibration Sensor",
            "BUS_VOLTAGE_SENSOR": "Electrical Bus Voltage Sensor"
        },
        "affected_signals": [
            "rpm", "map", "cht1", "cht2", "cht3", "cht4",
            "egt1", "egt2", "egt3", "egt4", "oil_press", "oil_temp",
            "fuel_flow", "vibration_rms", "battery_volt"
        ],
        "secondary_signals": [],
        "allowed_profiles": ["SUDDEN", "GRADUAL", "INTERMITTENT"],
        "supported_detection_sources": ["physics_residual", "cusum"],
        "classifier_label": "Electrical Bus Voltage Sensor Drift",
        "forecast_channels": ["battery_volt"],
        "description": "Instrumentation measurement bias (sensor drift without physical engine state modification)."
    },
    "ELECTRICAL_BUS_VOLTAGE_DEGRADATION": {
        "fault_id": "ELECTRICAL_BUS_VOLTAGE_DEGRADATION",
        "display_name": "Electrical Bus Voltage Degradation",
        "subsystem": "ELECTRICAL",
        "valid_components": [
            "ELECTRICAL_BUS",
            "ALTERNATOR",
            "BATTERY"
        ],
        "component_labels": {
            "ELECTRICAL_BUS": "Electrical Bus",
            "ALTERNATOR": "Alternator Assembly",
            "BATTERY": "Battery Subsystem"
        },
        "affected_signals": ["battery_volt"],
        "secondary_signals": [],
        "allowed_profiles": ["SUDDEN", "GRADUAL", "INTERMITTENT"],
        "supported_detection_sources": ["cusum", "xgboost"],
        "classifier_label": "Electrical Bus Voltage Sensor Drift",
        "forecast_channels": ["battery_volt"],
        "description": "Voltage drop or instability on main electrical supply bus."
    },
    "INTERMITTENT_COMBUSTION": {
        "fault_id": "INTERMITTENT_COMBUSTION",
        "display_name": "Intermittent Combustion Disturbance",
        "subsystem": "COMBUSTION",
        "valid_components": [
            "CYLINDER_1",
            "CYLINDER_2",
            "CYLINDER_3",
            "CYLINDER_4"
        ],
        "component_labels": {
            "CYLINDER_1": "Cylinder 1",
            "CYLINDER_2": "Cylinder 2",
            "CYLINDER_3": "Cylinder 3",
            "CYLINDER_4": "Cylinder 4"
        },
        "affected_signals": ["egt1", "egt2", "egt3", "egt4", "rpm"],
        "secondary_signals": ["cht1", "cht2", "cht3", "cht4", "vibration_rms", "engine_power_estimate"],
        "allowed_profiles": ["INTERMITTENT", "SUDDEN"],
        "supported_detection_sources": ["cusum", "xgboost"],
        "classifier_label": "Cylinder Misfire",
        "forecast_channels": ["egt1", "egt2", "egt3", "egt4"],
        "description": "Transient combustion instability or intermittent spark drop."
    }
}

# Alias Map for scenario key resolution
SCENARIO_ALIAS_MAP: Dict[str, str] = {
    "CYLINDER_THERMAL": "CYLINDER_THERMAL_DEGRADATION",
    "OVERHEATING": "CYLINDER_THERMAL_DEGRADATION",
    "CYLINDER_HEAD_OVERHEATING": "CYLINDER_THERMAL_DEGRADATION",
    "OIL_PRESSURE": "OIL_PRESSURE_DEGRADATION",
    "OIL_PRESSURE_DROP": "OIL_PRESSURE_DEGRADATION",
    "LUBRICATION_FAILURE": "OIL_PRESSURE_DEGRADATION",
    "VIBRATION_SPIKE": "INCREASING_VIBRATION",
    "ABNORMAL_VIBRATION": "INCREASING_VIBRATION",
    "INJECTOR_DISTURBANCE": "FUEL_INJECTOR_ABNORMALITY",
    "INJECTOR_ABNORMALITY": "FUEL_INJECTOR_ABNORMALITY",
    "MISFIRE": "CYLINDER_MISFIRE",
    "ELECTRICAL_DEGRADATION": "ELECTRICAL_BUS_VOLTAGE_DEGRADATION",
    "ELECTRICAL_BUS": "ELECTRICAL_BUS_VOLTAGE_DEGRADATION",
    "VOLTAGE_DRIFT": "ELECTRICAL_BUS_VOLTAGE_DEGRADATION"
}

def resolve_fault_id(scenario: str) -> str:
    """Normalizes input scenario name to canonical fault_id."""
    if not scenario:
        return "CYLINDER_THERMAL_DEGRADATION"
    key = str(scenario).strip().upper()
    if key in FAULT_REGISTRY:
        return key
    if key in SCENARIO_ALIAS_MAP:
        return SCENARIO_ALIAS_MAP[key]
    return key

def get_fault_spec(scenario: str) -> Optional[Dict[str, Any]]:
    """Retrieves full specification for a given fault/scenario."""
    fid = resolve_fault_id(scenario)
    return FAULT_REGISTRY.get(fid)

def get_valid_components(scenario: str) -> List[Dict[str, str]]:
    """Returns list of valid component objects {id, label} for a given fault."""
    spec = get_fault_spec(scenario)
    if not spec:
        return []
    valid_ids = spec.get("valid_components", [])
    labels = spec.get("component_labels", {})
    return [{"id": cid, "label": labels.get(cid, cid.replace("_", " ").title())} for cid in valid_ids]

def is_valid_fault_component(scenario: str, component: str) -> bool:
    """Validates whether (scenario, component) pair is compatible according to registry."""
    spec = get_fault_spec(scenario)
    if not spec:
        return False
    valid_ids = [c.upper() for c in spec.get("valid_components", [])]
    comp_upper = str(component).strip().upper()
    if comp_upper in valid_ids:
        return True
    
    # Handle cylinder index aliases e.g. "CYLINDER 2" or "2" or "INJECTOR_CYL_2" vs "CYLINDER_2"
    if "CYLINDER_1" in valid_ids or "INJECTOR_CYL_1" in valid_ids:
        if comp_upper in ["CYLINDER_1", "CYLINDER_2", "CYLINDER_3", "CYLINDER_4",
                          "CYLINDER 1", "CYLINDER 2", "CYLINDER 3", "CYLINDER 4",
                          "INJECTOR_CYL_1", "INJECTOR_CYL_2", "INJECTOR_CYL_3", "INJECTOR_CYL_4",
                          "INJECTOR CYL 1", "INJECTOR CYL 2", "INJECTOR CYL 3", "INJECTOR CYL 4",
                          "1", "2", "3", "4"]:
            return True
            
    if "OIL_SYSTEM" in valid_ids and comp_upper in ["LUBRICATION_SYSTEM", "OIL_SYSTEM", "OIL_PUMP", "OIL_PRESSURE_CIRCUIT"]:
        return True
    if "CRANKSHAFT_BEARING_ASSEMBLY" in valid_ids and comp_upper in ["CRANKSHAFT_BEARING_ASSEMBLY", "MECHANICAL_BEARING", "ENGINE_MOUNT", "PROPELLER_COUPLING"]:
        return True
    if "ELECTRICAL_BUS" in valid_ids and comp_upper in ["ELECTRICAL_BUS", "ALTERNATOR", "BATTERY", "ELECTRICAL_BUS_VOLTAGE_SENSOR"]:
        return True

    return False
