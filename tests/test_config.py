"""Tests for configuration management."""

from flights.config import FlightsConfig


def test_load_config(config):
    """Config loads from YAML and provides dot-notation access."""
    assert config.get("app.name") == "Flights Test"
    assert config.get("mqtt.broker_url") == "localhost"
    assert config.get("mqtt.broker_port") == 1883
    assert config.get("web_server.port") == 47475


def test_config_defaults(config):
    """Missing keys return defaults."""
    assert config.get("nonexistent.key", "fallback") == "fallback"
    assert config.get("deeply.nested.missing") is None


def test_config_section(config):
    """get_section returns a dict for a section."""
    mqtt = config.get_section("mqtt")
    assert isinstance(mqtt, dict)
    assert mqtt["broker_url"] == "localhost"


def test_env_override(tmp_path, monkeypatch):
    """Environment variables override YAML config."""
    config_content = """
mqtt:
  broker_url: "yaml-host"
  broker_port: 1883
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    monkeypatch.setenv("MQTT_BROKER_URL", "env-host")
    monkeypatch.setenv("MQTT_BROKER_PORT", "8883")

    cfg = FlightsConfig(str(config_file))
    assert cfg.get("mqtt.broker_url") == "env-host"
    assert cfg.get("mqtt.broker_port") == 8883


def test_env_prefix_override(tmp_path, monkeypatch):
    """FLIGHTS_ prefixed env vars also work."""
    config_content = """
mqtt:
  broker_url: "yaml-host"
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    monkeypatch.setenv("FLIGHTS_MQTT_BROKER_URL", "prefixed-host")
    cfg = FlightsConfig(str(config_file))
    assert cfg.get("mqtt.broker_url") == "prefixed-host"


def test_bool_coercion(tmp_path, monkeypatch):
    """Bool-like env vars are coerced correctly."""
    config_content = """
home_assistant:
  enabled: false
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)

    monkeypatch.setenv("HOME_ASSISTANT_ENABLED", "true")
    cfg = FlightsConfig(str(config_file))
    assert cfg.get("home_assistant.enabled") is True


def test_missing_config_file():
    """Config works with missing file (all defaults)."""
    cfg = FlightsConfig("/nonexistent/path/config.yaml")
    assert cfg.get("mqtt.broker_url") is None
    assert cfg.data == {}
