#!/bin/bash

docker run -d \
  --name flights \
  --restart always \
  -p 47474:47474 \
  -w /app/src \
  ghcr.io/ronschaeffer/flights:latest

# Make the script executable:  chmod +x docker_run_flights.sh
# Run the script:  ./docker_run_flights.sh
