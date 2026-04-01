# Flights

Enriches flight data from ADS-B receivers with MQTT publishing and HTTP API, suitable for integration with Home Assistant.

## Features

- Fetches real-time aircraft data from a local ADS-B receiver (PlaneFinder, dump1090, etc.)
- Enriches with airline, aircraft type, airport, and route information
- Publishes to MQTT with Home Assistant auto-discovery
- HTTP API serving JSON data, airline logos (SVG/PNG), and country flags
- Tracks unique flight counts and statistics over time
- Docker container with Unraid template

## Quick Start

```bash
# Install
poetry install

# Configure
cp config/config.yaml.example config/config.yaml
# Edit config/config.yaml with your settings

# Run
poetry run flights
```

## Docker

```bash
docker run -d \
  --name flights \
  -p 47475:47475 \
  -e MQTT_BROKER_URL=your-broker \
  -e DUMP_URL=http://your-receiver:30053/ajax/aircraft \
  -e WEB_SERVER_EXTERNAL_URL=http://your-host:47475 \
  -v /path/to/config:/app/config \
  ghcr.io/ronschaeffer/flights:latest
```

## Development

```bash
make fix        # lint + format
make test       # run tests
make ci-check   # full CI check
```
