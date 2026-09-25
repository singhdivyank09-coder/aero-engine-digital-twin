import re
import os

app_path = r"C:\Users\divya\.gemini\antigravity\scratch\aero_engine_digital_twin\frontend\app.js"
html_path = r"C:\Users\divya\.gemini\antigravity\scratch\aero_engine_digital_twin\frontend\index.html"

with open(app_path, "r", encoding="utf-8") as f:
    app_lines = f.readlines()

print("--- APP.JS SEARCH RESULTS FOR TIME-TO-RISK / TTR / 999 ---")
for idx, line in enumerate(app_lines):
    if any(k in line.lower() for k in ["time_to_risk", "ttr", "999", "estimated_time"]):
        print(f"Line {idx+1}: {line.strip()[:120]}")

with open(html_path, "r", encoding="utf-8") as f:
    html_lines = f.readlines()

print("\n--- INDEX.HTML SEARCH RESULTS FOR TIME-TO-RISK / TTR / 999 ---")
for idx, line in enumerate(html_lines):
    if any(k in line.lower() for k in ["time-to-risk", "ttr", "999", "risk"]):
        print(f"Line {idx+1}: {line.strip()[:120]}")
