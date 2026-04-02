"""Flight data enrichment with airline, airport, and geographic information."""

from datetime import UTC, datetime
import json
import logging
import os

import airportsdata
import haversine
import shapely.geometry

from flights.config import BASE_DIR

logger = logging.getLogger(__name__)


class FlightEnricher:
    """Enriches raw ADS-B flight data with contextual information."""

    def __init__(
        self,
        airlines_json: list,
        aircraft_json: list,
        reg_parser,
        config: dict,
        hex_db: dict | None = None,
    ):
        self.base_dir = BASE_DIR
        self.missing_file = os.path.join(BASE_DIR, "output", "missing.json")
        self.lookups = self._create_lookup_dictionaries(airlines_json, aircraft_json)
        self.reg_parser = reg_parser
        self.config = config
        self.hex_db = hex_db or {}
        self.flights_with_location: list[tuple[float, str]] = []
        self.missing_data_log = self._initialize_missing_data_log()

    def _create_lookup_dictionaries(
        self, airlines_json: list, aircraft_json: list
    ) -> dict:
        return {
            "airlines_icao": {
                a["icao_code"]: a for a in airlines_json if a.get("icao_code")
            },
            "airlines_iata": {
                a["iata_code"]: a for a in airlines_json if a.get("iata_code")
            },
            "aircraft": {
                a["icao_type_code"]: a for a in aircraft_json if a.get("icao_type_code")
            },
            "airports": airportsdata.load("IATA"),
        }

    def _initialize_missing_data_log(self) -> dict:
        default_log = {
            "last_updated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "airlines": {},
            "aircraft": {},
            "airports": {},
            "logos": {},
        }
        try:
            if os.path.exists(self.missing_file):
                with open(self.missing_file) as f:
                    return json.load(f)
        except Exception:
            logger.exception("Error initializing missing data log")
        return default_log

    def _save_missing_data_log(self) -> None:
        try:
            with open(self.missing_file, "w") as f:
                json.dump(self.missing_data_log, f, indent=2)
        except Exception:
            logger.exception("Error saving missing data log")

    def enrich_flights(self, flights: dict) -> dict:
        """Enrich all flights with contextual data."""
        flights_rich = {}
        self.flights_with_location = []

        for flight_id, flight_data in flights.items():
            enriched = self._enrich_single_flight(flight_id, flight_data)
            flights_rich[flight_id] = enriched

        self._calculate_relative_closeness(flights_rich)
        return flights_rich

    def _enrich_single_flight(self, flight_id: str, flight_data: dict) -> dict:
        result = {
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

        # Hex database enrichment (fills gaps from ADS-B data)
        self._apply_hex_lookup(result, flight_id, flight_data)

        self._add_registration_info(result, flight_data)
        self._add_airline_info(result, flight_data)

        route_info = self._parse_route(flight_data.get("route", ""))
        result.update(route_info)

        self._add_location_info(result, flight_data, flight_id)
        self._add_additional_info(result, flight_data)

        return result

    def _calculate_relative_closeness(self, flights_rich: dict) -> None:
        self.flights_with_location.sort()
        for i, (_, flight_id) in enumerate(self.flights_with_location):
            flights_rich[flight_id]["relative_closeness"] = i + 1

    def _get_country_flag_emoji(self, country_code: str) -> str:
        if not country_code or len(country_code) != 2:
            return ""
        try:
            country_code = country_code.upper()
            return "".join(chr(ord(c) + 127397) for c in country_code)
        except Exception:
            return ""

    def _apply_hex_lookup(
        self, result: dict, flight_id: str, flight_data: dict
    ) -> None:
        """Enrich from hex database. Fills missing reg/type, adds owner info."""
        hex_entry = self.hex_db.get(flight_id.upper())
        if not hex_entry:
            return

        # Fill missing registration from hex DB
        if not flight_data.get("reg") and hex_entry.registration:
            result["reg"] = hex_entry.registration
            flight_data["reg"] = hex_entry.registration

        # Fill missing type from hex DB
        if not flight_data.get("type") and hex_entry.type_code:
            result["type"] = hex_entry.type_code
            flight_data["type"] = hex_entry.type_code

        # Store hex-derived fields
        if hex_entry.owner:
            result["hex_owner"] = hex_entry.owner
        if hex_entry.description:
            result["hex_description"] = hex_entry.description
        if hex_entry.year:
            result["hex_year"] = hex_entry.year
        if hex_entry.is_military:
            result["is_military"] = True

    def _add_registration_info(self, result: dict, flight_data: dict) -> None:
        if flight_data.get("reg"):
            parsed_reg = self.reg_parser.parse(flight_data["reg"])
            if parsed_reg:
                country_code = parsed_reg.get("iso2", "")
                result.update(
                    {
                        "reg_country_name": parsed_reg.get("nation", ""),
                        "reg_country_code": country_code,
                        "reg_country_flag": self._get_country_flag_emoji(country_code),
                    }
                )

    def _add_airline_info(self, result: dict, flight_data: dict) -> None:
        airline = self._get_airline_info(
            flight_data.get("callsign", ""),
            flight_data.get("flightno", ""),
            flight_data.get("reg", ""),
            has_hex_owner=bool(result.get("hex_owner")),
        )
        if airline:
            country_code = airline.get("country_code", "").upper()
            result.update(
                {
                    "airline": airline.get("name", ""),
                    "airline_country": airline.get("country", ""),
                    "airline_country_code": country_code,
                    "airline_country_flag": self._get_country_flag_emoji(country_code),
                    "airline_callsign": airline.get("airline_callsign", ""),
                    "airline_icao": airline.get("icao_code", ""),
                    "airline_iata": airline.get("iata_code", ""),
                }
            )
        elif result.get("hex_owner"):
            # Fallback: use hex database owner as operator name
            result["airline"] = result["hex_owner"]

    def _add_location_info(
        self, result: dict, flight_data: dict, flight_id: str
    ) -> None:
        lat_str = flight_data.get("lat")
        lon_str = flight_data.get("lon")
        if not lat_str or not lon_str:
            return
        try:
            lat, lon = float(lat_str), float(lon_str)
        except (ValueError, TypeError):
            return

        distance = haversine.haversine(self.config["user_location"], (lat, lon))
        result.update(
            {
                "lat": lat,
                "lon": lon,
                "distance": "{}{}".format(
                    f"{distance:.1f}", self.config["distance_unit"]
                ),
                "distance_value": f"{distance:.1f}",
                "distance_unit_of_measurement": self.config["distance_unit"],
                "within_defined_radius": distance <= self.config["radius"],
                "within_defined_zone": self.config["defined_zone"].contains(
                    shapely.geometry.Point(lon, lat)
                ),
            }
        )
        self.flights_with_location.append((distance, flight_id))

    def _add_additional_info(self, result: dict, flight_data: dict) -> None:
        altitude_info = self._process_altitude(
            flight_data.get("altitude", ""),
            flight_data.get("vert_rate", 0),
        )
        result.update(altitude_info)

        aircraft_type = flight_data.get("type", "")
        if aircraft_type in self.lookups["aircraft"]:
            result["aircraft_model"] = self.lookups["aircraft"][aircraft_type].get(
                "aircraft_model", ""
            )
        elif aircraft_type and result.get("hex_description"):
            # Not in our DB but hex DB has a description — use it
            result["aircraft_model"] = result["hex_description"]
        elif aircraft_type:
            entry = {
                "type": aircraft_type,
                "reg": flight_data.get("reg", ""),
            }
            self._add_reg_country(entry, flight_data.get("reg", ""))
            self._update_missing_data_log("aircraft", aircraft_type, entry)

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
            result[key] = flight_data.get(key, "")

        try:
            last_seen_time = int(flight_data.get("last_seen_time", 0))
            if last_seen_time:
                result["last_seen_time_readable"] = datetime.fromtimestamp(
                    last_seen_time, tz=UTC
                ).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pass

    def _get_airline_info(
        self,
        callsign: str,
        flightno: str,
        registration: str,
        has_hex_owner: bool = False,
    ) -> dict | None:
        airline = None
        if callsign:
            airline = self.lookups["airlines_icao"].get(callsign[:3])
        if not airline and flightno:
            airline = self.lookups["airlines_iata"].get(flightno[:2])
        if not airline and callsign and not has_hex_owner:
            entry = {"callsign": callsign, "reg": registration}
            self._add_reg_country(entry, registration)
            self._update_missing_data_log("airlines", callsign[:3], entry)
        return airline

    def _parse_route(self, route: str) -> dict:
        """Parse a route string like 'JFK-LHR' or 'JFK-DUB-LHR'."""
        empty_route = {
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

        if not route:
            return empty_route

        try:
            origin, *via, destination = route.split("-")
        except (ValueError, IndexError):
            return empty_route

        origin_info = self._get_airport_info(origin)
        dest_info = self._get_airport_info(destination)

        origin_city = origin_info.get("city")
        origin_code = origin_info.get("airport_code")
        dest_city = dest_info.get("city")
        dest_code = dest_info.get("airport_code")

        result = {
            "origin": (
                f"{origin_city} {origin_code}" if origin_city or origin_code else None
            ),
            "origin_airport_code": origin_code,
            "origin_airport_name": origin_info.get("name"),
            "origin_airport_city": origin_city,
            "origin_airport_country_code": origin_info.get("country_code"),
            "origin_airport_country_flag": origin_info.get("country_flag"),
            "destination": (
                f"{dest_city} {dest_code}" if dest_city or dest_code else None
            ),
            "destination_airport_code": dest_code,
            "destination_airport_name": dest_info.get("name"),
            "destination_airport_city": dest_city,
            "destination_airport_country_code": dest_info.get("country_code"),
            "destination_airport_country_flag": dest_info.get("country_flag"),
        }

        if via:
            via_info = self._get_airport_info(via[0])
            via_city = via_info.get("city")
            via_code = via_info.get("airport_code")
            result.update(
                {
                    "via": (f"{via_city} {via_code}" if via_city or via_code else None),
                    "via_airport_code": via_code,
                    "via_airport_name": via_info.get("name"),
                    "via_airport_city": via_city,
                    "via_airport_country_code": via_info.get("country_code"),
                    "via_airport_country_flag": via_info.get("country_flag"),
                }
            )
        else:
            result.update(
                {
                    "via": None,
                    "via_airport_code": None,
                    "via_airport_name": None,
                    "via_airport_city": None,
                    "via_airport_country_code": None,
                    "via_airport_country_flag": None,
                }
            )

        return result

    def _get_airport_info(self, code: str) -> dict:
        airport = self.lookups["airports"].get(code, {})
        if not airport and code:
            self._update_missing_data_log("airports", code)
        country_code = airport.get("country")
        return {
            "name": airport.get("name"),
            "city": airport.get("city"),
            "country_code": country_code,
            "country_flag": (
                self._get_country_flag_emoji(country_code) if country_code else None
            ),
            "airport_code": code,
        }

    def _process_altitude(self, altitude_str: str, vert_rate: float) -> dict:
        try:
            altitude_value = int(altitude_str)
            vert_rate = float(vert_rate)
        except (ValueError, TypeError):
            return {}

        if self.config["altitude_unit"] == "m":
            altitude_value = round(altitude_value * 0.3048)
            vert_rate = round(vert_rate * 0.3048)

        symbols = self.config["altitude_trends"]["SYMBOLS"]
        if abs(vert_rate) < 500:
            trend = symbols["LEVEL"]
        elif vert_rate > 0:
            trend = symbols["UP"]
        else:
            trend = symbols["DOWN"]

        unit = self.config["altitude_unit"]
        return {
            "altitude": f"{altitude_value}{unit}",
            "altitude_value": altitude_value,
            "altitude_unit_of_measurement": unit,
            "altitude_trend_symbol": trend,
            "altitude_with_trend": f"{altitude_value}{unit} {trend}",
        }

    def _add_reg_country(self, entry: dict, registration: str) -> None:
        """Add country info from aircraft registration to a dict."""
        if not registration:
            return
        parsed = self.reg_parser.parse(registration)
        if parsed:
            code = parsed.get("iso2", "")
            entry["country"] = parsed.get("nation", "")
            entry["country_code"] = code
            entry["country_flag"] = self._get_country_flag_emoji(code)

    def _update_missing_data_log(
        self, category: str, code: str, data: dict | None = None
    ) -> None:
        if not code or category not in self.missing_data_log:
            return
        if code not in self.missing_data_log[category]:
            self.missing_data_log[category][code] = data or True
            self.missing_data_log["last_updated"] = datetime.now(UTC).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            self._save_missing_data_log()


def create_flights_rich(
    flights: dict,
    airlines_json: list,
    aircraft_json: list,
    reg_parser,
    user_location: tuple[float, float],
    radius: float,
    defined_zone,
    altitude_unit: str,
    distance_unit: str,
    altitude_trends: dict,
    base_url: str,
    hex_db: dict | None = None,
) -> dict:
    """Enrich flights and add logo links."""
    config = {
        "radius": radius,
        "defined_zone": defined_zone,
        "altitude_unit": altitude_unit,
        "distance_unit": distance_unit,
        "altitude_trends": altitude_trends,
        "user_location": user_location,
    }
    enricher = FlightEnricher(
        airlines_json, aircraft_json, reg_parser, config, hex_db=hex_db
    )
    flights_rich = enricher.enrich_flights(flights)

    logos_dir = os.path.join(BASE_DIR, "assets", "images", "logos")
    for flight_data in flights_rich.values():
        airline_icao = flight_data.get("airline_icao", "").upper()
        if airline_icao and base_url:
            flight_data["airline_logo_link"] = "{}/logos/{}".format(
                base_url.rstrip("/"), airline_icao
            )
            # Track missing logos
            has_svg = os.path.exists(
                os.path.join(logos_dir, "svg", f"{airline_icao}.svg")
            )
            has_png = os.path.exists(
                os.path.join(logos_dir, "png", f"{airline_icao}.png")
            )
            if not has_svg and not has_png:
                airline_name = flight_data.get("airline", "")
                enricher._update_missing_data_log(
                    "logos",
                    airline_icao,
                    {"name": airline_name} if airline_name else None,
                )

    return flights_rich
