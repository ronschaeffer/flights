from fastapi import FastAPI, Response
import subprocess
import os
import json

app = FastAPI()
request_port = 47474

@app.get("/output/{file_name}")
async def read_json_file(file_name: str):
    file_name = file_name.replace(".json", "")
    file_path = f"./output/{file_name}.json"
    if os.path.exists(file_path):
        with open(file_path) as json_file:
            data = json.load(json_file)
            return Response(content=json.dumps(data, indent=4), media_type="application/json")
    else:
        return {"msg": f"File '{file_name}' not found"}


@app.get("/logos/{file_name}")
async def read_logo_file(file_name: str):
    file_name = file_name.rsplit(".", 1)[0].upper() + ".png"
    file_path = f"./data/logos/42/{file_name}"
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            image_data = f.read()
        return Response(content=image_data, media_type="image/png")
    else:
        return {"msg": f"File '{file_name}' not found"}


@app.get("/flags/{file_name}")
async def read_flag_file(file_name: str):
    file_name = file_name.rsplit(".", 1)[0].lower() + ".png"
    file_path = f"./data/flags/42/{file_name}"
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            image_data = f.read()
        return Response(content=image_data, media_type="image/png")
    else:
        return {"msg": f"File '{file_name}' not found"}


def kill_process_on_port(port):
    """Kill any process using the specified port owned by the current user."""
    try:
        # Use netstat to find processes using the port
        result = subprocess.check_output(f"netstat -nlp | grep :{port}", shell=True).decode()
        for line in result.splitlines():
            parts = line.split()
            pid_info = parts[-1]  # Typically the last part contains PID/Program
            if "/" in pid_info:
                pid = int(pid_info.split("/")[0])  # Extract PID
                # Kill the process if owned by the current user
                try:
                    os.kill(pid, 9)  # Send SIGKILL to the process
                except PermissionError:
                    print(f"Permission denied to kill process {pid}. Skipping...")
    except subprocess.CalledProcessError:
        # If no process is found using the port, do nothing
        pass


if __name__ == '__main__':
    # Ensure the port is free by killing any processes using it
    kill_process_on_port(request_port)
    # Start the Uvicorn server
    subprocess.run([
        "uvicorn",
        "flights_server:app",
        "--host", "0.0.0.0",
        "--port", str(request_port)
    ])
