# mqtt_service.py
import paho.mqtt.client as mqtt
import json
import logging
import traceback
import os
import yaml

# Define base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Use absolute path for logging
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Load config to get log level
config_path = os.path.join(BASE_DIR, 'config/config.yaml')
with open(config_path, 'r') as config_file:
    config = yaml.safe_load(config_file)

# Configure logging with config log level
logger = logging.getLogger('mqtt_service')
logger.setLevel(getattr(logging, config.get('LOG_LEVEL', 'ERROR').upper()))

class MQTTService:
    def __init__(self, config):
        """Initialize MQTT service with config parameters"""
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config.get('MQTT_CLIENT_ID', 'flight_tracker'))
        self.broker_host = config['MQTT_BROKER']
        self.broker_port = config['MQTT_BROKER_PORT']
        
        # Set up logging
        self.logger = logging.getLogger('mqtt_service')
        self.logger.setLevel(getattr(logging, config.get('LOG_LEVEL', 'ERROR').upper()))
        
        # Set authentication if provided
        if 'MQTT_USER' in config and 'MQTT_PWD' in config:
            self.client.username_pw_set(config['MQTT_USER'], config['MQTT_PWD'])
        
    def connect(self):
        try:
            self.client.connect(self.broker_host, self.broker_port)
            self.client.loop_start()
        except Exception as e:
            logging.error(f"MQTT connection failed: {str(e)}\n{traceback.format_exc()}")
            raise
            
    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        
    def publish(self, topic, payload, qos=1, retain=True):
        try:
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            self.client.publish(topic, payload, qos=qos, retain=retain)
        except Exception as e:
            logging.error(f"MQTT publish failed - Topic: {topic}, Error: {str(e)}")
            raise