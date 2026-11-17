import cv2
import time
import os
import redis
from datetime import datetime
import xml.etree.ElementTree as ET
from ultralytics import YOLO
import numpy as np
import json
import threading
from collections import deque
from flask import Flask, Response

# =============================================================
# LOAD MODEL (global, once)
# =============================================================
tree = ET.parse(r"/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/Config.xml")
root = tree.getroot()
MODEL_PATH  = root.find("Model/ModelPath").text.strip()
MODEL       = YOLO(MODEL_PATH)
MODEL.to("cuda")                    # ← Force GPU
CLASS_NAMES = MODEL.names
print(f"[MODEL] Running on device : {next(MODEL.model.parameters()).device}")

# =============================================================
# BACKGROUND FRAME GRABBER  (decouples capture from inference)
# =============================================================
class FrameGrabber(threading.Thread):
    """
    Runs in a daemon thread.
    Always holds the LATEST frame so inference never waits on I/O.
    """
    def __init__(self, cap):
        super().__init__(daemon=True)
        self.cap   = cap
        self.frame = None
        self.lock  = threading.Lock()
        self.alive = True
        
    def run(self):
        while self.alive:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.frame = frame
            else:
                time.sleep(0.005)

    def get_frame(self):
        with self.lock:
            #return self.frame.copy() if self.frame is not None else None #MJ
            return self.frame if self.frame is not None else None

    def stop(self):
        self.alive = False


