#!/usr/bin/env python3

# Standard library imports
import time
from datetime import datetime, timezone
import json
import os
import threading
import logging

# Third-party imports
import requests
import paho.mqtt.client as mqtt
import yaml
import haversine
import shapely.geometry
import pickle
from tabulate import tabulate
from flydenity import Parser

# Local application/library-specific imports
from flights_server import start_server

def load_configuration(config_path):
    with open(config_path, 'r') as config_file:
        config = yaml.safe_load(config_file)
    for key, value in config.items():
        globals()[key] = value

def setup_logging(log_directory, log_file_path, log_level):
    os.makedirs(log_directory, exist_ok=True)
    logging.basicConfig(filename=log_file_path, level=getattr(logging, log_level.upper(), 'INFO'),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    return logger

def get_receiver_data(dump_url, reference_dump):
    logger.info("Fetching receiver data from URL: %s", dump_url)
    try:
        response = requests.get(dump_url, timeout=10)
        response.raise_for_status()
        receiver = response.json()
        logger.info("Successfully fetched receiver data")
        return receiver
    except requests.exceptions.RequestException as e:
        logger.error("Error fetching receiver data: %s", e)
        return {}

def process_flights(receiver, reference_dump):
    flights = {
        icao_id: {
            **{"icao_id": icao_id},
            **flight_data,
            **{key: flight_data.get(key, "") for key in reference_dump.get("aircraft", {}).get("icao_id", {})}
        }
        for icao_id, flight_data in receiver.get("aircraft", {}).items()
    }
    return flights

def get_receiver_visible(flights):
    logger.info("Processing visible flights data")
    current_time_utc = int(time.time())
    current_time_readable = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "visible_aircraft": len(flights),
        "last_update_utc": current_time_utc,
        "last_update_readable": current_time_readable
    }

def publish_receiver_visible(mqtt_client, visible, previous_visible_aircraft):
    logger.info("Publishing visible aircraft data")
    if visible != previous_visible_aircraft:
        print_receiver_visible(visible)
        write_to_file(VISIBLE_JSON_FILE_PATH, visible)
        mqtt_client.publish(MQTT_TOPIC_VISIBLE, json.dumps(visible), qos=1, retain=True)
        return visible
    return previous_visible_aircraft

def print_receiver_visible(visible):
    logger.info("Printing visible aircraft data")
    print(f"\n\nRECEIVER STATS\n")
    table = [[key, value] for key, value in visible.items()]
    print(tabulate(table, headers=["Key", "Value"]))
    print("\n")

#######

def write_to_file(filename, data):
    logger.info("Writing data to file: %s", filename)
    with open(filename, 'w') as json_file:
        json.dump(data, json_file, indent=4)

def get_closest_aircraft(flights_rich, user_location):
    logger.info("Getting closest aircraft to user location")
    closest_aircraft = None
    min_distance = float('inf')
    for flight in flights_rich.values():
        if 'lat' in flight and 'lon' in flight:
            try:
                lat = float(flight['lat'])
                lon = float(flight['lon'])
                distance = haversine.haversine(user_location, (lat, lon))
                if distance < min_distance:
                    min_distance = distance
                    closest_aircraft = {flight['icao_id']: flight}
            except ValueError as e:
                logger.error("Invalid latitude or longitude for flight: %s, error: %s", flight, e)
    return closest_aircraft

def publish_closest_aircraft(mqtt_client, closest_aircraft, previous_closest_aircraft):
    logger.info("Publishing closest aircraft data")
    if closest_aircraft != previous_closest_aircraft:
        print_closest_aircraft(closest_aircraft)
        write_to_file(CLOSEST_AIRCRAFT_JSON_FILE_PATH, closest_aircraft)
        mqtt_client.publish(MQTT_TOPIC_CLOSEST_AIRCRAFT, json.dumps(closest_aircraft), qos=1, retain=True)
        return closest_aircraft
    return previous_closest_aircraft

def print_closest_aircraft(closest_aircraft):
    logger.info("Printing closest aircraft data")
    print(f"CLOSEST AIRCRAFT\n")
    for key, value in closest_aircraft.items():
        print(tabulate(value.items(), headers=["Key", "Value"]))
    print("\n\n")

