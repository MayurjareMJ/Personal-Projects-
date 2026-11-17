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

# Base save path
SAVE_BASE_PATH = "/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/DATA_VIDEOS"

# Duration of each video
VIDEO_DURATION = 5 * 60   # 5 minutes in seconds

# FPS to save
FPS = 20

# Video codec
FOURCC = cv2.VideoWriter_fourcc(*'mp4v')

# ==========================================================
# ---------------- HELPER FUNCTIONS ------------------------
# ==========================================================

def get_day_folder(base_path):
    """
    Create date-wise folder:
    videos/2026_05_18/
    """

    date_str = datetime.now().strftime("%Y_%m_%d")

    folder_path = os.path.join(base_path, date_str)

    os.makedirs(folder_path, exist_ok=True)

    return folder_path


def open_rtsp(rtsp_url):
    """
    Open RTSP stream with low latency
    """

    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

    return cap


# ==========================================================
# ---------------------- MAIN ------------------------------
# ==========================================================

def main():

    # Create base directory
    os.makedirs(SAVE_BASE_PATH, exist_ok=True)

    # Open RTSP
    cap = open_rtsp(RTSP_URL)

    if not cap.isOpened():

        print("[ERROR] Unable to open RTSP stream")

        return

    print("[INFO] RTSP Capture Started")

    video_count = 0

    try:

        while True:

            # Read one frame to get size
            ret, frame = cap.read()

            if not ret:

                print("[WARNING] Failed to read frame")

                time.sleep(5)

                cap.release()

                cap = open_rtsp(RTSP_URL)

                continue

            height, width = frame.shape[:2]

            # Create folder
            save_dir = get_day_folder(SAVE_BASE_PATH)

            # Timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Video filename
            video_name = f"video_{video_count:06d}_{timestamp}.mp4"

            # Full path
            video_path = os.path.join(save_dir, video_name)

            # Create video writer
            writer = cv2.VideoWriter(
                video_path,
                FOURCC,
                FPS,
                (width, height)
            )

            print(f"[RECORDING] {video_path}")

            start_time = time.time()

            # Record for 5 minutes
            while (time.time() - start_time) < VIDEO_DURATION:

                ret, frame = cap.read()

                if not ret:

                    print("[WARNING] Frame read failed")

                    break

                writer.write(frame)

            # Release current writer
            writer.release()

            print(f"[SAVED] {video_path}")

            video_count += 1

    except KeyboardInterrupt:

        print("\n[STOPPED] Recording stopped by user")

    finally:

        cap.release()

        cv2.destroyAllWindows()

        print("[CLEANUP] Camera released")


# ==========================================================
# -------------------- ENTRY POINT -------------------------
# ==========================================================

if __name__ == "__main__":

    main()