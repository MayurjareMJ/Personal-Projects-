import time
import redis
import xml.etree.ElementTree as ET
from pymodbus.client import ModbusTcpClient         
from database_handler import SessionLocal, insert_vision_result


class IOTriggerConfig:
    # =========================================================
    # DIGITAL INPUTS (DI)
    # =========================================================
    DI_CONVEYOR_START_IDX       = 0
    DI_MANUAL_PASS_IDX          = 1
    DI_RECHECK_IDX              = 2
    DI_BYPASS_IDX               = 3
    # =========================================================
    # OUTPUT COILS
    # =========================================================
    COIL_CONVEYOR_STOP_IDX      = 0
    COIL_MANUAL_PASS_LAMP_IDX   = 1
    COIL_RECHECK_LAMP_IDX       = 2
    COIL_AI_READY_LAMP_IDX      = 3
    COIL_TOWER_GREEN_IDX        = 4
    COIL_TOWER_YELLOW_IDX       = 5
    COIL_TOWER_RED_IDX          = 6

    MANUAL_PASS_LAMP_DURATION   = 5.0

    def __init__(self, config_path=r"/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/Config.xml"):
        self.db            = SessionLocal()
        self.config_path   = config_path
        self.waveshare_ip  = None
        self.modbus_port   = None
        self.load_config()
        # =====================================================
        # INPUT STATUS
        # =====================================================
        self.conveyor_start = False
        self.manual_pass    = False
        self.recheck        = False
        self.bypass         = False
        # =====================================================
        # MACHINE STATES
        # =====================================================
        self.conveyor_stopped_by_ai   = False
        # Edge Trigger Memory
        self.last_manual_pass         = False
        self.last_recheck             = False
        self.last_bypass              = False
        # Manual pass lamp timer
        self.manual_pass_lamp_on_time = None

    # =========================================================
    # LOAD CONFIG
    # =========================================================
    def load_config(self):
        try:
            tree = ET.parse(self.config_path)
            root = tree.getroot()
            self.waveshare_ip = root.find("Modbus/WaveshareIP").text.strip()
            self.modbus_port  = int(root.find("Modbus/ModbusPort").text.strip())
            print("===================================")
            print("      IO CONFIG LOADED")
            print("===================================")
            print(f"Waveshare IP : {self.waveshare_ip}")
            print(f"Modbus Port  : {self.modbus_port}")
        except Exception as e:
            print(f"[ERROR] Config Loading Failed : {e}")


