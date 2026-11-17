import cv2

# =========================
# RTSP STREAM URL
# =========================
RTSP_URL = "rtsp://admin:Elansol%402026@192.168.1.64:554/Streaming/Channels/101"

# Open RTSP stream
cap = cv2.VideoCapture(RTSP_URL)

if not cap.isOpened():
    print("❌ Unable to open RTSP stream")
    exit()

# Read one frame
ret, frame = cap.read()

if not ret:
    print("❌ Unable to read frame from stream")
else:
    height, width = frame.shape[:2]

    print(f"✅ Stream Resolution: {width} x {height}")

# Release stream
cap.release()