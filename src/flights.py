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
from sys import exit
from flydenity import Parser
import subprocess
#import icaoaircrft

# Get the latest receiver dump data
def get_receiver_data():
    receiver = {}
    flights = {}

    try:
        receiver = requests.get(dump_url, timeout=10).json()
    except requests.exceptions.Timeout as e:
        print("Request timeout:", e)

    flights = dict(receiver["aircraft"])

    for icao_id, flight_data in flights.items():
        flight = {"icao_id": icao_id}
        for key, value in example_dump["aircraft"]["icao_id"].items():
            if key in flight_data:
                flight[key] = flight_data[key]
            else:
                flight[key] = ""
        flights[icao_id] = flight

    return flights

def get_receiver_visible():
    current_time_utc = int(time.time())
    current_time_readable = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    receiver_visible = {"visible_aircraft": len(flights), "last_update_utc": current_time_utc, "last_update_readable": current_time_readable}
    
    return receiver_visible

def publish_receiver_visible(visible):
    global previous_visible_aircraft  # Access the global variable to track state
    
    if visible != previous_visible_aircraft:  # Perform actions only if visible have changed
        print_receiver_visible(visible)
        write_receiver_visible_to_file(visible)
        client.publish("flights/visible", json.dumps(visible), qos=1, retain=True)
        previous_visible_aircraft = visible  # Update the previously published visible

def print_receiver_visible(visible):
    headers = list(visible.keys())
    table = [[key, visible[key]] for key in headers]
    print(f"\n\nRECEIVER STATS\n\n{tabulate(table, headers=headers)}\n")

def write_receiver_visible_to_file(visible):
    with open('./output/visible.json', 'w') as json_file:
        json.dump(visible, json_file, indent=4)

def get_closest_aircraft():
    closest_distance = None
    closest_aircraft = None
    relative_distance = 1
    
    zone_corners = [(lat_south, lon_west), (lat_south, lon_east), (lat_north, lon_east), (lat_north, lon_west), (lat_south, lon_west)]
    defined_zone = shapely.geometry.Polygon(zone_corners)
    
    flight_list = []
    for icao_id in flights:
        aircraft_lat = flights[icao_id].get('lat')
        aircraft_lon = flights[icao_id].get('lon')
        
        if aircraft_lat and aircraft_lon and aircraft_lat != "" and aircraft_lon != "":
            aircraft_location = (float(aircraft_lat), float(aircraft_lon))
            user_location = (float(user_lat), float(user_lon))
            
            distance = haversine.haversine(user_location, aircraft_location, unit=distance_unit)
            aircraft_point = shapely.geometry.Point(aircraft_location)
            
            flight_list.append((icao_id, distance))
            
            flights[icao_id]['distance'] = f"{round(distance, 1)} {distance_unit}"     
            flights[icao_id]['distance_value'] = f"{round(distance, 1)}"
            flights[icao_id]['distance_unit_of_measurement'] = f"{distance_unit}"
            flights[icao_id]['within_defined_zone'] = defined_zone.contains(aircraft_point)
            flights[icao_id]['within_defined_radius'] = distance <= radius
        else:
            flights[icao_id]['distance'] = ""
            flights[icao_id]['distance_value'] = ""
            flights[icao_id]['distance_unit_of_measurement'] = ""
            flights[icao_id]['within_defined_zone'] = ""
            flights[icao_id]['within_defined_radius'] = ""
    
    flight_list.sort(key=lambda x: x[1])
    for i, (icao_id, distance) in enumerate(flight_list):
        flights[icao_id]['relative_closeness'] = i + 1
        
    return flights


