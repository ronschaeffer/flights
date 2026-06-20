"""Tests for the web server."""

import time as _time

from fastapi.testclient import TestClient
from ha_mqtt_publisher import HealthTracker
import pytest

from flights.server import _server_config, app, attach_health_router

# Mount the health router once at module import time so /health and
# /health/mqtt exist for the TestClient. Tests use a permanently-healthy
# tracker so the basic /health route returns 200.
_test_tracker = HealthTracker(max_publish_age_seconds=3600)
_test_tracker.state.connected = True
_test_tracker.state.last_publish_success_at = _time.time()
try:
    attach_health_router(_test_tracker)
except Exception:
    # Idempotent: ignore if already attached on a re-import
    pass


@pytest.fixture(autouse=True)
def _setup_server_config():
    """Configure server for testing."""
    _server_config["port"] = 47475
    _server_config["external_url"] = "http://test-host:47475"
    _server_config["image_format"] = "svg"


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """Health check returns 200."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_json(client):
    """Root endpoint returns JSON for API clients."""
    response = client.get("/", headers={"accept": "application/json"})
    assert response.status_code == 200
    data = response.json()
    # If no output dir, returns empty files
    assert isinstance(data, dict)


def test_root_html(client):
    """Root endpoint returns HTML for browsers."""
    response = client.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_endpoints_json(client):
    """Endpoints listing returns proper JSON."""
    response = client.get("/endpoints.json")
    assert response.status_code == 200
    data = response.json()
    assert "available_endpoints" in data
    endpoints = data["available_endpoints"]
    assert "/" in endpoints
    assert "/health" in endpoints


def test_external_url_used_in_endpoints(client):
    """Endpoints use configured external URL, not internal IP."""
    response = client.get("/endpoints.json")
    data = response.json()
    endpoints = data["available_endpoints"]
    # All examples should use the configured external URL
    for _path, info in endpoints.items():
        if "example" in info:
            assert "test-host:47475" in info["example"]
        if "examples" in info:
            for example in info["examples"]:
                assert "test-host:47475" in example


def test_logos_endpoint(client):
    """Logos endpoint returns data."""
    response = client.get("/logos", headers={"accept": "application/json"})
    assert response.status_code == 200


def test_flags_endpoint(client):
    """Flags endpoint returns data."""
    response = client.get("/flags", headers={"accept": "application/json"})
    assert response.status_code == 200


def test_404_json_file(client):
    """Non-existent JSON file returns 404."""
    response = client.get("/nonexistent_file")
    assert response.status_code == 404


def test_invalid_file_name(client):
    """Path traversal attempt is rejected."""
    response = client.get("/../etc/passwd")
    assert response.status_code in (400, 404)


def test_favicon(client):
    """Favicon returns 200 if file exists, 404 otherwise."""
    response = client.get("/favicon.ico")
    assert response.status_code in (200, 404)


def test_dashboard_returns_html(client):
    """Dashboard endpoint returns a self-contained HTML page."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Visible Flights" in body
    assert "all_aircraft.json" in body
    assert "renderFlights" in body


def test_dashboard_in_endpoints(client):
    """Dashboard appears in the endpoints listing."""
    response = client.get("/endpoints.json")
    data = response.json()
    assert "/dashboard" in data["available_endpoints"]


# ---------------------------------------------------------------------------
# AI on-demand logo generation tests
# ---------------------------------------------------------------------------


def test_logo_ai_fallback_serves_none_placeholder_when_disabled(
    client, tmp_path, monkeypatch
):
    """With generation disabled and no logo/cache, the _NONE placeholder is served (200).

    The HA dashboard's picture: field expects an image for every airline, so an
    unknown ICAO must still resolve to the _NONE placeholder rather than a 404
    (which would render as a broken image). generate_logo_on_demand returns None
    when LOGO_AI_PROVIDER is unset, and the server falls through to _NONE.
    """
    import flights.logo_resolver as lr

    called = []

    def mock_generate(icao_code, airline_name=None):
        called.append(icao_code)
        return None  # disabled — no generation

    monkeypatch.delenv("LOGO_AI_PROVIDER", raising=False)
    monkeypatch.setattr(lr, "generate_logo_on_demand", mock_generate)

    cache_dir = tmp_path / "logo-cache"
    cache_dir.mkdir()
    monkeypatch.setattr(lr, "LOGO_CACHE_DIR", str(cache_dir))

    # XYZNOTEXIST has no static logo and no cache entry -> _NONE placeholder
    response = client.get("/logos/XYZNOTEXIST")
    assert response.status_code == 200
    # _NONE placeholder is served (svg or png — both ship as assets)
    assert response.headers["content-type"] in ("image/png", "image/svg+xml")
    # generation was attempted exactly once (cache miss) before the _NONE fallback
    assert called == ["XYZNOTEXIST"]


def test_logo_ai_fallback_serves_cached_png(client, tmp_path, monkeypatch):
    """When a cached PNG exists in LOGO_CACHE_DIR it is served directly."""
    from PIL import Image

    import flights.logo_resolver as lr

    # Write a tiny 1x1 PNG into a temp cache dir
    cache_dir = tmp_path / "logo-cache"
    cache_dir.mkdir()
    png_path = cache_dir / "XYZNOTEXIST.png"
    img = Image.new("RGB", (1, 1), color=(255, 0, 0))
    img.save(str(png_path))

    monkeypatch.setattr(lr, "LOGO_CACHE_DIR", str(cache_dir))

    # Mock generate_logo_on_demand to return the cached path (cache hit branch)
    monkeypatch.setattr(
        lr, "generate_logo_on_demand", lambda code, airline_name=None: str(png_path)
    )

    response = client.get("/logos/XYZNOTEXIST")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_logo_ai_fallback_calls_generate_on_demand(client, tmp_path, monkeypatch):
    """On cache miss, generate_logo_on_demand is called and its PNG result is served."""
    from PIL import Image

    import flights.logo_resolver as lr

    cache_dir = tmp_path / "logo-cache"
    cache_dir.mkdir()
    generated_png = cache_dir / "XYZNOTEXIST.png"

    def mock_generate(icao_code, airline_name=None):
        img = Image.new("RGB", (1, 1), color=(0, 0, 255))
        img.save(str(generated_png))
        return str(generated_png)

    monkeypatch.setattr(lr, "LOGO_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(lr, "generate_logo_on_demand", mock_generate)

    response = client.get("/logos/XYZNOTEXIST")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
