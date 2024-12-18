#!/usr/bin/env python3

# Standard library imports
import time
from datetime import datetime, timezone
import json
import os
import threading
import logging
import sys
import traceback
from functools import wraps

# Third-party imports
import requests
import yaml
import haversine
import shapely.geometry
from tabulate import tabulate
from flydenity import Parser

# Local application/library-spec`ific imports
from flights_server import start_server
from flight_counts import (
    load_unique_flights_data, save_unique_flights_data, update_unique_flights,
    count_unique_flights_in_period, get_time_periods, calculate_averages
)
from enrich_flight_info import create_flights_rich
from mqtt_service import MQTTService

def get_log_level(level_str: str) -> int:
    """Convert string log level from config to logging constant."""
    return getattr(logging, level_str.upper(), logging.ERROR)

# Constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

# Variables
SERVER_PORT = 8000  # Default value

# Create logs directory and load config first
os.makedirs(LOG_DIR, exist_ok=True)

# Load configuration
config_path = os.path.join(BASE_DIR, 'config/config.yaml')
with open(config_path, 'r') as config_file:
    config = yaml.safe_load(config_file)

def load_configuration(config_path):
    """Load configuration and set global variables"""
    with open(config_path, 'r') as config_file:
        loaded_config = yaml.safe_load(config_file)
        # Update the global config
        config.update(loaded_config)
        # Set global variables
        for key, value in loaded_config.items():
            globals()[key] = value

