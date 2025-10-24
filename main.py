import os
import json
import ssl
import asyncio
from datetime import datetime
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import paho.mqtt.client as mqtt

# --------------------------
# KONFIG
# --------------------------
BROKER_HOST = "b984550852ed4879b205fb8f7745202a.s1.eu.hivemq.cloud"
BROKER_PORT = 443
BROKER_PATH = "/mqtt"
MQTT_USER = "Pilatus"
MQTT_PASS = "N*Zhf2Siub"

TOPIC_OUT = "pilatus/messages/manifest"
TOPIC_IN = "pilatus/messages/pilot"
TOPIC_LIFT = "pilatus/lift"
TOPIC_LIFT_STATUS = "pilatus/lift/status"

STATE = {"club": "Pilatus Manifest", "messages": [], "lifts": []}

BASE_DIR = os.path.dirname(__file__)

# --------------------------
# MQTT CALLBACKS
# --------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT: Forbundet til HiveMQ WebSocket-gateway")
        client.subscribe(TOPIC_IN)
        client.subscribe(TOPIC_LIFT_STATUS)
    else:
        print("❌ MQTT: Forbindelsesfejl, rc =", rc)

def on_message(client, userdata, msg):
    payload = msg.payload.decode()
    print(f"📥 MQTT {msg.topic}: {payload}")
    try:
        data = json.loads(payload)
        if msg.topic == TOPIC_IN:
            data["direction"] = "in"
            STATE["messages"].append(data)
        elif msg.topic == TOPIC_LIFT_STATUS:
            lid = data.get("id")
            for lift in STATE["lifts"]:
                if lift["id"] == lid:
                    lift["status"] = data.get("status", lift["status"])
    except Exception as e:
        print("⚠️ Fejl ved MQTT-besked:", e)

# --------------------------
# MQTT SETUP
# --------------------------
def create_client():
    client = mqtt.Client(transport="websockets")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.ws_set_options(path=BROKER_PATH)
    client.on_connect = on_connect
    client.on_message = on_message
    return client

mqtt_client = create_client()

def start_mqtt():
    try:
        print("🔌 Opretter MQTT WebSocket-forbindelse ...")
        mqtt_client.connect_async(BROKER_HOST, BROKER_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print("❌ Kunne ikke starte MQTT:", e)

# --------------------------
# FASTAPI APP
# --------------------------
app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, start_mqtt)
    print("🌍 FastAPI startet og MQTT forsøges oprettet.")

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(BASE_DIR, "static/index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/state")
async def get_state():
    return STATE

@app.post("/api/messages")
async def post_message(text: str = Form(...)):
    msg = {
        "id": len(STATE["messages"]) + 1,
        "direction": "out",
        "text": text,
        "status": "sent",
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    STATE["messages"].append(msg)
    payload = json.dumps(msg)
    print("📤 Sender besked til MQTT:", payload)
    try:
        mqtt_client.publish(TOPIC_OUT, payload)
    except Exception as e:
        print("❌ Fejl ved send:", e)
    return {"ok": True}

@app.post("/api/lift")
async def post_lift(request: Request):
    data = await request.json()
    STATE["lifts"].append(data)
    payload = json.dumps(data)
    print("📤 Sender lift til MQTT:", payload)
    try:
        mqtt_client.publish(TOPIC_LIFT, payload)
    except Exception as e:
        print("❌ Fejl ved send:", e)
    return {"ok": True}

# --------------------------
# LOCAL TEST
# --------------------------
if __name__ == "__main__":
    import uvicorn
    print("Kører lokalt på http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
