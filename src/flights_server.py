#!/usr/bin/env python3

import subprocess
import os
import json
import yaml
import logging
import traceback
from fastapi import FastAPI, Response, HTTPException

# Use absolute path for logging
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Load config first to get log level
config_path = os.path.join(os.path.dirname(__file__), '../config/config.yaml')
with open(config_path, 'r') as config_file:
    config = yaml.safe_load(config_file)

logger = logging.getLogger('flights_server')
logger.setLevel(getattr(logging, config.get('LOG_LEVEL', 'ERROR').upper()))

# Configure logging
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'flights.log'),
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI()

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

@app.get("/output/{file_name}")
async def read_json_file(file_name: str):
    base_directory = os.path.join(os.path.dirname(__file__), "../output")
    if ".." in file_name or file_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file name")
    file_path = os.path.join(base_directory, f"{file_name}.json")
    if not os.path.abspath(file_path).startswith(os.path.abspath(base_directory)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    return get_file_content(file_path, "application/json")

@app.get("/{file_name}")
async def read_output_file(file_name: str):
    base_directory = os.path.join(os.path.dirname(__file__), "../output")
    if ".." in file_name or file_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file name")
    file_path = os.path.join(base_directory, f"{file_name}.json")
    if not os.path.abspath(file_path).startswith(os.path.abspath(base_directory)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    return get_file_content(file_path, "application/json")

@app.get("/logos/{file_name}")
async def read_logo_file(file_name: str):
    base_directory = os.path.join(os.path.dirname(__file__), "../assets/images/logos")
    if ".." in file_name or file_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file name")
    file_name = file_name.rsplit(".", 1)[0].upper() + ".png"
    file_path = os.path.join(base_directory, file_name)
    if not os.path.abspath(file_path).startswith(os.path.abspath(base_directory)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    return get_file_content(file_path, "image/png")

@app.get("/flags/{file_name}")
async def read_flag_file(file_name: str):
    base_directory = os.path.join(os.path.dirname(__file__), "../assets/images/flags")
    if ".." in file_name or file_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file name")
    file_name = file_name.rsplit(".", 1)[0].lower() + ".png"
    file_path = os.path.join(base_directory, file_name)
    if not os.path.abspath(file_path).startswith(os.path.abspath(base_directory)):
        raise HTTPException(status_code=400, detail="Invalid file path")
    return get_file_content(file_path, "image/png")

def kill_process_on_port(port):
    """Kill any process using the specified port owned by the current user."""
    try:
        result = subprocess.check_output(f"netstat -nlp 2>/dev/null | grep :{port}", shell=True).decode()
        for line in result.splitlines():
            parts = line.split()
            pid_info = parts[-1]
            if "/" in pid_info:
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

def start_server(request_port, log_level='ERROR'):
    logger.setLevel(getattr(logging, log_level.upper()))
    try:
        kill_process_on_port(request_port)
        subprocess.run([
            "uvicorn",
            "flights_server:app",
            "--host", "0.0.0.0",
            "--port", str(request_port)
        ])
    except Exception as e:
        logger.error(f"Failed to start server on port {request_port}: {str(e)}\n{traceback.format_exc()}")
        raise