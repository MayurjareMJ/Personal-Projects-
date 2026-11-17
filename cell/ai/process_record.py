import time
import xml.etree.ElementTree as ET
import os
from pysqlcipher3 import dbapi2 as sqlite
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler


# ============================================================
# LOGGER
# ============================================================

LOG_DIR = "/home/etpl/VISION/test-cell4/logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "ai_result.log")

logger = logging.getLogger("result_logger")
logger.setLevel(logging.ERROR)

handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)

formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s"
)

handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(handler)


# ============================================================
# CONFIG
# ============================================================

CONFIG_PATH = "/home/etpl/VISION/test-cell4/config/congfig.xml"

path_conf_file = ET.parse(CONFIG_PATH)
root = path_conf_file.getroot()

RECORDPATH = root.find("INCIDENTRECORDSAVEPATH").text
DATABASEPATH = root.find("DATABASEPATH").text
DATABASEPASS = root.find("DATABASEPASS").text

MACHINEUSER = root.find("MACHINEUSER").text

TRIGGERLOCATION = root.find("TRIGGERLOCATION").text
BUZZER_OFF = os.path.join(
    TRIGGERLOCATION,
    "HOOTER_OFF.txt"
)


# ============================================================
# DATABASE
# ============================================================

def open_db(db_path, key):

    safe_key = key.replace("'", "''")

    conn = sqlite.connect(db_path)

    conn.execute(
        f"PRAGMA key = '{safe_key}';"
    )

    return conn


def init_tables(conn):

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vision_result (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_name TEXT NOT NULL,
            location_name TEXT NOT NULL,
            final_result TEXT,
            image_path TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()


def log_vision_result(
    conn,
    camera_name,
    location_name,
    final_result,
    image_path
):

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO vision_result
        (
            camera_name,
            location_name,
            final_result,
            image_path
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            camera_name,
            location_name,
            final_result,
            image_path
        )
    )

    conn.commit()


# ============================================================
# PROCESS JSON
# ============================================================

def process_json_file(json_file_path):

    try:

        with open(json_file_path, "r") as f:
            data = json.load(f)

        camera_id = data.get("camera_id")
        event = data.get("event")
        timestamp = data.get("timestamp")
        location = data.get("location")
        img_path = data.get("img_save_path")

        print(
            "[INFO] Processing:",
            json_file_path
        )

        print(
            "[INFO] Camera:",
            camera_id,
            "Event:",
            event,
            "Location:",
            location
        )

        # ----------------------------------------------------
        # INSERT INTO DATABASE
        # ----------------------------------------------------

        conn = open_db(
            DATABASEPATH,
            DATABASEPASS
        )

        # Make sure table exists
        init_tables(conn)

        log_vision_result(
            conn,
            camera_id,
            location,
            event,
            img_path
        )

        conn.close()

        print(
            "[INFO] Database record inserted successfully"
        )

        # ----------------------------------------------------
        # DELETE JSON AFTER SUCCESSFUL INSERT
        # ----------------------------------------------------

        os.remove(json_file_path)

        print(
            "[INFO] Processed and deleted:",
            json_file_path
        )

    except Exception as e:

        logger.exception(
            "Failed to process %s: %s",
            json_file_path,
            e
        )

        print(
            "[ERROR] Failed to process:",
            json_file_path,
            e
        )


# ============================================================
# MONITOR RECORD FOLDER
# ============================================================

def monitor_folder(folder_path):

    print(
        "[INFO] Monitoring folder:",
        folder_path
    )

    while True:

        try:

            json_files = [
                os.path.join(folder_path, f)
                for f in os.listdir(folder_path)
                if f.endswith(".json")
            ]

            if not json_files:

                time.sleep(0.1)

                continue

            # Oldest JSON first
            json_files.sort(
                key=os.path.getctime
            )

            process_json_file(
                json_files[0]
            )

        except Exception as e:

            logger.exception(
                "Monitoring failed: %s",
                e
            )

            print(
                "[ERROR] Monitoring failed:",
                e
            )

            time.sleep(0.1)


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "[INFO] PROCESS_RECORD starting..."
    )

    print(
        "[INFO] Record path:",
        RECORDPATH
    )

    print(
        "[INFO] Database:",
        DATABASEPATH
    )

    # Check record folder
    if not os.path.exists(RECORDPATH):

        print(
            "[ERROR] Record folder does not exist:",
            RECORDPATH
        )

        return

    # Check database
    print(
        "[INFO] Database exists:",
        os.path.exists(DATABASEPATH)
    )

    monitor_folder(
        RECORDPATH
    )


if __name__ == "__main__":

    main()