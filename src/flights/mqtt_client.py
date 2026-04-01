"""MQTT client using ha_mqtt_publisher for Home Assistant integration."""

import logging

from ha_mqtt_publisher import AvailabilityPublisher, MQTTPublisher
from ha_mqtt_publisher.config import MQTTConfig

from flights.config import FlightsConfig

logger = logging.getLogger(__name__)


def create_publisher(config: FlightsConfig) -> MQTTPublisher:
    """Create and return an MQTTPublisher from config."""
    availability_topic = config.get("mqtt.topics.availability", "flights/availability")

    mqtt_cfg = MQTTConfig.from_dict(config.data)
    kwargs = MQTTConfig.to_publisher_kwargs(mqtt_cfg)

    # Add LWT for availability
    kwargs["last_will"] = {
        "topic": availability_topic,
        "payload": "offline",
        "qos": 1,
        "retain": True,
    }
    kwargs["default_qos"] = 1
    kwargs["default_retain"] = True

    publisher = MQTTPublisher(**kwargs)
    return publisher


def create_availability(
    publisher: MQTTPublisher, config: FlightsConfig
) -> AvailabilityPublisher:
    """Create an AvailabilityPublisher."""
    topic = config.get("mqtt.topics.availability", "flights/availability")
    return AvailabilityPublisher(
        mqtt_client=publisher,
        topic=topic,
        qos=1,
    )
