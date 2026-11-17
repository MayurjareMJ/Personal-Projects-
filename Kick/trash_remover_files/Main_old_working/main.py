import cv2
import time
import os
import redis
from datetime import datetime
import xml.etree.ElementTree as ET
from ultralytics import YOLO
import numpy as np

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

        self.exit_confirmed_frames = 1
        self.exit_confirm_threshold = 1
        self.nok_exit_frames = 1
        self.nok_exit_threshold = 1


        self.exit_confirmed_frames = 0
        self.exit_confirm_threshold = 8    # frames kick must be outside START to unlock OK

        # NOK: frames kick must be fully outside ALL engine regions
        self.nok_exit_frames = 15
        self.nok_exit_threshold = 15

        # GRACE PERIOD (mid-cycle): frozen window after each step match
        # prevents false NOK when kick briefly exits regions between steps
        self.grace_frames_after_step = 50
        self.grace_counter = 0


        # POST-RESET GRACE: fixed frame delay after reset before exit-check begins
        self.post_reset_grace_frames = 25
        self.post_reset_counter = 0

        # AWAITING EXIT: after reset + post-reset grace, we wait here until
        # the kick has fully left the START region before allowing a new cycle.
        # This is the key flag that prevents START being re-matched immediately.
        self.awaiting_start_exit = False
        self.start_exit_confirmed = 0
        self.start_exit_threshold = 8   # frames outside START to confirm clear

        self.last_frame_time = time.time()
        self.stream_timeout = 5          # seconds
        self.reconnect_delay = 2         # seconds
        self.max_reconnect_attempts = 999999

        # Redis Connection 
        self.redis_client = redis.Redis(host='localhost',port=6379,db=0,decode_responses=True)
        self.result_sent = False
        self.pubsub = self.redis_client.pubsub()
        self.pubsub.subscribe("recheck_trigger")


    # ---------------------------------------------------------
    # LOAD XML CONFIG
    # ---------------------------------------------------------
    def load_config(self):
        tree = ET.parse(self.config_path)
        root = tree.getroot()
        # Paths
        self.ok_path = root.find("Paths/OK_IMAGES").text.strip()
        self.nok_path = root.find("Paths/NOK_IMAGES").text.strip()
        # Stream settings
        self.main_stream = root.find("Stream/MainStream").text.strip()
        self.debug_video = root.find("Stream/DebugVideo").text.strip()
        self.debug_mode = (root.find("Stream/DebugMode").text.strip().lower() == "true")
        self.stream_url = (self.debug_video if self.debug_mode else self.main_stream)
        # Model
        self.model_path = root.find("Model/ModelPath").text.strip()
        print("=" * 50)
        print("Configuration Loaded")
        print("=" * 50)
        print(f"Debug Mode : {self.debug_mode}")
        print(f"Stream URL : {self.stream_url}")
        print(f"Model Path : {self.model_path}")
        print("=" * 50)

    def send_result_to_io(self, result):
        try:
            self.redis_client.publish("LISTEN_EVERYTHING",result)
            print(f"RESULT SENT : {result}")
        except Exception as e:
            print(f"REDIS ERROR : {e}")
    
    def ai_ready_status(self, result):
        try:
            self.redis_client.publish("ai_ready_status",result)
            print(f"RESULT SENT : {result}")
        except Exception as e:
            print(f"REDIS ERROR : {e}")

    # =========================================================
    # READ REDIS MESSAGES
    # =========================================================
    def read_redis_messages(self):
        try:
            message = self.pubsub.get_message()
            if message and message["type"] == "message":
                channel = message["channel"]
                data = message["data"]
                print("===================================")
                print(f"CHANNEL : {channel}")
                print(f"DATA    : {data}")
                # ============================================
                # RECHECK RECEIVED
                # ============================================
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
        # RESET COMPLETE CYCLE STATE
        self.kick_sequence = []
        self.seq_index = 0
        self.kick_status = "WAITING"
        self.cycle_locked = False
        self.result_sent = False
        self.last_detected = None
        self.region_history = []
        self.exit_confirmed_frames = 0
        self.nok_exit_frames = 0
        self.grace_counter = 0
        self.rearm_delay = 0
        self.awaiting_start_exit = False
        self.start_exit_confirmed = 0
        self.post_reset_counter = 0
        print("SYSTEM RESET FOR RECHECK")

    def check_overlap(self, box1, box2):
        x1, y1, x2, y2 = box1
        a1, b1, a2, b2 = box2
        return not (
            x2 < a1 or
            x1 > a2 or
            y2 < b1 or
            y1 > b2
        )

    def create_folders(self):
        os.makedirs(self.ok_path, exist_ok=True)
        os.makedirs(self.nok_path, exist_ok=True)

    def open_stream(self):
        reconnect_attempt = 0
        while reconnect_attempt < self.max_reconnect_attempts:
            print("=" * 50)
            print(f"Opening Stream : {self.stream_url}")
            print(f"Reconnect Attempt : {reconnect_attempt}")
            print("=" * 50)
            # Release old object
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            self.cap = cv2.VideoCapture(self.stream_url)
            # Reduce latency
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Optional for RTSP/GStreamer
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            time.sleep(1)
            if self.cap.isOpened():
                # Test frame
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
        # -------------------------------------------------
        # VALID FRAME
        # -------------------------------------------------
        if ret and frame is not None:
            self.last_frame_time = time.time()
            return True, frame
        # -------------------------------------------------
        # FRAME FAILED
        # -------------------------------------------------
        print("WARNING : Frame Not Received")
        elapsed = time.time() - self.last_frame_time
        print(f"No Frame Duration : {elapsed:.2f} sec")
        # -------------------------------------------------
        # DEBUG VIDEO MODE
        # -------------------------------------------------
        if self.debug_mode:
            print("Restarting Debug Video")
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return False, None
        # -------------------------------------------------
        # LIVE STREAM MODE
        # -------------------------------------------------
        if elapsed >= self.stream_timeout:
            print("Stream Timeout Detected")
            reconnect_ok = self.reconnect_stream()
            if not reconnect_ok:
                print("Reconnect Failed")
            return False, None
        return False, None

    def _kick_in_any_region(self, kick_bbox):
        """Returns True if kick overlaps with ANY engine region (START or END)."""
        kx1, ky1, kx2, ky2 = kick_bbox
        for region_box in self.engine_rectangles.values():
            rx1, ry1, rx2, ry2 = region_box
            ix1 = max(kx1, rx1)
            iy1 = max(ky1, ry1)
            ix2 = min(kx2, rx2)
            iy2 = min(ky2, ry2)
            if ix1 < ix2 and iy1 < iy2:
                return True
        return False

    def _kick_in_start(self, kick_bbox):
        """Returns True if kick overlaps specifically with START region."""
        if "START" not in self.engine_rectangles:
            return False
        kx1, ky1, kx2, ky2 = kick_bbox
        sx1, sy1, sx2, sy2 = self.engine_rectangles["START"]
        ix1 = max(kx1, sx1)
        iy1 = max(ky1, sy1)
        ix2 = min(kx2, sx2)
        iy2 = min(ky2, sy2)
        return ix1 < ix2 and iy1 < iy2

    def _reset_cycle(self):
        """Full reset. Arms post-reset grace then awaiting-exit gate."""
        self.cycle_locked = False
        self.seq_index = 0
        self.kick_sequence = []
        self.kick_status = "WAITING"
        self.last_detected = None
        self.region_history = []
        self.exit_confirmed_frames = 0
        self.nok_exit_frames = 0
        self.grace_counter = 0
        self.post_reset_counter = self.post_reset_grace_frames
        # Gate: sequence logic stays blocked until kick leaves START
        self.awaiting_start_exit = True
        self.start_exit_confirmed = 0
        self.result_sent = False

    def run_inference_engine(self, frame):
        objects = {}
        region_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        self.engine_rectangles = {}

        # -----------------------------
        # Cooldown handling
        # -----------------------------
        if self.rearm_delay > 0:
            self.rearm_delay -= 1

        results = MODEL.predict(frame, conf=0.6, verbose=False)

        for result in results:
            for box in result.boxes:

                cls_id = int(box.cls[0])
                labelname = CLASS_NAMES[cls_id]

                xmin, ymin, xmax, ymax = map(int, box.xyxy[0])
                confidence = float(box.conf[0])

                cx = int((xmin + xmax) / 2)
                cy = int((ymin + ymax) / 2)

                objects[labelname] = {
                    "bbox": [xmin, ymin, xmax, ymax],
                    "center": [cx, cy],
                    "confidence": confidence
                }

                # DRAW DETECTIONS
                cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
                cv2.putText(
                    frame,
                    f"{labelname} {confidence:.2f}",
                    (xmin, ymin - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2
                )

                # ENGINE REGION CREATION
                if labelname == "engine":

                    cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

                    rects = [
                        {"name": "START", "width": 100, "height": 290, "x_offset": 135},
                        {"name": "END",   "width": 100, "height": 290, "x_offset": -150}
                    ]

                    start_y = cy + 50

                    for rect in rects:

                        cx_r = cx + rect["x_offset"]

                        x1 = cx_r - rect["width"] // 2
                        y1 = start_y
                        x2 = x1 + rect["width"]
                        y2 = y1 + rect["height"]

                        self.engine_rectangles[rect["name"]] = [x1, y1, x2, y2]

                        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                        cv2.putText(
                            frame,
                            rect["name"],
                            (x1 - 5, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (255, 255, 0),
                            2
                        )
                        cv2.rectangle(region_mask, (x1, y1), (x2, y2), 255, -1)

        # =========================================================
        # UNLOCK CHECK (OK cycle) — kick must exit START for
        # exit_confirm_threshold consecutive frames
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
        # UNLOCK CHECK (NOK cycle) — kick must exit ALL regions for
        # nok_exit_threshold consecutive frames
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
        # BLOCK SEQUENCE LOGIC IF LOCKED OR COOLDOWN ACTIVE
        # =========================================================
        if self.cycle_locked or self.rearm_delay > 0:
            cv2.putText(
                frame,
                f"SEQ : {' -> '.join(self.kick_sequence)}",
                (20, 100),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 0),
                2
            )
            cv2.putText(
                frame,
                f"STATUS : {self.kick_status}",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0) if self.kick_status == "OK" else (0, 0, 255),
                2
            )
            return frame, objects

        # =========================================================
        # POST-RESET GRACE COUNTDOWN (fixed frame delay)
        # =========================================================
        if self.post_reset_counter > 0:
            self.post_reset_counter -= 1
            cv2.putText(frame, f"SEQ : ", (20, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            cv2.putText(frame, f"STATUS : WAITING", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            return frame, objects

        # =========================================================
        # AWAITING START EXIT GATE
        # After reset, block new cycle until kick has physically
        # left the START region for start_exit_threshold frames.
        # This is the key guard against immediate START re-match.
        # =========================================================
        if self.awaiting_start_exit:
            kick_clear_of_start = True

            if "kick" in objects and self.engine_rectangles:
                if self._kick_in_start(objects["kick"]["bbox"]):
                    kick_clear_of_start = False
                    self.start_exit_confirmed = 0   # still inside, reset counter

            if kick_clear_of_start:
                self.start_exit_confirmed += 1

            if self.start_exit_confirmed >= self.start_exit_threshold:
                # Kick has genuinely left START — new cycle may begin
                self.awaiting_start_exit = False
                self.start_exit_confirmed = 0
                self.region_history = []    # clear any history built during wait

            # Display while waiting for exit
            cv2.putText(frame, f"SEQ : ", (20, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            cv2.putText(frame, f"STATUS : WAITING", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(frame, f"WAIT EXIT START : {self.start_exit_confirmed}/{self.start_exit_threshold}",
                        (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 0), 2)
            return frame, objects   # nothing runs until kick is clear

        # =========================================================
        # GRACE PERIOD COUNTDOWN (mid-cycle)
        # =========================================================
        if self.grace_counter > 0:
            self.grace_counter -= 1
            self.nok_exit_frames = 0

        # =========================================================
        # NOK CHECK — kick left ALL regions before completing sequence
        # =========================================================
        if self.seq_index > 0 and self.grace_counter == 0 and \
                "kick" in objects and self.engine_rectangles:

            if not self._kick_in_any_region(objects["kick"]["bbox"]):
                self.nok_exit_frames += 1
            else:
                self.nok_exit_frames = 0

            if self.nok_exit_frames >= self.nok_exit_threshold:
                self.kick_status = "NOK"
                self.cycle_locked = True
                self.nok_exit_frames = 0
                
                if not self.result_sent:
                    self.send_result_to_io("NOK")
                    self.result_sent = True

        # =========================================================
        # SEQUENCE LOGIC (START → END → START)
        # =========================================================
        if "kick" in objects and not self.cycle_locked and self.rearm_delay == 0:

            kx1, ky1, kx2, ky2 = objects["kick"]["bbox"]
            current_regions = []

            for region_name, region_box in self.engine_rectangles.items():
                rx1, ry1, rx2, ry2 = region_box

                ix1 = max(kx1, rx1)
                iy1 = max(ky1, ry1)
                ix2 = min(kx2, rx2)
                iy2 = min(ky2, ry2)

                if ix1 < ix2 and iy1 < iy2:
                    current_regions.append(region_name)

            # -----------------------------
            # STABILITY FILTER
            # -----------------------------
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

                stable = max(set(self.region_history),
                             key=self.region_history.count)

                expected = self.expected_sequence[self.seq_index]

                # -----------------------------
                # STEP MATCH
                # -----------------------------
                if stable == expected:
                    if len(self.kick_sequence) == 0 or self.kick_sequence[-1] != stable:
                        self.kick_sequence.append(stable)
                        self.seq_index += 1
                        self.last_detected = stable
                        self.nok_exit_frames = 0
                        self.grace_counter = self.grace_frames_after_step
                else:
                    self.last_detected = None

        # =========================================================
        # CYCLE COMPLETE → LOCK AS OK
        # =========================================================
        if self.seq_index >= len(self.expected_sequence):
            self.kick_status = "OK"
            self.cycle_locked = True
            self.rearm_delay = self.cooldown_frames
            if not self.result_sent:
                self.send_result_to_io("OK")
                self.result_sent = True

        # =========================================================
        # DISPLAY
        # =========================================================
        cv2.putText(frame,f"SEQ : {' -> '.join(self.kick_sequence)}",(20, 100),cv2.FONT_HERSHEY_SIMPLEX,0.8,(255, 255, 0),2)
        cv2.putText(frame,f"STATUS : {self.kick_status}",(20, 50),cv2.FONT_HERSHEY_SIMPLEX,1,(0, 255, 0) if self.kick_status == "OK" else (0, 0, 255),2)

        if self.grace_counter > 0:
            cv2.putText(frame,f"GRACE  : {self.grace_counter}",(20, 150),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0, 165, 255),2)
        return frame, objects

    def run(self):
        # Initial Connection
        if not self.open_stream():
            print("Initial Stream Connection Failed")
            return
        while True:
            self.read_redis_messages()
            # -------------------------------------------------
            # CHECK STREAM STATE
            # -------------------------------------------------
            if self.cap is None or not self.cap.isOpened():
                print("Capture Closed")
                reconnect_ok = self.reconnect_stream()
                if not reconnect_ok:
                    print("Reconnect Failed")
                    time.sleep(1)
                    self.ai_ready_status("AI_NOT_READY")
                continue
            # -------------------------------------------------
            # READ FRAME
            # -------------------------------------------------
            ret, frame = self.read_frame()
            if not ret:
                self.ai_ready_status("AI_NOT_READY")
                # Small sleep avoids CPU 100%
                time.sleep(0.05)
                continue
            # -------------------------------------------------
            # INFERENCE
            # -------------------------------------------------
            inf_frame, objects = self.run_inference_engine(frame)
            # -------------------------------------------------
            # DISPLAY
            # -------------------------------------------------
            print(objects)
            self.ai_ready_status("AI_READY")
            # cv2.imshow("live frame", inf_frame)
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