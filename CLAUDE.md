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
tests/               pytest tests
config/              YAML config files
data/                airlines/aircraft databases
assets/              logos, flags, web assets
unraid/              Unraid Docker template XML
```

## CI

`ci.yml`: lint + test on Python 3.11 and 3.12.
`docker-publish.yml`: build and push to GHCR on `v*` tag.

## Docker / Unraid

See `unraid/flights.xml` for the Unraid template.
Set `WEB_SERVER_EXTERNAL_URL` to your host IP for correct URL generation.

## Coding conventions

- Line length: 88, quote style: double
- ruff isort with `force-sort-within-sections`
- No f-strings in logging calls (G004 enforced)
