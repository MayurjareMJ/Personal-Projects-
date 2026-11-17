import sys
import os
import time
project_root = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        ".."
    )
)

sys.path.append(project_root)
import socket
import struct
import json
import base64
import traceback
import numpy as np
import cv2

from sender.vision_result_sender import BULLMQ_SENDER
from CAMERA_MANAGER.camera_manager import CameraManager


class BaseReceiver:
    """
    Base TCP Receiver
    -----------------
    ✔ TCP socket handling
    ✔ Payload receive
    ✔ Image decoding
    ✔ Batch processing template
    ✔ Kafka producer handling
    """
 
    def __init__(
        self,
        host: str,
        port: int,
        model_cls,
        # model_path: str,
        org_id: str,
        name: str,
        usecase_id: str,
        model_path: str = None
    ):
        self.host = host
        self.port = port
        self.name = name

        self.server = None
        self.model = None

        self.model_cls = model_cls
        self.model_path = model_path
        self.org_id = org_id
        self.usecase_id = usecase_id
        self.batch_size = 4
        

        self.producer = BULLMQ_SENDER()

    # ----------------------------------------------------------
    # Model Initialization
    
    # ----------------------------------------------------------
    def load_model(self):
        try:
            print(f"[INFO] Initializing {self.name}...")

            # If model class exists
            if self.model_cls is not None:

                if self.model_path:
                    self.model = self.model_cls(
                        model_path=self.model_path,
                        org_id=self.org_id,
                        usecase_id=self.usecase_id
                    )
                else:
                    # For rule-based usecases (no model_path)
                    self.model = self.model_cls(
                        org_id=self.org_id,
                        usecase_id=self.usecase_id
                    )

                if hasattr(self.model, "load_model"):
                    self.model.load_model()

            print(f"[INFO] {self.name} initialized successfully")

        except Exception:
            print(f"[ERROR] Failed to initialize {self.name}")
            traceback.print_exc()
            raise

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------
    def decode_image(self, b64_str):
        try:
            img_bytes = base64.b64decode(b64_str)
            arr = np.frombuffer(img_bytes, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            traceback.print_exc()
            return None

    def recv_payload(self, conn):
        """
        Receive length-prefixed JSON payload.
        Payload is expected to be a LIST of frames.
        """
        try:
            raw_len = conn.recv(4)
            if not raw_len:
                return None

            msg_len = struct.unpack(">I", raw_len)[0]

            data = b""
            while len(data) < msg_len:
                packet = conn.recv(msg_len - len(data))
                if not packet:
                    return None
                data += packet

            return json.loads(data.decode("utf-8"))

        except Exception:
            traceback.print_exc()
            return None

    # ----------------------------------------------------------
    # Batch Processing (GENERIC)
    # ----------------------------------------------------------
    def process_batch(self, frames_list):
        try:
            if not isinstance(frames_list, list) or not frames_list:
                print(f"[WARN] Invalid or empty {self.name} batch received")
                return

            print(f"[INFO] {self.name} batch received | Frames: {len(frames_list)}")

            model_inputs = []

            for f in frames_list:
                img = self.decode_image(f.get("frameData"))
                if img is None:
                    continue

                # print({
                #     "cameraId": f.get("cameraId"),
                #     "frameId": f.get("frameId"),
                #     "timestamp": f.get("timestamp"),
                #     "keys": list(f.keys())
                # })

                model_inputs.append({
                    "camera_id": f.get("cameraId"),
                    "frame": img,
                    "frame_id": f.get("frameId"),
                    "timestamp": f.get("timestamp")
                })

            if not model_inputs:
                print("[WARN] No valid frames after decoding")
                return

            print(f"[INFO] Running {self.name} batch inference...")
            inference_results = self.model.batch_infer(model_inputs)

            self.model.forward_to_producer(
                self.producer,
                inference_results
            )

            print(f"[INFO] {self.name} results sent to Kafka")

        except Exception:
            print(f"[ERROR] {self.name} batch processing failed")
            traceback.print_exc()

    # ----------------------------------------------------------
    # Client Handler
    # ----------------------------------------------------------
    def handle_client(self, conn, addr):
        print(f"[INFO] Frame manager connected: {addr}")

        try:
            while True:
                payload = self.recv_payload(conn)
                if payload is None:
                    print("[WARN] Frame manager disconnected")
                    break

                self.process_batch(payload)
                conn.sendall(b"OK")

        except Exception:
            print("[ERROR] Client handling error")
            traceback.print_exc()

        finally:
            conn.close()
            print(f"[INFO] Connection closed: {addr}")

    # ----------------------------------------------------------
    # Server Start
    # ----------------------------------------------------------
    def start(self):
        try:
            self.load_model()
            camera_manager = CameraManager()
            camera_manager.start()
            print(f"[INFO] {self.name} receiver started")
            
            batch = []
            
            while True:
                frames = camera_manager.get_all_frames()
                
                if frames:
                    batch.extend(frames)        #  was: batch.append(payload)
                else:
                    time.sleep(0.01)            #   avoid busy-wait when queues empty
                
                if len(batch) >= self.batch_size:
                    self.process_batch(batch)
                    batch = []
                    
        except Exception:
            print(f"[FATAL] {self.name} receiver crashed")
            traceback.print_exc()

