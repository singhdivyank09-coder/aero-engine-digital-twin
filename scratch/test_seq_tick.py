import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance

print("=== TESTING SIMULATOR & TWIN CORE SEQUENCE GENERATION ===")
for i in range(10):
    raw = simulator_instance.get_next_frame()
    twin = digital_twin_core_instance.process_telemetry_frame(raw)
    print(f"Tick {i+1}: raw seq={raw.get('sequence_no')} / {raw.get('sequence_number')} | twin seq={twin.get('sequence_number')}")
