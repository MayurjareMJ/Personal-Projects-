#########################################
#REDIS_HANDLER.PY FOR REDIS COMMUNICAION
##########################################
import cv2
import numpy as np
import time
import os
from datetime import datetime
import threading
import queue

from database_handler import insert_vision_result
from redis_handler import RedisHandler
from flask import Flask, Response

latest_frame = None
frame_lock = threading.Lock()
# =========================================================
# FLASK APP
# =========================================================
app = Flask(__name__)

# =========================
# THREAD QUEUES
# =========================
frame_queue = queue.Queue(maxsize=10)

db_queue = queue.Queue()

image_queue = queue.Queue()

def flask_stream_worker():
    global latest_frame_bytes

    while True:
        frame = frame_queue.get()

        frame = cv2.resize(frame, (1280, 720))

        _, buffer = cv2.imencode('.jpg', frame)

        with frame_lock:
            latest_frame_bytes = buffer.tobytes()
# =========================
# CREATE IMAGE FOLDERS
# =========================
os.makedirs("inspection_results/ok_images", exist_ok=True)
os.makedirs("inspection_results/nok_images", exist_ok=True)

# =========================
# GLOBAL VARIABLES
# =========================
last_inspection_status = None
prev_gray = None

# =========================
# DB STATE TRACKING
# =========================
last_running_state = None
last_bypass_state = None
last_recheck_state = None
last_manual_pass_state = None


# =========================
# ROI CONFIG
# =========================
ROI_X1 = 500
ROI_Y1 = 300

ROI_X2 = 1200
ROI_Y2 = 700
# =========================
# REDIS HANDLER
# =========================
redis_handler = RedisHandler()

# =========================
# VIDEO STREAM
# =========================
STREAM_URL = "tcp://127.0.0.1:7000"

sock_stream = cv2.VideoCapture(STREAM_URL)

if not sock_stream.isOpened():
    print("Failed to open stream")
    exit()

# =========================
# MOTION DETECTION
# =========================
def detect_motion(frame):

    global prev_gray

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    gray = cv2.GaussianBlur(
        gray,
        (21, 21),
        0
    )

    # =========================
    # FIRST FRAME
    # =========================
    if prev_gray is None:

        prev_gray = gray

        return False

    # =========================
    # FRAME DIFFERENCE
    # =========================
    diff = cv2.absdiff(
        prev_gray,
        gray
    )

    _, thresh = cv2.threshold(
        diff,
        25,
        255,
        cv2.THRESH_BINARY
    )

    motion = np.sum(thresh) > 50000

    prev_gray = gray

    return motion


def save_image(frame, status, recheck=False):

    ts = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    if status == "OK":

        if recheck:
            image_path = f"inspection_results/ok_images/ok_{ts}.jpg"
        else:
            image_path = f"inspection_results/nok_images/nok_{ts}.jpg"

    else:

        if recheck:
            image_path = f"inspection_results/ok_images/recheck_ok_{ts}.jpg"
        else:
            image_path = f"inspection_results/nok_images/recheck_nok_{ts}.jpg"

    # MULTI-THREAD IMAGE SAVE
    image_queue.put(
        (image_path, frame.copy())
    )

    return image_path

# =========================
# DATABASE INSERT
# =========================
def insert_result(
    frame,
    status,
    inference_time,
    recheck="NO"
):

    image_path = save_image(
        frame,
        status,
        recheck == "YES"
    )

    data = {
        "model_name": "KICK_001",
        "station_id": "ST01",
        "inspection_status": status,
        "image_path": image_path,
        "video_path": None,
        "image_inference_time": inference_time,
        "bypassed": (
            "YES"
            if redis_handler.bypass_state
            else "NO"
        ),
        "manual_pass": (
            "YES"
            if redis_handler.manual_pass_triggered
            else "NO"
        ),
        "recheck": recheck
    }

    db_queue.put(data)

