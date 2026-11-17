from ultralytics import YOLO

model = YOLO("/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/MODELS/best_1_June.pt")

model.export(
    format="engine",
    imgsz=720,
    half=True,
    device=0
)