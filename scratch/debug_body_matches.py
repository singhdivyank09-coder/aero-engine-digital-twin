import asyncio
from playwright.async_api import async_playwright

async def debug_body_text():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("http://127.0.0.1:8000")
        await page.wait_for_selector("#login-modal", state="visible")
        await page.fill("#username", "engineer")
        await page.fill("#password", "engineer123")
        await page.click("button[type='submit']")
        await page.wait_for_selector("#main-gcs", state="visible")
        await page.wait_for_timeout(1000)

        body_text = await page.inner_text("body")
        lines = body_text.split("\n")
        keywords = ["sih", "26054", "drdo", "idex"]
        matches = [line.strip() for line in lines if any(k in line.lower() for k in keywords)]
        print(f"Total matching lines in body text: {len(matches)}")
        for m in matches:
            print("MATCH:", repr(m))

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_body_text())
