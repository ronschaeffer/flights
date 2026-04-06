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
from flights.hex_lookup import load_hex_db
from flights.logo_resolver import update_logos
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


def _check_web_server(config: FlightsConfig) -> str:
    """Check if the web server is reachable. Returns 'online' or 'offline'."""
    if not config.get("web_server.enabled", True):
        return "offline"
    port = int(config.get("web_server.port", 47475))
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=2)
        if resp.status_code == 200:
            return "online"
    except Exception:
        pass
    return "offline"


def _check_receiver(config: FlightsConfig) -> tuple[str, str]:
    """Check ADS-B receiver health via /ajax/stats.

    Returns (status, detail) where status is 'online' or 'offline'
    and detail explains the state.
    """
    if not config.get("receiver.health_check", True):
        return "online", ""
    dump_url = str(config.get("receiver.dump_url", ""))
    if not dump_url:
        return "offline", "No receiver URL configured"
    # Derive stats URL from dump URL (same host, /ajax/stats)
    base = (
        dump_url.rsplit("/ajax/", 1)[0]
        if "/ajax/" in dump_url
        else dump_url.rstrip("/")
    )
    stats_url = f"{base}/ajax/stats"
    try:
        resp = requests.get(stats_url, timeout=5)
        if resp.status_code != 200:
            return "offline", f"HTTP {resp.status_code} from {stats_url}"
        data = resp.json()
        bytes_ps = data.get("receiver_bytes_in_ps", 0)
        if bytes_ps > 0:
            return "online", f"Receiving {bytes_ps} bytes/s"
        return "offline", "Receiver not receiving data (0 bytes/s)"
    except requests.ConnectionError:
        return "offline", f"Cannot connect to {stats_url}"
    except Exception as exc:
        return "offline", str(exc)


def _publish_status(
    publisher,
    config: FlightsConfig,
    visible_count: int = 0,
    error: str = "",
) -> None:
    """Publish a status payload for diagnostic sensors."""
    status_topic = config.get("mqtt.topics.status", "flights/status")

    receiver_status, receiver_detail = _check_receiver(config)
    web_status = _check_web_server(config)

    status = "error" if error else "active"
    payload: dict[str, Any] = {
        "status": status,
        "visible_aircraft": visible_count,
        "last_update": datetime.now(UTC).isoformat(),
        "sw_version": __version__,
    }
    if config.get("web_server.enabled", True):
        payload["web_server_status"] = web_status
    if config.get("receiver.health_check", True):
        payload["receiver_status"] = receiver_status
        if receiver_detail:
            payload["receiver_detail"] = receiver_detail
    if error:
        payload["error"] = error
    try:
        publisher.publish(status_topic, payload, qos=1, retain=True)
    except Exception:
        logger.exception("Failed to publish status")


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------


