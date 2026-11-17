import time
import os
from pymodbus.client import ModbusTcpClient

# =========================================================
# CONFIG
# =========================================================
WAVESHARE_IP  = "192.168.1.11"
MODBUS_PORT   = 502
POLL_INTERVAL = 0.5  # seconds

# =========================================================
# MAPS
# =========================================================
DI_NAMES = {
    0: "CONVEYOR START",
    1: "MANUAL PASS",
    2: "RECHECK",
    3: "BYPASS"
}

COIL_NAMES = {
    0: "CONVEYOR STOP",
    1: "MANUAL PASS LAMP",
    2: "RECHECK LAMP",
    3: "AI READY LAMP",
    4: "TOWER GREEN",
    5: "TOWER YELLOW",
    6: "TOWER RED"
}

# =========================================================
# CONNECT
# =========================================================
client = ModbusTcpClient(host=WAVESHARE_IP, port=MODBUS_PORT)

print("Connecting to Waveshare...")
while True:
    if client.connect():
        print(f"Connected to {WAVESHARE_IP}:{MODBUS_PORT}")
        break
    print("Retrying...")
    time.sleep(2)

# =========================================================
# MONITOR LOOP
# =========================================================
def clear():
    os.system("cls" if os.name == "nt" else "clear")

def state(val):
    return "  ON  " if val else "  OFF "

while True:
    try:
        di_response   = client.read_discrete_inputs(0, 4)
        coil_response = client.read_coils(0, 7)

        clear()

        print("=" * 50)
        print("   WAVESHARE MODBUS MONITOR  —  192.168.1.11")
        print("=" * 50)

        # -------------------------------------------------
        # DIGITAL INPUTS
        # -------------------------------------------------
        print("\n  DIGITAL INPUTS")
        print("  " + "-" * 46)
        if di_response and not di_response.isError():
            bits = di_response.bits
            for idx, name in DI_NAMES.items():
                val = bool(bits[idx])
                indicator = "🟢" if val else "⚫"
                print(f"  DI {idx} | {indicator} {state(val)} | {name}")
        else:
            print("  [ERROR] Failed to read Digital Inputs")

        # -------------------------------------------------
        # OUTPUT COILS
        # -------------------------------------------------
        print("\n  OUTPUT COILS")
        print("  " + "-" * 46)
        if coil_response and not coil_response.isError():
            bits = coil_response.bits
            for idx, name in COIL_NAMES.items():
                val = bool(bits[idx])
                indicator = "🟢" if val else "⚫"
                print(f"  CO {idx} | {indicator} {state(val)} | {name}")
        else:
            print("  [ERROR] Failed to read Coils")

        print("\n" + "=" * 50)
        print(f"  Polling every {POLL_INTERVAL}s  |  Ctrl+C to exit")
        print("=" * 50)

    except KeyboardInterrupt:
        print("\nMonitor stopped.")
        client.close()
        break
    except Exception as e:
        print(f"[ERROR] {e}")

    time.sleep(POLL_INTERVAL)