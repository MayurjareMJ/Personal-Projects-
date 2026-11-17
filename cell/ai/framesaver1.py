import cv2
import os
from time import sleep, time
import xml.etree.ElementTree as ET
import numpy as np
import gc
import sys
import logging
from logging.handlers import RotatingFileHandler

# ---------- load config ----------
path_conf_file = ET.parse('/home/test-cell7/VISION/config/congfig.xml')
root = path_conf_file.getroot()

# Try to read optional log file path from XML; fallback to local file
try:
    log_file = root.find("LOGFILE").text
    if not log_file:
        raise AttributeError
except Exception:
    log_file = "camera_capture1.log"

# ---------- logger setup (rotating) ----------
logger = logging.getLogger("camera_capture")
logger.setLevel(logging.INFO)

# Rotating file handler: 10 MB per file, keep 5 backups
file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Console handler (stderr)
console_handler = logging.StreamHandler()
console_handler.setFormatter(file_formatter)
logger.addHandler(console_handler)

logger.info("Logger initialized. Log file: %s", os.path.abspath(log_file))

# -- User pipeline function (uses exactly the pipeline you provided) --
def get_gst_pipline(source):
    return (
        f"rtspsrc location={source} latency=0 protocols=udp ! "
        "rtpjitterbuffer latency=0 drop-on-latency=true ! "
        "rtph265depay ! h265parse ! nvv4l2decoder max-queued-buffers=1 ! "
        "nvvidconv ! video/x-raw, format=(string)BGRx ! "
        "videoconvert ! video/x-raw, format=(string)BGR ! "
        "queue max-size-buffers=1 leaky=2 ! "
        "appsink drop=true sync=false max-buffers=1"
    )

encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 100]

def atomic_write_jpg(path: str, frame: np.ndarray):
    """
    Atomically save a NumPy image as a JPG file.

    Parameters:
    - path: target file path (should end with .jpg)
    - frame: numpy array (H x W x C)
    """
    tmp_path = f"{path}.tmp"
    try:
        # Encode as JPG
        success, buffer = cv2.imencode('.jpg', frame, encode_param)
        if not success:
            raise ValueError("Failed to encode the image as JPG")

        # Ensure directory exists
        dirpath = os.path.dirname(path)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)

        # Write to temporary file
        with open(tmp_path, "wb") as f:
            f.write(buffer.tobytes())
            f.flush()
            os.fsync(f.fileno())  # ensure data is written to disk

        # Atomic replace
        os.replace(tmp_path, path)
        logger.debug("Wrote JPG atomically to %s", path)
    except Exception as e:
        # Clean up temp file if present
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        logger.exception("Failed to write JPG to %s: %s", path, e)
        raise

# -- Helper: encode frame to JPEG bytes with given params --
def encode_frame_to_jpeg_bytes(frame, jpeg_params):
    success, buf = cv2.imencode('.jpg', frame, list(jpeg_params))
    if not success:
        raise RuntimeError("Failed to encode frame to JPEG")
    return buf.tobytes()

# -- Main: capture loop with non-blocking save requests --
def main():
    try:
        rtsp1 = root.find("CAM1RTSP").text
        save_location1 = root.find("CAM1RAWSAVEPATH").text
    except Exception as e:
        logger.error("Required XML entries CAM1RTSP or CAM1RAWSAVEPATH not found: %s", e)
        sys.exit(1)

    TRIGGERLOCATION = root.find("TRIGGERLOCATION").text
    CAM1LIVE = os.path.join(TRIGGERLOCATION,f"CAM1LIVE.txt")

    gst1 = get_gst_pipline(rtsp1)
    logger.info("GStreamer pipeline: %s", gst1.replace(rtsp1, "<REDACTED_RTSP>") )

    cap1 = cv2.VideoCapture(gst1, cv2.CAP_GSTREAMER)
    if not cap1.isOpened():
        logger.error("Failed to open VideoCapture for CAM1. Exiting.")
        sys.exit(1)
    logger.info("VideoCapture opened for CAM1")

    starttime = time()
    restart_time = time()

    restartcounter = 3
    try:
        while True:
            fd=open(CAM1LIVE,'w')
            fd.close()
            if restartcounter == 0:
                logger.critical("Restart counter exhausted. Releasing capture and exiting.")
                cap1.release()
                del cap1
                gc.collect()
                sys.exit(1)

            ret1, frame1 = cap1.read()

            if not ret1:
                restartcounter -= 1
                logger.warning("Frame read failed. Decrementing restartcounter to %d", restartcounter)
                sleep(0.1)
                continue
            else:
                # Save a frame every 0.5s (like your original logic)
                if time() - starttime > 0.1:
                    try:
                        atomic_write_jpg(save_location1, frame1)
                        # logger.info("Saved frame to %s", save_location1)
                    except Exception as e:
                        logger.error("Error saving frame: %s", e)
                    starttime = time()

            restartcounter = 3
            sleep(0.02)

            # Periodic reconnect every 60s to refresh decoder (your original)
            # if time() - restart_time > 60:
            #     logger.info("Reinitializing VideoCapture (periodic reconnect).")
            #     try:
            #         cap1.release()
            #         del cap1
            #         gc.collect()
            #     except Exception:
            #         pass

            #     cap1 = cv2.VideoCapture(gst1, cv2.CAP_GSTREAMER)
            #     if not cap1.isOpened():
            #         logger.error("Failed to reopen VideoCapture after periodic reconnect. Exiting.")
            #         del cap1
            #         gc.collect()
            #         sys.exit(1)
            #     logger.info("VideoCapture reopened successfully after periodic reconnect.")
            #     restart_time = time()

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Cleaning up and exiting.")
        try:
            cap1.release()
        except Exception:
            pass
        sys.exit(0)
    except Exception as e:
        logger.exception("Unhandled exception in main loop: %s", e)
        try:
            cap1.release()
        except Exception:
            pass
        sys.exit(1)

if __name__ == "__main__":
    main()

