import yaml
import json
import os
import uuid
import socket

def generate_unique_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def generate_discovery_payload():
    config_path = os.path.join(os.path.dirname(__file__), '../config/config.yaml')
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)

    if not config.get('HA_MQTT_DISCOVERY', False):
        return None

    # Generate and update unique identifiers
    config['DEVICE_IDENTIFIERS'] = generate_unique_id("flights")
    config['CLOSEST_UNIQUE_ID'] = generate_unique_id("closest")
    config['VISIBLE_UNIQUE_ID'] = generate_unique_id("visible")

    # Ensure CLOSEST_NAME and VISIBLE_NAME are set
    config['CLOSEST_NAME'] = config.get('CLOSEST_NAME', 'Closest Aircraft')
    config['VISIBLE_NAME'] = config.get('VISIBLE_NAME', 'Visible Aircraft')

    base_url = f"http://{get_lan_ip()}:{config.get('FASTAPI_PORT', 47474)}/"
    config['CONFIGURATION_URL'] = base_url

    discovery_config = config.get('HA_MQTT_DISCOVERY_CONFIG', '')
    for key, value in config.items():
        placeholder = f"${{{key}}}"
        if isinstance(value, str):
            discovery_config = discovery_config.replace(placeholder, value)

    # Parse discovery_config to a JSON object
    return json.loads(discovery_config)

def save_discovery_payload(payload, filepath):
    with open(filepath, 'w') as file:
        json.dump(payload, file, indent=4)

def get_discovery_file_path():
    return os.path.join(os.path.dirname(__file__), '../config/ha_mqtt_disc_payload.json')

def discovery_file_exists():
    return os.path.exists(get_discovery_file_path())

def process_ha_mqtt_discovery():
    if discovery_file_exists():
        print(f"Discovery payload file already exists at: {get_discovery_file_path()}")
        return True

    payload = generate_discovery_payload()
    if payload:
        save_discovery_payload(payload, get_discovery_file_path())
        print("\nGenerated new discovery payload:")
        print(json.dumps(payload, indent=4))
        return True
    return False