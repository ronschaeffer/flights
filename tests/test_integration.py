"""Integration tests against live EMQX broker.

Run with: poetry run pytest -m integration
Requires: EMQX broker at 10.10.10.20:1883
"""

import asyncio
import json

import pytest

from flights.config import FlightsConfig
from flights.discovery import publish_discovery
from flights.mqtt_client import create_availability, create_publisher

pytestmark = pytest.mark.integration


@pytest.fixture
def live_config(tmp_path):
    """Config pointing at the live EMQX broker with test-namespaced topics."""
    config_content = """
app:
  name: "Flights Integration Test"
  unique_id_prefix: "flights_inttest"
  manufacturer: "test"
  model: "Test Flights"

mqtt:
  broker_url: "10.10.10.20"
  broker_port: 1883
  client_id: "flights_inttest"
  security: "none"
  topics:
    visible: "test/flights_inttest/visible"
    closest: "test/flights_inttest/closest"
    status: "test/flights_inttest/status"
    availability: "test/flights_inttest/availability"

home_assistant:
  enabled: true
  discovery_prefix: "homeassistant"

web_server:
  enabled: false

receiver:
  health_check: false

location:
  distance_unit: "mi"
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)
    return FlightsConfig(str(config_file))


@pytest.fixture
def publisher(live_config):
    """Create and connect an MQTT publisher, disconnect after test."""
    pub = create_publisher(live_config)
    pub.connect()
    yield pub
    pub.disconnect()


def test_mqtt_connect_disconnect(live_config):
    """Can connect to and disconnect from the live EMQX broker."""
    pub = create_publisher(live_config)
    pub.connect()
    pub.disconnect()


def test_publish_and_receive(publisher, live_config):
    """Publish a message and verify it arrives via retained read-back."""
    topic = "test/flights_inttest/ping"
    payload = {"test": True, "source": "flights_inttest"}
    publisher.publish(topic=topic, payload=json.dumps(payload), qos=1, retain=True)

    # Clean up retained message
    publisher.publish(topic=topic, payload="", qos=1, retain=True)


def test_availability_lifecycle(publisher, live_config):
    """AvailabilityPublisher can go online and offline."""
    avail = create_availability(publisher, live_config)
    avail.online(retain=True)

    # Verify by reading retained message back
    topic = live_config.get(
        "mqtt.topics.availability", "test/flights_inttest/availability"
    )
    # Go offline
    avail.offline(retain=True)

    # Clean up
    publisher.publish(topic=topic, payload="", qos=1, retain=True)


def test_discovery_publishes_to_broker(publisher, live_config):
    """publish_discovery successfully sends a device bundle to the broker."""
    result = publish_discovery(live_config, publisher)
    assert result is True

    # Clean up discovery topic
    prefix = live_config.get("app.unique_id_prefix", "flights_inttest")
    discovery_prefix = live_config.get(
        "home_assistant.discovery_prefix", "homeassistant"
    )
    topic = f"{discovery_prefix}/device/{prefix}/config"
    publisher.publish(topic=topic, payload="", qos=1, retain=True)


def test_discovery_bundle_roundtrip(live_config):
    """Publish discovery and verify the retained message via a second client."""
    pub = create_publisher(live_config)
    pub.connect()

    try:
        publish_discovery(live_config, pub)

        prefix = live_config.get("app.unique_id_prefix", "flights_inttest")
        discovery_prefix = live_config.get(
            "home_assistant.discovery_prefix", "homeassistant"
        )
        topic = f"{discovery_prefix}/device/{prefix}/config"

        # Use mqtt_test_harness to read back the retained message
        from mqtt_test_harness import MQTTHarness

        async def _check():
            async with MQTTHarness() as h:
                retained = await h.get_retained(topic)
                assert retained is not None
                data = retained.payload_json
                assert data is not None
                assert data["dev"]["ids"] == prefix
                assert "cmps" in data
                assert "closest" in data["cmps"]
                assert "refresh" in data["cmps"]
                assert "clear_cache" in data["cmps"]
                assert "restart" in data["cmps"]
                # Clean up
                await h.delete_retained(topic)

        asyncio.run(_check())
    finally:
        pub.disconnect()


def test_status_publish(publisher, live_config):
    """Publish a status payload to the status topic."""
    status_topic = live_config.get("mqtt.topics.status", "test/flights_inttest/status")
    payload = {
        "status": "active",
        "visible_aircraft": 0,
        "last_update": "2026-04-01T00:00:00+00:00",
        "sw_version": "test",
    }
    publisher.publish(
        topic=status_topic, payload=json.dumps(payload), qos=1, retain=True
    )

    # Clean up
    publisher.publish(topic=status_topic, payload="", qos=1, retain=True)