class IOTrigger(IOTriggerConfig):
    def __init__(self, config_path=r"/home/bks01/Desktop/VISION/P-VI37-Kick_Operation_AI_Inspection/Config.xml"):
        super().__init__(config_path)
        # =====================================================
        # REDIS
        # =====================================================
        self.redis_client = redis.Redis(
            host="localhost", port=6379, db=0, decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()
        self.pubsub.subscribe("LISTEN_EVERYTHING")
        self.pubsub.subscribe("ai_ready_status")
        # =====================================================
        # MODBUS
        # =====================================================
        self.client = ModbusTcpClient(
            host=self.waveshare_ip,
            port=self.modbus_port
        )
        self._wait_for_connection()

    # =========================================================
    # WAIT FOR HARDWARE CONNECTION
    # =========================================================
    def _wait_for_connection(self):
        print("===================================")
        print("  CONNECTING TO WAVESHARE...")
        print("===================================")
        while True:
            if self.client.connect():
                result = self.client.read_discrete_inputs(0, 1)
                if result and not result.isError():
                    print("  WAVESHARE CONNECTED OK")
                    print("===================================")
                    break
            print("  Waiting for Waveshare hardware...")
            time.sleep(2)

    # =========================================================
    # SAFE SINGLE COIL WRITE
    # =========================================================
    def _safe_write_coil(self, index, value):
        result = self.client.write_coil(index, value)
        if not result or result.isError():
            print(f"[COIL WRITE FAIL] Coil {index} = {value}")

    # =========================================================
    # REDIS MESSAGE READER
    # =========================================================
    def read_redis_messages(self):
        try:
            message = self.pubsub.get_message()
            if message and message["type"] == "message":
                channel = message["channel"]
                data    = message["data"]
                print("===================================")
                print(f"CHANNEL : {channel}")
                print(f"DATA    : {data}")
                if channel == "LISTEN_EVERYTHING":
                    self.process_ai_result(data)
                elif channel == "ai_ready_status":
                    self.process_ai_ready(data)
        except Exception as e:
            print(f"[REDIS ERROR] {e}")

    # =========================================================
    # PROCESS AI RESULT
    # =========================================================
    def process_ai_result(self, result):
        if result == "OK":
            print("KICK TRAVEL OK")
            self._insert_db_record(result)

        elif result == "NOK":
            print("KICK TRAVEL NOK")
            self._insert_db_record(result)
            if (
                self.conveyor_start is True
                and self.bypass      is False
                and self.manual_pass is False
                and self.recheck     is False
            ):
                print("CONVEYOR STOP CONDITIONS MATCHED")
                self._safe_write_coil(self.COIL_CONVEYOR_STOP_IDX, True)
                self.conveyor_stopped_by_ai = True
            else:
                print("STOP CONDITION NOT MATCHED")

    # =========================================================
    # DATABASE INSERT
    # =========================================================
    def _insert_db_record(self, result):
        try:
            data = {
                "model_name":        "KICK_001",
                "station_id":        "ST01",
                "inspection_status": result,
                "image_path":        None,
                "video_path":        None,
                "bypassed":    "YES" if self.bypass      else "NO",
                "manual_pass": "YES" if self.manual_pass else "NO",
                "recheck":     "YES" if self.recheck     else "NO",
            }
            insert_vision_result(data)
        except Exception as e:
            print(f"[DB INSERT ERROR] {e}")

    # =========================================================
    # HANDLE STOPPED CONVEYOR STATES
    # =========================================================
    def handle_stopped_conveyor_logic(self):
        try:
            if not self.conveyor_stopped_by_ai:
                return
            # Recheck — single-shot rising edge
            if self.recheck and not self.last_recheck:
                print("RECHECK INITIATED")
                self.redis_client.publish("recheck_trigger", "RECHECK")
            # Manual pass — rising edge
            if self.manual_pass and not self.last_manual_pass:
                print("MANUAL PASS INITIATED")
                self.start_conveyor()
            # Bypass
            if self.bypass:
                print("BYPASS ACTIVE")
                self.start_conveyor()
        except Exception as e:
            print(f"[STOP LOGIC ERROR] {e}")

    # =========================================================
    # START CONVEYOR
    # =========================================================
    def start_conveyor(self):
        self._safe_write_coil(self.COIL_CONVEYOR_STOP_IDX, False)
        self.conveyor_stopped_by_ai = False
        print("CONVEYOR STARTED")

    # =========================================================
    # PROCESS AI READY
    # =========================================================
    # def process_ai_ready(self, status):
    #     try:
    #         state = status == "TRUE"
    #         self._safe_write_coil(self.COIL_AI_READY_LAMP_IDX, state)
    #         print(f"AI READY {'ON' if state else 'OFF'}")
    #     except Exception as e:
    #         print(f"[AI READY ERROR] {e}")
    def process_ai_ready(self, status):
        try:
            status = str(status).strip().upper()
            state = status in ["TRUE", "AI_READY", "ON", "1"]
            self._safe_write_coil(self.COIL_AI_READY_LAMP_IDX, state)
            print("===================================")
            print(f"AI READY STATUS : {status}")
            print(f"AI READY {'ON' if state else 'OFF'}")
        except Exception as e:
            print(f"[AI READY ERROR] {e}")

    # =========================================================
    # READ INPUTS
    # =========================================================
    def read_inputs(self):
        try:
            response = self.client.read_discrete_inputs(0, 4)
            if response and not response.isError():
                inputs = response.bits              # ← pymodbus returns .bits
                self.conveyor_start = bool(inputs[self.DI_CONVEYOR_START_IDX])
                self.manual_pass    = bool(inputs[self.DI_MANUAL_PASS_IDX])
                self.recheck        = bool(inputs[self.DI_RECHECK_IDX])
                self.bypass         = bool(inputs[self.DI_BYPASS_IDX])
                print("===================================")
                print(f"CONVEYOR START : {self.conveyor_start}")
                print(f"MANUAL PASS    : {self.manual_pass}")
                print(f"RECHECK        : {self.recheck}")
                print(f"BYPASS         : {self.bypass}")
            else:
                print("[ERROR] Failed To Read Inputs")
        except Exception as e:
            print(f"[MODBUS ERROR] {e}")

    # =========================================================
    # UPDATE INDICATOR LAMPS
    # =========================================================
    def update_indicator_lamps(self):
        try:
            # MANUAL PASS LAMP — 5-second pulse on rising edge
            rising_edge_manual = self.manual_pass and not self.last_manual_pass
            if rising_edge_manual:
                self._safe_write_coil(self.COIL_MANUAL_PASS_LAMP_IDX, True)
                self.manual_pass_lamp_on_time = time.time()
                print("MANUAL PASS LAMP ON")
            elif self.manual_pass_lamp_on_time is not None:
                elapsed = time.time() - self.manual_pass_lamp_on_time
                if elapsed >= self.MANUAL_PASS_LAMP_DURATION:
                    self._safe_write_coil(self.COIL_MANUAL_PASS_LAMP_IDX, False)
                    self.manual_pass_lamp_on_time = None
                    print("MANUAL PASS LAMP OFF (timeout)")
            # TOWER GREEN — ON while conveyor is running
            self._safe_write_coil(self.COIL_TOWER_GREEN_IDX, self.conveyor_start)
            # TOWER YELLOW — mirrors BYPASS input
            self._safe_write_coil(self.COIL_TOWER_YELLOW_IDX, self.bypass)
            # TOWER RED — ON when conveyor is NOT running
            self._safe_write_coil(self.COIL_TOWER_RED_IDX, not self.conveyor_start)
        except Exception as e:
            print(f"[LAMP UPDATE ERROR] {e}")

    # =========================================================
    # MAIN LOOP
    # =========================================================
    def run(self):
        while True:
            self.read_redis_messages()
            self.read_inputs()
            self.handle_stopped_conveyor_logic()
            self.update_indicator_lamps()
            # Save edge states AFTER both handlers have used them
            self.last_manual_pass = self.manual_pass
            self.last_recheck     = self.recheck
            self.last_bypass      = self.bypass
            time.sleep(0.05)


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    app = IOTrigger()
    app.run()