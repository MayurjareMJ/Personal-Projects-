from algorithms.Fire_and_Smoke import FireSmoke
from base_receiver import BaseReceiver
import xml.etree.ElementTree as ET


USECASE = "FIRESMOKE"
XML_PATH = r"/home/elansol/Desktop/SCOUT_VISION/reciever/receiver.xml"

def load_receiver_config(xml_path, usecase_name):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    for receiver in root.findall("receiver"):
        if receiver.get("name") == usecase_name:
            return {
                "host": receiver.find("host").text.strip(),
                "usecase_id": receiver.find("usecase_id").text.strip(),
                "port": int(receiver.find("port").text.strip()),
                "model_class": receiver.find("model_class").text.strip(),
                "model_path": receiver.find("model_path").text.strip(),
                "org_id": receiver.find("org_id").text.strip()
            }
 
    raise ValueError(f"Usecase '{usecase_name}' not found in config")


if __name__ == "__main__":

    config = load_receiver_config(
        xml_path=XML_PATH,
        usecase_name=USECASE
    )

    receiver = BaseReceiver(
        host=config["host"],
        usecase_id=config["usecase_id"],
        port=config["port"],
        model_cls=FireSmoke,
        model_path=config["model_path"],
        org_id=config["org_id"],
        name=USECASE
    )

    receiver.start()