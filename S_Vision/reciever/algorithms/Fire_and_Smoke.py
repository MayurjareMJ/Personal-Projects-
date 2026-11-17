"""
Fire Smoke Processing Class
--------------------------
This class handles:

✔ Model loading (YOLO)
✔ Model releasing
✔ Batch inference
✔ Multiple detections → single Kafka message per frame
✔ Uses frame_id and frame_timestamp from upstream pipeline
✔ NO TRACKER (unlike intrusion)
"""

from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, Float, func
from sqlalchemy.orm import declarative_base, sessionmaker
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
import supervision as sv

import logging
from logging.handlers import RotatingFileHandler
import os

# ---------- LOGGER SETUP ----------
LOG_DIR = "new_firesmoke_logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "firesmoke.log")

logger = logging.getLogger("FIRE_SMOKE")
logger.setLevel(logging.INFO)
logger.propagate = False

handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,
    backupCount=5
)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
)

handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(handler)


Base = declarative_base()

tree = ET.parse(r"/home/elansol/Desktop/SCOUT_VISION/reciever/algorithms/config.xml")
root = tree.getroot()

db_node = root.find("database")

username = db_node.findtext("username")
password = db_node.findtext("password")
host = db_node.findtext("host")
port = db_node.findtext("port")
dbname = db_node.findtext("dbname")
schema = db_node.findtext("schema")


# ---------- SAME DB MODELS ----------
class SettingsUsecase(Base):
    __tablename__ = "settings_usecase"
    __table_args__ = {"schema": f"{schema}"}

    settings_usecase_id = Column(String(255), primary_key=True)
    usecase_name = Column(String(255))
    usecase_acronym = Column(String(255))
    model_in_use = Column(String(255))
    model_threshold = Column(Float)
    createdAt = Column(TIMESTAMP)
    updatedAt = Column(TIMESTAMP)
    createdBy = Column(String(255))
    updatedBy = Column(String(255))


class CameraMapper(Base):
    __tablename__ = "camera_mapper"
    __table_args__ = {"schema": f"{schema}"}

    camera_mapper_id = Column(String(255), primary_key=True)
    camera_id = Column(String(255))
    createdAt = Column(TIMESTAMP)
    updatedAt = Column(TIMESTAMP)
    createdBy = Column(String(255))
    updatedBy = Column(String(255))
    usecase_id = Column(String(255))
    roi_cordinates = Column(String(255))
    type_of_roi = Column(String(255))
    zone_id = Column(String(255))
    location_id = Column(String(255))


class SettingsCamera(Base):
    __tablename__ = "settings_camera"
    __table_args__ = {"schema": f"{schema}"}

    settings_camera_id = Column(String(255), primary_key=True)
    camera_name = Column(String(255))
    camera_zone = Column(String(255))
    user_name = Column(String(255))
    password = Column(String(255))
    camera_ip = Column(String(255))
    refresh_rate = Column(Integer)
    channel = Column(String(255))


# ---------- DB CLIENT (UNCHANGED) ----------
class DBClient:
    def __init__(self, username, password, host, database, port=6432):
        safe_username = quote_plus(username)
        safe_password = quote_plus(password)

        self.db_url = f"postgresql://{safe_username}:{safe_password}@{host}:{port}/{database}"
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session = self.SessionLocal()

    def get_all_camera_mappers(self):
        return self.session.query(CameraMapper).all()

    def get_camera_name_by_camera_id(self, camera_id):
        result = (
            self.session.query(SettingsCamera.camera_name)
            .filter(SettingsCamera.settings_camera_id == camera_id)
            .first()
        )
        return result[0] if result else None

    def get_camera_zone_by_camera_id(self, camera_id):
        result = (
            self.session.query(SettingsCamera.camera_zone)
            .filter(SettingsCamera.settings_camera_id == camera_id)
            .first()
        )
        return result[0] if result else None

    def get_roi_by_camera_id(self, camera_id):
        result = (
            self.session.query(CameraMapper.roi_cordinates)
            .filter(CameraMapper.camera_id == camera_id)
            .first()
        )
        return result[0] if result else None