def publish_closest_aircraft(flights):
    global previous_closest_aircraft

    closest_aircraft = None
    closest_icao_id = None

    # Loop to find the closest aircraft
    for icao_id in flights:
        if closest_aircraft is None or flights[icao_id]['relative_closeness'] == 1:
            closest_aircraft = flights[icao_id]
            closest_icao_id = icao_id

    if closest_aircraft is not None:
        # Create a dictionary with icao_id as the key and its details as the value
        data_to_publish = {closest_icao_id: closest_aircraft}

        # Check if the data has changed
        if data_to_publish != previous_closest_aircraft or data_to_publish == previous_closest_aircraft:
        # if data_to_publish != previous_closest_aircraft:
            print_closest_aircraft(data_to_publish)
            write_closest_aircraft_to_file(data_to_publish)

            # Publish the data if it has changed
            client.publish("flights/closest_aircraft", json.dumps(data_to_publish), qos=1, retain=True)

            # Update previous_closest_aircraft with the new data
            previous_closest_aircraft = data_to_publish
        else:
            print("No change in closest aircraft data.")
    else:
        print("No aircraft visible.")


def print_closest_aircraft(closest_aircraft):
    headers = ["Key", "Value"]
    table = []
    for aircraft_id, aircraft_data in closest_aircraft.items():
        for key, value in aircraft_data.items():
            table.append([key, value])
    print(tabulate(table, headers=headers, tablefmt="grid"))




def write_closest_aircraft_to_file(closest_aircraft):
    with open('./output/closest_aircraft.json', 'w') as json_file:
        json.dump(closest_aircraft, json_file, indent=4)

def publish_flights(flights):
    write_flights_to_file(flights)

def write_flights_to_file(flights):
    with open('./output/all_aircraft.json', 'w') as json_file:
        json.dump(flights, json_file, indent=4)


def write_filtered_flights_to_file(flights, filename, condition_key, condition_value):
    filtered_flights = {icao_id: flight for icao_id, flight in flights.items() if flight[condition_key] == condition_value}
    with open(filename, 'w') as json_file:
        json.dump(filtered_flights, json_file, indent=4)

def save_flights_within_defined_zone(flights):
    write_filtered_flights_to_file(flights, './output/flights_within_defined_zone.json', 'within_defined_zone', True)

def save_flights_within_defined_radius(flights):
    write_filtered_flights_to_file(flights, './output/flights_within_defined_radius.json', 'within_defined_radius', True)

def pretty_print_flights(flights):
    print(json.dumps(flights, indent=4))

