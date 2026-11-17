

import json
import time
import threading
from kafka import KafkaProducer

class VisionProducer:
    def __init__(self, bootstrap_servers=None):
        if bootstrap_servers is None:
            bootstrap_servers = ["192.168.0.33:9092"]

        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        self.topics = {
            "PPE": "safety.ppe",
            "FIRE": "safety.fire",
            "FALL": "safety.fall",
            "VEHICLE": "safety.vehicle",
            "EXIT": "safety.exit",
            "CROWD": "safety.crowd",
            "INTRUSION": "safety.intrusion",
        }

        # Store latest message per use-case
        self.latest_message = {}
        self.lock = threading.Lock()

        # Start background sender thread
        thread = threading.Thread(target=self.send_every_second, daemon=True)
        thread.start()

    def send_every_second(self):
        """Background thread: sends 1 message per second."""
        while True:
            time.sleep(1.0)  # send rate = 1 Hz

            with self.lock:
                for use_case, package in self.latest_message.items():
                    topic, key, msg = package

                    try:
                        self.producer.send(
                            topic,
                            key=str(key).encode("utf-8"),
                            value=msg
                        )
                        self.producer.flush()
                        print(f"[INFO] Sent 1 message to {topic}")
                    except Exception as e:
                        print(f"[ERROR] Failed to send: {e}")

                # After sending, clear buffer
                self.latest_message.clear()

    def send(self, use_case, key, message_dict):
        """Store the newest message; background thread sends it every 1 sec."""

        topic = self.topics.get(use_case)
        if topic is None:
            print(f"[ERROR] Unknown use case: {use_case}")
            return

        with self.lock:
            # Overwrite previous message (keep only latest)
            self.latest_message[use_case] = (topic, key, message_dict)
