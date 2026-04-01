"""Flights - ADS-B flight data enrichment for MQTT and Home Assistant."""

import argparse
from datetime import UTC, datetime
import json
import logging
import os
import signal
import sys
import threading
import time
from typing import Any

from flydenity import Parser
import requests
import shapely.geometry

from flights import __version__
from flights.config import BASE_DIR, FlightsConfig, load_config
from flights.counts import (
    calculate_averages,
    count_unique_flights_in_period,
    get_time_periods,
    load_unique_flights_data,
    save_unique_flights_data,
    update_unique_flights,
)
from flights.discovery import publish_discovery
from flights.enricher import create_flights_rich
from flights.mqtt_client import create_availability, create_publisher
from flights.server import get_base_url, start_server

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
STORAGE_DIR = os.path.join(BASE_DIR, "storage")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _ensure_directories() -> None:
    for d in (OUTPUT_DIR, STORAGE_DIR):
        os.makedirs(d, exist_ok=True)


def _ensure_json_file(filepath: str, default_content: dict) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            json.dump(default_content, f, indent=2)


def _ensure_output_files() -> None:
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    _ensure_json_file(
        os.path.join(OUTPUT_DIR, "visible.json"),
        {
            "visible_aircraft": 0,
            "last_update_utc": int(time.time()),
            "last_update_readable": now_str,
            "unique_flights": {},
            "average_flights": {},
        },
    )
    _ensure_json_file(
        os.path.join(OUTPUT_DIR, "closest_aircraft.json"),
        {"last_update": datetime.now(UTC).isoformat(), "data": {}},
    )
    _ensure_json_file(
        os.path.join(OUTPUT_DIR, "all_aircraft.json"),
        {"last_update": datetime.now(UTC).isoformat(), "data": {}},
    )
    _ensure_json_file(
        os.path.join(OUTPUT_DIR, "missing.json"),
        {
            "last_updated": now_str,
            "airlines": {},
            "aircraft": {},
            "airports": {},
        },
    )


def _write_to_file(file_path: str, data: Any) -> None:
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        logger.exception("Error writing file %s", file_path)


def _get_receiver_data(url: str) -> dict[str, Any] | None:
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        logger.exception("Error fetching receiver data")
    return None


def _get_receiver_visible(
    flights: dict,
    unique_counts: dict,
    averages: dict,
) -> dict[str, Any]:
    now = int(time.time())
    return {
        "visible_aircraft": len(flights or {}),
        "last_update_utc": now,
        "last_update_readable": datetime.fromtimestamp(now, tz=UTC).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "unique_flights": unique_counts,
        "average_flights": averages,
    }


