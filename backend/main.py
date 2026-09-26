"""
FastAPI Aero Engine Digital Twin Server
Provides REST APIs, JWT authentication, RBAC, SQLite audit logging,
and 10Hz WebSockets real-time streaming pipeline.
"""

import os
import sys
import json
import asyncio
import time
import numpy as np
from typing import Dict, Any, List, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.auth import authenticate_user, create_access_token, verify_token
from backend.database import init_db, log_audit_event, get_recent_audit_logs, save_telemetry_snapshot
from backend.telemetry_simulator import simulator_instance
from backend.digital_twin_core import digital_twin_core_instance
from backend.fault_registry import FAULT_REGISTRY, get_valid_components, is_valid_fault_component, get_fault_spec, resolve_fault_id

# Initialize database
init_db()


app = FastAPI(
    title="MALE UAV Aero Engine Digital Twin — Demo Prototype",
    description="Real-Time Digital Twin, PyTorch Autoencoder Anomaly Detection, XGBoost Fault Diagnosis, and LSTM RUL Prognostics Server",
    version="2.0.0"
)

# Enable CORS with configurable allowed origins
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "https://aero-engine-digital-twin.onrender.com")
env_mode = os.getenv("ENVIRONMENT", "").lower()
is_render_mode = os.getenv("RENDER", "").lower() == "true"
is_prod_mode = env_mode in ["production", "prod"] or is_render_mode

if is_prod_mode and (not allowed_origins_env or allowed_origins_env == "*"):
    render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "aero-engine-digital-twin.onrender.com")
    allowed_origins_env = f"https://{render_host}"

origins = [o.strip() for o in allowed_origins_env.split(",")] if allowed_origins_env != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Frontend Static Assets (Data directory is NOT mounted publicly for security)
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

import urllib.request
import urllib.parse
from collections import defaultdict

# Cloudflare Turnstile CAPTCHA & Rate Limiting Configuration
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
used_captcha_tokens: Dict[str, float] = {}
rate_limit_tracker: Dict[str, List[float]] = defaultdict(list)
MAX_DEMO_WS_CONNECTIONS = int(os.getenv("MAX_DEMO_WS_CONNECTIONS", "20"))

def get_client_ip(request: Request) -> str:
    """Extracts visitor client IP address, trusting proxy headers when deployed behind hosting proxy or provided in dev/test."""
    env = os.getenv("ENVIRONMENT", "").lower()
    is_render = os.getenv("RENDER", "").lower() == "true"
    trusted_proxy = is_render or env in ["production", "prod"] or os.getenv("TRUST_PROXY", "").lower() in ["true", "1"]

    if trusted_proxy:
        # CF-Connecting-IP is set authoritatively by Cloudflare edge proxy
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            return cf_ip.strip()

        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    else:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

def check_rate_limit(key: str, limit: int = 15, window_sec: int = 60):
    """Enforces rate-limits keyed by visitor client IP address."""
    now = time.time()
    # Cleanup stale entries
    stale_keys = [k for k, timestamps in rate_limit_tracker.items() if not timestamps or (now - max(timestamps) > window_sec * 2)]
    for sk in stale_keys:
        del rate_limit_tracker[sk]

    timestamps = [t for t in rate_limit_tracker[key] if now - t < window_sec]
    rate_limit_tracker[key] = timestamps
    if len(timestamps) >= limit:
        raise HTTPException(status_code=429, detail="Too many login attempts from your IP. Please wait a minute before retrying.")
    rate_limit_tracker[key].append(now)

