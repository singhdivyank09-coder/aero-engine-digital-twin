import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance
from backend.main import compute_canonical_tick

def test_dfcs_sync_acceptance_all():
    simulator_instance.reset()
    digital_twin_core_instance.reset()
    
    # 1. ACCEPTANCE TEST A — NORMAL
    frame = compute_canonical_tick()
    adv = frame.get("gcs_dfcs_advisory", {})
    
    assert frame["system_state"] == "NORMAL"
    assert adv["level"] == "NORMAL"
    assert adv["demand_recommendation"] == "NOMINAL"
    assert adv["title"] == "Nominal System Monitoring"
    assert "nominal reference envelopes" in adv["description"].lower() or "nominal physical envelopes" in adv["description"].lower()
    
    # ACCEPTANCE TEST F — SCENARIO
    scenario_val = frame["scenario"]
    if isinstance(scenario_val, dict):
        scenario_str = scenario_val.get("id", "CRUISE")
    else:
        scenario_str = str(scenario_val)
    assert scenario_str != "[object Object]"
    assert "CRUISE" in scenario_str.upper()

    # 2. ACCEPTANCE TEST B & C — GRADUAL THERMAL FAULT ON CYLINDER 4
    simulator_instance.start_fault_injection(
        scenario="CYLINDER_THERMAL",
        component="CYLINDER_4",
        profile="GRADUAL",
        intensity=1.0,
        rate="FAST"
    )
    
    states_observed = {}
    for step in range(300):
        f = compute_canonical_tick()
        st = f["system_state"]
        ad = f.get("gcs_dfcs_advisory", {})
        
        # Invariant 21: DFCS level must equal system_state exactly
        assert ad.get("level") == st, f"DFCS level {ad.get('level')} != system_state {st} at step {step}"
        
        if st not in states_observed:
            states_observed[st] = ad
            
        if st == "CRITICAL":
            # ACCEPTANCE TEST C — SAME COMPONENT
            comp_str = str(ad.get("description", "")) + str(ad.get("dominant_component", ""))
            assert "CYLINDER_4" in comp_str or "CYLINDER 4" in comp_str or "THERMAL" in comp_str, f"DFCS description missing CYLINDER_4: {ad}"
            assert ad.get("demand_recommendation") == "MINIMUM SAFE / EMERGENCY"
            assert ad.get("title") == "Critical Propulsion Advisory"
        elif st == "WARNING":
            assert ad.get("demand_recommendation") == "REDUCED"
            assert ad.get("title") == "Reduced Demand Advisory"
        elif st == "CAUTION":
            assert ad.get("demand_recommendation") == "CONSERVATIVE"
            assert ad.get("title") == "Operational Caution Advisory"
        elif st == "WATCH":
            assert ad.get("demand_recommendation") == "MONITOR"
            assert ad.get("title") == "Enhanced Monitoring Advisory"
            
    assert "CRITICAL" in states_observed, f"System did not reach CRITICAL during gradual thermal fault. Observed: {list(states_observed.keys())}"

    # 3. ACCEPTANCE TEST D — CLEAR / RECOVERY SYNCHRONIZATION
    simulator_instance.clear_fault_injection()
    
    # Process recovery frames until system returns to NORMAL
    final_frame = None
    for step in range(250):
        f = compute_canonical_tick()
        st = f["system_state"]
        ad = f.get("gcs_dfcs_advisory", {})
        assert ad.get("level") == st
        final_frame = f
        if st == "NORMAL":
            break
        
    assert final_frame["system_state"] == "NORMAL"
    final_adv = final_frame.get("gcs_dfcs_advisory", {})
    assert final_adv["level"] == "NORMAL"
    assert final_adv["demand_recommendation"] == "NOMINAL"
    assert final_adv["title"] == "Nominal System Monitoring"
