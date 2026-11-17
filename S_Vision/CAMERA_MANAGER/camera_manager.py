from queue import Queue
from CAMERA_MANAGER.db_config import Database
from CAMERA_MANAGER.camera_worker import CameraWorker
import time


class CameraManager:

    def __init__(self):
        self.db = Database()
        self.camera_queues = {}   # camera_id → Queue
        self.workers = []

    def load_cameras(self):
        return self.db.get_cameras()

    def start(self):
        cameras = self.load_cameras()
        print(f"[INFO] Found {len(cameras)} cameras")

        for cam in cameras:
            q = Queue(maxsize=10)
            self.camera_queues[cam["camera_id"]] = q

            worker = CameraWorker(
                camera_id=cam["camera_id"],
                rtsp_url=cam["rtsp_url"],
                usecase_id=cam["usecase_id"],
                output_queue=q,
                fps=1
            )
            worker.start()
            self.workers.append(worker)
            print(f"[INFO] Started {cam['camera_name']}")
            time.sleep(1)  # stagger pipeline starts

    def get_all_frames(self):
        """Round-robin across all camera queues"""
        frames = []
        for cam_id, q in self.camera_queues.items():
            if not q.empty():
                try:
                    frames.append(q.get_nowait())
                except Exception:
                    pass
        return frames