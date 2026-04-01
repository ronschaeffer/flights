"""Tests for flight data enrichment."""

import shapely.geometry

from flights.enricher import FlightEnricher, create_flights_rich


def _make_enricher_config():
    return {
        "radius": 10,
        "defined_zone": shapely.geometry.Polygon(
            [
                (-0.37, 51.45),
                (-0.37, 51.49),
                (-0.28, 51.49),
                (-0.28, 51.45),
            ]
        ),
        "altitude_unit": "ft",
        "distance_unit": "mi",
        "altitude_trends": {
            "LEVEL_THRESHOLD": 250,
            "SYMBOLS": {"UP": "U", "DOWN": "D", "LEVEL": "L"},
        },
        "user_location": (51.462649, -0.328869),
    }


class MockRegParser:
    def parse(self, reg):
        if reg and reg.startswith("G-"):
            return {"iso2": "GB", "nation": "United Kingdom"}
        if reg and reg.startswith("D-"):
            return {"iso2": "DE", "nation": "Germany"}
        return None


def test_enrich_single_flight(sample_airlines, sample_aircraft, sample_flights):
    """Enricher adds airline, route, distance info."""
    config = _make_enricher_config()
    enricher = FlightEnricher(sample_airlines, sample_aircraft, MockRegParser(), config)
    result = enricher.enrich_flights(sample_flights)

    assert "ABC123" in result
    flight = result["ABC123"]
    assert flight["airline"] == "British Airways"
    assert flight["airline_icao"] == "BAW"
    assert flight["reg_country_code"] == "GB"
    assert "distance_value" in flight
    assert flight["altitude_value"] == 3000


def test_enrich_route_parsing(sample_airlines, sample_aircraft):
    """Route parsing extracts origin and destination."""
    config = _make_enricher_config()
    enricher = FlightEnricher(sample_airlines, sample_aircraft, MockRegParser(), config)
    route_info = enricher._parse_route("JFK-LHR")
    assert route_info["origin_airport_code"] == "JFK"
    assert route_info["destination_airport_code"] == "LHR"
    assert route_info["via"] is None


def test_enrich_route_with_via(sample_airlines, sample_aircraft):
    """Route with via stop is parsed correctly."""
    config = _make_enricher_config()
    enricher = FlightEnricher(sample_airlines, sample_aircraft, MockRegParser(), config)
    route_info = enricher._parse_route("JFK-DUB-LHR")
    assert route_info["origin_airport_code"] == "JFK"
    assert route_info["destination_airport_code"] == "LHR"
    assert route_info["via_airport_code"] == "DUB"


def test_enrich_empty_route(sample_airlines, sample_aircraft):
    """Empty route returns None values."""
    config = _make_enricher_config()
    enricher = FlightEnricher(sample_airlines, sample_aircraft, MockRegParser(), config)
    route_info = enricher._parse_route("")
    assert route_info["origin"] is None
    assert route_info["destination"] is None


def test_altitude_processing(sample_airlines, sample_aircraft):
    """Altitude processing handles units and trends."""
    config = _make_enricher_config()
    enricher = FlightEnricher(sample_airlines, sample_aircraft, MockRegParser(), config)

    result = enricher._process_altitude("3000", 0)
    assert result["altitude_value"] == 3000
    assert result["altitude_trend_symbol"] == "L"

    result = enricher._process_altitude("3000", 1000)
    assert result["altitude_trend_symbol"] == "U"

    result = enricher._process_altitude("3000", -1000)
    assert result["altitude_trend_symbol"] == "D"


def test_altitude_metric(sample_airlines, sample_aircraft):
    """Altitude converts to meters when configured."""
    config = _make_enricher_config()
    config["altitude_unit"] = "m"
    enricher = FlightEnricher(sample_airlines, sample_aircraft, MockRegParser(), config)
    result = enricher._process_altitude("3000", 0)
    assert result["altitude_value"] == 914  # 3000 * 0.3048


def test_country_flag_emoji(sample_airlines, sample_aircraft):
    """Country flag emoji is generated from country code."""
    config = _make_enricher_config()
    enricher = FlightEnricher(sample_airlines, sample_aircraft, MockRegParser(), config)
    assert enricher._get_country_flag_emoji("GB") != ""
    assert enricher._get_country_flag_emoji("") == ""
    assert enricher._get_country_flag_emoji("X") == ""


def test_create_flights_rich_adds_logo_link(
    sample_airlines, sample_aircraft, sample_flights
):
    """create_flights_rich adds airline_logo_link to enriched data."""
    config = _make_enricher_config()
    result = create_flights_rich(
        sample_flights,
        sample_airlines,
        sample_aircraft,
        MockRegParser(),
        config["user_location"],
        config["radius"],
        config["defined_zone"],
        config["altitude_unit"],
        config["distance_unit"],
        config["altitude_trends"],
        "http://10.10.10.20:47475",
    )
    flight = result["ABC123"]
    assert flight["airline_logo_link"] == "http://10.10.10.20:47475/logos/BAW"
