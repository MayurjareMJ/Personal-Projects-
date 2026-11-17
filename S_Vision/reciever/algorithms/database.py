
# from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, Float, func
# from sqlalchemy.orm import declarative_base, sessionmaker
# import xml.etree.ElementTree as ET
# from urllib.parse import quote_plus

# Base = declarative_base()

# # tree = ET.parse("vision_algorithm/config.xml")
# tree = ET.parse(r"C:\Users\Elansol\Desktop\SCOUT\SCOUT_AI\reciever\algorithms\config.xml")

# root = tree.getroot()

# db_node = root.find("database")

# username =  db_node.findtext("username")
# password = db_node.findtext("password")
# host = db_node.findtext("host")
# port = db_node.findtext("port")
# dbname = db_node.findtext("dbname")
# schema = db_node.findtext("schema")


# class SettingsUsecase(Base):
#     __tablename__ = "settings_usecase"
#     __table_args__ = {"schema": f"{schema}"}   # exact schema

#     settings_usecase_id = Column(String(255), primary_key=True)
#     usecase_name = Column(String(255))
#     usecase_acronym = Column(String(255))
#     model_in_use = Column(String(255))
#     model_threshold = Column(Float)
#     createdAt = Column(TIMESTAMP)
#     updatedAt = Column(TIMESTAMP)
#     createdBy = Column(String(255))
#     updatedBy = Column(String(255))

#     def __repr__(self):
#         return (
#             f"<SettingsUsecase(id='{self.settings_usecase_id}', "
#             f"name='{self.usecase_name}', "
#             f"acronym='{self.usecase_acronym}', "
#             f"model='{self.model_in_use}', "
#             f"threshold={self.model_threshold})>"
#         )


# class CameraMapper(Base):
#     __tablename__ = "camera_mapper"
#     __table_args__ = {"schema": f"{schema}"}

#     camera_mapper_id = Column(String(255), primary_key=True)  # ✅ REAL PK
#     camera_id = Column(String(255))
#     createdAt = Column(TIMESTAMP)
#     updatedAt = Column(TIMESTAMP)
#     createdBy = Column(String(255))
#     updatedBy = Column(String(255))
#     usecase_id = Column(String(255))
#     roi_cordinates = Column(String(255))
#     type_of_roi = Column(String(255))
#     zone_id = Column(String(255))        # ✅ KEEP
#     location_id = Column(String(255))    # ✅ KEEP

#     def __repr__(self):
#         return (
#             f"<CameraMapper(camera_mapper_id='{self.camera_mapper_id}', "
#             f"usecase_id='{self.usecase_id}', "
#             f"zoneid='{self.zoneid}', "
#             f"locationid='{self.locationid}')>"
#         )

# class SettingsCamera(Base):
#     __tablename__ = "settings_camera"
#     __table_args__ = {"schema": f"{schema}"}

#     settings_camera_id = Column(String(255), primary_key=True)
#     camera_name = Column(String(255))
#     camera_zone = Column(String(255))
#     user_name = Column(String(255))
#     password = Column(String(255))
#     camera_ip = Column(String(255))
#     refresh_rate = Column(Integer)
#     channel = Column(String(255))

#     def __repr__(self):
#         return (
#             f"<SettingsCamera(id='{self.settings_camera_id}', "
#             f"zone='{self.camera_zone}')>"
#         )


# class DBClient:
#     def __init__(self, username, password, host, database, port=5432):
#         self.username = username
#         self.password = password
#         self.host = host
#         self.database = database
#         self.port = port

#         safe_username = quote_plus(username)
#         safe_password = quote_plus(password)

#         self.db_url = (
#             f"postgresql://{safe_username}:{safe_password}"
#             f"@{host}:{port}/{database}"
#         )


#         self.engine = create_engine(self.db_url)
#         self.SessionLocal = sessionmaker(bind=self.engine)
#         self.session = self.SessionLocal()

#     def get_all_setting_uscases(self):
#         """Fetch all rows from camera_mapper table"""
#         return self.session.query(SettingsUsecase).all()
    
#     def get_all_camera_mappers(self):
#         """Fetch all rows from camera_mapper table"""
#         return self.session.query(CameraMapper).all()
    
#     def get_camera_count(self):
#         """
#         Returns count of DISTINCT camera_mapper_id
#         """
#         return (
#             self.session
#             .query(func.count(CameraMapper.camera_mapper_id.distinct()))
#             .scalar()
#         )


#     def get_camera_by_id(self, camera_mapper_id):
#         """Fetch one row by camera_mapper_id"""
#         return (
#             self.session.query(CameraMapper)
#             .filter_by(camera_mapper_id=camera_mapper_id)
#             .first()
#         )
    
#     def get_camera_zone_by_camera_id(self, camera_id: str):
#         """
#         Input  : camera_id (settings_camera_id)
#         Output : camera_zone
#         """
#         result = (
#             self.session
#             .query(SettingsCamera.camera_zone)
#             .filter(SettingsCamera.settings_camera_id == camera_id)
#             .first()
#         )

#         return result[0] if result else None


#     def close(self):
#         """Close DB session"""
#         self.session.close()
    
    


# # dbobject = DBClient(username,password,host,dbname,port)
# # ret = dbobject.get_all_setting_uscases()
# # for row in ret:
# #     print(row)

