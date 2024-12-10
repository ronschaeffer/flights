#!/usr/bin/env python3

# Standard library imports
import time
from datetime import datetime
import json
import os
import logging

# Third-party imports
import requests
import paho.mqtt.client as mqtt
import yaml
import haversine
import shapely.geometry
from tabulate import tabulate
from flydenity import Parser

# Local application/library-specific imports
from flights_server_module import start_server

# Configure logging
logging.basicConfig(filename='flights.log', level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_receiver_data(dump_url, example_dump):
    """
    Fetch the latest receiver dump data from a given URL and process it into a dictionary of flights.

    Args:
        dump_url (str): URL to fetch the receiver dump data.
        example_dump (dict): Example dump data to fill missing keys.

    Returns:
        dict: Processed flights data.
    """
    try:
        response = requests.get(dump_url, timeout=10)
        response.raise_for_status()
        receiver = response.json()
    except requests.exceptions.RequestException as e:
        logger.error("Error fetching receiver data: %s", e)
        return {}

    flights = {icao_id: {**{"icao_id": icao_id}, **flight_data} for icao_id, flight_data in receiver.get("aircraft", {}).items()}
    for flight in flights.values():
        flight.update({key: flight.get(key, "") for key in example_dump.get("aircraft", {}).get("icao_id", {})})
    return flights

def get_receiver_visible(flights):
    """
    Process and return visible flights data.

    Args:
        flights (dict): Dictionary of flights data.

    Returns:
        dict: Processed visible flights data.
    """
    current_time_utc = int(time.time())
    current_time_readable = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "visible_aircraft": len(flights),
        "last_update_utc": current_time_utc,
        "last_update_readable": current_time_readable
    }

def publish_receiver_visible(mqtt_client, visible, previous_visible_aircraft):
    """
    Publish the visible aircraft data if it has changed.

    Args:
        mqtt_client (mqtt.Client): MQTT client instance.
        visible (dict): Current visible aircraft data.
        previous_visible_aircraft (dict): Previous visible aircraft data.

    Returns:
        dict: Updated previous visible aircraft data.
    """
    if visible != previous_visible_aircraft:
        print_receiver_visible(visible)
        write_to_file(VISIBLE_JSON_FILE_PATH, visible)
        mqtt_client.publish(MQTT_TOPIC_VISIBLE, json.dumps(visible), qos=1, retain=True)
        return visible
    return previous_visible_aircraft

def print_receiver_visible(visible):
    """
    Print the visible aircraft data.

    Args:
        visible (dict): Visible aircraft data.
    """
    headers = list(visible.keys())
    table = [[key, visible[key]] for key in headers]
    print(f"\n\nRECEIVER STATS\n\n{tabulate(table, headers=headers)}\n")

def write_to_file(filename, data):
    """
    Write data to a file.

    Args:
        filename (str): Path to the file.
        data (dict): Data to write.
    """
    with open(filename, 'w') as json_file:
        json.dump(data, json_file, indent=4)

def get_closest_aircraft(flights, user_location):
    """
    Get the closest aircraft to the user's location.

    Args:
        flights (dict): Dictionary of flights data.
        user_location (tuple): User's location as (latitude, longitude).

    Returns:
        dict: Closest aircraft data.
    """
    closest_aircraft = None
    min_distance = float('inf')
    for flight in flights.values():
        if 'lat' in flight and 'lon' in flight:
            distance = haversine.haversine(user_location, (flight['lat'], flight['lon']))
            if distance < min_distance:
                min_distance = distance
                closest_aircraft = flight
    return closest_aircraft

def publish_closest_aircraft(mqtt_client, closest_aircraft, previous_closest_aircraft):
    """
    Publish the closest aircraft data if it has changed.

    Args:
        mqtt_client (mqtt.Client): MQTT client instance.
        closest_aircraft (dict): Closest aircraft data.
        previous_closest_aircraft (dict): Previous closest aircraft data.

    Returns:
        dict: Updated previous closest aircraft data.
    """
    if closest_aircraft != previous_closest_aircraft:
        print_closest_aircraft(closest_aircraft)
        write_to_file(CLOSEST_AIRCRAFT_JSON_FILE_PATH, closest_aircraft)
        mqtt_client.publish(MQTT_TOPIC_CLOSEST_AIRCRAFT, json.dumps(closest_aircraft), qos=1, retain=True)
        return closest_aircraft
    return previous_closest_aircraft

def print_closest_aircraft(closest_aircraft):
    """
    Print the closest aircraft data.

    Args:
        closest_aircraft (dict): Closest aircraft data.
    """
    print(tabulate(closest_aircraft.items(), headers=["Key", "Value"]))

def publish_flights(mqtt_client, flights):
    """
    Publish all flights data.

    Args:
        mqtt_client (mqtt.Client): MQTT client instance.
        flights (dict): Dictionary of flights data.
    """
    mqtt_client.publish(MQTT_TOPIC_FLIGHTS, json.dumps(flights), qos=1, retain=True)

