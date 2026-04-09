import json
from datetime import datetime

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
import google.cloud.firestore as firestore

# ---------------- CONFIG ---------------- #

MQTT_BROKER = "broker.hivemq.com"

TOPICS = [
    ("iot/fire/detected", 0),
    ("iot/sensors/environment", 0),
    ("iot/threat/detected", 0)
]

# Initialize Firestore
db = firestore.Client.from_service_account_json("./iot-threat-demo-firebase-adminsdk-fbsvc-4d3bd459d3.json")

# ---------------- FIRESTORE LOGGING ---------------- #

def log_fire(data):
    db.collection("fire_logs").add({
        "fire_type": str(data.get("fire_type")),
        "confidence": float(data.get("confidence", 0.0)),
        "timestamp": data.get("timestamp") or datetime.utcnow(),
        "logged_at": datetime.utcnow()
    })


def log_sensor(data):
    db.collection("sensor_logs").add({
        "smoke": float(data.get("smoke", 0.0)),
        "flame": float(data.get("flame", 0.0)),
        "motion": float(data.get("motion", 0.0)),
        "logged_at": datetime.utcnow()
    })


def log_threat(data):
    db.collection("threat_logs").add({
        "video": str(data.get("video")),
        "frame": float(data.get("frame", 0.0)),
        "threat": str(data.get("threat")),
        "weapon": bool(data.get("weapon")),
        "masked_people": float(data.get("masked_people", 0.0)),
        "hand_near_neck": bool(data.get("hand_near_neck")),
        "aggressive_emotion": bool(data.get("aggressive_emotion")),
        "logged_at": datetime.utcnow()
    })


# ---------------- MQTT CALLBACKS ---------------- #

def on_connect(client, userdata, flags, reason_code, properties):
    print("✅ Connected to MQTT:", reason_code)

    for topic in TOPICS:
        client.subscribe(topic)
        print("📡 Subscribed to:", topic[0])


def on_message(client, userdata, msg):
    print(f"\n📩 Message received: {msg.topic}")

    try:
        payload = msg.payload.decode().strip()

        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]

        data = json.loads(payload)
        print("📦 Parsed Data:", data)

        # 🔁 Route to correct collection
        if msg.topic == "iot/fire/detected":
            log_fire(data)

        elif msg.topic == "iot/sensors/environment":
            log_sensor(data)

        elif msg.topic == "iot/threat/detected":
            log_threat(data)

        print("🔥 Successfully logged to Firestore")

    except Exception as e:
        print("❌ Error processing message:", e)


# ---------------- MQTT CLIENT SETUP ---------------- #

client = mqtt.Client(
    client_id="firestore_logger_node",
    callback_api_version=CallbackAPIVersion.VERSION2
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, 1883)

print("🚀 Listening for MQTT messages...")
client.loop_forever()