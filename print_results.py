import json

log_path = r"C:\Users\divya\.gemini\antigravity\brain\0097d5ff-f017-4bb7-83b2-b2aef1e3c7bc\.system_generated\tasks\task-7700.log"
with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

idx = text.find("SUMMARY OF ALL CHANNELS:")
if idx != -1:
    json_str = text[idx + len("SUMMARY OF ALL CHANNELS:"):].strip()
    try:
        data = json.loads(json_str)
        print("\n==========================================")
        print("CHANNEL TEST RESULTS SUMMARY:")
        print("==========================================")
        for item in data:
            p = item.get("param", "")
            st = item.get("state", "")
            pew = item.get("pew_curr", "")
            obs = item.get("chart_last_obs", "")
            fc = item.get("chart_fc", [])
            ymin = item.get("chart_yMin", "")
            ymax = item.get("chart_yMax", "")
            match = item.get("obs_matching", False)
            print(f"Param: {p:<14} | State: {st:<8} | PEW: {pew:<10} | Chart Obs: {obs:<6} | Forecast: {fc} | Y-Bounds: [{ymin}, {ymax}] | Match: {match}")
    except Exception as e:
        print("JSON parse error:", e)
else:
    print("Summary header not found in log.")