def create_flights_rich(flights):

    flights_rich = {}
    with open('./data/airlines.json') as f:
        airlines_json = json.load(f)
    with open('./data/airports.json') as f:
        airports_json = json.load(f)
    with open('./data/aircraft.json') as f:
        aircraft_json = json.load(f)

    for flight_id, flight_data in flights.items():
        flight_rich_data = {}

        #Set some variables
        callsign = flight_data.get("callsign", "")
        flightno = flight_data.get("flightno", "")
        reg = flight_data.get("reg", "")

        # Basic identifiers
        flight_rich_data["icao_id"] = flight_data.get("icao_id", "")
        flight_rich_data["callsign"] = flight_data.get("callsign", "")
        flight_rich_data["flightno"] = flight_data.get("flightno", "")
        flight_rich_data["squawk"] = flight_data.get("squawk", "")
        flight_rich_data["reg"] = flight_data.get("reg", "")

        # Aircraft country from reg
        if reg:
            if reg_parser.parse(reg) is not None:
                flight_rich_data["reg_country_name"] = reg_parser.parse(reg)["nation"]
                flight_rich_data["reg_country_code"] = reg_parser.parse(reg)["iso2"]
                
        else:
            flight_rich_data["reg_country_name"] = ""
            flight_rich_data["reg_country_code"] = ""

        # Airline details based on icao_code or flightno
        if callsign:
            for airline in airlines_json:
                if airline["icao_code"] and airline["icao_code"].startswith(callsign[:3] if callsign else ""):
                    flight_rich_data["airline"] = airline["name"]
                    flight_rich_data["airline_country"] = airline["country"]
                    flight_rich_data["airline_callsign"] = airline.get("airline_callsign", "")
                    flight_rich_data["airline_icao"] = airline.get("icao_code", "")
                    flight_rich_data["airline_iata"] = airline.get("iata_code", "")
                    break
            else:
                flight_rich_data["airline"] = ""
                flight_rich_data["airline_country"] = ""
                flight_rich_data["airline_icao"] = ""
                flight_rich_data["airline_iata"] = ""
                flight_rich_data["airline_callsign"] = ""
        elif flightno:
            for airline in airlines_json:
                if airline["iata_code"].startswith(flightno[:2]):
                    flight_rich_data["airline"] = airline["name"]
                    flight_rich_data["airline_country"] = airline["country"]
                    flight_rich_data["airline_icao"] = airline.get("icao_code", "")
                    flight_rich_data["airline_iata"] = airline.get("iata_code", "")
                    flight_rich_data["airline_callsign"] = airline.get("airline_callsign", "")
                    break
            else:
                flight_rich_data["airline"] = ""
                flight_rich_data["airline_country"] = ""
                flight_rich_data["airline_icao"] = ""
                flight_rich_data["airline_iata"] = ""
                flight_rich_data["airline_callsign"] = ""

        # Helper function to extract airport information
        def get_airport_info(code, airports_json):
            airport = airports_json.get(code, {})
            return {
                "name": airport.get("name", ""),
                "city": airport.get("city", ""),
                "country_code": airport.get("country_code", "").upper(),
                "airport_code": code
            }

        # Route, origin & destination
        flight_rich_data["route"] = flight_data.get("route", "")
        route = flight_data.get("route", "")
        if route:
            substrings = route.split("-")
            origin_info = get_airport_info(substrings[0], airports_json)
            flight_rich_data.update({
                "origin": f"{origin_info['city']} {origin_info['airport_code']}",
                "origin_airport": origin_info['name'],
                "origin_airport_code": origin_info['airport_code'],
                "origin_city": origin_info['city'],
                "origin_country_code": origin_info['country_code']
            })

            destination_info = get_airport_info(substrings[-1], airports_json)
            flight_rich_data.update({
                "destination": f"{destination_info['city']} {destination_info['airport_code']}",
                "destination_airport": destination_info['name'],
                "destination_airport_code": destination_info['airport_code'],
                "destination_city": destination_info['city'],
                "destination_country_code": destination_info['country_code']
            })

            if len(substrings) == 3:
                via_info = get_airport_info(substrings[1], airports_json)
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


        # Aircraft info
        flight_rich_data["category"] = flight_data.get("category", "")
        flight_rich_data["type"] = flight_data.get("type", "")
        for aircraft in aircraft_json:
            if aircraft['icao_type_code'] == flight_data.get("type", ""):
                flight_rich_data["aircraft_model"] = aircraft["aircraft_model"]
                break
        else:
            flight_rich_data["aircraft_model"] = ""


        flight_rich_data["lat"] = flight_data.get("lat", "")
        flight_rich_data["lon"] = flight_data.get("lon", "")
        flight_rich_data["relative_closeness"] = flight_data.get("relative_closeness", "")
        flight_rich_data['distance'] = flight_data.get("distance", "")
        flight_rich_data['distance_value'] = flight_data.get("distance", "")
        flight_rich_data['distance_unit_of_measurement'] = flight_data.get("distance", "")
        flight_rich_data['within_defined_radius'] = flight_data.get("within_defined_radius", "")
        flight_rich_data['within_defined_zone'] = flight_data.get("within_defined_zone", "")
        flight_rich_data["altitude"] = flight_data.get("altitude", "")
        flight_rich_data["selected_altitude"] = flight_data.get("selected_altitude", "")
        flight_rich_data["barometer"] = flight_data.get("barometer", "")
        flight_rich_data["heading"] = flight_data.get("heading", "")
        flight_rich_data["magnetic_heading"] = flight_data.get("magnetic_heading", "")
        flight_rich_data["target_heading"] = flight_data.get("target_heading", "")
        flight_rich_data["vert_rate"] = flight_data.get("vert_rate", "")
        flight_rich_data["speed"] = flight_data.get("speed", "")
        flight_rich_data["indicated_air_speed"] = flight_data.get("indicated_air_speed", "")
        flight_rich_data["true_air_speed"] = flight_data.get("true_air_speed", "")
        flight_rich_data["ground_speed"] = flight_data.get("ground_speed", "")
        flight_rich_data["mach"] = flight_data.get("mach", "")
        flight_rich_data["polar_distance"] = flight_data.get("polar_distance", "")
        flight_rich_data["polar_bearing"] = flight_data.get("polar_bearing", "")
        flight_rich_data["roll_angle"] = flight_data.get("roll_angle", "")
        flight_rich_data["track_angle"] = flight_data.get("track_angle", "")
        flight_rich_data["is_on_ground"] = flight_data.get("is_on_ground", "")
        flight_rich_data["wind_speed"] = flight_data.get("wind_speed", "")
        flight_rich_data["wind_direction"] = flight_data.get("wind_direction", "")
        flight_rich_data["oat"] = flight_data.get("oat", "")
        flight_rich_data["last_seen_time"] = flight_data.get("last_seen_time", "")

        # Add last_seen_time in readable format
        last_seen_time = flight_data.get("last_seen_time", "")
        if last_seen_time:
            try:
                flight_rich_data["last_seen_time_readable"] = datetime.fromtimestamp(int(last_seen_time)).strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                flight_rich_data["last_seen_time_readable"] = ""
        else:
            flight_rich_data["last_seen_time_readable"] = ""

        flight_rich_data["pos_update_time"] = flight_data.get("pos_update_time", "")
        flight_rich_data["bds40_seen_time"] = flight_data.get("bds40_seen_time", "")
        flight_rich_data["bds50_seen_time"] = flight_data.get("bds50_seen_time", "")
        flight_rich_data["bds60_seen_time"] = flight_data.get("bds60_seen_time", "")
        flight_rich_data["bds62_seen_time"] = flight_data.get("bds62_seen_time", "")
        flight_rich_data["is_mlat"] = flight_data.get("is_mlat", "")
        flight_rich_data["age"] = flight_data.get("age", "")

        flights_rich[flight_id] = flight_rich_data

    return flights_rich

