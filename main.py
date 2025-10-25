import os
import json
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import mqtt_handler

# -----------------------------------------------------
# Filer og mappeopsætning
# -----------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

FILE_MESSAGES = os.path.join(DATA_DIR, "messages.json")
FILE_LIFTS = os.path.join(DATA_DIR, "lifts.json")
FILE_QUICK = os.path.join(DATA_DIR, "quick.json")

# -----------------------------------------------------
# Globale variabler
# -----------------------------------------------------
messages = []
lifts = {}
current_lift = None
led_state = "blue"
msg_counter = 0
quick_messages = ["5 min forsinket", "Klar til lift", "Skal tanke"]

# -----------------------------------------------------
# Hjælpefunktioner til gem/indlæsning
# -----------------------------------------------------
def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Kunne ikke indlæse {path}: {e}")
    return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Kunne ikke gemme {path}: {e}")

def load_all():
    global messages, lifts, quick_messages
    messages = load_json(FILE_MESSAGES, [])
    lifts = load_json(FILE_LIFTS, {})
    quick_messages = load_json(FILE_QUICK, ["5 min forsinket", "Klar til lift", "Skal tanke"])

def save_all():
    save_json(FILE_MESSAGES, messages)
    save_json(FILE_LIFTS, lifts)
    save_json(FILE_QUICK, quick_messages)

load_all()

# -----------------------------------------------------
# MQTT-opsætning
# -----------------------------------------------------
bus = mqtt_handler.MqttBus()

def on_pilot_message(text: str):
    """Modtager tekst fra piloten"""
    global msg_counter
    msg_counter += 1
    messages.append({
        "id": msg_counter,
        "direction": "in",
        "text": text,
        "status": "delivered"
    })
    save_json(FILE_MESSAGES, messages)
    print(f"📩 Besked fra pilot: {text}")

def on_pilot_ack(payload: dict):
    """Modtager kvittering fra pilot (for leveret/læst)"""
    print(f"📬 ACK fra pilot: {payload}")
    for m in messages:
        if m.get("id") == payload.get("for_id"):
            m["status"] = payload.get("status")
    save_json(FILE_MESSAGES, messages)

def on_lift_status(payload: dict):
    """Piloten har markeret lift som færdigt"""
    print(f"🏁 Lift-status modtaget: {payload}")
    lid = str(payload.get("id"))
    if lid in lifts:
        lifts[lid]["status"] = payload.get("status", "completed")
        save_json(FILE_LIFTS, lifts)

bus.on_pilot_message = on_pilot_message
bus.on_pilot_ack = on_pilot_ack
bus.on_lift_status = on_lift_status

# -----------------------------------------------------
# FastAPI setup
# -----------------------------------------------------
app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# -----------------------------------------------------
# API endpoints
# -----------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index():
    """Returnér webinterfacet"""
    with open(os.path.join(BASE_DIR, "static", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/state")
async def api_state():
    """Returnér systemstatus"""
    return {
        "messages": messages,
        "quick": quick_messages,
        "lifts": list(lifts.values()),
        "current": current_lift,
        "led": led_state
    }

@app.post("/api/messages")
async def api_send_message(text: str = Form(...)):
    """Send besked til pilot"""
    global msg_counter
    msg_counter += 1
    msg = {
        "id": msg_counter,
        "direction": "out",
        "text": text,
        "status": "sent"
    }
    messages.append(msg)
    save_json(FILE_MESSAGES, messages)
    bus.publish_text_to_pilot(text)
    print(f"📤 Sendt besked til pilot: {text}")
    return {"status": "ok", "message": msg}

@app.post("/api/lift/send")
async def api_send_lift(data: str = Form(...)):
    """Send liftdata til pilot"""
    lift = json.loads(data)
    lifts[str(lift["id"])] = lift
    save_json(FILE_LIFTS, lifts)
    bus.publish_lift(lift)
    print(f"📤 Sendt lift til pilot: {lift}")
    return {"status": "ok", "lift": lift}

@app.post("/api/quick/add")
async def api_add_quick(text: str = Form(...)):
    quick_messages.append(text)
    save_json(FILE_QUICK, quick_messages)
    return {"status": "ok"}

@app.post("/api/quick/remove")
async def api_remove_quick(text: str = Form(...)):
    if text in quick_messages:
        quick_messages.remove(text)
        save_json(FILE_QUICK, quick_messages)
    return {"status": "ok"}

# -----------------------------------------------------
# Startup
# -----------------------------------------------------
@app.on_event("startup")
async def startup_event():
    print("🌍 Starter FastAPI og MQTT-handler ...")
    bus.start()
    print("✅ MQTT-handler startet")
