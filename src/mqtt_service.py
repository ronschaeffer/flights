# mqtt_service.py
import paho.mqtt.client as mqtt
import json

class MQTTService:
    def __init__(self, config):
        """Initialize MQTT service with config parameters"""
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config.get('MQTT_CLIENT_ID', 'flight_tracker'))
        self.broker_host = config['MQTT_BROKER']
        self.broker_port = config['MQTT_BROKER_PORT']
        
        # Set authentication if provided
        if 'MQTT_USER' in config and 'MQTT_PWD' in config:
            self.client.username_pw_set(config['MQTT_USER'], config['MQTT_PWD'])
        
    def connect(self):
        try:
            self.client.connect(self.broker_host, self.broker_port)
            self.client.loop_start()
        except Exception:
            raise
            
    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        
    def publish(self, topic, payload, qos=1, retain=True):
        try:
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            self.client.publish(topic, payload, qos=qos, retain=retain)
        except Exception:
            pass