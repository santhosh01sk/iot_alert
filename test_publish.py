import paho.mqtt.client as mqtt
import json
import time

broker = "broker.hivemq.com"
port = 1883

def publish_alerts():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_publisher_12345")
    client.connect(broker, port)
    
    # Send Fire Alert
    fire_payload = {
        "fire": "abnormal",
        "current_location": {
            "name": "Test Fire Area",
            "lat": 13.010602,
            "long": 80.23453
        }
    }
    client.publish("iot/fire/detected/alert/", json.dumps(fire_payload))
    print("Published Fire Alert")
    
    time.sleep(1)
    
    # Send Threat Alert
    threat_payload = {
        "threat": "suspicious",
        "location": {
            "name": "Test Threat Area",
            "lat": 13.010602,
            "long": 80.23453
        }
    }
    client.publish("iot/threat/detected", json.dumps(threat_payload))
    print("Published Threat Alert")
    
    client.disconnect()

if __name__ == "__main__":
    publish_alerts()