def write_filtered_flights_to_file(file_path, flights, filter_func):
    """
    Write filtered flights data to a file.

    Args:
        file_path (str): Path to the file.
        flights (dict): Dictionary of flights data.
        filter_func (function): Function to filter flights.
    """
    filtered_flights = {icao_id: flight for icao_id, flight in flights.items() if filter_func(flight)}
    write_to_file(file_path, filtered_flights)

def save_flights_within_defined_zone(file_path, flights, zone):
    """
    Save flights within a defined zone to a file.

    Args:
        file_path (str): Path to the file.
        flights (dict): Dictionary of flights data.
        zone (shapely.geometry.Polygon): Defined zone as a polygon.
    """
    def filter_func(flight):
        if 'lat' in flight and 'lon' in flight:
            point = shapely.geometry.Point(flight['lat'], flight['lon'])
            return zone.contains(point)
        return False

    write_filtered_flights_to_file(file_path, flights, filter_func)

def save_flights_within_defined_radius(file_path, flights, center, radius):
    """
    Save flights within a defined radius to a file.

    Args:
        file_path (str): Path to the file.
        flights (dict): Dictionary of flights data.
        center (tuple): Center of the radius as (latitude, longitude).
        radius (float): Radius in kilometers.
    """
    def filter_func(flight):
        if 'lat' in flight and 'lon' in flight:
            distance = haversine.haversine(center, (flight['lat'], flight['lon']))
            return distance <= radius
        return False

    write_filtered_flights_to_file(file_path, flights, filter_func)

def pretty_print_flights(flights):
    """
    Pretty print flights data.

    Args:
        flights (dict): Dictionary of flights data.
    """
    print(tabulate(flights.values(), headers="keys"))

