import serial
import time
from sqlalchemy import Column, String, Boolean, Integer, TIMESTAMP, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import sessionmaker
import logging
from logging.handlers import RotatingFileHandler


# ---------------- LOGGING CONFIG ----------------

LOG_FILE = "alarm_monitor.log"

logger = logging.getLogger("AlarmMonitor")
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,   # 5 MB
    backupCount=5               # keep last 5 logs
)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)

handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)


# ---------------- SERIAL CONFIG ----------------
PORT = "COM3"
BAUD = 9600

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(5)

def send(cmd):
    print("Sending:", cmd)
    ser.write((cmd + "\r").encode())
    ser.flush()
    time.sleep(0.2)

def start_alarm(source):
    logger.info(f"ALARM STARTED | Source: {source}")
    print("START ALARM")
    send("R:1")
    send("H:1")

def stop_alarm(source):
    logger.info(f"ALARM STOPPED | Source: {source}")
    print("STOP ALARM")
    send("H:0")
    send("R:0")

# ---------------- DATABASE CONFIG ----------------

Base = declarative_base()

SCHEMA_NAME = "cb8f28d4d4a924e3"

class IntrusionDetection(Base):
    __tablename__ = "intrusion_detection"
    __table_args__ = {"schema": SCHEMA_NAME}

    intrusion_detection_id = Column(String(255), primary_key=True)
    # alarm_triggered = Column(Boolean, default=False)
    createdAt = Column(TIMESTAMP, server_default=func.now())

class ShutdownPresenceDetection(Base):
    __tablename__ = "shutdown_presence_detection"
    __table_args__ = {"schema": SCHEMA_NAME}

    shutdown_presence_detection_id = Column(String(255), primary_key=True)
    # alarm_triggered = Column(Boolean, default=False)
    createdAt = Column(TIMESTAMP, server_default=func.now())


DATABASE_URL = "postgresql://postgres:Elansol%401@127.0.0.1:5432/scout_transactions"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# ---------------- FETCH METHODS ----------------

def get_last_intrusion_detection(session):
    return (
        session.query(IntrusionDetection)
        .order_by(IntrusionDetection.createdAt.desc())
        .first()
    )

def get_last_shutdown_presence_detection(session):
    return (
        session.query(ShutdownPresenceDetection)
        .order_by(ShutdownPresenceDetection.createdAt.desc())
        .first()
    )

# ---------------- MONITOR LOGIC ----------------

session = SessionLocal()

last_intrusion_id = None
last_shutdown_id = None

pending_intrusion = None
pending_shutdown = None

intrusion_time = None
shutdown_time = None

print("Monitoring incidents...")

while True:

    intrusion = get_last_intrusion_detection(session)
    shutdown = get_last_shutdown_presence_detection(session)

    current_time = time.time()

    # ---------------- INTRUSION CHECK ----------------
    if intrusion and intrusion.intrusion_detection_id != last_intrusion_id:

        print("New Intrusion Incident:", intrusion.intrusion_detection_id)

        pending_intrusion = intrusion.intrusion_detection_id
        intrusion_time = current_time
        last_intrusion_id = intrusion.intrusion_detection_id

    if pending_intrusion and (current_time - intrusion_time >= 10):

        logger.info("Intrusion confirmed -> Trigger alarm")

        start_alarm("Intrusion")
        time.sleep(10)
        stop_alarm("Intrusion")

        logger.info("Intrusion alarm cycle completed")

        pending_intrusion = None


    # ---------------- SHUTDOWN PRESENCE CHECK ----------------
    if shutdown and shutdown.shutdown_presence_detection_id != last_shutdown_id:

        print("New Shutdown Presence Incident:", shutdown.shutdown_presence_detection_id)

        pending_shutdown = shutdown.shutdown_presence_detection_id
        shutdown_time = current_time
        last_shutdown_id = shutdown.shutdown_presence_detection_id

    if pending_shutdown and (current_time - shutdown_time >= 10):

        logger.info("Shutdown presence confirmed -> Trigger alarm")

        start_alarm("Shutdown Presence")
        time.sleep(10)
        stop_alarm("Shutdown Presence")

        logger.info("Shutdown presence alarm cycle completed")

        pending_shutdown = None


    time.sleep(1)