def publish_flights(mqtt_client, flights):
    logger.info("Publishing all flights data")
    mqtt_client.publish(MQTT_TOPIC_FLIGHTS, json.dumps(flights), qos=1, retain=True)

def write_filtered_flights_to_file(file_path, flights, filter_func):
    logger.info("Writing filtered flights data to file: %s", file_path)
    filtered_flights = {icao_id: flight for icao_id, flight in flights.items() if filter_func(flight)}
    write_to_file(file_path, filtered_flights)

def save_flights_within_defined_zone(file_path, flights, zone):
    logger.info("Saving flights within defined zone to file: %s", file_path)
    def filter_func(flight):
        if 'lat' in flight and 'lon' in flight:
            try:
                lat = float(flight['lat'])
                lon = float(flight['lon'])
                point = shapely.geometry.Point(lat, lon)
                return zone.contains(point)
            except ValueError as e:
                logger.error("Invalid latitude or longitude for flight: %s, error: %s", flight, e)
        return False

    write_filtered_flights_to_file(file_path, flights, filter_func)

def save_flights_within_defined_radius(file_path, flights, center, radius):
    logger.info("Saving flights within defined radius to file: %s", file_path)
    def filter_func(flight):
        if 'lat' in flight and 'lon' in flight:
            try:
                lat = float(flight['lat'])
                lon = float(flight['lon'])
                distance = haversine.haversine(center, (lat, lon))
                return distance <= radius
            except ValueError as e:
                logger.error("Invalid latitude or longitude for flight: %s, error: %s", flight, e)
        return False

    write_filtered_flights_to_file(file_path, flights, filter_func)

def pretty_print_flights(flights):
    logger.info("Pretty printing flights data")
    print(tabulate(flights.values(), headers="keys"))