def verify_turnstile_captcha(token: str, client_ip: str = "", expected_action: str = "demo_login") -> bool:
    """Verifies Turnstile CAPTCHA token, requiring success, action, and target hostname matching configured domain."""
    if not token or not isinstance(token, str):
        return False

    now = time.time()
    # Reject replayed tokens
    if token in used_captcha_tokens:
        if now - used_captcha_tokens[token] < 300:
            return False

    # Clean expired cached tokens
    expired = [t for t, ts in used_captcha_tokens.items() if now - ts >= 300]
    for t in expired:
        del used_captcha_tokens[t]

    env = os.getenv("ENVIRONMENT", "").lower()
    is_render = os.getenv("RENDER", "").lower() == "true"
    is_prod = env in ["production", "prod"] or is_render

    secret_key = os.getenv("TURNSTILE_SECRET_KEY", TURNSTILE_SECRET_KEY)

    if is_prod and not secret_key:
        print("[CAPTCHA ERROR] Production mode requires TURNSTILE_SECRET_KEY!")
        return False

    # Safe test bypass ONLY when not in production and TURNSTILE_SECRET_KEY is 'test'/'dummy' or unconfigured in dev
    if not is_prod and (not secret_key or secret_key in ["test", "dummy"]):
        if token.startswith("test_") or token in ["valid_captcha_token", "test_captcha_token"]:
            used_captcha_tokens[token] = now
            return True

    if not secret_key:
        return False

    try:
        url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
        params = {"secret": secret_key, "response": token}
        if client_ip:
            params["remoteip"] = client_ip

        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        success = result.get("success", False)
        if not success:
            print(f"[CAPTCHA FAILED] Result: {result}")
            return False

        resp_action = result.get("action", "")
        resp_hostname = result.get("hostname", "")

        # In production, require BOTH action and hostname to be present
        if is_prod:
            if not resp_action:
                print("[CAPTCHA FAILED] Missing 'action' field in production response")
                return False
            if not resp_hostname:
                print("[CAPTCHA FAILED] Missing 'hostname' field in production response")
                return False

        # 1. Action verification
        if expected_action:
            if resp_action != expected_action:
                if is_prod or resp_action:
                    print(f"[CAPTCHA ACTION MISMATCH] Expected '{expected_action}', got '{resp_action}'")
                    return False

        # 2. Hostname verification strictly against configured domains (never arbitrary request headers)
        allowed_hosts = set()
        render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "aero-engine-digital-twin.onrender.com")
        if render_host:
            allowed_hosts.add(render_host.lower())

        allowed_env = os.getenv("ALLOWED_ORIGINS", "")
        for o in allowed_env.split(","):
            o_clean = o.strip().replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
            if o_clean and o_clean != "*":
                allowed_hosts.add(o_clean.lower())

        if not is_prod:
            allowed_hosts.update(["127.0.0.1", "localhost", "test", "testserver"])

        if resp_hostname:
            if resp_hostname.lower() not in allowed_hosts:
                print(f"[CAPTCHA HOSTNAME MISMATCH] '{resp_hostname}' not in configured allowed hosts {allowed_hosts}")
                return False

        used_captcha_tokens[token] = now
        return True
    except Exception as e:
        print(f"[CAPTCHA EXCEPTION] {e}")
        return False

# Pydantic Schemas
class LoginRequest(BaseModel):
    username: str
    password: str

class DemoLoginRequest(BaseModel):
    captcha_token: str

class MissionProfileRequest(BaseModel):
    profile: str

class FaultInjectionRequest(BaseModel):
    fault_type: str

class DatasetModeRequest(BaseModel):
    mode: str  # e.g., "NOMINAL_CRUISE", "DATASET_CMAPSS_1", "DATASET_CMAPSS_2"

class AuditLogRequest(BaseModel):
    action: str
    details: Optional[str] = ""


# REST Endpoints
@app.get("/")
def get_root():
    """Serves main GCS HMI index.html"""
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/api/health")
def get_health():
    return {"status": "ok", "system": "Aero Engine Digital Twin Orchestrator v2.0"}

@app.get("/api/auth/captcha-config")
def get_captcha_config():
    return {
        "site_key": TURNSTILE_SITE_KEY,
        "captcha_required": True
    }

