
from sqlalchemy import create_engine, Column, Integer, String, TIMESTAMP, Float, func
from sqlalchemy.orm import declarative_base, sessionmaker
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

Base = declarative_base()

# tree = ET.parse("vision_algorithm/config.xml")
tree = ET.parse(r"/home/elansol/Desktop/SCOUT_VISION/config/config.xml")

root = tree.getroot()

db_node = root.find("database")

username =  db_node.findtext("username")
password = db_node.findtext("password")
host = db_node.findtext("host")
port = db_node.findtext("port")
dbname = db_node.findtext("dbname")
schema = db_node.findtext("schema")


class SettingsUsecase(Base):
    __tablename__ = "settings_usecase"
    __table_args__ = {"schema": f"{schema}"}   # exact schema

    settings_usecase_id = Column(String(255), primary_key=True)
    usecase_name = Column(String(255))
    usecase_acronym = Column(String(255))
    model_in_use = Column(String(255))
    model_threshold = Column(Float)
    createdAt = Column(TIMESTAMP)
    updatedAt = Column(TIMESTAMP)
    createdBy = Column(String(255))
    updatedBy = Column(String(255))

    def __repr__(self):
        return (
            f"<SettingsUsecase(id='{self.settings_usecase_id}', "
            f"name='{self.usecase_name}', "
            f"acronym='{self.usecase_acronym}', "
            f"model='{self.model_in_use}', "
            f"threshold={self.model_threshold})>"
        )


class CameraMapper(Base):
    __tablename__ = "camera_mapper"
    __table_args__ = {"schema": f"{schema}"}

    camera_mapper_id = Column(String(255), primary_key=True)  # ✅ REAL PK
    camera_id = Column(String(255))
    createdAt = Column(TIMESTAMP)
    updatedAt = Column(TIMESTAMP)
    createdBy = Column(String(255))
    updatedBy = Column(String(255))
    usecase_id = Column(String(255))
    roi_cordinates = Column(String(255))
    type_of_roi = Column(String(255))
    zone_id = Column(String(255))        # ✅ KEEP
    location_id = Column(String(255))    # ✅ KEEP

    def __repr__(self):
        return (
            f"<CameraMapper(camera_mapper_id='{self.camera_mapper_id}', "
            f"usecase_id='{self.usecase_id}', "
            f"zoneid='{self.zoneid}', "
            f"locationid='{self.locationid}')>"
        )


class DBClient:
    def __init__(self, username, password, host, database, port=5432):
        self.username = username
        self.password = password
        self.host = host
        self.database = database
        self.port = port

        safe_username = quote_plus(username)
        safe_password = quote_plus(password)

        self.db_url = (
            f"postgresql://{safe_username}:{safe_password}"
            f"@{host}:{port}/{database}"
        )


        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session = self.SessionLocal()

    def get_all_setting_uscases(self):
        """Fetch all rows from camera_mapper table"""
        return self.session.query(SettingsUsecase).all()
    
    def get_all_camera_mappers(self):
        """Fetch all rows from camera_mapper table"""
        return self.session.query(CameraMapper).all()
    
    def get_camera_count(self):
        """
        Returns count of DISTINCT camera_mapper_id
        """
        return (
            self.session
            .query(func.count(CameraMapper.camera_mapper_id.distinct()))
            .scalar()
        )


    def get_camera_by_id(self, camera_mapper_id):
        """Fetch one row by camera_mapper_id"""
        return (
            self.session.query(CameraMapper)
            .filter_by(camera_mapper_id=camera_mapper_id)
            .first()
        )

    def close(self):
        """Close DB session"""
        self.session.close()
    
    