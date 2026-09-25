import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        context = await b.new_context()
        page = await context.new_page()
        
        await page.goto("http://localhost:8000/")
        await asyncio.sleep(2)
        
        await page.evaluate("document.querySelector(\"button[data-target='view-gcs-dfcs']\").click()")
        await asyncio.sleep(1)
        
        res1 = await page.evaluate("""() => {
            const el = document.getElementById('gcs-seq-display');
            if (el) el.innerText = 'Seq #9999';
            return el ? el.innerText : 'NULL';
        }""")
        print("Explicit DOM set result:", res1)

        res2 = await page.inner_text("#gcs-seq-display")
        print("Playwright inner_text result:", res2)
            
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
