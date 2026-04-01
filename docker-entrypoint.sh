#!/bin/sh
set -e

# Seed config on first run
if [ ! -f /app/config/config.yaml ]; then
    echo "First run: seeding config from defaults..."
    cp /app/config-defaults/config.yaml /app/config/config.yaml
fi

exec "$@"
