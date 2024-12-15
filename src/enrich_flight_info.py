from datetime import datetime
import haversine
import shapely.geometry
import os

def create_flights_rich(flights, airlines_json, airports_json, aircraft_json, reg_parser, user_location, radius, defined_zone, altitude_unit, distance_unit, altitude_trends):
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
        flight_rich_data = {key: flight_data.get(key, "") for key in ("icao_id", "callsign", "flightno", "squawk", "reg", "category", "type")}

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
        airline = get_airline_info(flight_data.get("callsign", ""), flight_data.get("flightno", ""), airlines_by_icao, airlines_by_iata)
        if airline:
            flight_rich_data.update({
                "airline": airline.get("name", ""),
                "airline_country": airline.get("country", ""),
                "airline_callsign": airline.get("airline_callsign", ""),
                "airline_icao": airline.get("icao_code", ""),
                "airline_iata": airline.get("iata_code", "")
            })

        # Parse route information
        route_info = parse_route(flight_data.get("route", ""), get_airport_info)
        flight_rich_data.update(route_info)

        # Calculate distance and location information
        try:
            lat_str, lon_str = flight_data.get("lat"), flight_data.get("lon")
            if lat_str and lon_str:
                lat, lon = float(lat_str), float(lon_str)
                distance = haversine.haversine(user_location, (lat, lon))
                flights_with_location.append((distance, flight_id))
                flight_rich_data.update({
                    "lat": lat,
                    "lon": lon,
                    "distance": f"{distance:.1f}{distance_unit}",
                    "distance_value": f"{distance:.1f}",
                    "distance_unit_of_measurement": distance_unit,
                    "within_defined_radius": distance <= radius,
                    "within_defined_zone": defined_zone.contains(shapely.geometry.Point(lon, lat))
                })
        except ValueError:
            pass

        # Process altitude information
        altitude_info = process_altitude(flight_data.get("altitude", ""), flight_data.get("vert_rate", 0), altitude_unit, altitude_trends)
        flight_rich_data.update(altitude_info)

        # Add aircraft model information
        if flight_data.get("type") in aircraft_by_type:
            flight_rich_data["aircraft_model"] = aircraft_by_type[flight_data["type"]].get("aircraft_model", "")

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
            pass

        flights_rich[flight_id] = flight_rich_data  # Add all flights to flights_rich

    # Calculate relative closeness for flights with location data
    flights_with_location.sort()
    for i, (_, flight_id) in enumerate(flights_with_location):
        flights_rich[flight_id]["relative_closeness"] = i + 1

    return flights_rich

def get_airline_info(callsign, flightno, airlines_by_icao, airlines_by_iata):
    airline = airlines_by_icao.get(callsign[:3]) if callsign else None
    if not airline:
        airline = airlines_by_iata.get(flightno[:2]) if flightno else None
    return airline

def parse_route(route, get_airport_info):
    try:
        origin, *via, destination = route.split("-")
        origin_info = get_airport_info(origin)
        destination_info = get_airport_info(destination)
        route_info = {
            "origin_airport_name": origin_info.get("name", None),
            "origin_airport_city": origin_info.get("city", None),
            "origin_airport_country_code": origin_info.get("country_code", None),
            "origin_airport_code": origin_info.get("airport_code", None),
            "destination_airport_name": destination_info.get("name", None),
            "destination_airport_city": destination_info.get("city", None),
            "destination_airport_country_code": destination_info.get("country_code", None),
            "destination_airport_code": destination_info.get("airport_code", None)
        }
        if via:
            via_info = get_airport_info(via[0])
            route_info.update({
                "via_airport_name": via_info.get("name", None),
                "via_airport_city": via_info.get("city", None),
                "via_airport_country_code": via_info.get("country_code", None),
                "via_airport_code": via_info.get("airport_code", None)
            })
        else:
            route_info.update({
                "via_airport_name": None,
                "via_airport_city": None,
                "via_airport_country_code": None,
                "via_airport_code": None
            })
        return route_info
    except (ValueError, IndexError):
        return {
            "origin_airport_name": None,
            "origin_airport_city": None,
            "origin_airport_country_code": None,
            "origin_airport_code": None,
            "destination_airport_name": None,
            "destination_airport_city": None,
            "destination_airport_country_code": None,
            "destination_airport_code": None,
            "via_airport_name": None,
            "via_airport_city": None,
            "via_airport_country_code": None,
            "via_airport_code": None
        }

def process_altitude(altitude_str, vert_rate, altitude_unit, altitude_trends):
    try:
        altitude_value = int(altitude_str)
        vert_rate = float(vert_rate)  # Ensure vert_rate is a float

        # Convert altitude to meters if the unit is 'm'
        if altitude_unit == 'm':
            altitude_value = round(altitude_value * 0.3048)
            vert_rate = round(vert_rate * 0.3048)

        altitude_trend_symbol = altitude_trends["SYMBOLS"]["UP"] if vert_rate > 0 else altitude_trends["SYMBOLS"]["DOWN"] if vert_rate < 0 else altitude_trends["SYMBOLS"]["LEVEL"]
        return {
            "altitude": f"{altitude_value}{altitude_unit}",
            "altitude_value": altitude_value,
            "altitude_unit_of_measurement": altitude_unit,
            "altitude_trend_symbol": altitude_trend_symbol,
            "altitude_with_trend": f"{altitude_value}{altitude_unit} {altitude_trend_symbol}"
        }
    except ValueError:
        return {}
