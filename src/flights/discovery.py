"""Home Assistant MQTT discovery with stable device identifiers."""

import logging

from ha_mqtt_publisher import Device
from ha_mqtt_publisher.ha_discovery import Sensor, publish_device_bundle

from flights import __version__
from flights.config import FlightsConfig

logger = logging.getLogger(__name__)


def create_device(config: FlightsConfig) -> Device:
    """Create an HA device with stable identifiers."""
    prefix = config.get("app.unique_id_prefix", "flights")
    return Device(
        config.data,
        identifiers=[prefix],
        name=config.get("app.name", "Flights"),
        manufacturer=config.get("app.manufacturer", "ronschaeffer"),
        model=config.get("app.model", "Flights"),
        sw_version=__version__,
        configuration_url=config.get("web_server.external_url", ""),
    )


def create_entities(config: FlightsConfig, device: Device) -> tuple[Sensor, Sensor]:
    """Create the HA sensor entities with stable unique IDs."""
    prefix = config.get("app.unique_id_prefix", "flights")
    distance_unit = config.get("location.distance_unit", "mi")
    closest_topic = config.get("mqtt.topics.closest", "flights/closest")
    visible_topic = config.get("mqtt.topics.visible", "flights/visible")

    closest_sensor = Sensor(
        config.data,
        device,
        name="Closest Aircraft",
        unique_id=f"{prefix}_closest",
        state_topic=closest_topic,
        unit_of_measurement=distance_unit,
        icon="mdi:airplane",
        value_template=(
            "{% set first_key = value_json.keys() | list | first %}"
            "{{ value_json.get(first_key, {}).get("
            "'distance_value', 0) | float }}"
        ),
        json_attributes_topic=closest_topic,
        json_attributes_template=(
            "{% set first_key = value_json.keys() | list | first %}"
            "{{ value_json.get(first_key, {}) | tojson }}"
        ),
    )

    visible_sensor = Sensor(
        config.data,
        device,
        name="Visible Aircraft",
        unique_id=f"{prefix}_visible",
        state_topic=visible_topic,
        unit_of_measurement="planes",
        icon="mdi:radar",
        value_template="{{ value_json.get('visible_aircraft', 0) }}",
        json_attributes_topic=visible_topic,
        json_attributes_template="{{ value_json | tojson }}",
    )

    return closest_sensor, visible_sensor


def publish_discovery(config: FlightsConfig, publisher) -> bool:
    """Publish HA discovery payload with stable identifiers."""
    if not config.get("home_assistant.enabled", True):
        logger.info("Home Assistant discovery disabled")
        return False

    device = create_device(config)
    closest, visible = create_entities(config, device)
    prefix = config.get("app.unique_id_prefix", "flights")

    try:
        publish_device_bundle(
            config=config.data,
            publisher=publisher,
            device=device,
            entities=[closest, visible],
            device_id=prefix,
            retain=True,
        )
        logger.info("Published HA discovery payload")
        return True
    except Exception:
        logger.exception("Failed to publish HA discovery payload")
        return False
