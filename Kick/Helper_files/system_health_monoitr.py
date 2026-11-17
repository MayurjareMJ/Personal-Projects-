#!/usr/bin/env python3

import cv2
import os
import time
import psutil
import threading
import subprocess
import xml.etree.ElementTree as ET

from ultralytics import YOLO
from collections import deque

# =========================================================
# CONFIG PATH
# =========================================================

CONFIG_PATH ="/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/Config.xml"

# =========================================================
# LOAD XML CONFIG
# =========================================================

try:
    tree = ET.parse(CONFIG_PATH)
    root = tree.getroot()

except Exception as e:
    print(f"CONFIG LOAD ERROR : {e}")
    exit()

# =========================================================
# READ CONFIG VALUES
# =========================================================

try:

    RTSP_URL = root.find("Stream/MainStream").text.strip()

    DEBUG_MODE = root.find("Stream/DebugMode").text.strip()

    DEBUG_VIDEO = root.find("Stream/DebugVideo").text.strip()

    MODEL_PATH = root.find("Model/ModelPath").text.strip()

    OK_IMAGES = root.find("Paths/OK_IMAGES").text.strip()

    NOK_VIDEOS = root.find("Paths/NOK_VIDEOS").text.strip()

    ROLLING_FRAMES = root.find("Paths/ROLLING_FRAMES").text.strip()

except Exception as e:

    print(f"XML READ ERROR : {e}")
    exit()

# =========================================================
# SETTINGS
# =========================================================

FRAME_SKIP = 2

DISPLAY = False

SAVE_TEST_IMAGES = False

# =========================================================
# CREATE OUTPUT FOLDERS
# =========================================================

os.makedirs(OK_IMAGES, exist_ok=True)
os.makedirs(NOK_VIDEOS, exist_ok=True)
os.makedirs(ROLLING_FRAMES, exist_ok=True)

# =========================================================
# LOAD YOLO MODEL
# =========================================================

print("\n===================================")
print("LOADING YOLO MODEL")
print("===================================")

try:

    model = YOLO(MODEL_PATH)

    model.to("cuda")

    print("GPU ENABLED")

except Exception as e:

    print(f"MODEL LOAD ERROR : {e}")

    exit()

# =========================================================
# SYSTEM MONITOR THREAD
# =========================================================

def system_monitor():

    while True:

        try:

            cpu = psutil.cpu_percent(interval=1)

            ram = psutil.virtual_memory()

            print("\n================ SYSTEM STATS ================")

            print(f"CPU Usage       : {cpu}%")

            print(f"RAM Usage       : {ram.percent}%")

            print(f"RAM Used        : {round(ram.used/1024**3, 2)} GB")

            print(f"RAM Available   : {round(ram.available/1024**3, 2)} GB")

            # ============================================
            # GPU STATS
            # ============================================

            result = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits"
                ]
            ).decode().strip()

            gpu_util, mem_used, mem_total, temp = result.split(",")

            print(f"GPU Usage       : {gpu_util.strip()}%")

            print(f"GPU Memory      : {mem_used.strip()} / {mem_total.strip()} MB")

            print(f"GPU Temperature : {temp.strip()} C")

            print("================================================")

        except Exception as e:

            print(f"SYSTEM MONITOR ERROR : {e}")

        time.sleep(2)

# =========================================================
# START SYSTEM MONITOR
# =========================================================

monitor_thread = threading.Thread(
    target=system_monitor,
    daemon=True
)

monitor_thread.start()

# =========================================================
# OPEN CAMERA / VIDEO
# =========================================================

print("\n===================================")
print("OPENING STREAM")
print("===================================")

if DEBUG_MODE == "True":

    print("DEBUG VIDEO MODE ENABLED")

    cap = cv2.VideoCapture(DEBUG_VIDEO)

else:

    print("RTSP MODE ENABLED")

    cap = cv2.VideoCapture(RTSP_URL)

# Reduce RTSP buffering
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():

    print("ERROR : UNABLE TO OPEN STREAM")

    exit()

