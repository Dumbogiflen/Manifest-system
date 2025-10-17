# mqtt_handler.py
import os, json, threading
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "b984550852ed4879b205fb8f7745202a.s1.eu.hivemq.cloud")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USER = os.getenv("MQTT_USER", "Pilatus")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# Topics (aftalt med pilot)
TOPIC_OUT_MSG   = "pilatus/manifest/messages"   # manifest -> pilot (text)
TOPIC_OUT_ACK   = "pilatus/manifest/acks"       # manifest -> pilot (ack for modtagelse/læsning)
TOPIC_LIFT      = "pilatus/lift"                # manifest -> pilot (lift json)

TOPIC_IN_MSG    = "pilatus/pilot/messages"      # pilot -> manifest (text)
TOPIC_IN_ACK    = "pilatus/pilot/acks"          # pilot -> manifest (acks for vores beskeder)
TOPIC_LIFT_STAT = "pilatus/lift_status"         # pilot -> manifest ({"id":x,"status":"completed"})

class MqttBus:
    def __init__(self):
        self.client = mqtt.Client(protocol=mqtt.MQTTv311)
        self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.client.tls_set()
        self.on_pilot_message = None     # callback(text:str)
        self.on_pilot_ack = None         # callback(payload:dict)
        self.on_lift_status = None       # callback(payload:dict)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, c, u, f, rc):
        print("✅ MQTT connected" if rc == 0 else f"❌ MQTT rc={rc}")
        if rc == 0:
            c.subscribe(TOPIC_IN_MSG)
            c.subscribe(TOPIC_IN_ACK)
            c.subscribe(TOPIC_LIFT_STAT)

    def _on_message(self, c, u, msg):
        try:
            if msg.topic == TOPIC_IN_MSG:
                text = msg.payload.decode(errors="ignore")
                if self.on_pilot_message:
                    self.on_pilot_message(text)

            elif msg.topic == TOPIC_IN_ACK:
                payload = json.loads(msg.payload.decode(errors="ignore") or "{}")
                if self.on_pilot_ack:
                    self.on_pilot_ack(payload)

            elif msg.topic == TOPIC_LIFT_STAT:
                payload = json.loads(msg.payload.decode(errors="ignore") or "{}")
                if self.on_lift_status:
                    self.on_lift_status(payload)
        except Exception as e:
            print("MQTT on_message error:", e)

    def publish_text_to_pilot(self, text: str):
        self.client.publish(TOPIC_OUT_MSG, text, qos=1)

    def publish_ack_to_pilot(self, payload: dict):
        # fx {"for_id":123,"status":"delivered"|"read"}
        self.client.publish(TOPIC_OUT_ACK, json.dumps(payload), qos=1)

    def publish_lift(self, lift: dict):
        self.client.publish(TOPIC_LIFT, json.dumps(lift), qos=1)

    def start(self):
        def run():
            self.client.connect(MQTT_HOST, MQTT_PORT, 60)
            self.client.loop_forever()
        t = threading.Thread(target=run, daemon=True)
        t.start()
