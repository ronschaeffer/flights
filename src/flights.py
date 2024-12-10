# Set content type correctly in fastapi for image files
# add image files to flights dictionary with correct url

# Set content type correctly in fastapi for image files
# add image files to flights dictionary with correct url

import time
from datetime import datetime
import requests
import paho.mqtt.client as mqtt
import json
import yaml
import haversine
import shapely.geometry
from tabulate import tabulate
import subprocess
from flydenity import Parser

# Configuration Variables
TOPIC_VISIBLE = "flights/visible"
TOPIC_CLOSEST_AIRCRAFT = "flights/closest_aircraft"
DUMP_URL = "your_dump_url_here"
EXAMPLE_DUMP = "your_example_dump_structure_here"
USER_LAT = 0.0  # Your latitude
USER_LON = 0.0  # Your longitude
DISTANCE_UNIT = "km"  # Your distance unit
LAT_SOUTH = 0.0  # Your southern latitude boundary
LON_WEST = 0.0  # Your western longitude boundary
LAT_NORTH = 0.0  # Your northern latitude boundary
LON_EAST = 0.0  # Your eastern longitude boundary
RADIUS = 100.0  # Your radius
CHECK_INTERVAL = 60  # Your interval in seconds
MQTT_CLIENT_ID = "your_mqtt_client_id"
MQTT_USER = "your_mqtt_user"
MQTT_PWD = "your_mqtt_pwd"
MQTT_BROKER = "your_mqtt_broker"
MQTT_BROKER_PORT = 1883
FASTAPI_PORT = 47474  # Port number as a variable
CONFIG_FILE_PATH = "./config/config.yaml"
EXAMPLE_DUMP_FILE_PATH = "./config/planefinder_dump_structure.json"
VISIBLE_JSON_FILE_PATH = "./output/visible.json"
CLOSEST_AIRCRAFT_JSON_FILE_PATH = "./output/closest_aircraft.json"
ALL_AIRCRAFT_JSON_FILE_PATH = "./output/all_aircraft.json"
FLIGHTS_WITHIN_DEFINED_ZONE_JSON_FILE_PATH = "./output/flights_within_defined_zone.json"
FLIGHTS_WITHIN_DEFINED_RADIUS_JSON_FILE_PATH = "./output/flights_within_defined_radius.json"
FASTAPI_SCRIPT = "flights_server.py"

# Get the latest receiver dump data
def get_receiver_data(dump_url, example_dump):
    try:
        receiver = requests.get(dump_url, timeout=10).json()
    except requests.exceptions.Timeout as e:
        print("Request timeout:", e)
        return {}

    flights = {icao_id: {**{"icao_id": icao_id}, **flight_data} for icao_id, flight_data in receiver.get("aircraft", {}).items()}
    for flight in flights.values():
        flight.update({key: flight.get(key, "") for key in example_dump.get("aircraft", {}).get("icao_id", {})})
    return flights

def get_receiver_visible(flights):
    current_time_utc = int(time.time())
    current_time_readable = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "visible_aircraft": len(flights),
        "last_update_utc": current_time_utc,
        "last_update_readable": current_time_readable
    }

def publish_receiver_visible(client, visible, previous_visible_aircraft):
    if visible != previous_visible_aircraft:
        print_receiver_visible(visible)
        write_to_file(VISIBLE_JSON_FILE_PATH, visible)
        client.publish(TOPIC_VISIBLE, json.dumps(visible), qos=1, retain=True)
        return visible
    return previous_visible_aircraft

def print_receiver_visible(visible):
    headers = list(visible.keys())
    table = [[key, visible[key]] for key in headers]
    print(f"\n\nRECEIVER STATS\n\n{tabulate(table, headers=headers)}\n")

def write_to_file(filename, data):
    with open(filename, 'w') as json_file:
        json.dump(data, json_file, indent=4)

