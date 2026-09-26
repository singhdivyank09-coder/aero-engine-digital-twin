import sqlite3
import os
import json
import time
from datetime import datetime
try:
    from backend.auth import get_password_hash
except ImportError:
    from auth import get_password_hash

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "telemetry_db.sqlite"))

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    if os.path.exists(DB_PATH):
        size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
        print(f"[DATABASE INIT] Telemetry database path: {DB_PATH} (Current size: {size_mb:.2f} MB)")
        if size_mb > 250.0:
            print(f"[DATABASE WARNING] Database size ({size_mb:.2f} MB) exceeds prototype threshold (250 MB).")

    # 1. Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        full_name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Telemetry logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        sequence_no INTEGER NOT NULL,
        rpm REAL,
        cht1 REAL, cht2 REAL, cht3 REAL, cht4 REAL,
        egt1 REAL, egt2 REAL, egt3 REAL, egt4 REAL,
        oil_press REAL,
        oil_temp REAL,
        fuel_flow REAL,
        vibration_rms REAL,
        battery_volt REAL,
        manifold_press REAL,
        anomaly_score REAL,
        health_index REAL,
        active_faults TEXT
    );
    """)

    # 3. Fault alerts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fault_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        severity TEXT NOT NULL,
        subsystem TEXT NOT NULL,
        fault_type TEXT NOT NULL,
        description TEXT NOT NULL,
        status TEXT DEFAULT 'Active',
        acknowledged_by TEXT
    );
    """)

    # 4. Audit logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        username TEXT NOT NULL,
        role TEXT DEFAULT 'operator',
        action TEXT NOT NULL,
        details TEXT
    );
    """)

    # Migration check for role column if table existed without role
    cursor.execute("PRAGMA table_info(audit_logs);")
    columns = [col[1] for col in cursor.fetchall()]
    if "role" not in columns:
        cursor.execute("ALTER TABLE audit_logs ADD COLUMN role TEXT DEFAULT 'operator';")
    conn.commit()

    # 5. Maintenance Records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS maintenance_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        engineer_name TEXT NOT NULL,
        component TEXT NOT NULL,
        action_taken TEXT NOT NULL,
        notes TEXT
    );
    """)

    # 6. Missions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS missions (
        mission_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT,
        duration REAL DEFAULT 0.0,
        telemetry_source TEXT DEFAULT 'SIMULATOR',
        analytics_dataset TEXT DEFAULT 'CMAPSS',
        initial_scenario TEXT DEFAULT 'CRUISE',
        final_state TEXT DEFAULT 'NORMAL',
        min_health REAL DEFAULT 100.0,
        max_anomaly REAL DEFAULT 0.0,
        rul_start REAL,
        rul_end REAL,
        frame_count INTEGER DEFAULT 0,
        summary_json TEXT
    );
    """)

    # 7. Mission Snapshots table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mission_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mission_id TEXT NOT NULL,
        sequence_number INTEGER NOT NULL,
        twin_timestamp REAL NOT NULL,
        snapshot_json TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
    );
    """)

    # 8. Mission Events table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mission_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL,
        mission_id TEXT NOT NULL,
        sequence_number INTEGER NOT NULL,
        twin_timestamp REAL NOT NULL,
        event_type TEXT NOT NULL,
        subsystem TEXT,
        component TEXT,
        event_json TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
    );
    """)

    # Seed or Update Users
    env = os.getenv("ENVIRONMENT", "").lower()
    is_render = os.getenv("RENDER", "").lower() == "true"
    is_prod = env in ["production", "prod"] or is_render

    op_user = os.getenv("DEMO_OPERATOR_USERNAME", "operator")
    op_password = os.getenv("DEMO_OPERATOR_PASSWORD")
    eng_user = os.getenv("DEMO_ENGINEER_USERNAME", "engineer")
    eng_password = os.getenv("DEMO_ENGINEER_PASSWORD")

    if is_prod:
        if not op_password or op_password == "operator123":
            raise RuntimeError("CRITICAL SECURITY FAILURE: DEMO_OPERATOR_PASSWORD environment variable must be explicitly configured in production!")
        if not eng_password or eng_password == "engineer123":
            raise RuntimeError("CRITICAL SECURITY FAILURE: DEMO_ENGINEER_PASSWORD environment variable must be explicitly configured in production!")

    op_password = op_password or "operator123"
    eng_password = eng_password or "engineer123"

    op_pass_hash = get_password_hash(op_password, op_user)
    eng_pass_hash = get_password_hash(eng_password, eng_user)

    cursor.execute("SELECT * FROM users WHERE username = ?;", (op_user,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?);",
                       (op_user, op_pass_hash, "operator", "UAV Flight Operator"))
    else:
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?;", (op_pass_hash, op_user))

    cursor.execute("SELECT * FROM users WHERE username = ?;", (eng_user,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?);",
                       (eng_user, eng_pass_hash, "engineer", "Demo Prototype Engineer"))
    else:
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?;", (eng_pass_hash, eng_user))

    cursor.execute("UPDATE users SET full_name = 'Demo Prototype Operator' WHERE full_name LIKE '%DRDO%' OR full_name LIKE '%Propulsion Engineer%';")
    conn.commit()
    conn.close()

    # Enforce retention on startup
    enforce_mission_retention(max_retained=5)

def enforce_mission_retention(max_retained: int = 5, conn=None):
    """
    Retains at most `max_retained` missions (active recording + 4 most recent completed missions).
    Removes older completed missions and their associated snapshots/events inside an atomic SQLite transaction.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT mission_id FROM missions ORDER BY start_time DESC;")
        rows = cursor.fetchall()
        mission_ids = [r["mission_id"] for r in rows]

        if len(mission_ids) > max_retained:
            to_delete = mission_ids[max_retained:]
            placeholders = ",".join(["?"] * len(to_delete))

            cursor.execute("BEGIN TRANSACTION;")
            cursor.execute(f"DELETE FROM mission_snapshots WHERE mission_id IN ({placeholders});", to_delete)
            cursor.execute(f"DELETE FROM mission_events WHERE mission_id IN ({placeholders});", to_delete)
            cursor.execute(f"DELETE FROM missions WHERE mission_id IN ({placeholders});", to_delete)
            conn.commit()
            print(f"[MISSION RETENTION] Purged {len(to_delete)} older mission recordings. Retained top {max_retained} missions.")
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        print(f"[MISSION RETENTION ERROR] {e}")
    finally:
        if should_close and conn:
            conn.close()

