import cv2
import time
import xml.etree.ElementTree as ET
import os
import numpy as np
from videoCapture import VideoCapture

# ---------------- Load config ----------------
path_conf_file = ET.parse('/home/test-cell7/VISION/config/congfig.xml')
root = path_conf_file.getroot()

# ---------------- RTSP Sources ----------------
SOURCE_1 = "rtsp://admin:Sanjeev%40321@192.168.1.214:554/Streaming/Channels/101"
# SOURCE_2 = "rtsp://admin:Sanjeev%40321@192.168.1.140:554/Streaming/Channels/101"

SAVE_PATH_1 = root.find("CAM1SAVEPATH").text
# SAVE_PATH_2 = root.find("CAM2SAVEPATH").text


RECONNECT_INTERVAL = 60  # seconds


# ---------------- GStreamer Pipeline ----------------
def get_gst_pipeline(source):
    return (
        f"rtspsrc location={source} protocols=tcp latency=0 drop-on-latency=true ! "
        "rtpjitterbuffer latency=0 drop-on-latency=true ! "
        "rtph265depay ! h265parse disable-passthrough=true ! "
        "nvv4l2decoder enable-max-performance=1 drop-frame-interval=1 ! "
        "nvvidconv ! video/x-raw,format=BGRx ! "
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink sync=false drop=true max-buffers=1"
    )


# ---------------- Atomic JPG Write ----------------
def atomic_write_jpg(path, frame, quality=60):
    tmp_path = path
    tmp_path = tmp_path.replace(".jpg",".tmp")

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]

    ok, buf = cv2.imencode(".jpg", frame, encode_param)
    if not ok:
        return

    with open(tmp_path, "wb") as f:
        f.write(buf.tobytes())
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, path)
    print(path)


# ---------------- Main Loop ----------------
def main():
    cam1 = VideoCapture(get_gst_pipeline(SOURCE_1))
    # cam2 = VideoCapture(get_gst_pipeline(SOURCE_2))

    last_reconnect = time.time()

    print("RTSP streams started")

    while True:
        now = time.time()

        # 🔥 PERIODIC RECONNECT
        if now - last_reconnect > RECONNECT_INTERVAL:
            print("Reconnecting RTSP streams...")

            cam1.release()
            # cam2.release()

            time.sleep(0.5)  # allow GStreamer cleanup

            cam1 = VideoCapture(get_gst_pipeline(SOURCE_1))
            # cam2 = VideoCapture(get_gst_pipeline(SOURCE_2))

            last_reconnect = now
            print("Reconnected")

        start = time.time()

        ret1, frame1 = cam1.read()
        if ret1 and frame1 is not None:
            atomic_write_jpg(SAVE_PATH_1, frame1)

        # ret2, frame2 = cam2.read()
        # if ret2 and frame2 is not None:
        #     atomic_write_jpg(SAVE_PATH_2, frame2)

        print("Frame time:", round(time.time() - start, 3))
        time.sleep(0.01)



if __name__ == "__main__":
    main()

