from pymodbus.client.sync import ModbusTcpClient

PLC_IP = "192.168.1.11"
PLC_PORT = 502
UNIT_ID = 1

client = ModbusTcpClient(PLC_IP, port=PLC_PORT)

if not client.connect():
    print("❌ Connection Failed")
    exit()

print("✅ Connected to Waveshare")


# =====================================================
# SCAN COILS
# =====================================================
print("\n==============================")
print(" SCANNING COILS ")
print("==============================")

try:

    result = client.read_coils(0, 16, unit=UNIT_ID)

    if result.isError():
        print("❌ Coil Read Failed")

    else:
        for i, val in enumerate(result.bits):
            print(f"Coil {i} : {val}")

except Exception as e:
    print(f"Coil Error : {e}")


# =====================================================
# SCAN DISCRETE INPUTS
# =====================================================
print("\n==============================")
print(" SCANNING DISCRETE INPUTS ")
print("==============================")

try:

    result = client.read_discrete_inputs(0, 16, unit=UNIT_ID)

    if result.isError():
        print("❌ DI Read Failed")

    else:
        for i, val in enumerate(result.bits):
            print(f"DI {i} : {val}")

except Exception as e:
    print(f"DI Error : {e}")


# =====================================================
# SCAN HOLDING REGISTERS
# =====================================================
print("\n==============================")
print(" SCANNING HOLDING REGISTERS ")
print("==============================")

try:

    result = client.read_holding_registers(0, 16, unit=UNIT_ID)

    if result.isError():
        print("❌ Holding Register Read Failed")

    else:
        for i, val in enumerate(result.registers):
            print(f"Holding Register {i} : {val}")

except Exception as e:
    print(f"Holding Register Error : {e}")


# =====================================================
# SCAN INPUT REGISTERS
# =====================================================
print("\n==============================")
print(" SCANNING INPUT REGISTERS ")
print("==============================")

try:

    result = client.read_input_registers(0, 16, unit=UNIT_ID)

    if result.isError():
        print("❌ Input Register Read Failed")

    else:
        for i, val in enumerate(result.registers):
            print(f"Input Register {i} : {val}")

except Exception as e:
    print(f"Input Register Error : {e}")


client.close()

print("\n🔌 Connection Closed")