# database.py

import psycopg2
from psycopg2.extras import RealDictCursor


# db_config.py

import xml.etree.ElementTree as ET


def load_db_config():

    tree = ET.parse(
        "/home/elansol/Desktop/SCOUT_VISION/config/config.xml"
    )

    root = tree.getroot()

    db = root.find("database")

    return {

        "host": db.find("host").text,

        "port": int(db.find("port").text),

        "database": db.find("dbname").text,

        "user": db.find("username").text,

        "password": db.find("password").text,

        "schema": db.find("schema").text
    }


DB_CONFIG = load_db_config()


class Database:

    def __init__(self):

        self.conn = psycopg2.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            database=DB_CONFIG["database"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"]
        )

    def get_cameras(self):

        query = f"""
        SELECT
            sc.settings_camera_id,
            sc.camera_name,
            sc.camera_zone,
            sc.rtsp_url,
            cm.camera_id,
            cm.usecase_id

        FROM "{DB_CONFIG['schema']}".settings_camera sc

        INNER JOIN "{DB_CONFIG['schema']}".camera_mapper cm
        ON sc.settings_camera_id = cm.camera_id

        WHERE sc.camera_status = 'ENABLE'
        """

        with self.conn.cursor(
            cursor_factory=RealDictCursor
        ) as cursor:

            cursor.execute(query)

            return cursor.fetchall()