# Configure logging with config log level
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'flights.log'),
    level=getattr(logging, config.get('LOG_LEVEL', 'ERROR').upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize module-specific logging
from flight_counts import initialize_logging
initialize_logging(config.get('LOG_LEVEL', 'ERROR'))

def handle_fatal_error(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"Fatal error occurred: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            print(f"\nFATAL ERROR: {str(e)}")
            print("Check logs for details: ../logs/flights.log")
            sys.exit(1)
    return wrapper

def load_configuration(config_path):
    with open(config_path, 'r') as config_file:
        config = yaml.safe_load(config_file)
    for key, value in config.items():
        globals()[key] = value

def get_receiver_data(dump_url):
    try:
        response = requests.get(dump_url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return {}

def process_flights(receiver, reference_dump):
    return {
        icao_id: {
            **{"icao_id": icao_id},
            **flight_data,
            **{key: flight_data.get(key, "") for key in reference_dump.get("aircraft", {}).get("icao_id", {})}
        }
        for icao_id, flight_data in receiver.get("aircraft", {}).items()
    }

def get_receiver_visible(flights, unique_flights_counts, averages):
    current_time_utc = int(time.time())
    current_time_readable = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "visible_aircraft": len(flights),
        "last_update_utc": current_time_utc,
        "last_update_readable": current_time_readable,
        "unique_flights": unique_flights_counts,
        "average_flights": averages
    }

def publish_and_print(mqtt_service, topic, data, previous_data, file_path, print_func=None):
    if data != previous_data:
        if print_func:
            print_func(data)
        write_to_file(file_path, data)
        mqtt_service.publish(topic, data)
        return data
    return previous_data

def print_receiver_visible(visible):
    table = [
        [key, "\n".join([f"{sub_key}: {sub_value}" for sub_key, sub_value in value.items()])] if key in {"unique_flights", "average_flights"} else [key, value]
        for key, value in visible.items()
    ]
    print("\n\nRECEIVER STATS\n" + tabulate(table, headers=["Key", "Value"], tablefmt="simple") + "\n")

def write_to_file(filename, data):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as json_file:
        json.dump(data, json_file, indent=4)

def get_closest_aircraft(flights_rich, user_location):
    closest_aircraft = None
    min_distance = float('inf')
    for flight in flights_rich.values():
        if 'lat' in flight and 'lon' in flight:
            try:
                lat, lon = float(flight['lat']), float(flight['lon'])
                distance = haversine.haversine(user_location, (lat, lon))
                if distance < min_distance:
                    min_distance = distance
                    closest_aircraft = {flight['icao_id']: flight}
            except ValueError:
                pass
    return closest_aircraft

def print_closest_aircraft(closest_aircraft):
    for key, value in closest_aircraft.items():
        print("\nCLOSEST AIRCRAFT\n" + tabulate(value.items(), headers=["Key", "Value"]) + "\n\n")

def save_flights_within_defined_zone(file_path, flights, zone):
    write_filtered_flights_to_file(file_path, flights, lambda flight: is_within_zone(flight, zone))

def save_flights_within_defined_radius(file_path, flights, center, radius):
    write_filtered_flights_to_file(file_path, flights, lambda flight: is_within_radius(flight, center, radius))

def is_within_zone(flight, zone):
    if 'lat' in flight and 'lon' in flight:
        try:
            lat, lon = float(flight['lat']), float(flight['lon'])
            return zone.contains(shapely.geometry.Point(lat, lon))
        except ValueError:
            pass
    return False

def is_within_radius(flight, center, radius):
    if 'lat' in flight and 'lon' in flight:
        try:
            lat, lon = float(flight['lat']), float(flight['lon'])
            return haversine.haversine(center, (lat, lon)) <= radius
        except ValueError:
            pass
    return False

def write_filtered_flights_to_file(file_path, flights, filter_func):
    filtered_flights = {icao_id: flight for icao_id, flight in flights.items() if filter_func(flight)}
    write_to_file(file_path, filtered_flights)

# Add src directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def ensure_json_file(filepath: str, default_content: dict) -> None:
    """Ensure JSON file exists and initialize it if not."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                json.dump(default_content, f, indent=4)
    except Exception as e:
        logging.error(f"Error ensuring JSON file {filepath}: {str(e)}\n{traceback.format_exc()}")

def get_lan_ip():
    """Get the machine's LAN IP address."""
    import socket
    try:
        # Create a UDP socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to an external IP address
        s.connect(('8.8.8.8', 80))
        # Get the local IP address
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'  # Fallback to localhost

def ensure_output_directory():
    """Central function to manage output directory creation and initialization"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Initialize all required output files with appropriate templates
    default_empty = {"last_update": datetime.now().isoformat(), "data": {}}
    default_stats = {
        "visible_aircraft": 0,
        "last_update_utc": int(time.time()),
        "last_update_readable": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "unique_flights": {},
        "average_flights": {}
    }
    default_missing = {
        "last_updated": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        "airlines": {},
        "aircraft": {},
        "airports": {}
    }
    
    # Ensure all required files exist with default content
    ensure_json_file(os.path.join(OUTPUT_DIR, 'visible.json'), default_stats)  # Use stats template
    ensure_json_file(os.path.join(OUTPUT_DIR, 'closest_aircraft.json'), default_empty)
    ensure_json_file(os.path.join(OUTPUT_DIR, 'all_aircraft.json'), default_empty)
    ensure_json_file(os.path.join(OUTPUT_DIR, 'missing.json'), default_missing)

@handle_fatal_error
def main():
    try:
        print("\n\n\n\n✈️  ✈️  ✈️   Flights - Rich flight data for MQTT, HTTP API and Home Assistant\n")
        
        # Load initial configuration using absolute path
        load_configuration(os.path.join(BASE_DIR, 'config/config.yaml'))

        # Create required directories
        ensure_output_directory()  # This is the only place output directory should be created
        os.makedirs(LOG_DIR, exist_ok=True)
        os.makedirs(os.path.join(BASE_DIR, 'storage'), exist_ok=True)

        # Now use the loaded config values with BASE_DIR
        reference_dump_path = os.path.join(BASE_DIR, config['REFERENCE_DUMP_FILE_PATH'])
        with open(reference_dump_path, 'r') as reference_dump_file:
            reference_dump = json.load(reference_dump_file)

        # Load additional JSON files
        airlines_path = os.path.join(BASE_DIR, 'data/airlines.json')
        aircraft_path = os.path.join(BASE_DIR, 'data/aircraft.json')
        
        with open(airlines_path, 'r') as airlines_file:
            airlines_json = json.load(airlines_file)
        with open(aircraft_path, 'r') as aircraft_file:
            aircraft_json = json.load(aircraft_file)

        mqtt_service = MQTTService({
            'MQTT_CLIENT_ID': MQTT_CLIENT_ID,
            'MQTT_BROKER': MQTT_BROKER,
            'MQTT_BROKER_PORT': MQTT_BROKER_PORT,
            'MQTT_USER': MQTT_USER,
            'MQTT_PWD': MQTT_PWD,
            'LOG_LEVEL': config.get('LOG_LEVEL', 'ERROR')
        })
        mqtt_service.connect()

        # Define the geographical zone
        defined_zone = shapely.geometry.Polygon([
            (LON_WEST, LAT_SOUTH),
            (LON_WEST, LAT_NORTH),
            (LON_EAST, LAT_NORTH),
            (LON_EAST, LAT_SOUTH)
        ])

        # Start the FastAPI server in a separate thread
        default_image_format = config.get('IMAGE_FORMAT', 'svg').lower()  # Get IMAGE_FORMAT from config
        server_thread = threading.Thread(
            target=start_server, 
            args=(FASTAPI_PORT, config.get('LOG_LEVEL', 'ERROR'), default_image_format)  # Pass default_image_format
        )
        server_thread.daemon = True  # Make thread daemon so it exits when main program exits
        server_thread.start()

        # Allow some time for the server to start and set the base_url
        time.sleep(2)  # Adjust as needed
        
        reg_parser = Parser()
        previous_visible = {}
        previous_closest_aircraft = {}

        # Ensure the storage directory exists
        storage_directory = os.path.join(BASE_DIR, 'storage')
        os.makedirs(storage_directory, exist_ok=True)

        # Load unique flights data
        unique_flights_file = os.path.join(storage_directory, 'unique_flights_with_timestamps.pkl')
        unique_flights_with_timestamps = load_unique_flights_data(unique_flights_file)

        base_url = f"http://{get_lan_ip()}:{FASTAPI_PORT}"

        # Main program loop
        while True:
            receiver = get_receiver_data(DUMP_URL)
            
            if not receiver:
                continue
                
            flights = process_flights(receiver, reference_dump)
            flights_rich = create_flights_rich(
                flights, 
                airlines_json,
                aircraft_json, 
                reg_parser, 
                (USER_LAT, USER_LON), 
                RADIUS, 
                defined_zone,
                ALTITUDE_UNIT,
                DISTANCE_UNIT,
                ALTITUDE_TRENDS,
                base_url  # Pass base_url to create_flights_rich
            )
            
            # Define time periods and calculate counts
            time_periods = get_time_periods()
            unique_flights_counts = {
                period: count_unique_flights_in_period(unique_flights_with_timestamps, start_time)
                for period, start_time in time_periods.items()
            }

            # Calculate averages
            averages = calculate_averages(unique_flights_with_timestamps, unique_flights_counts)

            # Update and publish visible data
            visible = get_receiver_visible(flights, unique_flights_counts, averages)
            previous_visible = publish_and_print(
                mqtt_service, 
                MQTT_TOPIC_VISIBLE,  # Changed from MQTT_TOPIC_STATISTICS to MQTT_TOPIC_VISIBLE
                visible,  # This is already in the correct format
                previous_visible,
                os.path.join(OUTPUT_DIR, 'visible.json'),  # Fix path - was using closest_aircraft.json
                print_receiver_visible
            )

            # Process and publish closest aircraft
            closest_aircraft = get_closest_aircraft(flights_rich, (USER_LAT, USER_LON))
            previous_closest_aircraft = publish_and_print(
                mqtt_service, 
                MQTT_TOPIC_CLOSEST_AIRCRAFT, 
                closest_aircraft, 
                previous_closest_aircraft,  # Use previous_closest_aircraft
                os.path.join(BASE_DIR, 'output/closest_aircraft.json'),  # Fixed path
                print_closest_aircraft
            )  # Closing parenthesis
            
            # Publish all flights data without printing
            publish_and_print(
                mqtt_service, 
                MQTT_TOPIC_FLIGHTS, 
                flights_rich, 
                None, 
                os.path.join(BASE_DIR, 'output/all_aircraft.json')  # Fixed path
            )

            # Update unique flights tracking
            current_unique_flights = set(flight["icao_id"] for flight in flights.values())
            update_unique_flights(unique_flights_with_timestamps, current_unique_flights, CHECK_INTERVAL)
            save_unique_flights_data(unique_flights_file, unique_flights_with_timestamps)

            # Wait for next update
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unhandled exception: {str(e)}\n{traceback.format_exc()}")
        print(f"\nUnhandled exception: {str(e)}")
        print("Check logs for details: ../logs/flights.log")
        sys.exit(1)