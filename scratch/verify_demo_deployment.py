import os
import sys
import time
import asyncio
from playwright.async_api import async_playwright

async def run_browser_verification():
    print("==========================================================================")
    print("     AERO ENGINE DIGITAL TWIN — BROWSER E2E DEMO VERIFICATION TEST         ")
    print("==========================================================================")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("[TEST 1] Loading Login Modal & Checking UI Notices...")
        await page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
        time.sleep(1)

        # Verify Data Loss Notice on Login modal
        login_notice = await page.inner_text("#login-modal .data-loss-notice")
        assert "Temporary Demonstration Data" in login_notice, "Data loss notice missing on login modal!"
        print("  [OK] Data Loss Notice verified on login screen.")

        # Verify Demo Button exists
        demo_btn = await page.query_selector("#btn-demo-login")
        assert demo_btn is not None, "Explore Demo button missing on login modal!"
        print("  [OK] Explore Demo button present.")

        # Take Login Screen Screenshot
        artifacts_dir = os.path.join(os.path.dirname(__file__), "..")
        screenshot_path_login = os.path.join(artifacts_dir, "demo_login_screen.png")
        await page.screenshot(path=screenshot_path_login)
        print(f"  [OK] Login screen screenshot saved to {screenshot_path_login}")

        print("\n[TEST 2] Public Demo Visitor Login & Read-Only UI Checks...")
        await page.click("#btn-demo-login")
        time.sleep(2)

        # Verify Main GCS rendered
        role_text = await page.inner_text("#user-role-badge")
        print(f"  [OK] Logged in as role: {role_text}")
        assert role_text.upper() in ["DEMO", "OP", "OPERATOR"], f"Unexpected role badge: {role_text}"

        # Verify Shared Demonstration Session badge in header
        banner_text = await page.inner_text(".disclaimer-banner")
        assert "SHARED DEMONSTRATION SESSION" in banner_text, "Shared session badge missing from header banner!"
        print("  [OK] SHARED DEMONSTRATION SESSION badge present in header.")

        # Verify eng-only controls hidden
        eng_controls = await page.query_selector_all(".eng-only")
        for el in eng_controls:
            is_visible = await el.is_visible()
            assert not is_visible, "Engineer-only control visible to Demo visitor!"
        print("  [OK] Engineer-only controls hidden for Demo visitor.")

        # Navigate to 2D Digital Twin view
        print("\n[TEST 3] Navigating to 2D Digital Twin Schematic...")
        await page.click("button[data-target='view-digital-twin']")
        time.sleep(1)
        svg_elem = await page.query_selector(".engine-svg")
        assert svg_elem is not None, "2D Engine SVG schematic missing!"
        print("  [OK] 2D Engine Schematic loaded.")

        # Navigate to Replay View & Check Data Loss Notice
        print("\n[TEST 4] Navigating to Historical Mission Replay View...")
        await page.click("button[data-target='view-replay']")
        time.sleep(1)
        replay_notice = await page.inner_text("#view-replay .data-loss-notice")
        assert "Temporary Demonstration Data" in replay_notice, "Data loss notice missing on Replay view!"
        print("  [OK] Data Loss Notice verified on Mission Replay view.")

        screenshot_path_replay = os.path.join(artifacts_dir, "demo_replay_screen.png")
        await page.screenshot(path=screenshot_path_replay)
        print(f"  [OK] Mission Replay view screenshot saved to {screenshot_path_replay}")

        # Logout
        print("\n[TEST 5] Testing Logout & Re-authentication as Engineer...")
        await page.click("#btn-logout")
        time.sleep(1)

        # Login as Engineer
        await page.fill("#username", "engineer")
        await page.fill("#password", "engineer123")
        await page.click("#login-form button[type='submit']")
        time.sleep(2)

        eng_role = await page.inner_text("#user-role-badge")
        assert "ENGINEER" in eng_role.upper(), f"Expected ENGINEER role badge, got {eng_role}"
        print(f"  [OK] Successfully authenticated as {eng_role}.")

        # Verify Engineer controls now visible
        fault_tab = await page.query_selector("button[data-target='view-engineer']")
        assert await fault_tab.is_visible(), "Fault Injection tab missing for Engineer!"
        print("  [OK] Fault Injection & Analytics controls accessible for Engineer.")

        screenshot_path_eng = os.path.join(artifacts_dir, "engineer_dashboard_screen.png")
        await page.screenshot(path=screenshot_path_eng)
        print(f"  [OK] Engineer dashboard screenshot saved to {screenshot_path_eng}")


        await browser.close()

    print("\n==========================================================================")
    print("      ALL E2E BROWSER ACCEPTANCE TESTS PASSED SUCCESSFULLY!                ")
    print("==========================================================================")

if __name__ == "__main__":
    asyncio.run(run_browser_verification())
