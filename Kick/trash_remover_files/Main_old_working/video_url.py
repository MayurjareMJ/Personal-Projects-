from flask import Flask, Response
import cv2
import time
from Main_1 import VisionSystem

# ==========================================================
# FLASK APP
# ==========================================================
app = Flask(__name__)

# ==========================================================
# VISION SYSTEM
# ==========================================================
vision = VisionSystem()

# ==========================================================
# INITIAL STREAM CONNECTION
# ==========================================================
print("=" * 60)
print("STARTING VISION SYSTEM")
print("=" * 60)

vision.open_stream()

# ==========================================================
# HOME PAGE
# ==========================================================
@app.route("/")
def index():

    return """
    <html>
        <head>
            <title>Vision System</title>
        </head>

        <body style="background-color:black; color:white; text-align:center;">

            <h1>Industrial Vision System</h1>

            <img src="/video_feed" width="900">

        </body>
    </html>
    """

# ==========================================================
# FRAME GENERATOR
# ==========================================================
def generate_frames():

    reconnect_attempts = 0

    while True:

        try:

            # ==================================================
            # CHECK STREAM OBJECT
            # ==================================================
            if vision.cap is None or not vision.cap.isOpened():

                print("\n" + "=" * 60)
                print("FLASK DETECTED CLOSED STREAM")
                print("TRYING RECONNECT...")
                print("=" * 60)

                reconnect_ok = vision.reconnect_stream()

                if reconnect_ok:

                    print("RECONNECTED SUCCESSFULLY")
                    reconnect_attempts = 0

                else:

                    reconnect_attempts += 1

                    print(f"RECONNECT FAILED : {reconnect_attempts}")

                    time.sleep(2)

                continue

            # ==================================================
            # READ FRAME
            # ==================================================
            ret, frame = vision.read_frame()

            # ==================================================
            # FRAME FAILED
            # ==================================================
            if not ret or frame is None:

                print("FRAME NOT RECEIVED")

                reconnect_attempts += 1

                # Small wait prevents CPU overload
                time.sleep(0.05)

                # Force reconnect after repeated failures
                if reconnect_attempts >= 20:

                    print("\n" + "=" * 60)
                    print("MULTIPLE FRAME FAILURES")
                    print("FORCING RECONNECT")
                    print("=" * 60)

                    vision.reconnect_stream()

                    reconnect_attempts = 0

                    time.sleep(1)

                continue

            # ==================================================
            # VALID FRAME
            # ==================================================
            reconnect_attempts = 0

            # ==================================================
            # RUN INFERENCE
            # ==================================================
            inf_frame, objects = vision.run_inference_engine(frame)

            # Optional
            # print(objects)

            # ==================================================
            # ENCODE JPEG
            # ==================================================
            success, buffer = cv2.imencode(".jpg", inf_frame)

            if not success:

                print("JPEG ENCODE FAILED")

                time.sleep(0.05)

                continue

            frame_bytes = buffer.tobytes()

            # ==================================================
            # SEND FRAME TO BROWSER
            # ==================================================
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                frame_bytes +
                b'\r\n'
            )

        # ======================================================
        # BROWSER CLOSED
        # ======================================================
        except GeneratorExit:

            print("BROWSER DISCONNECTED")

            break

        # ======================================================
        # ANY OTHER ERROR
        # ======================================================
        except Exception as e:

            print("\n" + "=" * 60)
            print(f"FLASK STREAM ERROR : {e}")
            print("TRYING RECOVERY...")
            print("=" * 60)

            try:
                vision.reconnect_stream()

            except Exception as reconnect_error:

                print(f"RECONNECT ERROR : {reconnect_error}")

            time.sleep(1)

# ==========================================================
# VIDEO ROUTE
# ==========================================================
@app.route("/video_feed")
def video_feed():

    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5000,threaded=True,debug=False)