import os
import json
import time
import threading
from fastapi import FastAPI, Form, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import paho.mqtt.client as mqtt

# ==============================
# KONFIGURATION
# ==============================
BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC_MSG_MANIFEST = "pilatus/messages/manifest"
TOPIC_MSG_PILOT = "pilatus/messages/pilot"
TOPIC_LIFT = "pilatus/lift"
CLUB_NAME = "Pilatus Manifest"

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")

# ==============================
# FASTAPI
# ==============================
app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ==============================
# DATA
# ==============================
messages: list[dict] = []
sent_lifts: list[dict] = []

# ==============================
# MQTT
# ==============================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT forbundet til broker")
        client.subscribe(TOPIC_MSG_PILOT)
        client.subscribe(TOPIC_LIFT)
    else:
        print(f"⚠️ MQTT fejl (rc={rc})")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        print(f"📩 MQTT modtaget [{msg.topic}] {payload}")
        data = json.loads(payload)
    except Exception as e:
        print(f"❌ MQTT parse fejl: {e}")
        return

    if msg.topic == TOPIC_MSG_PILOT:
        data["direction"] = "in"
        data["status"] = "received"
        messages.append(data)
    elif msg.topic == TOPIC_LIFT:
        sent_lifts.insert(0, {**data, "ts": time.time()})

# Start MQTT i separat tråd
def start_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, 60)
    client.loop_forever()

mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
mqtt_thread.start()

# Hjælpefunktioner
def normalize_lift(raw: dict) -> dict:
    lid = int(raw.get("id") or 0)
    name = raw.get("name") or f"Lift {lid}"

    rows = []
    for r in raw.get("rows", []):
        try:
            alt = int(r.get("alt") or 0)
            j = int(r.get("jumpers") or 0)
            if j <= 0:
                continue
            o = r.get("overflights")
            o = 1 if o in (None, "") else int(o)
            rows.append({"alt": alt, "jumpers": j, "overflights": o})
        except Exception:
            continue

    totals = raw.get("totals") or {}
    tj = totals.get("jumpers")
    tc = totals.get("canopies")

    sum_jumpers = sum(r["jumpers"] for r in rows)
    total_jumpers = int(tj) if tj not in (None, "") else sum_jumpers
    total_canopies = int(tc) if tc not in (None, "") else total_jumpers

    return {
        "id": lid,
        "name": name,
        "status": "active",
        "rows": rows,
        "totals": {"jumpers": total_jumpers, "canopies": total_canopies},
    }

# ==============================
# ROUTES
# ==============================
@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/state")
async def state():
    return {"club": CLUB_NAME, "messages": messages, "lifts": sent_lifts}

@app.post("/api/messages")
async def send_message(text: str = Form(...)):
    msg = {
        "id": len(messages) + 1,
        "direction": "out",
        "text": text,
        "status": "sent",
        "remote_id": None,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    messages.append(msg)
    print(f"📤 Sender besked til MQTT: {msg}")
    # Lav en midlertidig client til publishing
    pub = mqtt.Client()
    pub.connect(BROKER, PORT, 60)
    pub.publish(TOPIC_MSG_MANIFEST, json.dumps(msg))
    pub.disconnect()
    return {"ok": True}

@app.post("/api/lift")
async def send_lift(lift: dict = Body(...)):
    payload = normalize_lift(lift)
    sent_lifts.insert(0, {**payload, "ts": time.time()})
    if len(sent_lifts) > 50:
        sent_lifts.pop()

    print(f"📤 Sender lift til MQTT: {json.dumps(payload)}")
    pub = mqtt.Client()
    pub.connect(BROKER, PORT, 60)
    pub.publish(TOPIC_LIFT, json.dumps(payload), qos=1, retain=False)
    pub.disconnect()
    return {"status": "ok", "lift": payload}

# ==============================
# MAIN
# ==============================
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starter Pilatus Manifest på port 8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
