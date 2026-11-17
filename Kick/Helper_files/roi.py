import cv2
import json

# Replace with your camera link
CAMERA_LINK_1 = "rtsp://admin:Elansol%402026@192.168.1.64:554/cam/realmonitor?channel=1&subtype=0"


# Global variables for drawing rectangle
drawing = False
ix, iy = -1, -1
fx, fy = -1, -1
roi = [] # List to store ROI coordinates as [(x1, y1), (x2, y2)]

def draw_rectangle_and_save_roi(event, x, y, flags, param):
    """
    Mouse callback function to draw rectangle and save ROI
    """
    global ix, iy, fx, fy, drawing, roi, frame_display

    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y
        # Reset current ROI display when starting a new draw
        frame_display = frame.copy()

    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            # Create a fresh copy of the frame to redraw the rectangle dynamically
            frame_display = frame.copy()
            cv2.rectangle(frame_display, (ix, iy), (x, y), (0, 255, 0), 2)

    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        fx, fy = x, y
        cv2.rectangle(frame_display, (ix, iy), (fx, fy), (0, 255, 0), 2)

        # Ensure coordinates are always positive and represent top-left and bottom-right
        x1 = min(ix, fx)
        y1 = min(iy, fy)
        x2 = max(ix, fx)
        y2 = max(iy, fy)

        # Store ROI as a list of two tuples
        roi = [(x1, y1), (x2, y2)]
        print(f"ROI selected: {roi}")

        # Save ROI to a JSON file
        try:
            with open('roi_data.json', 'w') as f:
                json.dump(roi, f, indent=4)
            print("ROI data saved to roi_data.json")
        except IOError as e:
            print(f"Error saving ROI data: {e}")

# Open the RTSP camera stream
cap = cv2.VideoCapture(CAMERA_LINK_1)

if not cap.isOpened():
    print(f"Error: Could not open video stream from {CAMERA_LINK_1}")
    exit()

# Create a window and set the mouse callback function
window_name = 'Camera Feed - Draw ROI'
cv2.namedWindow(window_name)
cv2.setMouseCallback(window_name, draw_rectangle_and_save_roi)

print("Press 'q' to quit.")
print("Click and drag your mouse on the video to select a Region of Interest (ROI).")

while True:
    ret, frame = cap.read()

    if not ret:
        print("Failed to grab frame, trying to reconnect...")
        cap.release()
        cap = cv2.VideoCapture(CAMERA_LINK_1)
        if not cap.isOpened():
            print("Failed to reconnect. Exiting.")
            break
        continue

    # Initialize frame_display with the current frame if no drawing is in progress
    if not drawing:
        frame_display = frame.copy()
    else:
        # If drawing, frame_display is already being updated by the mouse callback
        pass

    # Display the frame
    cv2.imshow(window_name, frame_display)

    # Exit on 'q' press
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the capture and destroy all windows
cap.release()
cv2.destroyAllWindows()