#!/usr/bin/env python3

import json
import logging
import os
import sys
import threading
import time
import traceback
from datetime import UTC, datetime
from typing import Any

import requests
import shapely.geometry
from flydenity import Parser

from .config_manager import BASE_DIR, config
from .enrich_flight_info import create_flights_rich
from .flight_counts import (
    calculate_averages,
    count_unique_flights_in_period,
    get_time_periods,
    load_unique_flights_data,
    save_unique_flights_data,
    update_unique_flights,
)
from .flights_server import get_lan_ip, start_server
from .ha_mqtt_discovery import get_discovery_file_path, process_ha_mqtt_discovery
from .mqtt_service import MQTTService

# Paths
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def ensure_json_file(filepath: str, default_content: dict) -> None:
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        if not os.path.exists(filepath):
            with open(filepath, "w") as f:
                json.dump(default_content, f, indent=2)
    except Exception as e:
        logging.error(f"Error ensuring JSON file {filepath}: {e}\n{traceback.format_exc()}")


def ensure_output_directory() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    default_empty = {"last_update": datetime.now().isoformat(), "data": {}}
    default_stats = {
        "visible_aircraft": 0,
        "last_update_utc": int(time.time()),
        "last_update_readable": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "unique_flights": {},
        "average_flights": {},
    }
    default_missing = {
        "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "airlines": {},
        "aircraft": {},
        "airports": {},
    }

    ensure_json_file(os.path.join(OUTPUT_DIR, "visible.json"), default_stats)
    ensure_json_file(os.path.join(OUTPUT_DIR, "closest_aircraft.json"), default_empty)
    ensure_json_file(os.path.join(OUTPUT_DIR, "all_aircraft.json"), default_empty)
    ensure_json_file(os.path.join(OUTPUT_DIR, "missing.json"), default_missing)


def write_to_file(file_path: str, data: Any) -> None:
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Error writing file {file_path}: {e}\n{traceback.format_exc()}")


def get_receiver_data(url: str) -> dict[str, Any] | None:
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logging.error(f"Error fetching receiver data: {e}")
    return None


def process_flights(receiver: dict[str, Any], reference_dump: dict[str, Any]) -> dict[str, dict[str, Any]]:
    # Minimal processing: return aircraft dictionary as-is
    return receiver.get("aircraft", {}) if receiver else {}


