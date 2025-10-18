import os
import json
import time
import asyncio
import paho.mqtt.client as mqtt
from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# ==========================================================
# KONFIGURATION
# ==========================================================
BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC_MANIFEST = "pilatus/manifest"
TOPIC_PILOT = "pilatus/pilot"
TOPIC_LIFT = "pilatus/lift"

# evt. ændres når du sætter op i klubben
CLUB_NAME = "Pilatus Manifest"

# ==========================================================
# DATA OG STATE
# ==========================================================
messages: list[dict] = []
sent_lifts: list[dict] = []

BASE_DIR = os.path.dirname(__file__)

# ==========================================================
# FASTAPI APP
# ==========================================================
app = FastAPI(title="Pilatus Manifest System")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ==========================================================
# MQTT HANDLERS
# ==========================================================
def on_connect(client, userdata, flags, rc):
    print("📡 Forbundet til MQTT:", BROKER)
    client.subscribe(TOPIC_PILOT)
    client.subscribe(TOPIC_MANIFEST + "/status")
    client.subscribe(TOPIC_PILOT + "/status")


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
    except Exception as e:
        print("⚠️ Fejl i besked:", e)
        return

    topic = msg.topic

    # Når piloten sender beskeder
    if topic == TOPIC_PILOT:
        data["direction"] = "in"
        messages.append(data)

    # Når piloten sender statusopdatering (læst / leveret)
    elif topic.endswith("/status"):
        for m in messages:
            if str(m.get("id")) == str(data.get("id")):
                m["status"] = data.get("status", m.get("status"))

    # Begræns historik
    if len(messages) > 200:
        del messages[:-200]


# ==========================================================
# MQTT SETUP
# ==========================================================
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

mqtt_client.connect(BROKER, PORT, 60)
mqtt_client.loop_start()


# ==========================================================
# HJÆLPEFUNKTIONER
# ==========================================================
def _normalize_lift_payload(raw: dict) -> dict:
    """Beholder manuelle totals, og beregner kun hvis de mangler."""
    lift_id = int(raw.get("id") or 0)
    name = raw.get("name") or f"Lift {lift_id}"

    # Filtrér rækker uden springere
    rows_in = raw.get("rows", [])
    rows_out = []
    for r in rows_in:
        try:
            alt = int(r.get("alt") or 0)
            j = int(r.get("jumpers") or 0)
            if j <= 0:
                continue
            o = r.get("overflights")
            o = 1 if o in (None, "") else int(o)
            rows_out.append({"alt": alt, "jumpers": j, "overflights": o})
        except Exception:
            continue

    # Totals
    totals_in = raw.get("totals") or {}
    tj = totals_in.get("jumpers")
    tc = totals_in.get("canopies")

    sum_jumpers = sum(r["jumpers"] for r in rows_out)

    try:
        total_jumpers = int(tj) if tj not in (None, "",) else sum_jumpers
    except Exception:
        total_jumpers = sum_jumpers

    try:
        total_canopies = int(tc) if tc not in (None, "",) else total_jumpers
    except Exception:
        total_canopies = total_jumpers

    return {
        "id": lift_id,
        "name": name,
        "status": "active",
        "rows": rows_out,
        "totals": {"jumpers": total_jumpers, "canopies": total_canopies},
    }


# ==========================================================
# API ROUTES
# ==========================================================
@app.get("/", response_class=HTMLResponse)
async def index():
    """Serverer webinterfacet."""
    with open(os.path.join(BASE_DIR, "static", "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/state")
async def api_state():
    """Returner aktuel besked- og liftstatus."""
    return {
        "club": CLUB_NAME,