def _load_reference_data():
    """Load airlines, aircraft, hex database, and reference dump data."""
    reference_dump_path = os.path.join(
        BASE_DIR, "data", "planefinder_dump_structure.json"
    )
    with open(reference_dump_path) as f:
        json.load(f)  # validate it loads

    airlines_path = os.path.join(BASE_DIR, "data", "airlines.json")
    aircraft_path = os.path.join(BASE_DIR, "data", "aircraft.json")
    with open(airlines_path) as f:
        airlines_json = json.load(f)
    with open(aircraft_path) as f:
        aircraft_json = json.load(f)
    hex_db = load_hex_db()
    return airlines_json, aircraft_json, hex_db


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
    hex_db: dict | None = None,
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
        hex_db=hex_db,
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

    # Publish status for diagnostic sensors
    _publish_status(publisher, config, visible_count=len(flights))

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
    airlines_json, aircraft_json, hex_db = _load_reference_data()
    defined_zone = _build_zone(config)
    base_url = _start_web_server(config)

    publisher = create_publisher(config)
    publisher.connect()
    availability = create_availability(publisher, config)
    availability.online(retain=True)
    publish_discovery(config, publisher)

    # Re-publish discovery + availability on every reconnect so HA recovers
    # even if EMQX loses retained messages (e.g. broker restart).
    _orig_on_connect = publisher.client.on_connect

    def _reconnect_on_connect(client, userdata, *args, **kwargs):
        if _orig_on_connect:
            _orig_on_connect(client, userdata, *args, **kwargs)
        if publisher._connected:
            try:
                availability.online(retain=True)
                publish_discovery(config, publisher)
                logger.info("Re-published discovery and availability after reconnect")
            except Exception:
                logger.exception("Failed to re-publish discovery on reconnect")

    publisher.client.on_connect = _reconnect_on_connect

    shutdown_event = threading.Event()
    refresh_event = threading.Event()

    def _shutdown_handler(signum, _frame):
        logger.info("Received signal %s, shutting down...", signum)
        shutdown_event.set()
        refresh_event.set()  # unblock any wait

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    # Subscribe to commands
    prefix = config.get("app.unique_id_prefix", "flights")
    cmd_topic = f"{prefix}/cmd/#"
    unique_flights_file = os.path.join(STORAGE_DIR, "unique_flights.json")

    def _on_command(_client, _userdata, msg):
        cmd = msg.topic.rsplit("/", 1)[-1].lower()
        logger.info("Command received: %s", cmd)
        if cmd == "refresh":
            refresh_event.set()
        elif cmd == "clear_cache":
            try:
                if os.path.exists(unique_flights_file):
                    os.remove(unique_flights_file)
                logger.info("Cache cleared (unique flights data removed)")
            except Exception:
                logger.exception("Failed to clear cache")
        elif cmd == "restart":
            logger.info("Restart requested, shutting down for container restart")
            shutdown_event.set()
            refresh_event.set()

    publisher.subscribe(cmd_topic, qos=1, callback=_on_command)
    publisher.loop_start()

    reg_parser = Parser()
    unique_flights_with_timestamps = load_unique_flights_data(unique_flights_file)
    check_interval = int(config.get("receiver.check_interval", 15))

    # Mutable container so the updater thread can swap the hex DB
    hex_ref: dict[str, Any] = {"db": hex_db}

    def _on_hex_db_update(new_db):
        hex_ref["db"] = new_db

    _start_hex_db_updater(shutdown_event, _on_hex_db_update)
    _start_logo_updater(shutdown_event, airlines_json)

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
                hex_db=hex_ref["db"],
            )
            # Wait for interval or refresh command
            refresh_event.wait(check_interval)
            refresh_event.clear()
    finally:
        logger.info("Shutting down...")
        publisher.loop_stop()
        availability.offline(retain=True)
        publisher.disconnect()
        print("\nFlights stopped.")


def cmd_once(config: FlightsConfig) -> None:
    """Single fetch → enrich → publish cycle, then exit."""
    _ensure_directories()
    _ensure_output_files()
    airlines_json, aircraft_json, hex_db = _load_reference_data()
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
            hex_db=hex_db,
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


def _download_hex_db() -> dict[str, Any] | None:
    """Download the latest hex database from tar1090-db.

    Returns the loaded database dict on success, or None on failure.
    """
    import urllib.request

    from flights.hex_lookup import HEX_DB_GZ_PATH

    url = "https://github.com/wiedehopf/tar1090-db/raw/refs/heads/csv/aircraft.csv.gz"
    logger.info("Downloading hex database from tar1090-db...")
    try:
        urllib.request.urlretrieve(url, HEX_DB_GZ_PATH)
        hex_db = load_hex_db(HEX_DB_GZ_PATH)
        logger.info("Hex database updated: %d entries", len(hex_db))
        return hex_db
    except Exception:
        logger.exception("Failed to download hex database")
        return None


_HEX_DB_UPDATE_INTERVAL = 7 * 24 * 3600  # 1 week in seconds