def get_receiver_visible(
    flights: dict[str, dict[str, Any]],
    unique_counts: dict[str, int],
    averages: dict[str, int],
) -> dict[str, Any]:
    now = int(time.time())
    return {
        "visible_aircraft": len(flights or {}),
        "last_update_utc": now,
        "last_update_readable": datetime.fromtimestamp(now, tz=UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "unique_flights": unique_counts,
        "average_flights": averages,
    }


def publish_and_print(
    mqtt_service: MQTTService,
    topic: str,
    data: dict[str, Any],
    previous: dict[str, Any],
    file_path: str,
    print_func=None,
) -> dict[str, Any]:
    try:
        if data != previous:
            write_to_file(file_path, data)
            mqtt_service.publish(topic, data, qos=1, retain=True)
            if print_func:
                try:
                    print_func(data)
                except Exception:
                    pass
        return data
    except Exception as e:
        logging.error(f"Publish/print error for topic {topic}: {e}\n{traceback.format_exc()}")
        return previous


def get_closest_aircraft(
    flights_rich: dict[str, dict[str, Any]], user_location: tuple[float, float]
) -> dict[str, dict[str, Any]]:
    if not flights_rich:
        return {}

    def distance_val(f):
        try:
            return float(f.get("distance_value", 1e9))
        except Exception:
            return 1e9

    closest_id, closest = None, None
    for icao_id, flight in flights_rich.items():
        if closest is None or distance_val(flight) < distance_val(closest):
            closest_id, closest = icao_id, flight
    return {closest_id: closest} if closest_id and closest else {}


def print_receiver_visible(data: dict[str, Any]) -> None:
    print(f"Visible aircraft: {data.get('visible_aircraft')} at {data.get('last_update_readable')}")


def print_closest_aircraft(data: dict[str, Any]) -> None:
    try:
        if not data:
            print("No closest aircraft")
            return
        icao_id = next(iter(data.keys()))
        info = data[icao_id]
        dist = info.get("distance") or info.get("distance_value")
        cs = info.get("callsign") or icao_id
        print(f"Closest: {cs} ({icao_id}), distance: {dist}")
    except Exception:
        pass


def handle_ha_mqtt_discovery(cfg, mqtt_service: MQTTService, base_url: str) -> None:
    if cfg.get("ha_mqtt_discovery", False):
        discovery_file_path = get_discovery_file_path()
        if not os.path.exists(discovery_file_path):
            process_ha_mqtt_discovery(base_url)
        else:
            print(f"Discovery payload exists: {discovery_file_path} - publishing anyway")
        try:
            with open(discovery_file_path) as f:
                discovery_payload = json.load(f)
            config_topic = cfg.get("config_topic", "homeassistant/device/dev_flights/config")
            mqtt_service.publish(config_topic, discovery_payload, qos=1, retain=True)
            print(f"Published discovery payload to topic: {config_topic}")
        except Exception as e:
            print(f"Failed to publish discovery payload: {e}")


def main() -> None:
    print("\n✈️  Flights - Rich flight data for MQTT, HTTP API and Home Assistant\n")

    # Create required directories
    ensure_output_directory()
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "storage"), exist_ok=True)

    # Load reference dump
    reference_dump_rel = config.get("reference_dump_file_path") or "config/planefinder_dump_structure.json"
    reference_dump_path = os.path.join(BASE_DIR, str(reference_dump_rel))
    with open(reference_dump_path) as reference_dump_file:
        reference_dump = json.load(reference_dump_file)

    # Load additional JSON files
    airlines_path = os.path.join(BASE_DIR, "data/airlines.json")
    aircraft_path = os.path.join(BASE_DIR, "data/aircraft.json")
    with open(airlines_path) as airlines_file:
        airlines_json = json.load(airlines_file)
    with open(aircraft_path) as aircraft_file:
        aircraft_json = json.load(aircraft_file)

    # Define the geographical zone
    lon_west = float(config.get("lon_west") or 0.0)
    lat_south = float(config.get("lat_south") or 0.0)
    lon_east = float(config.get("lon_east") or 0.0)
    lat_north = float(config.get("lat_north") or 0.0)
    defined_zone = shapely.geometry.Polygon(
        [
            (lon_west, lat_south),
            (lon_west, lat_north),
            (lon_east, lat_north),
            (lon_east, lat_south),
        ]
    )

    # Start the FastAPI server in a separate thread
    default_image_format = (config.get("image_format") or "svg").lower()
    fastapi_port = int(config.get("fastapi_port") or 8000)
    server_thread = threading.Thread(
        target=start_server,
        args=(fastapi_port, config.get("log_level", "ERROR"), default_image_format),
        daemon=True,
    )
    server_thread.start()

    base_url = f"http://{get_lan_ip()}:{fastapi_port}"

    # Wait for the server to start
    for _ in range(10):
        try:
            response = requests.get(base_url, timeout=1)
            if response.status_code == 200:
                break
        except requests.ConnectionError:
            time.sleep(1)
    else:
        raise RuntimeError("Server did not start in time")

    # Initialize MQTT service
    mqtt_service = MQTTService(config)
    mqtt_service.connect()

    # Home Assistant discovery
    handle_ha_mqtt_discovery(config, mqtt_service, base_url)

    reg_parser = Parser()
    previous_visible: dict[str, Any] = {}
    previous_closest_aircraft: dict[str, Any] = {}
    previous_flights_rich: dict[str, Any] = {}

    storage_directory = os.path.join(BASE_DIR, "storage")
    os.makedirs(storage_directory, exist_ok=True)

    unique_flights_file = os.path.join(storage_directory, "unique_flights_with_timestamps.pkl")
    unique_flights_with_timestamps = load_unique_flights_data(unique_flights_file)

    # Main program loop
    while True:
        dump_url = str(config.get("dump_url") or "")
        receiver = get_receiver_data(dump_url) if dump_url else None
        if not receiver:
            time.sleep(int(config.get("check_interval") or 15))
            continue

        flights = process_flights(receiver, reference_dump)
        flights_rich = create_flights_rich(
            flights,
            airlines_json,
            aircraft_json,
            reg_parser,
            (
                float(config.get("user_lat") or 0.0),
                float(config.get("user_lon") or 0.0),
            ),
            float(config.get("radius") or 0.0),
            defined_zone,
            (config.get("altitude_unit") or "ft"),
            (config.get("distance_unit") or "mi"),
            (
                config.get("altitude_trends")
                or {
                    "LEVEL_THRESHOLD": 250,
                    "SYMBOLS": {"UP": "⬈", "DOWN": "⬊", "LEVEL": "→"},
                }
            ),
            base_url,
        )

        time_periods = get_time_periods()
        unique_flights_counts = {
            period: count_unique_flights_in_period(unique_flights_with_timestamps, start_time)
            for period, start_time in time_periods.items()
        }
        averages = calculate_averages(unique_flights_with_timestamps, unique_flights_counts)

        visible = get_receiver_visible(flights, unique_flights_counts, averages)
        previous_visible = publish_and_print(
            mqtt_service,
            str(config.get("mqtt_topic_visible") or "dev/flights/visible"),
            visible,
            previous_visible,
            os.path.join(OUTPUT_DIR, "visible.json"),
            print_receiver_visible,
        )

        closest_aircraft = get_closest_aircraft(
            flights_rich,
            (
                float(config.get("user_lat") or 0.0),
                float(config.get("user_lon") or 0.0),
            ),
        )
        previous_closest_aircraft = publish_and_print(
            mqtt_service,
            str(config.get("mqtt_topic_closest_aircraft") or "dev/flights/closest"),
            closest_aircraft,
            previous_closest_aircraft,
            os.path.join(OUTPUT_DIR, "closest_aircraft.json"),
            print_closest_aircraft,
        )

        if flights_rich != previous_flights_rich:
            write_to_file(os.path.join(OUTPUT_DIR, "all_aircraft.json"), flights_rich)
            previous_flights_rich = flights_rich

        current_unique_flights = {flight.get("icao_id") for flight in flights.values() if isinstance(flight, dict)}
        update_unique_flights(
            unique_flights_with_timestamps,
            current_unique_flights,
            int(config.get("check_interval") or 15),
        )
        save_unique_flights_data(unique_flights_file, unique_flights_with_timestamps)

        time.sleep(int(config.get("check_interval") or 15))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unhandled exception: {e}\n{traceback.format_exc()}")
        print(f"\nUnhandled exception: {e}")
        print("Check logs for details: ../logs/flights.log")
    sys.exit(1)