@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request):
    client_ip = get_client_ip(request)
    check_rate_limit(f"login:{client_ip}", limit=15, window_sec=60)
    user = authenticate_user(req.username, req.password)
    if not user:
        log_audit_event(req.username or "unknown", "failed login", f"Failed login attempt for username '{req.username}' from IP {client_ip}", role="guest")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": user["username"], "role": user["role"], "full_name": user["full_name"]})
    log_audit_event(user["username"], "login", f"User logged in with role {user['role']}", role=user["role"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user["role"],
        "full_name": user["full_name"]
    }

@app.post("/api/auth/demo-login")
def demo_login(req: DemoLoginRequest, request: Request):
    client_ip = get_client_ip(request)
    check_rate_limit(f"demo:{client_ip}", limit=10, window_sec=60)
    if not verify_turnstile_captcha(req.captcha_token, client_ip=client_ip, expected_action="demo_login"):
        raise HTTPException(status_code=400, detail="CAPTCHA verification failed. Please complete the security check.")

    demo_id = f"demo_visitor_{int(time.time() * 1000) % 100000}"
    token = create_access_token(
        data={"sub": demo_id, "role": "demo", "full_name": "Public Demo Visitor"},
        expires_minutes=60
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": demo_id,
        "role": "demo",
        "full_name": "Public Demo Visitor"
    }

@app.get("/api/debug/session")
def get_debug_session(authorization: Optional[str] = Header(None)):
    """Development diagnostic endpoint exposing authoritative single active TwinSession state."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required to view diagnostic debug session")


    global latest_canonical_snapshot
    if latest_canonical_snapshot is None:
        compute_canonical_tick()
    processed_twin = latest_canonical_snapshot
    sc = processed_twin.get("scenario", "CRUISE")
    scenario_name = sc.get("id", "CRUISE") if isinstance(sc, dict) else str(sc)
    return {
        "session_id": processed_twin.get("session_id", "TWIN_SESSION_SIH26054"),
        "sequence_number": processed_twin.get("sequence_number", 0),
        "scenario": scenario_name,
        "scenario_parameters": processed_twin.get("scenario_parameters", {}),
        "active_faults": processed_twin.get("active_faults", []),
        "subsystem_evidence": processed_twin.get("subsystem_evidence", {}),
        "dominant_subsystem": processed_twin.get("dominant_subsystem", "THERMAL"),
        "dominant_component": processed_twin.get("dominant_component", "Cylinder 1"),
        "secondary_degradations": processed_twin.get("secondary_degradations", []),
        "injected_faults": processed_twin.get("injected_faults", []),
        "detected_conditions": processed_twin.get("detected_conditions", []),
        "fault_event_log": simulator_instance.fault_event_log,
        "telemetry_history_length": len(digital_twin_core_instance.history_window_full),
        "forecast_history_length": len(digital_twin_core_instance.forecast_history),
        "gru_status": processed_twin.get("gru_status", processed_twin.get("forecast", {}).get("status", "WARMING_UP")),
        "state": processed_twin.get("system_state", "NORMAL"),
        "predictive_assessment": processed_twin.get("predictive_assessment", {}),
        "forecast": processed_twin.get("forecast", {}),
        "latest_telemetry": processed_twin.get("telemetry", {})
    }

@app.get("/api/telemetry/latest")
def get_latest_telemetry(authorization: Optional[str] = Header(None)):
    """Returns single frame of synchronized Digital Twin analysis."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    global latest_canonical_snapshot
    if latest_canonical_snapshot is None:
        compute_canonical_tick()
    return latest_canonical_snapshot

@app.post("/api/mission/set-profile")
@app.post("/api/session/scenario")
def set_mission_profile(req: MissionProfileRequest, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required to change scenario profile")

    simulator_instance.set_mission_profile(req.profile)
    log_audit_event(payload["sub"], "scenario changed", f"Changed mission scenario profile to {req.profile}", role=payload.get("role", "engineer"))
    return {
        "status": "success",
        "profile": req.profile,
        "session_id": "TWIN_SESSION_SIH26054",
        "scenario": req.profile
    }

@app.get("/api/faults/registry")
def get_fault_registry_endpoint():
    """Returns single authoritative fault registry."""
    return FAULT_REGISTRY

@app.get("/api/faults/{fault_id}/components")
def get_fault_components_endpoint(fault_id: str):
    """Returns valid component list for requested fault scenario."""
    comps = get_valid_components(fault_id)
    spec = get_fault_spec(fault_id)
    return {
        "fault_id": fault_id,
        "resolved_fault_id": resolve_fault_id(fault_id),
        "subsystem": spec.get("subsystem", "GENERAL") if spec else "GENERAL",
        "valid_components": [c["id"] for c in comps],
        "components": comps
    }

class StartFaultRequest(BaseModel):
    scenario: str
    component: Optional[str] = "CYLINDER_1"
    profile: Optional[str] = "GRADUAL"
    intensity: Optional[float] = 1.0
    rate: Optional[str] = "MODERATE"

@app.post("/api/fault-injection/start")
@app.post("/api/session/fault/start")
def start_fault_injection(req: StartFaultRequest, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required for fault injection")

    comp = req.component or "CYLINDER_1"
    if not is_valid_fault_component(req.scenario, comp):
        return JSONResponse(
            status_code=422,
            content={
                "error": "INVALID_FAULT_COMPONENT_PAIR",
                "fault": req.scenario,
                "component": comp,
                "detail": f"Component '{comp}' is not valid for fault '{req.scenario}'."
            }
        )

    cfg = simulator_instance.start_fault_injection(
        scenario=req.scenario,
        component=comp,
        profile=req.profile or "GRADUAL",
        intensity=req.intensity if req.intensity is not None else 1.0,
        rate=req.rate or "MODERATE"
    )
    log_audit_event(payload["sub"], "fault injection started", f"Started {req.scenario} fault on {comp} ({req.profile})", role=payload.get("role", "engineer"))
    active_faults = getattr(simulator_instance, "active_faults", [cfg])
    return {
        "status": "success",
        "fault_config": cfg,
        "fault_id": cfg.get("fault_id", "FLT_ACTIVE"),
        "session_id": "TWIN_SESSION_SIH26054",
        "active_faults_count": len(active_faults),
        "active_faults": active_faults
    }


@app.post("/api/fault-injection/pause")
@app.post("/api/session/fault/pause")
def pause_fault_injection(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required to pause fault injection")

    cfg = simulator_instance.pause_fault_injection()
    log_audit_event(payload["sub"], "fault injection paused", f"Fault status changed to {cfg['status']}", role=payload.get("role", "engineer"))
    return {"status": "success", "fault_config": cfg}

@app.post("/api/fault-injection/clear")
@app.post("/api/session/fault/clear")
def clear_fault_injection(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required to clear fault injection")

    res = simulator_instance.clear_fault_injection()
    log_audit_event(payload["sub"], "fault injection cleared", "Cleared all active fault injections", role=payload.get("role", "engineer"))
    return res

@app.post("/api/fault-injection/clear/{injection_id}")
@app.post("/api/session/fault/clear/{injection_id}")
def clear_single_fault_injection(injection_id: str, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required to clear fault injection")

    res = simulator_instance.clear_fault_injection(injection_id=injection_id)
    log_audit_event(payload["sub"], "single fault injection cleared", f"Cleared active fault injection {injection_id}", role=payload.get("role", "engineer"))
    return res

@app.get("/api/fault-injection/event-log")
@app.get("/api/session/fault/event-log")
def get_fault_event_log(authorization: Optional[str] = Header(None)):
    return {
        "active_config": simulator_instance.fault_config,
        "event_log": simulator_instance.fault_event_log
    }

@app.post("/api/fault-injection/inject")
def inject_fault(req: FaultInjectionRequest, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer authorization required for fault injection")

    simulator_instance.set_fault(req.fault_type)
    log_audit_event(payload["sub"], "fault injection started", f"Injected fault scenario: {req.fault_type}", role=payload.get("role", "engineer"))
    return {"status": "success", "active_fault": req.fault_type}

class DataSourcesRequest(BaseModel):
    telemetry_source: Optional[str] = "SIMULATOR"
    analytics_dataset: Optional[str] = "CMAPSS"

@app.post("/api/telemetry/dataset-mode")
def set_dataset_mode(req: DatasetModeRequest, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required to change dataset mode")

    simulator_instance.set_mode(req.mode)
    log_audit_event(payload["sub"], "analytics dataset changed", f"Switched telemetry streaming mode to {req.mode}", role=payload.get("role", "engineer"))
    return {"status": "success", "mode": req.mode}

@app.post("/api/telemetry/data-sources")
def set_data_sources(req: DataSourcesRequest, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required to change telemetry data sources")

    if req.telemetry_source:
        simulator_instance.set_telemetry_source(req.telemetry_source)
    if req.analytics_dataset:
        simulator_instance.set_analytics_dataset(req.analytics_dataset)

    log_audit_event(payload["sub"], "analytics dataset changed", f"Set telemetry source to {req.telemetry_source} and analytics dataset to {req.analytics_dataset}", role=payload.get("role", "engineer"))
    return {
        "status": "success",
        "telemetry_source": simulator_instance.telemetry_source,
        "analytics_dataset": simulator_instance.analytics_dataset
    }

@app.post("/api/audit-logs/log")
def create_audit_log_event(req: AuditLogRequest, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    log_audit_event(
        username=payload.get("sub", "unknown"),
        action=req.action,
        details=req.details or "",
        role=payload.get("role", "operator")
    )
    return {"status": "success"}

@app.get("/api/audit-logs")
def get_audit_logs(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required to access security audit logs")

    logs = get_recent_audit_logs(limit=50)
    return {"audit_logs": logs}

@app.get("/api/ml/metrics")
def get_ml_metrics():
    import json
    metrics_path_ae = os.path.join(os.path.dirname(__file__), "..", "models", "anomaly_metrics.json")
    metrics_path_rul = os.path.join(os.path.dirname(__file__), "..", "models", "rul_metrics.json")
    
    ae_metrics = {}
    rul_metrics = {}
    
    if os.path.exists(metrics_path_ae):
        with open(metrics_path_ae, "r") as f:
            ae_metrics = json.load(f)
    if os.path.exists(metrics_path_rul):
        with open(metrics_path_rul, "r") as f:
            rul_metrics = json.load(f)

    return {
        "autoencoder": ae_metrics,
        "lstm_rul": rul_metrics,
        "technology_stack": {
            "backend": "Python 3.11 / FastAPI 0.110",
            "frontend": "HTML5 / Vanilla CSS3 / JavaScript ES6 (Light Aerospace Theme)",
            "database": "SQLite (WAL Mode)",
            "streaming": "WebSockets (10Hz Real-Time State Pipeline)"
        }
    }

from backend.mission_recorder import mission_recorder_instance
from backend.replay_service import replay_service_instance

@app.get("/api/replay/missions")
def get_replay_missions():
    """Returns list of available recorded missions."""
    return replay_service_instance.get_available_missions()

@app.get("/api/replay/mission/{mission_id}")
def get_replay_mission_by_id(mission_id: str):
    """Returns recorded mission data for specific mission_id."""
    return replay_service_instance.get_mission_data(mission_id)

@app.get("/api/replay/mission-data")
def get_replay_mission_data(mission_id: Optional[str] = None):
    """Returns historical mission dataset processed from real recorded TwinSession."""
    return replay_service_instance.get_mission_data(mission_id or "latest")

@app.get("/api/replay/report")
def get_replay_report(mission_id: Optional[str] = None):
    """Returns Prototype Mission Health Summary report for recorded mission."""
    data = replay_service_instance.get_mission_data(mission_id or "latest")
    return data["summary"]

@app.get("/api/replay/export/{mission_id}")
def get_replay_export_report(mission_id: str):
    """Returns exportable JSON mission report."""
    return replay_service_instance.get_exportable_json_report(mission_id)

@app.post("/api/replay/start-new-mission")
def start_new_mission(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = authorization.split(" ")[1]
    payload = verify_token(token)
    if not payload or payload.get("role") != "engineer":
        raise HTTPException(status_code=403, detail="Engineer permission required to start new mission recording")
        
    new_id = mission_recorder_instance.start_new_mission(
        scenario=getattr(simulator_instance, "mission_profile", "CRUISE"),
        telemetry_source=getattr(simulator_instance, "telemetry_source", "SIMULATOR"),
        analytics_dataset=getattr(simulator_instance, "analytics_dataset", "CMAPSS")
    )
    return {"status": "success", "mission_id": new_id}

from backend.metrics_tracker import metrics_tracker_instance
from backend.model_registry import ModelRegistry

@app.get("/api/system/metrics")
def get_system_runtime_metrics():
    """Returns actual measured high-resolution runtime performance & data integrity metrics."""
    return metrics_tracker_instance.get_summary()

@app.get("/api/system/model-registry")
def get_system_model_registry():
    """Returns authoritative model registry and multi-dataset provenance mapping matrix."""
    return {
        "models": ModelRegistry.get_registered_models(),
        "dataset_provenance": ModelRegistry.get_dataset_provenance()
    }


# WebSocket Connections Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.demo_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, is_demo: bool = False) -> bool:
        if is_demo and len(self.demo_connections) >= MAX_DEMO_WS_CONNECTIONS:
            await websocket.close(code=1008, reason="Maximum concurrent Demo connections reached. Please try again later.")
            return False
        await websocket.accept()
        self.active_connections.append(websocket)
        if is_demo:
            self.demo_connections.append(websocket)
        return True

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.demo_connections:
            self.demo_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
                metrics_tracker_instance.record_ws_message()
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# Single Canonical TwinSession Snapshot Store & 10Hz Producer Loop
latest_canonical_snapshot: Optional[Dict[str, Any]] = None
producer_loop_task: Optional[asyncio.Task] = None

def compute_canonical_tick() -> Dict[str, Any]:
    global latest_canonical_snapshot
    raw_frame = simulator_instance.get_next_frame()
    twin_frame = digital_twin_core_instance.process_telemetry_frame(raw_frame)
    latest_canonical_snapshot = twin_frame
    
    # Record snapshot in real time
    try:
        mission_recorder_instance.record_snapshot(twin_frame)
    except Exception as e:
        print(f"[MISSION RECORDER ERROR] {e}")
        
    return twin_frame

async def canonical_10hz_producer_loop():
    global latest_canonical_snapshot
    print(f"[TWIN_SYNC] Single-worker producer loop started. TWSESSION_OBJECT_ID={hex(id(digital_twin_core_instance))} DIGITAL_TWIN_CORE_OBJECT_ID={hex(id(digital_twin_core_instance))} TELEMETRY_SIMULATOR_OBJECT_ID={hex(id(simulator_instance))}")
    while True:
        try:
            t_gen_0 = time.perf_counter()
            twin_frame = compute_canonical_tick()
            
            t_pub_0 = time.perf_counter()
            msg_str = json.dumps(twin_frame, default=safe_json_default)
            await manager.broadcast(msg_str)
            t_pub_1 = time.perf_counter()

            seq_num = twin_frame.get("sequence_number", 0)
            if seq_num % 50 == 0 or seq_num < 5:
                telem = twin_frame.get("telemetry", {})
                sc_name = twin_frame.get("scenario_id") or twin_frame.get("mission_profile") or "CRUISE"
                print(f"[BACKEND_LATEST] seq={seq_num} time={twin_frame.get('timestamp', 0.0):.1f} state={twin_frame.get('system_state')}")
                print(f"[LIVE_FRAME_TX] seq={seq_num} time={twin_frame.get('timestamp', 0.0):.1f} state={twin_frame.get('system_state')} scenario={sc_name} cht1={telem.get('cht1', 0):.1f} cht2={telem.get('cht2', 0):.1f} cht3={telem.get('cht3', 0):.1f} cht4={telem.get('cht4', 0):.1f}")
            
            metrics_tracker_instance.record_ws_publish_latency((t_pub_1 - t_pub_0) * 1000.0)
            metrics_tracker_instance.record_end_to_end_latency((t_pub_1 - t_gen_0) * 1000.0)
        except Exception as e:
            print(f"[CANONICAL LOOP ERROR] {e}")
            import traceback
            traceback.print_exc()
        await asyncio.sleep(0.1)  # 10 Hz broadcast rate

@app.on_event("startup")
async def startup_event():
    global producer_loop_task
    print(f"[TWIN_SYNC] FastAPI Startup: TWSESSION_OBJECT_ID={hex(id(digital_twin_core_instance))} DIGITAL_TWIN_CORE_OBJECT_ID={hex(id(digital_twin_core_instance))} TELEMETRY_SIMULATOR_OBJECT_ID={hex(id(simulator_instance))}")
    compute_canonical_tick()
    producer_loop_task = asyncio.create_task(canonical_10hz_producer_loop())

def safe_json_default(obj):
    if hasattr(obj, "item"):
        return obj.item()
    if isinstance(obj, (np.integer, np.floating)):
        return float(obj)
    return str(obj)

@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket, token: Optional[str] = None):
    query_token = token or websocket.query_params.get("token")
    if not query_token:
        await websocket.close(code=1008, reason="Authentication token required")
        return
    payload = verify_token(query_token)
    if not payload:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    is_demo = payload.get("role") == "demo"
    connected = await manager.connect(websocket, is_demo=is_demo)
    if not connected:
        return

    global latest_canonical_snapshot
    if latest_canonical_snapshot is not None:
        msg_str = json.dumps(latest_canonical_snapshot, default=safe_json_default)
        try:
            await websocket.send_text(msg_str)
            metrics_tracker_instance.record_ws_message()
        except Exception:
            pass
    try:
        while True:
            # Keep socket open and receive any incoming control messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    print("[TWIN_SYNC] Starting Uvicorn with single worker configuration (workers=1)...")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, workers=1)


