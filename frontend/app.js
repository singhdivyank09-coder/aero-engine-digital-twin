// Aero Engine Digital Twin GCS HMI Logic
const API_BASE = (window.location.protocol === "file:" || !window.location.host) ? "http://127.0.0.1:8000" : "";
const WS_BASE = (window.location.protocol === "file:" || !window.location.host) ? "ws://127.0.0.1:8000" : ((window.location.protocol === "https:" ? "wss://" : "ws://") + window.location.host);

let authToken = localStorage.getItem("dt_token") || null;
let userRole = localStorage.getItem("dt_role") || null;
let userName = localStorage.getItem("dt_name") || "User";

let telemetryChart = null;
let predictiveProjectionChart = null;
let selectedProjectionParam = "cht1";
let telemetrySocket = null;
let sampleMissionData = null;
let lastHeaderRulWindowId = undefined;

document.addEventListener("DOMContentLoaded", async () => {
    initNavigationTabs();
    initLoginForm();
    initMissionSelector();
    initFaultButtons();
    initReplayScrubber();
    initReportButtons();
    initLogout();
    initTwinComponentInteractions();
    checkServerConnection();

    if (!authToken) {
        await autoLoginDefaultUser();
    } else {
        showMainGCS();
    }
});

async function autoLoginDefaultUser() {
    try {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: "engineer", password: "engineer123" })
        });
        if (res.ok) {
            const data = await res.json();
            authToken = data.access_token;
            userRole = data.role;
            userName = data.full_name;
            localStorage.setItem("dt_token", authToken);
            localStorage.setItem("dt_role", userRole);
            localStorage.setItem("dt_name", userName);
        }
    } catch(e) {
        console.error("Auto login failed:", e);
    }
    showMainGCS();
}

async function checkServerConnection() {
    const statusDiv = document.getElementById("login-server-status");
    if (!statusDiv) return;
    try {
        const res = await fetch(`${API_BASE}/api/health`);
        if (res.ok) {
            statusDiv.innerHTML = `<i class="fa-solid fa-circle-check text-green"></i> Backend Server Connected (127.0.0.1:8000)`;
        } else {
            throw new Error(`HTTP ${res.status}`);
        }
    } catch(e) {
        statusDiv.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-red"></i> Connecting to 127.0.0.1:8000... <br><span style="font-size:0.7rem; color:#94a3b8">Press <strong>Ctrl + F5</strong> if server was just restarted.</span>`;
        setTimeout(checkServerConnection, 2000);
    }
}

// LOGIN & AUTHENTICATION
function initLoginForm() {
    const loginForm = document.getElementById("login-form");
    if (!loginForm) return;

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const username = document.getElementById("username").value.trim();
        const password = document.getElementById("password").value.trim();
        const errorDiv = document.getElementById("login-error");
        errorDiv.innerText = "";

        let loginSuccess = false;
        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password })
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({ detail: "Authentication failed." }));
                errorDiv.innerText = typeof errData.detail === "string" ? errData.detail : "Invalid username or password.";
                return;
            }

            const data = await res.json();
            authToken = data.access_token;
            userRole = data.role;
            userName = data.full_name;

            localStorage.setItem("dt_token", authToken);
            localStorage.setItem("dt_role", userRole);
            localStorage.setItem("dt_name", userName);

            loginSuccess = true;
        } catch (err) {
            console.error("Login fetch error:", err);
            errorDiv.innerText = `Network connection error (${err.message}). Is server running on 127.0.0.1:8000?`;
            return;
        }

        if (loginSuccess) {
            try {
                showMainGCS();
            } catch (gcsErr) {
                console.error("GCS UI initialization error:", gcsErr);
            }
        }
    });
}

function showMainGCS() {
    document.getElementById("login-modal").classList.remove("active");
    document.getElementById("main-gcs").classList.remove("hidden");

    document.getElementById("user-display-name").innerText = userName;
    document.getElementById("user-role-badge").innerText = userRole.toUpperCase();
    document.getElementById("user-role-badge").className = `badge-role ${userRole === 'engineer' ? 'eng' : 'op'}`;

    // Apply RBAC UI restrictions
    if (userRole !== "engineer") {
        document.querySelectorAll(".eng-only").forEach(el => el.classList.add("hidden"));
    } else {
        document.querySelectorAll(".eng-only").forEach(el => el.classList.remove("hidden"));
        loadAuditLogs();
    }

    initTelemetryChart();
    initPredictiveProjectionChart();
    initResidualsChart();
    loadMlMetrics();
    connectWebSocket();
}

