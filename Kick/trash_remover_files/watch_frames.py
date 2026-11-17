import cv2
import numpy as np

sock_stream = cv2.VideoCapture("tcp://127.0.0.1:7000")

if not sock_stream.isOpened():
    print("Failed to open stream")
    exit()

while True:
    ret, frame = sock_stream.read()

    if not ret:
        print("Frame not received")
        break

    cv2.imshow("Live Stream", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

sock_stream.release()
cv2.destroyAllWindows()


# import cv2
# from ultralytics import YOLO

# # =========================
# # LOAD YOLO MODEL
# # =========================
# model_path = "/home/bks01/Downloads/yolo11l.pt"   # <-- give your YOLO model path here
# model = YOLO(model_path)

# # =========================
# # OPEN TCP STREAM
# # =========================
# sock_stream = cv2.VideoCapture("tcp://127.0.0.1:7000")

# if not sock_stream.isOpened():
#     print("Failed to open stream")
#     exit()

# # =========================
# # READ FRAMES
# # =========================
# while True:
#     ret, frame = sock_stream.read()

#     if not ret:
#         print("Frame not received")
#         break

#     # =========================
#     # YOLO INFERENCE
#     # =========================
#     results = model(frame)

#     # Draw detections
#     annotated_frame = results[0].plot()

#     # =========================
#     # SHOW OUTPUT
#     # =========================
#     cv2.imshow("YOLO Live Stream", annotated_frame)

#     # Press Q to exit
#     if cv2.waitKey(1) & 0xFF == ord('q'):
#         break

# # =========================
# # CLEANUP
# # =========================
# sock_stream.release()
# cv2.destroyAllWindows()