def _get_closest_aircraft(
    flights_rich: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not flights_rich:
        return {}

    def dist_val(f):
        try:
            return float(f.get("distance_value", 1e9))
        except (ValueError, TypeError):
            return 1e9

    closest_id = min(flights_rich, key=lambda k: dist_val(flights_rich[k]))
    return {closest_id: flights_rich[closest_id]}


def _publish_and_save(
    publisher,
    topic: str,
    data: dict,
    previous: dict,
    file_path: str,
) -> dict:
    """Publish to MQTT and save to file only if data changed."""
    if data != previous:
        _write_to_file(file_path, data)
        try:
            publisher.publish(topic, data, qos=1, retain=True)
        except Exception:
            logger.exception("MQTT publish error for topic %s", topic)
    return data


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------


def _load_reference_data():
    """Load airlines, aircraft, and reference dump data."""
    reference_dump_path = os.path.join(
        BASE_DIR, "config", "planefinder_dump_structure.json"
    )
    with open(reference_dump_path) as f:
        json.load(f)  # validate it loads

    airlines_path = os.path.join(BASE_DIR, "data", "airlines.json")
    aircraft_path = os.path.join(BASE_DIR, "data", "aircraft.json")
    with open(airlines_path) as f:
        airlines_json = json.load(f)
    with open(aircraft_path) as f:
        aircraft_json = json.load(f)
    return airlines_json, aircraft_json


def _build_zone(config: FlightsConfig):
    """Build the geographic watch zone polygon."""
    lon_west = float(config.get("zone.lon_west", 0.0))
    lat_south = float(config.get("zone.lat_south", 0.0))
    lon_east = float(config.get("zone.lon_east", 0.0))
    lat_north = float(config.get("zone.lat_north", 0.0))
    return shapely.geometry.Polygon(
        [
            (lon_west, lat_south),
            (lon_west, lat_north),
            (lon_east, lat_north),
            (lon_east, lat_south),
        ]
    )


def _start_web_server(config: FlightsConfig) -> str:
    """Start the web server in a background thread. Returns the base URL."""
    web_enabled = config.get("web_server.enabled", True)
    web_port = int(config.get("web_server.port", 47475))
    image_format = str(config.get("web_server.image_format", "svg"))
    external_url = str(config.get("web_server.external_url", "") or "")

    if not web_enabled:
        return ""

    server_thread = threading.Thread(
        target=start_server,
        args=(
            web_port,
            config.get("logging.level", "ERROR"),
            image_format,
            external_url,
        ),
        daemon=True,
    )
    server_thread.start()

    # Wait for server startup
    for _ in range(10):
        try:
            response = requests.get(f"http://127.0.0.1:{web_port}/health", timeout=1)
            if response.status_code == 200:
                break
        except requests.ConnectionError:
            time.sleep(1)
    else:
        logger.warning("Web server did not start in time")

    return get_base_url()


def _run_cycle(
    config: FlightsConfig,
    publisher,
    airlines_json: list,
    aircraft_json: list,
    reg_parser,
    defined_zone,
    base_url: str,
    unique_flights_with_timestamps: dict,
    previous_visible: dict,
    previous_closest: dict,
    previous_flights_rich: dict,
) -> tuple[dict, dict, dict]:
    """Run a single fetch → enrich → publish cycle.

    Returns updated (previous_visible, previous_closest, previous_flights_rich).
    """
    dump_url = str(config.get("receiver.dump_url", ""))
    receiver = _get_receiver_data(dump_url) if dump_url else None
    if not receiver:
        logger.warning("No data from receiver")
        return previous_visible, previous_closest, previous_flights_rich

    flights = receiver.get("aircraft", {}) or {}
    user_lat = float(config.get("location.lat", 0.0))
    user_lon = float(config.get("location.lon", 0.0))
    flights_rich = create_flights_rich(
        flights,
        airlines_json,
        aircraft_json,
        reg_parser,
        (user_lat, user_lon),
        float(config.get("location.radius", 10.0)),
        defined_zone,
        str(config.get("location.altitude_unit", "ft")),
        str(config.get("location.distance_unit", "mi")),
        config.get("location.altitude_trends")
        or {
            "LEVEL_THRESHOLD": 250,
            "SYMBOLS": {
                "UP": "\u2b08",
                "DOWN": "\u2b0a",
                "LEVEL": "\u2192",
            },
        },
        base_url,
    )

    # Flight counts
    visible_topic = config.get("mqtt.topics.visible", "flights/visible")
    closest_topic = config.get("mqtt.topics.closest", "flights/closest")
    check_interval = int(config.get("receiver.check_interval", 15))
    unique_flights_file = os.path.join(STORAGE_DIR, "unique_flights.json")

    time_periods = get_time_periods()
    unique_counts = {
        period: count_unique_flights_in_period(
            unique_flights_with_timestamps, start_time
        )
        for period, start_time in time_periods.items()
    }
    averages = calculate_averages(unique_flights_with_timestamps, unique_counts)

    # Publish visible
    visible = _get_receiver_visible(flights, unique_counts, averages)
    previous_visible = _publish_and_save(
        publisher,
        visible_topic,
        visible,
        previous_visible,
        os.path.join(OUTPUT_DIR, "visible.json"),
    )

    # Publish closest
    closest = _get_closest_aircraft(flights_rich)
    previous_closest = _publish_and_save(
        publisher,
        closest_topic,
        closest,
        previous_closest,
        os.path.join(OUTPUT_DIR, "closest_aircraft.json"),
    )

    # Save all aircraft
    if flights_rich != previous_flights_rich:
        _write_to_file(
            os.path.join(OUTPUT_DIR, "all_aircraft.json"),
            flights_rich,
        )
        previous_flights_rich = flights_rich

    # Update unique flights
    current_unique = {
        flight.get("icao_id") for flight in flights.values() if isinstance(flight, dict)
    }
    update_unique_flights(
        unique_flights_with_timestamps,
        current_unique,
        check_interval,
    )
    save_unique_flights_data(unique_flights_file, unique_flights_with_timestamps)

    print(
        f"Visible: {visible.get('visible_aircraft', 0)}, "
        f"Closest: {next(iter(closest), 'none')}"
    )

    return previous_visible, previous_closest, previous_flights_rich


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def cmd_service(config: FlightsConfig) -> None:
    """Long-running service: fetch → enrich → publish in a loop."""
    _ensure_directories()
    _ensure_output_files()
    airlines_json, aircraft_json = _load_reference_data()
    defined_zone = _build_zone(config)
    base_url = _start_web_server(config)

    publisher = create_publisher(config)
    publisher.connect()
    availability = create_availability(publisher, config)
    availability.online(retain=True)
    publish_discovery(config, publisher)

    shutdown_event = threading.Event()

    def _shutdown_handler(signum, _frame):
        logger.info("Received signal %s, shutting down...", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    reg_parser = Parser()
    unique_flights_file = os.path.join(STORAGE_DIR, "unique_flights.json")
    unique_flights_with_timestamps = load_unique_flights_data(unique_flights_file)
    check_interval = int(config.get("receiver.check_interval", 15))

    prev_vis: dict = {}
    prev_closest: dict = {}
    prev_rich: dict = {}

    try:
        while not shutdown_event.is_set():
            prev_vis, prev_closest, prev_rich = _run_cycle(
                config,
                publisher,
                airlines_json,
                aircraft_json,
                reg_parser,
                defined_zone,
                base_url,
                unique_flights_with_timestamps,
                prev_vis,
                prev_closest,
                prev_rich,
            )
            shutdown_event.wait(check_interval)
    finally:
        logger.info("Shutting down...")
        availability.offline(retain=True)
        publisher.disconnect()
        print("\nFlights stopped.")


def cmd_once(config: FlightsConfig) -> None:
    """Single fetch → enrich → publish cycle, then exit."""
    _ensure_directories()
    _ensure_output_files()
    airlines_json, aircraft_json = _load_reference_data()
    defined_zone = _build_zone(config)
    base_url = str(config.get("web_server.external_url", "") or "")

    publisher = create_publisher(config)
    publisher.connect()
    availability = create_availability(publisher, config)
    availability.online(retain=True)
    publish_discovery(config, publisher)

    reg_parser = Parser()
    unique_flights_file = os.path.join(STORAGE_DIR, "unique_flights.json")
    unique_flights_with_timestamps = load_unique_flights_data(unique_flights_file)

    try:
        _run_cycle(
            config,
            publisher,
            airlines_json,
            aircraft_json,
            reg_parser,
            defined_zone,
            base_url,
            unique_flights_with_timestamps,
            {},
            {},
            {},
        )
    finally:
        availability.offline(retain=True)
        publisher.disconnect()

    print("\nDone.")


def cmd_status(config: FlightsConfig) -> None:
    """Print configuration and check connectivity."""
    print(f"Flights v{__version__}\n")

    print("Configuration:")
    print(f"  Receiver URL:   {config.get('receiver.dump_url', '(not set)')}")
    print(f"  Check interval: {config.get('receiver.check_interval', 15)}s")
    print(f"  MQTT broker:    {config.get('mqtt.broker_url', '(not set)')}")
    print(f"  MQTT port:      {config.get('mqtt.broker_port', 1883)}")
    print(f"  MQTT security:  {config.get('mqtt.security', 'none')}")
    print(f"  MQTT topics:    {config.get('mqtt.topics.visible', 'flights/visible')}")
    print(f"                  {config.get('mqtt.topics.closest', 'flights/closest')}")
    print(f"  HA discovery:   {config.get('home_assistant.enabled', True)}")
    print(f"  Web server:     {config.get('web_server.enabled', True)}")
    print(f"  External URL:   {config.get('web_server.external_url', '(not set)')}")
    print(
        f"  Location:       {config.get('location.lat')}, {config.get('location.lon')}"
    )
    print()

    # Check receiver
    dump_url = config.get("receiver.dump_url", "")
    if dump_url:
        print(f"Checking receiver at {dump_url}...")
        try:
            resp = requests.get(dump_url, timeout=5)
            data = resp.json()
            aircraft = data.get("aircraft", {})
            print(f"  OK - {len(aircraft)} aircraft visible")
        except Exception as e:
            print(f"  FAILED - {e}")
    else:
        print("Receiver URL not configured")

    print()

    # Check MQTT
    broker = config.get("mqtt.broker_url", "")
    if broker:
        print(
            f"Checking MQTT broker at {broker}:{config.get('mqtt.broker_port', 1883)}..."
        )
        try:
            publisher = create_publisher(config)
            publisher.connect()
            publisher.disconnect()
            print("  OK - connected successfully")
        except Exception as e:
            print(f"  FAILED - {e}")
    else:
        print("MQTT broker not configured")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Flights - ADS-B flight data enrichment for MQTT and Home Assistant",
    )
    parser.add_argument("--version", action="version", version=f"flights {__version__}")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (default: config/config.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "service",
        help="Run as a long-running service (default)",
    )
    subparsers.add_parser(
        "once",
        help="Run a single fetch/enrich/publish cycle and exit",
    )
    subparsers.add_parser(
        "status",
        help="Show configuration and check connectivity",
    )

    args = parser.parse_args()
    config = load_config(args.config)
    _setup_logging(config.get("logging.level", "INFO"))

    print(
        f"\nFlights v{__version__} - ADS-B flight data for MQTT, "
        "HTTP API and Home Assistant\n"
    )

    command = args.command or "service"

    if command == "service":
        cmd_service(config)
    elif command == "once":
        cmd_once(config)
    elif command == "status":
        cmd_status(config)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
        sys.exit(0)
