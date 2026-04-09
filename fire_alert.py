import json
import logging
import requests
import math
import asyncio
import paho.mqtt.client as mqtt
from telegram import Bot

# ---------------- CONFIGURATION ---------------- #
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPICS = [
    "iot/fire/detected/alert/",
    "iot/threat/detected"
]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Mock storage for Telegram Bots (unique IDs 1, 2, 3, 4)
# You will replace these with actual bot tokens and chat IDs.
EMERGENCY_CONTACTS = {
    "1": {"type": "fire_station", "bot_token": "BOT_TOKEN_1", "chat_id": 111111111},
    "2": {"type": "fire_station", "bot_token": "BOT_TOKEN_2", "chat_id": 222222222},
    "3": {"type": "police", "bot_token": "BOT_TOKEN_3", "chat_id": 333333333},
    "4": {"type": "police", "bot_token": "BOT_TOKEN_4", "chat_id": 444444444},
}

def calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine formula to calculate distance in km."""
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2)**2 + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def find_emergency_services(lat, lon):
    """Finds nearest fire and police stations using Overpass API."""
    bbox_offset = 0.05 # approx 5km bounding box
    south, west = lat - bbox_offset, lon - bbox_offset
    north, east = lat + bbox_offset, lon + bbox_offset

    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="police"]({south},{west},{north},{east});
      way["amenity"="police"]({south},{west},{north},{east});
      node["amenity"="fire_station"]({south},{west},{north},{east});
      way["amenity"="fire_station"]({south},{west},{north},{east});
    );
    out center;
    """

    logging.info(f"Querying Overpass API for nearby fire stations & police at ({lat}, {lon})...")
    
    try:
        response = requests.post("https://lz4.overpass-api.de/api/interpreter", data={'data': query}, timeout=25)
        response.raise_for_status()
        data = response.json()
        
        fire_stations = []
        police_stations = []

        for element in data.get('elements', []):
            st_lat = element.get('lat') or element.get('center', {}).get('lat')
            st_lon = element.get('lon') or element.get('center', {}).get('lon')
            st_type = element.get('tags', {}).get('amenity', 'unknown')
            st_name = element.get('tags', {}).get('name', f'Unknown {st_type}')

            if st_lat and st_lon:
                distance = calculate_distance(lat, lon, st_lat, st_lon)
                st_info = {
                    "name": st_name,
                    "lat": st_lat,
                    "lon": st_lon,
                    "distance_km": distance
                }
                
                if "fire_station" in st_type:
                    fire_stations.append(st_info)
                elif "police" in st_type:
                    police_stations.append(st_info)

        # Sort by distance
        fire_stations.sort(key=lambda x: x['distance_km'])
        police_stations.sort(key=lambda x: x['distance_km'])

        return fire_stations[:2], police_stations[:2]

    except Exception as e:
        logging.error(f"Error querying Overpass API: {e}")
        return [], []

def send_alert(station_id, message):
    station = EMERGENCY_CONTACTS.get(station_id)
    if not station:
        logging.error(f"❌ Token ID {station_id} not found in EMERGENCY_CONTACTS.")
        return

    async def send():
        try:
            bot = Bot(token=station["bot_token"])
            await bot.send_message(chat_id=station["chat_id"], text=message)
            logging.info(f"✅ Alert successfully sent to Token ID {station_id}")
        except Exception as e:
            logging.error(f"Failed to send Telegram alert to token {station_id}: {e}")

    try:
        asyncio.run(send())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(send())


def on_connect(client, userdata, flags, reason_code, properties=None):
    print("✅ Connected to MQTT:", reason_code)
    for topic in MQTT_TOPICS:
        client.subscribe(topic)
        print("📡 Subscribed to:", topic)

