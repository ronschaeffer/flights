# Standard library imports
import subprocess
import os
import json

# Third-party imports
from fastapi import FastAPI, Response, HTTPException

# Local application/library-specific imports

app = FastAPI()

def get_file_content(file_path, media_type):
    if os.path.exists(file_path):
        with open(file_path, "rb" if "image" in media_type else "r") as file:
            content = file.read()
        return Response(content=content, media_type=media_type)
    else:
        raise HTTPException(status_code=404, detail=f"File '{file_path}' not found")

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
        result = subprocess.check_output(f"netstat -nlp | grep :{port}", shell=True).decode()
        for line in result.splitlines():
            parts = line.split()
            pid_info = parts[-1]  # Typically the last part contains PID/Program
            if "/" in pid_info:
                pid = int(pid_info.split("/")[0])  # Extract PID
                try:
                    os.kill(pid, 9)  # Send SIGKILL to the process
                except PermissionError:
                    print(f"Permission denied to kill process {pid}. Skipping...")
    except subprocess.CalledProcessError:
        pass  # If no process is found using the port, do nothing

def start_server(request_port):
    kill_process_on_port(request_port)
    subprocess.run([
        "uvicorn",
        "flights_server:app",
        "--host", "0.0.0.0",
        "--port", str(request_port)
    ])