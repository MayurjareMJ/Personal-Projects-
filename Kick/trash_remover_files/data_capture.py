#!/usr/bin/env python3

import cv2
import os
import time
from datetime import datetime

# ==========================================================
# ------------------- CONFIGURATION ------------------------
# ==========================================================

# RTSP URL
RTSP_URL = "rtsp://admin:Elansol%402026@192.168.1.64:554/cam/realmonitor?channel=1&subtype=0"

# Save Path
SAVE_BASE_PATH = "/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/data"

# Save one image every 1 minute
SAVE_INTERVAL = 60   # seconds

# ==========================================================
# ---------------- HELPER FUNCTIONS ------------------------
# ==========================================================

def get_day_folder(base_path):
    """
    Create date-wise folder
    Example:
    data/2026_05_18/
    """

    date_str = datetime.now().strftime("%Y_%m_%d")

    folder_path = os.path.join(base_path, date_str)

    os.makedirs(folder_path, exist_ok=True)

    return folder_path


def open_rtsp(rtsp_url):
    """
    Open RTSP stream
    """

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    # Reduce RTSP latency
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

    return cap


# ==========================================================
# ---------------------- MAIN ------------------------------
# ==========================================================

def main():

    # Create main save directory
    os.makedirs(SAVE_BASE_PATH, exist_ok=True)

    # Open RTSP
    cap = open_rtsp(RTSP_URL)

    if not cap.isOpened():

        print("[ERROR] Unable to open RTSP stream")

        return

    print("[INFO] RTSP Capture Started")

    frame_id = 0

    try:

        while True:

            # Read frame
            ret, frame = cap.read()

            if not ret:

                print("[WARNING] Failed to read frame")

                time.sleep(5)

                # Try reconnecting
                cap.release()

                cap = open_rtsp(RTSP_URL)

                continue

            # Create today's folder
            save_dir = get_day_folder(SAVE_BASE_PATH)

            # Increase frame count
            frame_id += 1

            # Timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # File name
            filename = f"frame_{frame_id:06d}_{timestamp}.jpg"

            # Full save path
            file_path = os.path.join(save_dir, filename)

            # Save image
            success = cv2.imwrite(file_path, frame)

            if success:

                print(f"[SAVED] {file_path}")

            else:

                print("[ERROR] Failed to save image")

            # Wait 1 minute
            time.sleep(SAVE_INTERVAL)

    except KeyboardInterrupt:

        print("\n[STOPPED] Capture stopped by user")

    finally:

        cap.release()

        cv2.destroyAllWindows()

        print("[CLEANUP] Camera released")


# ==========================================================
# -------------------- ENTRY POINT -------------------------
# ==========================================================

if __name__ == "__main__":

    main()