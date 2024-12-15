#!/usr/bin/env python3

# Standard library imports
import time
from datetime import datetime, timezone
import json
import os
import threading

# Third-party imports
import requests
import yaml
import haversine
import shapely.geometry
from tabulate import tabulate
from flydenity import Parser

# Local application/library-specific imports
from flights_server import start_server
from flight_counts import (
    load_unique_flights_data, save_unique_flights_data, update_unique_flights,
    count_unique_flights_in_period, get_time_periods, calculate_averages
)
from enrich_flight_info import create_flights_rich
from mqtt_service import MQTTService

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

def main():
    try:
        config_path = os.path.join(os.path.dirname(__file__), '../config/config.yaml')
        load_configuration(config_path)

        with open(REFERENCE_DUMP_FILE_PATH, 'r') as reference_dump_file:
            reference_dump = json.load(reference_dump_file)

        # Load additional JSON files
        with open('../data/airlines.json', 'r') as airlines_file:
            airlines_json = json.load(airlines_file)
        with open('../data/airports.json', 'r') as airports_file:
            airports_json = json.load(airports_file)
        with open('../data/aircraft.json', 'r') as aircraft_file:
            aircraft_json = json.load(aircraft_file)

        mqtt_service = MQTTService({
            'MQTT_CLIENT_ID': MQTT_CLIENT_ID,
            'MQTT_BROKER': MQTT_BROKER,
            'MQTT_BROKER_PORT': MQTT_BROKER_PORT,
            'MQTT_USER': MQTT_USER,
            'MQTT_PWD': MQTT_PWD
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
        server_thread = threading.Thread(target=start_server, args=(FASTAPI_PORT,))
        server_thread.start()

        reg_parser = Parser()
        previous_statistics = {}
        previous_closest_aircraft = {}

        # Ensure the storage directory exists
        storage_directory = os.path.join(os.path.dirname(__file__), '..', 'storage')
        os.makedirs(storage_directory, exist_ok=True)

        # Load unique flights data
        unique_flights_file = os.path.join(storage_directory, 'unique_flights_with_timestamps.pkl')
        unique_flights_with_timestamps = load_unique_flights_data(unique_flights_file)

        # Main program loop
        while True:
            receiver = get_receiver_data(DUMP_URL)
            
            if not receiver:
                continue
                
            flights = process_flights(receiver, reference_dump)
            flights_rich = create_flights_rich(
                flights, 
                airlines_json, 
                airports_json, 
                aircraft_json, 
                reg_parser, 
                (USER_LAT, USER_LON), 
                RADIUS, 
                defined_zone,
                ALTITUDE_UNIT,
                DISTANCE_UNIT,
                ALTITUDE_TRENDS
            )
            
            # Define time periods and calculate counts
            time_periods = get_time_periods()
            unique_flights_counts = {
                period: count_unique_flights_in_period(unique_flights_with_timestamps, start_time)
                for period, start_time in time_periods.items()
            }

            # Calculate averages
            averages = calculate_averages(unique_flights_with_timestamps, unique_flights_counts)

            # Update and publish statistics data
            statistics = get_receiver_visible(flights, unique_flights_counts, averages)
            previous_statistics = publish_and_print(
                mqtt_service, 
                MQTT_TOPIC_STATISTICS,  # Change topic to statistics
                statistics, 
                previous_statistics,  # Use previous_statistics
                STATISTICS_JSON_FILE_PATH,  # Change file path to statistics
                print_receiver_visible
            )
            
            # Process and publish closest aircraft
            closest_aircraft = get_closest_aircraft(flights_rich, (USER_LAT, USER_LON))
            previous_closest_aircraft = publish_and_print(
                mqtt_service, 
                MQTT_TOPIC_CLOSEST_AIRCRAFT, 
                closest_aircraft, 
                previous_closest_aircraft,  # Use previous_closest_aircraft
                CLOSEST_AIRCRAFT_JSON_FILE_PATH, 
                print_closest_aircraft
            )
            
            # Publish all flights data without printing
            publish_and_print(
                mqtt_service, 
                MQTT_TOPIC_FLIGHTS, 
                flights_rich, 
                None, 
                ALL_AIRCRAFT_JSON_FILE_PATH
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
    main()