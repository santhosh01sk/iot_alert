import json
import logging
import requests
import math
import asyncio
from datetime import datetime
import paho.mqtt.client as mqtt
from telegram import Bot
import sys
import io

# Force UTF-8 for Windows console emoji support
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)


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

def log_incident_to_file(incident_type, lat, lon, fire_stations, police_stations):
    """Logs the incident details to a persistent text file."""
    log_filename = "emergency_incidents.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(log_filename, "a", encoding="utf-8") as f:
        f.write(f"\n=== [{timestamp}] Incident Report ===\n")
        f.write(f"Type: {incident_type}\n")
        f.write(f"Location: Lat = {lat}, Lon = {lon}\n")
        
        f.write("\n--- Nearest Fire Stations ---\n")
        for idx, s in enumerate(fire_stations):
            rank = "Primary" if idx == 0 else "Backup"
            f.write(f"{rank}: {s['name']} ({s['distance_km']:.2f} km)\n")
        if not fire_stations: f.write("None found nearby\n")

        f.write("\n--- Nearest Police Stations ---\n")
        for idx, s in enumerate(police_stations):
            rank = "Primary" if idx == 0 else "Backup"
            f.write(f"{rank}: {s['name']} ({s['distance_km']:.2f} km)\n")
        if not police_stations: f.write("None found nearby\n")
        
        f.write("===================================\n")
    
    print(f"📖 Incident logged to {log_filename}")

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
                    # ---------------- EMERGENCY SERVICES FETCH ---------------- #
                    nearest_fires, nearest_polices = find_emergency_services(fire_lat, fire_lon)
                    
                    p_fire = nearest_fires[0] if len(nearest_fires) > 0 else None
                    b_fire = nearest_fires[1] if len(nearest_fires) > 1 else None
                    p_police = nearest_polices[0] if len(nearest_polices) > 0 else None
                    b_police = nearest_polices[1] if len(nearest_polices) > 1 else None
                    
                    pf_name = p_fire['name'] if p_fire else "Unknown"
                    pf_dist = p_fire['distance_km'] if p_fire else 0.0
                    bf_name = b_fire['name'] if b_fire else "Unknown"
                    bf_dist = b_fire['distance_km'] if b_fire else 0.0
                    
                    pp_name = p_police['name'] if p_police else "Unknown"
                    pp_dist = p_police['distance_km'] if p_police else 0.0
                    bp_name = b_police['name'] if b_police else "Unknown"
                    bp_dist = b_police['distance_km'] if b_police else 0.0

                    maps_link = f"https://maps.google.com/?q={fire_lat},{fire_lon}"

                    message = f"""
🚨 EMERGENCY ALERT: FIRE 🚨

📍 Location:
Lat: {fire_lat}
Lon: {fire_lon}

🗺 Map: {maps_link}

🔥 Type: {data.get('fire')}
📊 Confidence: N/A

🚒 Primary Fire Station: {pf_name} ({pf_dist:.2f} km)
🚒 Backup Fire Station: {bf_name} ({bf_dist:.2f} km)
🚓 Primary Police Station: {pp_name} ({pp_dist:.2f} km)
🚓 Backup Police Station: {bp_name} ({bp_dist:.2f} km)
"""

                    print(f"🎯 Dispatching Fire & Police Alerts...")
                    for tid in ["1", "2", "3", "4"]:
                        send_alert(tid, message)
                    
                    # Log to file
                    log_incident_to_file("FIRE", fire_lat, fire_lon, nearest_fires, nearest_polices)
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
                    # ---------------- EMERGENCY SERVICES FETCH ---------------- #
                    nearest_fires, nearest_polices = find_emergency_services(threat_lat, threat_lon)
                    
                    p_fire = nearest_fires[0] if len(nearest_fires) > 0 else None
                    b_fire = nearest_fires[1] if len(nearest_fires) > 1 else None
                    p_police = nearest_polices[0] if len(nearest_polices) > 0 else None
                    b_police = nearest_polices[1] if len(nearest_polices) > 1 else None
                    
                    pf_name = p_fire['name'] if p_fire else "Unknown"
                    pf_dist = p_fire['distance_km'] if p_fire else 0.0
                    bf_name = b_fire['name'] if b_fire else "Unknown"
                    bf_dist = b_fire['distance_km'] if b_fire else 0.0
                    
                    pp_name = p_police['name'] if p_police else "Unknown"
                    pp_dist = p_police['distance_km'] if p_police else 0.0
                    bp_name = b_police['name'] if b_police else "Unknown"
                    bp_dist = b_police['distance_km'] if b_police else 0.0

                    maps_link = f"https://maps.google.com/?q={threat_lat},{threat_lon}"

                    message = f"""
🚨 EMERGENCY ALERT: THREAT 🚨

📍 Location:
Lat: {threat_lat}
Lon: {threat_lon}

🗺 Map: {maps_link}

⚠️ Threat: Suspicious Activity Detected

🚓 Primary Police Station: {pp_name} ({pp_dist:.2f} km)
🚓 Backup Police Station: {bp_name} ({bp_dist:.2f} km)
🚒 Primary Fire Station: {pf_name} ({pf_dist:.2f} km)
🚒 Backup Fire Station: {bf_name} ({bf_dist:.2f} km)
"""
                    print(f"🎯 Dispatching Threat & Police Alerts...")
                    for tid in ["1", "2", "3", "4"]:
                        send_alert(tid, message)
                    
                    # Log to file
                    log_incident_to_file("THREAT", threat_lat, threat_lon, nearest_fires, nearest_polices)
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
