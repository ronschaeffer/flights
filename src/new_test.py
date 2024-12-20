import yaml
import os
from ha_mqtt_discovery import process_ha_mqtt_discovery

def main():
    config_path = os.path.join(os.path.dirname(__file__), '../config/config.yaml')
    with open(config_path, 'r') as file:
        config = yaml.safe_load(file)

    if not config.get('HA_MQTT_DISCOVERY', False):
        print("Home Assistant MQTT Discovery is not enabled in config.")
        return

    process_ha_mqtt_discovery()

if __name__ == "__main__":
    main()