# Main program
if __name__ == "__main__":

    # Get config
    with open('./config/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    for key, value in config.items():
        globals()[key] = value
    # Get example dump file
    with open(tracker_dump_structure, 'r') as f:
        example_dump = json.load(f)

    # Set up MQTT client & connect to broker
    client = mqtt.Client(client_id=mqtt_client_id)
    client.username_pw_set(mqtt_user, mqtt_pwd)
    client.reconnect_delay_set(min_delay=1, max_delay=120) #reconnection parameters
    client.connect(mqtt_broker, mqtt_broker_port)
    client.loop_start() # Enable automatic reconnect

    #subprocess.Popen(["uvicorn", "flights_server:app", "--host", "0.0.0.0", "--port", "47474"])

    # Name of your FastAPI script in the same directory
    fastapi_script = "flights_server.py"

    # Start the FastAPI server in the background
    process = subprocess.Popen(["python", fastapi_script])

    reg_parser = Parser()
    previous_closest_aircraft = None
    previous_visible_aircraft = None

    while True:
        flights = get_receiver_data()
        flights = create_flights_rich(flights)
        visible = get_receiver_visible()
        publish_receiver_visible(visible)
        closest_aircraft = get_closest_aircraft()
        save_flights_within_defined_zone(flights)
        save_flights_within_defined_radius(flights)
        publish_closest_aircraft(closest_aircraft)
        publish_flights(flights)
        #pretty_print_flight_info(flights) # Print all flights


        time.sleep(check_interval)

