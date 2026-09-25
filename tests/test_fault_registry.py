import pytest
from backend.fault_registry import FAULT_REGISTRY, get_fault_spec, resolve_fault_id, get_valid_components

def test_fault_registry_presence_and_keys():
    required_faults = [
        "CYLINDER_MISFIRE",
        "FUEL_INJECTOR_ABNORMALITY",
        "CYLINDER_THERMAL_DEGRADATION",
        "OIL_PRESSURE_DEGRADATION",
        "INCREASING_VIBRATION",
        "SENSOR_DRIFT",
        "ELECTRICAL_BUS_VOLTAGE_DEGRADATION",
        "INTERMITTENT_COMBUSTION"
    ]
    for fid in required_faults:
        assert fid in FAULT_REGISTRY, f"Fault {fid} missing from FAULT_REGISTRY"
        spec = FAULT_REGISTRY[fid]
        for req_key in [
            "fault_id", "display_name", "subsystem", "valid_components",
            "affected_signals", "secondary_signals", "allowed_profiles",
            "supported_detection_sources", "classifier_label", "forecast_channels", "description"
        ]:
            assert req_key in spec, f"Key '{req_key}' missing from fault spec {fid}"

def test_fault_registry_valid_components():
    misfire_comps = [c["id"] for c in get_valid_components("CYLINDER_MISFIRE")]
    assert misfire_comps == ["CYLINDER_1", "CYLINDER_2", "CYLINDER_3", "CYLINDER_4"]

    injector_comps = [c["id"] for c in get_valid_components("FUEL_INJECTOR_ABNORMALITY")]
    assert "INJECTOR_CYL_1" in injector_comps
    assert "INJECTOR_CYL_2" in injector_comps

    oil_comps = [c["id"] for c in get_valid_components("OIL_PRESSURE_DEGRADATION")]
    assert "OIL_SYSTEM" in oil_comps
