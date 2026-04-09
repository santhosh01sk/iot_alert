import json
import math
import asyncio
import paho.mqtt.client as mqtt
from telegram import Bot

# ---------------- MQTT CONFIG ---------------- #

MQTT_BROKER = "broker.hivemq.com"

TOPICS = [
    ("iot/fire/detected", 0)
]

# ---------------- FIRE STATIONS ---------------- #



# ---------------- DISTANCE FUNCTION ---------------- #

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius (km)

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(d_lon / 2) ** 2)

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ---------------- FIND PRIMARY + BACKUP ---------------- #

def find_nearest_and_backup(fire_lat, fire_lon):
    distances = []

    for name, station in fire_stations.items():
        dist = calculate_distance(
            fire_lat, fire_lon,
            station["lat"], station["lon"]
        )
        distances.append((name, dist))

    # Sort by distance
    distances.sort(key=lambda x: x[1])

    primary = distances[0]
    backup = distances[1]

    return primary, backup


# ---------------- TELEGRAM ALERT ---------------- #

def send_alert(station_name, message):
    station = fire_stations[station_name]

    async def send():
        bot = Bot(token=station["bot_token"])
        await bot.send_message(chat_id=station["chat_id"], text=message)

    try:
        asyncio.run(send())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(send())


# ---------------- MQTT CALLBACKS ---------------- #

def on_connect(client, userdata, flags, reason_code, properties=None):
    print("✅ Connected to MQTT:", reason_code)

    for topic in TOPICS:
        client.subscribe(topic)
        print("📡 Subscribed to:", topic[0])


def on_message(client, userdata, msg):
    print(f"\n📩 Message received: {msg.topic}")

    try:
        payload = msg.payload.decode().strip()

        # Fix ESP32 formatting issue
        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]

        data = json.loads(payload)
        print("📦 Parsed Data:", data)

        # 🔥 Simulated fire location (replace with real GPS later)
        fire_lat = 13.0850
        fire_lon = 80.2750

        # Find nearest + backup
        primary, backup = find_nearest_and_backup(fire_lat, fire_lon)

        primary_name, primary_dist = primary
        backup_name, backup_dist = backup

        # Google Maps link
        maps_link = f"https://maps.google.com/?q={fire_lat},{fire_lon}"

        # Alert message
        message = f"""
🚨 FIRE ALERT 🚨

📍 Location:
Lat: {fire_lat}
Lon: {fire_lon}

🗺 Map: {maps_link}

🔥 Type: {data.get('fire_type')}
📊 Confidence: {data.get('confidence')}

🚒 Primary Station: {primary_name} ({primary_dist:.2f} km)
🚑 Backup Station: {backup_name} ({backup_dist:.2f} km)
"""

        print(f"🎯 Sending to PRIMARY: {primary_name}")
        send_alert(primary_name, message)

        print(f"🛟 Sending to BACKUP: {backup_name}")
        send_alert(backup_name, "⚠ BACKUP ALERT\n\n" + message)

        print("✅ Alerts sent successfully")

    except Exception as e:
        print("❌ Error:", e)


# ---------------- MQTT CLIENT ---------------- #

client = mqtt.Client(
    client_id="smart_fire_dispatch_system"
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, 1883)

print("🚀 Smart Fire Dispatch System Running...")
client.loop_forever()