print("STREAM OPENED SUCCESSFULLY")

# =========================================================
# VARIABLES
# =========================================================

frame_count = 0

fps_queue = deque(maxlen=30)

# =========================================================
# MAIN LOOP
# =========================================================

while True:

    loop_start = time.time()

    # =====================================================
    # CAMERA READ
    # =====================================================

    cam_start = time.time()

    ret, frame = cap.read()

    cam_time = time.time() - cam_start

    # =====================================================
    # STREAM FAILURE HANDLING
    # =====================================================

    if not ret:

        print("\nSTREAM FAILED - RECONNECTING")

        cap.release()

        time.sleep(2)

        if DEBUG_MODE == "True":

            cap = cv2.VideoCapture(DEBUG_VIDEO)

        else:

            cap = cv2.VideoCapture(RTSP_URL)

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        continue

    frame_count += 1

    # =====================================================
    # FRAME SKIP
    # =====================================================

    if frame_count % FRAME_SKIP != 0:

        continue

    # =====================================================
    # RESIZE
    # =====================================================

    resize_start = time.time()

    frame = cv2.resize(
        frame,
        (640, 640),
        interpolation=cv2.INTER_AREA
    )

    resize_time = time.time() - resize_start

    # =====================================================
    # YOLO INFERENCE
    # =====================================================

    infer_start = time.time()

    results = model(
        frame,
        conf=0.5,
        verbose=False,
        half=True
    )

    infer_time = time.time() - infer_start

    # =====================================================
    # DRAW RESULTS
    # =====================================================

    draw_start = time.time()

    annotated_frame = results[0].plot()

    draw_time = time.time() - draw_start

    # =====================================================
    # OPTIONAL IMAGE SAVE TEST
    # =====================================================

    if SAVE_TEST_IMAGES:

        try:

            save_start = time.time()

            image_path = os.path.join(
                OK_IMAGES,
                f"frame_{frame_count}.jpg"
            )

            cv2.imwrite(image_path, annotated_frame)

            save_time = time.time() - save_start

            print(f"IMAGE SAVE TIME : {save_time:.4f} sec")

        except Exception as e:

            print(f"IMAGE SAVE ERROR : {e}")

    # =====================================================
    # FPS CALCULATION
    # =====================================================

    total_time = time.time() - loop_start

    fps = 1 / total_time if total_time > 0 else 0

    fps_queue.append(fps)

    avg_fps = sum(fps_queue) / len(fps_queue)

    # =====================================================
    # DISPLAY FPS
    # =====================================================

    cv2.putText(
        annotated_frame,
        f"FPS: {avg_fps:.2f}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    # =====================================================
    # REDUCED LOGGING
    # =====================================================

    if frame_count % 30 == 0:

        print("\n================ PIPELINE TIMING ================")

        print(f"Frame Count      : {frame_count}")

        print(f"Camera Read Time : {cam_time:.4f} sec")

        print(f"Resize Time      : {resize_time:.4f} sec")

        print(f"Inference Time   : {infer_time:.4f} sec")

        print(f"Draw Time        : {draw_time:.4f} sec")

        print(f"Total Loop Time  : {total_time:.4f} sec")

        print(f"FPS              : {avg_fps:.2f}")

        print("=================================================")

    # =====================================================
    # WARNINGS
    # =====================================================

    if infer_time > 0.1:

        print("WARNING : SLOW INFERENCE")

    if cam_time > 0.5:

        print("WARNING : RTSP DELAY DETECTED")

    if avg_fps < 5:

        print("WARNING : LOW FPS")

    # =====================================================
    # DISPLAY WINDOW
    # =====================================================

    if DISPLAY:

        cv2.imshow(
            "YOLO SYSTEM HEALTH MONITOR",
            annotated_frame
        )

        key = cv2.waitKey(1)

        if key == ord("q"):

            break

# =========================================================
# CLEANUP
# =========================================================

cap.release()

cv2.destroyAllWindows()

print("\nAPPLICATION CLOSED")