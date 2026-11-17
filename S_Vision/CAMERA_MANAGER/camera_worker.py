import cv2
import uuid
import base64
import time
import threading
import numpy as np
import gi

gi.require_version("Gst", "1.0")

from gi.repository import Gst

Gst.init(None)


class CameraWorker(threading.Thread):

    def __init__(
        self,
        camera_id,
        rtsp_url,
        usecase_id,
        output_queue,
        fps=1
    ):
        super().__init__(daemon=True)

        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.usecase_id = usecase_id

        self.output_queue = output_queue

        self.fps = 1
        fps=1

        self.running = True

        self.pipeline = None
        self.appsink = None

        self.pipeline_started = False

        self.last_sent = 0
        
    # def build_pipeline(self):
    #   return (
    #     f"""
    #     rtspsrc location={self.rtsp_url} latency=100
    #     !
    #     rtph264depay
    #     !
    #     h264parse
    #     !
    #     avdec_h264
    #     !
    #     videorate
    #     !
    #     video/x-raw,framerate=1/1
    #     !
    #     videoconvert
    #     !
    #     video/x-raw,format=BGR
    #     !
    #     appsink name=sink emit-signals=true drop=true max-buffers=1
    #     """
    # )
    #     return f"""
    # rtspsrc location={self.rtsp_url} latency=100
    # !
    # rtph264depay
    # !
    # h264parse
    # !
    # vah264dec
    # !
    # videoconvert
    # !
    # video/x-raw,format=BGR
    # !
    # appsink name=sink drop=true max-buffers=1
    # """
    def build_pipeline(self):
        return f"""
            rtspsrc location={self.rtsp_url} latency=100
            ! rtph264depay
            ! h264parse
            ! avdec_h264 skip-frame=1
            ! videoconvert
            ! video/x-raw,format=BGR
            ! appsink name=sink drop=true max-buffers=1
        """

    def connect(self):

        try:

            pipeline_str = self.build_pipeline()

            self.pipeline = Gst.parse_launch(
                pipeline_str
            )

            self.appsink = self.pipeline.get_by_name(
                "sink"
            )

            self.pipeline.set_state(
                Gst.State.PLAYING
            )

            print(
                f"[{self.camera_id}] Pipeline Started"
            )

            return True

        except Exception as e:

            print(
                f"[{self.camera_id}] Connection Error: {e}"
            )

            return False

    def get_frame(self):

        try:

            sample = self.appsink.emit(
                "pull-sample"
            )

            if sample is None:
                return None

            buffer = sample.get_buffer()

            caps = sample.get_caps()

            structure = caps.get_structure(0)

            width = structure.get_value(
                "width"
            )

            height = structure.get_value(
                "height"
            )

            success, map_info = buffer.map(
                Gst.MapFlags.READ
            )

            if not success:
                return None

            frame = np.ndarray(
                shape=(height, width, 3),
                dtype=np.uint8,
                buffer=map_info.data
            )

            # frame = frame.copy()
            frame = np.array(
                frame,
                copy=True
            )

            buffer.unmap(map_info)

            return frame

        except Exception as e:

            print(
                f"[{self.camera_id}] Frame Error: {e}"
            )

            return None

    def build_payload(self, frame):

        success, jpeg = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 80]
        )

        if not success:
            return None

        frame_base64 = base64.b64encode(
            jpeg.tobytes()
        ).decode()

        payload = {

            "cameraId": self.camera_id,

            "frameId": str(uuid.uuid4()),

            "timestamp": int(time.time() * 1000),

            "frameData": frame_base64
        }

        return payload

    def cleanup(self):

        try:

            if self.pipeline:

                self.pipeline.set_state(
                    Gst.State.NULL
                )

        except:
            pass

    def run(self):
        print(f"[{self.camera_id}] Worker thread started")
        while self.running:
            try:
                if not self.pipeline_started:
                    if not self.connect():
                        print(f"[{self.camera_id}] Failed to connect, retrying in 5s")
                        time.sleep(5)
                        continue
                    print(f"[{self.camera_id}] Pipeline started successfully")
                    self.pipeline_started = True

                # ✅ timing check FIRST — no frame pull yet
                current_time = time.time()
                elapsed = current_time - self.last_sent
                gap = 1 / self.fps

                if elapsed < gap:
                    time.sleep(gap - elapsed)
                    continue

                # ✅ only pull frame when it's time
                frame = self.get_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue

                self.last_sent = time.time()

                payload = self.build_payload(frame)
                if payload:
                    print(f"[{self.camera_id}] Sending frame | queue size: {self.output_queue.qsize()}")
                    try:
                        self.output_queue.put_nowait(payload)
                    except Exception:
                        print(f"[{self.camera_id}] Queue full — frame dropped!")

            except Exception as e:
                print(f"[{self.camera_id}] Error: {e}")
                self.cleanup()
                self.pipeline_started = False
                time.sleep(5)

