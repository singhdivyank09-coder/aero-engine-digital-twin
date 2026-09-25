app_path = r"C:\Users\divya\.gemini\antigravity\scratch\aero_engine_digital_twin\frontend\app.js"
with open(app_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if any(k in line.lower() for k in ["pew-time-to-risk", "eng-ttr", "gcs-ttr", "gcs-fc-ttr", "time_to_risk", "twincomponentinteraction", "inspectcomponent"]):
        print(f"Line {idx+1}: {line.strip()}")
