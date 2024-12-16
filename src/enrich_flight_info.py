from datetime import datetime
import haversine
import shapely.geometry
import os
import airportsdata
from typing import Dict, List, Tuple
import logging
import traceback

logger = logging.getLogger('flight_enricher')

class FlightEnricher:
    def __init__(self, airlines_json: list, aircraft_json: list, reg_parser, config: dict):
        try:
            self.lookups = self._create_lookup_dictionaries(airlines_json, aircraft_json)
            self.reg_parser = reg_parser
            self.config = config
            self.flights_with_location: List[Tuple[float, str]] = []
            if 'LOG_LEVEL' in config:
                logger.setLevel(getattr(logging, config['LOG_LEVEL'].upper()))
        except Exception as e:
            logger.error(f"Failed to initialize FlightEnricher: {str(e)}\n{traceback.format_exc()}")
            raise
        
    def _create_lookup_dictionaries(self, airlines_json: list, aircraft_json: list) -> Dict:
        return {
            'airlines_icao': {airline["icao_code"]: airline for airline in airlines_json if airline["icao_code"]},
            'airlines_iata': {airline["iata_code"]: airline for airline in airlines_json if airline["iata_code"]},
            'aircraft': {aircraft["icao_type_code"]: aircraft for aircraft in aircraft_json},
            'airports': airportsdata.load('IATA')
        }

    def enrich_flights(self, flights: Dict) -> Dict:
        try:
            flights_rich = {}
            self.flights_with_location = []
            
            for flight_id, flight_data in flights.items():
                enriched_data = self._enrich_single_flight(flight_id, flight_data)
                flights_rich[flight_id] = enriched_data
                
            self._calculate_relative_closeness(flights_rich)
            return flights_rich
        except Exception as e:
            logger.error(f"Failed to enrich flights: {str(e)}\n{traceback.format_exc()}")
            raise

    def _enrich_single_flight(self, flight_id: str, flight_data: Dict) -> Dict:
        # Basic flight info
        flight_rich_data = {key: flight_data.get(key, "") for key in (
            "icao_id", "callsign", "flightno", "squawk", "reg", "category", "type"
        )}

        # Registration
        self._add_registration_info(flight_rich_data, flight_data)
        
        # Airline
        self._add_airline_info(flight_rich_data, flight_data)
        
        # Route
        route_info = self._parse_route(flight_data.get("route", ""))
        flight_rich_data.update(route_info)
        
        # Location and distance
        self._add_location_info(flight_rich_data, flight_data, flight_id)
        
        # Remaining processing
        self._add_additional_info(flight_rich_data, flight_data)
        
        return flight_rich_data

    def _calculate_relative_closeness(self, flights_rich: Dict) -> None:
        self.flights_with_location.sort()
        for i, (_, flight_id) in enumerate(self.flights_with_location):
            flights_rich[flight_id]["relative_closeness"] = i + 1

    def _add_registration_info(self, flight_rich_data: Dict, flight_data: Dict) -> None:
        if flight_data.get("reg"):
            parsed_reg = self.reg_parser.parse(flight_data["reg"])
            if parsed_reg:
                flight_rich_data.update({
                    "reg_country_name": parsed_reg.get("nation", ""),
                    "reg_country_code": parsed_reg.get("iso2", "")
                })

    def _add_airline_info(self, flight_rich_data: Dict, flight_data: Dict) -> None:
        airline = self._get_airline_info(
            flight_data.get("callsign", ""),
            flight_data.get("flightno", "")
        )
        if airline:
            flight_rich_data.update({
                "airline": airline.get("name", ""),
                "airline_country": airline.get("country", ""),
                "airline_callsign": airline.get("airline_callsign", ""),
                "airline_icao": airline.get("icao_code", ""),
                "airline_iata": airline.get("iata_code", "")
            })

    def _add_location_info(self, flight_rich_data: Dict, flight_data: Dict, flight_id: str) -> None:
        try:
            lat_str, lon_str = flight_data.get("lat"), flight_data.get("lon")
            if lat_str and lon_str:
                lat, lon = float(lat_str), float(lon_str)
                distance = haversine.haversine(self.config['user_location'], (lat, lon))
                flight_rich_data.update({
                    "lat": lat,
                    "lon": lon,
                    "distance": f"{distance:.1f}{self.config['distance_unit']}",
                    "distance_value": f"{distance:.1f}",
                    "distance_unit_of_measurement": self.config['distance_unit'],
                    "within_defined_radius": distance <= self.config['radius'],
                    "within_defined_zone": self.config['defined_zone'].contains(shapely.geometry.Point(lon, lat))
                })
                self.flights_with_location.append((distance, flight_id))
        except ValueError:
            pass

    def _add_additional_info(self, flight_rich_data: Dict, flight_data: Dict) -> None:
        altitude_info = self._process_altitude(flight_data.get("altitude", ""), flight_data.get("vert_rate", 0))
        flight_rich_data.update(altitude_info)

        if flight_data.get("type") in self.lookups['aircraft']:
            flight_rich_data["aircraft_model"] = self.lookups['aircraft'][flight_data["type"]].get("aircraft_model", "")

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

        try:
            last_seen_time = int(flight_data.get("last_seen_time", 0))
            flight_rich_data["last_seen_time_readable"] = datetime.fromtimestamp(last_seen_time).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass

    def _get_airline_info(self, callsign: str, flightno: str) -> Dict:
        airline = self.lookups['airlines_icao'].get(callsign[:3]) if callsign else None
        if not airline and flightno:
            airline = self.lookups['airlines_icao'].get(flightno[:3])
        if not airline and flightno:
            airline = self.lookups['airlines_iata'].get(flightno[:2])
        return airline

    def _parse_route(self, route: str) -> Dict:
        def get_airport_info(code: str) -> Dict:
            airport = self.lookups['airports'].get(code, {})
            return {
                "name": airport.get("name", ""),
                "city": airport.get("city", ""),
                "country_code": airport.get("country", "").upper(),
                "airport_code": code
            }

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

    def _process_altitude(self, altitude_str: str, vert_rate: float) -> Dict:
        try:
            altitude_value = int(altitude_str)
            vert_rate = float(vert_rate)

            if self.config['altitude_unit'] == 'm':
                altitude_value = round(altitude_value * 0.3048)
                vert_rate = round(vert_rate * 0.3048)

            altitude_trend_symbol = self.config['altitude_trends']["SYMBOLS"]["UP"] if vert_rate > 0 else self.config['altitude_trends']["SYMBOLS"]["DOWN"] if vert_rate < 0 else self.config['altitude_trends']["SYMBOLS"]["LEVEL"]
            return {
                "altitude": f"{altitude_value}{self.config['altitude_unit']}",
                "altitude_value": altitude_value,
                "altitude_unit_of_measurement": self.config['altitude_unit'],
                "altitude_trend_symbol": altitude_trend_symbol,
                "altitude_with_trend": f"{altitude_value}{self.config['altitude_unit']} {altitude_trend_symbol}"
            }
        except ValueError:
            return {}

def create_flights_rich(flights, airlines_json, aircraft_json, reg_parser, user_location, radius, defined_zone, altitude_unit, distance_unit, altitude_trends):
    config = {
        'radius': radius,
        'defined_zone': defined_zone,
        'altitude_unit': altitude_unit,
        'distance_unit': distance_unit,
        'altitude_trends': altitude_trends,
        'user_location': user_location
    }
    enricher = FlightEnricher(airlines_json, aircraft_json, reg_parser, config)
    return enricher.enrich_flights(flights)
