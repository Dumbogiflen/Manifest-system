import os
import json
import time
import paho.mqtt.client as mqtt
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------
# KONFIGURATION
# ---------------------------
MQTT_HOST = "b984550852ed4879b205fb8f7745202a.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "Pilatus"
MQTT_PASS = "N*Zhf2Siub"

TOPIC_PILOT_TO_MANIFEST = "pilatus/manifest/messages"
TOPIC_MANIFEST_TO_PILOT = "pilatus/pilot/messages"
TOPIC_STATUS = "pilatus/messages/status"
TOPIC_LIFT = "pilatus/lift"

# ---------------------------
# DATASTRUKTUR
# ---------------------------
messages = []
lifts = []
msg_counter = 0

# ---------------------------
# MQTT CALLBACKS
# ---------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT tilsluttet til HiveMQ")
        client.subscribe(TOPIC_PILOT_TO_MANIFEST)
        client.subscribe(TOPIC_STATUS)
        client.subscribe(TOPIC_LIFT)
    else:
        print(f"❌ MQTT forbindelse fejlede ({rc})")

def on_message(client, userdata, msg):
    global msg_counter
    topic = msg.topic
    payload = msg.payload.decode()

    try:
        if topic == TOPIC_PILOT_TO_MANIFEST:
            msg_counter += 1
            messages.append({
                "id": msg_counter,
                "sender": "pilot",
                "text": payload,
                "status": "received"
            })
            print(f"📨 Modtog besked fra pilot: {payload}")

            # Send kvittering for modtagelse
            ack = json.dumps({"status": "delivered", "id": msg_counter})
            client.publish(TOPIC_STATUS, ack)

        elif topic == TOPIC_STATUS:
            data = json.loads(payload)
            msg_id = data.get("id")
            new_status = data.get("status")
            for m in messages:
                if m["id"] == msg_id:
                    m["status"] = new_status
                    print(f"🔄 Opdaterede status for besked {msg_id}: {new_status}")

        elif topic == TOPIC_LIFT:
            lift = json.loads(payload)
            lifts.append(lift)
            print(f"🪂 Liftdata modtaget fra pilot: {lift}")

    except Exception as e:
        print(f"⚠️ Fejl i on_message: {e}")

# ---------------------------
# MQTT OPSÆTNING
# ---------------------------
mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.tls_set()

def start_mqtt():
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    mqtt_client.loop_start()

# ---------------------------
# FASTAPI OPSÆTNING
# ---------------------------
app = FastAPI()
BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/state")
async def get_state():
    return {"messages": messages, "lifts": lifts}

@app.post("/api/messages")
async def send_message(text: str = Form(...)):
    global msg_counter
    msg_counter += 1
    new_msg = {"id": msg_counter, "sender": "manifest", "text": text, "status": "sent"}
    messages.append(new_msg)
    mqtt_client.publish(TOPIC_MANIFEST_TO_PILOT, text)
    print(f"📤 Sendte besked til pilot: {text}")
    # Registrer som sendt
    mqtt_client.publish(TOPIC_STATUS, json.dumps({"status": "sent", "id": msg_counter}))
    return {"status": "ok"}

@app.post("/api/lift/create")
async def create_lift(data: str = Form(...)):
    try:
        lift = json.loads(data)
        lifts.append(lift)
        mqtt_client.publish(TOPIC_LIFT, json.dumps(lift))
        print(f"🪂 Sendte lift til pilot: {lift}")
        return {"status": "ok"}
    except Exception as e:
        print(f"⚠️ Fejl i lift upload: {e}")
        return {"status": "error", "detail": str(e)}

@app.on_event("startup")
async def startup_event():
    start_mqtt()

# ---------------------------
# API til at markere læst besked
# ---------------------------
@app.post("/api/messages/read")
async def read_message(msg_id: int = Form(...)):
    for m in messages:
        if m["id"] == msg_id:
            m["status"] = "read"
            mqtt_client.publish(TOPIC_STATUS, json.dumps({"status": "read", "id": msg_id}))
            print(f"👁️  Markerede besked {msg_id} som læst")
    return {"status": "ok"}