function initLogout() {
    const btnLogout = document.getElementById("btn-logout");
    if (!btnLogout) return;
    btnLogout.addEventListener("click", async () => {
        if (authToken) {
            try {
                await fetch(`${API_BASE}/api/audit-logs/log`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${authToken}`
                    },
                    body: JSON.stringify({
                        action: "logout",
                        details: `User ${userName} logged out`
                    })
                });
            } catch (e) {
                console.error("Failed to log logout event:", e);
            }
        }
        localStorage.clear();
        location.reload();
    });
}

// NAVIGATION TABS
function initNavigationTabs() {
    document.querySelectorAll(".nav-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

            tab.classList.add("active");
            const targetId = tab.getAttribute("data-target");
            const targetEl = document.getElementById(targetId);
            if (targetEl) {
                targetEl.classList.add("active");
            }
            
            // Immediately re-render canonical state from window.twinStore without re-fetching or resetting session
            if (window.twinStore && window.twinStore.currentSnapshot) {
                renderAllModules(window.twinStore.currentSnapshot);
            }

            if (targetId === "view-operator") {
                if (telemetryChart) {
                    telemetryChart.resize();
                    renderBufferedChart();
                }
                if (predictiveProjectionChart) {
                    predictiveProjectionChart.resize();
                    if (window.twinStore && window.twinStore.currentSnapshot) {
                        updatePredictiveProjectionChart(window.twinStore.currentSnapshot);
                    }
                }
            } else if (targetId === "view-digital-twin" && residualsChart) {
                residualsChart.resize();
                renderBufferedResidualsChart();
            } else if (targetId === "view-engineer" && faultProgressionChart) {
                faultProgressionChart.resize();
            } else if (targetId === "view-models-datasets") {
                loadMlMetrics();
            } else if (targetId === "view-metrics") {
                loadSystemMetrics();
            } else if (targetId === "view-audit") {
                loadAuditLogs();
            } else if (targetId === "view-replay") {
                loadReplayMissions();
            }
        });
    });
}

async function loadSystemMetrics() {
    try {
        const res = await fetch(`${API_BASE}/api/system/metrics`);
        if (!res.ok) return;
        const data = await res.json();

        // High-resolution Execution Rates & Latencies
        const rateStats = data.update_rate_hz || {};
        if (document.getElementById("m-rate-mean")) document.getElementById("m-rate-mean").innerText = rateStats.mean !== null && rateStats.mean !== undefined ? rateStats.mean.toFixed(1) : "N/A";
        if (document.getElementById("m-rate-med")) document.getElementById("m-rate-med").innerText = rateStats.median !== null && rateStats.median !== undefined ? rateStats.median.toFixed(1) : "N/A";
        if (document.getElementById("m-rate-p95")) document.getElementById("m-rate-p95").innerText = rateStats.p95 !== null && rateStats.p95 !== undefined ? rateStats.p95.toFixed(1) : "N/A";
        if (document.getElementById("m-rate-max")) document.getElementById("m-rate-max").innerText = rateStats.max !== null && rateStats.max !== undefined ? rateStats.max.toFixed(1) : "N/A";
        if (document.getElementById("st-rate")) {
            const stElem = document.getElementById("st-rate");
            stElem.innerText = rateStats.status || "NOT MEASURED";
            stElem.className = `gauge-state-badge ${rateStats.status === "MEASURED" ? "NORMAL" : "WATCH"}`;
        }

        const dtStats = data.dt_processing_latency_ms || {};
        if (document.getElementById("m-dt-mean")) document.getElementById("m-dt-mean").innerText = dtStats.mean !== null && dtStats.mean !== undefined ? dtStats.mean.toFixed(2) : "N/A";
        if (document.getElementById("m-dt-med")) document.getElementById("m-dt-med").innerText = dtStats.median !== null && dtStats.median !== undefined ? dtStats.median.toFixed(2) : "N/A";
        if (document.getElementById("m-dt-p95")) document.getElementById("m-dt-p95").innerText = dtStats.p95 !== null && dtStats.p95 !== undefined ? dtStats.p95.toFixed(2) : "N/A";
        if (document.getElementById("m-dt-max")) document.getElementById("m-dt-max").innerText = dtStats.max !== null && dtStats.max !== undefined ? dtStats.max.toFixed(2) : "N/A";
        if (document.getElementById("st-dt")) {
            const stElem = document.getElementById("st-dt");
            stElem.innerText = dtStats.status || "NOT MEASURED";
            stElem.className = `gauge-state-badge ${dtStats.status === "MEASURED" ? "NORMAL" : "WATCH"}`;
        }

        const mlStats = data.ml_inference_latency_ms || {};
        if (document.getElementById("m-ml-mean")) document.getElementById("m-ml-mean").innerText = mlStats.mean !== null && mlStats.mean !== undefined ? mlStats.mean.toFixed(2) : "N/A";
        if (document.getElementById("m-ml-med")) document.getElementById("m-ml-med").innerText = mlStats.median !== null && mlStats.median !== undefined ? mlStats.median.toFixed(2) : "N/A";
        if (document.getElementById("m-ml-p95")) document.getElementById("m-ml-p95").innerText = mlStats.p95 !== null && mlStats.p95 !== undefined ? mlStats.p95.toFixed(2) : "N/A";
        if (document.getElementById("m-ml-max")) document.getElementById("m-ml-max").innerText = mlStats.max !== null && mlStats.max !== undefined ? mlStats.max.toFixed(2) : "N/A";
        if (document.getElementById("st-ml")) {
            const stElem = document.getElementById("st-ml");
            stElem.innerText = mlStats.status || "NOT MEASURED";
            stElem.className = `gauge-state-badge ${mlStats.status === "MEASURED" ? "NORMAL" : "WATCH"}`;
        }

        if (document.getElementById("m-ws-rate")) {
            document.getElementById("m-ws-rate").innerText = typeof data.websocket_msg_rate_hz === "number" ? `${data.websocket_msg_rate_hz.toFixed(1)} msgs/s` : "NOT MEASURED";
        }

        // Data Quality & Ingestion Integrity
        const totalFrames = data.total_ingested_frames ?? 0;
        const droppedFrames = data.dropped_invalid_frames ?? 0;
        const ratePct = data.data_integrity_rate_pct;

        if (document.getElementById("m-total-frames")) {
            document.getElementById("m-total-frames").innerText = `${totalFrames} frames`;
        }
        if (document.getElementById("m-dropped-count")) {
            document.getElementById("m-dropped-count").innerText = `${droppedFrames} frames`;
        }

        const integrityElem = document.getElementById("m-integrity-pct");
        const statusElem = document.getElementById("st-integrity");

        if (totalFrames === 0 || ratePct === null || ratePct === undefined) {
            if (integrityElem) {
                integrityElem.innerText = "Awaiting telemetry";
                integrityElem.className = "text-muted";
            }
            if (statusElem) {
                statusElem.innerText = "NOT AVAILABLE";
                statusElem.className = "gauge-state-badge WATCH";
            }
        } else {
            if (integrityElem) {
                integrityElem.innerText = `${Number(ratePct).toFixed(1)}%`;
                integrityElem.className = Number(ratePct) >= 95.0 ? "text-green" : "text-red";
            }
            if (statusElem) {
                statusElem.innerText = data.data_integrity_status || "MEASURED";
                statusElem.className = "gauge-state-badge NORMAL";
            }
        }

    } catch (e) {
        console.error("Failed to load system runtime metrics:", e);
    }
}

async function loadMlMetrics() {
    try {
        const res = await fetch(`${API_BASE}/api/ml/metrics`);
        if (!res.ok) return;
        const data = await res.json();
        
        const ae = data.autoencoder || {};
        const aeMetrics = ae.evaluation_metrics || {};
        
        // Autoencoder Metadata
        if (document.getElementById("ae-artifact-path")) {
            document.getElementById("ae-artifact-path").innerText = ae.artifact_path || "NOT EVALUATED";
        }
        if (document.getElementById("ae-model-version")) {
            document.getElementById("ae-model-version").innerText = ae.model_version || "NOT EVALUATED";
        }
        if (document.getElementById("ae-training-dataset")) {
            document.getElementById("ae-training-dataset").innerText = ae.training_dataset || "NOT EVALUATED";
        }
        if (document.getElementById("ae-val-dataset")) {
            document.getElementById("ae-val-dataset").innerText = ae.validation_dataset || "NOT EVALUATED";
        }
        if (document.getElementById("ae-feature-count")) {
            document.getElementById("ae-feature-count").innerText = ae.feature_count ? String(ae.feature_count) : "NOT EVALUATED";
        }
        if (document.getElementById("ae-threshold-source")) {
            document.getElementById("ae-threshold-source").innerText = ae.threshold_source || "NOT EVALUATED";
        }
        if (document.getElementById("ae-eval-timestamp")) {
            document.getElementById("ae-eval-timestamp").innerText = ae.evaluation_timestamp || "NOT EVALUATED";
        }

        // Autoencoder Metrics
        if (document.getElementById("ae-metric-precision")) {
            document.getElementById("ae-metric-precision").innerText = (aeMetrics.precision !== undefined) ? `${(aeMetrics.precision * 100).toFixed(1)}%` : "NOT EVALUATED";
        }
        if (document.getElementById("ae-metric-recall")) {
            document.getElementById("ae-metric-recall").innerText = (aeMetrics.recall !== undefined) ? `${(aeMetrics.recall * 100).toFixed(1)}%` : "NOT EVALUATED";
        }
        if (document.getElementById("ae-metric-f1")) {
            document.getElementById("ae-metric-f1").innerText = (aeMetrics.f1_score !== undefined) ? `${(aeMetrics.f1_score * 100).toFixed(1)}%` : "NOT EVALUATED";
        }
        if (document.getElementById("ae-metric-roc")) {
            document.getElementById("ae-metric-roc").innerText = (aeMetrics.roc_auc !== undefined) ? aeMetrics.roc_auc.toFixed(3) : "NOT EVALUATED";
        }

        // LSTM Prognostics Metadata & Metrics
        const lstm = data.lstm_rul || {};
        const lstmMetrics = lstm.evaluation_metrics || {};

        if (document.getElementById("lstm-artifact-path")) {
            document.getElementById("lstm-artifact-path").innerText = lstm.artifact_path || "NOT EVALUATED";
        }
        if (document.getElementById("lstm-model-version")) {
            document.getElementById("lstm-model-version").innerText = lstm.model_version || "NOT EVALUATED";
        }
        if (document.getElementById("lstm-dataset")) {
            document.getElementById("lstm-dataset").innerText = lstm.training_dataset || "NOT EVALUATED";
        }
        if (document.getElementById("lstm-seq-len")) {
            document.getElementById("lstm-seq-len").innerText = lstm.sequence_length ? String(lstm.sequence_length) : "NOT EVALUATED";
        }
        if (document.getElementById("lstm-feature-count")) {
            document.getElementById("lstm-feature-count").innerText = lstm.feature_count ? `${lstm.feature_count} features` : "NOT EVALUATED";
        }
        if (document.getElementById("lstm-eval-timestamp")) {
            document.getElementById("lstm-eval-timestamp").innerText = lstm.evaluation_timestamp || "NOT EVALUATED";
        }

        if (document.getElementById("lstm-metric-mae")) {
            document.getElementById("lstm-metric-mae").innerText = (lstmMetrics.mae_cycles !== undefined) ? `${lstmMetrics.mae_cycles} cycles` : (lstmMetrics.mae_hours !== undefined ? `${lstmMetrics.mae_hours} cycles` : "NOT EVALUATED");
        }
        if (document.getElementById("lstm-metric-rmse")) {
            document.getElementById("lstm-metric-rmse").innerText = (lstmMetrics.rmse_cycles !== undefined) ? `${lstmMetrics.rmse_cycles} cycles` : (lstmMetrics.rmse_hours !== undefined ? `${lstmMetrics.rmse_hours} cycles` : "NOT EVALUATED");
        }
        if (document.getElementById("lstm-metric-r2")) {
            document.getElementById("lstm-metric-r2").innerText = (lstmMetrics.r2_score !== undefined) ? lstmMetrics.r2_score.toFixed(3) : "NOT EVALUATED";
        }
    } catch(e) {
        console.error("Failed to load ML metrics artifact:", e);
    }
}


// CANONICAL SINGLE FRONTEND STATE STORE
window.twinStore = {
    currentSnapshot: null,
    sequence_number: -1,
    lastFrameTime: Date.now(),
    update: function(snapshot) {
        if (!snapshot || typeof snapshot !== 'object') return false;
        const seq = (typeof snapshot.sequence_number === 'number') ? snapshot.sequence_number : ((typeof snapshot.sequence_no === 'number') ? snapshot.sequence_no : (snapshot.telemetry ? (snapshot.telemetry.sequence_no ?? snapshot.telemetry.sequence_number) : undefined));
        const sess = snapshot.session_id;

        // Reset sequence tracker if session ID changed
        if (this.currentSnapshot && sess && this.currentSnapshot.session_id && sess !== this.currentSnapshot.session_id) {
            this.sequence_number = -1;
        }

        // Stale snapshot protection: reject out-of-order sequence numbers within the same session
        if (typeof seq === 'number' && seq <= this.sequence_number && this.sequence_number > 0 && sess === (this.currentSnapshot ? this.currentSnapshot.session_id : null)) {
            return false;
        }

        this.sequence_number = typeof seq === 'number' ? seq : (this.sequence_number + 1);
        this.currentSnapshot = snapshot;
        this.lastFrameTime = Date.now();
        window.lastTwinFrame = snapshot;
        console.log(`[TWIN_STORE_UPDATE] raw_seq=${seq} store_seq=${this.sequence_number} snapshot_seq=${snapshot.sequence_number}`);

        if (window.DEBUG_TWIN_SYNC || (typeof seq === 'number' && (seq % 50 === 0 || seq < 5))) {
            const scName = snapshot.scenario_id || snapshot.mission_profile || (typeof snapshot.scenario === 'string' ? snapshot.scenario : snapshot.scenario?.id) || "CRUISE";
            const oldestSeq = typeof chartDataBuffer !== 'undefined' && chartDataBuffer.length > 0 ? chartDataBuffer[0].sequence_number : 'N/A';
            const newestSeq = typeof chartDataBuffer !== 'undefined' && chartDataBuffer.length > 0 ? chartDataBuffer[chartDataBuffer.length - 1].sequence_number : 'N/A';
            const oldestTime = typeof chartDataBuffer !== 'undefined' && chartDataBuffer.length > 0 ? chartDataBuffer[0].timestamp : 'N/A';
            const newestTime = typeof chartDataBuffer !== 'undefined' && chartDataBuffer.length > 0 ? chartDataBuffer[chartDataBuffer.length - 1].timestamp : 'N/A';
            console.log(`[FRONTEND_LATEST] seq=${this.sequence_number} time=${snapshot.timestamp} state=${snapshot.system_state}`);
            console.log(`[LIVE_FRAME_RX] seq=${this.sequence_number} time=${snapshot.timestamp} scenario=${scName} state=${snapshot.system_state}`);
            console.log(`[HISTORY_RANGE] oldest_seq=${oldestSeq} newest_seq=${newestSeq} oldest_time=${oldestTime} newest_time=${newestTime}`);
        }
        return true;
    }
};

function renderAllModules(frame) {
    if (!frame) return;
    const targetSnapshot = (window.twinStore && window.twinStore.currentSnapshot) ? window.twinStore.currentSnapshot : frame;
    try { updateGcsDfcsDemonstrator(targetSnapshot); } catch (e) { console.error("Error in updateGcsDfcsDemonstrator:", e); }
    try { updateDashboard(targetSnapshot); } catch (e) { console.error("Error in updateDashboard:", e); }
    try { updateDigitalTwinSchematic(targetSnapshot); } catch (e) { console.error("Error in updateDigitalTwinSchematic:", e); }
    try { updateEngineerAnalytics(targetSnapshot); } catch (e) { console.error("Error in updateEngineerAnalytics:", e); }
    try { updateDevSyncBadge(targetSnapshot); } catch (e) { console.error("Error in updateDevSyncBadge:", e); }
}

function updateDevSyncBadge(frame) {
    let badge = document.getElementById("dev-sync-badge");
    if (!badge) {
        badge = document.createElement("div");
        badge.id = "dev-sync-badge";
        badge.style.cssText = "position: fixed; bottom: 8px; right: 12px; z-index: 99999; background: rgba(15, 23, 42, 0.92); border: 1px solid rgba(56, 189, 248, 0.5); border-radius: 6px; padding: 4px 10px; font-family: monospace; font-size: 0.72rem; color: #38bdf8; box-shadow: 0 4px 12px rgba(0,0,0,0.4); pointer-events: none;";
        document.body.appendChild(badge);
    }

    const snapshot = (window.twinStore && window.twinStore.currentSnapshot) ? window.twinStore.currentSnapshot : frame;
    if (!snapshot) return;

    const rawSess = snapshot.session_id || "DATA UNAVAILABLE";
    const sess = String(rawSess).replace(/SIH\s*26054/gi, "DEMO_PROTOTYPE");
    const seq = snapshot.sequence_number !== undefined && snapshot.sequence_number !== null ? snapshot.sequence_number : "DATA UNAVAILABLE";
    const ts = typeof snapshot.timestamp === 'number' ? snapshot.timestamp.toFixed(1) : (snapshot.timestamp || "0.0");

    let sc = "DATA UNAVAILABLE";
    if (typeof snapshot.scenario === 'string' && snapshot.scenario.trim() !== '') {
        sc = snapshot.scenario;
    } else if (snapshot.scenario && typeof snapshot.scenario === 'object' && snapshot.scenario.id) {
        sc = snapshot.scenario.id;
    } else if (typeof snapshot.scenario_id === 'string') {
        sc = snapshot.scenario_id;
    } else if (typeof snapshot.mission_profile === 'string') {
        sc = snapshot.mission_profile;
    }

    const st = snapshot.system_state || snapshot.global_state || "DATA UNAVAILABLE";
    badge.innerText = `[TWIN_SYNC] Session: ${sess} | Seq: #${seq} | Time: t=${ts}s | Scenario: ${sc} | State: ${st}`;

    if (window.DEBUG_TWIN_SYNC) {
        console.log(`[TWIN FOOTER RENDER] seq=${seq} time=${ts} scenario=${sc} state=${st}`);
    }
}

// Lightweight Link Freshness Monitor
setInterval(() => {
    const statusElem = document.getElementById("link-status");
    if (!statusElem) return;
    if (!telemetrySocket || telemetrySocket.readyState !== WebSocket.OPEN) {
        statusElem.innerText = "DISCONNECTED";
        statusElem.style.color = "var(--hud-red)";
        return;
    }
    const elapsed = Date.now() - (window.twinStore?.lastFrameTime || 0);
    if (elapsed > 2000) {
        statusElem.innerText = "STALE (No Frames)";
        statusElem.style.color = "var(--hud-red)";
    } else if (elapsed > 500) {
        statusElem.innerText = "DEGRADED";
        statusElem.style.color = "var(--hud-yellow)";
    } else {
        statusElem.innerText = "SYNCHRONIZED (10Hz)";
        statusElem.style.color = "var(--hud-green)";
    }
}, 500);

// WEBSOCKET TELEMETRY STREAM
function connectWebSocket() {
    if (telemetrySocket && (telemetrySocket.readyState === WebSocket.OPEN || telemetrySocket.readyState === WebSocket.CONNECTING)) {
        return;
    }
    const wsUrl = `${WS_BASE}/ws/telemetry`;

    try {
        telemetrySocket = new WebSocket(wsUrl);
        window.telemetrySocket = telemetrySocket;

        telemetrySocket.onopen = () => {
            const statusElem = document.getElementById("link-status");
            if (statusElem) {
                statusElem.innerText = "SYNCHRONIZED (10Hz)";
                statusElem.style.color = "var(--hud-green)";
            }
            const gcsLinkStatus = document.getElementById("gcs-link-status");
            if (gcsLinkStatus) {
                gcsLinkStatus.innerHTML = `<i class="fa-solid fa-signal"></i> CONNECTED`;
                gcsLinkStatus.className = "text-green font-bold";
            }
        };

        telemetrySocket.onmessage = (event) => {
            try {
                const twinFrame = JSON.parse(event.data);
                if (window.twinStore.update(twinFrame)) {
                    renderAllModules(window.twinStore.currentSnapshot);
                }
            } catch (err) {
                console.error("Error updating modules from WebSocket frame:", err);
            }
        };

        telemetrySocket.onclose = () => {
            const statusElem = document.getElementById("link-status");
            if (statusElem) {
                statusElem.innerText = "DISCONNECTED";
                statusElem.style.color = "var(--hud-red)";
            }
            const gcsLinkStatus = document.getElementById("gcs-link-status");
            if (gcsLinkStatus) {
                gcsLinkStatus.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> DISCONNECTED / LINK DEGRADED`;
                gcsLinkStatus.className = "text-red font-bold";
            }
            setTimeout(connectWebSocket, 2000);
        };

        telemetrySocket.onerror = (err) => {
            console.error("WebSocket error:", err);
        };
    } catch (e) {
        console.error("Failed to connect WebSocket:", e);
        setTimeout(connectWebSocket, 2000);
    }
}

// DASHBOARD STATE UPDATER
// DASHBOARD STATE UPDATER
function updateDashboard(frame) {
    if (!frame) return;
    receivedFrameCount++;
    const telem = frame.telemetry || frame;
    const phy = frame.physics_baseline || {};
    const ai = frame;

    // 1. Header HUD Pills & System State Machine
    const sysState = frame.system_state || "NORMAL";
    const stateBadge = document.getElementById("header-state");
    if (stateBadge) {
        stateBadge.innerText = sysState;
        stateBadge.className = `badge-state ${sysState}`;
    }

    if (document.getElementById("header-hi")) {
        document.getElementById("header-hi").innerText = `${(frame.overall_health_index ?? 98.0).toFixed(1)}%`;
    }
    if (document.getElementById("header-anomaly")) {
        document.getElementById("header-anomaly").innerText = (frame.anomaly_score ?? 0.015).toFixed(3);
    }
    if (document.getElementById("header-rul") || document.getElementById("gcs-rul-display")) {
        const rulObj = frame.prototype_rul_estimate || frame.rul || {};
        const seqWindowId = rulObj.sequence_window_id ?? null;
        const status = rulObj.model_status || "";
        const displayCycles = rulObj.display_prediction_cycles;
        
        let shouldUpdateDom = false;
        let rulText = "Warming up / insufficient sequence";
        
        if (displayCycles !== null && displayCycles !== undefined && (status === "INFERENCE ACTIVE" || status === "READY")) {
            rulText = `${Number(displayCycles).toFixed(1)} cycles`;
            if (seqWindowId !== lastHeaderRulWindowId) {
                lastHeaderRulWindowId = seqWindowId;
                shouldUpdateDom = true;
            }
        } else {
            if (status === "ERROR") {
                rulText = "ERROR";
            } else {
                rulText = "Warming up / insufficient sequence";
            }
            const warmupState = `WARMUP_${status}`;
            if (lastHeaderRulWindowId !== warmupState) {
                lastHeaderRulWindowId = warmupState;
                shouldUpdateDom = true;
            }
        }

        if (shouldUpdateDom) {
            if (document.getElementById("header-rul")) {
                document.getElementById("header-rul").innerText = rulText;
            }
            if (document.getElementById("gcs-rul-display")) {
                document.getElementById("gcs-rul-display").innerText = rulText;
            }
        }
    }

    // GCS & DFCS Demonstrator Live Synchronization
    if (document.getElementById("gcs-state-display")) {
        const stateElem = document.getElementById("gcs-state-display");
        stateElem.innerText = sysState;
        stateElem.className = `badge-state ${sysState}`;
    }

    if (document.getElementById("gcs-hi-display")) {
        document.getElementById("gcs-hi-display").innerText = `${(frame.overall_health_index ?? 98.0).toFixed(1)}%`;
    }

    if (document.getElementById("gcs-anomaly-display")) {
        const score = (frame.anomaly_score ?? 0.015).toFixed(3);
        const diags = frame.predictive_diagnostics || frame.diagnostics || [];
        const label = diags.length > 0 ? diags[0].classifier_label : "Nominal";
        document.getElementById("gcs-anomaly-display").innerText = `Score: ${score} (${label})`;
    }

    if (document.getElementById("gcs-timestamp-display")) {
        const ts = telem.timestamp ?? frame.timestamp ?? 0;
        const tsStr = (typeof ts === 'number') ? `t=${ts.toFixed(1)}s` : String(ts);
        document.getElementById("gcs-timestamp-display").innerText = tsStr;
    }

    // 2. Scenario & Environment Display Bar
    const scenarioId = typeof frame.scenario === 'object' ? frame.scenario.id : (frame.scenario || frame.mission_profile || "CRUISE");
    const params = frame.scenario_parameters || {};
    if (document.getElementById("op-env-scenario")) document.getElementById("op-env-scenario").innerText = scenarioId;
    if (document.getElementById("op-env-alt")) document.getElementById("op-env-alt").innerText = `${(params.altitude_m ?? 1500).toLocaleString()} m`;
    if (document.getElementById("op-env-temp")) document.getElementById("op-env-temp").innerText = `${(params.ambient_temp_c ?? 15.0).toFixed(1)} °C`;
    if (document.getElementById("op-env-throttle")) document.getElementById("op-env-throttle").innerText = `${(params.throttle_pct ?? 75.0).toFixed(1)} %`;
    if (document.getElementById("op-env-load")) document.getElementById("op-env-load").innerText = `${(params.engine_load_pct ?? 70.0).toFixed(1)} %`;

    // Synchronize Mission Profile Dropdown with Canonical Backend Scenario
    const sel = document.getElementById("mission-profile-select");
    if (sel && sel !== document.activeElement) {
        sel.value = scenarioId;
    }

    // 3. State Progression Horizontal Indicator Bar
    const transitionMeta = frame.state_transition_metadata || frame.state_decision_explanation || {};
    const prevState = transitionMeta.previous_state || "NORMAL";
    const reasonText = frame.state_reasoning || frame.state_reason || transitionMeta.transition_reason || "System operating within nominal baseline envelope";
    const transTime = transitionMeta.timestamp ? `t=${Number(transitionMeta.timestamp).toFixed(1)}s` : `t=${Number(telem.timestamp || frame.timestamp || 0).toFixed(1)}s`;

    ["NORMAL", "WATCH", "CAUTION", "WARNING", "CRITICAL"].forEach(st => {
        const stepEl = document.getElementById(`sp-step-${st}`);
        if (stepEl) {
            stepEl.className = st === sysState ? `sp-step ${st} active` : `sp-step ${st}`;
        }
    });

    if (document.getElementById("sp-prev")) document.getElementById("sp-prev").innerText = prevState;
    if (document.getElementById("sp-curr")) {
        const currEl = document.getElementById("sp-curr");
        currEl.innerText = sysState;
        currEl.className = `badge-state ${sysState}`;
    }
    if (document.getElementById("sp-reason")) document.getElementById("sp-reason").innerText = reasonText;
    if (document.getElementById("sp-time")) document.getElementById("sp-time").innerText = transTime;

    // 4. Simulated Fault Injection Active Banner
    const activeFaults = frame.active_faults || [];
    const faultBanner = document.getElementById("simulated-fault-banner");
    if (faultBanner) {
        if (activeFaults.length > 0) {
            faultBanner.classList.remove("hidden");
            const af = activeFaults[0];
            if (document.getElementById("s-fault-scenario")) document.getElementById("s-fault-scenario").innerText = af.fault_scenario || af.scenario || "FAULT";
            if (document.getElementById("s-fault-comp")) document.getElementById("s-fault-comp").innerText = af.affected_component || af.component || "CYLINDER_1";
            if (document.getElementById("s-fault-prof")) document.getElementById("s-fault-prof").innerText = af.injection_profile || af.profile || "GRADUAL";
            if (document.getElementById("s-fault-effect")) document.getElementById("s-fault-effect").innerText = `${Math.round(af.current_effect_pct || (af.intensity * 100) || 0)}%`;
            if (document.getElementById("s-fault-elapsed")) document.getElementById("s-fault-elapsed").innerText = `${(af.elapsed_seconds || 0).toFixed(1)}s`;
        } else {
            faultBanner.classList.add("hidden");
        }
    }

    // 5. Real Predictive Early Warning Panel (Canonical Single Snapshot Sync)
    const ass = frame.latest_predictive_assessment || frame.predictive_assessment || (frame.predictive_health_assessments && frame.predictive_health_assessments[0]) || null;
    const fc = frame.latest_forecast || frame.forecast || {};
    const fcMode = frame.forecast_mode || fc.forecast_mode || "STATISTICAL_FALLBACK";
    const fcStatus = fc.status || "WARMING_UP";

    const warmupBadge = document.getElementById("pew-warmup-badge");
    if (warmupBadge) {
        if (fcStatus !== "READY") warmupBadge.classList.remove("hidden");
        else warmupBadge.classList.add("hidden");
    }

    const sourceBadge = document.getElementById("pew-model-source");
    if (sourceBadge) {
        if (fcMode === "GRU_MODEL" && fcStatus === "READY") {
            sourceBadge.innerHTML = `<i class="fa-solid fa-brain"></i> GRU Short-Horizon Model`;
            sourceBadge.style.background = "#e0e7ff";
            sourceBadge.style.color = "#3730a3";
        } else {
            sourceBadge.innerHTML = `<i class="fa-solid fa-chart-line"></i> Statistical Fallback`;
            sourceBadge.style.background = "#f1f5f9";
            sourceBadge.style.color = "#475569";
        }
    }

    const predStatus = (ass && ass.predictive_status && ass.predictive_status !== "NOMINAL")
        ? ass.predictive_status
        : ((ass && ass.status && ass.status !== "NOMINAL") ? ass.status : "NOMINAL");

    const isNominalDisplay = (predStatus === "NOMINAL" || (frame.system_state === "NORMAL" && (!frame.active_faults || frame.active_faults.length === 0) && (!frame.predictive_diagnostics || frame.predictive_diagnostics.length === 0)));

    const pewStatusBadge = document.getElementById("pew-status-badge");
    if (pewStatusBadge) {
        pewStatusBadge.innerText = isNominalDisplay ? "NOMINAL" : predStatus.replace(/_/g, " ");
        pewStatusBadge.className = `badge-state ${isNominalDisplay ? "NOMINAL" : predStatus}`;
    }

    const affectedSubsystem = isNominalDisplay ? "NONE" : (ass ? (ass.affected_subsystem || ass.subsystem || "NONE") : "NONE");
    const affectedCompLabel = isNominalDisplay ? "NONE" : (ass ? (ass.affected_component || ass.component || "NONE") : "NONE");
    const predictedFailureMode = isNominalDisplay ? "NONE" : (ass ? (ass.predicted_failure_mode || ass.description || "NONE") : "NONE");

    const primaryParamKey = (ass && ass.primary_parameter && ass.primary_parameter !== "NONE")
        ? ass.primary_parameter
        : (selectedProjectionParam || "cht1");
    const primaryParamLabel = (ass && ass.primary_parameter_label && ass.primary_parameter_label !== "Signal")
        ? ass.primary_parameter_label
        : primaryParamKey.toUpperCase();

    // Robust unit resolution per channel
    let primaryUnit = "°C";
    const kNorm = String(primaryParamKey).toLowerCase();
    if (kNorm.includes("press")) primaryUnit = "bar";
    else if (kNorm.includes("vib")) primaryUnit = "g";
    else if (kNorm.includes("volt")) primaryUnit = "V";
    else if (kNorm.includes("rpm")) primaryUnit = "RPM";
    else if (ass && ass.unit && ass.unit !== "Signal") primaryUnit = ass.unit;

    // Helper to safely extract signal value from telemetry dictionary
    const getTelemSignalVal = (key) => {
        if (!key || !telem) return undefined;
        const k = String(key).toLowerCase();
        if (telem[k] !== undefined && telem[k] !== null) return parseFloat(telem[k]);
        if (k === "oil_press" && telem.oilPress !== undefined) return parseFloat(telem.oilPress);
        if (k === "oil_press" && telem.oil_pressure !== undefined) return parseFloat(telem.oil_pressure);
        if (k === "oil_temp" && telem.oil_temperature !== undefined) return parseFloat(telem.oil_temperature);
        if (k === "vibration_rms" && telem.vibration !== undefined) return parseFloat(telem.vibration);
        return undefined;
    };

    let rawVal = getTelemSignalVal(primaryParamKey);
    if (rawVal === undefined) rawVal = getTelemSignalVal(selectedProjectionParam);
    if (rawVal === undefined) rawVal = parseFloat(telem.cht1) || 120.0;
    const currentVal = rawVal;

    if (document.getElementById("pew-subsystem")) document.getElementById("pew-subsystem").innerText = affectedSubsystem;
    if (document.getElementById("pew-component")) document.getElementById("pew-component").innerText = affectedCompLabel;
    if (document.getElementById("pew-failure-mode")) document.getElementById("pew-failure-mode").innerText = predictedFailureMode;

    const decCount = (primaryUnit === "bar" || primaryUnit === "g") ? 2 : 1;
    if (document.getElementById("pew-current-val")) document.getElementById("pew-current-val").innerText = `${currentVal.toFixed(decCount)} ${primaryUnit}`;

    let refEnvText = "110.0 - 145.0 °C";
    if (ass && ass.reference_envelope_text) {
        refEnvText = ass.reference_envelope_text;
    } else if (ass && ass.reference_envelope) {
        refEnvText = `${ass.reference_envelope.lower} - ${ass.reference_envelope.upper} ${ass.reference_envelope.unit}`;
    }

    if (document.getElementById("pew-ref-envelope")) {
        const envElem = document.getElementById("pew-ref-envelope");
        envElem.innerText = refEnvText;
        envElem.className = isNominalDisplay ? "pew-item-val text-green" : (predStatus === "ACTIVE_FAULT" ? "pew-item-val text-red" : "pew-item-val text-amber");
    }

    const getSafeNum = (v) => (typeof v === 'number' && !isNaN(v)) ? v : (v !== null && v !== undefined && !isNaN(parseFloat(v)) ? parseFloat(v) : null);

    const ttr = formatTimeToRisk(ass);
    if (document.getElementById("pew-time-to-risk")) document.getElementById("pew-time-to-risk").innerText = ttr;

    const degScore = getSafeNum(ass?.degradation_score) ?? getSafeNum(ass?.degradation_index) ?? getSafeNum(ass?.risk_score);
    const riskScore = isNominalDisplay ? "0.00" : (degScore !== null ? degScore.toFixed(2) : "0.00");
    if (document.getElementById("pew-risk-score")) document.getElementById("pew-risk-score").innerText = `${riskScore} / 1.0`;

    // GRU +10s / +30s / +60s Forecast Cards vs Warmup
    let defaultFallback = (fcStatus === "WARMING_UP") ? "Warming up..." : "Awaiting next inference...";
    let val10Str = defaultFallback;
    let val30Str = defaultFallback;
    let val60Str = defaultFallback;
    let fc30Num = null;

    const f10Dict = fc.forecast_10s || (fc.forecast && fc.forecast["10s"]) || {};
    const f30Dict = fc.forecast_30s || (fc.forecast && fc.forecast["30s"]) || {};
    const f60Dict = fc.forecast_60s || (fc.forecast && fc.forecast["60s"]) || {};

    if (fcStatus === "READY") {
        const targetKey = primaryParamKey;
        const extractFcVal = (dict) => {
            if (!dict) return undefined;
            if (dict[targetKey] !== undefined && dict[targetKey] !== null) return parseFloat(dict[targetKey]);
            if (targetKey === "oil_press" && dict["oil_pressure"] !== undefined) return parseFloat(dict["oil_pressure"]);
            if (targetKey === "oil_temp" && dict["oil_temperature"] !== undefined) return parseFloat(dict["oil_temperature"]);
            if (dict["cht1"] !== undefined) return parseFloat(dict["cht1"]);
            return undefined;
        };

        const f10 = extractFcVal(f10Dict) ?? currentVal;
        const f30 = extractFcVal(f30Dict) ?? currentVal;
        const f60 = extractFcVal(f60Dict) ?? currentVal;

        if (f10 !== null && f10 !== undefined) val10Str = `${Number(f10).toFixed(decCount)} ${primaryUnit}`;
        if (f30 !== null && f30 !== undefined) {
            fc30Num = Number(f30);
            val30Str = `${fc30Num.toFixed(decCount)} ${primaryUnit}`;
        }
        if (f60 !== null && f60 !== undefined) val60Str = `${Number(f60).toFixed(decCount)} ${primaryUnit}`;
    }

    if (document.getElementById("pew-10s")) document.getElementById("pew-10s").innerText = val10Str;
    if (document.getElementById("pew-30s")) document.getElementById("pew-30s").innerText = val30Str;
    if (document.getElementById("pew-60s")) document.getElementById("pew-60s").innerText = val60Str;

    // Callout Box Text Formatting
    const calloutCard = document.getElementById("predictive-early-warning-card");
    const calloutBox = document.getElementById("pew-callout-box");
    const calloutTitle = document.getElementById("pew-callout-title");
    const calloutBody = document.getElementById("pew-callout-body");

    if (calloutBox && calloutTitle && calloutBody) {
        const isCurrentInActiveFault = (predStatus === "ACTIVE_FAULT");
        const isFuturePredictiveRisk = (predStatus === "PREDICTIVE_RISK") || (predStatus === "DEGRADATION_DETECTED");

        if (isCurrentInActiveFault) {
            if (calloutCard) { calloutCard.style.borderLeftColor = "#dc2626"; calloutCard.style.background = "#fef2f2"; }
            calloutBox.style.borderLeftColor = "#dc2626";
            calloutBox.style.background = "#ffffff";
            calloutTitle.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-red"></i> ACTIVE FAULT DETECTED (${primaryParamLabel} Threshold Exceeded)`;
            calloutTitle.style.color = "#b91c1c";
            calloutBody.innerText = `Current ${primaryParamLabel} (${currentVal.toFixed(1)} ${primaryUnit}) HAS ENTERED active fault region (Envelope: ${refEnvText}). Emergency/reduced flight envelope advisory active.`;
        } else if (isFuturePredictiveRisk) {
            if (calloutCard) { calloutCard.style.borderLeftColor = "#d97706"; calloutCard.style.background = "#fffdf5"; }
            calloutBox.style.borderLeftColor = "#d97706";
            calloutBox.style.background = "#ffffff";
            calloutTitle.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-orange"></i> ${predStatus.replace(/_/g, " ")} — Pre-Occurrence Early Warning`;
            calloutTitle.style.color = "#b45309";
            
            const ttrVal = (ass && ass.estimated_time_to_risk_seconds !== null && ass.estimated_time_to_risk_seconds !== undefined) ? Math.round(ass.estimated_time_to_risk_seconds) : (ass && ass.estimated_time_to_risk !== undefined ? Math.round(ass.estimated_time_to_risk) : 27);
            const upperLimit = ass && ass.reference_envelope ? ass.reference_envelope.upper : 145.0;

            if (fcStatus === "READY" && fc30Num !== null) {
                if (fc30Num >= upperLimit) {
                    calloutBody.innerHTML = `<strong>Current ${primaryParamLabel} (${currentVal.toFixed(1)} ${primaryUnit}) is STILL NORMAL</strong> (envelope ${refEnvText}). However, GRU 30-second forecast predicts trajectory will reach <strong>${fc30Num.toFixed(1)} ${primaryUnit}</strong> (exceeding safety limit) in <strong>~${ttrVal} seconds</strong>.`;
                } else {
                    calloutBody.innerHTML = `<strong>Current ${primaryParamLabel} (${currentVal.toFixed(1)} ${primaryUnit}) is STILL NORMAL</strong> (envelope ${refEnvText}). Early degradation trend detected, GRU 30s forecast projects <strong>${fc30Num.toFixed(1)} ${primaryUnit}</strong> (approaching limit in ~${ttrVal}s).`;
                }
            } else {
                calloutBody.innerHTML = `<strong>Current ${primaryParamLabel} (${currentVal.toFixed(1)} ${primaryUnit}) is STILL NORMAL</strong> (envelope ${refEnvText}). Early degradation trend & physics residual slope detected (GRU status: WARMING UP). Estimated limit breach in <strong>~${ttrVal}s</strong>.`;
            }
        } else {
            if (calloutCard) { calloutCard.style.borderLeftColor = "#059669"; calloutCard.style.background = "#f0fdf4"; }
            calloutBox.style.borderLeftColor = "#059669";
            calloutBox.style.background = "#ffffff";
            calloutTitle.innerHTML = `<i class="fa-solid fa-circle-check text-green"></i> Predictive Status: NOMINAL`;
            calloutTitle.style.color = "#15803d";
            calloutBody.innerText = `Current parameters are inside reference envelope. Short-horizon trajectory forecasts predict stable flight behavior over the next 60 seconds.`;
        }
    }

    if (document.getElementById("pew-evidence-list")) {
        const evList = ass && ass.evidence_sources ? ass.evidence_sources.join(" • ") : "GRU Forecast, Autoencoder Anomaly, CUSUM, Physics Residuals";
        document.getElementById("pew-evidence-list").innerText = evList;
    }
    if (document.getElementById("pew-reason-text")) {
        document.getElementById("pew-reason-text").innerText = reasonText;
    }

    // 6. Independent Subsystem Health Cards
    const subStates = frame.subsystem_states || {};
    const subHealth = frame.subsystem_health || {};

    ["thermal", "lubrication", "combustion", "mechanical", "electrical"].forEach(subKey => {
        const val = subHealth[subKey] ?? 100.0;
        const st = subStates[subKey] || (val < 70 ? "CRITICAL" : (val < 80 ? "WARNING" : (val < 90 ? "CAUTION" : "NORMAL")));
        
        const valEl = document.getElementById(`subval-${subKey}`);
        const stEl = document.getElementById(`substate-${subKey}`);
        const trEl = document.getElementById(`subtrend-${subKey}`);

        if (valEl) {
            valEl.innerText = `${Math.round(val)}%`;
            valEl.className = val < 75 ? "sub-val text-red" : (val < 85 ? "sub-val" : "sub-val text-green");
        }
        if (stEl) {
            stEl.innerText = st;
            stEl.className = `gauge-state-badge ${st}`;
        }
        if (trEl) {
            trEl.innerText = st !== "NORMAL" ? "Degrading" : "Stable";
        }
    });

    // Gauges
    if (document.getElementById("val-rpm")) document.getElementById("val-rpm").innerText = Math.round(telem.rpm || 5000);
    if (document.getElementById("val-oil-press")) document.getElementById("val-oil-press").innerText = (telem.oil_press || 4.2).toFixed(2);
    if (document.getElementById("val-oil-temp")) document.getElementById("val-oil-temp").innerText = (telem.oil_temp || 88.0).toFixed(1);
    if (document.getElementById("val-fuel-flow")) document.getElementById("val-fuel-flow").innerText = (telem.fuel_flow || 17.5).toFixed(2);
    if (document.getElementById("val-vibration")) document.getElementById("val-vibration").innerText = (telem.vibration_rms || 1.1).toFixed(2);
    if (document.getElementById("val-battery")) document.getElementById("val-battery").innerText = (telem.battery_volt || 14.1).toFixed(2);

    const updateGaugeBadge = (elemId, stateVal) => {
        const elem = document.getElementById(elemId);
        if (elem) {
            elem.innerText = stateVal;
            elem.className = `gauge-state-badge ${stateVal}`;
        }
    };

    const pStatuses = frame.parameter_statuses || {};
    updateGaugeBadge("gstate-rpm", pStatuses.rpm ? pStatuses.rpm.status : (subStates["thermal"] || "NORMAL"));
    updateGaugeBadge("gstate-oil-press", pStatuses.oil_press ? pStatuses.oil_press.status : (subStates["lubrication"] || "NORMAL"));
    updateGaugeBadge("gstate-oil-temp", pStatuses.oil_temp ? pStatuses.oil_temp.status : (subStates["lubrication"] || "NORMAL"));
    updateGaugeBadge("gstate-fuel-flow", pStatuses.fuel_flow ? pStatuses.fuel_flow.status : (subStates["combustion"] || "NORMAL"));
    updateGaugeBadge("gstate-vibration", pStatuses.vibration_rms ? pStatuses.vibration_rms.status : (subStates["mechanical"] || "NORMAL"));
    updateGaugeBadge("gstate-battery", pStatuses.battery_volt ? pStatuses.battery_volt.status : (subStates["electrical"] || "NORMAL"));

    // Cylinder Temperature Matrix
    for (let i = 1; i <= 4; i++) {
        const chtVal = telem[`cht${i}`] !== undefined ? parseFloat(telem[`cht${i}`]) : 120.0;
        const egtVal = telem[`egt${i}`] !== undefined ? parseFloat(telem[`egt${i}`]) : 750.0;

        const chtHeight = Math.min(100, Math.max(6, (chtVal / 200.0) * 100));
        const egtHeight = Math.min(100, Math.max(6, (egtVal / 1000.0) * 100));

        const barCht = document.getElementById(`bar-cht${i}`);
        const valCht = document.getElementById(`val-cht${i}`);
        const stateCht = document.getElementById(`state-cht${i}`);
        const boxCht = document.getElementById(`cylbox-cht${i}`);

        if (valCht) valCht.innerText = `${Math.round(chtVal)}°C`;
        if (barCht) barCht.style.height = `${chtHeight}%`;

        const cylChtState = pStatuses[`cht${i}`] ? pStatuses[`cht${i}`].status : (chtVal >= 145.0 ? "CRITICAL" : (chtVal >= 135.0 ? "WARNING" : (chtVal >= 128.0 ? "WATCH" : "NORMAL")));

        if (stateCht) {
            stateCht.innerText = cylChtState;
            stateCht.className = `cyl-state-badge ${cylChtState}`;
        }

        if (boxCht) {
            if (cylChtState === "WARNING" || cylChtState === "CRITICAL") {
                boxCht.style.border = "2px solid #dc2626";
                boxCht.style.background = "#fef2f2";
                if (barCht) barCht.style.background = "#dc2626";
            } else if (cylChtState === "CAUTION") {
                boxCht.style.border = "2px solid #d97706";
                boxCht.style.background = "#fffdf5";
                if (barCht) barCht.style.background = "#d97706";
            } else if (cylChtState === "WATCH") {
                boxCht.style.border = "1px solid #3b82f6";
                boxCht.style.background = "#eff6ff";
                if (barCht) barCht.style.background = "#2563eb";
            } else {
                boxCht.style.border = "1px solid var(--border-light)";
                boxCht.style.background = "var(--bg-card)";
                if (barCht) barCht.style.background = "linear-gradient(to top, #0284c7, #059669)";
            }
        }

        const barEgt = document.getElementById(`bar-egt${i}`);
        const valEgt = document.getElementById(`val-egt${i}`);
        const stateEgt = document.getElementById(`state-egt${i}`);
        const boxEgt = document.getElementById(`cylbox-egt${i}`);

        if (valEgt) valEgt.innerText = `${Math.round(egtVal)}°C`;
        if (barEgt) barEgt.style.height = `${egtHeight}%`;

        const cylEgtState = pStatuses[`egt${i}`] ? pStatuses[`egt${i}`].status : (egtVal >= 850.0 ? "CRITICAL" : (egtVal >= 800.0 ? "WARNING" : (egtVal >= 775.0 ? "WATCH" : "NORMAL")));

        if (stateEgt) {
            stateEgt.innerText = cylEgtState;
            stateEgt.className = `cyl-state-badge ${cylEgtState}`;
        }
    }

    updateDigitalTwinSchematic(frame);

    // Residuals Table
    const resTab = frame.residuals_table || {};
    const updateResRow = (key, actId, phyId, deltaId, statusId, unit, abnLimit) => {
        const item = resTab[key];
        if (!item) return;
        const obs = item.observed_value ?? item.observed;
        const exp = item.predicted_value ?? item.expected;
        const res = item.residual ?? 0.0;
        const st = item.residual_status || item.status || "NORMAL";

        if (document.getElementById(actId)) document.getElementById(actId).innerText = `${obs} ${unit}`;
        if (document.getElementById(phyId)) document.getElementById(phyId).innerText = `${exp} ${unit}`;
        if (document.getElementById(deltaId)) {
            document.getElementById(deltaId).innerText = `${res >= 0 ? '+' : ''}${res}`;
            document.getElementById(deltaId).className = Math.abs(res) >= abnLimit ? 'text-red' : 'text-green';
        }
        if (document.getElementById(statusId)) {
            document.getElementById(statusId).innerText = st;
            document.getElementById(statusId).className = `gauge-state-badge ${st}`;
        }
    };

    updateResRow("power_kw", "res-act-power", "res-phy-power", "res-delta-power", "status-power", "kW", 5.0);
    updateResRow("avg_cht", "res-act-cht", "res-phy-cht", "res-delta-cht", "status-cht", "°C", 8.0);
    updateResRow("avg_egt", "res-act-egt", "res-phy-egt", "res-delta-egt", "status-egt", "°C", 25.0);
    updateResRow("oil_press", "res-act-oil", "res-phy-oil", "res-delta-oil", "status-oil", "bar", 0.40);
    updateResRow("oil_temp", "res-act-oil-t", "res-phy-oil-t", "res-delta-oil-t", "status-oil-t", "°C", 5.0);

    updateResidualsChartData(resTab, telem.timestamp || frame.timestamp);

    // Fault Alerts Console (Consumes Canonical Snapshot Diagnostics or Fallback Primary/Secondary Conditions)
    let diagnostics = frame.predictive_diagnostics || frame.diagnostics || [];
    if ((!diagnostics || diagnostics.length === 0) && sysState !== "NORMAL" && frame.detected_primary_condition) {
        const prim = frame.detected_primary_condition;
        diagnostics = [{
            classifier_label: `${prim.subsystem} Subsystem Anomaly`,
            classifier_confidence: 0.95,
            status: sysState === "CRITICAL" || sysState === "WARNING" ? "ACTIVE_FAULT" : "PREDICTIVE_RISK",
            affected_subsystem: prim.subsystem,
            affected_component: prim.component,
            observed_parameter: `${prim.subsystem} Status`,
            observed_value: prim.state,
            threshold_or_expected_range: "Nominal Envelope",
            trend: "Degradation trend active",
            evidence_sources: prim.evidence && prim.evidence.length > 0 ? prim.evidence : [`Primary Subsystem: ${prim.subsystem}`, `Affected Component: ${prim.component}`],
            advisory: `Engineering inspection recommended for ${prim.subsystem.toLowerCase()} subsystem.`,
            priority: sysState === "CRITICAL" ? "Critical" : "High"
        }];
    }

function formatConfidence(conf) {
    if (conf === null || conf === undefined) return "95.0%";
    const val = typeof conf === 'number' ? (conf <= 1.0 ? conf * 100 : conf) : parseFloat(conf);
    return isNaN(val) ? "95.0%" : `${val.toFixed(1)}%`;
}

    try {
        const alertsContainer = document.getElementById("alerts-container");
        if (alertsContainer) {
            if (diagnostics.length > 0) {
                alertsContainer.innerHTML = diagnostics.map(diag => {
                    const confText = formatConfidence(diag.classifier_confidence);
                    const isFault = diag.status === "ACTIVE_FAULT";
                    const statusBadgeText = isFault ? "Active Fault Detected" : "Predictive Risk — Pre-Occurrence Warning";
                    const badgeBg = isFault ? "#fee2e2" : "#fef3c7";
                    const badgeColor = isFault ? "#dc2626" : "#b45309";

                    const evidenceHtml = (diag.evidence_sources || []).map(src => `
                        <div style="margin-left: 12px; margin-bottom: 2px;">• ${src}</div>
                    `).join("");

                    return `
                        <div class="alert-item ${sysState}" style="margin-bottom: 12px;">
                            <div class="alert-header">
                                <div class="alert-title">
                                    <i class="fa-solid fa-triangle-exclamation"></i> ${diag.classifier_label}
                                    <span style="font-size:0.75rem; background:${badgeBg}; color:${badgeColor}; padding:2px 8px; border-radius:4px; font-weight:700; margin-left:6px;">
                                        ${statusBadgeText}
                                    </span>
                                </div>
                                <span class="conf-badge"><i class="fa-solid fa-shield-halved"></i> ${confText}</span>
                            </div>
                            <div class="alert-evidence" style="margin-top:6px; font-size:0.82rem;">
                                <strong><i class="fa-solid fa-microscope"></i> Targeted Diagnostic Evidence (${diag.affected_subsystem} Subsystem):</strong>
                                ${evidenceHtml}
                            </div>
                            <div class="fix-box temp-fix" style="margin-top:8px;">
                                <div class="fix-title"><i class="fa-solid fa-clipboard-check"></i> Autonomous Maintenance Advisory</div>
                                <div class="fix-content">${diag.advisory} (Priority: ${diag.priority})</div>
                            </div>
                            <div class="fix-box perm-fix" style="margin-top:4px;">
                                <div class="fix-title"><i class="fa-solid fa-magnifying-glass"></i> Inspection & Decision Support</div>
                                <div class="fix-content">Component: <strong>${diag.affected_component}</strong> | Observed Parameter: <strong>${diag.observed_parameter} = ${diag.observed_value}</strong> | Expected: <strong>${diag.threshold_or_expected_range}</strong> | Trend: <strong>${diag.trend}</strong>.</div>
                            </div>
                        </div>
                    `;
                }).join("");
            } else {
                alertsContainer.innerHTML = `<div class="no-alerts"><i class="fa-solid fa-circle-check text-green"></i> System Operating Nominal. No active faults detected.</div>`;
            }
        }
    } catch(err) {
        console.error("Alerts rendering error:", err);
    }

    // Update Live Telemetry & Predictive Projection Charts
    updateChartData(frame);
    updatePredictiveProjectionChart(frame);

    if (frame.runtime_metrics) {
        updateMetricsTab(frame.runtime_metrics);
    }
    if (frame.fault_event_log) {
        renderFaultEventLog(frame.fault_event_log);
    }
    updateEngineerAnalytics(frame);
    updateGcsDfcsDemonstrator(frame);
}

function initPredictiveProjectionChart() {
    try {
        if (typeof Chart === "undefined") return;
        const chartElem = document.getElementById("chart-predictive-projection");
        if (!chartElem || predictiveProjectionChart) return;

        const ctx = chartElem.getContext("2d");
        predictiveProjectionChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Observed Telemetry History',
                        data: [],
                        borderColor: '#0284c7',
                        backgroundColor: 'rgba(2, 132, 199, 0.08)',
                        borderWidth: 2,
                        fill: false,
                        tension: 0.2,
                        pointRadius: 0
                    },
                    {
                        label: 'GRU Model Forecast (+10s, +30s, +60s)',
                        data: [],
                        borderColor: '#9333ea',
                        borderWidth: 2.5,
                        borderDash: [6, 4],
                        pointRadius: 4,
                        pointBackgroundColor: '#9333ea',
                        fill: false,
                        tension: 0.2
                    },
                    {
                        label: 'Reference Envelope Limit',
                        data: [],
                        borderColor: '#dc2626',
                        borderWidth: 1.5,
                        borderDash: [4, 4],
                        pointRadius: 0,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: {
                        grid: { color: 'rgba(15, 23, 42, 0.05)' },
                        ticks: { color: '#64748b', font: { family: 'Inter', size: 10 } }
                    },
                    y: {
                        grid: { color: 'rgba(15, 23, 42, 0.06)' },
                        ticks: { color: '#475569', font: { family: 'Inter', size: 10 } }
                    }
                },
                plugins: {
                    legend: {
                        labels: { color: '#0f172a', font: { family: 'Outfit', size: 10, weight: '700' }, usePointStyle: true, boxWidth: 6 }
                    }
                }
            }
        });
        window.predictiveProjectionChart = predictiveProjectionChart;

        document.querySelectorAll(".btn-pred-param").forEach(btn => {
            btn.addEventListener("click", () => {
                document.querySelectorAll(".btn-pred-param").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                selectedProjectionParam = btn.getAttribute("data-param") || "cht1";
                window.userSelectedProjectionParam = true;
                // Immediate chart redraw on channel button click
                const snap = (window.twinStore && window.twinStore.currentSnapshot) ? window.twinStore.currentSnapshot : null;
                updatePredictiveProjectionChart(snap);
            });
        });
    } catch(err) {
        console.error("Failed to initialize predictive projection chart:", err);
    }
}

function updatePredictiveProjectionChart(frame) {
    if (!predictiveProjectionChart) {
        initPredictiveProjectionChart();
    }
    if (!predictiveProjectionChart) return;

    // Auto-select parameter if active fault or dominant component is present and user has not clicked manually
    if (!window.userSelectedProjectionParam && frame) {
        const ass = frame.latest_predictive_assessment || frame.predictive_assessment;
        const activeFaults = frame.active_faults || [];
        const primParam = ass?.primary_parameter ? String(ass.primary_parameter).toLowerCase() : null;
        const affComp = (ass?.affected_component || frame.dominant_component || activeFaults[0]?.component || activeFaults[0]?.affected_component || "").toUpperCase();
        const affSub = (ass?.affected_subsystem || frame.dominant_subsystem || activeFaults[0]?.subsystem || "").toUpperCase();

        let autoParam = null;
        if (primParam && ["cht1", "cht2", "cht3", "cht4", "oil_press", "oil_temp", "vibration_rms", "battery_volt"].includes(primParam)) {
            autoParam = primParam;
        } else if (affComp.includes("CYLINDER_4") || affComp.includes("CYLINDER 4") || affComp.includes("CHT4")) autoParam = "cht4";
        else if (affComp.includes("CYLINDER_3") || affComp.includes("CYLINDER 3") || affComp.includes("CHT3")) autoParam = "cht3";
        else if (affComp.includes("CYLINDER_2") || affComp.includes("CYLINDER 2") || affComp.includes("CHT2")) autoParam = "cht2";
        else if (affComp.includes("CYLINDER_1") || affComp.includes("CYLINDER 1") || affComp.includes("CHT1")) autoParam = "cht1";
        else if (affSub.includes("LUBRICATION") || affComp.includes("OIL")) autoParam = "oil_press";
        else if (affSub.includes("MECHANICAL") || affComp.includes("BEARING") || affComp.includes("VIBRATION")) autoParam = "vibration_rms";
        else if (affSub.includes("ELECTRICAL") || affComp.includes("BUS")) autoParam = "battery_volt";

        if (autoParam) {
            selectedProjectionParam = autoParam;
        }
    }
    window.selectedProjectionParam = selectedProjectionParam;

    // Synchronize button active highlighting with internal selectedProjectionParam state
    document.querySelectorAll(".btn-pred-param").forEach(b => {
        if (b.getAttribute("data-param") === selectedProjectionParam) {
            b.classList.add("active");
        } else {
            b.classList.remove("active");
        }
    });

    const fc = frame ? (frame.latest_forecast || frame.forecast || {}) : {};
    const fcStatus = fc.status || "INSUFFICIENT_HISTORY";

    const pointsToShow = Math.min(chartDataBuffer.length, 300);
    const sliced = chartDataBuffer.slice(-pointsToShow);

    const labels = sliced.map(d => d.timeLabel);

    const paramKeyMap = {
        "cht1": "cht1",
        "cht2": "cht2",
        "cht3": "cht3",
        "cht4": "cht4",
        "oil_press": "oil_press",
        "oil_temp": "oil_temp",
        "vibration_rms": "vibration_rms"
    };
    const key = paramKeyMap[selectedProjectionParam] || selectedProjectionParam || "cht1";

    const histData = sliced.map(d => {
        let val = d[selectedProjectionParam] ?? d[key];
        if (val === undefined && selectedProjectionParam === "oil_press") val = d.oilPress;
        if (val === undefined && frame && frame.telemetry) {
            val = frame.telemetry[selectedProjectionParam];
        }
        return val !== undefined ? parseFloat(val) : 0;
    });

    const currentVal = histData.length > 0 ? histData[histData.length - 1] : (frame && frame.telemetry ? (parseFloat(frame.telemetry[selectedProjectionParam]) || 0) : 0);

    const limitsMap = {
        "cht1": 145.0,
        "cht2": 145.0,
        "cht3": 145.0,
        "cht4": 145.0,
        "oil_press": 2.50,
        "oil_temp": 110.0,
        "vibration_rms": 2.50
    };
    const refLimit = limitsMap[selectedProjectionParam] || 145.0;

    let forecastLabels = [];
    let forecastData = [];

    const f10Dict = fc.forecast_10s || (fc.forecast && fc.forecast["10s"]);
    const f30Dict = fc.forecast_30s || (fc.forecast && fc.forecast["30s"]);
    const f60Dict = fc.forecast_60s || (fc.forecast && fc.forecast["60s"]);

    const getFcVal = (dict, pKey, altKey) => {
        if (!dict) return undefined;
        if (dict[pKey] !== undefined && dict[pKey] !== null) return parseFloat(dict[pKey]);
        if (altKey && dict[altKey] !== undefined && dict[altKey] !== null) return parseFloat(dict[altKey]);
        if (pKey === "oil_press" && dict["oil_pressure"] !== undefined) return parseFloat(dict["oil_pressure"]);
        if (pKey === "oil_temp" && dict["oil_temperature"] !== undefined) return parseFloat(dict["oil_temperature"]);
        return undefined;
    };

    let raw10 = getFcVal(f10Dict, selectedProjectionParam, key);
    let raw30 = getFcVal(f30Dict, selectedProjectionParam, key);
    let raw60 = getFcVal(f60Dict, selectedProjectionParam, key);

    // Fallback to PEW numerical card values if forecast dictionary keys do not match
    if (raw10 === undefined || isNaN(raw10)) {
        const parseCardNum = (id) => {
            const txt = document.getElementById(id)?.innerText || "";
            const match = txt.match(/([0-9]+\.?[0-9]*)/);
            return match ? parseFloat(match[1]) : undefined;
        };
        const card10 = parseCardNum("pew-10s");
        const card30 = parseCardNum("pew-30s");
        const card60 = parseCardNum("pew-60s");
        if (card10 !== undefined && !isNaN(card10)) {
            raw10 = card10;
            raw30 = card30 !== undefined ? card30 : card10;
            raw60 = card60 !== undefined ? card60 : card30;
        }
    }

    if (raw10 !== undefined && !isNaN(raw10)) {
        const f10 = raw10;
        const f30 = (raw30 !== undefined && !isNaN(raw30)) ? raw30 : f10;
        const f60 = (raw60 !== undefined && !isNaN(raw60)) ? raw60 : f30;

        const label10 = `+10s`;
        const label30 = `+30s`;
        const label60 = `+60s`;

        forecastLabels = [...labels, label10, label30, label60];

        const fcPoints = new Array(labels.length - 1).fill(null);
        fcPoints.push(currentVal, f10, f30, f60);
        forecastData = fcPoints;
    } else {
        forecastLabels = labels;
        forecastData = new Array(labels.length).fill(null);
    }

    const refLimitData = new Array(forecastLabels.length).fill(refLimit);
    const histDataExtended = [...histData, null, null, null];

    // Explicit Y-axis min/max scale recalculation for clear visualization of high/low forecast trajectories
    const allVals = [];
    histData.forEach(v => { if (typeof v === 'number' && !isNaN(v)) allVals.push(v); });
    forecastData.forEach(v => { if (typeof v === 'number' && !isNaN(v)) allVals.push(v); });
    if (typeof refLimit === 'number' && !isNaN(refLimit)) allVals.push(refLimit);

    if (allVals.length > 0) {
        const minV = Math.min(...allVals);
        const maxV = Math.max(...allVals);
        let range = maxV - minV;
        if (range < 2.0) range = 10.0;
        
        let padMin = Math.max(0, Math.floor(minV - range * 0.1));
        let padMax = Math.ceil(maxV + range * 0.15);

        if (predictiveProjectionChart.options.scales && predictiveProjectionChart.options.scales.y) {
            predictiveProjectionChart.options.scales.y.min = padMin;
            predictiveProjectionChart.options.scales.y.max = padMax;
            predictiveProjectionChart.options.scales.y.suggestedMin = padMin;
            predictiveProjectionChart.options.scales.y.suggestedMax = padMax;
        }
    }

    predictiveProjectionChart.data.labels = forecastLabels;
    predictiveProjectionChart.data.datasets[0].data = histDataExtended;
    predictiveProjectionChart.data.datasets[1].data = forecastData;
    predictiveProjectionChart.data.datasets[2].data = refLimitData;

    predictiveProjectionChart.update('none');
}

function updateMetricsTab(metrics) {
    if (!metrics) return;

    const telem = metrics.telemetry || {};
    const latencies = metrics.latencies || {};
    const integrity = metrics.data_integrity || {};
    const predPerf = metrics.predictive_performance || {};
    const ws = metrics.websocket || {};

    const rateObj = telem.effective_hz ? { mean: telem.effective_hz, median: telem.effective_hz, p95: telem.effective_hz, max: telem.effective_hz, status: telem.status } : metrics.update_rate_hz;
    const dtObj = latencies.digital_twin || metrics.dt_processing_latency_ms;
    const aeObj = latencies.autoencoder || metrics.ml_inference_latency_ms;
    const physObj = latencies.physics;
    const gruObj = latencies.gru_forecast;
    const rulObj = latencies.rul_inference;
    const predObj = latencies.predictive_health;

    const updateStatsRow = (prefix, dataObj) => {
        const meanEl = document.getElementById(`${prefix}-mean`);
        const medEl = document.getElementById(`${prefix}-med`);
        const p95El = document.getElementById(`${prefix}-p95`);
        const maxEl = document.getElementById(`${prefix}-max`);
        const stEl = document.getElementById(`st-${prefix.replace('m-', '')}`);

        if (dataObj && dataObj.status === "MEASURED" && dataObj.mean !== null && dataObj.mean !== undefined) {
            if (meanEl) meanEl.innerText = Number(dataObj.mean).toFixed(2);
            if (medEl) medEl.innerText = Number(dataObj.median).toFixed(2);
            if (p95El) p95El.innerText = Number(dataObj.p95).toFixed(2);
            if (maxEl) maxEl.innerText = Number(dataObj.max).toFixed(2);
            if (stEl) {
                stEl.innerText = "MEASURED";
                stEl.className = "gauge-state-badge NORMAL";
            }
        } else {
            if (meanEl) meanEl.innerText = "AWAITING DATA";
            if (medEl) medEl.innerText = "N/A";
            if (p95El) p95El.innerText = "N/A";
            if (maxEl) maxEl.innerText = "N/A";
            if (stEl) {
                stEl.innerText = "AWAITING DATA";
                stEl.className = "badge-tag not-evaluated";
            }
        }
    };

    updateStatsRow("m-rate", rateObj);
    updateStatsRow("m-dt", dtObj);
    updateStatsRow("m-ml", aeObj);
    if (physObj) updateStatsRow("m-phys", physObj);
    if (gruObj) updateStatsRow("m-gru", gruObj);
    if (rulObj) updateStatsRow("m-rul", rulObj);
    if (predObj) updateStatsRow("m-pred", predObj);

    if (document.getElementById("m-ws-rate")) {
        const wsRate = ws.publish_rate_hz ?? metrics.websocket_msg_rate_hz;
        const elem = document.getElementById("m-ws-rate");
        const stWs = document.getElementById("st-ws");
        if (wsRate !== undefined && wsRate !== "AWAITING DATA" && wsRate !== "NOT MEASURED" && wsRate !== null) {
            elem.innerText = `${wsRate} msgs/s`;
            if (stWs) { stWs.innerText = "MEASURED"; stWs.className = "gauge-state-badge NORMAL"; }
        } else {
            elem.innerText = "AWAITING DATA";
            if (stWs) { stWs.innerText = "AWAITING DATA"; stWs.className = "badge-tag not-evaluated"; }
        }
    }

    if (document.getElementById("m-integrity-pct")) {
        const pct = integrity.data_integrity_pct ?? metrics.data_integrity_rate_pct;
        const elem = document.getElementById("m-integrity-pct");
        const stInt = document.getElementById("st-integrity");
        if (pct !== undefined && pct !== null && pct !== "NOT MEASURED") {
            elem.innerText = `${Number(pct).toFixed(1)}%`;
            if (stInt) { stInt.innerText = "MEASURED"; stInt.className = "gauge-state-badge NORMAL"; }
        } else {
            elem.innerText = "AWAITING TELEMETRY";
            if (stInt) { stInt.innerText = "AWAITING DATA"; stInt.className = "badge-tag not-evaluated"; }
        }
    }

    if (document.getElementById("m-dropped-count")) {
        const dropped = integrity.dropped_invalid_frames ?? metrics.dropped_invalid_frames ?? 0;
        document.getElementById("m-dropped-count").innerText = `${dropped} frames`;
    }

    if (document.getElementById("m-total-frames")) {
        const total = integrity.total_ingested_frames ?? metrics.total_ingested_frames ?? 0;
        document.getElementById("m-total-frames").innerText = `${total} frames`;
    }

    if (document.getElementById("m-lead-time")) {
        const ltText = predPerf.lead_time_text || "NOT AVAILABLE (No complete degradation test)";
        document.getElementById("m-lead-time").innerText = ltText;
    }
}

function updateMetricsTable(metrics) {
    return updateMetricsTab(metrics);
}


let receivedFrameCount = 0;
let chartWindowSeconds = 30;
let chartDataBuffer = [];
window.chartDataBuffer = chartDataBuffer;

function initTelemetryChart() {
    try {
        if (typeof Chart === "undefined") {
            console.warn("Chart.js library not loaded. Telemetry line chart will be disabled.");
            return;
        }
        const chartElem = document.getElementById("chart-telemetry");
        if (!chartElem) return;
        const ctx = chartElem.getContext("2d");

        if (telemetryChart) {
            return; // Maintain single chart instance without recreate/destroy flickering
        }

        telemetryChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Engine Speed (RPM / 50)',
                        data: [],
                        borderColor: '#0284c7',
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        rawUnit: 'RPM',
                        rawScale: 1 / 50.0
                    },
                    {
                        label: 'CHT Cyl 1 (°C)',
                        data: [],
                        borderColor: '#059669',
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        rawUnit: '°C',
                        rawScale: 1.0
                    },
                    {
                        label: 'EGT Cyl 1 (/ 5)',
                        data: [],
                        borderColor: '#ea580c',
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        rawUnit: '°C',
                        rawScale: 1 / 5.0
                    },
                    {
                        label: 'Oil Pressure (bar × 20)',
                        data: [],
                        borderColor: '#d97706',
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        rawUnit: 'bar',
                        rawScale: 20.0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: {
                        grid: { color: 'rgba(15, 23, 42, 0.05)' },
                        ticks: {
                            color: '#64748b',
                            font: { family: 'Inter', size: 10 },
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 8
                        }
                    },
                    y: {
                        min: 0,
                        max: 200,
                        grid: { color: 'rgba(15, 23, 42, 0.06)' },
                        ticks: {
                            color: '#475569',
                            font: { family: 'Inter', size: 11, weight: '600' }
                        }
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#0f172a',
                            font: { family: 'Outfit', size: 11, weight: '700' },
                            usePointStyle: true,
                            boxWidth: 8
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleFont: { family: 'Outfit', size: 12, weight: '700' },
                        bodyFont: { family: 'Inter', size: 11 },
                        padding: 10,
                        callbacks: {
                            label: function(context) {
                                const dataset = context.dataset;
                                const normVal = context.parsed.y;
                                const rawVal = (context.raw && context.raw.rawVal !== undefined) ? context.raw.rawVal : (normVal / (dataset.rawScale || 1.0));
                                const unit = dataset.rawUnit || '';
                                return ` ${dataset.label}: Raw ${Number(rawVal).toFixed(1)} ${unit} (Chart Norm: ${normVal.toFixed(1)})`;
                            },
                            title: function(tooltipItems) {
                                if (!tooltipItems.length) return '';
                                const item = tooltipItems[0];
                                const rawTime = (item.raw && item.raw.timestamp !== undefined) ? item.raw.timestamp : item.label;
                                return `Timestamp: t=${typeof rawTime === 'number' ? rawTime.toFixed(1) + 's' : rawTime}`;
                            }
                        }
                    }
                }
            }
        });

        // Register window control button handlers
        document.querySelectorAll(".btn-chart-win").forEach(btn => {
            btn.addEventListener("click", () => {
                document.querySelectorAll(".btn-chart-win").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
                chartWindowSeconds = parseInt(btn.getAttribute("data-window")) || 30;
                renderBufferedChart();
            });
        });

    } catch(err) {
        console.error("Failed to initialize telemetry chart:", err);
    }
}

