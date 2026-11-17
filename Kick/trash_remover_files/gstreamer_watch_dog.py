import subprocess
import time
import socket
import os

PORT = 7000
FAIL_LIMIT = 3
CHECK_INTERVAL = 5

GST_COMMAND = [
    "gst-launch-1.0",
    "-e",
    "rtspsrc",
    'location=rtsp://admin:Elansol%402026@192.168.1.64:554/cam/realmonitor?channel=1&subtype=0',
    "protocols=tcp",
    "latency=60",
    "drop-on-latency=true",
    "timeout=5000000",
    "do-rtsp-keep-alive=true",
    "is-live=true",
    "!",
    "rtph264depay",
    "!",
    "h264parse",
    "!",
    "avdec_h264",
    "!",
    "videoscale",
    "!",
    "video/x-raw,width=1920,height=1080",
    "!",
    "videoconvert",
    "!",
    "jpegenc",
    "quality=40",
    "!",
    "tcpserversink",
    "host=127.0.0.1",
    "port=7000",
    "sync=false"
]

process = None
fail_count = 0

def start_pipeline():
    global process
    print("🚀 Starting GStreamer pipeline...")

    process = subprocess.Popen(
        GST_COMMAND,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL 
    )


def stop_pipeline():
    global process
    if process:
        print("🛑 Stopping pipeline...")
        process.kill()
        process = None
    os.system("taskkill /F /IM gst-launch-1.0.exe >nul 2>&1")



def check_stream():
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=2)
        s.close()
        return True
    except:
        return False


print("🔥 Watchdog started")

start_pipeline()

while True:
    alive = check_stream()
    if alive:
        fail_count = 0
        print("✅ Stream OK")
    else:
        fail_count += 1
        print(f"⚠️ Stream failure: {fail_count}")

    if fail_count >= FAIL_LIMIT:
        print("🔁 Restarting pipeline...")
        stop_pipeline()
        time.sleep(2)
        start_pipeline()
        fail_count = 0

    time.sleep(CHECK_INTERVAL)