def _start_hex_db_updater(
    shutdown_event: threading.Event,
    update_callback,
) -> threading.Thread:
    """Start a daemon thread that refreshes the hex database weekly."""

    def _updater():
        while not shutdown_event.wait(_HEX_DB_UPDATE_INTERVAL):
            new_db = _download_hex_db()
            if new_db is not None:
                update_callback(new_db)

    t = threading.Thread(target=_updater, name="hex-db-updater", daemon=True)
    t.start()
    return t


_LOGO_UPDATE_INTERVAL = 7 * 24 * 3600  # 1 week in seconds


def _get_logo_ai_config() -> tuple[str | None, str | None]:
    """Read AI provider and key from environment variables."""
    provider = os.environ.get("LOGO_AI_PROVIDER", "").lower() or None
    if provider == "claude":
        key = os.environ.get("ANTHROPIC_API_KEY")
    elif provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
    else:
        key = None
    return provider, key


def _start_logo_updater(
    shutdown_event: threading.Event,
    airlines_json: list,
) -> threading.Thread:
    """Start a daemon thread that updates logos weekly."""

    def _updater():
        while not shutdown_event.wait(_LOGO_UPDATE_INTERVAL):
            provider, api_key = _get_logo_ai_config()
            try:
                summary = update_logos(
                    ai_provider=provider,
                    api_key=api_key,
                    airlines_json=airlines_json,
                    publish=True,
                )
                if summary.get("generated") or summary.get("synced"):
                    logger.info(
                        "Logo update: %d generated, %d synced",
                        len(summary.get("generated", [])),
                        len(summary.get("synced", [])),
                    )
            except Exception:
                logger.exception("Logo update failed")

    t = threading.Thread(target=_updater, name="logo-updater", daemon=True)
    t.start()
    return t


def cmd_update_data() -> None:
    """Download the latest hex database from tar1090-db (CLI command)."""
    result = _download_hex_db()
    if result is not None:
        from flights.hex_lookup import HEX_DB_GZ_PATH

        print(f"OK - {len(result)} aircraft in database")
        print(f"Saved to {HEX_DB_GZ_PATH}")
    else:
        print("FAILED - check logs for details")


def cmd_update_logos(publish: bool = False) -> None:
    """Sync logo formats and optionally generate missing logos (CLI command)."""
    airlines_path = os.path.join(BASE_DIR, "data", "airlines.json")
    try:
        with open(airlines_path) as f:
            airlines_json = json.load(f)
    except Exception:
        airlines_json = []

    provider, api_key = _get_logo_ai_config()
    if provider:
        print(f"AI provider: {provider}")
    else:
        print("AI generation: disabled (set LOGO_AI_PROVIDER + API key)")

    summary = update_logos(
        ai_provider=provider,
        api_key=api_key,
        airlines_json=airlines_json,
        publish=publish,
    )

    synced = summary.get("synced", [])
    generated = summary.get("generated", [])

    if synced:
        print(f"Synced {len(synced)} SVGs to PNG: {', '.join(synced[:10])}")
    if generated:
        print(f"Generated {len(generated)} logos: {', '.join(generated[:10])}")
    if not synced and not generated:
        print("No logos to update")

    print(
        f"Totals: {summary.get('total_svg', 0)} SVG, {summary.get('total_png', 0)} PNG"
    )

    if summary.get("published"):
        print("Changes committed and pushed to git")


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
    subparsers.add_parser(
        "update-data",
        help="Download latest hex database from tar1090-db",
    )
    logos_parser = subparsers.add_parser(
        "update-logos",
        help="Sync logo formats and generate missing logos",
    )
    logos_parser.add_argument(
        "--publish",
        action="store_true",
        help="Commit, tag, and push logo changes to git",
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
    elif command == "update-data":
        cmd_update_data()
    elif command == "update-logos":
        cmd_update_logos(publish=getattr(args, "publish", False))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
        sys.exit(0)
