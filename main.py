import os
import json
import ssl
import asyncio
from datetime import datetime

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import paho.mqtt.client as mqtt

# ---------------------------------------------------
# Konfiguration
# ---------------------------------------------------
BROKER = "b984550852ed4879b205fb8f7745202a.s1.eu.hivemq.cloud"
PORT = 443  # ✅ WebSocket + TLS
MQTT_USER = "Pilatus"
MQTT_PASS = "N*Zhf2Siub"

STATE = {
    "club": "Pilatus Manifest",
    "messages": [],
    "lifts": []
}

BASE_DIR = os.path.dirname(__file__)

# ---------------------------------------------------
# MQTT-opsætning
# ---------------------------------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Forbundet til HiveMQ via WebSocket/TLS")
        client.subscribe("pilatus/messages/pilot")
        client.subscribe("pilatus/lift/status")
    else:
        print("❌ MQTT-forbindelsesfejl:", rc)

def on_message(client, userdata, msg):
    payload = msg.payload.decode()
    print(f"📥 MQTT {msg.topic}: {payload}")
    try:
        data = json.loads(payload)
        if msg.topic == "pilatus/messages/pilot":
            data["direction"] = "in"
            STATE["messages"].append(data)
        elif msg.topic == "pilatus/lift/status":
            lift_id = data.get("id")
            for lift in STATE["lifts"]:
                if lift["id"] == lift_id:
                    lift["status"] = data.get("status", lift["status"])
    except Exception as e:
        print("⚠️ Fejl ved MQTT-besked:", e)

def create_client():
    client = mqtt.Client(transport="websockets")
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.ws_set_options(path="/mqtt")  # ✅ vigtigt for HiveMQ Cloud
    client.on_connect = on_connect
    client.on_message = on_message
    return client

mqtt_client = create_client()

def start_mqtt():
    try:
        mqtt_client.connect(BROKER, PORT, 60)
        mqtt_client.loop_start()
        print("🚀 Starter MQTT-loop ...")
    except Exception as e:
        print("❌ Kunne ikke forbinde til MQTT:", e)

# ---------------------------------------------------
# FastAPI-app
# ---------------------------------------------------
app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, start_mqtt)
    print("🌍 FastAPI-server startet.")

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
        "remote_id": None,
        "ts": datetime.now().isoformat(timespec='seconds')
    }
    STATE["messages"].append(msg)
    payload = json.dumps(msg)
    print("📤 Sender besked til MQTT:", payload)
    try:
        mqtt_client.publish("pilatus/messages/manifest", payload)
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
        mqtt_client.publish("pilatus/lift", payload)
    except Exception as e:
        print("❌ Fejl ved send:", e)
    return {"ok": True}

# ---------------------------------------------------
# Local dev (kun ved kørsel manuelt)
# ---------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print("Kører lokalt på http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
