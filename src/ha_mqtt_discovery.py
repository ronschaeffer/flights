import json
import os
from typing import Any
import uuid

from config_manager import BASE_DIR, config


def generate_unique_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _build_variables_map(base_url: str | None) -> dict[str, Any]:
    # Start with config values (uppercased keys for placeholder matching)
    variables: dict[str, Any] = {str(k).upper(): v for k, v in config.items()}

    # Inject/override dynamic variables and defaults
    variables.setdefault("CLOSEST_NAME", "Closest Aircraft")
    variables.setdefault("VISIBLE_NAME", "Visible Aircraft")
    if base_url:
        variables["CONFIGURATION_URL"] = base_url

    # Generate unique identifiers each run
    variables["DEVICE_IDENTIFIERS"] = generate_unique_id("flights")
    variables["CLOSEST_UNIQUE_ID"] = generate_unique_id("closest")
    variables["VISIBLE_UNIQUE_ID"] = generate_unique_id("visible")

    return variables


def generate_discovery_payload(base_url: str | None) -> dict | None:
    if not config.get("ha_mqtt_discovery", False) and not config.get("HA_MQTT_DISCOVERY", False):
        return None

    variables = _build_variables_map(base_url)

    template = config.get("ha_mqtt_discovery_config") or config.get("HA_MQTT_DISCOVERY_CONFIG") or ""
    if not template:
        return None

    # Perform simple placeholder substitution ${KEY}
    rendered = template
    for key, value in variables.items():
        placeholder = f"${{{key}}}"
        rendered = rendered.replace(placeholder, str(value))

    return json.loads(rendered)


def save_discovery_payload(payload: dict, filepath: str) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as file:
        json.dump(payload, file, indent=4)


def get_discovery_file_path() -> str:
    return os.path.join(BASE_DIR, "config", "ha_mqtt_disc_payload.json")


def process_ha_mqtt_discovery(base_url: str | None = None) -> bool:
    payload = generate_discovery_payload(base_url)
    if payload:
        save_discovery_payload(payload, get_discovery_file_path())
        print("\nGenerated new discovery payload:")
        print(json.dumps(payload, indent=4))
        return True
    return False
