# CLAUDE.md - flights

## What this is

Containerised Python app that fetches ADS-B aircraft data from a local receiver,
enriches it with airline/airport/route information, publishes to MQTT (Home Assistant),
and serves data via an HTTP API with airline logos and country flags.

## Type: App (not a library)

- Public repo: `ronschaeffer/flights`
- Runs as a Docker container on Unraid (`flights`)
- Docker image: `ghcr.io/ronschaeffer/flights`
- Entry point: `src/flights/__main__.py` via `flights` script

## Dependencies

- `ha-mqtt-publisher` (ronschaeffer/ha_mqtt_publisher)
- `flydenity` (aircraft registration parsing)
- `airportsdata` (airport information)
- `haversine` (distance calculations)
- `shapely` (geographic zone filtering)
- `cairosvg` (SVG → PNG logo conversion)

## Toolchain

Python 3.11+, Poetry, ruff, pytest, pre-commit

## Key commands

```bash
poetry install --with dev   # install deps
make fix                    # lint + format
make test                   # run tests
make ci-check               # lint + test
make install-hooks          # install pre-commit hooks
```

## Structure

```
src/flights/         main package
  hex_lookup.py      ICAO hex → aircraft lookup (tar1090-db, 619K entries)
  logo_resolver.py   logo sync, AI generation (Claude/Gemini), git publishing
  enricher.py        flight enrichment (airlines, aircraft, hex DB, logos)
tests/               pytest tests (40 tests)
config/              YAML config files
data/                airlines, aircraft, hex database (aircraft_hex.csv.gz)
assets/              logos (SVG/PNG), flags, web assets
unraid/              Unraid Docker template XML
```

## Data enrichment pipeline

1. ADS-B receiver provides raw flight data (hex, callsign, position, etc.)
2. Hex DB lookup fills missing registration, type, owner, military flag
3. Airlines/aircraft DB lookup adds airline name, aircraft model
4. Missing data logged only when hex DB can't resolve either
5. Logo existence checked; missing logos tracked for AI generation

## Logo management

- Logos are named by ICAO airline code (e.g. `BAW.svg`, `BAW.png`)
- SVGs: 80×80 viewBox, icon-style, no text/wordmarks
- PNGs: 90×90, solid background (white, or dark slate for light logos)
- Weekly background thread syncs formats and generates missing logos via AI
- AI generation requires: `LOGO_AI_PROVIDER` (claude/gemini) + API key env var
- Generated logos are auto-committed, tagged, and pushed to git

## CI

`ci.yml`: lint + test on Python 3.11 and 3.12.
`docker-publish.yml`: build and push to GHCR on `v*` tag.

## Docker / Unraid

See `unraid/flights.xml` for the Unraid template.
Set `WEB_SERVER_EXTERNAL_URL` to your host IP for correct URL generation.

Container name: `flights`
Image: `ghcr.io/ronschaeffer/flights:latest`
Port: 47474 → 47475
Volumes: config, data, storage, output
Env vars for AI logos: `LOGO_AI_PROVIDER=claude`, `ANTHROPIC_API_KEY=...`

## Ship it checklist

1. `make ci-check` (use Python Workspace or `python3.11 -m poetry` if local Python < 3.11)
2. `make fix`, commit, push to main
3. Increment `v0.x.y` tag, push to trigger `docker-publish.yml`
4. Unraid MCP `update_container` (force=true) — or `docker pull` + recreate
5. Seed data volume if first run: `docker cp <tmp>:/app/data/. /mnt/user/appdata/flights/data/`
6. Verify: container healthy, HA entities active, MQTT publishing

## Coding conventions

- Line length: 88, quote style: double
- ruff isort with `force-sort-within-sections`
- No f-strings in logging calls (G004 enforced)
