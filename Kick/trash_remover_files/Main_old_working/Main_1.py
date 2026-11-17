import cv2
import time
import os
import redis
from datetime import datetime
import xml.etree.ElementTree as ET
from ultralytics import YOLO
import numpy as np
import json

tree = ET.parse(r"/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/Config.xml")
root = tree.getroot()
# Model Path
MODEL_PATH = root.find("Model/ModelPath").text.strip()
MODEL = YOLO(MODEL_PATH)
CLASS_NAMES = MODEL.names

class VisionSystem:
    def __init__(self, config_path=r"/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/Config.xml"):
        self.config_path = config_path
        # Load configuration
        self.load_config()
        # Create required folders
        self.create_folders()
        # VideoCapture object
        self.cap = None
        self.engine_rectangles = {}
        self.kick_sequence = []
        self.kick_status = "WAITING"
        self.expected_sequence = ["START", "END", "START"]
        self.cycle_locked = False
        self.last_detected = None
        self.sequence_completed = False
        self.current_region = None
        self.region_counter = 0
        self.region_threshold = 2

        self.region_history = []
        self.history_size = 2
        self.stable_region = None
        self.seq_index = 0
        self.rearm_delay = 0
        self.cooldown_frames = 3

        self.exit_confirmed_frames = 0
        self.exit_confirm_threshold = 8    # frames kick must be outside START to unlock OK

        # NOK: frames kick must be fully outside ALL engine regions
        self.nok_exit_frames = 0
        self.nok_exit_threshold = 15

        # GRACE PERIOD (mid-cycle): frozen window after each step match
        self.grace_frames_after_step = 50
        self.grace_counter = 0

        # POST-RESET GRACE: fixed frame delay after reset before exit-check begins
        self.post_reset_grace_frames = 25
        self.post_reset_counter = 0

        # AWAITING EXIT
        self.awaiting_start_exit = False
        self.start_exit_confirmed = 0
        self.start_exit_threshold = 8

        self.last_frame_time = time.time()
        self.stream_timeout = 5
        self.reconnect_delay = 2
        self.max_reconnect_attempts = 999999

        # Redis Connection
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.result_sent = False
        self.pubsub = self.redis_client.pubsub()
        self.pubsub.subscribe("recheck_trigger")

        # =========================================================
        # INSPECTION COLUMNS — static to frame (fixed pixel coords)
        # Adjust these values to reposition / resize the columns
        # =========================================================
        # RIGHT inspection column
        self.insp_right_x      = 1100   # left edge of the right column
        self.insp_right_y      = 150    # top edge
        self.insp_right_width  = 30     # column width  (pixels)
        self.insp_right_height = 500    # column height (pixels)

        # LEFT inspection column
        self.insp_left_x      = 200     # left edge of the left column
        self.insp_left_y      = 150     # top edge
        self.insp_left_width  = 30      # column width  (pixels)
        self.insp_left_height = 500     # column height (pixels)

        # Crossing-gate state
        # Engine centroid must cross RIGHT first, then LEFT
        self.insp_right_crossed = False   # True once centroid passed through right col
        self.insp_left_crossed  = False   # True once centroid passed through left col (after right)
        self.wait_sent          = False   # guard — send WAIT only once per pass-through

        # VIDEO SETTINGS
        self.fps = 20
        self.pre_video_seconds = 5
        self.post_video_seconds = 5
        self.pre_video_frame_count = (self.fps * self.pre_video_seconds)
        self.post_video_frame_count = (self.fps * self.post_video_seconds)
        self.total_rolling_frames = (self.pre_video_frame_count + self.post_video_frame_count)
        # CREATE ROLLING FRAME FOLDER
        os.makedirs(self.temp_frame_dir, exist_ok=True)
        self.frame_index = 0
        # RECORDING FLAGS
        self.record_ok_post = False
        self.record_nok_post = False
        self.ok_post_counter = 0
        self.nok_post_counter = 0
        self.ok_trigger_frame = 0
        self.nok_trigger_frame = 0
        # NOK TIMER
        self.last_detection_time = time.time()
        self.nok_timeout_seconds = 8

    # ---------------------------------------------------------
    # LOAD XML CONFIG
    # ---------------------------------------------------------
    def load_config(self):
        tree = ET.parse(self.config_path)
        root = tree.getroot()
        # OUTPUT ROOT
        self.output_root = root.find("Paths/OUTPUT_ROOT").text.strip().replace('"', '')
        # OK IMAGE PATH
        self.ok_path = root.find("Paths/OK_IMAGES").text.strip().replace('"', '')
        # OK VIDEO PATH
        self.ok_video_path = root.find("Paths/OK_VIDEOS").text.strip().replace('"', '')
        # NOK VIDEO PATH
        self.nok_video_path = root.find("Paths/NOK_VIDEOS").text.strip().replace('"', '')
        # ROLLING FRAME PATH
        self.temp_frame_dir = root.find("Paths/ROLLING_FRAMES").text.strip().replace('"', '')
        
        self.nok_path    = root.find("Paths/NOK_IMAGES").text.strip()
        self.main_stream = root.find("Stream/MainStream").text.strip()
        self.debug_video = root.find("Stream/DebugVideo").text.strip()
        self.debug_mode  = (root.find("Stream/DebugMode").text.strip().lower() == "true")
        self.stream_url  = (self.debug_video if self.debug_mode else self.main_stream)
        self.model_path  = root.find("Model/ModelPath").text.strip()
        print("=" * 50)
        print("Configuration Loaded")
        print("=" * 50)
        print(f"Debug Mode : {self.debug_mode}")
        print(f"Stream URL : {self.stream_url}")
        print(f"Model Path : {self.model_path}")
        print("=" * 50)
    
    # CREATE OUTPUT FOLDERS
    def create_folders(self):
        print("=" * 60)
        print("CREATING OUTPUT FOLDERS")
        print("=" * 60)
        os.makedirs(self.output_root, exist_ok=True)
        os.makedirs(self.ok_path, exist_ok=True)
        os.makedirs(self.ok_video_path, exist_ok=True)
        os.makedirs(self.nok_video_path, exist_ok=True)
        os.makedirs(self.temp_frame_dir, exist_ok=True)
        os.makedirs(self.nok_path, exist_ok=True)
        print("=" * 60)
    # SAVE ROLLING FRAME TO DISK
    def save_rolling_frame(self, frame):
        frame_name = f"frame_{self.frame_index:06d}.jpg"
        frame_path = os.path.join(self.temp_frame_dir,frame_name)
        cv2.imwrite(frame_path, frame)
        self.frame_index += 1
        # DELETE OLD FRAMES
        min_frame_to_keep = (self.frame_index - self.total_rolling_frames)
        if min_frame_to_keep > 0:
            old_frame_name = (f"frame_{min_frame_to_keep:06d}.jpg")
            old_frame_path = os.path.join(self.temp_frame_dir,old_frame_name)
            if os.path.exists(old_frame_path):
                try:
                    os.remove(old_frame_path)
                except Exception as e:
                    print(f"DELETE ERROR : {e}")
    # SAVE OK IMAGE
    def save_ok_image(self, frame):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_name = f"OK_{timestamp}.jpg"
        save_path = os.path.join(self.ok_path,image_name)
        success = cv2.imwrite(save_path, frame)
        if success:
            print("=" * 60)
            print(f"OK IMAGE SAVED : {save_path}")
            return save_path
        return None
    # EXPORT VIDEO FROM DISK FRAMES
    def export_video_from_disk(self,start_frame,end_frame,output_path):
        print("=" * 60)
        print("EXPORTING VIDEO")
        print(output_path)
        print("=" * 60)
        first_frame = None
        for i in range(start_frame, end_frame + 1):
            frame_name = f"frame_{i:06d}.jpg"
            frame_path = os.path.join(
                self.temp_frame_dir,
                frame_name
            )
            if os.path.exists(frame_path):
                first_frame = cv2.imread(frame_path)
                if first_frame is not None:
                    break
        if first_frame is None:
            print("NO VALID FRAMES FOUND")
            return
        height, width = first_frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(output_path,fourcc,self.fps,(width, height))
        if not writer.isOpened():
            print("VIDEO WRITER FAILED")
            return
        written_frames = 0
        for i in range(start_frame, end_frame + 1):
            frame_name = f"frame_{i:06d}.jpg"
            frame_path = os.path.join(self.temp_frame_dir,frame_name)
            if os.path.exists(frame_path):
                frame = cv2.imread(frame_path)
                if frame is not None:
                    writer.write(frame)
                    written_frames += 1
        writer.release()
        print("=" * 60)
        print(f"VIDEO SAVED : {output_path}")
        print(f"TOTAL FRAMES : {written_frames}")
        print("=" * 60)
    # FINALIZE OK VIDEO
    def finalize_ok_video(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(self.ok_video_path,f"OK_{timestamp}.mp4")
        start_frame = max(0,self.ok_trigger_frame - self.pre_video_frame_count)

        end_frame = (self.ok_trigger_frame + self.post_video_frame_count)
        self.export_video_from_disk(start_frame, end_frame, output_path)
    # FINALIZE NOK VIDEO
    def finalize_nok_video(self):

       timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

       output_path = os.path.join(
         self.nok_video_path,
         f"NOK_{timestamp}.mp4"
    )

       start_frame = max(
        0,
        self.nok_trigger_frame - self.pre_video_frame_count
    )

       end_frame = (
        self.nok_trigger_frame + self.post_video_frame_count
    )

       print("=" * 60)
       print("FINALIZING NOK VIDEO")
       print(f"OUTPUT PATH : {output_path}")
       print("=" * 60)

       self.export_video_from_disk(
        start_frame,
        end_frame,
        output_path
    )

       print("=" * 60)
       print(f"NOK VIDEO SAVED : {output_path}")
       print("=" * 60)

       return output_path

    # =========================================================
    # READ REDIS MESSAGES
    # =========================================================
    def read_redis_messages(self):
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
        self.kick_sequence       = []
        self.seq_index           = 0
        self.kick_status         = "WAITING"
        self.cycle_locked        = False
        self.result_sent         = False
        self.last_detected       = None
        self.region_history      = []
        self.exit_confirmed_frames = 0
        self.nok_exit_frames     = 0
        self.grace_counter       = 0
        self.rearm_delay         = 0
        self.awaiting_start_exit = False
        self.start_exit_confirmed = 0
        self.post_reset_counter  = 0
        # Reset inspection columns too
        self._reset_inspection_columns()
        print("SYSTEM RESET FOR RECHECK")

    # =========================================================
    # SEND RESULT TO IO
    # =========================================================
    def send_result_to_io(self, status, image_path=None, video_path=None):

        try:
            payload = {
                "status": status,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "image_path": image_path if image_path else "",
                "video_path": video_path if video_path else ""
            }

            self.redis_client.publish(
                "inspection_result",
                json.dumps(payload)
            )

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
        """Reset crossing gates for a fresh pass-through."""
        self.insp_right_crossed = False
        self.insp_left_crossed  = False
        self.wait_sent          = False

    def _centroid_in_column(self, cx, cy, col_x, col_y, col_w, col_h):
        """Returns True if point (cx, cy) is inside the column rectangle."""
        return (col_x <= cx <= col_x + col_w) and (col_y <= cy <= col_y + col_h)

    def _draw_inspection_columns(self, frame):
        """Draw the two static inspection columns on every frame."""
        # RIGHT column — cyan
        rx1 = self.insp_right_x
        ry1 = self.insp_right_y
        rx2 = rx1 + self.insp_right_width
        ry2 = ry1 + self.insp_right_height
        right_color = (0, 255, 255) if not self.insp_right_crossed else (0, 200, 0)
        # cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), right_color, 2)
        cv2.putText(frame, "INSP_RIGHT", (rx1 - 10, ry1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, right_color, 1)

        # LEFT column — magenta
        lx1 = self.insp_left_x
        ly1 = self.insp_left_y
        lx2 = lx1 + self.insp_left_width
        ly2 = ly1 + self.insp_left_height
        left_color = (255, 0, 255) if not self.insp_left_crossed else (0, 200, 0)
        # cv2.rectangle(frame, (lx1, ly1), (lx2, ly2), left_color, 2)
        cv2.putText(frame, "INSP_LEFT", (lx1 - 10, ly1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, left_color, 1)

    def _check_inspection_columns(self, engine_cx, engine_cy):
        """
        Call once per frame with the engine centroid.

        Gate logic:
          1. Engine centroid enters RIGHT column  → mark right_crossed
          2. Engine centroid later enters LEFT column (right already crossed)
             AND result has NOT been sent yet → send WAIT, mark wait_sent

        After a result IS sent (OK/NOK) the gate auto-resets on the next
        call to _reset_cycle(), so WAIT is not sent for that pass-through.
        """
        # Step 1 — right crossing
        if not self.insp_right_crossed:
            if self._centroid_in_column(engine_cx, engine_cy,
                                        self.insp_right_x, self.insp_right_y,
                                        self.insp_right_width, self.insp_right_height):
                self.insp_right_crossed = True
                print("[INSP] Engine centroid crossed RIGHT inspection column")

        # Step 2 — left crossing (only after right was crossed)
        elif self.insp_right_crossed and not self.insp_left_crossed:
            if self._centroid_in_column(engine_cx, engine_cy,
                                        self.insp_left_x, self.insp_left_y,
                                        self.insp_left_width, self.insp_left_height):
                self.insp_left_crossed = True
                print("[INSP] Engine centroid crossed LEFT inspection column")

                # If result still not sent by this point → send WAIT
                if not self.result_sent and not self.wait_sent:
                    self.send_result_to_io("WAIT")
                    self.wait_sent = True
                    print("[INSP] WAIT sent — result not received before left column")

    def check_overlap(self, box1, box2):
        x1, y1, x2, y2 = box1
        a1, b1, a2, b2 = box2
        return not (x2 < a1 or x1 > a2 or y2 < b1 or y1 > b2)

    def open_stream(self):
        reconnect_attempt = 0
        while reconnect_attempt < self.max_reconnect_attempts:
            print("=" * 50)
            print(f"Opening Stream : {self.stream_url}")
            print(f"Reconnect Attempt : {reconnect_attempt}")
            print("=" * 50)
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            self.cap = cv2.VideoCapture(self.stream_url)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            time.sleep(1)
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    print("Stream Connected Successfully")
                    self.last_frame_time = time.time()
                    return True
            print("ERROR : Stream Connection Failed")
            reconnect_attempt += 1
            time.sleep(self.reconnect_delay)
        return False

    def reconnect_stream(self):
        print("\n" + "=" * 60)
        print("STREAM LOST")
        print("Reconnecting Stream...")
        print("=" * 60)
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        cv2.destroyAllWindows()
        time.sleep(self.reconnect_delay)
        return self.open_stream()

    def read_frame(self):
        if self.cap is None:
            return False, None
        ret, frame = self.cap.read()
        if ret and frame is not None:
            self.last_frame_time = time.time()
            return True, frame
        print("WARNING : Frame Not Received")
        elapsed = time.time() - self.last_frame_time
        print(f"No Frame Duration : {elapsed:.2f} sec")
        if self.debug_mode:
            print("Restarting Debug Video")
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return False, None
        if elapsed >= self.stream_timeout:
            print("Stream Timeout Detected")
            reconnect_ok = self.reconnect_stream()
            if not reconnect_ok:
                print("Reconnect Failed")
            return False, None
        return False, None

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
        sx1, sy1, sx2, sy2 = self.engine_rectangles["START"]
        return max(kx1, sx1) < min(kx2, sx2) and max(ky1, sy1) < min(ky2, sy2)

    def _reset_cycle(self):
        self.cycle_locked        = False
        self.seq_index           = 0
        self.kick_sequence       = []
        self.kick_status         = "WAITING"
        self.last_detected       = None
        self.region_history      = []
        self.exit_confirmed_frames = 0
        self.nok_exit_frames     = 0
        self.grace_counter       = 0
        self.post_reset_counter  = self.post_reset_grace_frames
        self.awaiting_start_exit = True
        self.start_exit_confirmed = 0
        self.result_sent         = False
        # Reset inspection crossing gates for the new cycle
        self._reset_inspection_columns()

    def run_inference_engine(self, frame):
        objects     = {}
        self.engine_rectangles = {}

        if self.rearm_delay > 0:
            self.rearm_delay -= 1

        results = MODEL.predict(frame, conf=0.6, verbose=False)

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
                    "confidence": confidence
                }

                cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
                cv2.putText(frame, f"{labelname} {confidence:.2f}",
                            (xmin, ymin - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                if labelname == "engine":
                    cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

                    rects = [
                        # {"name": "START", "width": 100, "height": 290, "x_offset":  135},
                        # {"name": "END",   "width": 100, "height": 290, "x_offset": -150}
                        
                        {"name": "START", "width": 100, "height": 290, "x_offset":  100},
                        {"name": "END",   "width": 100, "height": 290, "x_offset": -150}
                      
                    ]
                    start_y = cy + 50

                    for rect in rects:
                        cx_r = cx + rect["x_offset"]
                        x1   = cx_r - rect["width"] // 2
                        y1   = start_y
                        x2   = x1 + rect["width"]
                        y2   = y1 + rect["height"]
                        self.engine_rectangles[rect["name"]] = [x1, y1, x2, y2]
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                        cv2.putText(frame, rect["name"], (x1 - 5, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                        

                    # -------------------------------------------------------
                    # INSPECTION COLUMN CHECK — runs every frame engine seen
                    # -------------------------------------------------------
                    self._check_inspection_columns(cx, cy)

        # Draw the two static columns on every frame regardless of detections
        self._draw_inspection_columns(frame)
        self.save_rolling_frame(frame)
        # =========================================================
        # RECORD NOK POST VIDEO STATUS
        # =========================================================
        if self.record_nok_post:

            self.nok_post_counter += 1

            cv2.putText(
                frame,
                "RECORDING NOK VIDEO",
                (20, 250),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2
            )

            # Stop recording indicator after post frames
            if self.nok_post_counter >= self.post_video_frame_count:

                self.record_nok_post = False

                print("=" * 60) 
                print("NOK POST RECORDING COMPLETE")
                print("=" * 60)

        # =========================================================
        # RECORD OK POST VIDEO STATUS
        # =========================================================
        if self.record_ok_post:

            self.ok_post_counter += 1

            cv2.putText(
                frame,
                "RECORDING OK VIDEO",
                (20, 200),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2
            )

            # Stop recording after post frames
            if self.ok_post_counter >= self.post_video_frame_count:

                self.record_ok_post = False

                self.finalize_ok_video()

                print("=" * 60)
                print("OK POST RECORDING COMPLETE")
                print("=" * 60)         

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
        # NOK CHECK
        # =========================================================
        if (
            self.seq_index > 0 and
            self.grace_counter == 0 and
            "kick" in objects and
            self.engine_rectangles
        ):

            # Kick completely outside all regions
            if not self._kick_in_any_region(objects["kick"]["bbox"]):
                self.nok_exit_frames += 1
            else:
                self.nok_exit_frames = 0

            # NOK confirmed
            if self.nok_exit_frames >= self.nok_exit_threshold:

                self.kick_status = "NOK"
                self.cycle_locked = True

                self.record_nok_post = True
                self.nok_post_counter = 0

                self.nok_trigger_frame = self.frame_index

                self.nok_exit_frames = 0

                print("=" * 60)
                print("NOK DETECTED")
                print("=" * 60)

                # -------------------------------------------------
                # SAVE VIDEO + SEND RESULT ONLY ONCE
                # -------------------------------------------------
                if not self.result_sent:

                    # Save video
                    video_path = self.finalize_nok_video()

                    print(f"NOK VIDEO PATH : {video_path}")

                    # Send result to IO
                    self.send_result_to_io(
                        "NOK",
                        video_path=video_path
                    )

                    self.result_sent = True

                # Reset sequence
                self.seq_index = 0
                self.kick_sequence = []
                self.last_detection_time = time.time()

        
        
        # =========================================================
        # SEQUENCE LOGIC (START → END → START)
        # =========================================================
        if "kick" in objects and not self.cycle_locked and self.rearm_delay == 0:
            kx1, ky1, kx2, ky2 = objects["kick"]["bbox"]
            current_regions = []

            for region_name, region_box in self.engine_rectangles.items():
                rx1, ry1, rx2, ry2 = region_box
                if max(kx1, rx1) < min(kx2, rx2) and max(ky1, ry1) < min(ky2, ry2):
                    current_regions.append(region_name)

            if len(current_regions) > 0:
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
                        self.seq_index     += 1
                        self.last_detected  = stable
                        self.nok_exit_frames = 0
                        self.grace_counter  = self.grace_frames_after_step
                else:
                    self.last_detected = None

        # =========================================================
        # CYCLE COMPLETE → OK
        # =========================================================
        if self.seq_index >= len(self.expected_sequence):

            self.kick_status = "OK"

            self.record_ok_post = True
            self.ok_post_counter = 0

            self.ok_trigger_frame = self.frame_index

            self.kick_sequence = []

            self.last_detection_time = time.time()

            self.cycle_locked = True

            self.rearm_delay = self.cooldown_frames

            if not self.result_sent:

                self.ok_image_path = self.save_ok_image(frame)

                self.send_result_to_io(
                    "OK",
                    image_path=self.ok_image_path
                )

                self.result_sent = True

           
        # =========================================================
        # DISPLAY
        # =========================================================
        cv2.putText(frame, f"SEQ : {' -> '.join(self.kick_sequence)}",
                    (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        cv2.putText(frame, f"STATUS : {self.kick_status}", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (0, 255, 0) if self.kick_status == "OK" else (0, 0, 255), 2)
        if self.grace_counter > 0:
            cv2.putText(frame, f"GRACE  : {self.grace_counter}",
                        (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

        # Show inspection crossing state on frame
        insp_str = (
            f"INSP : {'R✓' if self.insp_right_crossed else 'R-'} "
            f"{'L✓' if self.insp_left_crossed else 'L-'}"
        )
        cv2.putText(frame, insp_str, (20, 190),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

        return frame, objects
        
    # =========================================================
    # AI READY STATUS
    # =========================================================
    def ai_ready_status(self, status):

        try:
            payload = {
                "ai_status": status,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            self.redis_client.publish(
                "ai_status",
                json.dumps(payload)
            )

        except Exception as e:
            print(f"[AI STATUS ERROR] {e}")

    def run(self):
        if not self.open_stream():
            print("Initial Stream Connection Failed")
            return
        while True:
            self.read_redis_messages()
            if self.cap is None or not self.cap.isOpened():
                print("Capture Closed")
                reconnect_ok = self.reconnect_stream()
                if not reconnect_ok:
                    print("Reconnect Failed")
                    time.sleep(1)
                    self.ai_ready_status("AI_NOT_READY")
                continue
            ret, frame = self.read_frame()
            if not ret:
                self.ai_ready_status("AI_NOT_READY")
                time.sleep(0.05)
                continue
            inf_frame, objects = self.run_inference_engine(frame)
            print(objects)
            self.ai_ready_status("AI_READY")
            cv2.imshow("live frame", inf_frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
        self.ai_ready_status("AI_NOT_READY")
        self.cleanup()

    def cleanup(self):
        if self.cap is not None:
            self.cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    app = VisionSystem()
    app.run()