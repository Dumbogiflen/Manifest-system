# main.py
import os, json
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from db import init as db_init, add_message, list_messages, update_message_status, upsert_lift, list_lifts, set_lift_status
from mqtt_handler import MqttBus

CLUB_NAME = os.getenv("CLUB_NAME", "Pilatus Manifest")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------- UI ----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

# ---------- STATE ----------
@app.get("/api/state")
async def api_state():
    return {
        "club": CLUB_NAME,
        "messages": list_messages(),
        "lifts": list_lifts()
    }

# ---------- QUICK MESSAGES (simple local list i RAM) ----------
QUICK = ["5 min forsinket", "Klar til lift", "Skal tanke"]
@app.get("/api/quick")
async def get_quick():
    return QUICK

@app.post("/api/quick/add")
async def add_quick(text: str = Form(...)):
    if text and text not in QUICK:
        QUICK.append(text)
    return {"status":"ok"}

@app.post("/api/quick/remove")
async def remove_quick(text: str = Form(...)):
    if text in QUICK:
        QUICK.remove(text)
    return {"status":"ok"}

# ---------- BESKEDER ----------
@app.post("/api/messages")
async def post_message(text: str = Form(...)):
    # Manifest -> Pilot
    m = add_message(direction="out", text=text, status="sent")
    mqtt.publish_text_to_pilot(text)
    return {"status": "ok", "message": m}

# Markér modtaget eller læst fra Manifest-siden (til Pilot)
class AckIn(BaseModel):
    for_id: int
    status: str   # delivered|read
@app.post("/api/messages/ack")
async def post_ack(ack: AckIn):
    mqtt.publish_ack_to_pilot({"for_id": ack.for_id, "status": ack.status})
    return {"status":"ok"}

# ---------- LIFT ----------
class LiftRow(BaseModel):
    alt: int
    jumpers: int
    overflights: int

class LiftIn(BaseModel):
    id: int
    status: str = "active"     # active/completed
    rows: List[LiftRow]
    totals_jumpers: Optional[int] = None
    totals_canopies: Optional[int] = None

@app.post("/api/lift")
async def post_lift(l: LiftIn):
    # Filtrér rækker uden springere
    rows = [r.dict() for r in l.rows if r.jumpers > 0]

    # Totals: hvis tomme, brug summering af springere; canopies = totals_jumpers hvis ikke sat
    tj = l.totals_jumpers if l.totals_jumpers is not None else sum(r["jumpers"] for r in rows)
    tc = l.totals_canopies if l.totals_canopies is not None else tj

    lift = {
        "id": l.id,
        "name": f"Lift {l.id}",
        "status": l.status,
        "rows": rows,
        "totals": {"jumpers": tj, "canopies": tc}
    }
    upsert_lift(lift)
    mqtt.publish_lift(lift)
    return {"status":"ok","lift":lift}

# ---------- MQTT BINDINGS ----------
mqtt = MqttBus()

def _on_pilot_message(text: str):
    # Pilot -> Manifest (tekst)
    add_message(direction="in", text=text, status="delivered")

def _on_pilot_ack(payload: dict):
    # Pilot -> Manifest: {"for_id": <int>, "status":"delivered"|"read"}
    try:
        mid = int(payload.get("for_id"))
        st = str(payload.get("status","delivered"))
        update_message_status(mid, st)
    except Exception as e:
        print("ack parse error:", e)

def _on_lift_status(payload: dict):
    # Pilot -> Manifest: {"id":7,"status":"completed"}
    try:
        lid = int(payload.get("id"))
        st = str(payload.get("status","active"))
        set_lift_status(lid, st)
    except Exception as e:
        print("lift_status parse error:", e)

@app.on_event("startup")
async def on_start():
    db_init()
    mqtt.on_pilot_message = _on_pilot_message
    mqtt.on_pilot_ack = _on_pilot_ack
    mqtt.on_lift_status = _on_lift_status
    mqtt.start()

