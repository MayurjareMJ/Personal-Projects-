import time
time.sleep(60)
import sys
sys.path.insert(0, '/home/etpl/VISION/test-cell4')
from shared_frame import FrameWriter
import cv2
import time
import xml.etree.ElementTree as ET
from ultralytics import YOLO
from datetime import date, datetime
import os
from pathlib import Path
import torch
import json
import numpy as np
import gc
from queue import Queue
import threading
import logging
from logging.handlers import RotatingFileHandler

from Camera_Fetcher import CameraFetcher

# ---------- logging ----------
LOG_DIR  = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "ai_main.log")

logger = logging.getLogger("vision_logger")
logger.setLevel(logging.WARNING)
handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(handler)

# ---------- config ----------
path_conf_file = ET.parse('/home/etpl/VISION/test-cell4/config/congfig.xml') 
root = path_conf_file.getroot()

MODEL_PATH    = root.find("MODELPATH").text
SOURCE_1      = root.find("CAM1RTSP").text
SOURCE_2      = root.find("CAM2RTSP").text

SAVE_PATH_1   = root.find("CAM1SAVEPATH").text
SAVE_PATH_2   = root.find("CAM2SAVEPATH").text
INCIDENT_BASE = root.find("INCIDENTDATASAVEPATH").text
RECORD_BASE   = root.find("INCIDENTRECORDSAVEPATH").text

CAM1NUM       = root.find("CAM1NUM").text
CAM2NUM       = root.find("CAM2NUM").text
CAM1LOCATION  = root.find("CAM1LOCATION").text
CAM2LOCATION  = root.find("CAM2LOCATION").text

TRIGGERLOCATION   = root.find("TRIGGERLOCATION").text
AILIVE            = os.path.join(TRIGGERLOCATION, "AILIVE.txt")
EMERGENCYTRIGGER  = os.path.join(TRIGGERLOCATION, "EMERGENCY.txt")

# ---------- inference size ----------
# Change only these two values to resize inference input.
# Bboxes will be automatically scaled back to original frame size for drawing + saving.
INFER_W = 320
INFER_H = 320

# ---------- hazard state ----------
CONFIRM_FRAMES  = 2
COOLDOWN_FRAMES = 0

hazard_state = {
    "CAM1": {"fire": {"count": 0, "cooldown": 0},
             "oil":  {"count": 0, "cooldown": 0},
             "ppe":  {"count": 0, "cooldown": 0}},
    "CAM2": {"fire": {"count": 0, "cooldown": 0},
             "oil":  {"count": 0, "cooldown": 0},
             "ppe":  {"count": 0, "cooldown": 0}},
}

def check_and_trigger(cam_id, hazard_name, detected):
    state = hazard_state[cam_id][hazard_name]
    if state["cooldown"] > 0:
        state["cooldown"] -= 1
        return False
    if detected:
        state["count"] += 1
    else:
        state["count"] = 0
    if state["count"] >= CONFIRM_FRAMES:
        state["count"] = 0
        state["cooldown"] = COOLDOWN_FRAMES
        return True
    return False

# ---------- async JSON writer ----------
event_queue = Queue()

def json_writer_worker():
    while True:
        data, path = event_queue.get()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
            print("-" * 80)
            print("written:", path)
            print("-" * 80)
        except Exception as e:
            logger.exception(f"JSON write failed: {e}")
        finally:
            event_queue.task_done()

threading.Thread(target=json_writer_worker, daemon=True).start()

