import json
import logging
import os
import traceback
from datetime import datetime

import airportsdata
import haversine
import shapely.geometry

# Define base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger = logging.getLogger("flight_enricher")


class FlightEnricher:
    def __init__(
        self, airlines_json: list, aircraft_json: list, reg_parser, config: dict
    ):
        try:
            self.base_dir = BASE_DIR
            # Use predefined output directory path from main file
            self.missing_file = os.path.join(BASE_DIR, "output/missing.json")

            self.lookups = self._create_lookup_dictionaries(
                airlines_json, aircraft_json
            )
            self.reg_parser = reg_parser
            self.config = config
            self.flights_with_location: list[tuple[float, str]] = []
            self.missing_data_log = self._initialize_missing_data_log()
            if "LOG_LEVEL" in config:
                logger.setLevel(getattr(logging, config["LOG_LEVEL"].upper()))
        except Exception as e:
            logger.error(
                f"Failed to initialize FlightEnricher: {str(e)}\n{traceback.format_exc()}"
            )
            raise

    def _create_lookup_dictionaries(
        self, airlines_json: list, aircraft_json: list
    ) -> dict:
        return {
            "airlines_icao": {
                airline["icao_code"]: airline
                for airline in airlines_json
                if airline["icao_code"]
            },
            "airlines_iata": {
                airline["iata_code"]: airline
                for airline in airlines_json
                if airline["iata_code"]
            },
            "aircraft": {
                aircraft["icao_type_code"]: aircraft for aircraft in aircraft_json
            },
            "airports": airportsdata.load("IATA"),
        }

    def _initialize_missing_data_log(self) -> dict:
        default_log = {
            "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "airlines": {},
            "aircraft": {},
            "airports": {},
        }

        try:
            return (
                json.load(open(self.missing_file))
                if os.path.exists(self.missing_file)
                else default_log
            )
        except Exception as e:
            logger.error(
                f"Error initializing missing data log: {str(e)}\n{traceback.format_exc()}"
            )
            return default_log

    def _save_missing_data_log_safe(self, data: dict) -> None:
        """Safely save missing data log directly in output directory."""
        try:
            with open(self.missing_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(
                f"Error saving missing data log: {str(e)}\n{traceback.format_exc()}"
            )

    def enrich_flights(self, flights: dict) -> dict:
        try:
            flights_rich = {}
            self.flights_with_location = []

            for flight_id, flight_data in flights.items():
                enriched_data = self._enrich_single_flight(flight_id, flight_data)
                flights_rich[flight_id] = enriched_data

            self._calculate_relative_closeness(flights_rich)
            return flights_rich
        except Exception as e:
            logger.error(
                f"Failed to enrich flights: {str(e)}\n{traceback.format_exc()}"
            )
            raise

    def _enrich_single_flight(self, flight_id: str, flight_data: dict) -> dict:
        # Basic flight info
        flight_rich_data = {
            key: flight_data.get(key, "")
            for key in (
                "icao_id",
                "callsign",
                "flightno",
                "squawk",
                "reg",
                "category",
                "type",
            )
        }

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

    def _calculate_relative_closeness(self, flights_rich: dict) -> None:
        self.flights_with_location.sort()
        for i, (_, flight_id) in enumerate(self.flights_with_location):
            flights_rich[flight_id]["relative_closeness"] = i + 1

    def _get_country_flag_emoji(self, country_code: str) -> str:
        """Convert a two-letter country code to an emoji flag."""
        if not country_code or len(country_code) != 2:
            return ""
        try:
            # Convert to regional indicator symbols by adding offset 127397 to ASCII value
            country_code = country_code.upper()
            return "".join(chr(ord(c) + 127397) for c in country_code)
        except Exception:
            return ""

    def _add_registration_info(self, flight_rich_data: dict, flight_data: dict) -> None:
        if flight_data.get("reg"):
            parsed_reg = self.reg_parser.parse(flight_data["reg"])
            if parsed_reg:
                country_code = parsed_reg.get("iso2", "")
                flight_rich_data.update(
                    {
                        "reg_country_name": parsed_reg.get("nation", ""),
                        "reg_country_code": country_code,
                        "reg_country_flag": self._get_country_flag_emoji(country_code),
                    }
                )

    def _add_airline_info(self, flight_rich_data: dict, flight_data: dict) -> None:
        airline = self._get_airline_info(
            flight_data.get("callsign", ""),
            flight_data.get("flightno", ""),
            flight_data.get("reg", ""),  # Pass registration to the method
        )
        if airline:
            country_code = airline.get(
                "country_code", ""
            ).upper()  # Ensure we get the correct country code
            flight_rich_data.update(
                {
                    "airline": airline.get("name", ""),
                    "airline_country": airline.get(
                        "country", ""
                    ),  # Ensure we get the full country name
                    "airline_country_code": country_code,  # Two-letter country code
                    "airline_country_flag": self._get_country_flag_emoji(country_code),
                    "airline_callsign": airline.get("airline_callsign", ""),
                    "airline_icao": airline.get("icao_code", ""),
                    "airline_iata": airline.get("iata_code", ""),
                }
            )

    def _add_location_info(
        self, flight_rich_data: dict, flight_data: dict, flight_id: str
    ) -> None:
        try:
            lat_str, lon_str = flight_data.get("lat"), flight_data.get("lon")
            if lat_str and lon_str:
                lat, lon = float(lat_str), float(lon_str)
                distance = haversine.haversine(self.config["user_location"], (lat, lon))
                flight_rich_data.update(
                    {
                        "lat": lat,
                        "lon": lon,
                        "distance": f"{distance:.1f}{self.config['distance_unit']}",
                        "distance_value": f"{distance:.1f}",
                        "distance_unit_of_measurement": self.config["distance_unit"],
                        "within_defined_radius": distance <= self.config["radius"],
                        "within_defined_zone": self.config["defined_zone"].contains(
                            shapely.geometry.Point(lon, lat)
                        ),
                    }
                )
                self.flights_with_location.append((distance, flight_id))
        except ValueError:
            pass

    def _add_additional_info(self, flight_rich_data: dict, flight_data: dict) -> None:
        altitude_info = self._process_altitude(
            flight_data.get("altitude", ""), flight_data.get("vert_rate", 0)
        )
        flight_rich_data.update(altitude_info)

        if flight_data.get("type") in self.lookups["aircraft"]:
            flight_rich_data["aircraft_model"] = self.lookups["aircraft"][
                flight_data["type"]
            ].get("aircraft_model", "")
        else:
            self._update_missing_data_log(
                "aircraft",
                flight_data.get("type", ""),
                {
                    "type": flight_data.get("type", ""),
                    "reg": flight_data.get("reg", ""),
                },
            )

        for key in (
            "selected_altitude",
            "barometer",
            "heading",
            "magnetic_heading",
            "target_heading",
            "vert_rate",
            "speed",
            "indicated_air_speed",
            "true_air_speed",
            "ground_speed",
            "mach",
            "polar_distance",
            "polar_bearing",
            "roll_angle",
            "track_angle",
            "is_on_ground",
            "wind_speed",
            "wind_direction",
            "oat",
            "last_seen_time",
            "pos_update_time",
            "bds40_seen_time",
            "bds50_seen_time",
            "bds60_seen_time",
            "bds62_seen_time",
            "is_mlat",
            "age",
        ):
            flight_rich_data[key] = flight_data.get(key, "")

        try:
            last_seen_time = int(flight_data.get("last_seen_time", 0))
            flight_rich_data["last_seen_time_readable"] = datetime.fromtimestamp(
                last_seen_time
            ).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    def _get_airline_info(
        self, callsign: str, flightno: str, registration: str
    ) -> dict:
        airline = self.lookups["airlines_icao"].get(callsign[:3]) if callsign else None
        if not airline and flightno:
            airline = self.lookups["airlines_icao"].get(flightno[:3])
        if not airline and flightno:
            airline = self.lookups["airlines_iata"].get(flightno[:2])
        if not airline and callsign:
            # Pass registration properly using the parameter
            self._update_missing_data_log(
                "airlines", callsign[:3], {"callsign": callsign, "reg": registration}
            )
        return airline

    def _parse_route(self, route: str) -> dict:
        def get_airport_info(code: str) -> dict:
            airport = self.lookups["airports"].get(code, {})
            if not airport:
                self._update_missing_data_log("airports", code)
            country_code = airport.get("country", None)
            return {
                "name": airport.get("name", None),
                "city": airport.get("city", None),
                "country_code": country_code,
                "country_flag": self._get_country_flag_emoji(country_code)
                if country_code
                else None,
                "airport_code": code,
            }

        try:
            origin, *via, destination = route.split("-")
            origin_info = get_airport_info(origin)
            destination_info = get_airport_info(destination)

            origin_city = origin_info.get("city", None)
            origin_code = origin_info.get("airport_code", None)
            origin_combined = (
                f"{origin_city} {origin_code}" if origin_city or origin_code else None
            )

            destination_city = destination_info.get("city", None)
            destination_code = destination_info.get("airport_code", None)
            destination_combined = (
                f"{destination_city} {destination_code}"
                if destination_city or destination_code
                else None
            )

            route_info = {
                "origin": origin_combined,
                "origin_airport_code": origin_code,
                "origin_airport_name": origin_info.get("name", None),
                "origin_airport_city": origin_city,
                "origin_airport_country_code": origin_info.get("country_code", None),
                "origin_airport_country_flag": origin_info.get("country_flag", None),
                "destination": destination_combined,
                "destination_airport_code": destination_code,
                "destination_airport_name": destination_info.get("name", None),
                "destination_airport_city": destination_city,
                "destination_airport_country_code": destination_info.get(
                    "country_code", None
                ),
                "destination_airport_country_flag": destination_info.get(
                    "country_flag", None
                ),
            }
            if via:
                via_info = get_airport_info(via[0])
                via_city = via_info.get("city", None)
                via_code = via_info.get("airport_code", None)
                via_combined = (
                    f"{via_city} {via_code}" if via_city or via_code else None
                )
                route_info.update(
                    {
                        "via": via_combined,
                        "via_airport_code": via_code,
                        "via_airport_name": via_info.get("name", None),
                        "via_airport_city": via_city,
                        "via_airport_country_code": via_info.get("country_code", None),
                        "via_airport_country_flag": via_info.get("country_flag", None),
                    }
                )
            else:
                route_info.update(
                    {
                        "via": None,
                        "via_airport_code": None,
                        "via_airport_name": None,
                        "via_airport_city": None,
                        "via_airport_country_code": None,
                        "via_airport_country_flag": None,
                    }
                )
            return route_info
        except (ValueError, IndexError):
            return {
                "origin": None,
                "origin_airport_code": None,
                "origin_airport_name": None,
                "origin_airport_city": None,
                "origin_airport_country_code": None,
                "origin_airport_country_flag": None,
                "destination": None,
                "destination_airport_code": None,
                "destination_airport_name": None,
                "destination_airport_city": None,
                "destination_airport_country_code": None,
                "destination_airport_country_flag": None,
                "via": None,
                "via_airport_code": None,
                "via_airport_name": None,
                "via_airport_city": None,
                "via_airport_country_code": None,
                "via_airport_country_flag": None,
            }

    def _process_altitude(self, altitude_str: str, vert_rate: float) -> dict:
        try:
            altitude_value = int(altitude_str)
            vert_rate = float(vert_rate)

            if self.config["altitude_unit"] == "m":
                altitude_value = round(altitude_value * 0.3048)
                vert_rate = round(vert_rate * 0.3048)

            if abs(vert_rate) < 500:
                altitude_trend_symbol = self.config["altitude_trends"]["SYMBOLS"][
                    "LEVEL"
                ]
            elif vert_rate > 0:
                altitude_trend_symbol = self.config["altitude_trends"]["SYMBOLS"]["UP"]
            else:
                altitude_trend_symbol = self.config["altitude_trends"]["SYMBOLS"][
                    "DOWN"
                ]

            return {
                "altitude": f"{altitude_value}{self.config['altitude_unit']}",
                "altitude_value": altitude_value,
                "altitude_unit_of_measurement": self.config["altitude_unit"],
                "altitude_trend_symbol": altitude_trend_symbol,
                "altitude_with_trend": f"{altitude_value}{self.config['altitude_unit']} {altitude_trend_symbol}",
            }
        except ValueError:
            return {}

    def _update_missing_data_log(
        self, category: str, code: str, data: dict = None
    ) -> None:
        """Update missing data log with new missing item."""
        try:
            if not self.missing_data_log:
                self.missing_data_log = self._initialize_missing_data_log()

            if code and category in self.missing_data_log:
                # For airlines and aircraft, store both identifiers and registration
                if (
                    category in ["airlines", "aircraft"]
                    and code not in self.missing_data_log[category]
                ):
                    self.missing_data_log[category][code] = data
                elif (
                    category not in ["airlines", "aircraft"]
                    and code not in self.missing_data_log[category]
                ):
                    self.missing_data_log[category][code] = True

                self.missing_data_log["last_updated"] = datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                self._save_missing_data_log_safe(self.missing_data_log)
        except Exception as e:
            logger.error(
                f"Error updating missing data log: {str(e)}\n{traceback.format_exc()}"
            )


def create_flights_rich(
    flights,
    airlines_json,
    aircraft_json,
    reg_parser,
    user_location,
    radius,
    defined_zone,
    altitude_unit,
    distance_unit,
    altitude_trends,
    base_url,
):
    config = {
        "radius": radius,
        "defined_zone": defined_zone,
        "altitude_unit": altitude_unit,
        "distance_unit": distance_unit,
        "altitude_trends": altitude_trends,
        "user_location": user_location,
    }
    enricher = FlightEnricher(airlines_json, aircraft_json, reg_parser, config)
    flights_rich = enricher.enrich_flights(flights)

    for icao_id, flight_data in flights_rich.items():
        # Ensure airline_logo_link is added immediately after airline_icao
        airline_icao = flight_data.get("airline_icao", "").upper()
        flight_data_ordered = {}
        for key, value in flight_data.items():
            flight_data_ordered[key] = value
            if key == "airline_icao":
                flight_data_ordered["airline_logo_link"] = (
                    f"{base_url}/logos/{airline_icao}"
                )
        flights_rich[icao_id] = flight_data_ordered

    return flights_rich