def get_closest_aircraft(flights, user_lat, user_lon, distance_unit, lat_south, lon_west, lat_north, lon_east, radius):
    zone_corners = [(lat_south, lon_west), (lat_south, lon_east), (lat_north, lon_east), (lat_north, lon_west), (lat_south, lon_west)]
    defined_zone = shapely.geometry.Polygon(zone_corners)
    user_location = (float(user_lat), float(user_lon))

    flight_list = []
    for icao_id, flight_data in flights.items():
        aircraft_lat = flight_data.get('lat')
        aircraft_lon = flight_data.get('lon')

        if aircraft_lat and aircraft_lon:
            aircraft_location = (float(aircraft_lat), float(aircraft_lon))
            distance = haversine.haversine(user_location, aircraft_location, unit=distance_unit)
            aircraft_point = shapely.geometry.Point(aircraft_location)
            flight_data.update({
                'distance': f"{round(distance, 1)} {distance_unit}",
                'distance_value': round(distance, 1),
                'distance_unit_of_measurement': distance_unit,
                'within_defined_zone': defined_zone.contains(aircraft_point),
                'within_defined_radius': distance <= radius
            })
            flight_list.append((icao_id, distance))
        else:
            flight_data.update({
                'distance': "",
                'distance_value': "",
                'distance_unit_of_measurement': "",
                'within_defined_zone': False,
                'within_defined_radius': False
            })

    flight_list.sort(key=lambda x: x[1])
    for i, (icao_id, _) in enumerate(flight_list):
        flights[icao_id]['relative_closeness'] = i + 1

    return flights

def publish_closest_aircraft(client, flights, previous_closest_aircraft):
    closest_aircraft = min(flights.values(), key=lambda x: x.get('relative_closeness', float('inf')), default=None)

    if closest_aircraft:
        closest_icao_id = closest_aircraft['icao_id']
        data_to_publish = {closest_icao_id: closest_aircraft}

        if data_to_publish != previous_closest_aircraft:
            print_closest_aircraft(data_to_publish)
            write_to_file(CLOSEST_AIRCRAFT_JSON_FILE_PATH, data_to_publish)
            client.publish(TOPIC_CLOSEST_AIRCRAFT, json.dumps(data_to_publish), qos=1, retain=True)
            return data_to_publish

    print("No change in closest aircraft data." if closest_aircraft else "No aircraft visible.")
    return previous_closest_aircraft

def print_closest_aircraft(closest_aircraft):
    headers = ["Key", "Value"]
    table = [[key, value] for aircraft_data in closest_aircraft.values() for key, value in aircraft_data.items()]
    print(tabulate(table, headers=headers, tablefmt="grid"))

def publish_flights(flights):
    write_to_file(ALL_AIRCRAFT_JSON_FILE_PATH, flights)

def write_filtered_flights_to_file(flights, filename, condition_key, condition_value):
    filtered_flights = {icao_id: flight for icao_id, flight in flights.items() if flight[condition_key] == condition_value}
    write_to_file(filename, filtered_flights)

def save_flights_within_defined_zone(flights):
    write_filtered_flights_to_file(flights, FLIGHTS_WITHIN_DEFINED_ZONE_JSON_FILE_PATH, 'within_defined_zone', True)

def save_flights_within_defined_radius(flights):
    write_filtered_flights_to_file(flights, FLIGHTS_WITHIN_DEFINED_RADIUS_JSON_FILE_PATH, 'within_defined_radius', True)

def pretty_print_flights(flights):
    print(json.dumps(flights, indent=4))

def create_flights_rich(flights, airlines_json, airports_json, aircraft_json, reg_parser):
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
    with open(CONFIG_FILE_PATH, 'r') as f:
        config = yaml.safe_load(f)
    for key, value in config.items():
        globals()[key] = value

    with open(EXAMPLE_DUMP_FILE_PATH, 'r') as f:
        example_dump = json.load(f)

    client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.username_pw_set(MQTT_USER, MQTT_PWD)
    client.reconnect_delay_set(min_delay=1, max_delay=120)
    client.connect(MQTT_BROKER, MQTT_BROKER_PORT)
    client.loop_start()

    process = subprocess.Popen(["python", FASTAPI_SCRIPT, "--port", str(FASTAPI_PORT)])

    reg_parser = Parser()
    previous_closest_aircraft = None
    previous_visible_aircraft = None

    while True:
        flights = get_receiver_data(DUMP_URL, EXAMPLE_DUMP)
        if not flights:
            continue
        flights = create_flights_rich(flights, airlines_json, airports_json, aircraft_json, reg_parser)
        visible = get_receiver_visible(flights)
        previous_visible_aircraft = publish_receiver_visible(client, visible, previous_visible_aircraft)
        closest_aircraft = get_closest_aircraft(flights, USER_LAT, USER_LON, DISTANCE_UNIT, LAT_SOUTH, LON_WEST, LAT_NORTH, LON_EAST, RADIUS)
        save_flights_within_defined_zone(flights)
        save_flights_within_defined_radius(flights)
        previous_closest_aircraft = publish_closest_aircraft(client, closest_aircraft, previous_closest_aircraft)
        publish_flights(flights)
        time.sleep(CHECK_INTERVAL)
