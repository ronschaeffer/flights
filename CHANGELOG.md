# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2026-04-01

### Breaking Changes
- Config format changed from flat YAML to nested structure (see config.yaml.example)
- MQTT topics changed from `dev/flights/*` to `flights/*`
- License changed from GPL v3 to MIT
- Old `src/*.py` flat layout replaced with `src/flights/` package

### Added
- `ha-mqtt-publisher` integration (replaces custom MQTT wrapper)
- Stable HA device identifiers (fixes device duplication on restart)
- LWT (Last Will and Testament) for device availability
- `AvailabilityPublisher` for online/offline status
- Configurable external URL for web server (`WEB_SERVER_EXTERNAL_URL`)
- `/health` endpoint for Docker HEALTHCHECK
- Environment variable overrides for all config (`MQTT_BROKER_URL`, etc.)
- Multi-stage Dockerfile with Poetry
- Unraid Docker template (`unraid/flights.xml`)
- `icon.png` at repo root for Unraid template
- Makefile with standard targets (check/fix/test/ci-check)
- pytest test suite (36 tests)
- Pre-commit hooks (ruff, codespell, pre-commit-hooks)
- Docker entrypoint script with config seeding
- GitHub Actions: docker-publish workflow
- `CLAUDE.md` project documentation

### Changed
- Config system: nested YAML with dot-notation access and env var overrides
- MQTT: uses `ha_mqtt_publisher.MQTTPublisher` instead of raw paho-mqtt
- Discovery: uses `ha_mqtt_publisher.Device`/`Sensor` with deterministic IDs
- Web server URLs use configured external URL instead of container-internal IP
- Flight count persistence changed from pickle to JSON
- Ruff config: line-length 88 (was 120), expanded rules including G004
- CI: Poetry-based, tests on Python 3.11 + 3.12

### Fixed
- Device duplication/abandonment in HA (random UUIDs replaced with stable IDs)
- Device not recreated after deletion in HA
- Web server URLs unreachable from outside Docker container
- Deprecated `datetime.utcnow()` replaced with `datetime.now(UTC)`
- Unused computed values in flight_counts removed
- paho-mqtt v2 deprecation warnings

### Removed
- `docker-compose.yml` (use Unraid template or plain docker run)
- `docker_run_flights.sh`
- Custom `MQTTService` class
- Template-based discovery payload generation (`${PLACEHOLDER}` system)
- `generate_unique_id()` (root cause of device duplication)

## [0.2.0] - 2025-08-27

### Highlights
- Home Assistant MQTT discovery now always publishes (ignores existing-file check).
- Centralized configuration via `src/config_manager.py` with lowercase-normalized keys and uppercase fallback.
- Major cleanup of imports/formatting with Ruff; repo-wide pre-commit hooks added.
- FastAPI server hardening and endpoint docs improvements.
- MQTT service reliability improvements and clearer logging.

### Added
- GitHub Actions CI to run Ruff format check and lint on push/PR.
- `.pre-commit-config.yaml` with `ruff` and `ruff-format` hooks.
- `MQTT_HTTP_API_DOCUMENTATION.md` with detailed MQTT/HTTP analysis.

### Changed
- Always publish HA MQTT discovery payload; discovery file presence no longer blocks publishing.
- Standardized config access to lowercase keys in code; uppercase values still supported via fallback.
- Refactored `src/flights.py`, `src/flights_server.py`, `src/mqtt_service.py`, and `src/ha_mqtt_discovery.py` for clarity, error handling, and consistency.
- Normalized import order and whitespace across the repo; enforced by Ruff.

### Fixed
- Various lint issues (unused imports/vars, formatting, path handling).
- More robust favicon/file handling and safer endpoint listings in the server.

### Upgrade notes
- Python 3.11 required (as specified in `pyproject.toml`).
- If you have a local clone, run:
  - `pip install pre-commit && pre-commit install` to enable local hooks.
- Config: continue using your existing YAML; the code now prefers lowercase keys but tolerates uppercase.
- The static discovery JSON file (`config/ha_mqtt_disc_payload.json`) is no longer required and may be regenerated.

[0.2.0]: https://github.com/ronschaeffer/flights/releases/tag/0.2.0