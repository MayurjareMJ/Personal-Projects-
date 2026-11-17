#!/usr/bin/env python3

import os
import shutil
import time
from datetime import datetime

# ==========================================================
# ------------------- CONFIGURATION ------------------------
# ==========================================================

# Main OUTPUT folder
OUTPUT_FOLDER = "/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/OUTPUT"

# Maximum days to keep data
MAX_DAYS_RETENTION = 7

# Maximum allowed disk usage (GB)
MAX_DISK_LIMIT_GB = 100

# Cleanup interval
SLEEP_HOURS = 1

# ==========================================================
# ---------------- HELPER FUNCTIONS ------------------------
# ==========================================================

def parse_date_folder(folder_name):
    """
    Converts folder name to datetime
    Expected format:
    2026_06_08
    """
    try:
        return datetime.strptime(folder_name, "%Y_%m_%d")
    except ValueError:
        return None

def get_all_date_folders(base_path):
    """
    Recursively find all date folders
    """

    folders = []

    if not os.path.exists(base_path):
        return folders
    for root, dirs, files in os.walk(base_path):
        for folder in dirs:
            folder_date = parse_date_folder(folder)
            if folder_date:
                full_path = os.path.join(root, folder)
                folders.append((folder_date, full_path))
    return folders

def get_folder_size_bytes(path):
    """
    Get total folder size recursively
    """

    total_size = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                total_size += os.path.getsize(file_path)
            except Exception:
                pass
    return total_size

def bytes_to_gb(size_bytes):
    return size_bytes / (1024 ** 3)

# ==========================================================
# ---------------- AGE BASED CLEANUP -----------------------
# ==========================================================
def cleanup_old_folders(base_path, max_days):
    today = datetime.now()
    folders = get_all_date_folders(base_path)
    for folder_date, folder_path in folders:
        age_days = (today - folder_date).days
        if age_days > max_days:
            print("=" * 60)
            print(f"[DELETE OLD FOLDER]")
            print(f"PATH : {folder_path}")
            print(f"AGE  : {age_days} days")
            print("=" * 60)
            shutil.rmtree(folder_path, ignore_errors=True)

# ==========================================================
# ---------------- DISK LIMIT CLEANUP ----------------------
# ==========================================================
def cleanup_disk_limit(base_path, max_disk_gb):
    while True:
        total_size_bytes = get_folder_size_bytes(base_path)

        total_size_gb = bytes_to_gb(total_size_bytes)

        print("=" * 60)
        print(f"[CURRENT DISK USAGE] {total_size_gb:.2f} GB")
        print("=" * 60)

        # Stop if under limit
        if total_size_gb <= max_disk_gb:

            print("[DISK USAGE WITHIN LIMIT]")
            break

        print("[WARNING] DISK LIMIT EXCEEDED")

        folders = get_all_date_folders(base_path)

        if not folders:

            print("[NO DATE FOLDERS FOUND]")
            break

        # Oldest first
        folders.sort(key=lambda x: x[0])

        oldest_date, oldest_folder = folders[0]

        print("=" * 60)
        print("[DELETING OLDEST FOLDER]")
        print(f"PATH : {oldest_folder}")
        print(f"DATE : {oldest_date}")
        print("=" * 60)

        shutil.rmtree(oldest_folder, ignore_errors=True)

        print("[FOLDER DELETED]")


# ==========================================================
# ---------------- CREATE TODAY FOLDERS --------------------
# ==========================================================

def create_today_folders():

    today_folder = datetime.now().strftime("%Y_%m_%d")

    folder_paths = [

        os.path.join(OUTPUT_FOLDER, "OK_IMAGES", today_folder),

        os.path.join(OUTPUT_FOLDER, "NOK_IMAGES", today_folder)

    ]

    for path in folder_paths:

        os.makedirs(path, exist_ok=True)

        print(f"[FOLDER READY] {path}")


# ==========================================================
# ---------------------- MAIN ------------------------------
# ==========================================================

def main():

    print("\n" + "=" * 60)
    print("IMAGE CLEANER SERVICE STARTED")
    print("=" * 60)

    sleep_seconds = SLEEP_HOURS * 3600

    while True:

        try:

            print("\n" + "=" * 60)
            print(f"[RUNNING CLEANUP] {datetime.now()}")
            print("=" * 60)

            # Create today's folders
            create_today_folders()

            # Delete folders older than retention
            cleanup_old_folders(
                OUTPUT_FOLDER,
                MAX_DAYS_RETENTION
            )

            # Maintain disk usage below limit
            cleanup_disk_limit(
                OUTPUT_FOLDER,
                MAX_DISK_LIMIT_GB
            )

            print("=" * 60)
            print("[CLEANUP COMPLETED]")
            print("=" * 60)

        except Exception as e:

            print("=" * 60)
            print("[ERROR]")
            print(e)
            print("=" * 60)

        print(f"\n[SLEEP] Sleeping for {SLEEP_HOURS} hour(s)\n")

        time.sleep(sleep_seconds)


# ==========================================================
# -------------------- ENTRY POINT -------------------------
# ==========================================================

if __name__ == "__main__":

    main()