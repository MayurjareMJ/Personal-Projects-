#!/usr/bin/env python3

import os
import shutil
import time
from datetime import datetime

# ==========================================================
# ------------------- CONFIGURATION ------------------------
# ==========================================================

# Main image data folder
DATA_FOLDER = "/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/data"

# Delete folders older than X days
MAX_DAYS_RETENTION = 7

# Maximum disk usage allowed (GB)
MAX_DISK_LIMIT_GB = 10

# Number of oldest folders to delete if disk exceeds limit
DELETE_BATCH_COUNT = 2

# Cleanup cycle interval
SLEEP_HOURS = 1

# ==========================================================
# ---------------- HELPER FUNCTIONS ------------------------
# ==========================================================

def parse_date_folder(folder_name):
    """
    Converts folder name to datetime
    Expected format:
    2026_05_18
    """
    try:
        return datetime.strptime(folder_name, "%Y_%m_%d")
    except ValueError:
        return None


def get_date_folders(base_path):
    """
    Returns all valid date folders
    """
    folders = []

    if not os.path.exists(base_path):
        return folders

    for folder in os.listdir(base_path):

        full_path = os.path.join(base_path, folder)

        if os.path.isdir(full_path):

            folder_date = parse_date_folder(folder)

            if folder_date:
                folders.append((folder_date, full_path))

    return folders


def get_folder_size_bytes(path):
    """
    Calculate folder size recursively
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


# ==========================================================
# ------------------- AGE CLEANUP --------------------------
# ==========================================================

def cleanup_old_folders(base_path, max_days):

    today = datetime.now()

    folders = get_date_folders(base_path)

    for folder_date, folder_path in folders:

        age_days = (today - folder_date).days

        if age_days > max_days:

            print(f"[DELETE OLD] {folder_path} ({age_days} days old)")

            shutil.rmtree(folder_path, ignore_errors=True)


# ==========================================================
# ---------------- DISK LIMIT CLEANUP ----------------------
# ==========================================================

def cleanup_disk_limit(base_path, max_disk_gb, delete_batch):

    total_size_gb = get_folder_size_bytes(base_path) / (1024 ** 3)

    print(f"[CURRENT SIZE] {total_size_gb:.2f} GB")

    if total_size_gb <= max_disk_gb:
        return

    print("[WARNING] Disk limit exceeded")

    folders = get_date_folders(base_path)

    # Sort oldest first
    folders.sort(key=lambda x: x[0])

    delete_count = min(delete_batch, len(folders))

    for i in range(delete_count):

        _, folder_path = folders[i]

        print(f"[DISK DELETE] {folder_path}")

        shutil.rmtree(folder_path, ignore_errors=True)


# ==========================================================
# ---------------------- MAIN ------------------------------
# ==========================================================

def main():

    print("\n[IMAGE CLEANER SERVICE STARTED]")

    sleep_seconds = SLEEP_HOURS * 3600

    while True:

        try:

            print("\n-----------------------------------")
            print("[RUNNING CLEANUP]", datetime.now())

            # Delete old folders
            cleanup_old_folders(
                DATA_FOLDER,
                MAX_DAYS_RETENTION
            )

            # Disk limit cleanup
            cleanup_disk_limit(
                DATA_FOLDER,
                MAX_DISK_LIMIT_GB,
                DELETE_BATCH_COUNT
            )

            print("[CLEANUP COMPLETED]")

        except Exception as e:

            print("[ERROR]", e)

        print(f"[SLEEP] Sleeping for {SLEEP_HOURS} hour(s)")

        time.sleep(sleep_seconds)


# ==========================================================
# -------------------- ENTRY POINT -------------------------
# ==========================================================

if __name__ == "__main__":
    main()