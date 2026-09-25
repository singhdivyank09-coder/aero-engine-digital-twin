import asyncio
from playwright.async_api import async_playwright
import os

async def verify_branding():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("Navigating to http://127.0.0.1:8000...")
        await page.goto("http://127.0.0.1:8000")
        await page.wait_for_selector("#login-modal", state="visible")
        
        # Login as engineer
        await page.fill("#username", "engineer")
        await page.fill("#password", "engineer123")
        await page.click("button[type='submit']")
        
        # Wait for main GCS interface
        await page.wait_for_selector("#main-gcs", state="visible")
        await page.wait_for_timeout(2000)
        
        # Check title
        page_title = await page.title()
        print(f"Page Title: '{page_title}'")
        
        # Check Header Title
        header_title = await page.inner_text("header h1")
        print(f"Header Title: '{header_title}'")
        
        # Check Profile Badge and Name
        badge_text = await page.inner_text("#user-role-badge")
        user_name = await page.inner_text("#user-display-name")
        print(f"User Badge: '{badge_text}'")
        print(f"User Name: '{user_name}'")
        
        # Check Disclaimer Banner
        disclaimer_text = await page.inner_text(".disclaimer-banner")
        print(f"Disclaimer Text: '{disclaimer_text}'")
        
        # Verify no DRDO or SIH 26054 in body text
        body_text = await page.inner_text("body")
        drdo_in_body = "DRDO" in body_text
        sih_in_body = "SIH 26054" in body_text or "SIH26054" in body_text
        print(f"Contains 'DRDO': {drdo_in_body}")
        print(f"Contains 'SIH 26054': {sih_in_body}")
        
        assert not drdo_in_body, "ERROR: Found 'DRDO' in live page body!"
        assert not sih_in_body, "ERROR: Found 'SIH 26054' in live page body!"
        assert badge_text == "ENGINEER", f"Expected ENGINEER, got {badge_text}"
        assert user_name == "Demo Prototype Operator", f"Expected Demo Prototype Operator, got {user_name}"
        assert "Demo Prototype" in header_title, "Header title missing Demo Prototype"
        
        screenshot_path = r"C:\Users\divya\.gemini\antigravity\brain\0097d5ff-f017-4bb7-83b2-b2aef1e3c7bc\live_branding_cleanup_verification.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"Saved live screenshot to {screenshot_path}")
        
        await browser.close()
        print("ALL VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(verify_branding())
