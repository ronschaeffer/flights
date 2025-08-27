#!/bin/bash
# Run the flights application

echo "🚀 Starting flights application..."

# Check if config exists
if [ ! -f "config/config.yaml" ]; then
    echo "⚠️  Warning: config/config.yaml not found"
    echo "Please ensure configuration is set up correctly"
fi

# Run the main application
python src/flights.py