# =============================================================
# MAIN VISION SYSTEM
# =============================================================
class VisionSystem:
    def __init__(self, config_path=r"/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/Config.xml"):
        self.config_path = config_path

        # Load configuration
        self.load_config()
        # ── SINGLE ROI BLOCK (START + END combined) ──────────────
        self.roi_x_offset   = -50      # shifts the WHOLE box horizontally (relative to engine cx)
        self.roi_y_offset   =  50      # shifts the WHOLE box vertically — TOP edge offset from engine cy
        self.roi_width      = 500      # total width of the box (START + END combined)
        self.roi_height      = 290      # height of the box — applies to BOTH START and END since it's one rectangle
        self.roi_partition  = 0.5      # fraction of width given to START (0.3 = narrow START, wide END)
        self.roi_start_side = "right"  # which side of the partition is START: "left" or "right"

        # Create required folders (no rolling-frame folder needed)
        self.create_folders()

        # VideoCapture / grabber
        self.cap     = None
        self.grabber = None

        # ── Engine / Kick state ──────────────────────────────
        self.engine_rectangles   = {}
        self.kick_sequence       = []
        self.kick_status         = "WAITING"
        self.expected_sequence   = ["START", "END", "START"]
        self.cycle_locked        = False
        self.last_detected       = None
        self.sequence_completed  = False
        self.current_region      = None
        self.region_counter      = 0
        self.region_threshold    = 2

        self.region_history      = []
        self.history_size        = 2
        self.stable_region       = None
        self.seq_index           = 0
        self.rearm_delay         = 0
        self.cooldown_frames     = 3

        self.exit_confirmed_frames  = 0
        self.exit_confirm_threshold = 8

        self.nok_exit_frames     = 0
        self.nok_exit_threshold  = 15

        self.grace_frames_after_step = 50
        self.grace_counter           = 0

        self.post_reset_grace_frames = 25
        self.post_reset_counter      = 0

        self.awaiting_start_exit  = False
        self.start_exit_confirmed = 0
        self.start_exit_threshold = 8

        # ── Stream health ────────────────────────────────────
        self.last_frame_time       = time.time()
        self.stream_timeout        = 5
        self.reconnect_delay       = 2
        self.max_reconnect_attempts = 999999

        # ── Redis ────────────────────────────────────────────
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.result_sent  = False
        self.pubsub       = self.redis_client.pubsub()
        self.pubsub.subscribe("recheck_trigger")
        # Throttle Redis polling — check at most every N frames
        self._redis_frame_counter = 0
        self._redis_poll_every    = 5          # poll once every 5 frames

        # ── Inspection columns ───────────────────────────────
        self.insp_right_x      = 1100
        self.insp_right_y      = 150
        self.insp_right_width  = 30
        self.insp_right_height = 500

        self.insp_left_x       = 200
        self.insp_left_y       = 150
        self.insp_left_width   = 30
        self.insp_left_height  = 500

        self.insp_right_crossed = False
        self.insp_left_crossed  = False
        self.wait_sent          = False
        # ── UI frame slot (720p JPEG, written every frame) ───
        # UI process reads self.ui_jpeg_bytes at its own rate
        self.ui_jpeg_bytes  = None
        self.ui_frame_lock  = threading.Lock()
        self.ui_jpeg_quality = 60              # UI display quality
        self._ui_redis_every = 3               # push UI frame to Redis every N frames
        self._ui_redis_counter = 0
        # Separate Redis client without decode_responses for binary frame data
        self.redis_binary = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)


        # NOK timer (kept for NOK detection logic, no video saved)
        self.last_detection_time = time.time()
        self.nok_timeout_seconds = 8

    # =========================================================
    # LOAD XML CONFIG
    # =========================================================
    def load_config(self):
        tree = ET.parse(self.config_path)
        root = tree.getroot()
        self.output_root   = root.find("Paths/OUTPUT_ROOT").text.strip().replace('"', '')
        self.ok_path       = root.find("Paths/OK_IMAGES").text.strip().replace('"', '')
        self.ok_video_path = root.find("Paths/OK_VIDEOS").text.strip().replace('"', '')
        self.nok_video_path = root.find("Paths/NOK_VIDEOS").text.strip().replace('"', '')
        self.nok_path      = root.find("Paths/NOK_IMAGES").text.strip()
        self.main_stream   = root.find("Stream/MainStream").text.strip()
        self.debug_video   = root.find("Stream/DebugVideo").text.strip()
        self.debug_mode    = (root.find("Stream/DebugMode").text.strip().lower() == "true")
        self.stream_url    = self.debug_video if self.debug_mode else self.main_stream
        self.model_path    = root.find("Model/ModelPath").text.strip()
        print("=" * 50)
        print("Configuration Loaded")
        print("=" * 50)
        print(f"Debug Mode : {self.debug_mode}")
        print(f"Stream URL : {self.stream_url}")
        print(f"Model Path : {self.model_path}")
        print("=" * 50)

    # =========================================================
    # CREATE OUTPUT FOLDERS
    # =========================================================
    def create_folders(self):
        print("=" * 60)
        print("CREATING OUTPUT FOLDERS")
        print("=" * 60)
        os.makedirs(self.output_root,    exist_ok=True)
        os.makedirs(self.ok_path,        exist_ok=True)
        os.makedirs(self.nok_path,       exist_ok=True)
        # NOTE: No temp_frame_dir — we use in-memory buffer now
        print("=" * 60)
    # ========================================================
    # SAVE OK IMAGE
    # =========================================================
    def save_ok_image(self, frame):
        date_folder = datetime.now().strftime("%Y-%m-%d")
        save_dir = os.path.join(self.ok_path, date_folder)
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_name = f"OK_{timestamp}.jpg"
        save_path = os.path.join(save_dir, image_name)
        # success = cv2.imwrite(save_path, frame)
        # if success:
        #     print("=" * 60)
        #     print(f"OK IMAGE SAVED : {save_path}")
        #     print("=" * 60)
        #     return save_path
        # else:
        #     print("FAILED TO SAVE OK IMAGE")
        #     return None
        save_frame = frame.copy()
        cv2.putText(
            save_frame,
            "SEQUENCE : START -> END -> START",
            (20, 250),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 255, 0),
            2
        )
        cv2.putText(
            save_frame,
            "RESULT : OK",
            (20, 290),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            3
        )
        success = cv2.imwrite(save_path, save_frame)
    # # =========================================================
    # # SAVE NOK IMAGE
    # # =========================================================
    def save_nok_image(self, frame):
        date_folder = datetime.now().strftime("%Y-%m-%d")
        save_dir = os.path.join(self.nok_path, date_folder)
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_name = f"NOK_{timestamp}.jpg"
        save_path = os.path.join(save_dir, image_name)
        # success = cv2.imwrite(save_path, frame)
        # if success:
        #     print("=" * 60)
        #     print(f"NOK IMAGE SAVED : {save_path}")
        #     print("=" * 60)
        #     return save_path
        # else:
        #     print("FAILED TO SAVE NOK IMAGE")
        #     return None
        save_frame = frame.copy()
        seq_text = " -> ".join(self.kick_sequence)
        cv2.putText(
            save_frame,
            f"SEQUENCE : {seq_text}",
            (20, 250),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 255),
            2
        )
        cv2.putText(
            save_frame,
            "RESULT : NOK",
            (20, 290),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            3
        )
        success = cv2.imwrite(save_path, save_frame)
        
    # =========================================================
    # READ REDIS MESSAGES  (throttled — not every frame)
    # =========================================================
    def read_redis_messages(self):
        self._redis_frame_counter += 1
        if self._redis_frame_counter < self._redis_poll_every:
            return
        self._redis_frame_counter = 0
        try:
            message = self.pubsub.get_message()
            if message and message["type"] == "message":
                channel = message["channel"]
                data    = message["data"]
                print("===================================")
                print(f"CHANNEL : {channel}")
                print(f"DATA    : {data}")
                if channel == "recheck_trigger":
                    self.handle_recheck()
        except Exception as e:
            print(f"[REDIS ERROR] {e}")

    # =========================================================
    # HANDLE RECHECK
    # =========================================================
    def handle_recheck(self):
        print("\n" + "=" * 60)
        print("RECHECK INITIATED")
        print("=" * 60)
        self.kick_sequence        = []
        self.seq_index            = 0
        self.kick_status          = "WAITING"
        self.cycle_locked         = False
        self.result_sent          = False
        self.last_detected        = None
        self.region_history       = []
        self.exit_confirmed_frames = 0
        self.nok_exit_frames      = 0
        self.grace_counter        = 0
        self.rearm_delay          = 0
        self.awaiting_start_exit  = False
        self.start_exit_confirmed = 0
        self.post_reset_counter   = 0
        self._reset_inspection_columns()
        print("SYSTEM RESET FOR RECHECK")

    # =========================================================
    # SEND RESULT TO IO
    # =========================================================
    def send_result_to_io(self, status, image_path=None, video_path=None):
        try:
            payload = {
                "status":     status,
                "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "image_path": image_path if image_path else "",
                "video_path": video_path if video_path else ""
            }
            self.redis_client.publish("inspection_result", json.dumps(payload))
            print("=" * 60)
            print("RESULT SENT TO IO")
            print(json.dumps(payload, indent=4))
            print("=" * 60)
        except Exception as e:
            print(f"[SEND RESULT ERROR] {e}")

    # =========================================================
    # INSPECTION COLUMN HELPERS
    # =========================================================
    def _reset_inspection_columns(self):
        self.insp_right_crossed = False
        self.insp_left_crossed  = False
        self.wait_sent          = False

    def _centroid_in_column(self, cx, cy, col_x, col_y, col_w, col_h):
        return (col_x <= cx <= col_x + col_w) and (col_y <= cy <= col_y + col_h)

    def _draw_inspection_columns(self, frame):
        rx1 = self.insp_right_x
        ry1 = self.insp_right_y
        right_color = (0, 255, 255) if not self.insp_right_crossed else (0, 200, 0)
        cv2.putText(frame, "INSP_RIGHT", (rx1 - 10, ry1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, right_color, 1)
        lx1 = self.insp_left_x
        ly1 = self.insp_left_y
        left_color = (255, 0, 255) if not self.insp_left_crossed else (0, 200, 0)
        cv2.putText(frame, "INSP_LEFT", (lx1 - 10, ly1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, left_color, 1)

    def _check_inspection_columns(self, engine_cx, engine_cy):
        if not self.insp_right_crossed:
            if self._centroid_in_column(engine_cx, engine_cy,
                                        self.insp_right_x, self.insp_right_y,
                                        self.insp_right_width, self.insp_right_height):
                self.insp_right_crossed = True
                print("[INSP] Engine centroid crossed RIGHT inspection column")
        elif self.insp_right_crossed and not self.insp_left_crossed:
            if self._centroid_in_column(engine_cx, engine_cy,
                                        self.insp_left_x, self.insp_left_y,
                                        self.insp_left_width, self.insp_left_height):
                self.insp_left_crossed = True
                print("[INSP] Engine centroid crossed LEFT inspection column")
                if not self.result_sent and not self.wait_sent:
                    self.send_result_to_io("WAIT")
                    self.wait_sent = True
                    print("[INSP] WAIT sent — result not received before left column")

    # =========================================================
    # STREAM MANAGEMENT
    # =========================================================
    def open_stream(self):
        reconnect_attempt = 0
        while reconnect_attempt < self.max_reconnect_attempts:
            print("=" * 50)
            print(f"Opening Stream       : {self.stream_url}")
            print(f"Reconnect Attempt    : {reconnect_attempt}")
            print("=" * 50)
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            self.cap = cv2.VideoCapture(self.stream_url)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)   # slightly larger — avoids starvation
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            time.sleep(1)
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    print("Stream Connected Successfully")
                    self.last_frame_time = time.time()
                    # Start / restart background grabber
                    if self.grabber and self.grabber.is_alive():
                        self.grabber.stop()
                    self.grabber = FrameGrabber(self.cap)
                    self.grabber.start()
                    return True
            print("ERROR : Stream Connection Failed")
            reconnect_attempt += 1
            time.sleep(self.reconnect_delay)
        return False

    def reconnect_stream(self):
        print("\n" + "=" * 60)
        print("STREAM LOST — Reconnecting...")
        print("=" * 60)
        if self.grabber:
            self.grabber.stop()
            self.grabber = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        cv2.destroyAllWindows()
        time.sleep(self.reconnect_delay)
        return self.open_stream()

    def read_frame(self):
        """Non-blocking — returns latest frame from grabber thread."""
        frame = self.grabber.get_frame() if self.grabber else None
        if frame is not None:
            self.last_frame_time = time.time()
            return True, frame
        elapsed = time.time() - self.last_frame_time
        if self.debug_mode:
            # For debug video, restart if exhausted
            if elapsed > 1.0:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return False, None
        if elapsed >= self.stream_timeout:
            print("Stream Timeout Detected")
            self.reconnect_stream()
        return False, None

    # =========================================================
    # REGION HELPERS
    # =========================================================
    def _kick_in_any_region(self, kick_bbox):
        kx1, ky1, kx2, ky2 = kick_bbox
        for region_box in self.engine_rectangles.values():
            rx1, ry1, rx2, ry2 = region_box
            if max(kx1, rx1) < min(kx2, rx2) and max(ky1, ry1) < min(ky2, ry2):
                return True
        return False

    def _kick_in_start(self, kick_bbox):
        if "START" not in self.engine_rectangles:
            return False
        kx1, ky1, kx2, ky2 = kick_bbox
        sx1, sy1, sx2, sy2  = self.engine_rectangles["START"]
        return max(kx1, sx1) < min(kx2, sx2) and max(ky1, sy1) < min(ky2, sy2)

    # =========================================================
    # RESET CYCLE
    # =========================================================
    def _reset_cycle(self):
        self.cycle_locked         = False
        self.seq_index            = 0
        self.kick_sequence        = []
        self.kick_status          = "WAITING"
        self.last_detected        = None
        self.region_history       = []
        self.exit_confirmed_frames = 0
        self.nok_exit_frames      = 0
        self.grace_counter        = 0
        self.post_reset_counter   = self.post_reset_grace_frames
        self.awaiting_start_exit  = True
        self.start_exit_confirmed = 0
        self.result_sent          = False
        self._reset_inspection_columns()

    # =========================================================
    # MAIN INFERENCE ENGINE
    # =========================================================
    def run_inference_engine(self, frame):
        objects            = {}
        self.engine_rectangles = {}

        if self.rearm_delay > 0:
            self.rearm_delay -= 1

        # ── YOLO inference (GPU) ─────────────────────────────
        # results = MODEL.predict(frame, conf=0.8, verbose=False, device=0)
        results = MODEL(frame, conf=0.65, verbose=False) #MJ

        for result in results:
            for box in result.boxes:
                cls_id    = int(box.cls[0])
                labelname = CLASS_NAMES[cls_id]
                xmin, ymin, xmax, ymax = map(int, box.xyxy[0])
                confidence = float(box.conf[0])
                cx = int((xmin + xmax) / 2)
                cy = int((ymin + ymax) / 2)

                objects[labelname] = {
                    "bbox":       [xmin, ymin, xmax, ymax],
                    "center":     [cx, cy],
                    "confidence": confidence}

                cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
                cv2.putText(frame, f"{labelname} {confidence:.2f}",
                            (xmin, ymin - 10), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (0, 255, 0), 2)

                if labelname == "engine":
                    cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
                    # ── SINGLE BLOCK, PARTITIONED INTO START | END ───────────
                    blk_x1 = cx + self.roi_x_offset - self.roi_width // 2
                    blk_y1 = cy + self.roi_y_offset
                    blk_x2 = blk_x1 + self.roi_width
                    blk_y2 = blk_y1 + self.roi_height
                    mid_x  = blk_x1 + int(self.roi_width * self.roi_partition)

                    if self.roi_start_side == "right":
                        start_box = [mid_x,  blk_y1, blk_x2, blk_y2]
                        end_box   = [blk_x1, blk_y1, mid_x,  blk_y2]
                    else:
                        start_box = [blk_x1, blk_y1, mid_x,  blk_y2]
                        end_box   = [mid_x,  blk_y1, blk_x2, blk_y2]

                    self.engine_rectangles["START"] = start_box
                    self.engine_rectangles["END"]   = end_box

                    # Draw outer block
                    cv2.rectangle(frame, (blk_x1, blk_y1), (blk_x2, blk_y2), (255, 0, 0), 2)

                    # Draw partition line
                    cv2.line(frame, (mid_x, blk_y1), (mid_x, blk_y2), (0, 255, 255), 2)

                    # Labels
                    cv2.putText(frame, "START", (start_box[0] + 5, blk_y1 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    cv2.putText(frame, "END", (end_box[0] + 5, blk_y1 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    
                    # Inspection column check
                    self._check_inspection_columns(cx, cy)

        self._draw_inspection_columns(frame)
        # ── UI frame → Redis 'live_frame' (720p, every 3rd frame) ──
        self.push_ui_frame(frame)

        # =========================================================
        # UNLOCK CHECK — OK cycle
        # =========================================================
        if self.cycle_locked and self.kick_status == "OK":
            kick_outside_start = True
            if "kick" in objects and "START" in self.engine_rectangles:
                if self._kick_in_start(objects["kick"]["bbox"]):
                    kick_outside_start = False
                    self.exit_confirmed_frames = 0
            if kick_outside_start:
                self.exit_confirmed_frames += 1
            if self.exit_confirmed_frames >= self.exit_confirm_threshold:
                self._reset_cycle()

        # =========================================================
        # UNLOCK CHECK — NOK cycle
        # (No video saved — just reset when kick exits all regions)
        # =========================================================
        if self.cycle_locked and self.kick_status == "NOK":
            kick_outside_all = True
            if "kick" in objects and self.engine_rectangles:
                if self._kick_in_any_region(objects["kick"]["bbox"]):
                    kick_outside_all = False
                    self.nok_exit_frames = 0
            if kick_outside_all:
                self.nok_exit_frames += 1
            if self.nok_exit_frames >= self.nok_exit_threshold:
                self._reset_cycle()

        # =========================================================
        # BLOCK IF LOCKED OR COOLDOWN
        # =========================================================
        if self.cycle_locked or self.rearm_delay > 0:
            cv2.putText(frame, f"SEQ : {' -> '.join(self.kick_sequence)}",
                        (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            cv2.putText(frame, f"STATUS : {self.kick_status}", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1,
                        (0, 255, 0) if self.kick_status == "OK" else (0, 0, 255), 2)
            return frame, objects

        # =========================================================
        # POST-RESET GRACE COUNTDOWN
        # =========================================================
        if self.post_reset_counter > 0:
            self.post_reset_counter -= 1
            cv2.putText(frame, "SEQ : ", (20, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            cv2.putText(frame, "STATUS : WAITING", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            return frame, objects

        # =========================================================
        # AWAITING START EXIT GATE
        # =========================================================
        if self.awaiting_start_exit:
            kick_clear_of_start = True
            if "kick" in objects and self.engine_rectangles:
                if self._kick_in_start(objects["kick"]["bbox"]):
                    kick_clear_of_start = False
                    self.start_exit_confirmed = 0
            if kick_clear_of_start:
                self.start_exit_confirmed += 1
            if self.start_exit_confirmed >= self.start_exit_threshold:
                self.awaiting_start_exit  = False
                self.start_exit_confirmed = 0
                self.region_history       = []
            cv2.putText(frame, "SEQ : ", (20, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            cv2.putText(frame, "STATUS : WAITING", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame,
                        f"WAIT EXIT START : {self.start_exit_confirmed}/{self.start_exit_threshold}",
                        (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 0), 2)
            return frame, objects

        # =========================================================
        # GRACE PERIOD COUNTDOWN (mid-cycle)
        # =========================================================
        if self.grace_counter > 0:
            self.grace_counter  -= 1
            self.nok_exit_frames = 0

        # =========================================================
        # NOK DETECTION
        # (result sent to IO, NO video/image saved)
        # =========================================================
        if (
            self.seq_index > 0 and
            self.grace_counter == 0 and
            "kick" in objects and
            self.engine_rectangles
        ):
            if not self._kick_in_any_region(objects["kick"]["bbox"]):
                self.nok_exit_frames += 1
            else:
                self.nok_exit_frames = 0

            if self.nok_exit_frames >= self.nok_exit_threshold:
                self.kick_status  = "NOK"
                self.cycle_locked = True
                self.nok_exit_frames = 0

                print("=" * 60)
                print("NOK DETECTED")
                print("=" * 60)

                # if not self.result_sent:
                #     # Send NOK result — no image/video paths
                #     self.send_result_to_io("NOK")
                #     self.result_sent = True

                if not self.result_sent:
                    # SAVE NOK IMAGE
                    self.nok_image_path = self.save_nok_image(frame)
                    # SEND RESULT
                    self.send_result_to_io("NOK",image_path=self.nok_image_path)
                    self.result_sent = True

                self.seq_index           = 0
                self.kick_sequence       = []
                self.last_detection_time = time.time()

        # =========================================================
        # SEQUENCE LOGIC  (START → END → START)
        # =========================================================
        if "kick" in objects and not self.cycle_locked and self.rearm_delay == 0:
            kx1, ky1, kx2, ky2 = objects["kick"]["bbox"]
            current_regions = []

            for region_name, region_box in self.engine_rectangles.items():
                rx1, ry1, rx2, ry2 = region_box
                if max(kx1, rx1) < min(kx2, rx2) and max(ky1, ry1) < min(ky2, ry2):
                    current_regions.append(region_name)

            if current_regions:
                priority = ["START", "END"]
                detected = None
                for p in priority:
                    if p in current_regions:
                        detected = p
                        break

                self.region_history.append(detected)
                if len(self.region_history) > self.history_size:
                    self.region_history.pop(0)

                stable   = max(set(self.region_history), key=self.region_history.count)
                expected = self.expected_sequence[self.seq_index]

                if stable == expected:
                    if len(self.kick_sequence) == 0 or self.kick_sequence[-1] != stable:
                        self.kick_sequence.append(stable)
                        self.seq_index      += 1
                        self.last_detected   = stable
                        self.nok_exit_frames = 0
                        self.grace_counter   = self.grace_frames_after_step
                else:
                    self.last_detected = None

        # =========================================================
        # CYCLE COMPLETE → OK
        # =========================================================
        if self.seq_index >= len(self.expected_sequence):
            self.kick_status      = "OK"
            # self.record_ok_post   = True
            # self.ok_post_counter  = 0
            # self.ok_trigger_frame = self.frame_index
            self.kick_sequence    = []
            self.last_detection_time = time.time()
            self.cycle_locked     = True
            self.rearm_delay      = self.cooldown_frames

            if not self.result_sent:
                self.ok_image_path = self.save_ok_image(frame)
                self.send_result_to_io("OK", image_path=self.ok_image_path)
                self.result_sent = True

        # =========================================================
        # DISPLAY OVERLAY
        # =========================================================
        cv2.putText(frame, f"SEQ : {' -> '.join(self.kick_sequence)}",
                    (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        cv2.putText(frame, f"STATUS : {self.kick_status}", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (0, 255, 0) if self.kick_status == "OK" else (0, 0, 255), 2)
        if self.grace_counter > 0:
            cv2.putText(frame, f"GRACE  : {self.grace_counter}",
                        (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

        insp_str = (
            f"INSP : {'R✓' if self.insp_right_crossed else 'R-'} "
            f"{'L✓' if self.insp_left_crossed else 'L-'}"
        )
        cv2.putText(frame, insp_str, (20, 190),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

        return frame, objects


    def push_ui_frame(self, frame):
        self._ui_redis_counter += 1

        if self._ui_redis_counter < self._ui_redis_every:
            return

        self._ui_redis_counter = 0

        try:
            small = cv2.resize(frame, (1280, 720))

            _, buf = cv2.imencode(
                '.jpg',
                small,
                [cv2.IMWRITE_JPEG_QUALITY, self.ui_jpeg_quality]
            )

            self.redis_binary.set(
                'live_frame',
                buf.tobytes(),
                ex=2
            )

        except Exception as e:
            print(f"[UI FRAME ERROR] {e}")
    # =========================================================
    # AI READY STATUS
    # =========================================================
    def ai_ready_status(self, status):
        try:
            payload = {
                "ai_status": status,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.redis_client.publish("ai_status", json.dumps(payload))
        except Exception as e:
            print(f"[AI STATUS ERROR] {e}")

    # =========================================================
    # MAIN INFERENCE LOOP  (runs in its own thread)
    # =========================================================
    def run(self):
        if not self.open_stream():
            print("Initial Stream Connection Failed")
            return

        while True:
            self.read_redis_messages()

            if self.cap is None or not self.cap.isOpened():
                print("Capture Closed")
                ok = self.reconnect_stream()
                if not ok:
                    print("Reconnect Failed")
                    time.sleep(1)
                    self.ai_ready_status("AI_NOT_READY")
                continue

            ret, frame = self.read_frame()
            if not ret:
                self.ai_ready_status("AI_NOT_READY")
                time.sleep(0.005)
                continue

            inf_frame, objects = self.run_inference_engine(frame)
            # cv2.imshow("Inference", inf_frame)

            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break
            print(objects)
            self.ai_ready_status("AI_READY")

    # =========================================================
    # CLEANUP
    # =========================================================
    def cleanup(self):
        if self.grabber:
            self.grabber.stop()
        if self.cap is not None:
            self.cap.release()


# =============================================================
# FLASK APP
# =============================================================
flask_app = Flask(__name__)

# Shared state updated by the Redis listener thread
_flask_state = {
    "ai_status":   "—",
    "last_result": "—",
    "timestamp":   "—"
}
_flask_state_lock = threading.Lock()


def _redis_status_listener():
    """Background thread — keeps _flask_state in sync with Redis pubsub."""
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    ps = r.pubsub()
    ps.subscribe("ai_status", "inspection_result")
    for msg in ps.listen():
        if msg["type"] != "message":
            continue
        try:
            data = json.loads(msg["data"])
            with _flask_state_lock:
                if msg["channel"] == "ai_status":
                    _flask_state["ai_status"] = data.get("ai_status", "—")
                    _flask_state["timestamp"]  = data.get("timestamp", "—")
                elif msg["channel"] == "inspection_result":
                    _flask_state["last_result"] = data.get("status", "—")
                    _flask_state["timestamp"]   = data.get("timestamp", "—")
        except Exception:
            pass


def _mjpeg_generator():
    """
    Pulls latest JPEG from Redis key 'live_frame' and yields
    it as a multipart MJPEG stream.  Browser <img src="/video_feed">
    renders each part as the next video frame.
    """
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)
    while True:
        try:
            jpg = r.get('live_frame')
            if jpg:
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    jpg +
                    b'\r\n'
                )
            else:
                time.sleep(0.05)
                continue
        except Exception:
            time.sleep(0.1)
        # ~15 fps to browser — no need to stream faster
        time.sleep(1 / 15)


@flask_app.route('/video_feed')
def video_feed():
    return Response(
        _mjpeg_generator(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@flask_app.route('/status')
def status():
    with _flask_state_lock:
        return json.dumps(dict(_flask_state))


# =============================================================
# ENTRY POINT
# =============================================================
if __name__ == "__main__":
    vision = VisionSystem()

    # 1 — Inference loop in a background daemon thread
    inference_thread = threading.Thread(target=vision.run, daemon=True)
    inference_thread.start()
    print("=" * 60)
    print("INFERENCE THREAD STARTED")
    print("=" * 60)

    # 2 — Redis status listener (keeps Flask status endpoint fresh)
    listener_thread = threading.Thread(target=_redis_status_listener, daemon=True)
    listener_thread.start()

    # 3 — Flask on main thread  →  http://0.0.0.0:5000
    print("=" * 60)
    print("FLASK SERVER  →  http://0.0.0.0:5000")
    print("=" * 60)
    flask_app.run(
        host='0.0.0.0',
        port=5000,
        threaded=True,
        use_reloader=False      # MUST be False — reloader forks and breaks YOLO/CUDA
    )