# =========================
# RECHECK LOGIC
# =========================
def run_recheck():

    global prev_gray
    global sock_stream

    print("[VISION] RECHECK STARTED")

    # =========================
    # RESET MOTION HISTORY
    # =========================
    prev_gray = None

    time.sleep(0.5)

    # =========================
    # CAPTURE 2 FRAMES
    # =========================
    try:

        frame1 = frame_queue.get(timeout=1)

        time.sleep(0.1)

        frame2 = frame_queue.get(timeout=1)

    except queue.Empty:

        print("[VISION] RECHECK FRAME ERROR")

        return

    # =========================
    # INITIALIZE
    # =========================
    detect_motion(frame1)

    # =========================
    # ACTUAL MOTION CHECK
    # =========================
    start_time = time.time()

    roi_frame = frame2[
        ROI_Y1:ROI_Y2,
        ROI_X1:ROI_X2
    ]

    motion = detect_motion(roi_frame)

    inference_time = int(
        (time.time() - start_time) * 1000
    )

    recheck_status = (
        "NOK"
        if motion
        else "OK"
    )

    print(
        f"[VISION] RECHECK RESULT → {recheck_status}"
    )

    # =========================
    # SAVE RECHECK RESULT
    # =========================
    insert_result(
        frame2,
        recheck_status,
        inference_time,
        recheck="YES"
    )
    # =========================
    # RECHECK PASSED
    # =========================
    if recheck_status == "OK":

        print(
            "[VISION] RECHECK PASSED → START CONVEYOR"
        )

        redis_handler.publish_event(
            "START_CONVEYOR",
            True
        )

        redis_handler.waiting_for_recheck_result = False

        redis_handler.last_sent_stop = False

    # =========================
    # RECHECK FAILED
    # =========================
    else:

        print(
            "[VISION] RECHECK FAILED → KEEP STOPPED"
        )

        redis_handler.publish_event(
            "STOP_CONVEYOR",
            True
        )

        redis_handler.waiting_for_recheck_result = True

        redis_handler.last_sent_stop = True

# =========================
# CAMERA CAPTURE THREAD
# =========================
def capture_frames():

    global sock_stream
    global latest_frame

    while True:

        ret, frame = sock_stream.read()

        if not ret:

            print("Frame not received. Reconnecting...")

            sock_stream.release()

            time.sleep(1)

            sock_stream = cv2.VideoCapture(STREAM_URL)

            continue

        # ✅ THIS IS THE PART YOU ASKED ABOUT
        with frame_lock:
            latest_frame = frame.copy()

        # optional small sleep to reduce CPU load
        time.sleep(0.01)

# ========================
# DATABASE THREAD
# =========================
def db_worker():

    while True:

        data = db_queue.get()

        try:

            insert_vision_result(data)

            print("[DB] Inserted")

        except Exception as e:

            print("[DB ERROR]", e)

        db_queue.task_done()

# =========================
# IMAGE SAVE THREAD
# =========================
def image_saver_worker():

    while True:

        image_path, frame = image_queue.get()

        try:

            cv2.imwrite(image_path, frame)
            
            print(f"[IMAGE] Saved → {image_path}")

        except Exception as e:

            print("[IMAGE ERROR]", e)

        image_queue.task_done()


# =========================================================
# FLASK ROUTES
# =========================================================
@app.route('/')
def index():

    return """
    <html>

    <head>

        <title>VISION UI</title>

    </head>

    <body style="background:black;text-align:center;">

        <h1 style="color:white;">
            LIVE INFERENCE STREAM
        </h1>

        <img src="/video_feed" width="1200">

    </body>

    </html>
    """
