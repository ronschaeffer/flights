#!/usr/bin/env python3

import uvicorn
import subprocess  # Add this line
import os
import json
import yaml
import logging
import traceback
from fastapi import FastAPI, Response, HTTPException, Request
import glob
from fastapi.staticfiles import StaticFiles

# Define base directory once at the top
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Use output directory from main application - don't create it here
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')  # Only define the path, don't create directory

# Removed unused JSON file path variables
# STATISTICS_JSON_FILE_PATH = os.path.join(OUTPUT_DIR, 'statistics.json')
# CLOSEST_AIRCRAFT_JSON_FILE_PATH = os.path.join(OUTPUT_DIR, 'closest_aircraft.json')
# ALL_AIRCRAFT_JSON_FILE_PATH = os.path.join(OUTPUT_DIR, 'all_aircraft.json')

# Use absolute path for logging
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Load configuration
config_path = os.path.join(BASE_DIR, 'config/config.yaml')
with open(config_path, 'r') as config_file:
    config = yaml.safe_load(config_file)

# Add DEFAULT_IMAGE_FORMAT initialization
DEFAULT_IMAGE_FORMAT = config.get('IMAGE_FORMAT', 'svg').lower()

logger = logging.getLogger('flights_server')
logger.setLevel(getattr(logging, 'ERROR'.upper()))

# Configure logging
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'flights.log'),
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI()

# Add global port variable near the top after imports
SERVER_PORT = 8000  # Default value

def get_lan_ip():
    """Get the machine's LAN IP address."""
    import socket
    try:
        # Create a UDP socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to an external IP address
        s.connect(('8.8.8.8', 80))
        # Get the local IP address
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'  # Fallback to localhost

# Add base_url initialization after get_lan_ip is defined
base_url = f"http://{get_lan_ip()}:{SERVER_PORT}"

def get_file_content(file_path, media_type):
    try:
        if os.path.exists(file_path):
            with open(file_path, "rb" if "image" in media_type else "r") as file:
                content = file.read()
            return Response(content=content, media_type=media_type)
        else:
            logger.error(f"File not found: {file_path}")
            raise HTTPException(status_code=404, detail=f"File '{file_path}' not found")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error")

def try_file_with_ext(base_dir, filename, primary_ext=None, fallback_ext=None, none_fallback=False):
    """Try to find file with primary extension, fallback to secondary if not found."""
    name = os.path.splitext(filename)[0]
    
    primary_ext = primary_ext or f'.{DEFAULT_IMAGE_FORMAT}'
    fallback_ext = fallback_ext or ('.svg' if DEFAULT_IMAGE_FORMAT == 'png' else '.png')
    
    # Try primary extension
    primary_path = os.path.join(base_dir, primary_ext.lstrip('.'), name + primary_ext)
    if (os.path.exists(primary_path)):
        return primary_path, "image/svg+xml" if primary_ext == '.svg' else "image/png"
    
    # Fallback to secondary extension
    fallback_path = os.path.join(base_dir, fallback_ext.lstrip('.'), name + fallback_ext)
    if (os.path.exists(fallback_path)):
        return fallback_path, "image/svg+xml" if fallback_ext == '.svg' else "image/png"
    
    if (none_fallback):
        # Final fallback to _NONE
        none_primary_path = os.path.join(base_dir, primary_ext.lstrip('.'), "_NONE" + primary_ext)
        if (os.path.exists(none_primary_path)):
            return none_primary_path, "image/svg+xml" if primary_ext == '.svg' else "image/png"
        
        none_fallback_path = os.path.join(base_dir, fallback_ext.lstrip('.'), "_NONE" + fallback_ext)
        if (os.path.exists(none_fallback_path)):
            return none_fallback_path, "image/svg+xml" if fallback_ext == '.svg' else "image/png"
        
    return None, None

def get_directory_listing(base_dir, ext=None, strip_ext=False):
    """Get list of files in directory with optional extension filtering."""
    pattern = os.path.join(base_dir, f'*.{ext}' if ext else '*')
    files = glob.glob(pattern)
    if (strip_ext):
        return [os.path.splitext(os.path.basename(f))[0] for f in files]
    return [os.path.basename(f) for f in files]

