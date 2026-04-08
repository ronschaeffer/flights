# ✈️ Flights

Real-time ADS-B flight tracking with enriched data, MQTT publishing, and Home Assistant integration.

[![CI](https://github.com/ronschaeffer/flights/actions/workflows/ci.yml/badge.svg)](https://github.com/ronschaeffer/flights/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## What It Does

Flights connects to a local ADS-B receiver (such as Plane Finder Client, dump1090, or readsb), fetches live aircraft positions, and enriches each flight with detailed contextual information:

| Data | Source | Example |
|---|---|---|
| **Airline** | ICAO/IATA lookup | Ryanair, British Airways, Lufthansa |
| **Aircraft type** | ICAO type code | Boeing 737 MAX 8, Airbus A320 |
| **Route** | Origin → Destination | Seville SVQ 🇪🇸 → London STN 🇬🇧 |
| **Registration** | Country lookup | EI-IHP (Ireland 🇮🇪) |
| **Hex database** | tar1090-db (619K aircraft) | Owner, year, military flag |
| **Distance** | Haversine calculation | 2.1 mi from observer |
| **Altitude & trend** | Vertical rate analysis | 16,700ft ⬊ (descending) |
| **Geographic zone** | Shapely polygon check | Within/outside defined watch area |
| **Country flags** | ISO code → emoji | 🇬🇧 🇮🇪 🇪🇸 🇩🇪 🇺🇸 |

The enriched data is published to MQTT for Home Assistant and served via an HTTP API with airline logos and country flags.

---

## 🏠 Home Assistant Integration

Flights registers as a device in Home Assistant via MQTT discovery with stable identifiers — no duplicate devices on restart, and the device is automatically recreated if deleted.

### Entities

| Entity | Type | Description |
|---|---|---|
| **Closest Aircraft** | sensor | Distance to nearest plane (mi/km) with full flight details as attributes |
| **Visible Aircraft** | sensor | Count of aircraft in range, plus unique flight statistics |
| **Status** | sensor (diagnostic) | Service status: `active` or `error` |
| **Last Update** | sensor (diagnostic) | Timestamp of last data cycle |
| **ADS-B Receiver** | binary_sensor (diagnostic) | Plane Finder Client health — checks `/ajax/stats` for live data reception |
| **Web Server** | binary_sensor (diagnostic) | HTTP API health — checks `/health` endpoint |
| **Refresh** | button | Triggers an immediate fetch/publish cycle |

The closest aircraft sensor exposes rich attributes including airline name, route, aircraft type, registration, altitude with trend symbol, distance, country flags, and a link to the airline logo.

### Alerts

An example automation is included at `ha_automations/flights_source_alert.yaml` that creates persistent notifications when:

- The ADS-B receiver stops responding or receiving data
- The Flights web server goes offline
- The Flights service disconnects from MQTT

Notifications are automatically dismissed when the source recovers.

---

## 🌐 HTTP API

A built-in FastAPI web server provides JSON data and static image assets.

| Endpoint | Description |
|---|---|
| `/` | Home page — lists available JSON files and image directories |
| `/health` | Process liveness — always returns 200 |
| `/health/mqtt` | MQTT broker liveness (since v0.5.0) — returns 200 if the publisher is connected and a successful publish has happened in the last 5 minutes; 503 otherwise. **This is what the Docker HEALTHCHECK probes**, so a real broker outage now actually marks the container unhealthy. Built on `ha_mqtt_publisher`'s shared [`HealthTracker`](https://github.com/ronschaeffer/ha_mqtt_publisher#health--liveness). |
| `/{file_name}` | JSON output files: `visible`, `closest_aircraft`, `all_aircraft` |
| `/logos` | List all airline logos (SVG and PNG) |
| `/logos/{icao}` | Airline logo by ICAO code (e.g. `/logos/BAW`) |
| `/flags` | List all country flags (SVG and PNG) |
| `/flags/{code}` | Country flag by ISO code (e.g. `/flags/gb`) |
| `/endpoints` | API documentation with examples |

All URLs use the configured external URL so they work correctly from outside Docker.

---

## 📊 Flight Statistics

Tracks unique flights over time and calculates:

- Unique flights today, yesterday, last 7/30/365 days
- Daily averages per period
- All data persisted as JSON between restarts

---

## 🖼️ Logo Management

Flights includes an automated logo pipeline that keeps airline logos up to date:

- **Missing logo tracking** — when a flight has no matching logo file, the ICAO code is logged to `missing.json` for resolution
- **SVG ↔ PNG sync** — SVG logos are automatically rasterised to 90×90 PNG via cairosvg, with solid backgrounds (white, or dark slate for light logos)
- **AI generation (optional)** — missing logos can be generated using Claude or Gemini, producing clean 80×80 SVG icons matching the existing style
- **Auto-publish** — generated logos are committed, tagged, and pushed to git automatically
- **Weekly updates** — both the hex database and logo resolver run as background threads in the service

Set `LOGO_AI_PROVIDER` and the corresponding API key to enable AI generation (see Environment Variables below).

---

## ⚡ CLI

```
flights service       Run as a long-running service (default, used by Docker)
flights once          Single fetch/enrich/publish cycle, then exit
flights status        Show configuration and check receiver + MQTT connectivity
flights update-data   Download latest hex database from tar1090-db
flights update-logos  Sync logo formats and generate missing logos (--publish to git push)
flights --version     Show version
```

---

## 🐳 Docker

```bash
docker run -d \
  --name flights \
  -p 47475:47475 \
  --add-host=host.docker.internal:host-gateway \
  -e MQTT_BROKER_URL=10.10.10.20 \
  -e DUMP_URL=http://192.168.1.100:30053/ajax/aircraft \
  -e WEB_SERVER_EXTERNAL_URL=http://your-host:47475 \
  -e USER_LAT=51.4627 \
  -e USER_LON=-0.3289 \
  -v /path/to/config:/app/config \
  -v /path/to/data:/app/data \
  -v /path/to/storage:/app/storage \
  -v /path/to/output:/app/output \
  ghcr.io/ronschaeffer/flights:latest
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MQTT_BROKER_URL` | Yes | — | MQTT broker hostname or IP |
| `MQTT_BROKER_PORT` | No | `1883` | MQTT broker port |
| `MQTT_SECURITY` | No | `none` | `none` or `username` |
| `MQTT_USERNAME` | No | — | MQTT username |
| `MQTT_PASSWORD` | No | — | MQTT password |
| `DUMP_URL` | Yes | — | ADS-B receiver URL |
| `WEB_SERVER_EXTERNAL_URL` | No | — | External URL for correct link generation in Docker |
| `USER_LAT` | No | `0.0` | Observer latitude |
| `USER_LON` | No | `0.0` | Observer longitude |
| `CHECK_INTERVAL` | No | `15` | Seconds between receiver checks |
| `HOME_ASSISTANT_ENABLED` | No | `true` | Enable HA MQTT discovery |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOGO_AI_PROVIDER` | No | — | AI provider for logo generation: `claude` or `gemini` |
| `ANTHROPIC_API_KEY` | No | — | API key for Claude logo generation |
| `GEMINI_API_KEY` | No | — | API key for Gemini logo generation |

### Unraid

An Unraid Docker template is included at `unraid/flights.xml`.

---

## 🛠️ Development

```bash
poetry install --with dev   # Install dependencies
make fix                    # Lint + format (ruff)
make test                   # Run pytest (40 tests)
make ci-check               # Full CI check (lint + test)
make install-hooks          # Install pre-commit hooks
```

### Project Structure

```
src/flights/          Main package
  __main__.py         CLI entry point and service loop
  config.py           YAML config with env var overrides
  discovery.py        HA MQTT device-bundle discovery
  enricher.py         Flight data enrichment engine
  hex_lookup.py       ICAO hex code → aircraft lookup (tar1090-db)
  logo_resolver.py    Logo sync, AI generation, and git publishing
  counts.py           Flight statistics and persistence
  mqtt_client.py      MQTT publisher setup (ha-mqtt-publisher)
  server.py           FastAPI web server
tests/                40 pytest tests
config/               YAML configuration files
data/                 Airlines, aircraft, hex database
assets/               Airline logos (SVG/PNG), country flags, web assets
ha_automations/       Example HA automations
unraid/               Unraid Docker template
```

---

## 📡 MQTT Topics

| Topic | Retained | Description |
|---|---|---|
| `flights/visible` | Yes | Visible aircraft count and statistics |
| `flights/closest` | Yes | Closest aircraft with full enriched data |
| `flights/status` | Yes | Service status, health checks, version |
| `flights/availability` | Yes | Device online/offline (LWT) |
| `flights/cmd/refresh` | No | Refresh command (subscribe) |

---

## 🔧 Configuration

Copy `config/config.yaml.example` to `config/config.yaml` and edit. All settings can be overridden with environment variables (prefixed with `FLIGHTS_` or bare).

See `config/config.yaml.example` for the full configuration reference.
