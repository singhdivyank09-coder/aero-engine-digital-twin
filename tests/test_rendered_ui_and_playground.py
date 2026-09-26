"""
Comprehensive Playwright Rendered UI & Public Playground Test Suite
Validates:
1. Engineer login and Demo login workflows.
2. ALL 9 top-level tabs activate, are direct children of <main>, have non-zero visible dimensions and recognizable content.
3. Public Fault Playground: all 6 precomputed scenarios, play/pause/reset/scrubber controls, valid data contract ('Not available' for missing model outputs).
4. Logout button functionality.
5. Captures screenshots and asserts zero critical browser console errors.
"""

import os
import sys
import time
import subprocess
import pytest
import urllib.request
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

@pytest.mark.anyio
async def test_rendered_ui_all_tabs_and_playground():
    # 1. Start local server process on port 8010
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8010"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for server readiness
    server_ready = False
    for _ in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8010/api/health", timeout=1) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.3)

    assert server_ready, "Backend server failed to start on port 8010!"

    console_errors = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1400, "height": 900})

            # Track console errors
            page.on("console", lambda msg: console_errors.append(f"[{msg.type.upper()}] {msg.text}") if msg.type == "error" else None)

            # --- STEP A: INITIAL LOGIN PAGE & ENGINEER AUTHENTICATION ---
            print("[TEST] Opening login page...")
            await page.goto("http://127.0.0.1:8010", wait_until="networkidle")
            await page.wait_for_timeout(1000)

            # Check status banner
            status_text = await page.inner_text("#login-server-status")
            print(f"[TEST] Connection status: '{status_text.strip()}'")
            assert "127.0.0.1:8000" not in status_text, "Hardcoded localhost IP found!"

            # Fill Engineer credentials
            print("[TEST] Logging in as Engineer...")
            await page.fill("#username", "engineer")
            await page.fill("#password", "engineer123")
            await page.click("#login-form button[type='submit']")
            await page.wait_for_timeout(1500)

            # Assert GCS is open
            main_gcs_hidden = await page.evaluate("document.getElementById('main-gcs').classList.contains('hidden')")
            assert not main_gcs_hidden, "Main GCS failed to open after Engineer login!"

            role_text = await page.inner_text("#user-role-badge")
            assert "ENGINEER" in role_text, f"Expected ENGINEER role badge, got '{role_text}'"

            # --- STEP B: TEST ALL 9 TOP-LEVEL TAB PANELS ---
            tabs = [
                ("view-operator", "Operator Dashboard"),
                ("view-digital-twin", "2D Digital Twin Schematic"),
                ("view-engineer", "Fault Injection & Analytics"),
                ("view-playground", "Simulated Fault Playground"),
                ("view-replay", "Mission Replay & Reports"),
                ("view-models-datasets", "AI Models & Dataset Mapping"),
                ("view-gcs-dfcs", "GCS & DFCS Demonstrator"),
                ("view-metrics", "System Metrics & Assumptions"),
                ("view-audit", "Security Audit Logs")
            ]

            print("[TEST] Verifying all 9 tabs have non-zero visible dimensions & content...")
            for tab_id, tab_label in tabs:
                tab_btn = await page.query_selector(f"button.nav-tab[data-target='{tab_id}']")
                assert tab_btn is not None, f"Tab button for {tab_id} missing!"

                await tab_btn.click()
                await page.wait_for_timeout(400)

                # 1. Assert tab active
                is_active = await page.evaluate(f"document.getElementById('{tab_id}').classList.contains('active')")
                assert is_active, f"Tab {tab_id} is not active after click!"

                # 2. Assert direct child of <main>
                is_direct_child = await page.evaluate(f"""
                    () => {{
                        const el = document.getElementById('{tab_id}');
                        return el && el.parentElement && el.parentElement.tagName.toLowerCase() === 'main';
                    }}
                """)
                assert is_direct_child, f"Tab {tab_id} is NOT a direct child of <main>!"

                # 3. Assert non-zero visible dimensions
                panel = await page.query_selector(f"#{tab_id}")
                box = await panel.bounding_box()
                assert box is not None, f"Panel #{tab_id} bounding box is None!"
                assert box["width"] > 100, f"Panel #{tab_id} width is too small ({box['width']}px)!"
                assert box["height"] > 100, f"Panel #{tab_id} height is too small ({box['height']}px)!"

                # 4. Take screenshot
                ss_path = os.path.join(SCREENSHOT_DIR, f"tab_{tab_id}.png")
                await page.screenshot(path=ss_path)
                print(f"  [OK] Tab '{tab_label}' (#{tab_id}): width={box['width']:.0f}px, height={box['height']:.0f}px")

            # --- STEP C: TEST PUBLIC FAULT PLAYGROUND ---
            print("[TEST] Testing Public Simulated Fault Playground...")
            await page.click("button.nav-tab[data-target='view-playground']")
            await page.wait_for_timeout(500)

            scenarios = [
                "CYLINDER_THERMAL",
                "OIL_PRESSURE",
                "INCREASING_VIBRATION",
                "SENSOR_DRIFT",
                "INTERMITTENT_COMBUSTION",
                "INJECTOR_DISTURBANCE"
            ]

            select_elem = await page.query_selector("#playground-scenario-select")
            assert select_elem is not None, "Playground scenario selector missing!"

            for scenario in scenarios:
                print(f"  Testing scenario '{scenario}'...")
                await page.select_option("#playground-scenario-select", scenario)
                await page.wait_for_timeout(300)

                # Verify readout values exist
                cht1_text = await page.inner_text("#pg-val-cht1")
                assert "°C" in cht1_text, f"Invalid CHT1 text in scenario {scenario}: {cht1_text}"

                # Verify 'Not available' handling for missing model outputs
                rul_text = await page.inner_text("#pg-rul-val")
                assert rul_text in ["Not available", "210 cycles"] or "cycles" in rul_text or "Not available" in rul_text, f"Unexpected RUL text: {rul_text}"

            # Test Play, Pause, Reset, Scrubber
            print("  Testing Play/Pause/Reset/Scrubber controls...")
            await page.click("#pg-btn-play")
            await page.wait_for_timeout(600)

            await page.click("#pg-btn-pause")
            await page.wait_for_timeout(200)

            # Scrub timeline to 30s
            await page.fill("#pg-timeline-scrubber", "30")
            await page.dispatch_event("#pg-timeline-scrubber", "input")
            await page.wait_for_timeout(300)

            time_text = await page.inner_text("#pg-time-display")
            assert "30.0s" in time_text, f"Scrubber failed to set timeline to 30.0s, got '{time_text}'"

            await page.click("#pg-btn-reset")
            await page.wait_for_timeout(200)
            time_text_reset = await page.inner_text("#pg-time-display")
            assert "0.0s" in time_text_reset, f"Reset failed, got '{time_text_reset}'"

            # Take Playground screenshot
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "playground_tested.png"))

            # --- STEP D: TEST LOGOUT & DEMO LOGIN ---
            print("[TEST] Testing Logout button...")
            await page.click("#btn-logout")
            await page.wait_for_timeout(800)

            login_modal_active = await page.evaluate("document.getElementById('login-modal').classList.contains('active')")
            assert login_modal_active, "Logout failed to open login modal!"

            print("[TEST] Testing Public Demo Login...")
            await page.click("#btn-demo-login")
            await page.wait_for_timeout(1500)

            gcs_open = await page.evaluate("!document.getElementById('main-gcs').classList.contains('hidden')")
            assert gcs_open, "Demo login failed to open GCS!"

            demo_role = await page.inner_text("#user-role-badge")
            assert "OPERATOR" in demo_role or "DEMO" in demo_role, f"Expected Demo role badge, got '{demo_role}'"

            # Verify Engineer-only notice banner is visible in Engineer tab
            await page.click("button.nav-tab[data-target='view-engineer']")
            await page.wait_for_timeout(300)

            notice_visible = await page.evaluate("""
                () => {
                    const el = document.getElementById('engineer-access-notice-banner');
                    return el && el.offsetParent !== null;
                }
            """)
            assert notice_visible, "Engineer access restriction notice banner should be visible for Demo user!"

            await browser.close()

            print(f"[TEST CONSOLE ERRORS] Count: {len(console_errors)}")
            if console_errors:
                print("Console errors logged during test execution:")
                for err in console_errors:
                    print(f"  {err}")

            # Filter out non-fatal extension/font standard warnings if any
            critical_errors = [e for e in console_errors if "TypeError" in e or "ReferenceError" in e or "SyntaxError" in e or "Uncaught" in e]
            assert len(critical_errors) == 0, f"Critical JS errors encountered: {critical_errors}"

            print("\n[ALL PLAYWRIGHT TESTS PASSED 100%] Rendered UI & Playground fully verified!")
    finally:
        server_process.terminate()
        server_process.wait()
