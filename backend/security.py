from typing import Dict, Tuple

class DataIntegrityValidator:
    def __init__(self):
        self.last_sequence = -1

    def validate_telemetry_frame(self, frame: Dict) -> Tuple[bool, str]:
        # 1. Sequence Number check
        seq = frame.get("sequence_no", 0)
        if self.last_sequence >= 0 and seq <= self.last_sequence:
            # Check for reset or jump
            if seq != 0: # reset allowed
                return False, f"Sequence integrity failure: Expected > {self.last_sequence}, got {seq}"
        self.last_sequence = seq

        # 2. Sensor Bounds Sanity Check
        rpm = frame.get("rpm", 0)
        if rpm < 0 or rpm > 7000:
            return False, f"RPM out of physical bounds: {rpm}"

        cht_list = [frame.get(f"cht{i}", 0) for i in range(1, 5)]
        for idx, cht in enumerate(cht_list, 1):
            if cht < -40 or cht > 350:
                return False, f"CHT cylinder {idx} out of physical bounds: {cht}°C"

        egt_list = [frame.get(f"egt{i}", 0) for i in range(1, 5)]
        for idx, egt in enumerate(egt_list, 1):
            if egt < -40 or egt > 1100:
                return False, f"EGT cylinder {idx} out of physical bounds: {egt}°C"

        oil_press = frame.get("oil_press", 0)
        if oil_press < 0 or oil_press > 12:
            return False, f"Oil pressure out of bounds: {oil_press} bar"

        return True, "Data Integrity Verified"

validator_instance = DataIntegrityValidator()
