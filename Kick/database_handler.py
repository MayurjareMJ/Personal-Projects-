from sqlalchemy import (
    Column, Integer, String, Boolean, TIMESTAMP, Text, create_engine
)
from sqlalchemy.dialects.postgresql import INET
#from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
import xml.etree.ElementTree as ET
tree = ET.parse(r"/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/Config.xml")
# =========================
# DB CONFIG
# =========================
root = tree.getroot()
DB_URL = root.find("Database/DB_URL").text.strip()
engine = create_engine(DB_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()
# =========================
# MODELS
# =========================
class DeviceConnectivityStatus(Base):
    __tablename__ = "device_connectivity_status"
    __table_args__ = {"schema": "ai"}
    id = Column(Integer, primary_key=True, autoincrement=True)
    camera = Column(String(50))
    plc = Column(String(50))
    camera_ip_address = Column(INET)
    camera_port = Column(Integer)
    plc_ip_address = Column(INET)
    plc_port = Column(Integer)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    plc_status = Column(Boolean)
    camera_status = Column(Boolean)

class VisionResults(Base):
    __tablename__ = "vision_results"
    __table_args__ = {"schema": "ai"}
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(50))
    station_id = Column(String(20))
    inspection_status = Column(String(10))
    image_path = Column(Text)
    video_path = Column(Text)
    bypassed = Column(String(5))
    manual_pass = Column(String(5))
    recheck = Column(String(5))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


class ErrorLogs(Base):
    __tablename__ = "error_logs"
    __table_args__ = {"schema": "ai"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    module = Column(String(50))
    severity = Column(String(10))
    message = Column(Text)
    error_code = Column(String(50))
    created_at = Column(TIMESTAMP, server_default=func.now())

class Operations(Base):
    __tablename__ = "operations"
    __table_args__ = {"schema": "ai"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_pass = Column(String(5), default="NO")
    recheck = Column(String(5), default="NO")
    bypass = Column(String(5), default="NO")
    running = Column(String(5), default="NO")
    stop = Column(String(5), default="NO")
    ui_manual_pass = Column(String(5), default="NO")
    ui_recheck = Column(String(5), default="NO")
    created_at = Column(
        TIMESTAMP,
        server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now()
    )


class SystemHealth(Base):
    __tablename__ = "system_health"
    __table_args__ = {"schema": "ai"}

    id = Column(Integer, primary_key=True, autoincrement=True)

    cpu_usage = Column(String(20))
    ram_usage = Column(String(20))
    disk_usage = Column(String(20))
    free_disk_space = Column(String(50))

    cpu_temp = Column(String(20))
    gpu_temp = Column(String(20))

    uptime = Column(String(50))

    network_status = Column(String(20))
    internet_status = Column(String(20))

    camera_status = Column(String(20))
    plc_status = Column(String(20))

    redis_status = Column(String(20))
    database_status = Column(String(20))
    ai_service_status = Column(String(20))

    storage_status = Column(String(20))

    power_status = Column(String(20))
    restart_logs = Column(Text)

    created_at = Column(
        TIMESTAMP,
        server_default=func.now()
    )

def insert_system_health(data):
    session = SessionLocal()

    try:
        record = SystemHealth(**data)

        session.add(record)
        session.commit()

        print("[DB] System Health Inserted")

    except Exception as e:
        session.rollback()
        print("[DB ERROR TYPE]", type(e).__name__)
        print("[DB ERROR DETAILS]", str(e))


    finally:
        session.close()


# def insert_vision_result(data):
#     session = SessionLocal()
#     try:
#         record = VisionResults(**data)
#         session.add(record)
#         session.commit()
#     except Exception as e:
#         session.rollback()
#         print("[DB ERROR]", e)
#     finally:
#         session.close()

########################################
def insert_vision_result(data):
    print("INSERT FUNCTION CALLED")
    print(data)
    session = SessionLocal()
    try:
        record = VisionResults(**data)
        session.add(record)
        session.commit()
        print("INSERT SUCCESS")
    # except Exception as e:
    #     session.rollback()
    #     print("[DB ERROR]", e)
    # finally:
    #     session.close()
    except Exception as e:
        session.rollback()

        print("===================================")
        print("[DB ERROR TYPE]")
        print(type(e).__name__)

        print("===================================")
        print("[DB ERROR DETAILS]")
        print(str(e))

        print("===================================")
    ###################################

def update_operations_status(**kwargs):
    session = SessionLocal()
    try:
        print("\n========== DB UPDATE START ==========")
        print("[DEBUG] Received kwargs:", kwargs)
        # =========================
        # GET ROW WITH ID = 1
        # =========================
        row = session.query(Operations).filter_by(id=1).first()
        print("[DEBUG] Existing Row:", row)
        # =========================
        # CREATE DEFAULT ROW
        # =========================
        if not row:
            row = Operations(id=1)
            session.add(row)
            session.commit()
            print("[DB] Default row created with ID=1")
        updated_fields = []
        # =========================
        # UPDATE VALUES
        # =========================
        for key, value in kwargs.items():
            print(f"[DEBUG] Processing -> {key} = {value}")
            if hasattr(row, key):
                value = str(value).upper()
                print(f"[DEBUG] Converted Value -> {value}")
                if value not in ["YES", "NO"]:
                    raise ValueError(
                        f"{key} must be YES or NO")
                setattr(row, key, value)
                updated_fields.append(f"{key}={value}")
                print(f"[DEBUG] Updated {key}")
            else:
                print(f"[DB WARNING] Invalid column: {key}")
        # =========================
        # COMMIT
        # =========================
        print("[DEBUG] Before Commit")
        session.commit()
        print("[DEBUG] After Commit")
        # =========================
        # VERIFY DATA
        # =========================
        verify_row = session.query(Operations).filter_by(id=1).first()
        print("\n========== DB VERIFY ==========")
        for column in Operations.__table__.columns:
            print(column.name, "=", getattr(verify_row, column.name))
        print("================================\n")
        print(
            f"[DB] Operations Updated Successfully -> "
            f"{', '.join(updated_fields)}")
    except Exception as e:
        session.rollback()
        print("[DB ERROR]", e)
    finally:
        session.close()
# =========================
# OPTIONAL: INIT FUNCTION
# =========================
# def init_db():
#     """
#     Call this once from your main application
#     to create tables if they don't exist.
#     """
#     Base.metadata.create_all(engine)


# =========================
# CREATE TABLES
# =========================
Base.metadata.create_all(bind=engine)

print("ALL TABLES CREATED SUCCESSFULLY")