function updateChartData(frame) {
    if (!telemetryChart) {
        initTelemetryChart();
    }
    if (!frame) return;

    const telem = frame.telemetry || frame;
    const seq = frame.sequence_number;
    
    // Deduplication check based on unique accepted sequence number
    if (chartDataBuffer.length > 0 && seq !== undefined && seq !== null) {
        const lastSeq = chartDataBuffer[chartDataBuffer.length - 1].sequence_number;
        if (lastSeq === seq) return;
    }

    const maxCapacity = 1200; // Store up to 120s buffer at 10Hz (1200 samples)
    const timestamp = telem.timestamp ?? frame.timestamp;
    const tVal = (typeof timestamp === 'number') ? timestamp : (chartDataBuffer.length * 0.1);
    const tLabel = `t=${tVal.toFixed(1)}s`;

    const oilP = telem.oil_press ?? telem.oilPress ?? 4.2;

    chartDataBuffer.push({
        sequence_number: seq,
        timeLabel: tLabel,
        timestamp: tVal,
        rpm: parseFloat(telem.rpm) || 5000,
        oilPress: parseFloat(oilP) || 4.2,
        oil_press: parseFloat(oilP) || 4.2,
        oil_temp: parseFloat(telem.oil_temp ?? telem.oil_temperature ?? 88.5),
        vibration_rms: parseFloat(telem.vibration_rms ?? 1.12),
        map: parseFloat(telem.map ?? 1.15),
        cht1: parseFloat(telem.cht1 ?? 120),
        cht2: parseFloat(telem.cht2 ?? 120),
        cht3: parseFloat(telem.cht3 ?? 120),
        cht4: parseFloat(telem.cht4 ?? 120),
        egt1: parseFloat(telem.egt1 ?? 750),
        egt2: parseFloat(telem.egt2 ?? 750),
        egt3: parseFloat(telem.egt3 ?? 750),
        egt4: parseFloat(telem.egt4 ?? 750)
    });

    if (chartDataBuffer.length > maxCapacity) {
        chartDataBuffer.shift();
    }

    // Debug assertion requirement & temporary consistency check
    if (receivedFrameCount > 10 && chartDataBuffer.length === 0) {
        console.error("[REAL-TIME CHART ERROR] Received > 10 telemetry frames, but Real-Time Telemetry Channels chart buffer has ZERO points!");
    }

    if (window.DEBUG_TWIN_SYNC || (typeof seq === 'number' && (seq % 50 === 0 || seq < 5))) {
        const oldestBuf = chartDataBuffer.length > 0 ? chartDataBuffer[0] : null;
        const newestBuf = chartDataBuffer.length > 0 ? chartDataBuffer[chartDataBuffer.length - 1] : null;
        const liveCht1 = telem ? telem.cht1 : frame.cht1;

        console.log(`[LIVE_FRAME] seq=${seq} time=${tVal.toFixed(1)} state=${frame.system_state} cht1=${liveCht1}`);
        if (newestBuf) {
            console.log(`[HISTORY_NEWEST] seq=${newestBuf.sequence_number} time=${newestBuf.timestamp} state=${frame.system_state} cht1=${newestBuf.cht1}`);
        }
        if (oldestBuf) {
            console.log(`[HISTORY_OLDEST] seq=${oldestBuf.sequence_number} time=${oldestBuf.timestamp} state=${frame.system_state} cht1=${oldestBuf.cht1}`);
        }

        if (newestBuf && seq !== undefined && newestBuf.sequence_number !== undefined) {
            if (seq !== newestBuf.sequence_number) {
                console.warn("[LIVE/HISTORY DESYNC]", `seq=${seq}`, `history_seq=${newestBuf.sequence_number}`);
            }
        }
    }

    renderBufferedChart();
}

