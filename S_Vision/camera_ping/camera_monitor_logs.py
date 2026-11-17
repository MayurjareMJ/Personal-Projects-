# import psycopg2
# import subprocess
# import time
# from datetime import datetime
# from config import DB_CONFIG, CAMERAS

# # ===============================
# # DATABASE CONNECTION
# # ===============================
# def get_connection():
#     return psycopg2.connect(**DB_CONFIG)

# # ===============================
# # CHECK CAMERA CONNECTION
# # ===============================
# def check_camera(ip):
#     try:
#         result = subprocess.run(
#             ["ping", "-n", "1", "-w", "1000", ip],
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE
#         )
#         return "CONNECTED" if result.returncode == 0 else "DISCONNECTED"
#     except:
#         return "DISCONNECTED"

# # ===============================
# # GET LAST STATUS FROM LOG TABLE
# # ===============================
# def get_last_status(cursor, camera_id):

#     cursor.execute("""
#         SELECT status
#         FROM camera_status_logs
#         WHERE camera_id=%s
#         ORDER BY checked_at DESC
#         LIMIT 1
#     """, (camera_id,))

#     result = cursor.fetchone()
#     return result[0] if result else None

# # ===============================
# # INSERT STATUS LOG
# # ===============================
# def insert_status(cursor, camera_id, setting_camera_id, camera_name, camera_zone, camera_ip, status):

#     cursor.execute("""
#         INSERT INTO camera_status_logs
#         (camera_id, setting_camera_id, camera_name, camera_zone, camera_ip, status, checked_at)
#         VALUES (%s,%s,%s,%s,%s,%s,%s)
#     """, (
#         camera_id,
#         setting_camera_id,
#         camera_name,
#         camera_zone,
#         camera_ip,
#         status,
#         datetime.now()
#     ))

# # ===============================
# # MONITOR LOOP
# # ===============================
# def monitor():

#     while True:
#         try:
#             conn = get_connection()
#             cursor = conn.cursor()

#             print("\nChecking Cameras...\n")

#             for cam_id, setting_id, name, zone, ip in CAMERAS:

#                 new_status = check_camera(ip)
#                 old_status = get_last_status(cursor, cam_id)

#                 print(f"{name} ({ip}) -> {new_status}")

#                 if old_status != new_status:

#                     print(f"Status changed: {old_status} -> {new_status}")

#                     insert_status(
#                         cursor,
#                         cam_id,
#                         setting_id,
#                         name,
#                         zone,
#                         ip,
#                         new_status
#                     )

#                 else:
#                     print("No change")

#             conn.commit()
#             cursor.close()
#             conn.close()

#             print("\nCheck finished\n")

#         except Exception as e:
#             print("Error:", e)

#         time.sleep(5)

# # ===============================
# # MAIN
# # ===============================
# if __name__ == "__main__":
#     print("Camera Monitoring Service Started")
#     monitor()









# import psycopg2
# import subprocess
# import time
# from datetime import datetime
# from config import DB_CONFIG, CAMERAS


# def get_connection():
#     return psycopg2.connect(**DB_CONFIG)


# def check_camera(ip):
#     try:
#         result = subprocess.run(
#             ["ping", "-n", "1", "-w", "1000", ip],
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE
#         )
#         return "CONNECTED" if result.returncode == 0 else "DISCONNECTED"
#     except:
#         return "DISCONNECTED"


# def get_last_status(cursor, camera_id):

#     cursor.execute("""
#         SELECT status
#         FROM camera_status_logs
#         WHERE camera_id = %s
#         ORDER BY last_checked DESC
#         LIMIT 1
#     """, (camera_id,))

#     result = cursor.fetchone()
#     return result[0] if result else None


# def insert_status(cursor, camera_id, setting_camera_id,
#                   camera_name, camera_zone, camera_ip, status):

#     cursor.execute("""
#         INSERT INTO camera_status_logs
#         (camera_id, setting_camera_id, camera_name,
#          camera_zone, camera_ip, status, last_checked)

#         VALUES (%s,%s,%s,%s,%s,%s,%s)
#     """, (
#         camera_id,
#         setting_camera_id,
#         camera_name,
#         camera_zone,
#         camera_ip,
#         status,
#         datetime.now()
#     ))


# def monitor():

#     while True:

#         try:
#             conn = get_connection()
#             cursor = conn.cursor()

