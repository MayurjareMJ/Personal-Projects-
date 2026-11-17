import psycopg2
import subprocess
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from config import DB_SETTINGS_CONFIG, DB_TRANSACTIONS_CONFIG
 
SCHEMA = "98a6faaf09fc260a"
 
failure_counts = {}
success_counts = {}
 
OFFLINE_THRESHOLD = 3
ONLINE_THRESHOLD = 2
CHECK_INTERVAL = 10
 
 
# ======================================
# DATABASE CONNECTIONS
# ======================================
def get_settings_conn():
    """Connects to scout_settings — where settings_camera lives."""
    conn = psycopg2.connect(**DB_SETTINGS_CONFIG)
    cursor = conn.cursor()
    cursor.execute(f'SET search_path TO "{SCHEMA}"')
    cursor.close()
    return conn
 
 
def get_transactions_conn():
    """Connects to scout_transactions — where camera_status lives."""
    conn = psycopg2.connect(**DB_TRANSACTIONS_CONFIG)
    cursor = conn.cursor()
    cursor.execute(f'SET search_path TO "{SCHEMA}"')
    cursor.close()
    return conn
 
 
# ======================================
# FETCH CAMERAS FROM DB
# ======================================
def fetch_cameras(cursor):
    """
    Pulls active cameras from settings_camera (scout_settings DB).
    Returns list of tuples: (camera_id, setting_camera_id, camera_name, camera_zone, camera_ip)
    """
    cursor.execute(f"""
        SELECT
            settings_camera_id,
            settings_camera_id,
            camera_name,
            camera_zone,
            camera_ip
        FROM "{SCHEMA}".settings_camera
        WHERE camera_status = 'ENABLE'
    """)
    rows = cursor.fetchall()
    print(f"Loaded {len(rows)} active camera(s) from DB")
    return rows
 
 
# ======================================
# PING CAMERA IP
# ======================================
def check_camera(ip):
    try:
        result = subprocess.run(
            ["ping", "-c", "2", "-W", "2", ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return "CONNECTED" if result.returncode == 0 else "DISCONNECTED"
    except Exception:
        return "DISCONNECTED"
 
 
# ======================================
# CAMERA PROCESSOR
# ======================================
def process_camera(camera):
    cam_id, setting_id, name, zone, ip = camera
    status = check_camera(ip)
    return {
        "camera_id": cam_id,
        "setting_id": setting_id,
        "name": name,
        "zone": zone,
        "ip": ip,
        "status": status
    }
 
 
# ======================================
# GET CURRENT STATUS FROM DB
# ======================================
def get_current_status(cursor, camera_id):
    cursor.execute(
        f'SELECT status FROM "{SCHEMA}".camera_status WHERE camera_id = %s',
        (camera_id,)
    )
    result = cursor.fetchone()
    return result[0] if result else None
 
 
# ======================================
# UPSERT CAMERA STATUS
# ======================================
def upsert_camera_status(cursor, cam):
    cursor.execute(f"""
        INSERT INTO "{SCHEMA}".camera_status
            (camera_id, setting_camera_id, camera_name, camera_zone, camera_ip, status, last_checked)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (camera_id)
        DO UPDATE SET
            setting_camera_id = EXCLUDED.setting_camera_id,
            camera_name       = EXCLUDED.camera_name,
            camera_zone       = EXCLUDED.camera_zone,
            camera_ip         = EXCLUDED.camera_ip,
            status            = EXCLUDED.status,
            last_checked      = EXCLUDED.last_checked
    """, (
        cam["camera_id"],
        cam["setting_id"],
        cam["name"],
        cam["zone"],
        cam["ip"],
        cam["status"],
        datetime.now()
    ))
 
 
# ======================================
# MONITOR LOOP
# ======================================
def monitor():
    print("Camera Monitoring Service Started")
 
    while True:
        try:
            print("\n==============================")
            print("Checking Cameras...")
            print("==============================\n")
 
            # --- Fetch camera list from scout_settings ---
            settings_conn = get_settings_conn()
            settings_cursor = settings_conn.cursor()
            cameras = fetch_cameras(settings_cursor)
            settings_cursor.close()
            settings_conn.close()
 
            if not cameras:
                print("No active cameras found in DB. Retrying next cycle...")
                time.sleep(CHECK_INTERVAL)
                continue
 
            # --- Ping all cameras in parallel ---
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(process_camera, cameras))
 
            # --- Write results to scout_transactions ---
            tx_conn = get_transactions_conn()
            tx_cursor = tx_conn.cursor()
 
            for cam in results:
                cam_id = cam["camera_id"]
 
                old_status = get_current_status(tx_cursor, cam_id)
                new_status = cam["status"]
 
                failure_counts.setdefault(cam_id, 0)
                success_counts.setdefault(cam_id, 0)
 
                if new_status == "DISCONNECTED":
                    failure_counts[cam_id] += 1
                    success_counts[cam_id] = 0
                else:
                    success_counts[cam_id] += 1
                    failure_counts[cam_id] = 0
 
                # First time seeing this camera
                if old_status is None:
                    print(f"{cam['name']} ({cam['ip']}) initial status -> {new_status}")
                    upsert_camera_status(tx_cursor, cam)
 
                # Confirmed offline after repeated failures
                elif old_status == "CONNECTED" and failure_counts[cam_id] >= OFFLINE_THRESHOLD:
                    print(f"{cam['name']} ({cam['ip']}) confirmed OFFLINE")
                    upsert_camera_status(tx_cursor, cam)
 
                # Confirmed online after repeated successes
                elif old_status == "DISCONNECTED" and success_counts[cam_id] >= ONLINE_THRESHOLD:
                    print(f"{cam['name']} ({cam['ip']}) confirmed ONLINE")
                    upsert_camera_status(tx_cursor, cam)
 
                else:
                    print(f"{cam['name']} ({cam['ip']}) -> {new_status}")
 
            tx_conn.commit()
            tx_cursor.close()
            tx_conn.close()
 
            print("\nCheck finished\n")
 
        except Exception as e:
            print("ERROR:", e)
 
        time.sleep(CHECK_INTERVAL)
 
 
# ======================================
# MAIN
# ======================================
if __name__ == "__main__":
    monitor()