def log_telemetry_data(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO telemetry_logs (
            timestamp, sequence_no, rpm, cht1, cht2, cht3, cht4,
            egt1, egt2, egt3, egt4, oil_press, oil_temp, fuel_flow,
            vibration_rms, battery_volt, manifold_press, anomaly_score, health_index, active_faults
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("timestamp"), data.get("sequence_no"), data.get("rpm"),
        data.get("cht1"), data.get("cht2"), data.get("cht3"), data.get("cht4"),
        data.get("egt1"), data.get("egt2"), data.get("egt3"), data.get("egt4"),
        data.get("oil_press"), data.get("oil_temp"), data.get("fuel_flow"),
        data.get("vibration_rms"), data.get("battery_volt"), data.get("manifold_press"),
        data.get("anomaly_score"), data.get("health_index"), json.dumps(data.get("active_faults", []))
    ))
    conn.commit()
    conn.close()

def create_fault_alert(severity, subsystem, fault_type, description):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO fault_alerts (timestamp, severity, subsystem, fault_type, description)
        VALUES (?, ?, ?, ?, ?)
    """, (now, severity, subsystem, fault_type, description))
    conn.commit()
    conn.close()

def log_audit_event(username, action, details="", role="operator"):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO audit_logs (timestamp, username, role, action, details)
        VALUES (?, ?, ?, ?, ?)
    """, (now, username, role, action, details))
    conn.commit()
    conn.close()

def get_recent_audit_logs(limit=50):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?;", (limit,))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        row_dict = dict(r)
        row_dict["user"] = row_dict.get("username", "unknown")
        if "role" not in row_dict or not row_dict["role"]:
            row_dict["role"] = "operator"
        result.append(row_dict)
    return result

def save_telemetry_snapshot(data):
    log_telemetry_data(data)

def save_mission_record(mission_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO missions (
            mission_id, session_id, start_time, end_time, duration,
            telemetry_source, analytics_dataset, initial_scenario, final_state,
            min_health, max_anomaly, rul_start, rul_end, frame_count, summary_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        mission_dict.get("mission_id"),
        mission_dict.get("session_id", "TWIN_SESSION_SIH26054"),
        mission_dict.get("start_time", datetime.now().isoformat()),
        mission_dict.get("end_time"),
        mission_dict.get("duration", 0.0),
        mission_dict.get("telemetry_source", "SIMULATOR"),
        mission_dict.get("analytics_dataset", "CMAPSS"),
        mission_dict.get("initial_scenario", "CRUISE"),
        mission_dict.get("final_state", "NORMAL"),
        mission_dict.get("min_health", 100.0),
        mission_dict.get("max_anomaly", 0.0),
        mission_dict.get("rul_start"),
        mission_dict.get("rul_end"),
        mission_dict.get("frame_count", 0),
        json.dumps(mission_dict.get("summary_json", {}))
    ))
    conn.commit()
    conn.close()
    enforce_mission_retention(max_retained=5)

def save_mission_snapshot_record(mission_id, seq, ts, snapshot_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO mission_snapshots (mission_id, sequence_number, twin_timestamp, snapshot_json)
        VALUES (?, ?, ?, ?)
    """, (mission_id, seq, ts, json.dumps(snapshot_dict)))
    conn.commit()
    conn.close()

def save_mission_event_record(mission_id, event_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO mission_events (event_id, mission_id, sequence_number, twin_timestamp, event_type, subsystem, component, event_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        event_dict.get("event_id", f"EVT_{int(time.time())}"),
        mission_id,
        event_dict.get("sequence_number", 0),
        event_dict.get("twin_timestamp", 0.0),
        event_dict.get("event_type", "GENERIC"),
        event_dict.get("subsystem", "GLOBAL_SYSTEM"),
        event_dict.get("component", "ENGINE"),
        json.dumps(event_dict)
    ))
    conn.commit()
    conn.close()

def db_get_all_missions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM missions ORDER BY start_time DESC;")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_mission(mission_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM missions WHERE mission_id = ?;", (mission_id,))
    mission_row = cursor.fetchone()
    if not mission_row:
        conn.close()
        return None
    mission_dict = dict(mission_row)
    
    cursor.execute("SELECT * FROM mission_snapshots WHERE mission_id = ? ORDER BY sequence_number ASC;", (mission_id,))
    snapshots_rows = cursor.fetchall()
    
    cursor.execute("SELECT * FROM mission_events WHERE mission_id = ? ORDER BY sequence_number ASC;", (mission_id,))
    events_rows = cursor.fetchall()
    conn.close()
    
    snapshots = [json.loads(r["snapshot_json"]) for r in snapshots_rows]
    events = [json.loads(r["event_json"]) for r in events_rows]
    
    mission_dict["snapshots"] = snapshots
    mission_dict["events"] = events
    if mission_dict.get("summary_json"):
        try:
            mission_dict["summary"] = json.loads(mission_dict["summary_json"])
        except Exception:
            mission_dict["summary"] = {}
    return mission_dict


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")