function renderBufferedChart() {
    if (!telemetryChart) return;

    const pointsToShow = Math.min(chartDataBuffer.length, chartWindowSeconds * 10);
    const slicedBuffer = chartDataBuffer.slice(-pointsToShow);

    // Dynamic cylinder channel resolution based on current twin snapshot
    let selectedCyl = "cht1";
    let selectedEgt = "egt1";
    let cylLabel = "CHT Cyl1 (°C)";
    let egtLabel = "EGT Cyl1 (/ 5)";

    const lastFrame = (window.twinStore && window.twinStore.currentSnapshot) ? window.twinStore.currentSnapshot : null;
    const ass = lastFrame?.latest_predictive_assessment || lastFrame?.predictive_assessment;
    const activeFlts = lastFrame?.active_faults || [];
    const affComp = (ass?.affected_component || lastFrame?.dominant_component || activeFlts[0]?.component || activeFlts[0]?.affected_component || "").toUpperCase();

    if (affComp.includes("CYLINDER_3") || affComp.includes("CYLINDER 3") || affComp.includes("CHT3")) {
        selectedCyl = "cht3";
        selectedEgt = "egt3";
        cylLabel = "CHT Cyl3 (°C)";
        egtLabel = "EGT Cyl3 (/ 5)";
    } else if (affComp.includes("CYLINDER_2") || affComp.includes("CYLINDER 2") || affComp.includes("CHT2")) {
        selectedCyl = "cht2";
        selectedEgt = "egt2";
        cylLabel = "CHT Cyl2 (°C)";
        egtLabel = "EGT Cyl2 (/ 5)";
    } else if (affComp.includes("CYLINDER_4") || affComp.includes("CYLINDER 4") || affComp.includes("CHT4")) {
        selectedCyl = "cht4";
        selectedEgt = "egt4";
        cylLabel = "CHT Cyl4 (°C)";
        egtLabel = "EGT Cyl4 (/ 5)";
    }

    const labels = slicedBuffer.map(d => d.timeLabel);
    const rpmNorm = slicedBuffer.map(d => ({ x: d.timeLabel, y: d.rpm / 50.0, rawVal: d.rpm, timestamp: d.timestamp }));
    const chtNorm = slicedBuffer.map(d => ({ x: d.timeLabel, y: d[selectedCyl] ?? d.cht1, rawVal: d[selectedCyl] ?? d.cht1, timestamp: d.timestamp }));
    const egtNorm = slicedBuffer.map(d => ({ x: d.timeLabel, y: (d[selectedEgt] ?? d.egt1) / 5.0, rawVal: d[selectedEgt] ?? d.egt1, timestamp: d.timestamp }));
    const oilNorm = slicedBuffer.map(d => ({ x: d.timeLabel, y: d.oilPress * 20.0, rawVal: d.oilPress, timestamp: d.timestamp }));

    telemetryChart.data.labels = labels;
    telemetryChart.data.datasets[0].data = rpmNorm;
    telemetryChart.data.datasets[1].data = chtNorm;
    telemetryChart.data.datasets[1].label = cylLabel;
    telemetryChart.data.datasets[2].data = egtNorm;
    telemetryChart.data.datasets[2].label = egtLabel;
    telemetryChart.data.datasets[3].data = oilNorm;

    telemetryChart.update('none');
}

async function authFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (authToken && !options.headers["Authorization"]) {
        options.headers["Authorization"] = `Bearer ${authToken}`;
    }
    if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(options.body);
    }
    try {
        const res = await fetch(url, options);
        if (res.status === 401) {
            console.warn(`[AUTH 401] Token expired or invalid for ${url}. Re-authenticating default session...`);
            const reloginRes = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: "engineer", password: "engineer123" })
            });
            if (reloginRes.ok) {
                const data = await reloginRes.json();
                authToken = data.access_token;
                userRole = data.role;
                userName = data.full_name;
                localStorage.setItem("dt_token", authToken);
                localStorage.setItem("dt_role", userRole);
                localStorage.setItem("dt_name", userName);
                options.headers["Authorization"] = `Bearer ${authToken}`;
                return await fetch(url, options);
            }
        }
        if (!res.ok) {
            const errText = await res.text().catch(() => "");
            console.error(`[API ERROR] ${options.method || 'GET'} ${url} returned HTTP ${res.status}:`, errText);
        }
        return res;
    } catch(err) {
        console.error(`[NETWORK ERROR] Request failed for ${url}:`, err);
        throw err;
    }
}

// MISSION & DATASET STREAM SELECTORS
function initMissionSelector() {
    const profileElem = document.getElementById("select-mission-profile");
    if (profileElem) {
        profileElem.addEventListener("change", async (e) => {
            const profile = e.target.value;
            const res = await authFetch(`${API_BASE}/api/mission/set-profile`, {
                method: "POST",
                body: { profile }
            });
            if (!res.ok) {
                console.error("Failed to update scenario profile on backend:", res.status);
            }
        });
    }

    const telemSourceElem = document.getElementById("select-telemetry-source");
    const analyticsDatasetElem = document.getElementById("select-analytics-dataset");

    async function sendDataSourcesUpdate() {
        const telemetry_source = telemSourceElem ? telemSourceElem.value : "SIMULATOR";
        const analytics_dataset = analyticsDatasetElem ? analyticsDatasetElem.value : "CMAPSS";

        await authFetch(`${API_BASE}/api/telemetry/data-sources`, {
            method: "POST",
            body: { telemetry_source, analytics_dataset }
        });
    }

    if (telemSourceElem) {
        telemSourceElem.addEventListener("change", sendDataSourcesUpdate);
    }
    if (analyticsDatasetElem) {
        analyticsDatasetElem.addEventListener("change", sendDataSourcesUpdate);
    }

    const datasetElem = document.getElementById("select-dataset-mode");
    if (datasetElem) {
        datasetElem.addEventListener("change", async (e) => {
            const mode = e.target.value;
            await authFetch(`${API_BASE}/api/telemetry/dataset-mode`, {
                method: "POST",
                body: { mode }
            });
        });
    }
}

async function updateFaultComponentDropdown(scenario) {
    const compSelect = document.getElementById("select-fault-component");
    if (!compSelect || !scenario) return;
    try {
        const res = await fetch(`${API_BASE}/api/faults/${encodeURIComponent(scenario)}/components`);
        if (res.ok) {
            const data = await res.json();
            const comps = data.components || [];
            if (comps.length > 0) {
                compSelect.innerHTML = comps.map(c => `<option value="${c.id}">${c.label}</option>`).join("");
                return;
            }
        }
    } catch(e) {
        console.error("Failed to update fault component dropdown:", e);
    }
}

// FAULT INJECTION CONTROLS & LIVE LOG RENDERER
function initFaultButtons() {
    const scenarioSelect = document.getElementById("select-fault-scenario");
    if (scenarioSelect) {
        scenarioSelect.addEventListener("change", (e) => {
            updateFaultComponentDropdown(e.target.value);
        });
        updateFaultComponentDropdown(scenarioSelect.value);
    }

    const slider = document.getElementById("slider-fault-intensity");
    const disp = document.getElementById("val-fault-intensity-disp");
    if (slider && disp) {
        slider.addEventListener("input", (e) => {
            disp.innerText = `${Math.round(parseFloat(e.target.value) * 100)}%`;
        });
    }

    const btnStart = document.getElementById("btn-start-fault");
    if (btnStart) {
        btnStart.addEventListener("click", async () => {
            const scenario = document.getElementById("select-fault-scenario") ? document.getElementById("select-fault-scenario").value : "CYLINDER_THERMAL";
            const component = document.getElementById("select-fault-component") ? document.getElementById("select-fault-component").value : "CYLINDER_1";
            const profile = document.getElementById("select-fault-profile") ? document.getElementById("select-fault-profile").value : "GRADUAL";
            const rate = document.getElementById("select-fault-rate") ? document.getElementById("select-fault-rate").value : "MODERATE";
            const intensity = slider ? parseFloat(slider.value) : 1.0;

            const res = await authFetch(`${API_BASE}/api/fault-injection/start`, {
                method: "POST",
                body: { scenario, component, profile, intensity, rate }
            });
            if (!res.ok) {
                console.error("Failed to start fault injection on backend:", res.status);
            }
        });
    }

    const btnPause = document.getElementById("btn-pause-fault");
    if (btnPause) {
        btnPause.addEventListener("click", async () => {
            await authFetch(`${API_BASE}/api/fault-injection/pause`, {
                method: "POST"
            });
        });
    }

    const btnClear = document.getElementById("btn-clear-fault");
    if (btnClear) {
        btnClear.addEventListener("click", async () => {
            await authFetch(`${API_BASE}/api/fault-injection/clear`, {
                method: "POST"
            });
        });
    }
}


