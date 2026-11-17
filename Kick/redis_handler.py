# import redis
# import json
# import time
# import threading


# class RedisHandler:

#     def __init__(
#         self,
#         host='localhost',
#         port=6379,
#         channel="LISTEN_EVERYTHING"
#     ):

#         self.r = redis.Redis(
#             host=host,
#             port=port,
#             decode_responses=True
#         )

#         self.channel = channel

#         # =========================
#         # STATES
#         # =========================
#         self.conveyor_state = False
#         self.bypass_state = False
#         self.manual_pass_triggered = False
#         self.recheck_requested = False

#     # =========================
#     # PUBLISH EVENT
#     # =========================
#     def publish_event(self, event, value):

#         msg = {
#             "event": event,
#             "value": value,
#             "ts": time.time()
#         }

#         self.r.publish(
#             self.channel,
#             json.dumps(msg)
#         )

#         print(f"[REDIS PUBLISH] → {msg}")

#     # =========================
#     # REDIS LISTENER
#     # =========================
#     def redis_listener(self):

#         pubsub = self.r.pubsub()

#         pubsub.subscribe(self.channel)

#         print("Redis listener started...")

#         for msg in pubsub.listen():

#             if msg["type"] != "message":
#                 continue

#             try:

#                 data = json.loads(msg["data"])

#             except Exception as e:

#                 print("[REDIS ERROR]", e)
#                 continue

#             event = data.get("event")
#             value = data.get("value")

#             # =========================
#             # EVENTS
#             # =========================
#             if event == "conveyor":

#                 self.conveyor_state = value

#                 print(f"Conveyor → {self.conveyor_state}")

#             elif event == "bypass":

#                 self.bypass_state = value

#                 print(f"Bypass → {self.bypass_state}")

#             elif event == "recheck":

#                 print("[VISION] Recheck Trigger RECEIVED")

#                 self.recheck_requested = True

#             elif event == "manual_pass":

#                 print("[VISION] Manual PASS RECEIVED")

#                 self.manual_pass_triggered = True

#     # =========================
#     # START LISTENER
#     # =========================
#     def start_listener(self):

#         threading.Thread(
#             target=self.redis_listener,
#             daemon=True
#         ).start()

############################################
############################################
import redis
import json
import time
import threading

class RedisHandler:

    def __init__(
        self,
        host='localhost',
        port=6379,
        channel="LISTEN_EVERYTHING"
    ):

        self.host = host
        self.port = port
        self.channel = channel

        # =========================
        # CONNECT REDIS
        # =========================
        self.connect()

        # =========================
        # STATES
        # =========================
        self.conveyor_state = False
        self.bypass_state = False
        self.manual_pass_triggered = False
        self.recheck_requested = False

        self.waiting_for_recheck_result = False
        self.last_sent_stop = False

        # =========================
        # CALLBACKS
        # =========================
        self.callbacks = {}

    # =========================
    # REDIS CONNECTION
    # =========================
    def connect(self):

        while True:

            try:

                self.r = redis.Redis(
                    host=self.host,
                    port=self.port,
                    decode_responses=True
                )

                self.r.ping()

                print("[REDIS] Connected")

                break

            except Exception as e:

                print(f"[REDIS] Connection Failed: {e}")
                

                time.sleep(2)

    # =========================
    # PUBLISH EVENT
    # =========================
    def publish_event(self, event, value):

        msg = {
            "event": event,
            "value": value,
            "ts": time.time()
        }

        self.r.publish(
            self.channel,
            json.dumps(msg)
        )

        print(f"[REDIS PUBLISH] → {msg}")

    # =========================
    # REGISTER CALLBACK
    # =========================
    def register_callback(
        self,
        event,
        callback
    ):

        self.callbacks[event] = callback

    # =========================
    # REDIS LISTENER
    # =========================
    def redis_listener(self):

        pubsub = self.r.pubsub()

        pubsub.subscribe(self.channel)

        print("[REDIS] Listener Started...")

        for msg in pubsub.listen():

            if msg["type"] != "message":
                continue

            try:

                data = json.loads(msg["data"])

            except Exception as e:

                print("[REDIS ERROR]", e)

                continue

            event = data.get("event")
            value = data.get("value")

            # # =========================
            # # INTERNAL STATE UPDATE
            # # =========================
            # if event == "conveyor":

            #     self.conveyor_state = value

            #     print(f"Conveyor → {self.conveyor_state}")

            # elif event == "bypass":

            #     self.bypass_state = value

            #     print(f"Bypass → {self.bypass_state}")

            # elif event == "recheck":

            #     print("[REDIS] Recheck Trigger RECEIVED")

            #     self.recheck_requested = True

            # elif event == "manual_pass":

            #     print("[REDIS] Manual PASS RECEIVED")

            #     self.manual_pass_triggered = True

            # # =========================
            # # CUSTOM CALLBACKS
            # # =========================
            # if event in self.callbacks:

            #     try:

            #         self.callbacks[event](value)

            #     except Exception as e:

            #         print(
            #             f"[CALLBACK ERROR] {event}: {e}"
            #         )



            # =========================
            # INTERNAL STATE UPDATE
            # =========================

            # CONVEYOR STATE
            if event == "CONVEYOR_STATE":

                self.conveyor_state = bool(value)

                print(f"[REDIS] Conveyor → {self.conveyor_state}")


            # BYPASS STATE
            elif event == "BYPASS_STATE":

                self.bypass_state = bool(value)

                print(f"[REDIS] Bypass → {self.bypass_state}")


            # RECHECK BUTTON
            elif event == "RECHECK_TRIGGER":

                if value:

                    print("[REDIS] Recheck Trigger RECEIVED")

                    self.recheck_requested = True


            # MANUAL PASS BUTTON
            elif event == "MANUAL_PASS_TRIGGER":

                if value:

                    print("[REDIS] Manual PASS RECEIVED")

                    self.manual_pass_triggered = True


    # =========================
    # START LISTENER
    # =========================
    def start_listener(self):

        threading.Thread(
            target=self.redis_listener,
            daemon=True
        ).start()