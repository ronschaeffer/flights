# mqtt_service.py
import paho.mqtt.client as mqtt
import json
import logging

logger = logging.getLogger(__name__)

class MQTTService:
    def __init__(self, config):
        """Initialize MQTT service with config parameters"""
        self.client = mqtt.Client(client_id=config.get('MQTT_CLIENT_ID', 'flight_tracker'))
        self.broker_host = config['MQTT_BROKER']
        self.broker_port = config['MQTT_BROKER_PORT']
        
        # Set authentication if provided
        if 'MQTT_USER' in config and 'MQTT_PWD' in config:
            self.client.username_pw_set(config['MQTT_USER'], config['MQTT_PWD'])
        
    def connect(self):
        try:
            logger.info(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}")
            self.client.connect(self.broker_host, self.broker_port)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise
            
    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        
    def publish(self, topic, payload, qos=1, retain=True):
        try:
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            self.client.publish(topic, payload, qos=qos, retain=retain)
            logger.debug(f"Published to {topic}")
        except Exception as e:
            logger.error(f"Publish failed: {e}")