function renderFaultEventLog(logList) {
    const tbody = document.getElementById("fault-event-log-body");
    if (!tbody) return;

    if (!logList || logList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No active simulated fault injections logged. System operating in nominal baseline.</td></tr>`;
        return;
    }

    tbody.innerHTML = logList.slice().reverse().map(item => {
        const isRunning = item.status === "RUNNING";
        const isPaused = item.status === "PAUSED";
        const statusBadge = isRunning
            ? `<span class="gauge-state-badge WARNING"><i class="fa-solid fa-play"></i> RUNNING</span>`
            : (isPaused ? `<span class="gauge-state-badge WATCH"><i class="fa-solid fa-pause"></i> PAUSED</span>` : `<span class="gauge-state-badge NORMAL"><i class="fa-solid fa-check"></i> CLEARED (${item.cleared_time})</span>`);

        return `
            <tr>
                <td><strong>${item.fault_scenario}</strong></td>
                <td>${item.start_time}</td>
                <td><code style="color:var(--primary-blue); font-weight:700;">${item.affected_input}</code></td>
                <td><span class="badge-tag direct">${item.injection_profile}</span></td>
                <td>${item.intensity} (${item.progression_rate})</td>
                <td>${statusBadge}</td>
            </tr>
        `;
    }).join("");
}

// MISSION REPLAY & DIGITAL TWIN HISTORICAL RECONSTRUCTION
let replayDataset = null;
let currentReplayIndex = 0;
let isReplayPlaying = false;
let replayTimer = null;
let replaySpeed = 5;
let currentMissionId = "latest";

async function loadReplayMissions() {
    const sel = document.getElementById("select-replay-mission");
    if (!sel) return;

    try {
        const res = await fetch(`${API_BASE}/api/replay/missions`);
        if (!res.ok) return;
        const missions = await res.json();

        if (!Array.isArray(missions) || missions.length === 0) {
            sel.innerHTML = `<option value="">No recorded missions found</option>`;
            return;
        }

        sel.innerHTML = missions.map(m => {
            const startStr = m.start_time ? (m.start_time.split("T")[1]?.substring(0, 8) || m.start_time) : "";
            const dur = (m.duration || 0).toFixed(1);
            const scenario = m.initial_scenario || "CRUISE";
            const fc = m.frame_count || 0;
            return `<option value="${m.mission_id}">${m.mission_id} — ${scenario} (${dur}s, ${fc} frames)</option>`;
        }).join("");

        currentMissionId = missions[0].mission_id;
        sel.value = currentMissionId;
        await loadMissionReplay(currentMissionId);

    } catch (e) {
        console.error("Failed to load recorded missions list:", e);
    }
}

async function startNewMission() {
    try {
        const res = await authFetch(`${API_BASE}/api/replay/start-new-mission`, { method: "POST" });
        if (res.ok) {
            const data = await res.json();
            console.log("New mission started:", data);
            await loadReplayMissions();
        }
    } catch (e) {
        console.error("Failed to start new mission:", e);
    }
}

async function loadMissionReplay(missionId) {
    if (!missionId) return;
    try {
        const res = await fetch(`${API_BASE}/api/replay/mission/${missionId}`);
        if (!res.ok) return;
        replayDataset = await res.json();
        const frames = replayDataset.frames || [];
        const summary = replayDataset.summary || {};
        const markers = replayDataset.timeline_markers || replayDataset.events || [];

        const slider = document.getElementById("replay-scrubber");
        if (slider) {
            slider.min = 0;
            slider.max = Math.max(0, frames.length - 1);
            slider.value = 0;
        }

        renderReplayTimelineMarkers(markers, frames.length);
        populateReplayReportSummary(summary);
        currentReplayIndex = 0;
        renderReplayFrame(0);
    } catch (e) {
        console.error("Failed to load mission replay:", e);
    }
}

async function initReplayScrubber() {
    const sel = document.getElementById("select-replay-mission");
    if (sel) {
        sel.addEventListener("change", async (e) => {
            currentMissionId = e.target.value;
            await loadMissionReplay(currentMissionId);
        });
    }

    const btnNew = document.getElementById("btn-start-new-mission");
    if (btnNew) {
        btnNew.addEventListener("click", startNewMission);
    }

    const slider = document.getElementById("replay-scrubber");
    if (slider) {
        slider.addEventListener("input", (e) => {
            pauseReplay();
            const idx = parseInt(e.target.value, 10);
            renderReplayFrame(idx);
        });
    }

    const speedSelect = document.getElementById("select-replay-speed");
    if (speedSelect) {
        speedSelect.addEventListener("change", (e) => {
            replaySpeed = parseFloat(e.target.value);
            if (isReplayPlaying) {
                pauseReplay();
                playReplay();
            }
        });
    }

    const playBtn = document.getElementById("btn-replay-play");
    const pauseBtn = document.getElementById("btn-replay-pause");
    const restartBtn = document.getElementById("btn-replay-restart");

    if (playBtn) playBtn.addEventListener("click", playReplay);
    if (pauseBtn) pauseBtn.addEventListener("click", pauseReplay);
    if (restartBtn) restartBtn.addEventListener("click", restartReplay);

    await loadReplayMissions();
}

function playReplay() {
    if (!replayDataset || !replayDataset.frames || replayDataset.frames.length === 0) return;
    if (isReplayPlaying) return;

    isReplayPlaying = true;
    if (authToken) {
        fetch(`${API_BASE}/api/audit-logs/log`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${authToken}`
            },
            body: JSON.stringify({
                action: "mission replay started",
                details: `Mission ${currentMissionId} replay playback started (${replayDataset.frames.length} frames)`
            })
        }).catch(err => console.error("Audit log error:", err));
    }

    const intervalMs = Math.max(20, Math.round(100 / replaySpeed));

    replayTimer = setInterval(() => {
        if (currentReplayIndex >= replayDataset.frames.length - 1) {
            pauseReplay();
            return;
        }
        currentReplayIndex += 1;
        renderReplayFrame(currentReplayIndex);
    }, intervalMs);
}

function pauseReplay() {
    isReplayPlaying = false;
    if (replayTimer) {
        clearInterval(replayTimer);
        replayTimer = null;
    }
}

function restartReplay() {
    pauseReplay();
    currentReplayIndex = 0;
    renderReplayFrame(0);
}

function renderReplayTimelineMarkers(markers, totalFrames) {
    const container = document.getElementById("replay-timeline-markers");
    if (!container || totalFrames <= 0) return;

    if (!markers || markers.length === 0) {
        container.innerHTML = "";
        return;
    }

    container.innerHTML = markers.map(m => {
        const frameIdx = m.frame_index !== undefined ? m.frame_index : (m.sequence_number || 0);
        const pct = ((frameIdx / Math.max(1, totalFrames - 1)) * 100).toFixed(2);
        const color = m.color || (m.event_type?.includes("CRITICAL") ? "#dc2626" : (m.event_type?.includes("WARNING") ? "#ea580c" : (m.event_type?.includes("CAUTION") ? "#d97706" : "#0284c7")));
        const label = m.label || m.event_type || "Event";
        return `<div class="replay-marker" style="left:${pct}%; background:${color};" title="${label} (Frame ${frameIdx + 1})" onclick="scrubToReplayFrame(${frameIdx})"></div>`;
    }).join("");
}

window.scrubToReplayFrame = function(frameIdx) {
    pauseReplay();
    renderReplayFrame(frameIdx);
};

function renderReplayFrame(idx) {
    if (!replayDataset || !replayDataset.frames || idx < 0 || idx >= replayDataset.frames.length) return;
    currentReplayIndex = idx;

    const frame = replayDataset.frames[idx];
    const telem = frame.telemetry || {};
    const fc = frame.latest_forecast || frame.forecast || {};
    const activeFaults = frame.active_faults || [];

    const slider = document.getElementById("replay-scrubber");
    if (slider) slider.value = idx;

    const timeDisplay = document.getElementById("replay-time-display");
    if (timeDisplay) {
        const ts = typeof frame.timestamp === 'number' ? frame.timestamp.toFixed(1) : (idx * 0.1).toFixed(1);
        timeDisplay.innerText = `Frame ${idx + 1} / ${replayDataset.frames.length} (${ts}s)`;
    }

    const stageElem = document.getElementById("replay-mission-stage");
    if (stageElem) {
        const scenario = typeof frame.scenario === 'object' ? frame.scenario.id : (frame.scenario || 'CRUISE');
        stageElem.innerHTML = `<i class="fa-solid fa-plane-departure"></i> RECORDED SCENARIO: ${scenario}`;
    }

    const stateBadge = document.getElementById("replay-state-badge");
    const sysState = frame.system_state || "NORMAL";
    if (stateBadge) {
        stateBadge.innerText = sysState;
        stateBadge.className = `badge-state ${sysState}`;
    }

    // Telemetry readouts
    const rpmVal = Math.round(floatOr(telem.rpm, 5000));
    const chtVal = floatOr(telem.cht1, 120.0).toFixed(1);
    const oilPVal = floatOr(telem.oil_press, 4.2).toFixed(2);
    
    const rulObj = frame.prototype_rul_estimate || frame.rul || {};
    let rulText = "Warming up / insufficient sequence";
    if (rulObj.display_prediction_cycles !== null && rulObj.display_prediction_cycles !== undefined && (rulObj.model_status === "INFERENCE ACTIVE" || rulObj.model_status === "READY")) {
        rulText = `${Number(rulObj.display_prediction_cycles).toFixed(1)} cycles`;
    }

    if (document.getElementById("replay-val-rpm")) document.getElementById("replay-val-rpm").innerText = `${rpmVal} RPM`;
    if (document.getElementById("replay-val-cht")) document.getElementById("replay-val-cht").innerText = `${chtVal} °C`;
    if (document.getElementById("replay-val-oil-p")) document.getElementById("replay-val-oil-p").innerText = `${oilPVal} bar`;
    if (document.getElementById("replay-val-rul")) document.getElementById("replay-val-rul").innerText = rulText;

    if (document.getElementById("replay-frame-num")) document.getElementById("replay-frame-num").innerText = idx + 1;
    if (document.getElementById("replay-fc-frame")) document.getElementById("replay-fc-frame").innerText = idx + 1;

    // Historical Forecast Readout
    const fcStatus = fc.status || "WARMING_UP";
    if (document.getElementById("replay-fc-status")) {
        document.getElementById("replay-fc-status").innerText = fcStatus === "READY" ? "Historical GRU Model Inference" : "Warming up / Statistical Fallback";
    }

    if (fc.forecast_10s && fc.forecast_30s && fc.forecast_60s) {
        if (document.getElementById("replay-fc-10s")) document.getElementById("replay-fc-10s").innerText = `${floatOr(fc.forecast_10s.cht1, floatOr(telem.cht1, 120.0)).toFixed(1)} °C`;
        if (document.getElementById("replay-fc-30s")) document.getElementById("replay-fc-30s").innerText = `${floatOr(fc.forecast_30s.cht1, floatOr(telem.cht1, 120.0)).toFixed(1)} °C`;
        if (document.getElementById("replay-fc-60s")) document.getElementById("replay-fc-60s").innerText = `${floatOr(fc.forecast_60s.cht1, floatOr(telem.cht1, 120.0)).toFixed(1)} °C`;
    } else {
        if (document.getElementById("replay-fc-10s")) document.getElementById("replay-fc-10s").innerText = "Warming up";
        if (document.getElementById("replay-fc-30s")) document.getElementById("replay-fc-30s").innerText = "Warming up";
        if (document.getElementById("replay-fc-60s")) document.getElementById("replay-fc-60s").innerText = "Warming up";
    }

    // Historical Active Faults Readout (array supporting multiple active faults)
    const faultsBody = document.getElementById("replay-active-faults-body");
    if (faultsBody) {
        if (activeFaults.length > 0) {
            faultsBody.innerHTML = activeFaults.map(f => {
                const sc = f.fault_scenario || f.scenario || "FAULT";
                const comp = f.affected_component || f.component || "CYLINDER_1";
                const prof = f.injection_profile || f.profile || "GRADUAL";
                const eff = Math.round(f.current_effect_pct || (f.intensity * 100) || 0);
                return `<div style="margin-bottom:2px;">• <strong>${sc}</strong> on <code>${comp}</code> (${prof}, Effect: ${eff}%)</div>`;
            }).join("");
        } else {
            faultsBody.innerText = "None active at this timestamp.";
        }
    }

    // Diagnostics & Advisories at this timestamp
    const diagBody = document.getElementById("replay-diagnostics-body");
    const diags = frame.predictive_diagnostics || frame.diagnostics || [];
    if (diagBody) {
        if (diags.length > 0) {
            diagBody.innerHTML = diags.map(d => `
                <div style="margin-bottom:6px; padding:6px; background:#ffffff; border-radius:6px; border:1px solid #e2e8f0;">
                    <div style="font-weight:700; color:#5b21b6;">• ${d.classifier_label} (${d.affected_subsystem || 'SYSTEM'} Subsystem - ${d.affected_component || 'Engine'})</div>
                    <div style="font-size:0.75rem; color:#475569;">Observed ${d.observed_parameter || 'Status'}: ${d.observed_value || 'Excursion'} (${d.threshold_or_expected_range || 'Envelope Limit'}) | Trend: ${d.trend || 'Degradation'}</div>
                    <div style="margin-top:2px; font-weight:600; color:#1e40af;">Advisory: ${d.advisory || 'Engineering inspection recommended.'}</div>
                </div>
            `).join("");
        } else {
            diagBody.innerHTML = `<i class="fa-solid fa-circle-check text-green"></i> System operating in nominal state machine (${sysState}). No active fault evidence detected at this timestamp.`;
        }
    }
}

function populateReplayReportSummary(summary) {
    if (!summary) return;

    if (document.getElementById("rep-mission-id")) document.getElementById("rep-mission-id").innerText = summary.mission_id || "MIS-20260920-001";
    if (document.getElementById("rep-data-source")) {
        const telemSrc = summary.telemetry_source || "Physics Simulator";
        const analyticsDs = summary.analytics_dataset || "C-MAPSS";
        document.getElementById("rep-data-source").innerText = `${telemSrc} / ${analyticsDs}`;
    }
    if (document.getElementById("rep-duration")) {
        const dur = (summary.duration || summary.replay_duration_seconds || 0).toFixed(1);
        const fc = summary.frame_count || summary.total_frames || 0;
        document.getElementById("rep-duration").innerText = `${dur}s (${fc} frames)`;
    }
    if (document.getElementById("rep-min-hi")) document.getElementById("rep-min-hi").innerText = `${(summary.min_health ?? 100.0).toFixed(1)}%`;
    if (document.getElementById("rep-max-anomaly")) document.getElementById("rep-max-anomaly").innerText = (summary.max_anomaly ?? 0.0).toFixed(3);
    if (document.getElementById("rep-rul-span")) {
        const rulStart = summary.rul_start !== null && summary.rul_start !== undefined ? `${Number(summary.rul_start).toFixed(1)} cycles` : "N/A";
        const rulEnd = summary.rul_end !== null && summary.rul_end !== undefined ? `${Number(summary.rul_end).toFixed(1)} cycles` : "N/A";
        document.getElementById("rep-rul-span").innerText = `Start: ${rulStart} → End: ${rulEnd}`;
    }
}

// AUDIT LOGS
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

async function loadAuditLogs() {
    const tbody = document.getElementById("audit-table-body");
    if (!tbody) return;

    try {
        const res = await fetch(`${API_BASE}/api/audit-logs`, {
            headers: { "Authorization": `Bearer ${authToken}` }
        });

        if (!res.ok) {
            let errDetail = `HTTP ${res.status} ${res.statusText}`;
            try {
                const errJson = await res.json();
                if (errJson && errJson.detail) {
                    errDetail += `: ${typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail)}`;
                }
            } catch (_) {}
            console.error("Audit log API error:", errDetail);
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--hud-red); padding:1rem;"><i class="fa-solid fa-triangle-exclamation"></i> <strong>Audit log unavailable</strong> (${escapeHtml(errDetail)})</td></tr>`;
            return;
        }

        const data = await res.json();
        const logs = Array.isArray(data) ? data : (data && Array.isArray(data.audit_logs) ? data.audit_logs : []);

        if (logs.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:1rem;"><i class="fa-solid fa-info-circle"></i> No audit events recorded.</td></tr>`;
            return;
        }

        tbody.innerHTML = logs.map(l => {
            const userDisplay = l.user || l.username || "unknown";
            const roleDisplay = l.role || "operator";
            const isEng = roleDisplay.toLowerCase() === "engineer";
            const roleClass = isEng ? "eng" : "op";
            const tsDisplay = l.timestamp ? String(l.timestamp).replace("T", " ").substring(0, 19) : "";

            return `
                <tr>
                    <td><code>${escapeHtml(tsDisplay)}</code></td>
                    <td><strong class="text-blue">${escapeHtml(userDisplay)}</strong></td>
                    <td><span class="role-badge ${roleClass}">${escapeHtml(roleDisplay.toUpperCase())}</span></td>
                    <td><strong style="color:var(--text-primary);">${escapeHtml(l.action)}</strong></td>
                    <td>${escapeHtml(l.details || "")}</td>
                </tr>
            `;
        }).join("");
    } catch(e) {
        console.error("Audit log fetch exception:", e);
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--hud-red); padding:1rem;"><i class="fa-solid fa-triangle-exclamation"></i> <strong>Audit log unavailable</strong> (${escapeHtml(e.message || String(e))})</td></tr>`;
    }
}

// PROTOTYPE MISSION HEALTH SUMMARY REPORT GENERATOR
function initReportButtons() {
    const jsonBtn = document.getElementById("btn-export-json");
    if (jsonBtn) {
        jsonBtn.addEventListener("click", async () => {
            if (!currentMissionId) return;
            try {
                const res = await fetch(`${API_BASE}/api/replay/export/${currentMissionId}`);
                if (!res.ok) return;
                const exportData = await res.json();
                const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `Mission_Report_${currentMissionId}.json`;
                a.click();
            } catch (e) {
                console.error("Failed to export JSON report:", e);
            }
        });
    }

    const printBtn = document.getElementById("btn-print-report");
    if (printBtn) {
        printBtn.addEventListener("click", () => {
            window.print();
        });
    }
}


// 2D DIGITAL TWIN SCHEMATIC & COMPONENT INSPECTOR LOGIC
let selectedTwinComponent = 'cyl1';
let lastTwinFrame = null;
let faultProgressionChart = null;

function initTwinComponentInteractions() {
    const compElements = document.querySelectorAll('#view-digital-twin .svg-subsystem');
    compElements.forEach(el => {
        el.addEventListener('click', () => {
            const compId = el.getAttribute('data-component');
            if (compId) {
                selectedTwinComponent = compId;
                compElements.forEach(c => c.classList.remove('selected'));
                el.classList.add('selected');
                if (lastTwinFrame) {
                    updateTwinComponentDetail(lastTwinFrame);
                }
            }
        });
    });
}

function formatTimeToRisk(ass) {
    if (!ass) return "N/A — Forecast unavailable";

    const riskStatus = ass.risk_status || ass.riskStatus;
    const ttrRaw = ass.estimated_time_to_risk_seconds ?? ass.estimated_time_to_risk ?? ass.ttr;
    const predStatus = ass.status || ass.predictive_status;

    // 1. Immediate Limit Exceeded check (0.0s)
    if (riskStatus === "LIMIT_EXCEEDED" || (ttrRaw !== null && ttrRaw !== undefined && Number(ttrRaw) === 0.0) || predStatus === "ACTIVE_FAULT") {
        return "0 s — LIMIT EXCEEDED";
    }

    // 2. Valid predicted breach within supported forecast horizon (<= 60s)
    if (riskStatus === "PREDICTED_BREACH" || (ttrRaw !== null && ttrRaw !== undefined && !isNaN(parseFloat(ttrRaw)) && parseFloat(ttrRaw) <= 60.0)) {
        const num = parseFloat(ttrRaw);
        if (num === 0.0) return "0 s — LIMIT EXCEEDED";
        return `~${Math.round(num)} s`;
    }

    // 3. Forecast available and no breach predicted within 60s horizon
    if (riskStatus === "NO_BREACH_PREDICTED") {
        return "No breach predicted within 60 s";
    }

    // 4. Forecast unavailable
    if (riskStatus === "FORECAST_UNAVAILABLE") {
        return "N/A — Forecast unavailable";
    }

    // Fallback checks for direct numeric time_to_risk_seconds values
    if (ttrRaw !== null && ttrRaw !== undefined && !isNaN(parseFloat(ttrRaw))) {
        const num = parseFloat(ttrRaw);
        if (num === 0.0) return "0 s — LIMIT EXCEEDED";
        if (num <= 60.0) return `~${Math.round(num)} s`;
        return "No breach predicted within 60 s";
    }

    return "N/A — Forecast unavailable";
}

function floatOr(val, fallback) {
    if (val === null || val === undefined) return fallback;
    const n = parseFloat(val);
    return isNaN(n) ? fallback : n;
}

function getComponentState(compId, frame) {
    if (!frame) return 'NORMAL';
    const telem = frame.telemetry || frame;
    const subHealth = frame.subsystem_health || {};
    const subStates = frame.subsystem_states || {};
    const fc = frame.latest_forecast || frame.forecast || {};
    const ass = frame.latest_predictive_assessment || frame.predictive_assessment || null;
    const activeFaults = frame.active_faults || [];

    const activeComp = activeFaults.length > 0 ? (activeFaults[0].affected_component || activeFaults[0].component || '') : '';

    if (compId === 'cyl1') {
        const cht = floatOr(telem.cht1, 120.0);
        const egt = floatOr(telem.egt1, 748.0);
        const fc30 = fc.forecast_30s ? floatOr(fc.forecast_30s.cht1, cht) : cht;
        
        if (cht >= 145.0 || egt >= 850.0) return 'CRITICAL';
        if (cht >= 138.0 || egt >= 810.0) return 'WARNING';
        if (fc30 >= 145.0) return 'WARNING';
        if (fc30 >= 138.0) return 'CAUTION';
        
        if (ass && (ass.affected_component === 'Cylinder 1' || ass.affected_component === 'CYLINDER_1' || activeComp === 'CYLINDER_1')) {
            if (ass.status === 'ACTIVE_FAULT') return 'CRITICAL';
            if (ass.status === 'PREDICTIVE_RISK' || ass.status === 'WARNING') return 'WARNING';
            if (ass.status === 'CAUTION') return 'CAUTION';
            if (ass.status === 'WATCH') return 'WATCH';
        }

        if (cht >= 132.0 || egt >= 780.0) return 'CAUTION';
        if (cht >= 126.0 || egt >= 765.0) return 'WATCH';
        return 'NORMAL';
    }

    if (compId === 'cyl2') {
        const cht = floatOr(telem.cht2, 120.0);
        const egt = floatOr(telem.egt2, 750.0);
        const fc30 = fc.forecast_30s ? floatOr(fc.forecast_30s.cht2, cht) : cht;
        if (cht >= 145.0 || egt >= 850.0) return 'CRITICAL';
        if (cht >= 138.0 || egt >= 810.0) return 'WARNING';
        if (fc30 >= 145.0) return 'WARNING';
        if (fc30 >= 138.0) return 'CAUTION';
        if (activeComp === 'CYLINDER_2') return 'WARNING';
        if (cht >= 132.0 || egt >= 780.0) return 'CAUTION';
        if (cht >= 126.0 || egt >= 765.0) return 'WATCH';
        return 'NORMAL';
    }

    if (compId === 'cyl3') {
        const cht = floatOr(telem.cht3, 120.0);
        const egt = floatOr(telem.egt3, 746.0);
        const fc30 = fc.forecast_30s ? floatOr(fc.forecast_30s.cht3, cht) : cht;
        if (cht >= 145.0 || egt >= 850.0) return 'CRITICAL';
        if (cht >= 138.0 || egt >= 810.0) return 'WARNING';
        if (fc30 >= 145.0) return 'WARNING';
        if (fc30 >= 138.0) return 'CAUTION';
        if (activeComp === 'CYLINDER_3') return 'WARNING';
        if (cht >= 132.0 || egt >= 780.0) return 'CAUTION';
        if (cht >= 126.0 || egt >= 765.0) return 'WATCH';
        return 'NORMAL';
    }

    if (compId === 'cyl4') {
        const cht = floatOr(telem.cht4, 120.0);
        const egt = floatOr(telem.egt4, 749.0);
        const fc30 = fc.forecast_30s ? floatOr(fc.forecast_30s.cht4, cht) : cht;
        if (cht >= 145.0 || egt >= 850.0) return 'CRITICAL';
        if (cht >= 138.0 || egt >= 810.0) return 'WARNING';
        if (fc30 >= 145.0) return 'WARNING';
        if (fc30 >= 138.0) return 'CAUTION';
        if (activeComp === 'CYLINDER_4') return 'WARNING';
        if (cht >= 132.0 || egt >= 780.0) return 'CAUTION';
        if (cht >= 126.0 || egt >= 765.0) return 'WATCH';
        return 'NORMAL';
    }

    if (compId === 'oil') {
        const oilP = floatOr(telem.oil_press, 4.2);
        const oilT = floatOr(telem.oil_temp, 88.0);
        const h = subHealth.lubrication ?? 99.0;
        const fc30P = fc.forecast_30s ? floatOr(fc.forecast_30s.oil_press, oilP) : oilP;

        if (oilP <= 2.5 || oilT >= 115.0 || h < 45.0) return 'CRITICAL';
        if (oilP <= 3.0 || oilT >= 105.0 || h < 65.0) return 'WARNING';
        if (fc30P <= 2.8) return 'WARNING';
        if (fc30P <= 3.2 || oilP <= 3.4 || oilT >= 98.0 || h < 80.0) return 'CAUTION';
        if (subStates.lubrication && subStates.lubrication !== 'NORMAL') return subStates.lubrication;
        if (oilP <= 3.8 || h < 85.0) return 'WATCH';
        return 'NORMAL';
    }

    if (compId === 'turbo') {
        const map = floatOr(telem.map, 1.15);
        const h = subHealth.combustion ?? 97.0;
        if (map >= 1.45 || h < 45.0) return 'CRITICAL';
        if (map >= 1.35 || h < 65.0) return 'WARNING';
        if (map >= 1.25 || h < 80.0) return 'CAUTION';
        if (subStates.combustion && subStates.combustion !== 'NORMAL') return subStates.combustion;
        if (h < 85.0) return 'WATCH';
        return 'NORMAL';
    }

    if (compId === 'mechanical') {
        const vib = floatOr(telem.vibration_rms, 1.12);
        const h = subHealth.mechanical ?? 96.0;
        const fc30V = fc.forecast_30s ? floatOr(fc.forecast_30s.vibration_rms, vib) : vib;
        if (vib >= 2.5 || h < 45.0) return 'CRITICAL';
        if (vib >= 1.8 || h < 65.0) return 'WARNING';
        if (fc30V >= 1.8) return 'WARNING';
        if (fc30V >= 1.4 || vib >= 1.5 || h < 80.0) return 'CAUTION';
        if (subStates.mechanical && subStates.mechanical !== 'NORMAL') return subStates.mechanical;
        if (vib >= 1.3 || h < 85.0) return 'WATCH';
        return 'NORMAL';
    }

    if (compId === 'electrical') {
        const volt = floatOr(telem.battery_volt, 14.1);
        const h = subHealth.electrical ?? 100.0;
        if (volt <= 11.5 || volt >= 15.5 || h < 45.0) return 'CRITICAL';
        if (volt <= 12.5 || volt >= 15.0 || h < 65.0) return 'WARNING';
        if (volt <= 13.0 || volt >= 14.6 || h < 80.0) return 'CAUTION';
        if (subStates.electrical && subStates.electrical !== 'NORMAL') return subStates.electrical;
        if (h < 85.0) return 'WATCH';
        return 'NORMAL';
    }

    if (compId === 'core') {
        const h = frame.overall_health_index ?? 98.0;
        const st = frame.system_state || 'NORMAL';
        if (st === 'CRITICAL' || h < 45.0) return 'CRITICAL';
        if (st === 'WARNING' || h < 65.0) return 'WARNING';
        if (st === 'CAUTION' || h < 80.0) return 'CAUTION';
        if (st === 'WATCH' || h < 85.0) return 'WATCH';
        return 'NORMAL';
    }

    return 'NORMAL';
}