# # dbobject.close()










# database.py

from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, Float, Time, func
from sqlalchemy.orm import declarative_base, sessionmaker
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
import time
import threading

# --------------------------------------------------
# Load DB Config
# --------------------------------------------------

tree = ET.parse(r"c:\Users\joshi\Downloads\SCOUT CODES\SCOUT_AI\reciever\algorithms\config.xml")
root = tree.getroot()

db_node = root.find("database")

username = db_node.findtext("username")
password = db_node.findtext("password")
host = db_node.findtext("host")
port = db_node.findtext("port")
dbname = db_node.findtext("dbname")
schema = db_node.findtext("schema")

# --------------------------------------------------
# Base
# --------------------------------------------------
 
Base = declarative_base()

# --------------------------------------------------
# ORM MODELS
# --------------------------------------------------

class SettingsUsecase(Base):
    __tablename__ = "settings_usecase"
    __table_args__ = {"schema": schema}

    settings_usecase_id = Column(String(255), primary_key=True)
    usecase_name = Column(String(255))
    usecase_acronym = Column(String(255))
    model_in_use = Column(String(255))
    model_threshold = Column(Float)
    createdAt = Column(TIMESTAMP)
    updatedAt = Column(TIMESTAMP)


class CameraMapper(Base):
    __tablename__ = "camera_mapper"
    __table_args__ = {"schema": schema}

    camera_mapper_id = Column(String(255), primary_key=True)
    camera_id = Column(String(255))
    usecase_id = Column(String(255))
    roi_cordinates = Column(String(255))
    zone_id = Column(String(255))
    location_id = Column(String(255))


class SettingsCamera(Base):
    __tablename__ = "settings_camera"
    __table_args__ = {"schema": schema}

    settings_camera_id = Column(String(255), primary_key=True)
    camera_name = Column(String(255))
    camera_zone = Column(String(255))
    camera_ip = Column(String(255))


class EmployeeIdleTime(Base):
    __tablename__ = "employee_idle_time_without_face_setting"
    __table_args__ = {"schema": schema}

    cameras = Column(String(255), primary_key=True)
    threshhold = Column(Integer)


class ShiftInformation(Base):
    __tablename__ = "setting_shift_information"
    __table_args__ = {"schema": schema}

    shift_id = Column(String(255), primary_key=True)
    start_time = Column(Time)
    end_time = Column(Time)

# --------------------------------------------------
# DB CLIENT
# --------------------------------------------------

class DBClient:

    def __init__(self, refresh_interval=600):
        self.refresh_interval = refresh_interval
        safe_username = quote_plus(username)
        safe_password = quote_plus(password)

        db_url = (
            f"postgresql://{safe_username}:{safe_password}"
            f"@{host}:{port}/{dbname}"
        )

        self.engine = create_engine(db_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine)

         # 🔥 In-memory cache
        self.cache = {}
        self._lock = threading.RLock()
        # Load initially
        self.refresh_all()
        # Start background refresh thread
        self.start_auto_refresh()
      


    def refresh_all(self):
        print("Refreshing DB cache...")

        session = self.SessionLocal()
        try:
            new_cache = {}

            # -------- Settings Camera --------
            cameras = session.query(SettingsCamera).all()
            new_cache["settings_camera"] = {
                cam.settings_camera_id: cam
                for cam in cameras
            }

            # -------- Camera Mapper --------
            mappers = session.query(CameraMapper).all()
            new_cache["camera_mapper"] = {
                (cm.camera_id, cm.usecase_id): cm
                for cm in mappers
            }

            # -------- Shift Info --------
            new_cache["shift_info"] = session.query(ShiftInformation).first()

            # -------- Employee Idle --------
            idle_settings = session.query(EmployeeIdleTime).all()
            new_cache["employee_idle"] = {
                idle.cameras: idle
                for idle in idle_settings
            }

            # -------- Usecases --------
            usecases = session.query(SettingsUsecase).all()
            new_cache["settings_usecase"] = {
                uc.settings_usecase_id: uc
                for uc in usecases
            }

            # 🔥 Atomic swap (very important)
            with self._lock:
               self.cache = new_cache

            print("DB cache refreshed successfully")

        except Exception as e:
            print("DB REFRESH ERROR:", e)

        finally:
            session.close()
            
    def start_auto_refresh(self):

        def refresh_loop():
            while True:
                time.sleep(self.refresh_interval)
                print("Auto refreshing DB cache...")
                self.refresh_all()

        thread = threading.Thread(target=refresh_loop, daemon=True)
        thread.start()

    def get_camera_name(self, camera_id):
        with self._lock:
            cam = self.cache.get("settings_camera", {}).get(camera_id)
            return cam.camera_name if cam else None

    def get_camera_zone(self, camera_id):
        with self._lock:
            cam = self.cache.get("settings_camera", {}).get(camera_id)
            return cam.camera_zone if cam else None

    def get_roi(self, camera_id, usecase_id):
        with self._lock:
            cm = self.cache.get("camera_mapper", {}).get((camera_id, usecase_id))
            return cm.roi_cordinates if cm else None

    def get_shift_times(self):
        with self._lock:
            shift = self.cache.get("shift_info")
            if shift:
                return shift.start_time, shift.end_time
            return None, None