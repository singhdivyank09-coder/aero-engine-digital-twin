import os
import sys
import time
import json
import sqlite3
import shutil

db_dir = r"C:\Users\divya\.gemini\antigravity\scratch\aero_engine_digital_twin\data"
db_path = os.path.join(db_dir, "telemetry_db.sqlite")
wal_path = os.path.join(db_dir, "telemetry_db.sqlite-wal")
shm_path = os.path.join(db_dir, "telemetry_db.sqlite-shm")

print("==========================================================================================")
print("1. FILE SIZES AND GROWTH RATE OBSERVATION")
print("==========================================================================================")

def get_sizes():
    db_sz = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    wal_sz = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
    shm_sz = os.path.getsize(shm_path) if os.path.exists(shm_path) else 0
    return db_sz, wal_sz, shm_sz

db0, wal0, shm0 = get_sizes()
t0 = time.time()

print(f"Main DB Path:  {db_path}")
print(f"Main DB Size:  {db0} bytes ({db0 / (1024**2):.2f} MB / {db0 / (1024**3):.4f} GB)")
print(f"WAL File Path: {wal_path}")
print(f"WAL File Size: {wal0} bytes ({wal0 / (1024**2):.2f} MB)")
print(f"SHM File Path: {shm_path}")
print(f"SHM File Size: {shm_sz if 'shm_sz' in locals() else shm0} bytes ({shm0 / 1024:.2f} KB)")
print(f"Total Database Storage: {(db0 + wal0 + shm0) / (1024**2):.2f} MB / {(db0 + wal0 + shm0) / (1024**3):.4f} GB")

print("\nObserving growth rate over 10 seconds...")
time.sleep(10)
db1, wal1, shm1 = get_sizes()
t1 = time.time()
dt = t1 - t0
delta_bytes = (db1 + wal1 + shm1) - (db0 + wal0 + shm0)
rate_bytes_sec = delta_bytes / dt
rate_mb_hr = (rate_bytes_sec * 3600) / (1024**2)

print(f"Elapsed Time: {dt:.2f} s")
print(f"Growth Delta: {delta_bytes} bytes ({delta_bytes / 1024:.2f} KB)")
print(f"Growth Rate:  {rate_bytes_sec:.2f} bytes/sec ({rate_mb_hr:.2f} MB/hour)")
if delta_bytes == 0:
    print("Database is currently STATIONARY (no active writes during observation window).")

print("\n==========================================================================================")
print("2. SQLITE SCHEMA, TABLES & RECORD COUNTS")
print("==========================================================================================")

uri = f"file:{db_path}?mode=ro"
conn = sqlite3.connect(uri, uri=True)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [r[0] for r in cursor.fetchall()]
print(f"Found {len(tables)} tables: {tables}")

table_stats = []

for tbl in tables:
    cursor.execute(f"SELECT COUNT(*) FROM \"{tbl}\";")
    cnt = cursor.fetchone()[0]
    
    # Get column names
    cursor.execute(f"PRAGMA table_info(\"{tbl}\");")
    cols = [r[1] for r in cursor.fetchall()]
    
    # Get total size of payload in table if text/blob columns exist
    text_cols = []
    for c in cols:
        cursor.execute(f"SELECT typeof(\"{c}\") FROM \"{tbl}\" LIMIT 1;")
        res = cursor.fetchone()
        col_type = res[0] if res else ""
        if col_type.lower() in ["text", "blob"]:
            text_cols.append(c)
            
    total_payload_bytes = 0
    max_payload_bytes = 0
    avg_payload_bytes = 0
    
    if cnt > 0 and text_cols:
        col_sum_expr = " + ".join([f"COALESCE(length(\"{c}\"), 0)" for c in text_cols])
        cursor.execute(f"SELECT SUM({col_sum_expr}), MAX({col_sum_expr}), AVG({col_sum_expr}) FROM \"{tbl}\";")
        row = cursor.fetchone()
        total_payload_bytes = row[0] or 0
        max_payload_bytes = row[1] or 0
        avg_payload_bytes = row[2] or 0

    table_stats.append({
        "table": tbl,
        "count": cnt,
        "columns": cols,
        "total_payload_mb": total_payload_bytes / (1024**2),
        "max_payload_kb": max_payload_bytes / 1024,
        "avg_payload_kb": avg_payload_bytes / 1024
    })
    
    print(f"\nTable: '{tbl}'")
    print(f"  Record Count: {cnt:,}")
    print(f"  Columns: {cols}")
    print(f"  Total Text/Blob Payload: {total_payload_bytes / (1024**2):.2f} MB ({total_payload_bytes / (1024**3):.4f} GB)")
    print(f"  Max Record Payload: {max_payload_bytes / 1024:.2f} KB")
    print(f"  Avg Record Payload: {avg_payload_bytes / 1024:.2f} KB")

print("\n==========================================================================================")
print("3. LARGEST PAYLOADS & PAYLOAD CONTENT INSPECTION")
print("==========================================================================================")

for tbl in tables:
    cursor.execute(f"PRAGMA table_info(\"{tbl}\");")
    cols = [r[1] for r in cursor.fetchall()]
    json_cols = [c for c in cols if "json" in c.lower() or "data" in c.lower() or "snapshot" in c.lower() or "summary" in c.lower()]
    
    if not json_cols:
        continue
        
    for jc in json_cols:
        cursor.execute(f"SELECT rowid, length(\"{jc}\"), \"{jc}\" FROM \"{tbl}\" WHERE \"{jc}\" IS NOT NULL ORDER BY length(\"{jc}\") DESC LIMIT 3;")
        rows = cursor.fetchall()
        print(f"\nTop 3 largest records in '{tbl}' for column '{jc}':")
        for r in rows:
            row_id, payload_len, raw_text = r
            print(f"  RowID={row_id}, Size={payload_len / 1024:.2f} KB ({payload_len} bytes)")
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, dict):
                    keys = list(parsed.keys())
                    print(f"    Top-level JSON keys ({len(keys)} keys): {keys}")
                    # Inspect sizes of internal dictionary values
                    val_sizes = {}
                    for k, v in parsed.items():
                        v_str = json.dumps(v)
                        val_sizes[k] = len(v_str)
                    sorted_val_sizes = sorted(val_sizes.items(), key=lambda x: x[1], reverse=True)
                    print(f"    Largest internal properties: {[(k, f'{v/1024:.2f} KB') for k, v in sorted_val_sizes[:5]]}")
                elif isinstance(parsed, list):
                    print(f"    JSON Array length: {len(parsed)} items")
            except Exception as e:
                print(f"    JSON parse error: {e}")

conn.close()