function applyComponentSvgStyle(gElem, compState) {
    if (!gElem) return;
    const rect = gElem.querySelector('.svg-comp-rect');
    if (!rect) return;

    if (compState === 'CRITICAL') {
        rect.style.stroke = '#dc2626';
        rect.style.fill = '#fee2e2';
    } else if (compState === 'WARNING') {
        rect.style.stroke = '#ea580c';
        rect.style.fill = '#fff7ed';
    } else if (compState === 'CAUTION') {
        rect.style.stroke = '#d97706';
        rect.style.fill = '#fef3c7';
    } else if (compState === 'WATCH') {
        rect.style.stroke = '#2563eb';
        rect.style.fill = '#eff6ff';
    } else {
        rect.style.stroke = '#cbd5e1';
        rect.style.fill = '#ffffff';
    }
}

function updateDigitalTwinSchematic(frame) {
    lastTwinFrame = frame;
    const telem = frame.telemetry || frame;

    const components = ['cyl1', 'cyl2', 'cyl3', 'cyl4', 'turbo', 'oil', 'mechanical', 'electrical', 'core'];

    if (document.getElementById('svg-val-turbo')) document.getElementById('svg-val-turbo').textContent = `MAP: ${floatOr(telem.map, 1.15).toFixed(2)} bar`;
    if (document.getElementById('svg-val-oil')) document.getElementById('svg-val-oil').textContent = `${floatOr(telem.oil_press, 4.2).toFixed(2)} BAR | ${floatOr(telem.oil_temp, 88.0).toFixed(1)}°C`;
    if (document.getElementById('svg-val-mechanical')) document.getElementById('svg-val-mechanical').textContent = `${floatOr(telem.vibration_rms, 1.12).toFixed(2)} g (RMS)`;
    if (document.getElementById('svg-val-electrical')) document.getElementById('svg-val-electrical').textContent = `${floatOr(telem.battery_volt, 14.1).toFixed(2)} V`;
    if (document.getElementById('svg-val-core')) document.getElementById('svg-val-core').textContent = `${Math.round(floatOr(telem.rpm, 5000))} RPM | 62.5 kW`;
    if (document.getElementById('svg-hi-core')) document.getElementById('svg-hi-core').textContent = `Overall HI: ${(frame.overall_health_index ?? 98.0).toFixed(1)}%`;

    for (let i = 1; i <= 4; i++) {
        const valElem = document.getElementById(`svg-val-cyl${i}`);
        if (valElem) valElem.textContent = `${Math.round(floatOr(telem[`cht${i}`], 120.0))}°C`;
    }

    components.forEach(compId => {
        const stateVal = getComponentState(compId, frame);
        const stateElem = document.getElementById(`svg-state-${compId}`);
        if (stateElem) {
            stateElem.textContent = stateVal;
        }
        const gElem = document.getElementById(`svg-comp-${compId}`);
        if (gElem) {
            applyComponentSvgStyle(gElem, stateVal);
            if (compId === selectedTwinComponent) {
                gElem.classList.add('selected');
            } else {
                gElem.classList.remove('selected');
            }
        }
    });

    updateTwinComponentDetail(frame);
}

function updateTwinComponentDetail(frame) {
    if (!frame) return;
    const telem = frame.telemetry || frame;
    const subHealth = frame.subsystem_health || {};
    const resTab = frame.residuals_table || {};
    const fc = frame.latest_forecast || frame.forecast || {};
    const ass = frame.latest_predictive_assessment || frame.predictive_assessment || null;

    const titleElem = document.getElementById("comp-detail-title");
    const stateBadge = document.getElementById("comp-detail-state");
    const bodyElem = document.getElementById("comp-detail-body");

    if (!titleElem || !bodyElem || !stateBadge) return;

    const compId = selectedTwinComponent || 'cyl1';
    const compState = getComponentState(compId, frame);

    stateBadge.innerText = compState;
    stateBadge.className = `gauge-state-badge ${compState}`;

    const names = {
        'cyl1': 'Cylinder 1', 'cyl2': 'Cylinder 2', 'cyl3': 'Cylinder 3', 'cyl4': 'Cylinder 4',
        'oil': 'Oil System', 'turbo': 'Turbo / Intake System', 'mechanical': 'Mechanical Subsystem',
        'electrical': 'Electrical Subsystem', 'core': 'Engine Core'
    };

    titleElem.innerHTML = `<i class="fa-solid fa-microchip text-blue"></i> Component Inspector: ${names[compId] || 'Cylinder 1'}`;

    let html = '';

    if (compId.startsWith('cyl')) {
        const idx = compId.replace('cyl', '');
        const cht = floatOr(telem[`cht${idx}`], 120.0).toFixed(1);
        const egt = floatOr(telem[`egt${idx}`], 748.0).toFixed(1);
        const expCht = (resTab.avg_cht ? (resTab.avg_cht.expected ?? resTab.avg_cht.predicted_value) : 121.0);
        const resCht = (parseFloat(cht) - expCht).toFixed(1);

        const fc10 = fc.forecast_10s ? floatOr(fc.forecast_10s[`cht${idx}`], parseFloat(cht)).toFixed(1) : 'Warming up';
        const fc30 = fc.forecast_30s ? floatOr(fc.forecast_30s[`cht${idx}`], parseFloat(cht)).toFixed(1) : 'Warming up';
        const fc60 = fc.forecast_60s ? floatOr(fc.forecast_60s[`cht${idx}`], parseFloat(cht)).toFixed(1) : 'Warming up';
        const ttrVal = formatTimeToRisk(ass);
        const aeScore = (frame.anomaly_score ?? 0.015).toFixed(3);
        const cusumSt = frame.cusum_state || 'NORMAL';

        html = `
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:0.6rem; margin-bottom:0.6rem; font-size:0.78rem;">
                <div style="font-weight:700; color:var(--primary-blue); margin-bottom:4px;"><i class="fa-solid fa-code-compare"></i> CURRENT vs PHYSICS EXPECTED vs GRU FUTURE</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.35rem;">
                    <div><strong>Current CHT${idx}:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${cht} °C</span></div>
                    <div><strong>Physics Expected:</strong> ${expCht} °C</div>
                    <div><strong>Residual Δ:</strong> <span class="${Math.abs(resCht) > 8 ? 'text-red' : 'text-green'}">${resCht >= 0 ? '+' : ''}${resCht} °C</span></div>
                    <div><strong>30s GRU Forecast:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${fc30} °C</span></div>
                    <div><strong>10s Forecast:</strong> ${fc10} °C</div>
                    <div><strong>60s Forecast:</strong> ${fc60} °C</div>
                    <div><strong>Current Condition:</strong> ${parseFloat(cht) >= 145.0 ? 'Exceeded Limit' : (parseFloat(cht) >= 135.0 ? 'Watch Zone' : 'Ref Envelope')}</div>
                    <div><strong>Predictive State:</strong> <span class="role-badge ${compState === 'NORMAL' ? 'op' : 'eng'}">${compState}</span></div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.4rem; margin-bottom:0.5rem; font-size:0.78rem;">
                <div><strong>Current EGT${idx}:</strong> ${egt} °C</div>
                <div><strong>Subsystem Health:</strong> ${subHealth.thermal ?? 98.0}%</div>
                <div><strong>Autoencoder Score:</strong> ${aeScore}</div>
                <div><strong>CUSUM Status:</strong> <span class="gauge-state-badge ${cusumSt}">${cusumSt}</span></div>
                <div><strong>Est. Time-to-Risk:</strong> ${ttrVal}</div>
                <div><strong>Component State:</strong> <span class="gauge-state-badge ${compState}">${compState}</span></div>
            </div>
            <div style="font-size:0.75rem; background:#eff6ff; border:1px solid #bfdbfe; color:#1e40af; padding:6px; border-radius:6px;">
                <i class="fa-solid fa-circle-info"></i> <strong>Diagnostic Evidence:</strong> ${compState === 'NORMAL' ? 'Operating within nominal thermal reference envelope' : `Thermal excursion / predictive risk detected on Cylinder ${idx}`}
            </div>
        `;
    } else if (compId === 'oil') {
        const press = floatOr(telem.oil_press, 4.2).toFixed(2);
        const temp = floatOr(telem.oil_temp, 88.0).toFixed(1);
        const expOil = (resTab.oil_press ? (resTab.oil_press.expected ?? resTab.oil_press.predicted_value) : 4.25);
        const resOil = (parseFloat(press) - expOil).toFixed(2);

        const fc10 = fc.forecast_10s ? floatOr(fc.forecast_10s.oil_press, parseFloat(press)).toFixed(2) : 'Warming up';
        const fc30 = fc.forecast_30s ? floatOr(fc.forecast_30s.oil_press, parseFloat(press)).toFixed(2) : 'Warming up';
        const fc60 = fc.forecast_60s ? floatOr(fc.forecast_60s.oil_press, parseFloat(press)).toFixed(2) : 'Warming up';
        const ttrVal = formatTimeToRisk(ass);

        html = `
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:0.6rem; margin-bottom:0.6rem; font-size:0.78rem;">
                <div style="font-weight:700; color:var(--primary-blue); margin-bottom:4px;"><i class="fa-solid fa-code-compare"></i> CURRENT vs PHYSICS EXPECTED vs GRU FUTURE</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.35rem;">
                    <div><strong>Current Oil Press:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${press} bar</span></div>
                    <div><strong>Physics Expected:</strong> ${expOil} bar</div>
                    <div><strong>Residual Δ:</strong> <span class="${Math.abs(resOil) > 0.4 ? 'text-red' : 'text-green'}">${resOil >= 0 ? '+' : ''}${resOil} bar</span></div>
                    <div><strong>30s GRU Forecast:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${fc30} bar</span></div>
                    <div><strong>10s Forecast:</strong> ${fc10} bar</div>
                    <div><strong>60s Forecast:</strong> ${fc60} bar</div>
                    <div><strong>Current Condition:</strong> ${parseFloat(press) <= 2.50 ? 'Exceeded Limit' : 'Ref Envelope'}</div>
                    <div><strong>Predictive State:</strong> <span class="role-badge ${compState === 'NORMAL' ? 'op' : 'eng'}">${compState}</span></div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.4rem; margin-bottom:0.5rem; font-size:0.78rem;">
                <div><strong>Oil Temp:</strong> ${temp} °C</div>
                <div><strong>Lubrication Health:</strong> ${subHealth.lubrication ?? 99.0}%</div>
                <div><strong>Autoencoder Score:</strong> ${(frame.anomaly_score ?? 0.015).toFixed(3)}</div>
                <div><strong>CUSUM Status:</strong> <span class="gauge-state-badge ${frame.cusum_state || 'NORMAL'}">${frame.cusum_state || 'NORMAL'}</span></div>
                <div><strong>Est. Time-to-Risk:</strong> ${ttrVal}</div>
                <div><strong>Component State:</strong> <span class="gauge-state-badge ${compState}">${compState}</span></div>
            </div>
            <div style="font-size:0.75rem; background:#eff6ff; border:1px solid #bfdbfe; color:#1e40af; padding:6px; border-radius:6px;">
                <i class="fa-solid fa-circle-info"></i> <strong>Lubrication Evidence:</strong> ${compState === 'NORMAL' ? 'Nominal oil pressure & sump temperature' : `Lubrication pressure degradation detected (${press} bar)`}
            </div>
        `;
    } else if (compId === 'mechanical') {
        const vib = floatOr(telem.vibration_rms, 1.12).toFixed(2);
        const fc30 = fc.forecast_30s ? floatOr(fc.forecast_30s.vibration_rms, parseFloat(vib)).toFixed(2) : 'Warming up';
        const ttrVal = formatTimeToRisk(ass);

        html = `
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:0.6rem; margin-bottom:0.6rem; font-size:0.78rem;">
                <div style="font-weight:700; color:var(--primary-blue); margin-bottom:4px;"><i class="fa-solid fa-code-compare"></i> CURRENT vs BASELINE vs GRU FUTURE</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.35rem;">
                    <div><strong>Vibration RMS:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${vib} g</span></div>
                    <div><strong>Baseline RMS:</strong> 1.10 g</div>
                    <div><strong>Residual Δ:</strong> <span class="${parseFloat(vib) > 1.5 ? 'text-red' : 'text-green'}">+${(parseFloat(vib) - 1.10).toFixed(2)} g</span></div>
                    <div><strong>30s Forecast:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${fc30} g</span></div>
                    <div><strong>Current Condition:</strong> ${parseFloat(vib) >= 2.50 ? 'Exceeded Limit' : 'Ref Envelope'}</div>
                    <div><strong>Predictive State:</strong> <span class="role-badge ${compState === 'NORMAL' ? 'op' : 'eng'}">${compState}</span></div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.4rem; margin-bottom:0.5rem; font-size:0.78rem;">
                <div><strong>Mechanical Health:</strong> ${subHealth.mechanical ?? 96.0}%</div>
                <div><strong>Autoencoder Score:</strong> ${(frame.anomaly_score ?? 0.015).toFixed(3)}</div>
                <div><strong>Est. Time-to-Risk:</strong> ${ttrVal}</div>
                <div><strong>Component State:</strong> <span class="gauge-state-badge ${compState}">${compState}</span></div>
            </div>
        `;
    } else if (compId === 'electrical') {
        const volt = floatOr(telem.battery_volt, 14.1).toFixed(2);
        const expVolt = 14.10;
        const resVolt = (parseFloat(volt) - expVolt).toFixed(2);
        const ttrVal = formatTimeToRisk(ass);

        html = `
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:0.6rem; margin-bottom:0.6rem; font-size:0.78rem;">
                <div style="font-weight:700; color:var(--primary-blue); margin-bottom:4px;"><i class="fa-solid fa-code-compare"></i> CURRENT vs BASELINE vs DRIFT</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.35rem;">
                    <div><strong>Bus Voltage:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${volt} V</span></div>
                    <div><strong>Physics Expected:</strong> 14.10 V</div>
                    <div><strong>Measurement Residual:</strong> <span class="${Math.abs(resVolt) > 0.8 ? 'text-red' : 'text-green'}">${resVolt >= 0 ? '+' : ''}${resVolt} V</span></div>
                    <div><strong>Sensor Evidence:</strong> ${Math.abs(resVolt) > 0.5 ? 'Sensor Drift Detected' : 'Nominal Calibration'}</div>
                    <div><strong>Predictive State:</strong> <span class="role-badge ${compState === 'NORMAL' ? 'op' : 'eng'}">${compState}</span></div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.4rem; margin-bottom:0.5rem; font-size:0.78rem;">
                <div><strong>Electrical Health:</strong> ${subHealth.electrical ?? 100.0}%</div>
                <div><strong>Autoencoder Score:</strong> ${(frame.anomaly_score ?? 0.015).toFixed(3)}</div>
                <div><strong>Est. Time-to-Risk:</strong> ${ttrVal}</div>
                <div><strong>Component State:</strong> <span class="gauge-state-badge ${compState}">${compState}</span></div>
            </div>
        `;
    } else if (compId === 'turbo') {
        const map = floatOr(telem.map, 1.15).toFixed(2);
        const expMap = 1.12;
        const resMap = (parseFloat(map) - expMap).toFixed(2);
        const fc30 = fc.forecast_30s ? floatOr(fc.forecast_30s.map, parseFloat(map)).toFixed(2) : 'Warming up';

        html = `
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:0.6rem; margin-bottom:0.6rem; font-size:0.78rem;">
                <div style="font-weight:700; color:var(--primary-blue); margin-bottom:4px;"><i class="fa-solid fa-code-compare"></i> CURRENT vs BASELINE vs GRU FUTURE</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.35rem;">
                    <div><strong>Manifold Press (MAP):</strong> <span style="font-family:var(--font-mono); font-weight:700;">${map} bar</span></div>
                    <div><strong>Physics Expected:</strong> 1.12 bar</div>
                    <div><strong>Residual Δ:</strong> <span class="${Math.abs(resMap) > 0.15 ? 'text-red' : 'text-green'}">${resMap >= 0 ? '+' : ''}${resMap} bar</span></div>
                    <div><strong>30s Forecast:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${fc30} bar</span></div>
                    <div><strong>Predictive State:</strong> <span class="role-badge ${compState === 'NORMAL' ? 'op' : 'eng'}">${compState}</span></div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.4rem; margin-bottom:0.5rem; font-size:0.78rem;">
                <div><strong>Combustion Health:</strong> ${subHealth.combustion ?? 97.0}%</div>
                <div><strong>Component State:</strong> <span class="gauge-state-badge ${compState}">${compState}</span></div>
            </div>
        `;
    } else if (compId === 'core') {
        const rpm = Math.round(floatOr(telem.rpm, 5000));
        const hi = (frame.overall_health_index ?? 98.0).toFixed(1);
        const st = frame.system_state || 'NORMAL';

        html = `
            <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:0.6rem; margin-bottom:0.6rem; font-size:0.78rem;">
                <div style="font-weight:700; color:var(--primary-blue); margin-bottom:4px;"><i class="fa-solid fa-code-compare"></i> CORE ENGINE TOPOLOGY SUMMARY</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.35rem;">
                    <div><strong>Engine Speed:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${rpm} RPM</span></div>
                    <div><strong>Estimated Power:</strong> 62.5 kW</div>
                    <div><strong>Overall Health Index:</strong> <span style="font-family:var(--font-mono); font-weight:700;">${hi}%</span></div>
                    <div><strong>Global System State:</strong> <span class="badge-state ${st}">${st}</span></div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.4rem; margin-bottom:0.5rem; font-size:0.78rem;">
                <div><strong>Autoencoder Score:</strong> ${(frame.anomaly_score ?? 0.015).toFixed(3)}</div>
                <div><strong>CUSUM State:</strong> <span class="gauge-state-badge ${frame.cusum_state || 'NORMAL'}">${frame.cusum_state || 'NORMAL'}</span></div>
                <div><strong>Core State:</strong> <span class="gauge-state-badge ${compState}">${compState}</span></div>
            </div>
        `;
    }

    bodyElem.innerHTML = html;
}

