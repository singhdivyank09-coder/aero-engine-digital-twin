import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page()
        
        page.on("console", lambda msg: print(f"  [BROWSER CONSOLE] {msg.text}") if "TWIN" in msg.text or "GCS" in msg.text or "seq" in msg.text else None)
        
        print("Navigating to http://localhost:8000/...")
        await page.goto("http://localhost:8000/")
        await asyncio.sleep(2)
        
        gcs_tab = page.locator("button.nav-tab[data-tab='gcs-dfcs-page']")
        if await gcs_tab.count() > 0:
            await gcs_tab.click()
            print("Clicked GCS/DFCS tab.")
            await asyncio.sleep(1)
        
        for i in range(5):
            await asyncio.sleep(1)
            seq = await page.inner_text("#gcs-seq-display")
            st = await page.inner_text("#gcs-state-display")
            print(f"  [t={i+1}s] seq='{seq}', state='{st}'")
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