# ==========================================================
# 🔥 FIRE SMOKE CLASS
# ==========================================================
import threading
import time
from typing import Any, Dict, List, Optional
from ultralytics import YOLO
import base64
import cv2
import json
import numpy as np
import torch

# Limit CPU threads
torch.set_num_threads(2)
cv2.setNumThreads(2)

class FireSmoke:   # ❗ KEEP SAME NAME (as you requested)
    def __init__(
        self,
        model_path: str,
        usecase_id: str,
        use_case: str = "FIRE_SMOKE",   # ✅ CHANGED
        org_id: str = "DEFAULT_ORG",
        device: Optional[str] = None
    ):
        self.model_path = model_path
        self.use_case = use_case
        self.org_id = org_id
        self.device = "cpu"
        self.class_names = None
        self.model = None
        self._loaded = False
        self.usecase_id = usecase_id
        self._lock = threading.RLock()
        self._ref_count = 0

        self.dbobj = DBClient(username, password, host, dbname, port)

        self.cache = {}
        self.cache_lock = threading.Lock()

        self._preload_cache()

    # ---------- MODEL ----------
    def load_model(self):
        with self._lock:
            if self._loaded:
                return

            self.model = YOLO(self.model_path)
            self.model.to(self.device)
            self.class_names = self.model.names
            self._loaded = True
            logger.info(f"[{self.use_case}] Model loaded")

    def _acquire(self):
        with self._lock:
            self._ref_count += 1

    def _release(self):
        with self._lock:
            self._ref_count = max(0, self._ref_count - 1)

    # ---------- CACHE ----------
    def _preload_cache(self):
        camera_mappers = self.dbobj.get_all_camera_mappers()

        for cm in camera_mappers:
            cam_id = cm.camera_id

            self.cache[cam_id] = {
                "camera_name": self.dbobj.get_camera_name_by_camera_id(cam_id),
                "camera_zone": self.dbobj.get_camera_zone_by_camera_id(cam_id),
                "roi": cm.roi_cordinates
            }

    def get_camera_data(self, camera_id):
        if camera_id in self.cache:
            return self.cache[camera_id]

        with self.cache_lock:
            data = {
                "camera_name": self.dbobj.get_camera_name_by_camera_id(camera_id),
                "camera_zone": self.dbobj.get_camera_zone_by_camera_id(camera_id),
                "roi": self.dbobj.get_roi_by_camera_id(camera_id)
            }
            self.cache[camera_id] = data
            return data

    # ---------- ROI ----------
    def convert_rois_to_pixel_np(self, roi_data):
        if not roi_data:
            return []

        # parse string → dict
        if isinstance(roi_data, str):
            roi_data = json.loads(roi_data)

        pixel_rois = []

        for roi in roi_data.get("rois", []):
            roi_type = roi.get("type")
            mode = roi.get("mode")

            # ---------- POLYGON ----------
            if roi_type == "polygon":
                pts = np.array(
                    [
                        (
                            int(p["x"] * 320),
                            int(p["y"] * 320)
                        )
                        for p in roi.get("points", [])
                    ],
                    dtype=np.int32
                )

                pixel_rois.append({
                    "mode": mode,
                    "type": "polygon",
                    "points": pts.tolist()
                })

            # ✅ ---------- RECTANGLE (THIS WAS MISSING) ----------
            elif roi_type == "rectangle":
                p1, p2 = roi["points"]

                x1 = int(p1["x"] * 320)
                y1 = int(p1["y"] * 320)
                x2 = int(p2["x"] * 320)
                y2 = int(p2["y"] * 320)

                pixel_rois.append({
                    "mode": mode,
                    "type": "rectangle",
                    "points": [
                        {"x": x1, "y": y1},
                        {"x": x2, "y": y2}
                    ]
                })

        return pixel_rois
    # def display_frame(self, frame, detections, window_name="FireSmoke Live"):

    #     display_frame = frame.copy()

    #     for det in detections:
    #         bbox = det["bbox"]

    #         x1 = int(bbox["x1"])
    #         y1 = int(bbox["y1"])
    #         x2 = int(bbox["x2"])
    #         y2 = int(bbox["y2"])

    #         label = det["object"]
    #         conf = det["confidence"]

    #         color = (0, 0, 255) if label == "Fire" else (255, 255, 0)

    #         # Draw box
    #         cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)

    #         # Label
    #         text = f"{label} {conf:.2f}"
    #         cv2.putText(
    #             display_frame,
    #             text,
    #             (x1, y1 - 10),
    #             cv2.FONT_HERSHEY_SIMPLEX,
    #             0.5,
    #             color,
    #             2
    #         )

    #     cv2.imshow(window_name, display_frame)
    #     cv2.waitKey(1)
    
    # ==========================================================
    # 🔥 BATCH INFER (NO TRACKER)
    # ==========================================================
    def batch_infer(self, frames: List[Dict[str, Any]], batch_size: int = 8):

        if not self._loaded:
            raise RuntimeError("Call load_model() before inference")

        self._acquire()

        try:
            results = []

            # Resize once
            batch_imgs = []
            batch_meta = []

            for frame_info in frames:
                resized = cv2.resize(frame_info["frame"], (320, 320))

                batch_imgs.append(resized)
                batch_meta.append(frame_info)

            # TRUE BATCH INFERENCE
            yolo_results = self.model(
                batch_imgs,
                device=self.device,
                verbose=False,
                conf=0.2
            )

            for frame_info, img, det in zip(
                batch_meta,
                batch_imgs,
                yolo_results
            ):

                detections = []

                if det.boxes is not None:

                    for box in det.boxes:

                        cls_id = int(box.cls[0])
                        label = det.names[cls_id]

                        if label not in ["Fire", "Smoke"]:
                            continue

                        xyxy = box.xyxy[0].cpu().numpy()

                        detections.append({
                            "object": label,
                            "confidence": float(box.conf[0]),
                            "bbox": {
                                "x1": float(xyxy[0]),
                                "y1": float(xyxy[1]),
                                "x2": float(xyxy[2]),
                                "y2": float(xyxy[3]),
                            }
                        })

                results.append({
                    "camera_id": frame_info["camera_id"],
                    "frame_id": frame_info["frame_id"],
                    "timestamp": frame_info["timestamp"],
                    "frame": img,
                    "detections": detections
                })

            return results

        finally:
            self._release()
    # ---------- ENCODE ----------
    def encode_frame(self, frame):
        resized = cv2.resize(frame, (320, 320)).copy()
        _, buffer = cv2.imencode(".jpg", resized)
        return base64.b64encode(buffer).decode("utf-8")

    # ---------- PROCESS ----------
    def process_raw(self, raw_outputs):
        kafka_messages = []

        for frame in raw_outputs:
            cam_data = self.get_camera_data(frame["camera_id"])

            roi_string = cam_data.get("roi")
            pixel_rois = self.convert_rois_to_pixel_np(roi_string)

            payload = {
                "org_id": self.org_id,
                "use_case": self.use_case,
                "camera_id": frame["camera_id"],
                "camera_name": cam_data.get("camera_name"),
                "timestamp": frame["timestamp"],
                "frame_id": frame["frame_id"],
                "frame": self.encode_frame(frame["frame"]),
                "detections": frame.get("detections", []),
                "camera_zone": cam_data.get("camera_zone"),
                "roi_pixel_coordinates": pixel_rois
            }

            kafka_messages.append(payload)

        return kafka_messages

    # ---------- KAFKA ----------
    # def forward_to_producer(self, producer, raw_outputs):

    #     messages = self.process_raw(raw_outputs)

    #     for raw, msg in zip(raw_outputs, messages):

    #         # ✅ SHOW LIVE FRAME (no payload change)
    #         self.display_frame(raw["frame"], raw["detections"])

    #         producer.send(
    #             use_case=self.use_case,
    #             key=msg["camera_id"],
    #             message_dict=msg
    #         )



    def forward_to_producer(self, producer, raw_outputs):

        messages = self.process_raw(raw_outputs)

        for raw, msg in zip(raw_outputs, messages):

            producer.send(
                use_case=self.use_case,
                key=msg["camera_id"],
                message_dict=msg
            )