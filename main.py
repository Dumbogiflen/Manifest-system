import os
import json
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Importér den oprindelige MQTT-handler
from mqtt_handler import start_mqtt, publish_message, publish_lift

# -----------------------
# DATA
# -----------------------
messages = []
lifts = {}
current_lift = None
msg_counter = 0
led_state = "blue"

QUICK_FILE = "pilot_pi/quick.json"
quick_messages = []

# -----------------------
# Hjælpefunktioner
# -----------------------
def load_quick_messages():
    global quick_messages
    if os.path.exists(QUICK_FILE):
        with open(QUICK_FILE, "r") as f:
            quick_messages = json.load(f)
    else:
        quick_messages = ["5 min forsinket", "Klar til lift", "Skal tanke"]

def save_quick_messages():
    with open(QUICK_FILE, "w") as f:
        json.dump(quick_messages, f)

load_quick_messages()

# -----------------------
# FastAPI setup
# -----------------------
app = FastAPI()
BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Viser hovedsiden"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "messages": messages,
        "quick": quick_messages,
        "lifts": list(lifts.values()),
        "current": current_lift,
        "led": led_state
    })


@app.get("/api/state")
async def get_state():
    """Returnerer hele systemets aktuelle status"""
    return {
        "messages": messages,
        "quick": quick_messages,
        "lifts": list(lifts.values()),
        "current": current_lift,
        "led": led_state
    }


@app.post("/api/messages")
async def send_message(text: str = Form(...)):
    """Sender en besked til manifest via MQTT"""
    global msg_counter
    msg_counter += 1
    new_msg = {"id": msg_counter, "sender": "pilot", "text": text, "status": "sent"}
    messages.append(new_msg)
    publish_message(text)
    return {"status": "ok", "message": new_msg}


@app.post("/api/quick/add")
async def add_quick_message(text: str = Form(...)):
    """Tilføjer hurtigbesked"""
    quick_messages.append(text)
    save_quick_messages()
    return {"status": "ok"}


@app.post("/api/quick/remove")
async def remove_quick_message(text: str = Form(...)):
    """Fjerner hurtigbesked"""
    if text in quick_messages:
        quick_messages.remove(text)
        save_quick_messages()
    return {"status": "ok"}


@app.post("/api/lift")
async def send_lift(data: str = Form(...)):
    """Sender liftdata til manifest via MQTT"""
    try:
        lift = json.loads(data)
        lifts[lift["id"]] = lift
        publish_lift(lift)
        return {"status": "ok", "lift": lift}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.on_event("startup")
async def startup_event():
    """Starter MQTT når webserveren starter"""
    start_mqtt()
