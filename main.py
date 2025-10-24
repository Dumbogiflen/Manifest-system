import os
import json
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import mqtt_handler  # <-- vigtig: vi bruger det gamle handler-system

# -----------------------------------------------------
# Global data
# -----------------------------------------------------
messages = []
lifts = {}
current_lift = None
led_state = "blue"
msg_counter = 0

QUICK_FILE = "pilot_pi/quick.json"
quick_messages = []


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

# -----------------------------------------------------
# FastAPI setup
# -----------------------------------------------------
app = FastAPI()
BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# -----------------------------------------------------
# Routes
# -----------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
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
    return {
        "messages": messages,
        "quick": quick_messages,
        "lifts": list(lifts.values()),
        "current": current_lift,
        "led": led_state
    }


@app.post("/api/messages")
async def send_message(text: str = Form(...)):
    global msg_counter
    msg_counter += 1
    new_msg = {"id": msg_counter, "sender": "pilot", "text": text, "status": "sent"}
    messages.append(new_msg)

    # Send via mqtt_handler i stedet for direkte klient
    mqtt_handler.publish_pilot_message(text)
    print(f"📤 Sendt besked via mqtt_handler: {text}")

    return {"status": "ok", "message": new_msg}


@app.post("/api/quick/add")
async def add_quick_message(text: str = Form(...)):
    quick_messages.append(text)
    save_quick_messages()
    return {"status": "ok"}


@app.post("/api/quick/remove")
async def remove_quick_message(text: str = Form(...)):
    if text in quick_messages:
        quick_messages.remove(text)
        save_quick_messages()
    return {"status": "ok"}


@app.post("/api/lift/{lift_id}/complete")
async def complete_lift(lift_id: int):
    if lift_id in lifts:
        lifts[lift_id]["status"] = "completed"
    return {"status": "ok"}


@app.post("/api/lift/select")
async def select_lift(lift_id: int = Form(...)):
    global current_lift
    if lift_id in lifts:
        current_lift = lift_id
    return {"status": "ok"}


@app.post("/api/lift/send")
async def send_lift(data: str = Form(...)):
    """Modtager JSON liftdata fra manifest og sender videre via mqtt_handler"""
    try:
        lift = json.loads(data)
        lifts[lift["id"]] = lift
        mqtt_handler.publish_lift(lift)
        print(f"📤 Sendt lift via mqtt_handler: {lift}")
        return {"status": "ok", "lift": lift}
    except Exception as e:
        print(f"⚠️ Fejl ved send_lift: {e}")
        return {"status": "error", "detail": str(e)}


# -----------------------------------------------------
# Startup
# -----------------------------------------------------
@app.on_event("startup")
async def startup_event():
    print("🌍 Starter FastAPI og MQTT handler...")
    mqtt_handler.start()  # <-- starter din separate MQTT tråd
    print("✅ MQTT handler startet")

