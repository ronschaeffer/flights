"""Shared test fixtures."""

import pytest

from flights.config import FlightsConfig


@pytest.fixture
def sample_config_yaml(tmp_path):
    """Create a minimal config YAML file."""
    config_content = """
app:
  name: "Flights Test"
  unique_id_prefix: "flights_test"
  manufacturer: "test"
  model: "Test Flights"

mqtt:
  broker_url: "localhost"
  broker_port: 1883
  client_id: "test_client"
  security: "none"
  topics:
    visible: "test/flights/visible"
    closest: "test/flights/closest"
    availability: "test/flights/availability"

home_assistant:
  enabled: true
  discovery_prefix: "homeassistant"

web_server:
  enabled: true
  host: "0.0.0.0"
  port: 47475
  external_url: "http://10.10.10.20:47475"
  image_format: "svg"

receiver:
  dump_url: "http://localhost:30053/ajax/aircraft"
  check_interval: 15

location:
  lat: 51.462649
  lon: -0.328869
  radius: 10
  distance_unit: "mi"
  altitude_unit: "ft"

zone:
  lat_south: 51.45538
  lat_north: 51.48787
  lon_west: -0.37257
  lon_east: -0.28753
  max_alt: 3000
  min_alt: 0

logging:
  level: "DEBUG"
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)
    return str(config_file)


@pytest.fixture
def config(sample_config_yaml):
    """Return a FlightsConfig instance."""
    return FlightsConfig(sample_config_yaml)


@pytest.fixture
def sample_airlines():
    """Minimal airlines data."""
    return [
        {
            "icao_code": "BAW",
            "iata_code": "BA",
            "name": "British Airways",
            "country": "United Kingdom",
            "country_code": "GB",
            "airline_callsign": "SPEEDBIRD",
        },
        {
            "icao_code": "DLH",
            "iata_code": "LH",
            "name": "Lufthansa",
            "country": "Germany",
            "country_code": "DE",
            "airline_callsign": "LUFTHANSA",
        },
    ]


@pytest.fixture
def sample_aircraft():
    """Minimal aircraft data."""
    return [
        {
            "icao_type_code": "B772",
            "aircraft_model": "Boeing 777-200",
        },
        {
            "icao_type_code": "A320",
            "aircraft_model": "Airbus A320",
        },
    ]


@pytest.fixture
def sample_flights():
    """Sample flight data as returned by an ADS-B receiver."""
    return {
        "ABC123": {
            "icao_id": "ABC123",
            "callsign": "BAW123",
            "flightno": "BA123",
            "route": "JFK-LHR",
            "type": "B772",
            "reg": "G-VIIA",
            "lat": "51.47",
            "lon": "-0.33",
            "altitude": "3000",
            "heading": "270",
            "speed": "180",
            "vert_rate": "0",
            "squawk": "1234",
            "category": "",
        },
        "DEF456": {
            "icao_id": "DEF456",
            "callsign": "DLH456",
            "flightno": "LH456",
            "route": "FRA-LHR",
            "type": "A320",
            "reg": "D-AIUA",
            "lat": "51.46",
            "lon": "-0.35",
            "altitude": "2500",
            "heading": "90",
            "speed": "160",
            "vert_rate": "-500",
            "squawk": "5678",
            "category": "",
        },
    }
