import asyncio
import os
import sys
import json
from playwright.async_api import async_playwright

async def test_all_channels():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        print("Navigating to http://localhost:8000...")
        await page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Token
        token = await page.evaluate("localStorage.getItem('dt_token')")
        print(f"Logged in token: {token[:10] if token else 'None'}...")

        tests = [
            {"param": "cht1", "comp": "CYLINDER_1", "scen": "CYLINDER_THERMAL"},
            {"param": "cht2", "comp": "CYLINDER_2", "scen": "CYLINDER_THERMAL"},
            {"param": "cht3", "comp": "CYLINDER_3", "scen": "CYLINDER_THERMAL"},
            {"param": "cht4", "comp": "CYLINDER_4", "scen": "CYLINDER_THERMAL"},
            {"param": "oil_press", "comp": "OIL_PUMP", "scen": "OIL_PRESSURE_DROP"},
            {"param": "oil_temp", "comp": "OIL_COOLER", "scen": "OIL_OVERTEMPERATURE"},
            {"param": "vibration_rms", "comp": "MAIN_BEARING", "scen": "BEARING_WEAR"}
        ]

        results = []

        for t in tests:
            param = t["param"]
            comp = t["comp"]
            scen = t["scen"]
            print(f"\n==========================================")
            print(f"Testing Channel: {param} (Scenario: {scen}, Component: {comp})")
            print(f"==========================================")

            # Clear faults first
            await page.evaluate("""
                async () => {
                    const token = localStorage.getItem('dt_token');
                    await fetch('/api/fault-injection/clear', {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                }
            """)
            await page.wait_for_timeout(3000)

            # Click parameter button
            btn = await page.query_selector(f"button.btn-pred-param[data-param='{param}']")
            if btn:
                await btn.click()
                await page.wait_for_timeout(500)

            # Inject fault
            inj_res = await page.evaluate(f"""
                async () => {{
                    const token = localStorage.getItem('dt_token');
                    const res = await fetch('/api/fault-injection/start', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${{token}}`
                        }},
                        body: JSON.stringify({{
                            scenario: '{scen}',
                            component: '{comp}',
                            profile: 'GRADUAL',
                            intensity: 1.0,
                            rate: 'FAST'
                        }})
                    }});
                    return res.json();
                }}
            """)
            print(f"Fault injection response: {inj_res}")

            print("Waiting 12 seconds for escalation...")
            await page.wait_for_timeout(12000)

            # Extract PEW readouts
            pew_curr = await page.inner_text("#pew-current-val")
            pew_10s = await page.inner_text("#pew-10s")
            pew_30s = await page.inner_text("#pew-30s")
            pew_60s = await page.inner_text("#pew-60s")
            pew_comp = await page.inner_text("#pew-component")
            sys_state = await page.inner_text("#header-state")

            print(f"State: {sys_state} | Component: {pew_comp}")
            print(f"PEW Current: {pew_curr} | 10s: {pew_10s} | 30s: {pew_30s} | 60s: {pew_60s}")

            # Extract Chart.js dataset state
            cdata = await page.evaluate("""
                () => {
                    const c = window.predictiveProjectionChart;
                    if (!c) return null;
                    const obs = c.data.datasets[0].data.filter(v => v !== null && v !== undefined);
                    const fc = c.data.datasets[1].data.filter(v => v !== null && v !== undefined);
                    return {
                        selectedParam: window.selectedProjectionParam,
                        userSelectedParam: window.userSelectedProjectionParam,
                        obsCount: obs.length,
                        firstObserved: obs.length > 0 ? obs[0] : null,
                        lastObserved: obs.length > 0 ? obs[obs.length - 1] : null,
                        forecastPoints: fc,
                        refLimit: c.data.datasets[2].data[0],
                        yMin: c.options.scales?.y?.min,
                        yMax: c.options.scales?.y?.max,
                        bufLen: window.chartDataBuffer ? window.chartDataBuffer.length : 0,
                        lastBufVal: (window.chartDataBuffer && window.chartDataBuffer.length > 0) ? window.chartDataBuffer[window.chartDataBuffer.length - 1] : null
                    };
                }
            """)

            print(f"Chart Data: {json.dumps(cdata, indent=2)}")

            # Check if chart matches PEW
            is_obs_matching = False
            if cdata and cdata["lastObserved"] is not None:
                pew_num = float(pew_curr.split()[0])
                if abs(cdata["lastObserved"] - pew_num) < 5.0:
                    is_obs_matching = True

            res_dict = {
                "param": param,
                "state": sys_state,
                "pew_curr": pew_curr,
                "pew_30s": pew_30s,
                "chart_selected": cdata["selectedParam"] if cdata else None,
                "chart_last_obs": cdata["lastObserved"] if cdata else None,
                "chart_fc": cdata["forecastPoints"] if cdata else None,
                "chart_yMin": cdata["yMin"] if cdata else None,
                "chart_yMax": cdata["yMax"] if cdata else None,
                "obs_matching": is_obs_matching
            }
            results.append(res_dict)

            # Screenshot
            ss_path = f"C:\\Users\\divya\\.gemini\\antigravity\\brain\\0097d5ff-f017-4bb7-83b2-b2aef1e3c7bc\\test_{param}_screenshot.png"
            await page.screenshot(path=ss_path)
            print(f"Saved screenshot: {ss_path}")

        print("\n==========================================")
        print("SUMMARY OF ALL CHANNELS:")
        print("==========================================")
        print(json.dumps(results, indent=2))

        # Clear final fault
        await page.evaluate("""
            async () => {
                const token = localStorage.getItem('dt_token');
                await fetch('/api/fault-injection/clear', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
            }
        """)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_all_channels())
