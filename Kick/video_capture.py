import cv2
import os
from datetime import datetime

# ==========================
# RTSP URL
# ==========================
rtsp_url = "rtsp://admin:Elansol%402026@192.168.1.64:554/cam/realmonitor?channel=1&subtype=0"

# ==========================
# Create save folder
# ==========================
save_folder = "datacollection"
os.makedirs(save_folder, exist_ok=True)

filename = datetime.now().strftime("video_%Y%m%d_%H%M%S.mp4")
filepath = os.path.join(save_folder, filename)

# ==========================
# Open RTSP
# ==========================
cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

if not cap.isOpened():
    print("Failed to connect camera")
    exit()

fps = cap.get(cv2.CAP_PROP_FPS)
if fps <= 0:
    fps = 25

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print("Resolution:", width, "x", height)
print("FPS:", fps)

# ==========================
# Video writer
# ==========================
fourcc = cv2.VideoWriter_fourcc(*'mp4v')

writer = cv2.VideoWriter(
    filepath,
    fourcc,
    fps,
    (width, height)
)

# ==========================
# Small display window
# ==========================
cv2.namedWindow("RTSP", cv2.WINDOW_NORMAL)
cv2.resizeWindow("RTSP", 500, 300)      # width, height

print("Recording...")
print("Saving:", filepath)
print("Press q to stop")

# ==========================
# Main loop
# ==========================
while True:
    ret, frame = cap.read()

    if not ret:
        print("Frame lost")
        continue

    writer.write(frame)

    cv2.imshow("RTSP", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
writer.release()
cv2.destroyAllWindows()

print("Saved:", filepath)