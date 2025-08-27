import json
import logging
import os
import traceback

import paho.mqtt.client as mqtt

from config_manager import BASE_DIR

LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


class MQTTService:
    def __init__(self, cfg):
        """Initialize MQTT service with config parameters."""
        self.logger = logging.getLogger("mqtt_service")
        self.logger.setLevel(
            getattr(logging, (cfg.get("log_level") or "ERROR").upper())
        )

        client_id = str(
            cfg.get("mqtt_client_id") or cfg.get("MQTT_CLIENT_ID") or "flight_tracker"
        )
        # Use default protocol and transport; CallbackAPIVersion not required for basic usage
        self.client = mqtt.Client(client_id=client_id)

        self.broker_host = str(cfg.get("mqtt_broker") or cfg.get("MQTT_BROKER"))
        self.broker_port = int(
            cfg.get("mqtt_broker_port") or cfg.get("MQTT_BROKER_PORT") or 1883
        )

        self.topics = [
            str(
                cfg.get("mqtt_topic_visible")
                or cfg.get("MQTT_TOPIC_VISIBLE")
                or "dev/flights/visible"
            ),
            str(
                cfg.get("mqtt_topic_closest_aircraft")
                or cfg.get("MQTT_TOPIC_CLOSEST_AIRCRAFT")
                or "dev/flights/closest"
            ),
        ]

        username = cfg.get("mqtt_user") or cfg.get("MQTT_USER")
        password = cfg.get("mqtt_pwd") or cfg.get("MQTT_PWD")
        if username and password:
            self.client.username_pw_set(str(username), str(password))

    def connect(self):
        try:
            self.client.connect(self.broker_host, self.broker_port)
            print(f"\nConnected to MQTT broker: {self.broker_host}:{self.broker_port}")
            _cid = self.client._client_id
            client_id_display = _cid.decode() if isinstance(_cid, bytes) else _cid
            print(f"MQTT client id: {client_id_display}")
            print("Topics:")
            for topic in self.topics:
                print(f"  {topic}")
            self.client.loop_start()
        except Exception as e:
            logging.error(f"MQTT connection failed: {e}\n{traceback.format_exc()}")
            raise

    def disconnect(self):
        try:
            self.client.loop_stop()
        finally:
            self.client.disconnect()

    def publish(self, topic: str, payload, qos: int = 1, retain: bool = True):
        try:
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            self.client.publish(topic, payload, qos=qos, retain=retain)
        except Exception as e:
            logging.error(f"MQTT publish failed - Topic: {topic}, Error: {e}")
            raise
