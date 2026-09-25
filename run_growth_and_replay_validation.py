import os
import sys
import time
import json
import sqlite3
import urllib.request
import asyncio
from playwright.async_api import async_playwright

db_path = r"C:\Users\divya\.gemini\antigravity\scratch\aero_engine_digital_twin\data\telemetry_db.sqlite"

def get_db_file_size():
    return os.path.getsize(db_path)

async def validate():
    print("==========================================================================================")
    print("1. STARTING NEW CONTROLLED MISSION SESSION FOR GROWTH MEASUREMENT")
    print("==========================================================================================")

    # Login token
    login_req = urllib.request.Request(
        "http://127.0.0.1:8000/api/auth/login",
        data=json.dumps({"username": "engineer", "password": "engineer123"}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    res = urllib.request.urlopen(login_req)
    data = json.loads(res.read().decode())
    token = data["access_token"]

    # Start new mission
    start_req = urllib.request.Request(
        "http://127.0.0.1:8000/api/replay/start-new-mission",
        data=b"{}",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    )
    res = urllib.request.urlopen(start_req)
    new_m = json.loads(res.read().decode())
    mission_id = new_m["mission_id"]
    print(f"Created Controlled Validation Mission: {mission_id}")

    db_size_start = get_db_file_size()
    t_start = time.time()
    print(f"Initial DB File Size: {db_size_start / (1024**2):.3f} MB ({db_size_start} bytes)")

    print("\nSimulating flight session for 45 seconds (90 downsampled 0.2Hz snapshots)...")
    await asyncio.sleep(45)

    db_size_end = get_db_file_size()
    t_end = time.time()
    dur = t_end - t_start
    db_delta = db_size_end - db_size_start

    print(f"Elapsed Time: {dur:.2f} seconds")
    print(f"Final DB File Size: {db_size_end / (1024**2):.3f} MB")
    print(f"Total Storage Growth Delta: {db_delta / 1024:.2f} KB ({db_delta} bytes)")
    print(f"Growth Rate: {db_delta / dur:.2f} bytes/sec ({(db_delta / dur * 3600)/(1024**2):.2f} MB/hour)")

    print("\n==========================================================================================")
    print("2. MEASURING NEWLY PERSISTED SNAPSHOT PAYLOAD SIZES")
    print("==========================================================================================")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    c = conn.cursor()

    c.execute("SELECT sequence_number, length(snapshot_json), snapshot_json FROM mission_snapshots WHERE mission_id = ? ORDER BY sequence_number ASC;", (mission_id,))
    new_rows = c.fetchall()
    print(f"Newly Persisted Snapshots for Mission {mission_id}: {len(new_rows)} records")

    if new_rows:
        sizes = [r[1] for r in new_rows]
        min_sz = min(sizes)
        max_sz = max(sizes)
        avg_sz = sum(sizes) / len(sizes)
        print(f"Minimum Snapshot Payload: {min_sz / 1024:.2f} KB ({min_sz} bytes)")
        print(f"Maximum Snapshot Payload: {max_sz / 1024:.2f} KB ({max_sz} bytes)")
        print(f"Average Snapshot Payload: {avg_sz / 1024:.2f} KB ({avg_sz:.0f} bytes)")

        print("\nChecking payload size stability across mission timeline:")
        print(f"  First Snapshot (seq #{new_rows[0][0]}): {new_rows[0][1] / 1024:.2f} KB")
        print(f"  Middle Snapshot (seq #{new_rows[len(new_rows)//2][0]}): {new_rows[len(new_rows)//2][1] / 1024:.2f} KB")
        print(f"  Latest Snapshot (seq #{new_rows[-1][0]}): {new_rows[-1][1] / 1024:.2f} KB")

        is_constant = abs(new_rows[-1][1] - new_rows[0][1]) < 2048
        print(f"  Payload Size Constant over Time: {'YES (STABLE CONSTANT SIZE)' if is_constant else 'NO'}")

        # Property-by-property breakdown of latest new snapshot
        latest_json = new_rows[-1][2]
        parsed_latest = json.loads(latest_json)
        print(f"\nProperty-by-Property Breakdown of New Snapshot (Total: {len(latest_json)} bytes / {len(latest_json)/1024:.2f} KB):")
        prop_sizes = {k: len(json.dumps(v)) for k, v in parsed_latest.items()}
        for k, sz in sorted(prop_sizes.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {k:<30}: {sz/1024:.2f} KB ({sz} bytes)")

    conn.close()

    print("\n==========================================================================================")
    print("3. VERIFYING HISTORICAL MISSION REPLAY & LIVE UI RECONSTRUCTION")
    print("==========================================================================================")

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Go to Replay view
        replay_tab = await page.query_selector("button.nav-tab[data-target='view-replay']")
        if replay_tab:
            await replay_tab.click()
            await page.wait_for_timeout(1000)

        # Check mission select dropdown options
        m_sel = await page.query_selector("#replay-mission-select")
        opts = await page.evaluate("el => Array.from(el.options).map(o => o.value)", m_sel) if m_sel else []
        print(f"Available Replay Missions in UI Dropdown: {opts[:5]}")

        # Click play button
        play_btn = await page.query_selector("#btn-replay-play")
        if play_btn:
            await play_btn.click()
            await page.wait_for_timeout(2000)
            t_disp = await page.inner_text("#replay-time-display")
            rpm_disp = await page.inner_text("#replay-val-rpm")
            cht_disp = await page.inner_text("#replay-val-cht")
            print(f"Replay Playback Active -> Time Display: '{t_disp}', RPM: '{rpm_disp}', CHT: '{cht_disp}'")
            assert "Frame" in t_disp or "0." in t_disp, "Replay playback failed!"
            print("MISSION REPLAY FUNCTIONALITY VERIFIED SUCCESSFULLY!")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(validate())
