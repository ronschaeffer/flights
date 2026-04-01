"""Home Assistant MQTT discovery using device-bundle payload.

Publishes a single retained message to homeassistant/device/<id>/config
containing the device info, origin, all component configs, and availability.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ha_mqtt_publisher import Device, Entity

from flights import __version__
from flights.config import FlightsConfig

logger = logging.getLogger(__name__)


def create_device(config: FlightsConfig) -> Device:
    """Create an HA device with stable identifiers."""
    prefix = config.get("app.unique_id_prefix", "flights")
    return Device(
        config,
        identifiers=[prefix],
        name=config.get("app.name", "Flights"),
        manufacturer=config.get("app.manufacturer", "ronschaeffer"),
        model=config.get("app.model", "Flights"),
        sw_version=__version__,
        configuration_url=config.get("web_server.external_url", ""),
    )


def create_entities(config: FlightsConfig, device: Device) -> list[Entity]:
    """Create all HA entities for the Flights device."""
    prefix = config.get("app.unique_id_prefix", "flights")
    distance_unit = config.get("location.distance_unit", "mi")
    closest_topic = config.get("mqtt.topics.closest", "flights/closest")
    visible_topic = config.get("mqtt.topics.visible", "flights/visible")
    status_topic = config.get("mqtt.topics.status", "flights/status")
    cmd_topic_base = f"{prefix}/cmd"

    entities: list[Entity] = [
        # --- Primary sensors ---
        Entity(
            config,
            device,
            component="sensor",
            unique_id="closest",
            name="Closest Aircraft",
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
        ),
        Entity(
            config,
            device,
            component="sensor",
            unique_id="visible",
            name="Visible Aircraft",
            state_topic=visible_topic,
            unit_of_measurement="planes",
            icon="mdi:radar",
            value_template="{{ value_json.get('visible_aircraft', 0) }}",
            json_attributes_topic=visible_topic,
            json_attributes_template="{{ value_json | tojson }}",
        ),
        # --- Diagnostic sensors ---
        Entity(
            config,
            device,
            component="sensor",
            unique_id="status",
            name="Status",
            state_topic=status_topic,
            value_template="{{ value_json.status }}",
            json_attributes_topic=status_topic,
            icon="mdi:information",
            entity_category="diagnostic",
        ),
        Entity(
            config,
            device,
            component="sensor",
            unique_id="last_update",
            name="Last Update",
            state_topic=status_topic,
            value_template="{{ value_json.last_update }}",
            device_class="timestamp",
            entity_category="diagnostic",
        ),
        # --- Control buttons ---
        Entity(
            config,
            device,
            component="button",
            unique_id="refresh",
            name="Refresh",
            command_topic=f"{cmd_topic_base}/refresh",
            icon="mdi:refresh",
        ),
        Entity(
            config,
            device,
            component="button",
            unique_id="clear_cache",
            name="Clear Cache",
            command_topic=f"{cmd_topic_base}/clear_cache",
            icon="mdi:delete-sweep",
        ),
        Entity(
            config,
            device,
            component="button",
            unique_id="restart",
            name="Restart",
            command_topic=f"{cmd_topic_base}/restart",
            icon="mdi:restart",
        ),
    ]

    # Optional: Web server health sensor
    if config.get("web_server.enabled", True):
        entities.append(
            Entity(
                config.data,
                device,
                component="binary_sensor",
                unique_id="web_server",
                name="Web Server",
                state_topic=status_topic,
                value_template="{{ value_json.web_server_status }}",
                payload_on="online",
                payload_off="offline",
                device_class="connectivity",
                entity_category="diagnostic",
            )
        )

    # Optional: Receiver health sensor
    if config.get("receiver.health_check", True):
        entities.append(
            Entity(
                config.data,
                device,
                component="binary_sensor",
                unique_id="receiver",
                name="ADS-B Receiver",
                state_topic=status_topic,
                value_template="{{ value_json.receiver_status }}",
                payload_on="online",
                payload_off="offline",
                device_class="connectivity",
                entity_category="diagnostic",
            )
        )

    return entities


def publish_discovery(config: FlightsConfig, publisher: Any) -> bool:
    """Publish device-bundle discovery."""
    if not config.get("home_assistant.enabled", True):
        logger.info("Home Assistant discovery disabled")
        return False

    device = create_device(config)
    entities = create_entities(config, device)
    prefix = config.get("app.unique_id_prefix", "flights")
    availability_topic = config.get("mqtt.topics.availability", "flights/availability")
    discovery_prefix = config.get("home_assistant.discovery_prefix", "homeassistant")

    # Abbreviated device keys (HA requires these in device bundles)
    dev: dict[str, Any] = {
        "ids": prefix,
        "name": device.name,
    }
    if getattr(device, "manufacturer", None):
        dev["mf"] = device.manufacturer
    if getattr(device, "model", None):
        dev["mdl"] = device.model
    if getattr(device, "sw_version", None):
        dev["sw"] = device.sw_version
    cu = getattr(device, "configuration_url", None)
    if cu:
        dev["cu"] = cu

    # Build compact component payloads
    cmps: dict[str, dict] = {}
    for entity in entities:
        comp = entity.get_config_payload().copy()
        comp.pop("device", None)
        comp["p"] = entity.component
        cmps[entity.unique_id] = comp

    payload = {
        "dev": dev,
        "o": {
            "name": config.get("app.name", "Flights"),
            "sw": __version__,
            "url": "https://github.com/ronschaeffer/flights",
        },
        "cmps": cmps,
        "availability": [{"topic": availability_topic}],
        "payload_available": "online",
        "payload_not_available": "offline",
    }

    topic = f"{discovery_prefix}/device/{prefix}/config"

    try:
        publisher.publish(topic=topic, payload=json.dumps(payload), retain=True)
        logger.info("Published HA discovery bundle to %s", topic)
        return True
    except Exception:
        logger.exception("Failed to publish HA discovery")
        return False
