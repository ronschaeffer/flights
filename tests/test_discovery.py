"""Tests for Home Assistant MQTT discovery."""

from flights.discovery import create_device, create_entities


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
    closest, visible = create_entities(config, device)

    closest_payload = closest.get_config_payload()
    visible_payload = visible.get_config_payload()

    assert "flights_test_closest" in closest_payload["unique_id"]
    assert "flights_test_visible" in visible_payload["unique_id"]

    # Create again - should be identical (deterministic, not random)
    closest2, visible2 = create_entities(config, device)
    assert closest2.get_config_payload()["unique_id"] == closest_payload["unique_id"]
    assert visible2.get_config_payload()["unique_id"] == visible_payload["unique_id"]


def test_entity_topics(config):
    """Entities use configured MQTT topics."""
    device = create_device(config)
    closest, visible = create_entities(config, device)

    closest_payload = closest.get_config_payload()
    visible_payload = visible.get_config_payload()

    assert closest_payload["state_topic"] == "test/flights/closest"
    assert visible_payload["state_topic"] == "test/flights/visible"


def test_closest_sensor_properties(config):
    """Closest sensor has correct unit and icon."""
    device = create_device(config)
    closest, _ = create_entities(config, device)
    payload = closest.get_config_payload()

    assert payload["unit_of_measurement"] == "mi"
    assert payload["icon"] == "mdi:airplane"


def test_visible_sensor_properties(config):
    """Visible sensor has correct unit and icon."""
    device = create_device(config)
    _, visible = create_entities(config, device)
    payload = visible.get_config_payload()

    assert payload["unit_of_measurement"] == "planes"
    assert payload["icon"] == "mdi:radar"
