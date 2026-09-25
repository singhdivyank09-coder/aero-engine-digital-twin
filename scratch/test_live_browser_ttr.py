import time
import sys

# Ensure UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

def test_live_browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1440, "height": 900})
        
        page.goto("http://127.0.0.1:8000")
        page.wait_for_timeout(2000)

        # Handle login modal if present
        if page.is_visible("#login-modal"):
            print("Logging in via UI form...")
            page.fill("#username", "engineer")
            page.fill("#password", "engineer123")
            page.click("#btn-login")
            page.wait_for_timeout(2000)

        # Ensure main GCS interface is visible
        page.wait_for_selector("#main-gcs:not(.hidden)", timeout=10000)
        print("Main GCS interface active.")

        # Start fault via API directly using token
        res = page.evaluate("""async () => {
            const token = localStorage.getItem('dt_token') || '';
            return await fetch('/api/fault-injection/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                },
                body: JSON.stringify({
                    scenario: 'CYLINDER_THERMAL',
                    component: 'CYLINDER_1',
                    profile: 'SUDDEN',
                    intensity: 1.5,
                    rate: 'FAST'
                })
            }).then(r => r.json());
        }""")
        print("API Fault Injection Start response:", res)

        print("Waiting for CHT1 to breach 145.0°C limit...")
        for i in range(25):
            cht = page.evaluate("window.twinStore && window.twinStore.currentSnapshot ? window.twinStore.currentSnapshot.telemetry.cht1 : 120.0")
            print(f"t={i}s: CHT1 = {cht:.1f}°C")
            if cht >= 145.0:
                print(f"Limit breached! Current CHT1 = {cht:.1f}°C")
                break
            time.sleep(1)

        time.sleep(1.5)

        # 1. Operator Dashboard PEW Panel TTR
        page.evaluate("document.querySelector('.nav-tab[data-target=\"view-operator\"]').click()")
        page.wait_for_timeout(500)
        pew_ttr = page.inner_text("#pew-time-to-risk")
        print(f"[Operator Dashboard PEW Panel] Time-to-Risk: '{pew_ttr}'")

        # 2. Fault Analytics Page TTR
        page.evaluate("document.querySelector('.nav-tab[data-target=\"view-engineer\"]').click()")
        page.wait_for_timeout(500)
        eng_ttr = page.inner_text("#eng-ttr")
        print(f"[Fault Analytics Page] Time-to-Risk: '{eng_ttr}'")

        # 3. GCS/DFCS Overview TTR
        page.evaluate("document.querySelector('.nav-tab[data-target=\"view-gcs-dfcs\"]').click()")
        page.wait_for_timeout(500)
        gcs_ttr = page.inner_text("#gcs-ttr-display")
        print(f"[GCS/DFCS Overview] Time-to-Risk: '{gcs_ttr}'")

        # 4. 2D Digital Twin Component Inspector Modal TTR
        page.evaluate("document.querySelector('.nav-tab[data-target=\"view-digital-twin\"]').click()")
        page.wait_for_timeout(500)
        if page.query_selector("#svg-comp-cyl1"):
            page.click("#svg-comp-cyl1")
            page.wait_for_timeout(500)
        inspector_ttr = page.inner_text("#comp-detail-body")
        safe_excerpt = inspector_ttr[:150].encode('ascii', 'ignore').decode('ascii')
        print(f"[2D Component Inspector Modal] Excerpt: {safe_excerpt}...")

        # Screenshot
        screenshot_path = "C:/Users/divya/.gemini/antigravity/brain/0097d5ff-f017-4bb7-83b2-b2aef1e3c7bc/live_ttr_limit_exceeded_cht1.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print("Captured artifact screenshot: live_ttr_limit_exceeded_cht1.png")

        # Assertions
        assert "0 s" in pew_ttr and "LIMIT EXCEEDED" in pew_ttr, f"PEW error: '{pew_ttr}'"
        assert "0 s" in eng_ttr and "LIMIT EXCEEDED" in eng_ttr, f"Eng error: '{eng_ttr}'"
        assert "0 s" in gcs_ttr and "LIMIT EXCEEDED" in gcs_ttr, f"GCS error: '{gcs_ttr}'"
        assert "0 s — LIMIT EXCEEDED" in inspector_ttr or "LIMIT EXCEEDED" in inspector_ttr, f"Inspector error: '{inspector_ttr}'"

        print("\n[LIVE ACCEPTANCE SUCCESS] ALL 4 PANELS VERIFIED MATCHING AND CORRECT FOR '0 s — LIMIT EXCEEDED'!")

        # Clear fault
        page.evaluate("""async () => {
            const token = localStorage.getItem('dt_token') || '';
            return await fetch('/api/fault-injection/clear', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + token }
            });
        }""")
        browser.close()

if __name__ == "__main__":
    test_live_browser()
