import os

import yaml

# Define base directory - from package in src/flights, go up two levels to reach project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _normalize(dct: dict) -> dict:
    return {str(k).lower(): v for k, v in (dct or {}).items()}


class ConfigProxy(dict):
    """Dictionary that prefers lowercase keys but tolerates uppercase lookups."""

    def get(self, key, default=None):
        if isinstance(key, str):
            lk = key.lower()
            if lk in self:
                return super().get(lk, default)
        return super().get(key, default)


def load_config() -> ConfigProxy:
    config_path = os.path.join(BASE_DIR, "config/config.yaml")
    with open(config_path) as config_file:
        raw = yaml.safe_load(config_file) or {}
    return ConfigProxy(_normalize(raw))


# Load configuration once for modules to import
config = load_config()
