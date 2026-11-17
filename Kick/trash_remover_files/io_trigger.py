import time
import json
import redis
import threading
from database_handler import update_operations_status


from pymodbus.client import ModbusTcpClient

# =====================================================
# CONFIG
# =====================================================
WAVESHARE_IP = "192.168.1.11"
MODBUS_PORT = 502

# =====================================================
# MODBUS MAP
# =====================================================

# -------------------------
# DIGITAL INPUTS
# -------------------------
DI_CONVEYOR_START_IDX = 0
DI_MANUAL_PASS_IDX    = 1
DI_RECHECK_IDX        = 2
DI_BYPASS_IDX         = 3

# -------------------------
# OUTPUT COILS
# -------------------------
COIL_CONVEYOR_STOP_IDX     = 0
COIL_MANUAL_PASS_LAMP_IDX  = 1
COIL_RECHECK_LAMP_IDX      = 2
COIL_AI_READY_LAMP_IDX     = 3

COIL_TOWER_GREEN_IDX       = 4
COIL_TOWER_YELLOW_IDX      = 5
COIL_TOWER_RED_IDX         = 6


# =====================================================
# REDIS BUS
# =====================================================
class RedisBus:

    def __init__(self):

        self.r = redis.Redis(
            host="localhost",
            port=6379,
            decode_responses=True
        )

        self.channel = "LISTEN_EVERYTHING"

    def publish(self, event, value):

        self.r.publish(
            self.channel,
            json.dumps({
                "event": event,
                "value": value,
                "ts": time.time()
            })
        )


# =====================================================
# WAVESHARE MODBUS DRIVER
# =====================================================
class WaveshareIO:

    def __init__(self):

        self.client = ModbusTcpClient(
            WAVESHARE_IP,
            port=MODBUS_PORT
        )

        connected = self.client.connect()

        if connected:
            print(f"[IO] Connected to Waveshare {WAVESHARE_IP}")
        else:
            print("[IO ERROR] Failed to connect")

    # =================================================
    # READ DIGITAL INPUT
    # =================================================
    def read_di(self, idx):

        try:

            if not self.client.connected:
                print("[MODBUS] Reconnecting...")
                self.client.connect()

            res = self.client.read_discrete_inputs(idx, 1)

            if res.isError():
                return 0

            return int(res.bits[0])

        except Exception as e:

            print("[MODBUS READ ERROR]", e)

            try:
                self.client.connect()
            except:
                pass

            return 0

    # =================================================
    # WRITE COIL
    # =================================================
    def write_coil(self, idx, value):

        try:

            if not self.client.connected:
                print("[MODBUS] Reconnecting...")
                self.client.connect()

            self.client.write_coil(
                idx,
                bool(value)
            )

            print(f"[COIL] {idx} → {value}")

        except Exception as e:

            print("[MODBUS WRITE ERROR]", e)

            try:
                self.client.connect()
            except:
                pass


# =====================================================
# TOWER LIGHT CONTROL
# =====================================================
class TowerLight:

    def __init__(self, io):

        self.io = io

    def off(self):

        self.io.write_coil(
            COIL_TOWER_GREEN_IDX,
            0
        )

        self.io.write_coil(
            COIL_TOWER_YELLOW_IDX,
            0
        )

        self.io.write_coil(
            COIL_TOWER_RED_IDX,
            0
        )