def create_flights_rich(flights, airlines_json, airports_json, aircraft_json, reg_parser):
    """
    Create enriched flights data with additional information.

    Args:
        flights (dict): Dictionary of flights data.
        airlines_json (dict): Additional information about airlines.
        airports_json (dict): Additional information about airports.
        aircraft_json (dict): Additional information about aircraft.
        reg_parser (Parser): Registration parser.

    Returns:
        dict: Enriched flights data.
    """
    def get_airport_info(code):
        airport = airports_json.get(code, {})
        return {
            "name": airport.get("name", ""),
            "city": airport.get("city", ""),
            "country_code": airport.get("country_code", "").upper(),
            "airport_code": code
        }

    flights_rich = {}
    for flight_id, flight_data in flights.items():
        flight_rich_data = {
            "icao_id": flight_data.get("icao_id", ""),
            "callsign": flight_data.get("callsign", ""),
            "flightno": flight_data.get("flightno", ""),
            "squawk": flight_data.get("squawk", ""),
            "reg": flight_data.get("reg", "")
        }

        reg = flight_data.get("reg", "")
        if reg:
            parsed_reg = reg_parser.parse(reg)
            if parsed_reg:
                flight_rich_data.update({
                    "reg_country_name": parsed_reg["nation"],
                    "reg_country_code": parsed_reg["iso2"]
                })
        else:
            flight_rich_data.update({
                "reg_country_name": "",
                "reg_country_code": ""
            })

        callsign = flight_data.get("callsign", "")
        airline = next((airline for airline in airlines_json if airline["icao_code"].startswith(callsign[:3])), None)
        if not airline:
            flightno = flight_data.get("flightno", "")
            airline = next((airline for airline in airlines_json if airline["iata_code"].startswith(flightno[:2])), None)

        flight_rich_data.update({
            "airline": airline.get("name", "") if airline else "",
            "airline_country": airline.get("country", "") if airline else "",
            "airline_callsign": airline.get("airline_callsign", "") if airline else "",
            "airline_icao": airline.get("icao_code", "") if airline else "",
            "airline_iata": airline.get("iata_code", "") if airline else ""
        })

        route = flight_data.get("route", "")
        if route:
            substrings = route.split("-")
            origin_info = get_airport_info(substrings[0])
            flight_rich_data.update({
                "origin": f"{origin_info['city']} {origin_info['airport_code']}",
                "origin_airport": origin_info['name'],
                "origin_airport_code": origin_info['airport_code'],
                "origin_city": origin_info['city'],
                "origin_country_code": origin_info['country_code']
            })

            destination_info = get_airport_info(substrings[-1])
            flight_rich_data.update({
                "destination": f"{destination_info['city']} {destination_info['airport_code']}",
                "destination_airport": destination_info['name'],
                "destination_airport_code": destination_info['airport_code'],
                "destination_city": destination_info['city'],
                "destination_country_code": destination_info['country_code']
            })

            if len(substrings) == 3:
                via_info = get_airport_info(substrings[1])
                flight_rich_data.update({
                    "via": f"{via_info['city']} {via_info['airport_code']}",
                    "via_airport": via_info['name'],
                    "via_airport_code": via_info['airport_code'],
                    "via_city": via_info['city'],
                    "via_country_code": via_info['country_code']
                })
            else:
                flight_rich_data.update({
                    "via": "",
                    "via_airport": "",
                    "via_airport_code": "",
                    "via_city": "",
                    "via_country_code": ""
                })
        else:
            flight_rich_data.update({
                "origin": "",
                "origin_airport": "",
                "origin_airport_code": "",
                "origin_city": "",
                "origin_country_code": "",
                "destination": "",
                "destination_airport": "",
                "destination_airport_code": "",
                "destination_city": "",
                "destination_country_code": "",
                "via": "",
                "via_airport": "",
                "via_airport_code": "",
                "via_city": "",
                "via_country_code": ""
            })

        flight_rich_data.update({
            "category": flight_data.get("category", ""),
            "type": flight_data.get("type", ""),
            "aircraft_model": next((aircraft["aircraft_model"] for aircraft in aircraft_json if aircraft["icao_type_code"] == flight_data.get("type", "")), ""),
            "lat": flight_data.get("lat", ""),
            "lon": flight_data.get("lon", ""),
            "relative_closeness": flight_data.get("relative_closeness", ""),
            "distance": flight_data.get("distance", ""),
            "distance_value": flight_data.get("distance_value", ""),
            "distance_unit_of_measurement": flight_data.get("distance_unit_of_measurement", ""),
            "within_defined_radius": flight_data.get("within_defined_radius", ""),
            "within_defined_zone": flight_data.get("within_defined_zone", ""),
            "altitude": flight_data.get("altitude", ""),
            "selected_altitude": flight_data.get("selected_altitude", ""),
            "barometer": flight_data.get("barometer", ""),
            "heading": flight_data.get("heading", ""),
            "magnetic_heading": flight_data.get("magnetic_heading", ""),
            "target_heading": flight_data.get("target_heading", ""),
            "vert_rate": flight_data.get("vert_rate", ""),
            "speed": flight_data.get("speed", ""),
            "indicated_air_speed": flight_data.get("indicated_air_speed", ""),
            "true_air_speed": flight_data.get("true_air_speed", ""),
            "ground_speed": flight_data.get("ground_speed", ""),
            "mach": flight_data.get("mach", ""),
            "polar_distance": flight_data.get("polar_distance", ""),
            "polar_bearing": flight_data.get("polar_bearing", ""),
            "roll_angle": flight_data.get("roll_angle", ""),
            "track_angle": flight_data.get("track_angle", ""),
            "is_on_ground": flight_data.get("is_on_ground", ""),
            "wind_speed": flight_data.get("wind_speed", ""),
            "wind_direction": flight_data.get("wind_direction", ""),
            "oat": flight_data.get("oat", ""),
            "last_seen_time": flight_data.get("last_seen_time", ""),
            "last_seen_time_readable": datetime.fromtimestamp(int(flight_data.get("last_seen_time", 0))).strftime('%Y-%m-%d %H:%M:%S') if flight_data.get("last_seen_time", "") else "",
            "pos_update_time": flight_data.get("pos_update_time", ""),
            "bds40_seen_time": flight_data.get("bds40_seen_time", ""),
            "bds50_seen_time": flight_data.get("bds50_seen_time", ""),
            "bds60_seen_time": flight_data.get("bds60_seen_time", ""),
            "bds62_seen_time": flight_data.get("bds62_seen_time", ""),
            "is_mlat": flight_data.get("is_mlat", ""),
            "age": flight_data.get("age", "")
        })

        flights_rich[flight_id] = flight_rich_data

    return flights_rich

# Main program
if __name__ == "__main__":
    with open(CONFIG_FILE_PATH, 'r') as config_file:
        config = yaml.safe_load(config_file)
    for key, value in config.items():
        globals()[key] = value

    with open(EXAMPLE_DUMP_FILE_PATH, 'r') as example_dump_file:
        example_dump = json.load(example_dump_file)

    mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PWD)
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=120)
    mqtt_client.connect(MQTT_BROKER, MQTT_BROKER_PORT)
    mqtt_client.loop_start()

    previous_visible_aircraft = {}
    previous_closest_aircraft = {}

    while True:
        flights = get_receiver_data(DUMP_URL, example_dump)
        if not flights:
            continue
        flights = create_flights_rich(flights, airlines_json, airports_json, aircraft_json, reg_parser)
        visible = get_receiver_visible(flights)
        previous_visible_aircraft = publish_receiver_visible(mqtt_client, visible, previous_visible_aircraft)
        closest_aircraft = get_closest_aircraft(flights, (USER_LAT, USER_LON))
        save_flights_within_defined_zone(FLIGHTS_WITHIN_DEFINED_ZONE_JSON_FILE_PATH, flights, defined_zone)
        save_flights_within_defined_radius(FLIGHTS_WITHIN_DEFINED_RADIUS_JSON_FILE_PATH, flights, (USER_LAT, USER_LON), RADIUS)
        previous_closest_aircraft = publish_closest_aircraft(mqtt_client, closest_aircraft, previous_closest_aircraft)
        publish_flights(mqtt_client, flights)
        time.sleep(CHECK_INTERVAL)