def on_message(client, userdata, msg):
    print(f"\n📩 Message received: {msg.topic}")
    try:
        payload_str = msg.payload.decode('utf-8').strip()
        if payload_str.startswith('"') and payload_str.endswith('"'):
            payload_str = payload_str[1:-1]
            
        data = json.loads(payload_str)
        print("📦 Parsed Data:", data)

        # Handle Fire topic
        if msg.topic == "iot/fire/detected/alert/":
            if data.get("fire") == "abnormal" and "current_location" in data:
                loc = data["current_location"]
                fire_lat = float(loc.get("lat", 0.0))
                fire_lon = float(loc.get("long", loc.get("lon", 0.0)))
                
                if fire_lat != 0.0 and fire_lon != 0.0:
                    # ---------------- FIRE STATIONS ALERT ---------------- #
                    nearest_fires, _ = find_emergency_services(fire_lat, fire_lon)
                    
                    primary_fire = nearest_fires[0] if len(nearest_fires) > 0 else None
                    backup_fire = nearest_fires[1] if len(nearest_fires) > 1 else None
                    
                    primary_name = primary_fire['name'] if primary_fire else "Unknown Fire Station"
                    primary_dist = primary_fire['distance_km'] if primary_fire else 0.0
                    
                    backup_name = backup_fire['name'] if backup_fire else "Unknown Backup Fire Station"
                    backup_dist = backup_fire['distance_km'] if backup_fire else 0.0

                    maps_link = f"https://maps.google.com/?q={fire_lat},{fire_lon}"

                    message = f"""
🚨 FIRE ALERT 🚨

📍 Location:
Lat: {fire_lat}
Lon: {fire_lon}

🗺 Map: {maps_link}

🔥 Type: {data.get('fire')}
📊 Confidence: N/A

🚒 Primary Station: {primary_name} ({primary_dist:.2f} km)
🚑 Backup Station: {backup_name} ({backup_dist:.2f} km)
"""

                    print(f"🎯 Sending to PRIMARY FIRE: {primary_name}")
                    send_alert("1", message) # Primary Fire token

                    print(f"🛟 Sending to BACKUP FIRE: {backup_name}")
                    send_alert("2", "⚠ BACKUP ALERT\n\n" + message) # Backup Fire Token
                else:
                    print("❌ Invalid or Zero coordinates parsed from the payload.")
            else:
                print("❌ Payload ignored (fire is not abnormal or missing location data).")

        # Handle Threat topic
        elif msg.topic == "iot/threat/detected":
            if data.get("threat") == "suspicious":
                loc = data.get("current_location", data.get("location", {}))
                threat_lat = float(loc.get("lat", 0.0))
                threat_lon = float(loc.get("long", loc.get("lon", 0.0)))

                if threat_lat != 0.0 and threat_lon != 0.0:
                    # ---------------- POLICE ALERT FOR THREATS ---------------- #
                    _, nearest_polices = find_emergency_services(threat_lat, threat_lon)
                    
                    primary_police = nearest_polices[0] if len(nearest_polices) > 0 else None
                    backup_police = nearest_polices[1] if len(nearest_polices) > 1 else None
                    
                    primary_name = primary_police['name'] if primary_police else "Unknown Police Station"
                    primary_dist = primary_police['distance_km'] if primary_police else 0.0

                    backup_name = backup_police['name'] if backup_police else "Unknown Backup Police Station"
                    backup_dist = backup_police['distance_km'] if backup_police else 0.0

                    maps_link = f"https://maps.google.com/?q={threat_lat},{threat_lon}"

                    message = f"""
🚨 THREAT ALERT 🚨

📍 Location:
Lat: {threat_lat}
Lon: {threat_lon}

🗺 Map: {maps_link}

⚠️ Threat: Suspicious Activity Detected

🚓 Primary Police Station: {primary_name} ({primary_dist:.2f} km)
🚓 Backup Police Station: {backup_name} ({backup_dist:.2f} km)
"""
                    print(f"🎯 Suspicious Threat! Dispatching PRIMARY POLICE: {primary_name}")
                    send_alert("3", message) # Primary Police Token
                    
                    print(f"🎯 Dispatching BACKUP POLICE: {backup_name}")
                    send_alert("4", "⚠ BACKUP ALERT\n\n" + message) # Backup Police Token
                else:
                    print("❌ Invalid or Zero coordinates parsed from the threat payload.")
            else:
                print("❌ Threat is not 'suspicious' or missing threat type. Ignored.")

    except json.JSONDecodeError:
        print(f"❌ Malformed JSON Payload: {msg.payload}")
    except Exception as e:
        print(f"❌ Error processing message: {e}")

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="emergency_dispatch_master")
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"🚀 Connecting to {MQTT_BROKER}...")
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("Disconnecting from broker...")
        client.disconnect()
    except Exception as e:
        print(f"❌ MQTT Error: {e}")

if __name__ == "__main__":
    main()
