import json

with open(r"C:\Users\divya\.gemini\antigravity\brain\0097d5ff-f017-4bb7-83b2-b2aef1e3c7bc\.system_generated\tasks\task-7820.log", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

start = text.rfind("[\n  {\n")
if start != -1:
    end = text.find("]", start) + 1
    json_str = text[start:end]
    items = json.loads(json_str)
    print("\n==========================================================================================")
    print(f"{'PARAM':<15} | {'STATE':<10} | {'PEW READOUT':<14} | {'CHART LAST OBS':<14} | {'CHART FORECAST':<22} | {'Y-BOUNDS'}")
    print("==========================================================================================")
    for it in items:
        p = it.get('param', '')
        st = it.get('state', '')
        pew = it.get('pew_curr', '')
        obs = str(it.get('chart_last_obs'))
        fc = str(it.get('chart_fc'))
        bounds = f"[{it.get('chart_yMin')}, {it.get('chart_yMax')}]"
        print(f"{p:<15} | {st:<10} | {pew:<14} | {obs:<14} | {fc:<22} | {bounds}")
else:
    print("Still running or JSON summary block not reached yet.")