def create_flights_rich(flights, airlines_json, airports_json, aircraft_json, reg_parser, user_location, radius, defined_zone):
    """
    Enriches flight data with information from airlines, airports, and aircraft databases.

    Args:
        flights (dict): A dictionary of flight data.
        airlines_json (list): A list of airline data.
        airports_json (dict): A dictionary of airport data.
        aircraft_json (list): A list of aircraft data.
        reg_parser (object): An object to parse aircraft registrations.
        user_location (tuple): The user's latitude and longitude.
        radius (float): The radius around the user's location.
        defined_zone (shapely.geometry.Polygon): The defined geographical zone.

    Returns:
        dict: A dictionary of enriched flight data.
    """
    logger.info("Creating enriched flights data")

    # Create dictionaries for faster lookups
    airlines_by_icao = {airline["icao_code"]: airline for airline in airlines_json if airline["icao_code"]}
    airlines_by_iata = {airline["iata_code"]: airline for airline in airlines_json if airline["iata_code"]}
    aircraft_by_type = {aircraft["icao_type_code"]: aircraft for aircraft in aircraft_json}

    def get_airport_info(code):
        """Retrieves airport information from airports_json."""
        airport = airports_json.get(code, {})
        return {
            "name": airport.get("name", ""),
            "city": airport.get("city", ""),
            "country_code": airport.get("country_code", "").upper(),
            "airport_code": code
        }

    flights_rich = {}
    flights_with_location = []

    for flight_id, flight_data in flights.items():
        flight_rich_data = {}

        # Add basic flight information
        for key in ("icao_id", "callsign", "flightno", "squawk", "reg", "category", "type"):
            flight_rich_data[key] = flight_data.get(key, "")

        # Parse aircraft registration
        reg = flight_data.get("reg", "")
        if reg:
            parsed_reg = reg_parser.parse(reg)
            if parsed_reg:
                flight_rich_data.update({
                    "reg_country_name": parsed_reg.get("nation", ""),
                    "reg_country_code": parsed_reg.get("iso2", "")
                })

        # Find airline information
        callsign = flight_data.get("callsign", "")
        airline = airlines_by_icao.get(callsign[:3]) if callsign else None
        if not airline:
            flightno = flight_data.get("flightno", "")
            airline = airlines_by_iata.get(flightno[:2]) if flightno else None

        if airline:
            flight_rich_data.update({
                "airline": airline.get("name", ""),
                "airline_country": airline.get("country", ""),
                "airline_callsign": airline.get("airline_callsign", ""),
                "airline_icao": airline.get("icao_code", ""),
                "airline_iata": airline.get("iata_code", "")
            })

        # Parse route information
        route = flight_data.get("route", "")
        if route:
            try:
                origin, *via, destination = route.split("-")
                flight_rich_data.update({
                    "origin": f"{get_airport_info(origin)['city']} {origin}",
                    "origin_airport": get_airport_info(origin)['name'],
                    "origin_airport_code": origin,
                    "origin_city": get_airport_info(origin)['city'],
                    "origin_country_code": get_airport_info(origin)['country_code'],
                    "destination": f"{get_airport_info(destination)['city']} {destination}",
                    "destination_airport": get_airport_info(destination)['name'],
                    "destination_airport_code": destination,
                    "destination_city": get_airport_info(destination)['city'],
                    "destination_country_code": get_airport_info(destination)['country_code']
                })
                if via:
                    via_point = via[0]  # Assuming only one via point
                    flight_rich_data.update({
                        "via": f"{get_airport_info(via_point)['city']} {via_point}",
                        "via_airport": get_airport_info(via_point)['name'],
                        "via_airport_code": via_point,
                        "via_city": get_airport_info(via_point)['city'],
                        "via_country_code": get_airport_info(via_point)['country_code']
                    })
            except (ValueError, IndexError) as e:
                logger.warning("Error parsing route for flight: %s, route: %s, error: %s", flight_id, route, e)

        # Calculate distance and location information
        try:
            lat_str = flight_data.get("lat")
            lon_str = flight_data.get("lon")
            if lat_str and lon_str:
                try:
                    lat = float(lat_str)
                    lon = float(lon_str)
                    distance = haversine.haversine(user_location, (lat, lon))
                    flights_with_location.append((distance, flight_id))
                    flight_rich_data.update({
                        "lat": lat,
                        "lon": lon,
                        "distance": f"{distance:.1f}mi",
                        "distance_value": f"{distance:.1f}",
                        "distance_unit_of_measurement": "mi",
                        "within_defined_radius": distance <= radius,
                        "within_defined_zone": defined_zone.contains(shapely.geometry.Point(lon, lat))
                    })
                except ValueError as e:
                    logger.error("Error converting latitude/longitude to float for flight: %s, lat: %s, lon: %s, error: %s", flight_id, lat_str, lon_str, e)
            else:
                logger.warning("Missing latitude/longitude for flight: %s", flight_id)
        except (ValueError, TypeError) as e:
            logger.error("Error processing latitude/longitude for flight: %s, error: %s", flight_id, e)

        # Process altitude information
        try:
            altitude_str = flight_data.get("altitude", "")
            if altitude_str:

                try:
                    altitude_value = int(altitude_str)
                    # Convert altitude to meters if needed
                    if ALTITUDE_UNIT.lower() in ["m", "meters"]:
                        altitude_str = str(int(float(altitude_str) * 0.3048)) # Convert feet to meters and back to string
                    try:
                        vert_rate = int(float(flight_data.get("vert_rate", 0)))
                        altitude_trend_symbol = "↗" if vert_rate > 0 else "↘" if vert_rate < 0 else "→"
                    except (ValueError, TypeError):
                        vert_rate = ""
                        altitude_trend_symbol = ""
                    flight_rich_data.update({
                        "altitude": f"{altitude_str}{ALTITUDE_UNIT}",
                        "altitude_value": f"{altitude_str}",  # String
                        "altitude_unit_of_measurement": ALTITUDE_UNIT,
                        "altitude_trend_symbol": altitude_trend_symbol,
                        "altitude_with_trend": f"{altitude_str}{ALTITUDE_UNIT} {altitude_trend_symbol}"
                    })          
                except ValueError as e:
                    # Try to sanitize the altitude string before converting to int
                    try:
                        altitude_str = ''.join([c for c in altitude_str if c.isdigit()])
                        altitude_value = int(altitude_str) if altitude_str else 0
                        logger.warning("Sanitized altitude for flight: %s, original: %s, sanitized: %s", flight_id, flight_data.get("altitude"), altitude_str)
                        # Convert altitude to meters if needed
                        if ALTITUDE_UNIT.lower() in ["m", "meters"]:
                            altitude_str = str(int(float(altitude_str) * 0.3048)) # Convert feet to meters and back to string
                        try:
                            vert_rate = int(float(flight_data.get("vert_rate", 0)))
                            altitude_trend_symbol = "↗" if vert_rate > 0 else "↘" if vert_rate < 0 else "→"
                        except (ValueError, TypeError):
                            vert_rate = ""
                            altitude_trend_symbol = ""
                        flight_rich_data.update({
                            "altitude": f"{altitude_str}{ALTITUDE_UNIT}",
                            "altitude_value": f"{altitude_str}",  # String
                            "altitude_unit_of_measurement": ALTITUDE_UNIT,
                            "altitude_trend_symbol": altitude_trend_symbol,
                            "altitude_with_trend": f"{altitude_str}{ALTITUDE_UNIT} {altitude_trend_symbol}"
                        })
                    except ValueError as e:
                        logger.error("Error converting altitude to int for flight: %s, altitude: %s, error: %s", flight_id, flight_data.get("altitude"), e)







                try:
                    altitude_value = int(altitude_str)
                    # ... (altitude conversion and update flight_rich_data) ...
                    if ALTITUDE_UNIT.lower() in ["m", "meters"]:
                        altitude_str = str(int(float(altitude_str) * 0.3048)) # Convert feetto meters and back to string
                    try:
                        vert_rate = int(float(flight_data.get("vert_rate", 0)))
                        altitude_trend_symbol = "↗" if vert_rate > 0 else "↘" if vert_rate < 0 else "→"
                    except (ValueError, TypeError):
                        vert_rate = ""
                        altitude_trend_symbol = ""
                    flight_rich_data.update({
                        "altitude": f"{altitude_str}{ALTITUDE_UNIT}",
                        "altitude_value": f"{altitude_str}",  # String
                        "altitude_unit_of_measurement": ALTITUDE_UNIT,
                        "altitude_trend_symbol": altitude_trend_symbol,
                        "altitude_with_trend": f"{altitude_str}{ALTITUDE_UNIT} {altitude_trend_symbol}"
                    })          
                except ValueError as e:
                    # Try to sanitize the altitude string before converting to int
                    try:
                        altitude_str = ''.join([c for c in altitude_str if c.isdigit()])
                        altitude_value = int(altitude_str) if altitude_str else 0
                        logger.warning("Sanitized altitude for flight: %s, original: %s, sanitized: %s", flight_id, flight_data.get("altitude"), altitude_str)
                        # ... (altitude conversion and update flight_rich_data) ...
                    except ValueError as e:
                        logger.error("Error converting altitude to int for flight: %s, altitude: %s, error: %s", flight_id, flight_data.get("altitude"), e)
            else:
                logger.warning("Empty altitude for flight: %s", flight_id)
        except (ValueError, TypeError) as e:
            logger.error("Error processing altitude for flight: %s, error: %s", flight_id, e)

        # Add aircraft model information
        aircraft_type = flight_data.get("type")
        if aircraft_type and aircraft_type in aircraft_by_type:
            flight_rich_data["aircraft_model"] = aircraft_by_type[aircraft_type].get("aircraft_model", "")

        # Add remaining flight data
        for key in (
            "selected_altitude", "barometer", "heading", "magnetic_heading",
            "target_heading", "vert_rate", "speed", "indicated_air_speed",
            "true_air_speed", "ground_speed", "mach", "polar_distance",
            "polar_bearing", "roll_angle", "track_angle", "is_on_ground",
            "wind_speed", "wind_direction", "oat", "last_seen_time",
            "pos_update_time", "bds40_seen_time", "bds50_seen_time",
            "bds60_seen_time", "bds62_seen_time", "is_mlat", "age"
        ):
            flight_rich_data[key] = flight_data.get(key, "")

        # Format last_seen_time
        try:
            last_seen_time = int(flight_data.get("last_seen_time", 0))
            flight_rich_data["last_seen_time_readable"] = datetime.fromtimestamp(last_seen_time).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            logger.warning("Invalid last_seen_time for flight: %s", flight_id)

        flights_rich[flight_id] = flight_rich_data  # Add all flights to flights_rich

    # Calculate relative closeness for flights with location data
    flights_with_location.sort()
    for i, (_, flight_id) in enumerate(flights_with_location):
        flights_rich[flight_id]["relative_closeness"] = i + 1

    return flights_rich

