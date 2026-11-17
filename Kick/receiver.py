import redis
import json

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# =========================
# EVENT HANDLERS
# =========================
def handle_conveyor(data):
    print("[CONVEYOR]")
    print("State:", data["value"])   # True / False only

def handle_bypass(data):
    print("[BYPASS]")
    print("State:", data["value"])   # True / False only

def handle_recheck(data):
    print("[RECHECK]")
    print("Triggered:", data["value"])  # True only when triggered

def handle_manual_pass(data):
    print("[MANUAL PASS]")
    print("Triggered:", data["value"])  # True only when triggered


# =========================
# ROUTER
# =========================
def route_event(data):
    event = data.get("event")
    value = data.get("value")

    if event == "conveyor":
        handle_conveyor(data)

    elif event == "bypass":
        handle_bypass(data)

    elif event == "recheck":
        if value is True:
            handle_recheck(data)

    elif event == "manual_pass":
        if value is True:
            handle_manual_pass(data)

    else:
        print("[UNKNOWN EVENT]", data)


# =========================
# LISTENER LOOP
# =========================
def listen():
    pubsub = r.pubsub()
    pubsub.subscribe("LISTEN_EVERYTHING")

    print("Listening on LISTEN_EVERYTHING...\n")

    for msg in pubsub.listen():
        if msg["type"] != "message":
            continue

        try:
            data = json.loads(msg["data"])
            route_event(data)

        except Exception as e:
            print("[ERROR] Invalid message:", e)


if __name__ == "__main__":
    listen()