# ---------- helpers ----------
def save_incident_frame(cam_num, frame):
    today = date.today()
    save_dir = os.path.join(INCIDENT_BASE, str(today))
    os.makedirs(save_dir, exist_ok=True)
    img_name = f"CAM_{cam_num}_{time.time()}.jpg"
    save_path = os.path.join(save_dir, img_name)
    cv2.imwrite(save_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return save_path

def get_bbox_centroid(xmin, ymin, xmax, ymax):
    return (xmin + xmax) / 2, (ymin + ymax) / 2

def scale_box(xmin, ymin, xmax, ymax, scale_x, scale_y):
    """Scale bbox coords from inference space back to original frame space."""
    return (
        int(xmin * scale_x),
        int(ymin * scale_y),
        int(xmax * scale_x),
        int(ymax * scale_y),
    )

# ---------- inference ----------
def process_camera_frames(model, frames_dict, class_names, use_cuda):
    pred_device = 0 if use_cuda else "cpu"
    cam_ids     = list(frames_dict.keys())

    # ── Step 1: keep original frames for drawing, resize copies for inference ──
    orig_frames   = [frames_dict[c][0] for c in cam_ids]   # 1920×1080 — for annotation + save
    infer_frames  = [
        cv2.resize(f, (INFER_W, INFER_H), interpolation=cv2.INTER_LINEAR)
        for f in orig_frames
    ]   # 320×320 — sent to YOLO

    # ── Step 2: inference on small frames ─────────────────────────────────────
    with torch.inference_mode():
        all_results = model.predict(
            infer_frames,
            conf=0.50,
            imgsz=320,          # lock YOLO to 320 — prevents internal upscale to 640
            device=pred_device,
            half=use_cuda,
            verbose=False,
        )

    output = {}

    for idx, cam_id in enumerate(cam_ids):
        frame, cam_num, _ = frames_dict[cam_id]        # original full-res frame
        orig_h, orig_w    = frame.shape[:2]            # e.g. 1080, 1920

        # ── Step 3: compute scale factors ─────────────────────────────────────
        # YOLO boxes are in INFER_W×INFER_H space → scale up to orig_w×orig_h
        scale_x = orig_w / INFER_W   # e.g. 1920 / 320 = 6.0
        scale_y = orig_h / INFER_H   # e.g. 1080 / 320 = 3.375

        boxes = all_results[idx].boxes

        fire_smoke_status   = False
        oil_spillage_status = False
        ppe_absent_status   = False
        persons     = []
        no_wearings = []

        for box in boxes:
            labelname = class_names[int(box.cls)]

            # raw coords are in 320×320 space
            xmin_s, ymin_s, xmax_s, ymax_s = (int(box.data[0][i]) for i in range(4))

            # scale back to original frame space for drawing
            xmin, ymin, xmax, ymax = scale_box(xmin_s, ymin_s, xmax_s, ymax_s, scale_x, scale_y)

            if labelname in ("fire", "smoke") and not fire_smoke_status:
                cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2, cv2.LINE_AA)
                cv2.putText(frame, labelname, (xmin, ymin - 3), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                fire_smoke_status = True

            elif labelname == "oil_spillage" and not oil_spillage_status:
                cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2, cv2.LINE_AA)
                cv2.putText(frame, labelname, (xmin, ymin - 3), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                oil_spillage_status = True

            elif labelname == "person":
                # store already-scaled coords
                persons.append([xmin, ymin, xmax, ymax])

            elif labelname in ("no_hat", "no_glove"):
                # store already-scaled coords
                no_wearings.append([xmin, ymin, xmax, ymax])

        # ── PPE check — all coords already in original frame space ────────────
        for person in persons:
            p_xmin, p_ymin, p_xmax, p_ymax = person
            person_ppe_absent = False
            for no_obj in no_wearings:
                cx, cy = get_bbox_centroid(*no_obj)
                if p_xmin <= cx <= p_xmax and p_ymin <= cy <= p_ymax:
                    person_ppe_absent = True
                    ppe_absent_status = True
                    break
            if person_ppe_absent:
                cv2.rectangle(frame, (p_xmin, p_ymin), (p_xmax, p_ymax), (0, 0, 255), 2, cv2.LINE_AA)
                cv2.putText(frame, "PPE ABSENT", (p_xmin, p_ymin - 3), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # ── Save only annotated frame (single write per event) ────────────────
        save_path = None
        if fire_smoke_status or oil_spillage_status or ppe_absent_status:
            save_path = save_incident_frame(cam_num, frame)   # annotated, full-res

        output[cam_id] = (fire_smoke_status, oil_spillage_status, ppe_absent_status, frame, save_path)

    del all_results, infer_frames
    if use_cuda:
        torch.cuda.synchronize()
        torch.cuda.empty_cache()

    return output

# ---------- trigger handler ----------
def handle_triggers(cam_id, cam_location, fire_status, oil_status, ppe_status, save_path):
    events_to_check = [
        ("fire", fire_status, "fire_smoke_detected"),
        ("oil",  oil_status,  "oil_spillage_detected"),
        ("ppe",  ppe_status,  "ppe_absent_detected"),
    ]
    for hazard_key, status, event_name in events_to_check:
        if check_and_trigger(cam_id, hazard_key, status):
            try:
                with open(EMERGENCYTRIGGER, 'x'):
                    pass
            except FileExistsError:
                continue

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = os.path.join(RECORD_BASE, f"record_{timestamp}.json")
            os.makedirs(os.path.dirname(json_path), exist_ok=True)

            event_queue.put(({
                "camera_id":     cam_id,
                "event":         event_name,
                "timestamp":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "location":      cam_location,
                "img_save_path": save_path,
            }, json_path))

# ---------- main ----------
def main():
    try:
        print("checking device...")
        use_cuda = torch.cuda.is_available()
        device   = "cuda:0" if use_cuda else "cpu"
        print(f"device -> {device}")

        print("loading model...")
        model = YOLO(MODEL_PATH)
        if use_cuda:
            model.to("cuda")
            print("model moved to GPU")
        class_names = model.names
        print("class names:", class_names)
        print(f"inference size: {INFER_W}x{INFER_H}")

        cam1 = CameraFetcher(rtsp_url=SOURCE_1, name="CAM1", reconnect_attempts=3, fps=2)
        time.sleep(2)
        cam2 = CameraFetcher(rtsp_url=SOURCE_2, name="CAM2", reconnect_attempts=3, fps=2)

        if cam1.cap is None:
            print("WARNING: CAM1 not available at startup — will retry in loop")
        if cam2.cap is None:
            print("WARNING: CAM2 not available at startup — will retry in loop")

        print("cameras initialized")
        frame_count = 0
        frame_writer = FrameWriter()

        try:
            while True:
                Path(AILIVE).touch()
                starttime = time.time()

                ret1, frame1 = cam1.read()
                ret2, frame2 = cam2.read()

                frames_dict = {}
                if ret1 and frame1 is not None:
                    frames_dict["CAM1"] = (frame1, CAM1NUM, CAM1LOCATION)
                if ret2 and frame2 is not None:
                    frames_dict["CAM2"] = (frame2, CAM2NUM, CAM2LOCATION)
                if ret1 and frame1 is not None:
                    frames_dict["CAM1"] = (frame1, CAM1NUM, CAM1LOCATION)
                    _, buf = cv2.imencode('.jpg', frame1, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    frame_writer.write("CAM1", buf.tobytes())

                if ret2 and frame2 is not None:
                    frames_dict["CAM2"] = (frame2, CAM2NUM, CAM2LOCATION)
                    _, buf = cv2.imencode('.jpg', frame2, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    frame_writer.write("CAM2", buf.tobytes())

                if frames_dict:
                    results = process_camera_frames(model, frames_dict, class_names, use_cuda)

                    if "CAM1" in results:
                        fire1, oil1, ppe1, _, save1 = results["CAM1"]
                        handle_triggers("CAM1", CAM1LOCATION, fire1, oil1, ppe1, save1)

                    if "CAM2" in results:
                        fire2, oil2, ppe2, _, save2 = results["CAM2"]
                        handle_triggers("CAM2", CAM2LOCATION, fire2, oil2, ppe2, save2)

                frame_count += 1
                if frame_count % 100 == 0:
                    gc.collect()
                    if use_cuda:
                        torch.cuda.empty_cache()
                    frame_count = 0

                print(f"loop time: {time.time() - starttime:.3f}s")

        finally:
            cam1.release()
            cam2.release()
            cv2.destroyAllWindows()
            frame_writer.close()
            print("cameras released")

    except Exception as e:
        logger.exception(f"Error occurred: {e}")


if __name__ == "__main__":
    main()