// FAULT INJECTION & ENGINEER ANALYTICS SYNCHRONIZATION
function updateEngineerAnalytics(frame) {
    if (!frame) return;
    const telem = frame.telemetry || frame;
    const resTab = frame.residuals_table || {};
    const fc = frame.latest_forecast || frame.forecast || {};
    const ass = frame.latest_predictive_assessment || frame.predictive_assessment || null;
    const activeFaults = frame.active_faults || [];
    const sysState = frame.system_state || "NORMAL";

    // 1. Simulated Fault Banner
    const bannerElem = document.getElementById("simulated-fault-banner-eng");
    if (bannerElem) {
        if (activeFaults.length > 0) {
            bannerElem.classList.remove("hidden");
            const af = activeFaults[0];
            if (document.getElementById("eng-fault-scenario")) document.getElementById("eng-fault-scenario").innerText = af.fault_scenario || af.scenario || "FAULT";
            if (document.getElementById("eng-fault-comp")) document.getElementById("eng-fault-comp").innerText = af.affected_component || af.component || "CYLINDER_1";
            if (document.getElementById("eng-fault-prof")) document.getElementById("eng-fault-prof").innerText = af.injection_profile || af.profile || "GRADUAL";
            if (document.getElementById("eng-fault-effect")) document.getElementById("eng-fault-effect").innerText = `${Math.round(af.current_effect_pct || (af.intensity * 100) || 0)}%`;
            if (document.getElementById("eng-fault-elapsed")) document.getElementById("eng-fault-elapsed").innerText = `${(af.elapsed_seconds || 0).toFixed(1)}s`;
        } else {
            bannerElem.classList.add("hidden");
        }
    }

    // 2. AI Analytics Section
    const statusBadge = document.getElementById("eng-ai-status-badge");
    if (statusBadge) {
        statusBadge.innerText = sysState;
        statusBadge.className = `badge-state ${sysState}`;
    }

    const aeScore = (frame.anomaly_score ?? 0.015).toFixed(3);
    if (document.getElementById("eng-ae-score")) document.getElementById("eng-ae-score").innerText = aeScore;
    if (document.getElementById("eng-ae-trend")) {
        const trendElem = document.getElementById("eng-ae-trend");
        if (frame.anomaly_score > 0.10) {
            trendElem.innerText = "Increasing Excursion";
            trendElem.className = "text-red font-semibold";
        } else {
            trendElem.innerText = "Stable Baseline";
            trendElem.className = "text-green font-semibold";
        }
    }

    const cusumSt = frame.cusum_state || "NORMAL";
    const cusumElem = document.getElementById("eng-cusum-state");
    if (cusumElem) {
        cusumElem.innerText = cusumSt;
        cusumElem.className = `gauge-state-badge ${cusumSt}`;
    }

    const mainRes = resTab.avg_cht ? parseFloat(resTab.avg_cht.residual || 0.0) : 0.0;
    if (document.getElementById("eng-residual-val")) {
        const resElem = document.getElementById("eng-residual-val");
        resElem.innerText = `${mainRes >= 0 ? '+' : ''}${mainRes.toFixed(1)} °C`;
        resElem.className = Math.abs(mainRes) > 8.0 ? "text-red font-mono font-bold" : "text-green font-mono font-bold";
    }

    const riskScore = ass ? (typeof ass.degradation_score === 'number' ? ass.degradation_score.toFixed(2) : "0.00") : "0.00";
    if (document.getElementById("eng-risk-score")) document.getElementById("eng-risk-score").innerText = `${riskScore} / 1.0`;

    const ttr = formatTimeToRisk(ass);
    if (document.getElementById("eng-ttr")) document.getElementById("eng-ttr").innerText = ttr;

    const failureMode = sysState === "NORMAL" ? "NONE" : (ass ? (ass.predicted_failure_mode || ass.description || "NONE") : "NONE");
    if (document.getElementById("eng-failure-mode")) document.getElementById("eng-failure-mode").innerText = failureMode;

    // 3. Resolve Target Component Channel Dynamically
    let targetChannelKey = "cht1";
    const primaryParam = ass?.primary_parameter ? String(ass.primary_parameter).toLowerCase() : null;
    const affComp = (ass?.affected_component || frame.dominant_component || activeFaults[0]?.affected_component || activeFaults[0]?.component || "").toUpperCase();

    if (primaryParam && ["cht1", "cht2", "cht3", "cht4", "oil_press", "oil_temp", "vibration_rms", "battery_volt"].includes(primaryParam)) {
        targetChannelKey = primaryParam;
    } else if (affComp.includes("CYLINDER_4") || affComp.includes("CYLINDER 4") || affComp.includes("CHT4")) {
        targetChannelKey = "cht4";
    } else if (affComp.includes("CYLINDER_3") || affComp.includes("CYLINDER 3") || affComp.includes("CHT3")) {
        targetChannelKey = "cht3";
    } else if (affComp.includes("CYLINDER_2") || affComp.includes("CYLINDER 2") || affComp.includes("CHT2")) {
        targetChannelKey = "cht2";
    } else if (affComp.includes("CYLINDER_1") || affComp.includes("CYLINDER 1") || affComp.includes("CHT1")) {
        targetChannelKey = "cht1";
    } else if (affComp.includes("OIL") || affComp.includes("LUBRICATION")) {
        targetChannelKey = "oil_press";
    } else if (affComp.includes("BEARING") || affComp.includes("VIBRATION") || affComp.includes("MECHANICAL")) {
        targetChannelKey = "vibration_rms";
    } else if (affComp.includes("ELECTRICAL") || affComp.includes("BUS")) {
        targetChannelKey = "battery_volt";
    }

    const channelLabels = {
        "cht1": "Cylinder 1 CHT", "cht2": "Cylinder 2 CHT", "cht3": "Cylinder 3 CHT", "cht4": "Cylinder 4 CHT",
        "oil_press": "Oil Pressure", "oil_temp": "Oil Temp", "vibration_rms": "Vibration RMS", "battery_volt": "Battery Volt"
    };
    const channelUnits = {
        "cht1": "°C", "cht2": "°C", "cht3": "°C", "cht4": "°C",
        "oil_press": "bar", "oil_temp": "°C", "vibration_rms": "g", "battery_volt": "V"
    };

    const curVal = telem[targetChannelKey] !== undefined ? parseFloat(telem[targetChannelKey]) : 120.0;
    const curUnit = channelUnits[targetChannelKey] || "°C";

    if (document.getElementById("eng-forecast-mode")) {
        document.getElementById("eng-forecast-mode").innerText = `GRU Forecast: ${channelLabels[targetChannelKey] || targetChannelKey.toUpperCase()}`;
    }

    const f10Dict = fc.forecast_10s || (fc.forecast && fc.forecast["10s"]) || {};
    const f30Dict = fc.forecast_30s || (fc.forecast && fc.forecast["30s"]) || {};
    const f60Dict = fc.forecast_60s || (fc.forecast && fc.forecast["60s"]) || {};

    const getFcChannelVal = (dict, key, defaultVal) => {
        if (!dict) return defaultVal;
        if (dict[key] !== undefined && dict[key] !== null) return parseFloat(dict[key]);
        if (key === "oil_press" && dict.oil_pressure !== undefined) return parseFloat(dict.oil_pressure);
        if (key === "oil_temp" && dict.oil_temperature !== undefined) return parseFloat(dict.oil_temperature);
        return defaultVal;
    };

    if (fc.status === "READY") {
        const v10 = getFcChannelVal(f10Dict, targetChannelKey, curVal);
        const v30 = getFcChannelVal(f30Dict, targetChannelKey, curVal);
        const v60 = getFcChannelVal(f60Dict, targetChannelKey, curVal);

        const fmtDec = (curUnit === "bar" || curUnit === "g" || curUnit === "V") ? 2 : 1;
        if (document.getElementById("eng-fc-10s")) document.getElementById("eng-fc-10s").innerText = `${v10.toFixed(fmtDec)} ${curUnit}`;
        if (document.getElementById("eng-fc-30s")) document.getElementById("eng-fc-30s").innerText = `${v30.toFixed(fmtDec)} ${curUnit}`;
        if (document.getElementById("eng-fc-60s")) document.getElementById("eng-fc-60s").innerText = `${v60.toFixed(fmtDec)} ${curUnit}`;
    } else {
        const engFallback = (fc.status === "WARMING_UP") ? "Warming up..." : "Awaiting next inference...";
        if (document.getElementById("eng-fc-10s")) document.getElementById("eng-fc-10s").innerText = engFallback;
        if (document.getElementById("eng-fc-30s")) document.getElementById("eng-fc-30s").innerText = engFallback;
        if (document.getElementById("eng-fc-60s")) document.getElementById("eng-fc-60s").innerText = engFallback;
    }

    // 4. Update 5-Subsystem Health Breakdown Progress Bars & Percentages
    const subHealth = frame.subsystem_health || {};
    ["thermal", "lubrication", "combustion", "electrical", "mechanical"].forEach(subKey => {
        const val = subHealth[subKey] !== undefined ? parseFloat(subHealth[subKey]) : null;
        const barElem = document.getElementById(`hi-${subKey}`);
        const pctElem = document.getElementById(`pct-${subKey}`);

        if (val !== null && !isNaN(val)) {
            const roundedVal = Math.round(val);
            if (barElem) {
                barElem.style.width = `${Math.max(0, Math.min(100, roundedVal))}%`;
                if (val < 75.0) barElem.style.backgroundColor = '#dc2626';
                else if (val < 85.0) barElem.style.backgroundColor = '#d97706';
                else barElem.style.backgroundColor = '#059669';
            }
            if (pctElem) {
                pctElem.innerText = `${val.toFixed(1)}%`;
                pctElem.className = val < 75.0 ? 'pct text-red font-bold' : (val < 85.0 ? 'pct font-bold' : 'pct text-green font-bold');
            }
        } else {
            if (barElem) barElem.style.width = '0%';
            if (pctElem) pctElem.innerText = 'N/A';
        }
    });

    // 5. Update XAI Autonomous Maintenance Advisory
    const xaiTextElem = document.getElementById("xai-advisory-text");
    if (xaiTextElem) {
        const diagnostics = frame.predictive_diagnostics || frame.diagnostics || [];
        const advisories = frame.maintenance_advisories || [];
        const primaryDiag = diagnostics.length > 0 ? diagnostics[0] : null;

        if (sysState === "CRITICAL" || sysState === "WARNING" || sysState === "ACTIVE_FAULT") {
            if (primaryDiag && primaryDiag.advisory) {
                const comp = primaryDiag.affected_component || primaryDiag.component || frame.dominant_component || "Component";
                const sub = primaryDiag.affected_subsystem || frame.dominant_subsystem || "Subsystem";
                const obsVal = primaryDiag.observed_value !== undefined ? primaryDiag.observed_value : "";
                const param = primaryDiag.observed_parameter || "";
                const obsStr = obsVal ? ` (${param} = ${obsVal})` : "";
                xaiTextElem.innerHTML = `<strong class="text-red">[${sysState} ADVISORY]</strong> Excursion detected in <strong>${sub} (${comp})</strong>${obsStr}. ${primaryDiag.advisory}`;
            } else if (advisories.length > 0) {
                xaiTextElem.innerHTML = `<strong class="text-red">[${sysState} ADVISORY]</strong> ${advisories[0]}`;
            } else {
                const domSub = frame.dominant_subsystem || "Thermal";
                const domComp = frame.dominant_component || "Engine Subsystem";
                xaiTextElem.innerHTML = `<strong class="text-red">[${sysState} ADVISORY]</strong> Critical safety envelope breach detected in ${domSub} subsystem (${domComp}). Reduce propulsion demand immediately and inspect engine parameters.`;
            }
        } else if (sysState === "CAUTION" || sysState === "WATCH") {
            if (primaryDiag && primaryDiag.advisory) {
                xaiTextElem.innerHTML = `<strong class="text-orange">[${sysState} WARNING]</strong> ${primaryDiag.advisory}`;
            } else {
                xaiTextElem.innerHTML = `<strong class="text-orange">[${sysState} WARNING]</strong> Minor parameter variation detected. Continuous monitoring recommended.`;
            }
        } else {
            xaiTextElem.innerText = "Propulsion system operating within nominal physical parameters. Continuous monitoring active.";
        }
    }

    // 6. Update Fault Progression Chart
    updateFaultProgressionChart(frame);
}

function initFaultProgressionChart() {
    try {
        if (typeof Chart === "undefined") return;
        const chartElem = document.getElementById("chart-fault-progression");
        if (!chartElem || faultProgressionChart) return;

        const ctx = chartElem.getContext("2d");
        faultProgressionChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Observed Telemetry',
                        data: [],
                        borderColor: '#dc2626',
                        backgroundColor: 'rgba(220, 38, 38, 0.08)',
                        borderWidth: 2,
                        fill: false,
                        tension: 0.2,
                        pointRadius: 0
                    },
                    {
                        label: 'Physics Expected Baseline',
                        data: [],
                        borderColor: '#059669',
                        borderWidth: 1.5,
                        borderDash: [4, 4],
                        pointRadius: 0,
                        fill: false
                    },
                    {
                        label: '30s GRU Forecast',
                        data: [],
                        borderColor: '#9333ea',
                        borderWidth: 2,
                        borderDash: [6, 3],
                        pointRadius: 3,
                        pointBackgroundColor: '#9333ea',
                        fill: false
                    },
                    {
                        label: 'Safety Threshold Limit',
                        data: [],
                        borderColor: '#991b1b',
                        borderWidth: 1.5,
                        borderDash: [2, 2],
                        pointRadius: 0,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: {
                        grid: { color: 'rgba(15, 23, 42, 0.05)' },
                        ticks: { color: '#64748b', font: { family: 'Inter', size: 9 }, maxTicksLimit: 6 }
                    },
                    y: {
                        grid: { color: 'rgba(15, 23, 42, 0.06)' },
                        ticks: { color: '#475569', font: { family: 'Inter', size: 9 } }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { color: '#0f172a', font: { family: 'Outfit', size: 9, weight: '700' }, usePointStyle: true, boxWidth: 6, padding: 4 }
                    }
                }
            }
        });
    } catch(err) {
        console.error("Failed to initialize fault progression chart:", err);
    }
}

function updateFaultProgressionChart(frame) {
    if (!faultProgressionChart) {
        initFaultProgressionChart();
    }
    if (!faultProgressionChart) return;

    const telem = frame.telemetry || frame;
    const fc = frame.latest_forecast || frame.forecast || {};
    const resTab = frame.residuals_table || {};
    const ass = frame.latest_predictive_assessment || frame.predictive_assessment || null;
    const activeFaults = frame.active_faults || [];

    // Resolve target channel
    let targetChannelKey = "cht1";
    const primaryParam = ass?.primary_parameter ? String(ass.primary_parameter).toLowerCase() : null;
    const affComp = (ass?.affected_component || frame.dominant_component || activeFaults[0]?.affected_component || activeFaults[0]?.component || "").toUpperCase();

    if (primaryParam && ["cht1", "cht2", "cht3", "cht4", "oil_press", "oil_temp", "vibration_rms", "battery_volt"].includes(primaryParam)) {
        targetChannelKey = primaryParam;
    } else if (affComp.includes("CYLINDER_4") || affComp.includes("CYLINDER 4") || affComp.includes("CHT4")) {
        targetChannelKey = "cht4";
    } else if (affComp.includes("CYLINDER_3") || affComp.includes("CYLINDER 3") || affComp.includes("CHT3")) {
        targetChannelKey = "cht3";
    } else if (affComp.includes("CYLINDER_2") || affComp.includes("CYLINDER 2") || affComp.includes("CHT2")) {
        targetChannelKey = "cht2";
    } else if (affComp.includes("CYLINDER_1") || affComp.includes("CYLINDER 1") || affComp.includes("CHT1")) {
        targetChannelKey = "cht1";
    } else if (affComp.includes("OIL") || affComp.includes("LUBRICATION")) {
        targetChannelKey = "oil_press";
    } else if (affComp.includes("BEARING") || affComp.includes("VIBRATION") || affComp.includes("MECHANICAL")) {
        targetChannelKey = "vibration_rms";
    } else if (affComp.includes("ELECTRICAL") || affComp.includes("BUS")) {
        targetChannelKey = "battery_volt";
    }

    const channelNames = {
        "cht1": "CHT1", "cht2": "CHT2", "cht3": "CHT3", "cht4": "CHT4",
        "oil_press": "Oil Press", "oil_temp": "Oil Temp", "vibration_rms": "Vibration RMS", "battery_volt": "Battery Volt"
    };
    const limitsMap = {
        "cht1": 145.0, "cht2": 145.0, "cht3": 145.0, "cht4": 145.0,
        "oil_press": 2.50, "oil_temp": 110.0, "vibration_rms": 2.50, "battery_volt": 12.0
    };

    const pointsToShow = Math.min(chartDataBuffer.length, 150);
    const sliced = chartDataBuffer.slice(-pointsToShow);

    const labels = sliced.map(d => d.timeLabel);
    const obsData = sliced.map(d => {
        let val = d[targetChannelKey];
        if (val === undefined && targetChannelKey === "oil_press") val = d.oilPress;
        return val !== undefined ? parseFloat(val) : (telem[targetChannelKey] !== undefined ? parseFloat(telem[targetChannelKey]) : 120.0);
    });

    // Physics expected baseline for channel
    const phyData = sliced.map(d => {
        if (targetChannelKey.startsWith("cht")) return (resTab.avg_cht ? (resTab.avg_cht.expected ?? 121.0) : 121.0);
        if (targetChannelKey === "oil_press") return (resTab.oil_press ? (resTab.oil_press.expected ?? 4.20) : 4.20);
        if (targetChannelKey === "oil_temp") return (resTab.oil_temp ? (resTab.oil_temp.expected ?? 88.0) : 88.0);
        if (targetChannelKey === "vibration_rms") return 1.10;
        if (targetChannelKey === "battery_volt") return 14.10;
        return 120.0;
    });

    const curVal = obsData.length > 0 ? obsData[obsData.length - 1] : 120.0;

    const f30Dict = fc.forecast_30s || (fc.forecast && fc.forecast["30s"]);
    let f30 = curVal;
    if (fc.status === "READY" && f30Dict) {
        if (f30Dict[targetChannelKey] !== undefined) f30 = parseFloat(f30Dict[targetChannelKey]);
        else if (targetChannelKey === "oil_press" && f30Dict.oil_pressure !== undefined) f30 = parseFloat(f30Dict.oil_pressure);
    }

    const forecastPoints = new Array(labels.length - 1).fill(null);
    forecastPoints.push(curVal, f30);

    const forecastLabels = [...labels, '+30s'];
    const obsExtended = [...obsData, null];
    const phyExtended = [...phyData, phyData.length > 0 ? phyData[phyData.length - 1] : 121.0];
    const refLimit = limitsMap[targetChannelKey] || 145.0;
    const limitExtended = new Array(forecastLabels.length).fill(refLimit);

    // Update dataset labels dynamically
    const nameStr = channelNames[targetChannelKey] || targetChannelKey.toUpperCase();
    faultProgressionChart.data.datasets[0].label = `Observed Telemetry (${nameStr})`;
    faultProgressionChart.data.datasets[2].label = `30s GRU Forecast (${nameStr})`;

    faultProgressionChart.data.labels = forecastLabels;
    faultProgressionChart.data.datasets[0].data = obsExtended;
    faultProgressionChart.data.datasets[1].data = phyExtended;
    faultProgressionChart.data.datasets[2].data = forecastPoints;
    faultProgressionChart.data.datasets[3].data = limitExtended;

    faultProgressionChart.update('none');
}

// ROLLING RESIDUAL EXCURSION TREND CHART
let residualsChart = null;
let residualBuffer = [];
let residualWindowSeconds = 30;

function initResidualsChart() {
    try {
        if (typeof Chart === "undefined") return;
        const chartElem = document.getElementById("chart-residuals");
        if (!chartElem) return;
        const ctx = chartElem.getContext("2d");

        if (residualsChart) {
            return; // Reuse single instance without recreate/destroy flickering
        }

        residualsChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Avg CHT Residual (°C)',
                        data: [],
                        borderColor: '#dc2626',
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        unit: '°C'
                    },
                    {
                        label: 'Oil Press Residual (bar)',
                        data: [],
                        borderColor: '#d97706',
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        unit: 'bar'
                    },
                    {
                        label: 'Avg EGT Residual (°C)',
                        data: [],
                        borderColor: '#ea580c',
                        borderWidth: 1.5,
                        borderDash: [3, 3],
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        unit: '°C'
                    },
                    {
                        label: 'Oil Temp Residual (°C)',
                        data: [],
                        borderColor: '#2563eb',
                        borderWidth: 1.5,
                        borderDash: [2, 2],
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        unit: '°C'
                    },
                    {
                        label: 'Power Residual (kW)',
                        data: [],
                        borderColor: '#059669',
                        borderWidth: 1.5,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        unit: 'kW'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { size: 9 }, maxTicksLimit: 6 }
                    },
                    y: {
                        grid: { color: '#f1f5f9' },
                        ticks: { font: { size: 9 } }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { font: { size: 9, weight: '600' }, boxWidth: 10, padding: 6 }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                const dataset = context.dataset;
                                const val = context.parsed.y;
                                const unit = dataset.unit || '';
                                return `${dataset.label}: ${val >= 0 ? '+' : ''}${val.toFixed(2)} ${unit}`;
                            }
                        }
                    }
                }
            }
        });
    } catch(e) {
        console.error("Residuals chart error:", e);
    }
}

function updateResidualsChartData(resTable, ts) {
    if (!residualsChart) {
        initResidualsChart();
    }
    if (!resTable) return;

    const tVal = (typeof ts === 'number') ? ts : (residualBuffer.length * 0.1);
    const timeLabel = `t=${tVal.toFixed(1)}s`;

    const chtRes = (resTable.avg_cht && resTable.avg_cht.residual !== undefined) ? parseFloat(resTable.avg_cht.residual) : 0.0;
    const oilPRes = (resTable.oil_press && resTable.oil_press.residual !== undefined) ? parseFloat(resTable.oil_press.residual) : 0.0;
    const egtRes = (resTable.avg_egt && resTable.avg_egt.residual !== undefined) ? parseFloat(resTable.avg_egt.residual) : 0.0;
    const oilTRes = (resTable.oil_temp && resTable.oil_temp.residual !== undefined) ? parseFloat(resTable.oil_temp.residual) : 0.0;
    const powRes = (resTable.power_kw && resTable.power_kw.residual !== undefined) ? parseFloat(resTable.power_kw.residual) : 0.0;

    residualBuffer.push({
        timeLabel: timeLabel,
        timestamp: tVal,
        cht: chtRes,
        oilP: oilPRes,
        egt: egtRes,
        oilT: oilTRes,
        pow: powRes
    });

    const maxCapacity = 1200; // Store up to 120s rolling buffer (1200 samples)
    if (residualBuffer.length > maxCapacity) {
        residualBuffer.shift();
    }

    // Debug assertion requirement
    if (receivedFrameCount > 10 && residualBuffer.length === 0) {
        console.error("[REAL-TIME CHART ERROR] Received > 10 telemetry frames, but Rolling Residual Excursion Trends chart buffer has ZERO points!");
    }

    renderBufferedResidualsChart();
}

function renderBufferedResidualsChart() {
    if (!residualsChart) return;

    const pointsToShow = Math.min(residualBuffer.length, residualWindowSeconds * 10);
    const slicedBuffer = residualBuffer.slice(-pointsToShow);

    const labels = slicedBuffer.map(d => d.timeLabel);
    const chtData = slicedBuffer.map(d => ({ x: d.timeLabel, y: d.cht, rawVal: d.cht, timestamp: d.timestamp }));
    const oilPData = slicedBuffer.map(d => ({ x: d.timeLabel, y: d.oilP, rawVal: d.oilP, timestamp: d.timestamp }));
    const egtData = slicedBuffer.map(d => ({ x: d.timeLabel, y: d.egt, rawVal: d.egt, timestamp: d.timestamp }));
    const oilTData = slicedBuffer.map(d => ({ x: d.timeLabel, y: d.oilT, rawVal: d.oilT, timestamp: d.timestamp }));
    const powData = slicedBuffer.map(d => ({ x: d.timeLabel, y: d.pow, rawVal: d.pow, timestamp: d.timestamp }));

    residualsChart.data.labels = labels;
    residualsChart.data.datasets[0].data = chtData;
    residualsChart.data.datasets[1].data = oilPData;
    residualsChart.data.datasets[2].data = egtData;
    residualsChart.data.datasets[3].data = oilTData;
    residualsChart.data.datasets[4].data = powData;

    residualsChart.update('none');
}

// GCS & DFCS INTEGRATION DEMONSTRATOR SYNCHRONIZATION
let gcsEventHistory = [];
let lastGcsState = null;
let lastGcsAdvisoryLevel = null;