@app.route('/video_feed')
def video_feed():

    def generate():
        global latest_frame

        while True:

            with frame_lock:
                if latest_frame is None:
                    continue
                frame = latest_frame.copy()

            _, buffer = cv2.imencode('.jpg', frame)

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buffer.tobytes() +
                b'\r\n'
            )

            time.sleep(0.03)

    return Response(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

# =========================
# MAIN LOOP
# =========================
def main():

    # ========================
    # START THREADS
    # =========================
    threading.Thread(
        target=capture_frames,
        daemon=True
    ).start()

    threading.Thread(
        target=image_saver_worker,
        daemon=True
    ).start()

    threading.Thread(
        target=db_worker,
        daemon=True
    ).start()
    threading.Thread(target=flask_stream_worker, daemon=True).start()
    global last_inspection_status
    global sock_stream

    global last_running_state
    global last_bypass_state
    global last_recheck_state
    global last_manual_pass_state



    # =========================
    # START REDIS LISTENER
    # =========================
    redis_handler.start_listener()

    while True:

        if frame_queue.empty():

            time.sleep(0.01)

            continue

        frame = frame_queue.get()
        
        

        # =========================
        # DEFAULT STATUS
        # =========================
        status = "WAIT"

        start_time = time.time()

        # =========================
        # NORMAL INSPECTION
        # =========================
        if (
            redis_handler.conveyor_state
            and not redis_handler.waiting_for_recheck_result
        ):
            

            # =========================
            # CROP ROI
            # =========================
            roi_frame = frame[
                ROI_Y1:ROI_Y2,
                ROI_X1:ROI_X2
            ]

            motion = detect_motion(roi_frame)

            status = (
                "NOK"
                if motion
                else "OK"
            )

        inference_time = int(
            (time.time() - start_time) * 1000
        )

        conveyor_on = redis_handler.conveyor_state

        print(
            f"Status={status} | Conveyor={conveyor_on}"
        )

        # =========================
        # INSERT ONLY ON CHANGE
        # =========================
        should_insert = (
            conveyor_on
            and status != "WAIT"
            and status != last_inspection_status
        )

        if should_insert:

            insert_result(
                frame,
                status,
                inference_time,
                recheck="NO"
            )

            last_inspection_status = status

        # =========================
        # RESET LAST STATUS
        # =========================
        if not conveyor_on:

            last_inspection_status = None

        # =========================
        # NOK DETECTED
        # =========================
        if (
            conveyor_on
            and not redis_handler.waiting_for_recheck_result
            and status == "NOK"
            and not redis_handler.bypass_state
            and not redis_handler.manual_pass_triggered
            and not redis_handler.last_sent_stop
        ):

            print(
                "[VISION] NOK DETECTED → STOP CONVEYOR"
            )

            redis_handler.publish_event(
                "STOP_CONVEYOR",
                True
            )

            redis_handler.waiting_for_recheck_result = True

            redis_handler.last_sent_stop = True


        # =========================
        # BYPASS / MANUAL PASS
        # =========================
        if redis_handler.waiting_for_recheck_result:

            # =========================
            # BYPASS RECEIVED
            # =========================
            if redis_handler.bypass_state:

                print(
                    "[VISION] BYPASS ENABLED → START CONVEYOR"
                )

                redis_handler.publish_event(
                    "START_CONVEYOR",
                    True
                )

                redis_handler.waiting_for_recheck_result = False

                redis_handler.last_sent_stop = False

            # =========================
            # MANUAL PASS RECEIVED
            # =========================
            elif redis_handler.manual_pass_triggered:

                print(
                    "[VISION] MANUAL PASS → START CONVEYOR"
                )

                redis_handler.publish_event(
                    "START_CONVEYOR",
                    True
                )

                redis_handler.waiting_for_recheck_result = False

                redis_handler.last_sent_stop = False
        # =========================
        # RUN RECHECK
        # =========================
        if (
            redis_handler.waiting_for_recheck_result
            and redis_handler.recheck_requested
        ):

            print(
                "[VISION] RECHECK TRIGGER RECEIVED"
            )

            redis_handler.recheck_requested = False

            run_recheck()

        # # =========================
        # # MANUAL PASS LOGIC
        # # =========================
        # if (
        #     redis_handler.waiting_for_recheck_result
        #     and redis_handler.manual_pass_triggered
        # ):

        #     print(
        #         "[VISION] MANUAL PASS → START CONVEYOR"
        #     )

        #     redis_handler.publish_event(
        #         "START_CONVEYOR",
        #         True
        #     )

        #     redis_handler.waiting_for_recheck_result = False

        #     redis_handler.last_sent_stop = False

        #     # IMPORTANT
        #     last_inspection_status = None

        #     # CONSUME MANUAL PASS
        #     redis_handler.manual_pass_triggered = False

        # =========================
        # RESET MANUAL PASS
        # =========================
        if (
            not redis_handler.waiting_for_recheck_result
            and redis_handler.manual_pass_triggered
        ):

            print(
                "[VISION] Manual pass consumed"
            )

            redis_handler.manual_pass_triggered = False

        # =========================
        # DISPLAY
        # =========================
        color = (0, 0, 255) if status == "NOK" else (0, 255, 0)

        # =========================
        # DRAW ROI BOX
        # =========================
        cv2.rectangle(
            frame,
            (ROI_X1, ROI_Y1),
            (ROI_X2, ROI_Y2),
            (0, 255, 255),
            2
        )

        cv2.putText(frame, status, (50, 80),cv2.FONT_HERSHEY_SIMPLEX, 2, color, 4)
        cv2.putText(frame,f"Conveyor: {'ON' if conveyor_on else 'OFF'}",(50, 140),cv2.FONT_HERSHEY_SIMPLEX,1,(255, 255, 0),2)


        frame_resize = cv2.resize(frame, (1280, 720))
        cv2.imshow("Live Stream", frame_resize)
        

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    sock_stream.release()
    cv2.destroyAllWindows()

# =========================================================
# ENTRY
# =========================================================
if __name__ == "__main__":

    # =====================================================
    # START FLASK SERVER
    # =====================================================
    threading.Thread(
        target=lambda: app.run(
            host='0.0.0.0',
            port=8000,
            debug=False,
            use_reloader=False
        ),
        daemon=True
    ).start()

    # =====================================================
    # START MAIN
    # =====================================================
    main()
