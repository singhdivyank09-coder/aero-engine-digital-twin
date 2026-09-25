import os

html_path = r"C:\Users\divya\.gemini\antigravity\scratch\aero_engine_digital_twin\frontend\index.html"
app_path = r"C:\Users\divya\.gemini\antigravity\scratch\aero_engine_digital_twin\frontend\app.js"

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

with open(app_path, "r", encoding="utf-8") as f:
    app = f.read()

print("HTML DRDO count:", html.count("DRDO"))
print("HTML SIH 26054 count:", html.count("SIH 26054") + html.count("SIH26054"))
print("APP DRDO count:", app.count("DRDO"))
print("APP SIH 26054 count:", app.count("SIH 26054") + app.count("SIH26054"))