# =====================================================
# IO CONTROLLER CORE
# =====================================================
class IOTrigger:

    def __init__(self):

        self.io = WaveshareIO()

        self.redis = RedisBus()

        self.tower = TowerLight(self.io)

        self.state = "IDLE"

        self.conveyor = False

        self.bypass = False

        self.last_inputs = None

        # =============================================
        # OUTPUT CACHE
        # =============================================
        self.last_outputs = {
            "green": None,
            "yellow": None,
            "red": None,
            "stop": None,
            "manual": None,
            "recheck": None,
            "ai": None,
        }

    # =================================================
    # INPUT READ
    # =================================================
    def read_inputs(self):

        return {

            "conveyor":
                self.io.read_di(
                    DI_CONVEYOR_START_IDX
                ),

            "manual_pass":
                self.io.read_di(
                    DI_MANUAL_PASS_IDX
                ),

            "recheck":
                self.io.read_di(
                    DI_RECHECK_IDX
                ),

            "bypass":
                self.io.read_di(
                    DI_BYPASS_IDX
                ),
        }

    # =================================================
    # SAFE COIL WRITE
    # =================================================
    def write_coil(self, idx, value, key):

        if self.last_outputs[key] == value:
            return

        self.io.write_coil(idx, value)

        self.last_outputs[key] = value

    # =================================================
    # MANUAL PASS LAMP PULSE
    # =================================================
    def manual_pass_lamp(self):

        def pulse():

            self.write_coil(
                COIL_MANUAL_PASS_LAMP_IDX,
                1,
                "manual"
            )

            time.sleep(5)

            self.write_coil(
                COIL_MANUAL_PASS_LAMP_IDX,
                0,
                "manual"
            )

        threading.Thread(
            target=pulse,
            daemon=True
        ).start()

    # =================================================
    # REDIS EVENT HANDLER
    # =================================================
    def handle_event(self, event, value):

        print(f"[REDIS EVENT] {event} → {value}")

        # =============================================
        # STOP CONVEYOR
        # =============================================
        if event == "STOP_CONVEYOR":

            self.write_coil(
                COIL_CONVEYOR_STOP_IDX,
                1,
                "stop"
            )

            self.state = "IDLE"

        # =============================================
        # START CONVEYOR
        # =============================================
        elif event == "START_CONVEYOR":

            self.write_coil(
                COIL_CONVEYOR_STOP_IDX,
                0,
                "stop"
            )

            self.state = "RUN"

        # =============================================
        # MANUAL PASS
        # =============================================
        elif event == "MANUAL_PASS":

            self.manual_pass_lamp()

        # =============================================
        # RECHECK LAMP
        # =============================================
        elif event == "RECHECK_LAMP":

            self.write_coil(
                COIL_RECHECK_LAMP_IDX,
                value,
                "recheck"
            )

        # =============================================
        # AI READY
        # =============================================
        elif event == "AI_READY":

            self.write_coil(
                COIL_AI_READY_LAMP_IDX,
                value,
                "ai"
            )

        # FORCE INPUT REFRESH
        self.last_inputs = None


    # =================================================
    # STATE MACHINE
    # =================================================
    def update(self):

        inputs = self.read_inputs()

        self.conveyor = bool(
            inputs["conveyor"]
        )

        self.bypass = bool(
            inputs["bypass"]
        )

        # =============================================
        # STATE LOGIC
        # =============================================
        if not self.conveyor:

            new_state = "IDLE"

        elif self.bypass:

            new_state = "BYPASS"

        else:

            new_state = "RUN"

        self.state = new_state

        # =============================================
        # TOWER LIGHT LOGIC
        # =============================================
        green = (
            1
            if self.state in ["RUN", "BYPASS"]
            else 0
        )

        yellow = (
            1
            if self.state == "BYPASS"
            else 0
        )

        red = (
            1
            if self.state == "IDLE"
            else 0
        )

        self.write_coil(
            COIL_TOWER_GREEN_IDX,
            green,
            "green"
        )

        self.write_coil(
            COIL_TOWER_YELLOW_IDX,
            yellow,
            "yellow"
        )

        self.write_coil(
            COIL_TOWER_RED_IDX,
            red,
            "red"
        )

        # =============================================
        # INPUT CHANGE TRACKING
        # =============================================
        # =============================
        # RUNNING / STOP UPDATE
        # =============================

        if inputs != self.last_inputs:

            # =============================
            # BYPASS DB UPDATE
            # =============================
            update_operations_status(

                running=(
                    "YES"
                    if inputs["conveyor"]
                    else "NO"
                ),

                stop=(
                    "NO"
                    if inputs["conveyor"]
                    else "YES"
                ),

                bypass=(
                    "YES"
                    if inputs["bypass"]
                    else "NO"
                ),

                manual_pass=(
                    "YES"
                    if inputs["manual_pass"]
                    else "NO"
                ),

                recheck=(
                    "YES"
                    if inputs["recheck"]
                    else "NO"
                )
            )
  
            # =============================
            # PUBLISH REDIS EVENTS
            # =============================
            self.redis.publish(
                "CONVEYOR_STATE",
                bool(inputs["conveyor"])
            )

            self.redis.publish(
                "BYPASS_STATE",
                bool(inputs["bypass"])
            )

            self.redis.publish(
                "MANUAL_PASS_TRIGGER",
                bool(inputs["manual_pass"])
            )

            self.redis.publish(
                "RECHECK_TRIGGER",
                bool(inputs["recheck"])
            )

            self.last_inputs = inputs

            self.debug()

    # =================================================
    # DEBUG
    # =================================================
    def debug(self):

        print("\n========== IO STATUS ==========")

        print("STATE:", self.state)

        print("CONVEYOR:", self.conveyor)

        print("BYPASS:", self.bypass)

        print("INPUTS:", self.last_inputs)

        print("================================\n")


# =====================================================
# REDIS LISTENER
# =====================================================
def redis_listener(io):

    r = redis.Redis(
        host="localhost",
        port=6379,
        decode_responses=True
    )

    pubsub = r.pubsub()

    pubsub.subscribe("LISTEN_EVERYTHING")

    print("[IO] Redis Listener Started")

    for msg in pubsub.listen():

        if msg["type"] != "message":
            continue

        try:

            data = json.loads(msg["data"])

            io.handle_event(
                data["event"],
                data["value"]
            )

        except Exception as e:

            print("[REDIS ERROR]", e)


# =====================================================
# MAIN LOOP
# =====================================================
if __name__ == "__main__":

    io = IOTrigger()

    # =============================================
    # START REDIS THREAD
    # =============================================
    threading.Thread(
        target=redis_listener,
        args=(io,),
        daemon=True
    ).start()

    print("[SYSTEM] IO_TRIGGER STARTED")

    # =============================================
    # MAIN SCAN LOOP
    # =============================================
    while True:

        io.update()

        time.sleep(0.05)