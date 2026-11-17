import subprocess
import time
import logging
import os
from logging.handlers import RotatingFileHandler

# ---------------- CONFIG ----------------
RECEIVERS = {
    # "intrusion": ["python", r"C:\Users\Elansol\Desktop\SCOUT\SCOUT_AI\reciever\intrusion_receiver.py"],
    # "CameraTampering": ["python", r"C:\Users\Elansol\Desktop\SCOUT\SCOUT_AI\reciever\camera_tampering_receiver.py"],
    # "ShutdownMovement": ["python", r"C:\Users\Elansol\Desktop\SCOUT\SCOUT_AI\reciever\shutdown_movement_receiver.py"]
    "FallDetection": ["python", r"C:\Users\Elansol\Desktop\SCOUT\SCOUT_AI\reciever\Falldetection_receiver.py"],
    "FireSmoke": ["python", r"C:\Users\Elansol\Desktop\SCOUT\SCOUT_AI\reciever\FireSmoke_receiver.py"]

}

RESTART_DELAY = 2

# ---------------- LOG PATH SETUP ----------------
LOG_DIR = r"C:\Users\Elansol\Desktop\SCOUT\SCOUT_AI\logs"

os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, r"C:\Users\Elansol\Desktop\SCOUT\SCOUT_AI\logs\receiver_logs.log")
MAX_LOG_SIZE = 5 * 1024 * 1024   # 5 MB
BACKUP_COUNT = 5

# ---------------- LOGGING SETUP ----------------
logger = logging.getLogger("ReceiverManager")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=MAX_LOG_SIZE,
    backupCount=BACKUP_COUNT
)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)

handler.setFormatter(formatter)
logger.addHandler(handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ---------------- PROCESS MANAGEMENT ----------------
processes = {}

def start_process(name):
    logger.info(f"[STARTING] {name}")
    return subprocess.Popen(RECEIVERS[name])

# Start all receivers
for name in RECEIVERS:
    processes[name] = start_process(name)

logger.info("[INFO] All receivers started")

# ---------------- MONITOR LOOP ----------------
while True:
    for name, process in processes.items():
        if process.poll() is not None:
            logger.error(f"[CRASHED] {name} → restarting in {RESTART_DELAY}s")
            time.sleep(RESTART_DELAY)
            processes[name] = start_process(name)

    time.sleep(2)