def get_url_for_file(path: str, filename: str, ext: str = None, port: int = None) -> str:
    """Generate full URL for a file."""
    try:
        port = port or SERVER_PORT  # Use provided port or default to SERVER_PORT
        host = getattr(app.state, 'host', get_lan_ip())
        base_url = f"http://{host}:{port}"  # Use the correct port
        
        # Clean up path components
        path = path.strip('/')
        parts = [base_url]
        if (path):
            parts.append(path)
        parts.append(filename)
        if (ext):
            parts[-1] = f"{parts[-1]}.{ext}"
        else:
            parts[-1] = f"{parts[-1]}.{DEFAULT_IMAGE_FORMAT}"  # Use default format
                
        # Join with single slashes
        return '/'.join(parts).replace(':/', '://')
    except Exception as e:
        logger.error(f"Error generating URL: {str(e)}, falling back to relative path")
        parts = [part.strip('/') for part in [path, filename] if part]
        if (ext):
            parts[-1] = f"{parts[-1]}.{ext}"
        else:
            parts[-1] = f"{parts[-1]}.{DEFAULT_IMAGE_FORMAT}"  # Use default format
        return '/'.join(parts)

def create_html_list(title: str, items: dict) -> str:
    """Create HTML page with clickable links and an optional banner."""
    html = f"""
    <html>
        <head>
            <title>{title}</title>
            <style>
                body {{ font-family: sans-serif; margin: 20px; position: relative; padding-top: 60px; }} /* Adjusted padding-top */
                h1 {{ color: #333; }} /* Removed margin-top */
                .section {{ margin: 20px 0; }}
                a {{ color: #0066cc; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                /* Banner Styles */
                .banner-container {{
                    display: flex;
                    align-items: center;
                    position: absolute;
                    top: 10px;
                    left: 10px;
                }}
                .banner {{
                    width: 50px; /* Adjust the size as needed */
                    margin-right: 10px;
                }}
                .banner-text {{
                    font-size: 36px; /* Increased font size */
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
    """
    
    # Path to the banner image
    banner_path = "/assets/.web/flights.svg"  # Corrected path to assets/.web
    
    # Add banner if flights.svg exists and make it a link to the base URL
    banner_full_path = os.path.join(BASE_DIR, 'assets/.web/flights.svg')
    if os.path.exists(banner_full_path):
        base_url = f"http://{get_lan_ip()}:{SERVER_PORT}/"  # Generate dynamic base URL
        html += f'''
        <div class="banner-container">
            <a href="{base_url}">
                <img src="{banner_path}" alt="Banner" class="banner"/>
            </a>
            <div class="banner-text">Flights</div>
        </div>
        <br><br> <!-- Insert two lines below the banner -->
        '''
    
    html += f"""
            <h1>{title}</h1>
            <br> <!-- Add this line to create a blank line -->
    """
    
    for section, links in items.items():
        if links:  # Only show sections with content
            html += f'<div class="section"><h2>{section}</h2><ul>'
            if isinstance(links, dict):
                for name, url in links.items():
                    html += f'<li><a href="{url}">{name}</a></li>'
            else:
                for item in links:
                    html += f'<li><a href="{item}">{item}</a></li>'
            html += '</ul></div>'
    
    html += "</body></html>"
    return html

@app.get("/")
async def list_json_files(request: Request):
    """List all available JSON files."""
    try:
        base_directory = OUTPUT_DIR
        if not os.path.exists(base_directory):
            data = {"files": {}}
        else:
            files = get_directory_listing(base_directory, ext='json', strip_ext=True)
            data = {
                "Output JSON Files": {
                    file: get_url_for_file("", file, ext='json', port=SERVER_PORT) for file in sorted(files)
                },
                "Image Files": {
                    "Airline Logos": f"http://{get_lan_ip()}:{SERVER_PORT}/logos/",
                    "Country Flags": f"http://{get_lan_ip()}:{SERVER_PORT}/flags/"
                }
            }

        # Return HTML for browsers, JSON for API requests
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            # Pass the entire data dictionary to include all sections
            html = create_html_list("Main menu", data)  # Updated title for clarity
            return Response(content=html, media_type="text/html")
        return data
    except Exception as e:
        logger.error(f"Error listing JSON files: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Error listing files")

@app.get("/logos")
async def list_logos(request: Request):
    """List all available airline logos."""
    try:
        base_directory = os.path.join(BASE_DIR, 'assets/images/logos')
        if (not os.path.exists(base_directory)):
            return {"airlines": [], "formats": {"svg": {}, "png": {}}}
            
        svg_dir = os.path.join(base_directory, 'svg')
        png_dir = os.path.join(base_directory, 'png')
        
        svg_files = get_directory_listing(svg_dir, ext='svg', strip_ext=True) if os.path.exists(svg_dir) else []
        png_files = get_directory_listing(png_dir, ext='png', strip_ext=True) if os.path.exists(png_dir) else []
        
        airlines = sorted(set(svg_files + png_files))
        data = {
            "airlines": airlines,
            "formats": {
                "svg": {
                    file: get_url_for_file("logos", file, "svg", port=SERVER_PORT)  # Pass SERVER_PORT
                    for file in sorted(svg_files)
                },
                "png": {
                    file: get_url_for_file("logos", file, "png", port=SERVER_PORT)  # Pass SERVER_PORT
                    for file in sorted(png_files)
                }
            }
        }
        
        accept = request.headers.get("accept", "")
        if ("text/html" in accept):
            html = create_html_list("Available Airline Logos", {
                "SVG Files": data["formats"]["svg"],
                "PNG Files": data["formats"]["png"]
            })
            return Response(content=html, media_type="text/html")
        return data
    except Exception as e:
        logger.error(f"Error listing logos: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Error listing files")

