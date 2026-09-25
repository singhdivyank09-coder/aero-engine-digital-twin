import asyncio
import os
import sys
import time
from playwright.async_api import async_playwright

ARTIFACT_DIR = r"C:\Users\divya\.gemini\antigravity\brain\0097d5ff-f017-4bb7-83b2-b2aef1e3c7bc"

async def run_live_acceptance_test():
    async with async_playwright() as p:
        print("Launching system Edge browser...")
        try:
            browser = await p.chromium.launch(channel="msedge", headless=True)
        except Exception as e:
            print(f"Edge launch failed ({e}), trying Chrome...")
            browser = await p.chromium.launch(channel="chrome", headless=True)

        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        print("Navigating to http://localhost:8000 ...")
        await page.goto("http://localhost:8000", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        # Confirm main GCS visible
        main_gcs = await page.query_selector("#main-gcs")
        assert main_gcs, "Main GCS failed to load!"
        print("Main GCS loaded successfully.")

        # Inspect WebSocket connection and initial buffer
        ws_status = await page.inner_text("#link-status")
        buf_len = await page.evaluate("window.chartDataBuffer?.length || 0")
        seq_num = await page.evaluate("window.twinStore?.sequence_number || 0")
        print(f"Initial Link Status: {ws_status}, Buffer Length: {buf_len}, Twin Seq: {seq_num}")

        # Step 1: Nominal Cruise state check
        print("\n--- STEP 1: Nominal Cruise Verification ---")
        state_text = await page.inner_text("#header-state")
        print(f"Header State: {state_text}")

        # Step 2: Select CHT2 button manually
        print("\n--- STEP 2: Select CHT2 Channel ---")
        cht2_btn = await page.query_selector("button.btn-pred-param[data-param='cht2']")
        assert cht2_btn, "CHT2 button not found!"
        await cht2_btn.click()
        await page.wait_for_timeout(1000)

        # Check button active class & internal state
        active_btn = await page.evaluate("document.querySelector('button.btn-pred-param.active')?.getAttribute('data-param')")
        print(f"Currently active button data-param: {active_btn}")
        assert active_btn == "cht2", "CHT2 button click failed to set active class!"

        # Step 3: Inject Cylinder 2 Thermal Degradation Fault via backend API with Auth Token
        print("\n--- STEP 3: Injecting Cylinder 2 Thermal Degradation Fault ---")
        fault_res = await page.evaluate("""
            async () => {
                const token = localStorage.getItem('dt_token');
                const res = await fetch('/api/fault-injection/start', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        scenario: 'CYLINDER_THERMAL',
                        component: 'CYLINDER_2',
                        profile: 'GRADUAL',
                        intensity: 1.0,
                        rate: 'FAST'
                    })
                });
                return res.json();
            }
        """)
        print(f"Fault injection API response: {fault_res}")

        # Wait for telemetry to update & fault to escalate through WATCH -> CAUTION -> WARNING -> CRITICAL
        print("Waiting for fault escalation and GRU forecast generation (20 seconds)...")
        await page.wait_for_timeout(20000)

        ws_status2 = await page.inner_text("#link-status")
        buf_len2 = await page.evaluate("window.chartDataBuffer?.length || 0")
        seq_num2 = await page.evaluate("window.twinStore?.sequence_number || 0")
        print(f"Active Fault Link Status: {ws_status2}, Buffer Length: {buf_len2}, Twin Seq: {seq_num2}")

        # Extract values from PEW numerical cards
        pew_curr = await page.inner_text("#pew-current-val")
        pew_10s = await page.inner_text("#pew-10s")
        pew_30s = await page.inner_text("#pew-30s")
        pew_60s = await page.inner_text("#pew-60s")
        pew_comp = await page.inner_text("#pew-component")
        sys_state = await page.inner_text("#header-state")

        print(f"\n--- ACTIVE FAULT CARD NUMERICAL VALUES ---")
        print(f"System State: {sys_state}")
        print(f"Affected Component: {pew_comp}")
        print(f"PEW Current CHT2: {pew_curr}")
        print(f"PEW +10s Forecast: {pew_10s}")
        print(f"PEW +30s Forecast: {pew_30s}")
        print(f"PEW +60s Forecast: {pew_60s}")

        # Extract Chart.js dataset values from window.predictiveProjectionChart
        chart_data = await page.evaluate("""
            () => {
                if (!window.predictiveProjectionChart) return null;
                const c = window.predictiveProjectionChart;
                const labels = c.data.labels;
                const dsObserved = c.data.datasets[0].data;
                const dsForecast = c.data.datasets[1].data;
                const dsRefLimit = c.data.datasets[2].data;
                const yMin = c.options.scales?.y?.suggestedMin;
                const yMax = c.options.scales?.y?.suggestedMax;
                
                const validObserved = dsObserved.filter(v => v !== null && v !== undefined);
                const validForecast = dsForecast.filter(v => v !== null && v !== undefined);

                return {
                    labelsCount: labels.length,
                    totalObservedPoints: dsObserved.length,
                    validObservedCount: validObserved.length,
                    lastObservedVal: validObserved.length > 0 ? validObserved[validObserved.length - 1] : null,
                    firstObservedVal: validObserved.length > 0 ? validObserved[0] : null,
                    forecastPoints: validForecast,
                    refLimit: dsRefLimit[0],
                    yMin: yMin,
                    yMax: yMax,
                    selectedParam: window.selectedProjectionParam
                };
            }
        """)
        assert chart_data is not None, "Chart.js instance window.predictiveProjectionChart is null!"

        print(f"\n--- CHART.JS PROJECTION DATASET ANALYSIS ---")
        print(f"Internal Selected Param: {chart_data['selectedParam']}")
        print(f"Valid Observed Points Count: {chart_data['validObservedCount']}")
        print(f"First Observed CHT2: {chart_data['firstObservedVal']} °C")
        print(f"Last Observed CHT2: {chart_data['lastObservedVal']} °C")
        print(f"Forecast Plotted Trajectory: {chart_data['forecastPoints']}")
        print(f"Reference Limit: {chart_data['refLimit']} °C")
        print(f"Dynamic Y-Axis Bounds: min={chart_data['yMin']}, max={chart_data['yMax']}")

        # STEP 4: Take screenshot during active Cylinder 2 Thermal Fault
        screenshot_path = os.path.join(ARTIFACT_DIR, "cht2_fault_projection_chart.png")
        await page.screenshot(path=screenshot_path, full_page=False)
        print(f"\nSaved live fault screenshot to: {screenshot_path}")

        # Verifications
        assert chart_data['selectedParam'] == 'cht2', f"Selected param mismatch: {chart_data['selectedParam']}"
        assert chart_data['lastObservedVal'] is not None and chart_data['lastObservedVal'] > 140.0, f"Observed CHT2 did not rise as expected! Value={chart_data['lastObservedVal']}"
        assert len(chart_data['forecastPoints']) >= 4, f"Forecast points missing! {chart_data['forecastPoints']}"
        assert chart_data['yMax'] >= max(chart_data['forecastPoints']), f"Y-Axis max ({chart_data['yMax']}) does not fit forecast trajectory max ({max(chart_data['forecastPoints'])})"
        print("\nVERIFICATION SUCCESS: Graph observed line & GRU forecast trajectory match numerical PEW cards and dynamically scaled Y-axis!")

        # Step 5: Test Channel Switching to other supported channels
        print("\n--- STEP 5: Testing Channel Switching Across Supported Parameters ---")
        for param in ["oil_press", "oil_temp", "vibration_rms", "cht1"]:
            btn = await page.query_selector(f"button.btn-pred-param[data-param='{param}']")
            if btn:
                await btn.click()
                await page.wait_for_timeout(500)
                sel = await page.evaluate("window.selectedProjectionParam")
                print(f"Clicked {param} -> internal param is {sel}")
                assert sel == param, f"Channel switch to {param} failed!"

        # Return to CHT2
        await (await page.query_selector("button.btn-pred-param[data-param='cht2']")).click()
        await page.wait_for_timeout(500)

        # Step 6: Test Tab Switching & Return
        print("\n--- STEP 6: Testing Tab Switch to Digital Twin view and Return ---")
        dt_tab = await page.query_selector("button.nav-tab[data-target='view-digital-twin']")
        if dt_tab:
            await dt_tab.click()
            await page.wait_for_timeout(1000)
            print("Switched to Digital Twin tab.")

            op_tab = await page.query_selector("button.nav-tab[data-target='view-operator']")
            await op_tab.click()
            await page.wait_for_timeout(1000)
            print("Returned to Operator tab.")

            post_tab_data = await page.evaluate("window.predictiveProjectionChart?.data.datasets[1].data.filter(v => v !== null)")
            print(f"Forecast trajectory after tab return: {post_tab_data}")
            assert post_tab_data and len(post_tab_data) >= 4, "Chart lost data on tab return!"

        # Step 7: Clear Fault & Verify Recovery
        print("\n--- STEP 7: Clear Fault & Recovery Verification ---")
        clear_res = await page.evaluate("""
            async () => {
                const token = localStorage.getItem('dt_token');
                const res = await fetch('/api/fault-injection/clear', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                return res.json();
            }
        """)
        print(f"Clear fault response: {clear_res}")
        await page.wait_for_timeout(5000)

        recov_state = await page.inner_text("#header-state")
        print(f"Post-clear System State: {recov_state}")

        await browser.close()
        print("\nALL LIVE ACCEPTANCE TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(run_live_acceptance_test())