# Main program
if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), '../config/config.yaml')
    load_configuration(config_path)

    log_directory = os.path.join(os.path.dirname(__file__), '../logs')
    log_file_path = os.path.join(log_directory, 'flights.log')
    logger = setup_logging(log_directory, log_file_path, LOG_LEVEL)

    logger.info("Starting flights.py script")

    with open(REFERENCE_DUMP_FILE_PATH, 'r') as reference_dump_file:
        reference_dump = json.load(reference_dump_file)

    # Load additional JSON files
    with open('../data/airlines.json', 'r') as airlines_file:
        airlines_json = json.load(airlines_file)
    with open('../data/airports.json', 'r') as airports_file:
        airports_json = json.load(airports_file)
    with open('../data/aircraft.json', 'r') as aircraft_file:
        aircraft_json = json.load(aircraft_file)

    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PWD)
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=120)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"\nMQTT: Connected to broker as: {MQTT_CLIENT_ID}")

    mqtt_client.on_connect = on_connect
    mqtt_client.connect(MQTT_BROKER, MQTT_BROKER_PORT)
    mqtt_client.loop_start()

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
    previous_visible_aircraft = {}
    previous_closest_aircraft = {}

    while True:
        receiver = get_receiver_data(DUMP_URL, reference_dump)
        if not receiver:
            continue
        flights = process_flights(receiver, reference_dump)
        flights_rich = create_flights_rich(flights, airlines_json, airports_json, aircraft_json, reg_parser, (USER_LAT, USER_LON), RADIUS, defined_zone)
        visible = get_receiver_visible(flights)
        previous_visible_aircraft = publish_receiver_visible(mqtt_client, visible, previous_visible_aircraft)
        closest_aircraft = get_closest_aircraft(flights_rich, (USER_LAT, USER_LON))
        save_flights_within_defined_zone(FLIGHTS_WITHIN_DEFINED_ZONE_JSON_FILE_PATH, flights_rich, defined_zone)
        save_flights_within_defined_radius(FLIGHTS_WITHIN_DEFINED_RADIUS_JSON_FILE_PATH, flights_rich, (USER_LAT, USER_LON), RADIUS)
        previous_closest_aircraft = publish_closest_aircraft(mqtt_client, closest_aircraft, previous_closest_aircraft)
        publish_flights(mqtt_client, flights_rich)
        
        time.sleep(CHECK_INTERVAL)

#flights = get_receiver_data(DUMP_URL, reference_dump)
#if flights:
#    print(flights)
#    flights_rich = create_flights_rich(flights, airlines_json, airports_json, aircraft_json, reg_parser, (USER_LAT, USER_LON), RADIUS, defined_zone)
#    visible = get_receiver_visible(flights)
#    previous_visible_aircraft = publish_receiver_visible(mqtt_client, visible, previous_visible_aircraft)
#    closest_aircraft = get_closest_aircraft(flights_rich, (USER_LAT, USER_LON))
#    save_flights_within_defined_zone(FLIGHTS_WITHIN_DEFINED_ZONE_JSON_FILE_PATH, flights_rich, defined_zone)
#    save_flights_within_defined_radius(FLIGHTS_WITHIN_DEFINED_RADIUS_JSON_FILE_PATH, flights_rich, (USER_LAT, USER_LON), RADIUS)
#    previous_closest_aircraft = publish_closest_aircraft(mqtt_client, closest_aircraft, previous_closest_aircraft)
#    publish_flights(mqtt_client, flights_rich)