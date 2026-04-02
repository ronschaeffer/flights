"""FastAPI server for flight data and static assets."""

from glob import glob
import logging
import os
import socket

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from flights.config import BASE_DIR

logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join(BASE_DIR, "output")

app = FastAPI()

# Module-level state set by start_server()
_server_config = {
    "port": 8000,
    "external_url": "",
    "image_format": "svg",
}


def get_lan_ip() -> str:
    """Get the machine's LAN IP address (best-effort for non-Docker)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_base_url() -> str:
    """Get the base URL for generating external links.

    Uses external_url config if set (required for Docker),
    falls back to LAN IP detection.
    """
    external = _server_config.get("external_url", "")
    if external:
        return external.rstrip("/")
    port = _server_config["port"]
    return f"http://{get_lan_ip()}:{port}"


def _get_image_format() -> str:
    return _server_config.get("image_format", "svg")


def _try_file_with_ext(
    base_dir: str,
    filename: str,
    primary_ext: str | None = None,
    fallback_ext: str | None = None,
    none_fallback: bool = False,
) -> tuple[str | None, str | None]:
    """Try to find file with primary extension, fallback to secondary."""
    name = os.path.splitext(filename)[0]
    fmt = _get_image_format()
    primary_ext = primary_ext or (f".{fmt}")
    fallback_ext = fallback_ext or (".svg" if fmt == "png" else ".png")

    for ext in (primary_ext, fallback_ext):
        path = os.path.join(base_dir, ext.lstrip("."), name + ext)
        if os.path.exists(path):
            media = "image/svg+xml" if ext == ".svg" else "image/png"
            return path, media

    if none_fallback:
        for ext in (primary_ext, fallback_ext):
            path = os.path.join(base_dir, ext.lstrip("."), "_NONE" + ext)
            if os.path.exists(path):
                media = "image/svg+xml" if ext == ".svg" else "image/png"
                return path, media

    return None, None


def _get_directory_listing(
    base_dir: str, ext: str | None = None, strip_ext: bool = False
) -> list[str]:
    pattern = os.path.join(base_dir, f"*.{ext}" if ext else "*")
    files = glob(pattern)
    if strip_ext:
        return [os.path.splitext(os.path.basename(f))[0] for f in files]
    return [os.path.basename(f) for f in files]


def _get_file_content(file_path: str, media_type: str) -> Response:
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )
    mode = "rb" if "image" in media_type else "r"
    with open(file_path, mode) as f:
        content = f.read()
    return Response(content=content, media_type=media_type)


def _url_for_file(path: str, filename: str, ext: str | None = None) -> str:
    """Generate URL for a file using the configured base URL."""
    base = get_base_url()
    fmt = _get_image_format()
    path = path.strip("/")
    parts = [base]
    if path:
        parts.append(path)
    suffix = ext or fmt
    parts.append(f"{filename}.{suffix}")
    return "/".join(parts)


def _create_html_page(title: str, items: dict) -> str:
    """Create an HTML page with banner navigation."""
    base_url = get_base_url()
    banner_path = "/assets/.web/flights.svg"
    banner_exists = os.path.exists(
        os.path.join(BASE_DIR, "assets", ".web", "flights.svg")
    )

    html = f"""<html><head><title>{title}</title>
<style>
body {{ font-family: sans-serif; margin: 20px; }}
h1 {{ color: #333; font-size: 24px; text-transform: uppercase;
     margin-top: 80px; margin-bottom: 40px; }}