function updateGcsDfcsDemonstrator(frame) {
    if (!frame) return;
    const telem = frame.telemetry || frame;
    const seq = (typeof frame.sequence_number === 'number') ? frame.sequence_number : ((typeof frame.sequence_no === 'number') ? frame.sequence_no : (telem ? (telem.sequence_no ?? telem.sequence_number) : undefined)) ?? (window.twinStore ? window.twinStore.sequence_number : 0);
    const sessionId = frame.session_id || "aero_twin_session";
    const ts = telem.timestamp ?? frame.timestamp ?? 0;
    const tsStr = (typeof ts === 'number') ? `t=${ts.toFixed(1)}s` : String(ts);

    if (document.getElementById("gcs-session-id")) document.getElementById("gcs-session-id").innerText = String(sessionId).replace(/SIH\s*26054/gi, "DEMO_PROTOTYPE");
    if (document.getElementById("gcs-seq-display")) document.getElementById("gcs-seq-display").innerText = `Seq #${seq}`;
    if (document.getElementById("gcs-timestamp-display")) document.getElementById("gcs-timestamp-display").innerText = tsStr;

    try {
        const getSafeNum = (v) => (typeof v === 'number' && !isNaN(v)) ? v : (v !== null && v !== undefined && !isNaN(parseFloat(v)) ? parseFloat(v) : null);

        const subStates = frame.subsystem_states || {};
        const subHealth = frame.subsystem_health || {};
        const fc = frame.latest_forecast || frame.forecast || {};
        const ass = frame.latest_predictive_assessment || frame.predictive_assessment || null;
        const activeFaults = frame.active_faults || [];
        const sysState = frame.system_state || "NORMAL";

        const rateVal = (frame.runtime_metrics && frame.runtime_metrics.update_rate_hz && frame.runtime_metrics.update_rate_hz.mean)
            ? `${frame.runtime_metrics.update_rate_hz.mean.toFixed(1)} Hz` : "10.0 Hz";
        if (document.getElementById("gcs-rate-display")) document.getElementById("gcs-rate-display").innerText = rateVal;

        const linkStatus = document.getElementById("gcs-link-status");
        if (linkStatus) {
            if (telemetrySocket && telemetrySocket.readyState === WebSocket.OPEN) {
                linkStatus.innerHTML = `<i class="fa-solid fa-signal"></i> CONNECTED`;
                linkStatus.className = "text-green font-bold";
            } else {
                linkStatus.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> DISCONNECTED / LINK DEGRADED`;
                linkStatus.className = "text-red font-bold";
            }
        }

        // 2. Simulated Fault Injection Banner
        const faultBanner = document.getElementById("gcs-fault-banner");
        if (faultBanner) {
            if (activeFaults.length > 0) {
                faultBanner.classList.remove("hidden");
                const af = activeFaults[0];
                if (document.getElementById("gcs-fault-scenario")) document.getElementById("gcs-fault-scenario").innerText = af.fault_scenario || af.scenario || "FAULT";
                if (document.getElementById("gcs-fault-comp")) document.getElementById("gcs-fault-comp").innerText = af.affected_component || af.component || "CYLINDER_1";
                if (document.getElementById("gcs-fault-prof")) document.getElementById("gcs-fault-prof").innerText = af.injection_profile || af.profile || "GRADUAL";
                if (document.getElementById("gcs-fault-effect")) document.getElementById("gcs-fault-effect").innerText = `${Math.round(af.current_effect_pct || (af.intensity * 100) || 0)}%`;
                if (document.getElementById("gcs-fault-elapsed")) document.getElementById("gcs-fault-elapsed").innerText = `${(af.elapsed_seconds || 0).toFixed(1)}s`;
            } else {
                faultBanner.classList.add("hidden");
            }
        }

        // 3. Engine Health Overview
        const stateElem = document.getElementById("gcs-state-display");
        if (stateElem) {
            stateElem.innerText = sysState;
            stateElem.className = `badge-state ${sysState}`;
        }

        if (document.getElementById("gcs-hi-display")) {
            const hiVal = getSafeNum(frame.overall_health_index) ?? getSafeNum(frame.overall_health) ?? 98.0;
            document.getElementById("gcs-hi-display").innerText = `${hiVal.toFixed(1)}%`;
        }

        if (document.getElementById("gcs-anomaly-display")) {
            const scoreVal = getSafeNum(frame.anomaly_score) ?? 0.015;
            const label = sysState === "NORMAL" ? "Nominal" : "Excursion";
            document.getElementById("gcs-anomaly-display").innerText = `Score: ${scoreVal.toFixed(3)} (${label})`;
        }

        if (document.getElementById("gcs-risk-score-display")) {
            const riskNum = getSafeNum(ass?.degradation_score) ?? getSafeNum(ass?.degradation_index) ?? getSafeNum(ass?.risk_score);
            document.getElementById("gcs-risk-score-display").innerText = (riskNum !== null) ? `${riskNum.toFixed(2)} / 1.0` : "0.00 / 1.0";
        }

        if (document.getElementById("gcs-ttr-display")) {
            const ttrText = formatTimeToRisk(ass);
            document.getElementById("gcs-ttr-display").innerText = ttrText;
            if (document.getElementById("gcs-fc-ttr")) document.getElementById("gcs-fc-ttr").innerText = ttrText;
        }

        if (document.getElementById("gcs-scenario-display")) {
            const sc = frame.scenario;
            const scStr = (typeof sc === 'object' && sc !== null)
                ? (sc.id || sc.label || sc.name || "CRUISE")
                : (sc || frame.mission_profile || "CRUISE");
            document.getElementById("gcs-scenario-display").innerText = String(scStr).toUpperCase();
        }

        // 5-Subsystem Health
        ["thermal", "lubrication", "combustion", "mechanical", "electrical"].forEach(subKey => {
            const val = getSafeNum(subHealth[subKey]) ?? 100.0;
            const st = subStates[subKey] || (val < 70 ? "CRITICAL" : (val < 80 ? "WARNING" : (val < 90 ? "CAUTION" : "NORMAL")));
            
            const valEl = document.getElementById(`gcs-hi-${subKey}`);
            const stEl = document.getElementById(`gcs-state-${subKey}`);

            if (valEl) {
                valEl.innerText = `${Math.round(val)}%`;
                valEl.className = val < 75 ? "text-red font-bold" : (val < 85 ? "font-bold" : "text-green font-bold");
            }
            if (stEl) {
                stEl.innerText = st;
                stEl.className = `gauge-state-badge ${st}`;
            }
        });

        // 4. Dominant Predictive Trajectory Forecast Panel (Part 9)
        let dominantSub = "thermal";
        if (ass && ass.affected_subsystem && typeof ass.affected_subsystem === 'string') {
            dominantSub = ass.affected_subsystem.toLowerCase();
        } else if (subStates.lubrication && subStates.lubrication !== "NORMAL") {
            dominantSub = "lubrication";
        } else if (subStates.mechanical && subStates.mechanical !== "NORMAL") {
            dominantSub = "mechanical";
        } else if (subStates.electrical && subStates.electrical !== "NORMAL") {
            dominantSub = "electrical";
        }

        const titleEl = document.getElementById("gcs-forecast-param-title");
        const curEl = document.getElementById("gcs-fc-current");
        const f10El = document.getElementById("gcs-fc-10s");
        const f30El = document.getElementById("gcs-fc-30s");
        const f60El = document.getElementById("gcs-fc-60s");
        const envEl = document.getElementById("gcs-fc-envelope");

        const f10Dict = fc.forecast_10s || (fc.forecast && fc.forecast["10s"]) || {};
        const f30Dict = fc.forecast_30s || (fc.forecast && fc.forecast["30s"]) || {};
        const f60Dict = fc.forecast_60s || (fc.forecast && fc.forecast["60s"]) || {};
        const isFcReady = fc.status === "READY" && (fc.forecast_30s || (fc.forecast && fc.forecast["30s"]));

        if (dominantSub === "lubrication") {
            const oilP = getSafeNum(telem.oil_press) ?? 4.2;
            if (titleEl) titleEl.innerHTML = `<i class="fa-solid fa-oil-can text-orange"></i> Lubrication Trajectory (Oil Pressure)`;
            if (curEl) curEl.innerText = `${oilP.toFixed(2)} bar`;
            if (isFcReady) {
                if (f10El) f10El.innerText = `${(getSafeNum(f10Dict.oil_press ?? f10Dict.oil_pressure) ?? oilP).toFixed(2)} bar`;
                if (f30El) f30El.innerText = `${(getSafeNum(f30Dict.oil_press ?? f30Dict.oil_pressure) ?? oilP).toFixed(2)} bar`;
                if (f60El) f60El.innerText = `${(getSafeNum(f60Dict.oil_press ?? f60Dict.oil_pressure) ?? oilP).toFixed(2)} bar`;
            } else {
                if (f10El) f10El.innerText = "Warming up...";
                if (f30El) f30El.innerText = "Warming up...";
                if (f60El) f60El.innerText = "Warming up...";
            }
            if (envEl) {
                envEl.innerText = "> 2.50 bar";
                envEl.className = oilP <= 2.50 ? "text-red font-bold" : "text-green font-bold";
            }
        } else if (dominantSub === "mechanical") {
            const vib = getSafeNum(telem.vibration_rms) ?? 1.12;
            if (titleEl) titleEl.innerHTML = `<i class="fa-solid fa-wave-square text-purple"></i> Mechanical Vibration Trajectory (Vibration RMS)`;
            if (curEl) curEl.innerText = `${vib.toFixed(2)} g`;
            if (isFcReady) {
                if (f10El) f10El.innerText = `${(getSafeNum(f10Dict.vibration_rms) ?? vib).toFixed(2)} g`;
                if (f30El) f30El.innerText = `${(getSafeNum(f30Dict.vibration_rms) ?? vib).toFixed(2)} g`;
                if (f60El) f60El.innerText = `${(getSafeNum(f60Dict.vibration_rms) ?? vib).toFixed(2)} g`;
            } else {
                if (f10El) f10El.innerText = "Warming up...";
                if (f30El) f30El.innerText = "Warming up...";
                if (f60El) f60El.innerText = "Warming up...";
            }
            if (envEl) {
                envEl.innerText = "< 2.50 g";
                envEl.className = vib >= 2.50 ? "text-red font-bold" : "text-green font-bold";
            }
        } else {
            // Thermal default — active fault channel selection
            let selectedCyl = "cht1";
            let cylLabel = "Cylinder 1 CHT";

            const rawAffComp = ass?.affected_component || frame.dominant_component || "";
            const affComp = (typeof rawAffComp === 'string') ? rawAffComp.toUpperCase() : String(rawAffComp).toUpperCase();
            const activeFlts = frame.active_faults || [];
            const fltStr = JSON.stringify(activeFlts).toUpperCase();
            const diagStr = JSON.stringify(frame.predictive_diagnostics || frame.diagnostics || []).toUpperCase();

            if (affComp.includes("CYLINDER_3") || affComp.includes("CYLINDER 3") || affComp.includes("CHT3") || fltStr.includes("CYLINDER_3") || diagStr.includes("CYLINDER 3") || diagStr.includes("CHT3")) {
                selectedCyl = "cht3";
                cylLabel = "Cylinder 3 CHT";
            } else if (affComp.includes("CYLINDER_2") || affComp.includes("CYLINDER 2") || affComp.includes("CHT2") || fltStr.includes("CYLINDER_2") || diagStr.includes("CYLINDER 2") || diagStr.includes("CHT2")) {
                selectedCyl = "cht2";
                cylLabel = "Cylinder 2 CHT";
            } else if (affComp.includes("CYLINDER_4") || affComp.includes("CYLINDER 4") || affComp.includes("CHT4") || fltStr.includes("CYLINDER_4") || diagStr.includes("CYLINDER 4") || diagStr.includes("CHT4")) {
                selectedCyl = "cht4";
                cylLabel = "Cylinder 4 CHT";
            }

            const curChtVal = getSafeNum(telem[selectedCyl]) ?? 122.5;

            if (titleEl) titleEl.innerHTML = `<i class="fa-solid fa-temperature-full text-red"></i> Thermal Trajectory (${cylLabel})`;
            if (curEl) curEl.innerText = `${curChtVal.toFixed(1)} °C`;

            if (isFcReady) {
                if (f10El) f10El.innerText = `${(getSafeNum(f10Dict[selectedCyl]) ?? curChtVal).toFixed(1)} °C`;
                if (f30El) f30El.innerText = `${(getSafeNum(f30Dict[selectedCyl]) ?? curChtVal).toFixed(1)} °C`;
                if (f60El) f60El.innerText = `${(getSafeNum(f60Dict[selectedCyl]) ?? curChtVal).toFixed(1)} °C`;
            } else {
                if (f10El) f10El.innerText = "Warming up...";
                if (f30El) f30El.innerText = "Warming up...";
                if (f60El) f60El.innerText = "Warming up...";
            }
            if (envEl) {
                envEl.innerText = "< 145.0 °C";
                envEl.className = curChtVal >= 145.0 ? "text-red font-bold" : "text-green font-bold";
            }
        }

        // 5. DFCS ADVISORY DEMONSTRATOR & PREDICTIVE GCS ADVISORY
        // Section 11: GCS / DFCS MUST NOT CALCULATE ITS OWN STATE. Display state equals canonical system_state.
        const advisoryObj = frame.gcs_dfcs_advisory || {};
        let advisoryLevel = sysState; // Strictly system_state: NORMAL, WATCH, CAUTION, WARNING, CRITICAL

        let prototypeDemand = "NOMINAL";
        let advisoryTitle = "Nominal System Monitoring";
        let advisoryReason = "All monitored propulsion parameters are within nominal reference envelopes.";
        let operatorAction = "Maintain standard flight profile.";

        const rawAffSub = ass?.affected_subsystem || advisoryObj.dominant_subsystem || (frame.active_faults?.[0]?.subsystem) || "NONE";
        const rawAffComp = ass?.affected_component || advisoryObj.dominant_component || (frame.active_faults?.[0]?.affected_component) || "NONE";
        const affSub = String(rawAffSub);
        const affComp = String(rawAffComp);
        const compStr = (affComp !== "NONE" && affSub !== "NONE") ? `${affSub} (${affComp})` : (affSub !== "NONE" ? affSub : "");

        if (sysState === "CRITICAL") {
            prototypeDemand = "MINIMUM SAFE / EMERGENCY";
            advisoryTitle = "Critical Propulsion Advisory";
            advisoryReason = compStr ? `Confirmed safety-envelope violation or critical subsystem condition detected in ${compStr}.` : "Confirmed safety-envelope violation or critical subsystem condition detected.";
            operatorAction = "Reduce propulsion demand where operationally appropriate and perform immediate operator/engineering assessment.";
        } else if (sysState === "WARNING") {
            prototypeDemand = "REDUCED";
            advisoryTitle = "Reduced Demand Advisory";
            advisoryReason = compStr ? `Significant propulsion degradation detected in ${compStr}.` : "Significant propulsion degradation detected.";
            operatorAction = "Reduce propulsion demand where operationally appropriate and perform operator assessment.";
        } else if (sysState === "CAUTION") {
            prototypeDemand = "CONSERVATIVE";
            advisoryTitle = "Operational Caution Advisory";
            advisoryReason = compStr ? `Persistent degradation evidence detected in ${compStr}.` : "Persistent degradation evidence detected.";
            operatorAction = "Prepare for flight envelope adjustment if trend continues.";
        } else if (sysState === "WATCH") {
            prototypeDemand = "MONITOR";
            advisoryTitle = "Enhanced Monitoring Advisory";
            advisoryReason = compStr ? `Early diagnostic evidence detected in ${compStr}. Continue enhanced monitoring.` : "Early diagnostic evidence detected. Continue enhanced monitoring.";
            operatorAction = "Monitor trend indicators.";
        } else {
            prototypeDemand = "NOMINAL";
            advisoryTitle = "Nominal System Monitoring";
            advisoryReason = "All monitored propulsion parameters are within nominal reference envelopes.";
            operatorAction = "Maintain standard flight profile.";
        }

        if (advisoryObj.title && advisoryObj.level === sysState) {
            advisoryTitle = advisoryObj.title;
        }
        if (advisoryObj.description && advisoryObj.level === sysState) {
            advisoryReason = advisoryObj.description;
        }
        if (advisoryObj.operator_action && advisoryObj.level === sysState) {
            operatorAction = advisoryObj.operator_action;
        }
        if (advisoryObj.demand_recommendation && advisoryObj.level === sysState) {
            prototypeDemand = advisoryObj.demand_recommendation;
        }

        let conditionType = sysState === "NORMAL" ? "NOMINAL BASELINE" : `STATE: ${sysState}`;
        let condBg = sysState === "CRITICAL" ? "#fee2e2" : (sysState === "WARNING" ? "#ffedd5" : (sysState === "CAUTION" ? "#fef3c7" : (sysState === "WATCH" ? "#dbeafe" : "#d1fae5")));
        let condColor = sysState === "CRITICAL" ? "#dc2626" : (sysState === "WARNING" ? "#ea580c" : (sysState === "CAUTION" ? "#d97706" : (sysState === "WATCH" ? "#2563eb" : "#059669")));

        // Update DFCS UI Elements
        const dfcsBadge = document.getElementById("dfcs-advisory-badge");
        if (dfcsBadge) {
            dfcsBadge.innerText = advisoryTitle.toUpperCase();
            dfcsBadge.className = `gauge-state-badge ${advisoryLevel}`;
        }

        const dfcsCard = document.getElementById("dfcs-card-panel");
        const dfcsBox = document.getElementById("dfcs-advisory-box");
        if (dfcsCard && dfcsBox) {
            if (advisoryLevel === "CRITICAL") {
                dfcsCard.style.borderLeftColor = "#dc2626";
                dfcsBox.style.borderLeftColor = "#dc2626";
                dfcsBox.style.background = "#fff5f5";
            } else if (advisoryLevel === "WARNING") {
                dfcsCard.style.borderLeftColor = "#ea580c";
                dfcsBox.style.borderLeftColor = "#ea580c";
                dfcsBox.style.background = "#fffdf5";
            } else if (advisoryLevel === "CAUTION") {
                dfcsCard.style.borderLeftColor = "#d97706";
                dfcsBox.style.borderLeftColor = "#d97706";
                dfcsBox.style.background = "#fffdf5";
            } else if (advisoryLevel === "WATCH") {
                dfcsCard.style.borderLeftColor = "#2563eb";
                dfcsBox.style.borderLeftColor = "#2563eb";
                dfcsBox.style.background = "#eff6ff";
            } else {
                dfcsCard.style.borderLeftColor = "#059669";
                dfcsBox.style.borderLeftColor = "#059669";
                dfcsBox.style.background = "#f0fdf4";
            }
        }

        const titleElem = document.getElementById("dfcs-advisory-title");
        if (titleElem) titleElem.innerHTML = `<i class="fa-solid fa-sliders"></i> ${advisoryTitle}`;

        const condElem = document.getElementById("dfcs-condition-type");
        if (condElem) {
            condElem.innerText = conditionType;
            condElem.style.background = condBg;
            condElem.style.color = condColor;
        }

        if (document.getElementById("dfcs-curr-state")) {
            const stEl = document.getElementById("dfcs-curr-state");
            stEl.innerText = sysState;
            stEl.className = `badge-state ${sysState}`;
        }

        if (document.getElementById("dfcs-demand-level")) {
            const demEl = document.getElementById("dfcs-demand-level");
            demEl.innerText = prototypeDemand;
            demEl.style.color = (advisoryLevel === "CRITICAL" || advisoryLevel === "WARNING") ? (advisoryLevel === "CRITICAL" ? "#dc2626" : "#ea580c") : (advisoryLevel === "CAUTION" ? "#d97706" : (advisoryLevel === "WATCH" ? "#2563eb" : "#059669"));
        }

        if (document.getElementById("dfcs-reason-text")) {
            document.getElementById("dfcs-reason-text").innerText = advisoryReason;
        }

        if (document.getElementById("dfcs-action-text")) {
            document.getElementById("dfcs-action-text").innerText = operatorAction;
        }

        // 6. Live Advisory & Event History Log (Part 13)
        if (lastGcsState !== sysState || lastGcsAdvisoryLevel !== advisoryLevel) {
            lastGcsState = sysState;
            lastGcsAdvisoryLevel = advisoryLevel;

            gcsEventHistory.unshift({
                timestamp: tsStr,
                state: sysState,
                level: advisoryLevel,
                title: advisoryTitle,
                reason: advisoryReason
            });

            if (gcsEventHistory.length > 20) gcsEventHistory.pop();

            renderGcsEventHistory();
        }
    } catch(err) {
        console.error("Error in updateGcsDfcsDemonstrator:", err);
    }
}

function renderGcsEventHistory() {
    const tbody = document.getElementById("gcs-event-history-body");
    if (!tbody) return;

    if (gcsEventHistory.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No state transitions recorded. Operating in nominal baseline.</td></tr>`;
        return;
    }

    tbody.innerHTML = gcsEventHistory.map(item => `
        <tr>
            <td><code>${item.timestamp}</code></td>
            <td><span class="badge-state ${item.state}">${item.state}</span></td>
            <td><span class="gauge-state-badge ${item.level}">${item.level}</span></td>
            <td><strong>${item.title}:</strong> <span style="color:#475569;">${item.reason}</span></td>
        </tr>
    `).join("");
}

// COMPOUND FAULT CONFIRMATION MODAL & MULTI-FAULT UI LOGIC
let pendingFaultRequestPayload = null;

function initCompoundFaultModal() {
    const btnCancel = document.getElementById("btn-cancel-compound-fault");
    const btnConfirm = document.getElementById("btn-confirm-compound-fault");
    const modal = document.getElementById("compound-fault-modal");

    if (btnCancel) {
        btnCancel.addEventListener("click", () => {
            if (modal) modal.classList.add("hidden");
            pendingFaultRequestPayload = null;
        });
    }

    if (btnConfirm) {
        btnConfirm.addEventListener("click", async () => {
            if (modal) modal.classList.add("hidden");
            if (pendingFaultRequestPayload) {
                await executeFaultInjection(pendingFaultRequestPayload);
                pendingFaultRequestPayload = null;
            }
        });
    }
}

async function executeFaultInjection(payload) {
    try {
        const res = await fetch(`${API_BASE}/api/fault-injection/start`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${authToken}`
            },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            console.log("Fault injection started successfully:", payload);
        } else {
            console.error("Failed to start fault injection:", res.status);
        }
    } catch (e) {
        console.error("Fault injection network error:", e);
    }
}

function triggerFaultInjectionWithSafetyCheck(payload) {
    const activeCount = (window.lastTwinFrame && window.lastTwinFrame.active_faults) ? window.lastTwinFrame.active_faults.length : 0;
    if (activeCount > 0) {
        pendingFaultRequestPayload = payload;
        const modal = document.getElementById("compound-fault-modal");
        if (modal) modal.classList.remove("hidden");
    } else {
        executeFaultInjection(payload);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    initCompoundFaultModal();
});

