import re

with open("frontend/index.html", "r", encoding="utf-8") as f:
    html = f.read()

ids = re.findall(r'id="([^"]+)"', html)
print("All IDs found in index.html:")
for i in ids:
    if "seq" in i.lower() or "gcs" in i.lower() or "header" in i.lower() or "sub" in i.lower():
        print("  -", i)
