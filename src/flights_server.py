# Standard library imports
import subprocess
import os
import json

# Third-party imports
from fastapi import FastAPI, Response

# Local application/library-specific imports

app = FastAPI()

def get_file_content(file_path, media_type):
    if os.path.exists(file_path):
        with open(file_path, "rb" if "image" in media_type else "r") as file:
            content = file.read()
        return Response(content=content, media_type=media_type)
    else:
        return {"msg": f"File '{file_path}' not found"}

@app.get("/output/{file_name}")
async def read_json_file(file_name: str):
    file_name = file_name.replace(".json", "")
    file_path = f"../output/{file_name}.json"
    return get_file_content(file_path, "application/json")

@app.get("/logos/{file_name}")
async def read_logo_file(file_name: str):
    file_name = file_name.rsplit(".", 1)[0].upper() + ".png"
    file_path = f"../assets/logos/{file_name}"
    return get_file_content(file_path, "image/png")

@app.get("/flags/{file_name}")
async def read_flag_file(file_name: str):
    file_name = file_name.rsplit(".", 1)[0].lower() + ".png"
    file_path = f"../assets/flags/{file_name}"
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
        "flights_server_module:app",
        "--host", "0.0.0.0",
        "--port", str(request_port)
    ])