@app.get("/flags")
async def list_flags(request: Request):
    """List all available country flags."""
    try:
        base_directory = os.path.join(BASE_DIR, 'assets/images/flags')
        if (not os.path.exists(base_directory)):
            return {"countries": [], "formats": {"svg": {}, "png": {}}}
            
        svg_dir = os.path.join(base_directory, 'svg')
        png_dir = os.path.join(base_directory, 'png')
        
        svg_files = get_directory_listing(svg_dir, ext='svg', strip_ext=True) if os.path.exists(svg_dir) else []
        png_files = get_directory_listing(png_dir, ext='png', strip_ext=True) if os.path.exists(png_dir) else []
        
        countries = sorted(set(svg_files + png_files))
        data = {
            "countries": countries,
            "formats": {
                "svg": {
                    file: get_url_for_file("flags", file, "svg", port=SERVER_PORT)  # Pass SERVER_PORT
                    for file in sorted(svg_files)
                },
                "png": {
                    file: get_url_for_file("flags", file, "png", port=SERVER_PORT)  # Pass SERVER_PORT
                    for file in sorted(png_files)
                }
            }
        }
        
        accept = request.headers.get("accept", "")
        if ("text/html" in accept):
            html = create_html_list("Available Country Flags", {
                "SVG Files": data["formats"]["svg"],
                "PNG Files": data["formats"]["png"]
            })
            return Response(content=html, media_type="text/html")
        return data
    except Exception as e:
        logger.error(f"Error listing flags: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Error listing files")

@app.get("/favicon.ico")
async def get_favicon():
    """Serve the favicon.ico file if it exists."""
    try:
        favicon_path = os.path.join(BASE_DIR, 'assets', '.web', 'favicon.ico')  # Changed directory name to .web
        # Log full debug info
        logger.error(f"Favicon debug info:")
        logger.error(f"BASE_DIR: {BASE_DIR}")
        logger.error(f"Full path: {favicon_path}")
        logger.error(f"Parent exists: {os.path.exists(os.path.dirname(favicon_path))}")
        logger.error(f"File exists: {os.path.exists(favicon_path)}")
        if os.path.exists(favicon_path):
            logger.error(f"File permissions: {oct(os.stat(favicon_path).st_mode)[-3:]}")
        
        if not os.path.exists(favicon_path):
            logger.error("Favicon file not found")
            return Response(status_code=404)
        
        try:
            with open(favicon_path, "rb") as f:
                content = f.read()
            return Response(content=content, media_type="image/x-icon")
        except (IOError, OSError) as e:
            logger.error(f"IO Error reading favicon: {str(e)}")
            return Response(status_code=500, content="Internal server error")
            
    except Exception as e:
        logger.error(f"Favicon error: {str(e)}\n{traceback.format_exc()}")
        return Response(status_code=500, content="Internal server error")

@app.get("/{file_name}")
async def read_output_file(file_name: str):
    """Read and return the specified JSON file."""
    base_directory = OUTPUT_DIR
    if (".." in file_name or file_name.startswith("/")):
        raise HTTPException(status_code=400, detail="Invalid file name")
    
    # Modify to not append '.json' if already present
    file_path = os.path.join(
        base_directory, 
        f"{file_name}.json" if not file_name.endswith('.json') else file_name
    )
    
    if (not os.path.abspath(file_path).startswith(os.path.abspath(base_directory))):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    return get_file_content(file_path, "application/json")

