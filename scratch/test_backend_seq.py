import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from backend.main import compute_canonical_tick

print("=== TESTING compute_canonical_tick() sequence_number ===")
for i in range(5):
    snap = compute_canonical_tick()
    print(f"Call {i+1}: sequence_number={snap.get('sequence_number')}, state={snap.get('system_state')}")