#             # IMPORTANT: use correct schema
#             cursor.execute("SET search_path TO 5af69246f54eea1c")

#             print("\n==============================")
#             print("Checking Cameras...")
#             print("==============================\n")

#             for cam_id, setting_id, name, zone, ip in CAMERAS:

#                 new_status = check_camera(ip)
#                 old_status = get_last_status(cursor, cam_id)

#                 print(f"{name} ({ip}) -> {new_status}")

#                 if old_status != new_status:

#                     print(f"Status changed: {old_status} -> {new_status}")

#                     # insert_status(
#                     #     cursor,
#                     #     cam_id,
#                     #     setting_id,
#                     #     name,
#                     #     zone,
#                     #     ip,
#                     #     new_status
#                     # )

#                 else:
#                     print("No change")

#             conn.commit()
#             cursor.close()
#             conn.close()

#             print("\nCheck finished\n")

#         except Exception as e:
#             print("Error:", e)

#         time.sleep(1)


# if __name__ == "__main__":
#     print("Camera Monitoring Service Started")
#     monitor()














import psycopg2
import subprocess
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from config import DB_CONFIG, CAMERAS


# ===============================
# DATABASE CONNECTION
# ===============================
def get_connection():
    return psycopg2.connect(**DB_CONFIG)


# ===============================
# CHECK CAMERA CONNECTION
# ===============================
def check_camera(rtsp_url):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-rtsp_transport", "tcp",
                "-timeout", "3000000",
                "-i", rtsp_url
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )

        return "CONNECTED" if result.returncode == 0 else "DISCONNECTED"

    except subprocess.TimeoutExpired:
        return "DISCONNECTED"
    except Exception:
        return "DISCONNECTED"


# ===============================
# GET LAST STATUS
# ===============================
def get_last_status(cursor, camera_id):

    cursor.execute("""
        SELECT status
        FROM camera_status_logs
        WHERE camera_id = %s
        ORDER BY last_checked DESC
        LIMIT 1
    """, (camera_id,))

    result = cursor.fetchone()
    return result[0] if result else None


# ===============================
# INSERT STATUS CHANGE
# ===============================
def insert_status(cursor, camera_id, setting_camera_id,
                  camera_name, camera_zone, camera_ip, status):

    cursor.execute("""
        INSERT INTO camera_status_logs
        (camera_id, setting_camera_id, camera_name,
         camera_zone, camera_ip, status, last_checked)

        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (
        camera_id,
        setting_camera_id,
        camera_name,
        camera_zone,
        camera_ip,
        status,
        datetime.now()
    ))


# ===============================
# PROCESS ONE CAMERA
# ===============================
def process_camera(camera):

    cam_id, setting_id, name, zone, rtsp = camera

    new_status = check_camera(rtsp)

    return {
        "camera_id": cam_id,
        "setting_id": setting_id,
        "name": name,
        "zone": zone,
        "rtsp": rtsp,
        "status": new_status
    }


# ===============================
# MAIN MONITOR LOOP
# ===============================
def monitor():

    while True:

        try:

            print("\n==============================")
            print("Checking Cameras...")
            print("==============================\n")

            # --------------------------------
            # PARALLEL CAMERA CHECK
            # --------------------------------
            with ThreadPoolExecutor(max_workers=20) as executor:
                results = list(executor.map(process_camera, CAMERAS))

            # --------------------------------
            # DATABASE PART
            # --------------------------------
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("SET search_path TO 5af69246f54eea1c")

            for cam in results:

                cam_id = cam["camera_id"]
                setting_id = cam["setting_id"]
                name = cam["name"]
                zone = cam["zone"]
                rtsp = cam["rtsp"]
                new_status = cam["status"]

                old_status = get_last_status(cursor, cam_id)

                print(f"{name} ({rtsp}) -> {new_status}")

                if old_status != new_status:

                    print(f"Status changed: {old_status} -> {new_status}")

                    insert_status(
                        cursor,
                        cam_id,
                        setting_id,
                        name,
                        zone,
                        rtsp,
                        new_status
                    )

                else:
                    print("No change")

            conn.commit()
            cursor.close()
            conn.close()

            print("\nCheck finished\n")

        except Exception as e:
            print("Error:", e)

        # check every second
        time.sleep(1)


# ===============================
# ENTRY POINT
# ===============================
if __name__ == "__main__":
    print("Camera Monitoring Service Started")
    monitor()