@app.get("/logos/{file_name}")
async def read_logo_file(file_name: str):
    name, ext = os.path.splitext(file_name)
    ext = ext.lower() if ext else ''
    
    if (ext and ext not in ['.png', '.svg']):
        raise HTTPException(status_code=400, detail="Invalid file extension")
        
    base_directory = os.path.join(BASE_DIR, 'assets/images/logos')
    if (".." in file_name or file_name.startswith("/")):
        raise HTTPException(status_code=400, detail="Invalid file name")

    if (ext):
        # Specific extension requested
        dir_path = os.path.join(base_directory, ext.lstrip('.'))
        file_path = os.path.join(dir_path, name.upper() + ext)
        media_type = "image/svg+xml" if ext == '.svg' else "image/png"
    else:
        # Use default image format for primary_ext
        primary_ext = f'.{DEFAULT_IMAGE_FORMAT}'
        fallback_ext = '.svg' if DEFAULT_IMAGE_FORMAT == 'png' else '.png'
        file_path, media_type = try_file_with_ext(
            base_directory, 
            name.upper(),
            primary_ext=primary_ext,
            fallback_ext=fallback_ext,
            none_fallback=True
        )
        if (not file_path):
            raise HTTPException(status_code=404, detail="Image not found in any format")

    if (not os.path.abspath(file_path).startswith(os.path.abspath(base_directory))):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    return get_file_content(file_path, media_type)

@app.get("/flags/{file_name}")
async def read_flag_file(file_name: str):
    name, ext = os.path.splitext(file_name)
    ext = ext.lower() if ext else ''
    
    if (ext and ext not in ['.png', '.svg']):
        raise HTTPException(status_code=400, detail="Invalid file extension")
        
    base_directory = os.path.join(BASE_DIR, 'assets/images/flags')
    if (".." in file_name or file_name.startswith("/")):
        raise HTTPException(status_code=400, detail="Invalid file name")

    if (ext):
        # Specific extension requested
        dir_path = os.path.join(base_directory, ext.lstrip('.'))
        file_path = os.path.join(dir_path, name.lower() + ext)
        media_type = "image/svg+xml" if ext == '.svg' else "image/png"
    else:
        # Try PNG first, fallback to SVG
        file_path, media_type = try_file_with_ext(base_directory, name.lower(), primary_ext='.png', fallback_ext='.svg')
        if (not file_path):
            raise HTTPException(status_code=404, detail="Image not found in either PNG or SVG format")

    if (not os.path.abspath(file_path).startswith(os.path.abspath(base_directory))):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    return get_file_content(file_path, media_type)

# Mount the .web directory to serve static files
app.mount("/assets/.web", StaticFiles(directory=os.path.join(BASE_DIR, "assets/.web")), name="web_assets")

def kill_process_on_port(port):
    """Kill any process using the specified port owned by the current user."""
    try:
        result = subprocess.check_output(f"netstat -nlp 2>/dev/null | grep :{port}", shell=True).decode()
        for line in result.splitlines():
            parts = line.split()
            pid_info = parts[-1]
            if ("/" in pid_info):
                pid = int(pid_info.split("/")[0])
                try:
                    os.kill(pid, 9)
                except PermissionError:
                    pass
    except subprocess.CalledProcessError:
        pass
    except Exception as e:
        logger.error(f"Error killing process on port {port}: {str(e)}\n{traceback.format_exc()}")
        raise

def get_lan_ip():
    """Get the machine's LAN IP address."""
    import socket
    try:
        # Create a UDP socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to an external IP address
        s.connect(('8.8.8.8', 80))
        # Get the local IP address
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'  # Fallback to localhost

def print_endpoints():
    """Print all available API endpoints to the console."""
    print("\nAvailable API endpoints:")
    print("------------------------")
    for route in app.routes:
        if (hasattr(route, "methods")):
            methods = ", ".join(route.methods)
            print(f"{methods:<10} http://{app.state.host}:{app.state.port}{route.path}")
    print()

def start_server(request_port, log_level='ERROR', default_image_format='svg'):
    global SERVER_PORT, DEFAULT_IMAGE_FORMAT  # Declare as global
    SERVER_PORT = request_port  # Set the port globally
    DEFAULT_IMAGE_FORMAT = default_image_format  # Set the default image format
    logger.setLevel(getattr(logging, log_level.upper()))  # Update logger level
    try:
        kill_process_on_port(request_port)
        lan_ip = get_lan_ip()
        print(f"\nStarting server on {lan_ip}:{request_port}")
        app.state.port = request_port  # Keep this for compatibility
        app.state.host = lan_ip
        print_endpoints()
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=request_port
        )
    except Exception as e:
        logger.error(f"Failed to start server on port {request_port}: {str(e)}\n{traceback.format_exc()}")
        raise  # Keep this one
    
def main():
    parser = argparse.ArgumentParser(description="Start the Flights Server")
    parser.add_argument('--port', type=int, default=8000, help='Port number to run the server on')
    parser.add_argument('--log_level', type=str, default='ERROR', help='Logging level')
    args = parser.parse_args()
    
    start_server(request_port=args.port, log_level=args.log_level)

if __name__ == "__main__":
    main()