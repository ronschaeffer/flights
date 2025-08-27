# Changelog

All notable changes to this project will be documented in this file.

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