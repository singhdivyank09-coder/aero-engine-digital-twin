import sqlite3
import os

db_path = r"C:\Users\divya\.gemini\antigravity\scratch\aero_engine_digital_twin\data\telemetry_db.sqlite"

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET full_name = 'Demo Prototype Operator' WHERE username = 'engineer' OR full_name LIKE '%DRDO%' OR full_name LIKE '%Propulsion Engineer%';")
    conn.commit()
    print(f"Updated {cursor.rowcount} rows in database users table.")
    
    cursor.execute("SELECT username, role, full_name FROM users;")
    rows = cursor.fetchall()
    print("Database users now:")
    for r in rows:
        print(f"  User: {r[0]}, Role: {r[1]}, Full Name: '{r[2]}'")
    conn.close()
else:
    print("Database file does not exist yet.")
