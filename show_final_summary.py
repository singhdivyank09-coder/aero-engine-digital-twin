import json

log_path = r"C:\Users\divya\.gemini\antigravity\brain\0097d5ff-f017-4bb7-83b2-b2aef1e3c7bc\.system_generated\tasks\task-7820.log"
with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

idx = text.rfind("[\n  {\n")
if idx != -1:
    json_str = text[idx:].strip()
    data = json.loads(json_str)
    print("\n==========================================================================================================")
    print(f"{'CHANNEL':<15} | {'STATE':<10} | {'PEW CARD READOUT':<16} | {'CHART OBSERVED':<16} | {'CHART FORECAST TRAJECTORY':<28} | {'Y-BOUNDS'}")
    print("==========================================================================================================")
    for item in data:
        p = item.get("param", "")
        st = item.get("state", "")
        pew = item.get("pew_curr", "")
        obs = str(item.get("chart_last_obs"))
        fc = str(item.get("chart_fc"))
        bounds = f"[{item.get('chart_yMin')}, {item.get('chart_yMax')}]"
        print(f"{p:<15} | {st:<10} | {pew:<16} | {obs:<16} | {fc:<28} | {bounds}")
    print("==========================================================================================================")
else:
    print("JSON summary not found")