.section {{ margin: 20px 0; }}
a {{ color: #0066cc; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.banner-container {{ display: flex; align-items: center;
  position: fixed; top: 0; left: 0; width: 100%;
  padding: 10px 20px; background: #f8f8f8;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.banner-left {{ display: flex; align-items: center; margin-right: 40px; }}
.banner {{ width: 50px; margin-right: 10px; }}
.banner-text {{ font-size: 32px; font-weight: bold; }}
nav {{ display: flex; align-items: center; }}
nav a {{ margin-left: 20px; font-weight: bold; }}
</style></head><body>"""

    if banner_exists:
        html += f"""<div class="banner-container">
<div class="banner-left">
<a href="{base_url}/"><img src="{banner_path}" alt="Banner" class="banner"/></a>
<div class="banner-text">Flights</div></div>
<nav><a href="/">Home</a><a href="/dashboard">Dashboard</a><a href="/flags">Flags</a>
<a href="/logos">Logos</a><a href="/endpoints">Endpoints</a>
</nav></div>"""

    html += f"<h1>{title}</h1>"

    for section, content in items.items():
        if not content:
            continue
        html += f'<div class="section"><h2>{section}</h2><ul>'
        if isinstance(content, dict):
            for name in sorted(content):
                url = content[name]
                display = os.path.splitext(name)[0]
                html += f'<li><a href="{url}">{display}</a></li>'
        elif isinstance(content, list):
            for item in content:
                html += f'<li><a href="{item}">{item}</a></li>'
        html += "</ul></div>"

    html += "</body></html>"
    return html


def _build_dashboard_html(_base_url: str) -> str:
    """Read the dashboard HTML from the static assets directory."""
    dashboard_path = os.path.join(BASE_DIR, "assets", ".web", "dashboard.html")
    with open(dashboard_path) as f:
        return f.read()


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker HEALTHCHECK."""
    return {"status": "ok"}


@app.get("/")
async def list_json_files(request: Request):
    """List all available JSON files."""
    base_url = get_base_url()
    if not os.path.exists(OUTPUT_DIR):
        data = {"files": {}}
    else:
        files = _get_directory_listing(OUTPUT_DIR, ext="json", strip_ext=True)
        data = {
            "Output JSON Files": {
                f: _url_for_file("", f, ext="json") for f in sorted(files)
            },
            "Image Files": {
                "Airline Logos": f"{base_url}/logos/",
                "Country Flags": f"{base_url}/flags/",
            },
        }

    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return Response(
            content=_create_html_page("Main menu", data),
            media_type="text/html",
        )
    return JSONResponse(content=data)


@app.get("/logos")
async def list_logos(request: Request):
    """List all available airline logos."""
    base_dir = os.path.join(BASE_DIR, "assets", "images", "logos")
    if not os.path.exists(base_dir):
        return {"airlines": [], "formats": {"svg": {}, "png": {}}}

    svg_dir = os.path.join(base_dir, "svg")
    png_dir = os.path.join(base_dir, "png")
    svg_files = (
        _get_directory_listing(svg_dir, ext="svg", strip_ext=True)
        if os.path.exists(svg_dir)
        else []
    )
    png_files = (
        _get_directory_listing(png_dir, ext="png", strip_ext=True)
        if os.path.exists(png_dir)
        else []
    )

    data = {
        "airlines": sorted(set(svg_files + png_files)),
        "formats": {
            "svg": {f: _url_for_file("logos", f, "svg") for f in sorted(svg_files)},
            "png": {f: _url_for_file("logos", f, "png") for f in sorted(png_files)},
        },
    }

    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return Response(
            content=_create_html_page(
                "Available Airline Logos",
                {
                    "SVG Files": data["formats"]["svg"],
                    "PNG Files": data["formats"]["png"],
                },
            ),
            media_type="text/html",
        )
    return data


@app.get("/flags")
async def list_flags(request: Request):
    """List all available country flags."""
    base_dir = os.path.join(BASE_DIR, "assets", "images", "flags")
    if not os.path.exists(base_dir):
        return {"countries": [], "formats": {"svg": {}, "png": {}}}

    svg_dir = os.path.join(base_dir, "svg")
    png_dir = os.path.join(base_dir, "png")
    svg_files = (
        _get_directory_listing(svg_dir, ext="svg", strip_ext=True)
        if os.path.exists(svg_dir)
        else []
    )
    png_files = (
        _get_directory_listing(png_dir, ext="png", strip_ext=True)
        if os.path.exists(png_dir)
        else []
    )

    data = {
        "countries": sorted(set(svg_files + png_files)),
        "formats": {
            "svg": {f: _url_for_file("flags", f, "svg") for f in sorted(svg_files)},
            "png": {f: _url_for_file("flags", f, "png") for f in sorted(png_files)},
        },
    }

    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return Response(
            content=_create_html_page(
                "Available Country Flags",
                {
                    "SVG Files": data["formats"]["svg"],
                    "PNG Files": data["formats"]["png"],
                },
            ),
            media_type="text/html",
        )
    return data


@app.get("/favicon.ico")
async def get_favicon():
    """Serve the favicon."""
    favicon_path = os.path.join(BASE_DIR, "assets", ".web", "favicon.ico")
    if not os.path.exists(favicon_path):
        return Response(status_code=404)
    with open(favicon_path, "rb") as f:
        content = f.read()
    return Response(content=content, media_type="image/x-icon")


def _build_endpoints() -> dict:
    base_url = get_base_url()
    return {
        "/": {
            "description": "Home page with file listing.",
            "example": f"GET {base_url}/",
        },
        "/health": {
            "description": "Health check endpoint.",
            "example": f"GET {base_url}/health",
        },
        "/logos": {
            "description": "List airline logos (SVG/PNG).",
            "example": f"GET {base_url}/logos",
        },
        "/flags": {
            "description": "List country flags (SVG/PNG).",
            "example": f"GET {base_url}/flags",
        },
        "/{file_name}": {
            "description": "Retrieve a JSON output file.",
            "examples": [
                f"GET {base_url}/closest_aircraft",
                f"GET {base_url}/closest_aircraft.json",
            ],
        },
        "/logos/{file_name}": {
            "description": "Retrieve an airline logo.",
            "examples": [
                f"GET {base_url}/logos/BAW",
                f"GET {base_url}/logos/BAW.svg",
            ],
        },
        "/flags/{file_name}": {
            "description": "Retrieve a country flag.",
            "examples": [
                f"GET {base_url}/flags/gb",
                f"GET {base_url}/flags/gb.svg",
            ],
        },
        "/dashboard": {
            "description": "Live flight dashboard showing 5 closest aircraft.",
            "example": f"GET {base_url}/dashboard",
        },
        "/endpoints": {
            "description": "This page.",
            "example": f"GET {base_url}/endpoints",
        },
    }


@app.get("/dashboard")
async def dashboard():
    """Serve the flight dashboard page."""
    base_url = get_base_url()
    html = _build_dashboard_html(base_url)
    return HTMLResponse(content=html)


@app.get("/endpoints")
async def list_endpoints(request: Request):
    """List all available API endpoints."""
    endpoints = _build_endpoints()
    base_url = get_base_url()

    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        banner_path = "/assets/.web/flights.svg"
        banner_exists = os.path.exists(
            os.path.join(BASE_DIR, "assets", ".web", "flights.svg")
        )

        html = """<html><head><title>API Endpoints</title>
<style>
body { font-family: sans-serif; margin: 20px; }
h1 { color: #333; font-size: 24px; text-transform: uppercase;
     margin-top: 80px; margin-bottom: 40px; }
.endpoint { margin-bottom: 20px; }
.key { font-weight: bold; color: blue; }
.description { display: block; margin-bottom: 10px; }
.example { margin-left: 20px; color: #555; display: block; }
.banner-container { display: flex; align-items: center;
  position: fixed; top: 0; left: 0; width: 100%;
  padding: 10px 20px; background: #f8f8f8;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.banner-left { display: flex; align-items: center;
  margin-right: 40px; }
.banner { width: 50px; margin-right: 10px; }
.banner-text { font-size: 32px; font-weight: bold; }
nav { display: flex; align-items: center; }
nav a { margin-left: 20px; color: #0066cc; text-decoration: none;
  font-weight: bold; }
nav a:hover { text-decoration: underline; }
</style></head><body>"""

        if banner_exists:
            html += (
                '<div class="banner-container">'
                '<div class="banner-left">'
                f'<a href="{base_url}/">'
                f'<img src="{banner_path}" alt="Banner" class="banner"/></a>'
                '<div class="banner-text">Flights</div></div>'
                "<nav>"
                '<a href="/">Home</a>'
                '<a href="/dashboard">Dashboard</a>'
                '<a href="/flags">Flags</a>'
                '<a href="/logos">Logos</a>'
                '<a href="/endpoints">Endpoints</a>'
                "</nav></div>"
            )

        html += "<h1>API Endpoints</h1>"
        for path, info in endpoints.items():
            html += '<div class="endpoint">'
            html += (
                '<span class="key">{}</span> <span class="description">{}</span>'
            ).format(path, info["description"])
            if "example" in info:
                html += '<div class="example">Example: {}</div>'.format(info["example"])
            elif "examples" in info:
                for ex in info["examples"]:
                    html += f'<div class="example">Example: {ex}</div>'
            html += "</div>"
        html += "</body></html>"
        return Response(content=html, media_type="text/html")

    return JSONResponse(content={"available_endpoints": endpoints})


@app.get("/endpoints.json")
async def get_endpoints_json():
    """Serve endpoints as JSON."""
    return JSONResponse(content={"available_endpoints": _build_endpoints()})


@app.get("/{file_name}")
async def read_output_file(file_name: str):
    """Read and return a JSON output file."""
    if ".." in file_name or file_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file name")

    # Reject names that collide with named routes (safety net)
    _reserved = {"health", "logos", "flags", "favicon.ico", "endpoints", "dashboard"}
    bare = file_name.removesuffix(".json")
    if bare in _reserved:
        raise HTTPException(status_code=404, detail="Not found")

    if not file_name.endswith(".json"):
        file_name = f"{file_name}.json"
    file_path = os.path.join(OUTPUT_DIR, file_name)

    if not os.path.abspath(file_path).startswith(os.path.abspath(OUTPUT_DIR)):
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    import json

    with open(file_path) as f:
        content = json.load(f)
    formatted = json.dumps(content, indent=2, sort_keys=True)
    return Response(content=formatted, media_type="application/json")


@app.get("/logos/{file_name}")
async def read_logo_file(file_name: str):
    """Serve an airline logo."""
    name, ext = os.path.splitext(file_name)
    ext = ext.lower() if ext else ""

    if ext and ext not in (".png", ".svg"):
        raise HTTPException(status_code=400, detail="Invalid file extension")

    base_dir = os.path.join(BASE_DIR, "assets", "images", "logos")
    if ".." in file_name or file_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file name")

    if ext:
        dir_path = os.path.join(base_dir, ext.lstrip("."))
        file_path = os.path.join(dir_path, name.upper() + ext)
        media_type = "image/svg+xml" if ext == ".svg" else "image/png"
    else:
        file_path, media_type = _try_file_with_ext(
            base_dir, name.upper(), none_fallback=True
        )
        if not file_path:
            raise HTTPException(status_code=404, detail="Image not found")

    if not os.path.abspath(file_path).startswith(os.path.abspath(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid file path")

    return _get_file_content(file_path, media_type)


@app.get("/flags/{file_name}")
async def read_flag_file(file_name: str):
    """Serve a country flag."""
    name, ext = os.path.splitext(file_name)
    ext = ext.lower() if ext else ""

    if ext and ext not in (".png", ".svg"):
        raise HTTPException(status_code=400, detail="Invalid file extension")

    base_dir = os.path.join(BASE_DIR, "assets", "images", "flags")
    if ".." in file_name or file_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file name")

    if ext:
        dir_path = os.path.join(base_dir, ext.lstrip("."))
        file_path = os.path.join(dir_path, name.lower() + ext)
        media_type = "image/svg+xml" if ext == ".svg" else "image/png"
    else:
        file_path, media_type = _try_file_with_ext(
            base_dir,
            name.lower(),
            primary_ext=".png",
            fallback_ext=".svg",
        )
        if not file_path:
            raise HTTPException(status_code=404, detail="Image not found")

    if not os.path.abspath(file_path).startswith(os.path.abspath(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid file path")

    return _get_file_content(file_path, media_type)


# Mount static web assets
_web_assets_dir = os.path.join(BASE_DIR, "assets", ".web")
if os.path.exists(_web_assets_dir):
    app.mount(
        "/assets/.web",
        StaticFiles(directory=_web_assets_dir),
        name="web_assets",
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        html = (
            f"<html><head><title>Error {exc.status_code}</title></head>"
            f"<body><h1>Error {exc.status_code}</h1>"
            f"<p>{exc.detail}</p></body></html>"
        )
        return HTMLResponse(content=html, status_code=exc.status_code)
    return JSONResponse(content={"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        html = (
            "<html><head><title>Error</title></head>"
            "<body><h1>500 Internal Server Error</h1></body></html>"
        )
        return HTMLResponse(content=html, status_code=500)
    return JSONResponse(content={"detail": "Internal Server Error"}, status_code=500)


def start_server(
    port: int,
    log_level: str = "ERROR",
    image_format: str = "svg",
    external_url: str = "",
) -> None:
    """Start the FastAPI server (blocking - run in a thread)."""
    _server_config["port"] = port
    _server_config["image_format"] = image_format.lower()
    _server_config["external_url"] = external_url

    logger.setLevel(getattr(logging, log_level.upper(), logging.ERROR))

    lan_ip = get_lan_ip()
    base_url = get_base_url()
    logger.info("Starting server on %s:%s (base URL: %s)", lan_ip, port, base_url)
    print(f"Starting server on {lan_ip}:{port}")
    print(f"Base URL: {base_url}")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level.lower())
