"""Configuration management with nested YAML and environment variable overrides."""

import logging
import os
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Use FLIGHTS_BASE_DIR env var if set (Docker), otherwise derive from source tree.
# When pip-installed, __file__ is in site-packages so we fall back to cwd.
_src_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_has_config = os.path.isdir(os.path.join(_src_root, "config"))
BASE_DIR = os.environ.get("FLIGHTS_BASE_DIR") or (
    _src_root if _has_config else os.getcwd()
)

# Environment variable prefixes checked in order
_ENV_PREFIXES = ("FLIGHTS_", "")

# Mapping of flat env var names to nested config paths
_ENV_MAP = {
    "MQTT_BROKER_URL": "mqtt.broker_url",
    "MQTT_BROKER_PORT": "mqtt.broker_port",
    "MQTT_SECURITY": "mqtt.security",
    "MQTT_USERNAME": "mqtt.auth.username",
    "MQTT_PASSWORD": "mqtt.auth.password",
    "MQTT_CLIENT_ID": "mqtt.client_id",
    "MQTT_USE_TLS": "mqtt.tls.enabled",
    "TLS_VERIFY": "mqtt.tls.verify",
    "WEB_SERVER_ENABLED": "web_server.enabled",
    "WEB_SERVER_HOST": "web_server.host",
    "WEB_SERVER_PORT": "web_server.port",
    "WEB_SERVER_EXTERNAL_URL": "web_server.external_url",
    "IMAGE_FORMAT": "web_server.image_format",
    "DUMP_URL": "receiver.dump_url",
    "CHECK_INTERVAL": "receiver.check_interval",
    "HOME_ASSISTANT_ENABLED": "home_assistant.enabled",
    "LOG_LEVEL": "logging.level",
    "USER_LAT": "location.lat",
    "USER_LON": "location.lon",
    "DISTANCE_UNIT": "location.distance_unit",
    "ALTITUDE_UNIT": "location.altitude_unit",
}


def _coerce_value(value: str) -> Any:
    """Coerce string env var values to appropriate Python types."""
    low = value.lower()
    if low in ("true", "1", "yes", "on"):
        return True
    if low in ("false", "0", "no", "off"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _set_nested(data: dict, dotted_key: str, value: Any) -> None:
    """Set a value in a nested dict using dot-separated key."""
    keys = dotted_key.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _get_nested(data: dict, dotted_key: str, default: Any = None) -> Any:
    """Get a value from a nested dict using dot-separated key."""
    keys = dotted_key.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


class FlightsConfig:
    """Configuration loaded from YAML with environment variable overrides."""

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = os.path.join(BASE_DIR, "config", "config.yaml")

        self._data: dict = {}
        if os.path.exists(config_path):
            with open(config_path) as f:
                self._data = yaml.safe_load(f) or {}

        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides to config."""
        for env_name, config_path in _ENV_MAP.items():
            for prefix in _ENV_PREFIXES:
                full_name = f"{prefix}{env_name}"
                value = os.environ.get(full_name)
                if value is not None:
                    _set_nested(self._data, config_path, _coerce_value(value))
                    break

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value using dot notation (e.g. 'mqtt.broker_url')."""
        return _get_nested(self._data, key, default)

    def get_section(self, key: str) -> dict:
        """Get an entire config section as a dict."""
        result = _get_nested(self._data, key)
        if isinstance(result, dict):
            return dict(result)
        return {}

    @property
    def data(self) -> dict:
        """Return the raw config data."""
        return self._data


def load_config(config_path: str | None = None) -> FlightsConfig:
    """Load and return a FlightsConfig instance."""
    return FlightsConfig(config_path)
