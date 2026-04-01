"""Tests for Home Assistant MQTT discovery."""

import json
from unittest.mock import MagicMock

from flights.discovery import create_device, create_entities, publish_discovery


def test_device_has_stable_identifiers(config):
    """Device identifiers are deterministic, not random."""
    device = create_device(config)
    info = device.get_device_info()
    assert info["identifiers"] == ["flights_test"]

    # Create again - should be identical
    device2 = create_device(config)
    info2 = device2.get_device_info()
    assert info["identifiers"] == info2["identifiers"]


def test_entities_have_stable_unique_ids(config):
    """Entity unique IDs are deterministic, not random."""
    device = create_device(config)
    entities = create_entities(config, device)

    unique_ids = [e.unique_id for e in entities]
    # Create again - should be identical
    entities2 = create_entities(config, device)
    unique_ids2 = [e.unique_id for e in entities2]
    assert unique_ids == unique_ids2


def test_entity_types(config):
    """All expected entity types are present."""
    device = create_device(config)
    entities = create_entities(config, device)

    components = {e.unique_id: e.component for e in entities}
    # Primary sensors
    assert "closest" in components
    assert components["closest"] == "sensor"
    assert "visible" in components
    assert components["visible"] == "sensor"
    # Diagnostic sensors
    assert "status" in components
    assert components["status"] == "sensor"
    assert "last_update" in components
    assert "web_server" in components
    assert components["web_server"] == "binary_sensor"
    # Buttons
    assert "refresh" in components
    assert components["refresh"] == "button"


def test_closest_sensor_properties(config):
    """Closest sensor has correct unit and icon."""
    device = create_device(config)
    entities = create_entities(config, device)
    closest = next(e for e in entities if e.unique_id == "closest")
    payload = closest.get_config_payload()

    assert payload["unit_of_measurement"] == "mi"
    assert payload["icon"] == "mdi:airplane"
    assert payload["state_topic"] == "test/flights/closest"


def test_visible_sensor_properties(config):
    """Visible sensor has correct unit and icon."""
    device = create_device(config)
    entities = create_entities(config, device)
    visible = next(e for e in entities if e.unique_id == "visible")
    payload = visible.get_config_payload()

    assert payload["unit_of_measurement"] == "planes"
    assert payload["icon"] == "mdi:radar"


def test_web_server_is_binary_sensor(config):
    """Web server entity is a binary_sensor with connectivity device_class."""
    device = create_device(config)
    entities = create_entities(config, device)
    ws = next(e for e in entities if e.unique_id == "web_server")

    assert ws.component == "binary_sensor"
    payload = ws.get_config_payload()
    assert payload["device_class"] == "connectivity"
    assert payload["entity_category"] == "diagnostic"


def test_publish_discovery_builds_bundle(config):
    """publish_discovery publishes a device-bundle with abbreviated keys."""
    mock_pub = MagicMock()
    mock_pub.publish.return_value = True

    result = publish_discovery(config, mock_pub)
    assert result is True
    assert mock_pub.publish.called

    call_kwargs = mock_pub.publish.call_args
    topic = call_kwargs.kwargs.get("topic") or call_kwargs[1].get("topic")
    payload_str = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
    payload = json.loads(payload_str)

    assert topic == "homeassistant/device/flights_test/config"
    # Abbreviated device keys
    assert "ids" in payload["dev"]
    assert "mf" in payload["dev"]
    assert "mdl" in payload["dev"]
    assert "sw" in payload["dev"]
    # Full keys should NOT be present
    assert "identifiers" not in payload["dev"]
    assert "manufacturer" not in payload["dev"]
    # Components
    assert "cmps" in payload
    assert "closest" in payload["cmps"]
    assert "visible" in payload["cmps"]
    assert "status" in payload["cmps"]
    assert "web_server" in payload["cmps"]
    assert "refresh" in payload["cmps"]
    # Availability
    assert "availability" in payload
    assert payload["payload_available"] == "online"
