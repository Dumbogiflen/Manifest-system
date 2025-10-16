import os
import json
import ssl
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import paho.mqtt.client as mqtt

# -----------------------------
# Konfiguration (miljø el. defaults)
# -----------------------------
MQTT_HOST = os.getenv("MQTT_HOST", "b984550852ed4879b205fb8f7745202a.s1.eu.hivemq.cloud")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "Pilatus")
MQTT_PASS = os.getenv("MQTT_PASS", "N*Zhf2Siub")

# Topics (samme som piloten bruger)
TOPIC_PILOT_TO_MANIFEST = "pilatus/pilot/messages"     # pilot -> manifest (plain text i dag)
TOPIC_MANIFEST_TO_PILOT = "pilatus/manifest/messages"  # manifest -> pilot (plain text i dag)
TOPIC_LIFT_OUT          = "pilatus/lift"               # manifest -> pilot (JSON lift)
TOPIC_LIFT_STATUS       = "pilatus/lift/status"        # (valgfrit) pilot -> manifest (id,status)

# Filer
BASE_DIR   = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR   = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
QUICK_FILE = DATA_DIR / "quick.json"

# -----------------------------
# In-memory state (enkeltbrug)
# -----------------------------
messages: List[Dict[str, Any]] = []  # {id, sender, text, status, ts}
msg_counter = 0

# Quick beskeder persist
def load_quick() -> List[str]:
    if QUICK_FILE.exists():
        try:
            return json.loads(QUICK_FILE.read_text(encoding="utf-8"))
        except Exception:
            return ["5 min forsinket", "Klar til lift", "Skal tanke"]
    return ["5 min forsinket", "Klar til lift", "Skal tanke"]

def save_quick(q: List[str]) -> None:
    QUICK_FILE.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")

quick_messages = load_quick()

# Lifts (server-side liste så vi kan vise dagens sendt + evt. “completed” fra pilot)
# {id:int, name:str, status:str, rows:list, totals:dict, ts_iso:str}
lifts_sent: Dict[int, Dict[str, Any]] = {}

# -----------------------------
# MQTT client
# -----------------------------
mqtt_client = mqtt.Client(protocol=mqtt.MQTTv311)
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASS)
mqtt_client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT connected (Manifest)")
        client.subscribe(TOPIC_PILOT_TO_MANIFEST)
        client.subscribe(TOPIC_LIFT_STATUS)  # hvis piloten på et tidspunkt melder completed
    else:
        print(f"❌ MQTT connect failed: {rc}")

def on_message(client, userdata, msg):
    global msg_counter, lifts_sent
    try:
        payload = msg.payload.decode(errors="ignore")
        if msg.topic == TOPIC_PILOT_TO_MANIFEST:
            # Pilot sender ren tekst i dag (uden id’er)
            msg_counter += 1
            messages.append({
                "id": msg_counter,
                "sender": "pilot",
                "text": payload,
                "status": "delivered",   # vi har modtaget den
                "ts": datetime.now().isoformat(timespec="seconds")
            })
            print(f"✉️ Pilot → Manifest: {payload}")

        elif msg.topic == TOPIC_LIFT_STATUS:
            # Forventet payload: {"id": <int>, "status": "completed"}
            try:
                obj = json.loads(payload)
                lid = obj.get("id")
                status = obj.get("status")
                if isinstance(lid, int) and lid in lifts_sent and status:
                    lifts_sent[lid]["status"] = status
                    print(f"ℹ️ Lift #{lid} status opdateret til {status}")
            except Exception:
                pass

    except Exception as e:
        print("⚠️ on_message error:", e)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def start_mqtt():
    def _run():
        try:
            mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            mqtt_client.loop_forever()
        except Exception as e:
            print("❌ MQTT thread died:", e)
    t = threading.Thread(target=_run, daemon=True)
    t.start()

# -----------------------------
# FastAPI app
# -----------------------------
app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/api/state")
def api_state():
    # Saml frontend-state
    # (messages + quick + dagens lifts)
    today = datetime.now().strftime("%Y-%m-%d")
    # Filtrer lifts efter dagsdato (via ts_iso)
    day_lifts = [
        v for v in sorted(lifts_sent.values(), key=lambda x: x["id"])
        if v.get("ts_iso","").startswith(today)
    ]
    return {
        "messages": messages[-200:],  # beskær
        "quick": quick_messages,
        "lifts": day_lifts,
    }

@app.post("/api/messages")
def api_send_message(text: str = Form(...)):
    global msg_counter
    text = (text or "").strip()
    if not text:
        return {"status":"error", "error":"empty"}

    # Lokalt: opret “sendt”
    msg_counter += 1
    messages.append({
        "id": msg_counter,
        "sender": "manifest",
        "text": text,
        "status": "sent",
        "ts": datetime.now().isoformat(timespec="seconds")
    })
    # Send til pilot som plain text (for at være kompatibel med pilotens nuværende kode)
    mqtt_client.publish(TOPIC_MANIFEST_TO_PILOT, text, qos=0, retain=False)

    return {"status":"ok"}

@app.post("/api/messages/read")
def api_mark_read():
    # Markér alle pilot → manifest som “read”
    for m in messages:
        if m["sender"] == "pilot" and m["status"] != "read":
            m["status"] = "read"
    return {"status":"ok"}

@app.post("/api/quick/add")
def api_quick_add(text: str = Form(...)):
    t = (text or "").strip()
    if not t:
        return {"status":"error", "error":"empty"}
    quick_messages.append(t)
    save_quick(quick_messages)
    return {"status":"ok"}

@app.post("/api/quick/remove")
def api_quick_remove(text: str = Form(...)):
    try:
        quick_messages.remove(text)
        save_quick(quick_messages)
    except ValueError:
        pass
    return {"status":"ok"}

@app.post("/api/lift/send")
def api_lift_send(payload: str = Form(...)):
    """
    Forventer payload = JSON i formatet piloten forventer, fx:
    {
      "id": 7,
      "name": "Lift 7",
      "status": "active",
      "rows": [
        { "alt": 1000, "jumpers": 2, "overflights": 2 },
        { "alt": 1500, "jumpers": 1, "overflights": 1 },
        { "alt": 2250, "jumpers": 2, "overflights": 1 },
        { "alt": 4000, "jumpers": 10, "overflights": 1 }
      ],
      "totals": { "jumpers": 15, "canopies": 11 }
    }
    """
    try:
        obj = json.loads(payload)
        # Let sanity
        lid = int(obj["id"])
        name = str(obj.get("name", f"Lift {lid}"))
        status = obj.get("status", "active")
        rows = obj.get("rows", [])
        totals = obj.get("totals", {})

        # Send til pilot
        mqtt_client.publish(TOPIC_LIFT_OUT, json.dumps(obj, ensure_ascii=False), qos=0, retain=False)

        # Gem lokalt (til visning)
        lifts_sent[lid] = {
            "id": lid,
            "name": name,
            "status": status,
            "rows": rows,
            "totals": totals,
            "ts_iso": datetime.now().isoformat(timespec="seconds"),
        }
        return {"status":"ok", "lift": lifts_sent[lid]}
    except Exception as e:
        return JSONResponse({"status":"error", "error": str(e)}, status_code=400)

@app.on_event("startup")
def _startup():
    start_mqtt()
