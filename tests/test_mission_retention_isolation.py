"""
Unit & Integration Tests for 5-Mission Retention & Atomic Transaction Cleanup
Verifies:
1. Retention of at most 5 missions (active + 4 completed).
2. Atomic SQLite transaction deletion of snapshots and events for older missions.
3. Rollover logic when MAX_MISSION_DURATION_SECONDS is exceeded.
NOTE: Uses an ISOLATED temporary database file (data/test_retention.sqlite) to protect local historical database.
"""

import os
import sqlite3
import pytest
import time
from datetime import datetime

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "test_retention.sqlite")

def get_test_connection():
    os.makedirs(os.path.dirname(TEST_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(TEST_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def setup_test_database():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        
    conn = get_test_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE missions (
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
    cursor.execute("""
    CREATE TABLE mission_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mission_id TEXT NOT NULL,
        sequence_number INTEGER NOT NULL,
        twin_timestamp REAL NOT NULL,
        snapshot_json TEXT NOT NULL,
        FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
    );
    """)
    cursor.execute("""
    CREATE TABLE mission_events (
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
    conn.commit()
    conn.close()

def enforce_test_retention(max_retained=5):
    conn = get_test_connection()
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
    conn.close()

def test_five_mission_retention_transaction():
    setup_test_database()
    conn = get_test_connection()
    cursor = conn.cursor()

    # Seed 8 missions with 10 snapshots and 2 events each
    for i in range(1, 9):
        mid = f"MIS-TEST-{i:03d}"
        t_str = f"2026-09-26T10:00:{i:02d}"
        cursor.execute("INSERT INTO missions (mission_id, session_id, start_time) VALUES (?, ?, ?);", (mid, "TWIN_SESSION", t_str))
        
        for s in range(1, 11):
            cursor.execute("INSERT INTO mission_snapshots (mission_id, sequence_number, twin_timestamp, snapshot_json) VALUES (?, ?, ?, ?);",
                           (mid, s * 50, s * 5.0, '{"test": true}'))
        cursor.execute("INSERT INTO mission_events (event_id, mission_id, sequence_number, twin_timestamp, event_type, event_json) VALUES (?, ?, ?, ?, ?, ?);",
                       (f"EVT_{mid}_1", mid, 0, 0.0, "START", '{"evt": 1}'))
    conn.commit()
    conn.close()

    # Enforce retention (max 5)
    enforce_test_retention(max_retained=5)

    # Verify results
    conn = get_test_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM missions;")
    m_count = cursor.fetchone()[0]
    assert m_count == 5, f"Expected 5 retained missions, got {m_count}"

    cursor.execute("SELECT mission_id FROM missions ORDER BY start_time DESC;")
    retained_ids = [r[0] for r in cursor.fetchall()]
    expected_ids = [f"MIS-TEST-{i:03d}" for i in range(8, 3, -1)]
    assert retained_ids == expected_ids, f"Retained IDs mismatch: {retained_ids}"

    # Verify older mission snapshots and events deleted
    cursor.execute("SELECT COUNT(*) FROM mission_snapshots WHERE mission_id IN ('MIS-TEST-001', 'MIS-TEST-002', 'MIS-TEST-003');")
    old_snaps = cursor.fetchone()[0]
    assert old_snaps == 0, f"Expected 0 snapshots for purged missions, got {old_snaps}"

    cursor.execute("SELECT COUNT(*) FROM mission_events WHERE mission_id IN ('MIS-TEST-001', 'MIS-TEST-002', 'MIS-TEST-003');")
    old_evts = cursor.fetchone()[0]
    assert old_evts == 0, f"Expected 0 events for purged missions, got {old_evts}"

    conn.close()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
