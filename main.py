import os
import json
import time
from fastapi import FastAPI, Form, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import paho.mqtt.client as mqtt

# ==============================
# KONFIGURATION
# ==============================
BROKER = "broker.hivemq.com"  # offentlig MQTT broker
PORT = 1883
TOPIC_MSG_MANIFEST = "pilatus/messages/manifest"
TOPIC_MSG_PILOT = "pilatus/messages/pilot"
TOPIC_LIFT = "pilatus/lift"

CLUB_NAME = "Pilatus Manifest"

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")

# ==============================
# FASTAPI APP
# ==============================
app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ==============================
# DATASTRUKTURER
# ==============================
messages: list[dict] = []
sent_lifts: list[dict] = []

# ==============================
# MQTT CALLBACKS
# ==============================
def on_connect(client, userdata, flags, rc):
    print("✅ Forbundet til MQTT Broker" if rc == 0 else f"⚠️ MQTT-fejl ({rc})")
    client.subscribe(TOPIC_MSG_PILOT)
    client.subscribe(TOPIC_LIFT)

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    print(f"📩 Modtaget fra {topic}: {payload}")
    try:
        data = json.loads(payload)
    except Exception:
        print("❌ Kunne ikke parse JSON")
        return

    if topic == TOPIC_MSG_PILOT:
        data["direction"] = "in"
        data["status"] = "received"
        messages.append(data)
    elif topic == TOPIC_LIFT:
        # Hvis piloten sender liftstatus
        sent_lifts.insert(0, {**data, "ts": time.time()})

# ==============================
# MQTT OPSÆTNING
# ==============================
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

print("🔌 Forbinder til MQTT broker...")
mqtt_client.connect(BROKER, PORT, 60)
mqtt_client.loop_start()

# ==============================
# HJÆLPEFUNKTIONS
# ==============================
def _normalize_lift_payload(raw: dict) -> dict:
    """
    Normaliserer liftdata fra manifest-UI.
    Beholder manuelle totaler, fjerner rækker uden jumpers,
    og udfylder overflights=1 hvis tom.
    """
    lift_id = int(raw.get("id") or 0)
    name = raw.get("name") or f"Lift {lift_id}"

    # Filtrér og rengør rows
    rows_out = []
    for r in raw.get("rows", []):
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

    # Behold manuelle totaler hvis de findes
    totals_in = raw.get("totals") or {}
    tj = totals_in.get("jumpers")
    tc = totals_in.get("canopies")

    sum_jumpers = sum(r["jumpers"] for r in rows_out)
    try:
        total_jumpers = int(tj) if tj not in (None, "") else sum_jumpers
    except Exception:
        total_jumpers = sum_jumpers

    try:
        total_canopies = int(tc) if tc not in (None, "") else total_jumpers
    except Exception:
        total_canopies = total_jumpers

    return {
        "id": lift_id,
        "name": name,
        "status": "active",  # Manifest sender altid "active"
        "rows": rows_out,
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
async def api_state():
    """Returner nuværende beskeder og lifts til UI'et."""
    return {"club": CLUB_NAME, "messages": messages, "lifts": sent_lifts}

@app.post("/api/messages")
async def api_send_message(text: str = Form(...)):
    """Modtag besked fra UI og send til pilot."""
    msg = {
        "id": len(messages) + 1,
        "direction": "out",
        "text": text,
        "status": "sent",
        "remote_id": None,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    messages.append(msg)
    mqtt_client.publish(TOPIC_MSG_MANIFEST, json.dumps(msg))
    return {"ok": True}

@app.post("/api/lift")
async def api_send_lift(lift: dict = Body(...)):
    """Modtag lift fra UI og publicér til piloten."""
    payload = _normalize_lift_payload(lift)

    payload_with_ts = {**payload, "ts": time.time()}
    sent_lifts.insert(0, payload_with_ts)
    if len(sent_lifts) > 50:
        sent_lifts.pop()

    mqtt_client.publish(TOPIC_LIFT, json.dumps(payload), qos=1, retain=False)
    return {"status": "ok", "lift": payload}

# ==============================
# KØR SOM APP
# ==============================
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starter Pilatus Manifest server på port 8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
